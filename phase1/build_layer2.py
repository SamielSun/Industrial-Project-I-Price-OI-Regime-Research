#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_layer2 —— 从 raw 数据建第 2 层 4 张标准 1h 表

它在 Phase 1 中的位置：Step 4（见 phase1/guidance.md §1.1 进度表与 §4 流水线）。

做什么
------
  读 data/raw/ 的 1,144 个 parquet，建四张规范化表，按 year/chunk=YYYY-MM 落盘：

    klines_1h       (symbol, ts)         12 列 —— 网格的【定义者】
    mark_index_1h   (symbol, ts)          5 列 —— 左连接到 klines 网格
    oi_1h           (symbol, ts)          5 列 —— 左连接到 klines 网格
    funding         (symbol, ts_funding)  4 列 —— 事件表，独立于网格

核心设计（全部为已决策项，依据见 phase1/guidance.md §7.2）
-----------------------------------------------------------
1. **网格 = klines_1h 实际存在的 ts**。稀疏，不发明行。
   `features_1h`（Step 5）才密集化。

2. **三张网格表的 (symbol, ts) 集合逐一致**。mark/index/oi 里那些
   klines 没有的小时一律丢弃 —— 这同时自然处理了两件事：
     · 下架合约 mark 多写的尾部空行（123,916 行）
     · LUNAUSDT 的 OI 孤立残留（跨到 2024-06，而 klines 止于 2022-05）

3. **OI 终点对齐**：bar [ts, ts_end) 配 OI(ts_end)。
   即 `oi_1h.ts = 源 create_time - 1h`。这是 schema 已定的语义
   （`ts_end` = "OI 对齐时刻 = 决策时刻"）。

4. **funding 落在结算时刻【起的】那根 bar**：`ts_funding == klines.ts`。
   实测 calc_time 截断到整秒后 100% 落在整点、100% 等于某 bar 的 ts。
   `funding_rate` 只在结算时刻有值；`funding_interval_hours` 的
   前向填充在 Step 5 做，不在这张表里。

5. **缺值用 NaN，不填充**：
   · mark/index 缺小时 → `NaN`（价格是连续量，填充等于发明数据）
   · OI 缺快照 → `NaN` + `oi_missing=True`（有这一列就是为了保留"缺"与"不存在"的区分）

6. **全量重建**，不做增量（`layer2_built_at` 留到 §9 真正做增量时再加）。

产出
----
  data/01_layer2/{klines_1h,mark_index_1h,oi_1h,funding}/year=YYYY/chunk=YYYY-MM.parquet
  4 表 × 57 月 = 228 个文件

用法
----
  python phase1/build_layer2.py --sample-end 2026-08-31
  python phase1/build_layer2.py --sample-end 2026-08-31 --subset BTCUSDT

依据：phase1/guidance.md §6（闸）§7.2（四张表）§7.4（validate）§8（质量规则）
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根
import config as cfg_mod                                     # noqa: E402
from lib.schema import LAYER2_SCHEMAS, SchemaViolation, validate   # noqa: E402

# ============================================================================
# 路径
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent

# ⚠️ 输出根目录【必须】由 --out-root 显式给出，不用环境变量。
#    理由：环境变量不跨 shell 调用保留，实测因此把冒烟结果三次写进正式目录
#    （data/01_layer2 被 3 个合约的产出覆盖过两回）。显式参数无法"忘记设置"。
DATA = ROOT / "data"            # 运行时被 --out-root 覆盖
RAW = ROOT / "data" / "raw"     # 运行时被 --raw-root / --out-root 覆盖
L2 = DATA / "01_layer2"
MANIFEST = DATA / "00_config" / "manifest.parquet"
CANDIDATE_POOL = ROOT / "data" / "03_reference" / "candidate_pool.csv"
RUN_INFO = DATA / "00_config" / "sample_end.json"


def configure_paths(out_root: Path, raw_root: Path | None, pool: Path | None) -> None:
    """按命令行参数定路径。必须在 main() 最开头调用。"""
    global DATA, RAW, L2, MANIFEST, CANDIDATE_POOL, RUN_INFO
    DATA = out_root.resolve()
    RAW = (raw_root or (DATA / "raw")).resolve()
    L2 = DATA / "01_layer2"
    MANIFEST = DATA / "00_config" / "manifest.parquet"
    CANDIDATE_POOL = (pool or (ROOT / "data" / "03_reference"
                               / "candidate_pool.csv")).resolve()
    RUN_INFO = DATA / "00_config" / "sample_end.json"

T_START = time.time()


def log(msg: str) -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


# ============================================================================
# 读取 raw
# ============================================================================

def raw_path(src: str, sym: str) -> Path:
    """raw 下某合约的落盘位置（月频一币一文件）。"""
    return RAW / src / f"symbol={sym}.parquet"


def read_monthly(src: str, sym: str) -> pd.DataFrame | None:
    """读月频 raw，附上 symbol 与 ts（datetime64[ns,UTC]）。"""
    p = raw_path(src, sym)
    if not p.exists():
        return None
    df = pq.read_table(p).to_pandas()
    if df.empty:
        return None
    df = df.copy()
    tcol = "open_time" if "open_time" in df.columns else "calc_time"
    df["ts"] = pd.to_datetime(df[tcol], unit="ms", utc=True)
    df["symbol"] = sym
    return df


def read_metrics(sym: str, years: list[int]) -> pd.DataFrame | None:
    """读日频 metrics（按年分文件），只取该合约。"""
    frames = []
    for y in years:
        p = RAW / "metrics" / f"year={y}.parquet"
        if not p.exists():
            continue
        d = pq.read_table(p).to_pandas()
        d = d[d["symbol"] == sym]
        if not d.empty:
            frames.append(d)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    df["ts"] = pd.to_datetime(df["create_time"], utc=True)
    return df


# ============================================================================
# 建四张表（单个合约）
# ============================================================================

def build_symbol(sym: str, years: list[int]
                 ) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """为一个合约建四张表的行。返回 ({表名: DataFrame}, 统计)。"""
    stats: Counter = Counter()
    out: dict[str, pd.DataFrame] = {}

    # ---- 1. klines_1h —— 网格的定义者 ----
    k = read_monthly("klines", sym)
    if k is None or k.empty:
        stats["klines_缺失"] += 1
        return {}, stats

    k = k.sort_values("ts", ignore_index=True)
    grid = k["ts"]
    stats["klines_行"] = len(k)
    out["klines_1h"] = pd.DataFrame({
        "symbol": sym,
        "ts": grid,
        "ts_end": grid + pd.Timedelta(hours=1),
        "open": k["open"].astype("float64"),
        "high": k["high"].astype("float64"),
        "low": k["low"].astype("float64"),
        "close": k["close"].astype("float64"),
        "volume": k["volume"].astype("float64"),
        "quote_volume": k["quote_volume"].astype("float64"),
        "trades": k["count"].astype("float64"),          # ← 源列 count 改名
        "taker_buy_volume": k["taker_buy_volume"].astype("float64"),
        "taker_buy_quote_volume": k["taker_buy_quote_volume"].astype("float64"),
    })

    # ---- 2. mark_index_1h —— 左连接到 klines 网格 ----
    mk = read_monthly("markPriceKlines", sym)
    ix = read_monthly("indexPriceKlines", sym)
    mi = pd.DataFrame({"symbol": sym, "ts": grid})
    if mk is not None:
        a = mk[["ts", "close"]].rename(columns={"close": "mark_close"})
        a = a.drop_duplicates(subset=["ts"], keep="last")
        mi = mi.merge(a, on="ts", how="left")
    if "mark_close" not in mi.columns:
        mi["mark_close"] = float("nan")      # 不能用 pd.NA —— 它 astype("float64") 会抛
    if ix is not None:
        b = ix[["ts", "close"]].rename(columns={"close": "index_close"})
        b = b.drop_duplicates(subset=["ts"], keep="last")
        mi = mi.merge(b, on="ts", how="left")
    if "index_close" not in mi.columns:
        mi["index_close"] = float("nan")
    mi["mark_close"] = mi["mark_close"].astype("float64")
    mi["index_close"] = mi["index_close"].astype("float64")
    stats["mark缺"] = int(mi["mark_close"].isna().sum())
    stats["index缺"] = int(mi["index_close"].isna().sum())
    mi["ts_end"] = mi["ts"] + pd.Timedelta(hours=1)
    out["mark_index_1h"] = mi[["symbol", "ts", "ts_end", "mark_close", "index_close"]]

    # ---- 3. oi_1h —— 终点对齐：bar 的 ts_end 配该时刻的快照 ----
    oi = read_metrics(sym, years)
    o = pd.DataFrame({"symbol": sym, "ts_end": grid + pd.Timedelta(hours=1)})
    if oi is not None:
        c = oi[["ts", "sum_open_interest"]].rename(
            columns={"ts": "ts_end", "sum_open_interest": "oi"})
        c = c.drop_duplicates(subset=["ts_end"], keep="last")
        o = o.merge(c, on="ts_end", how="left")
    if "oi" not in o.columns:
        o["oi"] = float("nan")
    o["oi"] = o["oi"].astype("float64")
    o["oi_missing"] = o["oi"].isna()
    stats["oi缺"] = int(o["oi_missing"].sum())
    o["ts"] = o["ts_end"] - pd.Timedelta(hours=1)
    out["oi_1h"] = o[["symbol", "ts", "ts_end", "oi", "oi_missing"]]

    # ---- 4. funding —— 事件表，独立于网格 ----
    fu = read_monthly("fundingRate", sym)
    if fu is not None and not fu.empty:
        fu = fu.sort_values("ts", ignore_index=True)
        # 毫秒位不恒为 0 —— 只能按整秒截断（§3.6）
        tf = fu["ts"].dt.floor("s")
        stats["funding毫秒非零"] = int((fu["ts"].dt.microsecond != 0).sum())
        f = pd.DataFrame({
            "symbol": sym,
            "ts_funding": tf,
            "funding_rate": fu["last_funding_rate"].astype("float64"),
            "funding_interval_hours": fu["funding_interval_hours"].astype("float64"),
        })
        f = f.drop_duplicates(subset=["ts_funding"], keep="last")
        stats["funding_行"] = len(f)
        # 结算时刻应落在网格上（ts_funding == 某 bar 的 ts）
        on_grid = f["ts_funding"].isin(set(grid))
        stats["funding不在网格"] = int((~on_grid).sum())
        out["funding"] = f
    else:
        stats["funding_缺失"] += 1

    return out, stats


# ============================================================================
# 落盘
# ============================================================================

def chunk_key(ts: pd.Series) -> pd.Series:
    """按 year / chunk=YYYY-MM 分区。"""
    return ts.dt.strftime("%Y-%m")


def conform(df: pd.DataFrame, table: str) -> pd.DataFrame:
    """按 schema 归一化 dtype 与列顺序。

    `validate()` 检查 dtype，而 pandas 默认给字符串列 object、给整数列 int64，
    都需要显式转成 schema 的语义类型（string / float64）。
    """
    sch = LAYER2_SCHEMAS[table]
    out = {}
    for col in sch.columns:
        name = col.name                      # Column 是具名元组，下标要用 .name
        s = df[name]
        if col.dtype == "string":
            out[name] = s.astype("string")
        elif col.dtype == "float64":
            out[name] = s.astype("float64")
        elif col.dtype == "bool":
            out[name] = s.astype("bool")
        elif col.dtype == "timestamp":
            out[name] = pd.to_datetime(s, utc=True)
        else:
            raise ValueError(f"未知语义类型 {col.dtype!r}（列 {name}）")
    return pd.DataFrame(out, columns=[c.name for c in sch.columns])


def write_chunk(table: str, ym: str, df: pd.DataFrame, *, do_validate: bool) -> tuple[int, int]:
    """写一个 chunk（与已有内容【合并】，不是覆盖）。

    逐合约处理意味着同一个 chunk 会被写入 len(pool) 次，每次只带一个合约的增量。
    所以必须读回已有内容、合并、去重、排序后再写 —— 单纯的覆盖会让文件里
    只剩最后一个合约的数据。

    返回 (本次新增行数, 合并后的总行数)。
    """
    df = conform(df, table)
    key = list(LAYER2_SCHEMAS[table].primary_key)
    cols = [c.name for c in LAYER2_SCHEMAS[table].columns]
    year = ym[:4]
    out = L2 / table / f"year={year}" / f"chunk={ym}.parquet"
    added = len(df)
    if out.exists():
        # ⚠️ pyarrow 会从目录名 year=YYYY 推断出一个分区列加进表里，
        #    physical schema 里并没有它。`partitioning=None` 关掉这个行为；
        #    合并后再按 schema 取列作为第二道保险。
        old = pq.read_table(str(out), partitioning=None).to_pandas()
        df = pd.concat([old[cols], df], ignore_index=True)
    df = df[cols].drop_duplicates(subset=key, keep="last")
    df = df.sort_values(key, ignore_index=True)
    if do_validate:
        validate(df, table)              # 失败抛 SchemaViolation，一次报全部问题
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp,
                   compression="zstd")
    os.replace(tmp, out)
    return added, len(df)


def main() -> int:
    ap = argparse.ArgumentParser(description="Step 4 —— 建第 2 层 4 张标准 1h 表")
    ap.add_argument("--out-root", required=True,
                    help="产出根目录。正式运行传 data/ 的绝对路径；冒烟传临时目录。"
                         "【必填】—— 不用环境变量，见文件头说明")
    ap.add_argument("--raw-root", default=None,
                    help="raw 的读取位置（默认 <out-root>/raw）。冒烟时可指向正式 raw")
    ap.add_argument("--pool", default=None, help="候选池 CSV 路径（默认项目内那一个）")
    ap.add_argument("--sample-end", required=True, help="样本截止日，必须是月末")
    ap.add_argument("--subset", nargs="+", default=None, help="只处理这些合约（冒烟）")
    ap.add_argument("--batch", type=int, default=30,
                    help="每多少个合约合并落盘一次（默认 30）。越小内存越省、"
                         "但 chunk 重写次数越多（次数 ≈ 合约数/批大小 × 57）")
    ap.add_argument("--no-validate", action="store_true", help="跳过 validate()（不建议）")
    args = ap.parse_args()

    configure_paths(Path(args.out_root),
                    Path(args.raw_root) if args.raw_root else None,
                    Path(args.pool) if args.pool else None)

    cfg = cfg_mod.Config()
    cfg_mod.validate_sample_end(args.sample_end)

    log("=" * 78)
    log(f"build_layer2   sample_end={args.sample_end}   "
        f"窗口 {cfg.sample_start} .. {args.sample_end}")
    log(f"数据根目录: {DATA}")
    log("=" * 78)

    if not CANDIDATE_POOL.exists():
        log(f"找不到候选池 {CANDIDATE_POOL}")
        return 2
    pool = [l.strip() for l in CANDIDATE_POOL.read_text(encoding="utf-8").split()
            if l.strip() and l != "symbol"]
    if args.subset:
        pool = [s for s in pool if s in set(args.subset)]
        if not pool:
            log(f"--subset 里的合约都不在候选池中：{args.subset}")
            return 2
    years = sorted({int(p.stem.split("=")[1]) for p in (RAW / "metrics").glob("year=*.parquet")})
    log(f"候选池 {len(pool)} 个合约   metrics 年份 {years}")

    # ---- 逐合约建表，按【批】合并落盘 ----
    # 内存约束：不能把所有合约攒到最后（2,400 万行）。
    # 性能约束：也不能每个合约都读回全部 57 个 chunk 重写一遍
    #          （285 × 57 ≈ 10 万次"读回+合并+重写"，二次方）。
    # 折中：每 --batch 个合约攒一批合并一次。缓冲区峰值 ≈ batch × 一个合约。
    agg: Counter = Counter()
    rows_by_table: Counter = Counter()
    chunks_written: dict[str, set[str]] = {t: set() for t in LAYER2_SCHEMAS}
    pend: dict[str, dict[str, list[pd.DataFrame]]] = {
        t: defaultdict(list) for t in LAYER2_SCHEMAS
    }
    pend_syms = 0

    def flush() -> None:
        nonlocal pend, pend_syms
        for tname in LAYER2_SCHEMAS:
            for ym, parts in pend[tname].items():
                added, _ = write_chunk(tname, ym,
                                       pd.concat(parts, ignore_index=True),
                                       do_validate=not args.no_validate)
                rows_by_table[tname] += added
                chunks_written[tname].add(ym)
        pend = {t: defaultdict(list) for t in LAYER2_SCHEMAS}
        pend_syms = 0

    t0 = time.time()
    for i, sym in enumerate(pool, 1):
        tables, st = build_symbol(sym, years)
        agg.update(st)
        for tname, df in tables.items():
            if df.empty:
                continue
            # 分区键永远是主键里的【时间列】（klines/mark/oi 是 ts，funding 是 ts_funding）
            tpk = LAYER2_SCHEMAS[tname].primary_key[1]
            for ym, g in df.groupby(chunk_key(df[tpk]), sort=False):
                pend[tname][ym].append(g)
        pend_syms += 1
        if pend_syms >= args.batch:
            flush()
            log(f"    {i}/{len(pool)} 个合约  已用 {time.time()-t0:.0f}s")
    flush()
    log(f"  建表+落盘完成，耗时 {time.time()-t0:.0f}s")
    log(f"  统计: klines 行 {agg['klines_行']:,}  funding 行 {agg['funding_行']:,}")
    log(f"        mark 缺 {agg['mark缺']:,}   index 缺 {agg['index缺']:,}   "
        f"oi 缺 {agg['oi缺']:,}")
    log(f"        funding 毫秒非零 {agg['funding毫秒非零']:,}   "
        f"不在网格 {agg['funding不在网格']:,}")
    written = {t: len(chunks_written[t]) for t in LAYER2_SCHEMAS}
    for tname in LAYER2_SCHEMAS:
        log(f"    {tname:<16} {written[tname]:>3} 个 chunk   "
            f"{rows_by_table[tname]:>12,} 行")

    # ---- 交叉判据：三张网格表的 (symbol, ts) 必须逐一致 ----
    log("")
    log("交叉校验…")
    grids = {}
    for tname in ("klines_1h", "mark_index_1h", "oi_1h"):
        keys = set()
        for f in (L2 / tname).rglob("*.parquet"):
            # partitioning=None：关掉 pyarrow 从目录名推断分区列的行为
            d = pq.read_table(str(f), columns=["symbol", "ts"],
                              partitioning=None).to_pandas()
            keys |= set(zip(d["symbol"], d["ts"]))
        grids[tname] = keys
        log(f"    {tname:<16} {len(keys):>12,} 个 (symbol, ts)")
    ok = True
    base = grids["klines_1h"]
    for tname, ks in grids.items():
        if ks != base:
            ok = False
            log(f"    !! {tname} 与 klines_1h 不一致："
                f"缺 {len(base - ks):,}  多 {len(ks - base):,}")
    log(f"    三张网格表一致: {'是' if ok else '否'}")

    # ---- 运行元信息 ----
    RUN_INFO.parent.mkdir(parents=True, exist_ok=True)
    import json
    RUN_INFO.write_text(json.dumps({
        "sample_end": args.sample_end,
        "sample_start": cfg.sample_start,
        "config_snapshot": cfg.snapshot(),
        "step": "build_layer2",
        "run_at": datetime.now(timezone.utc).isoformat(),
        "candidate_pool_size": len(pool),
        "chunks_per_table": written,
        "rows_by_table": dict(rows_by_table),
        "grid_consistent": ok,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    log("")
    log("=" * 78)
    log("运行摘要")
    log("=" * 78)
    log(f"  候选池合约            {len(pool):>10,}")
    for tname in LAYER2_SCHEMAS:
        log(f"  {tname:<20} {rows_by_table[tname]:>10,} 行   {written[tname]:>3} chunk")
    log(f"  三张网格表一致        {'是' if ok else '否':>10}")
    log(f"  总耗时                {time.time()-T_START:>10.0f}s")
    log("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
    except SchemaViolation as e:
        print(f"\nschema 校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(3)
