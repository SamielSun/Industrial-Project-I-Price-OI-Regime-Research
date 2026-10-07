#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_layer2 —— 从 raw 数据建第 2 层 4 张标准 1h 表

它在 Phase 1 中的位置：Step 4（建第 2 层 4 张规范化 1h 表）。

做什么
------
  读 data/raw/ 下的全部 parquet（月频源每合约一个文件、metrics 按年分文件），
  建四张规范化表，按 year/chunk=YYYY-MM 落盘：

    klines_1h       (symbol, ts)         12 列 —— 网格的【定义者】
    mark_index_1h   (symbol, ts)          5 列 —— 左连接到 klines 网格
    oi_1h           (symbol, ts)          5 列 —— 左连接到 klines 网格
    funding         (symbol, ts_funding)  4 列 —— 事件表，独立于网格

核心设计（全部为已决策项，各条的理由写在下面对应位置）
-----------------------------------------------------------
1. **网格 = klines_1h 实际存在的 ts**。稀疏，不发明行。
   `features_1h`（Step 5）才密集化。

2. **三张网格表的 (symbol, ts) 集合逐一致**。mark/index/oi 里那些
   klines 没有的小时一律丢弃，这自然处理了尾部残留：
     · 下架合约 mark 多写的、末根 bar 之后的空行（123,916 行）
     · LUNAUSDT 的 OI 孤立残留（数据的最后一条是 2024-04-06 02:00，而 klines 止于 2022-05）
   ⚠️ 代价：这条规则也丢掉【归档里确实存在】的 mark/index 行 —— 面板里 klines 没有
   bar 的小时共 6,886 个，其中 raw 里 mark 有 6,863 小时、index 有 6,766 小时的数据，
   全被排除。它们不是归档缺口，是网格规则的后果（data_quality.md §3.3 已按此归因）。

3. **OI 终点对齐**：bar [ts, ts_end) 配 OI(ts_end)。
   即 `oi_1h.ts = 源 create_time - 1h`。这是 schema 已定的语义
   （`ts_end` = "OI 对齐时刻 = 决策时刻"）。
   **`create_time` 的秒位必须截断**（实测 4,138 行非 0）—— 见下方 oi_1h 一节的说明。

4. **funding 落在结算时刻【起的】那根 bar**：`ts_funding == klines.ts`。
   实测 calc_time 截断到整秒后 100% 落在整点；但**不是** 100% 等于某根 bar 的 ts ——
   首根 bar 之前与末根 bar 之后的结算自然不在网格上（本脚本记在
   `stats["funding不在网格"]` 里，Step 5 也算出同一现象，见那里的日志）。
   `funding_rate` 只在结算时刻有值；`funding_interval_hours` 的
   前向填充在 Step 5 做，不在这张表里。

5. **缺值用 NaN，不填充**：
   · mark/index 缺小时 → `NaN`（价格是连续量，填充等于发明数据）
   · OI 缺快照 → `NaN` + `oi_missing=True`（有这一列就是为了保留"缺"与"不存在"的区分）

6. **全量重建**，不做增量。`layer2_built_at` 进度戳【尚未实现】，留到真正做增量时
   再加。真做增量时它是单一时间戳，因此 mark/index 的
   构建顺序是硬性要求：合并落盘成功后才写戳，否则 index 的数据会永久丢失且不报错。

产出
----
  data/01_layer2/{klines_1h,mark_index_1h,oi_1h,funding}/year=YYYY/chunk=YYYY-MM.parquet
  4 张表 × 每个样本月一个 chunk

用法
----
  python phase1/build_layer2.py --out-root data --sample-end 2026-08-31
  python phase1/build_layer2.py --out-root /tmp/x --raw-root data \
      --subset BTCUSDT --sample-end 2026-08-31        # 冒烟

设计参数见 config.py；四张表的列契约见 lib/schema.py 的 LAYER2_SCHEMAS。
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
from collections import Counter, defaultdict
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
CANDIDATE_POOL = ROOT / "data" / "03_reference" / "candidate_pool.csv"


def configure_paths(out_root: Path, raw_root: Path | None, pool: Path | None) -> None:
    """按命令行参数定路径。必须在 main() 最开头调用。"""
    global DATA, RAW, L2, CANDIDATE_POOL
    DATA = out_root.resolve()
    RAW = (raw_root or (DATA / "raw")).resolve()
    L2 = DATA / "01_layer2"
    CANDIDATE_POOL = (pool or (ROOT / "data" / "03_reference"
                               / "candidate_pool.csv")).resolve()

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


_METRICS_CACHE: dict[str, pd.DataFrame] | None = None


def _metrics_cache(years: list[int]) -> dict[str, pd.DataFrame]:
    """把 6 个年度 metrics 文件读【一次】、解析 ts、并【按合约预分组】。

    两个优化叠加：
      1. 原来每个合约都重读一遍 6 个文件（同一份 730 万行 × 285 次）—— 实测 289s；
      2. 只在读完后按 `symbol == s` 反复过滤仍是 285 次全表布尔扫描 —— 实测 114s。
    一次 groupby 建索引后，取单个合约是 O(1) 字典查找（实测 < 2s）。
    """
    global _METRICS_CACHE
    if _METRICS_CACHE is None:
        frames = [pq.read_table(RAW / "metrics" / f"year={y}.parquet").to_pandas()
                  for y in years if (RAW / "metrics" / f"year={y}.parquet").exists()]
        if not frames:
            raise SystemExit(f"找不到 metrics：{RAW / 'metrics'}")
        c = pd.concat(frames, ignore_index=True)
        c["ts"] = pd.to_datetime(c["create_time"], utc=True)
        c = c[["symbol", "ts", "sum_open_interest"]].sort_values(
            ["symbol", "ts"], ignore_index=True)
        _METRICS_CACHE = {s: g for s, g in c.groupby("symbol", sort=False)}
    return _METRICS_CACHE


def read_metrics(sym: str, years: list[int]) -> pd.DataFrame | None:
    """取该合约的日频 metrics（来自共享缓存）。"""
    return _metrics_cache(years).get(sym)


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
        # 对齐规则：ts_end == create_time（实测确认，例 TLMUSDT 2021-12-01：
        # bar [00:00,01:00) 的 oi = 102,744,323 = create_time 01:00 的快照）。
        # 秒位必须截断，否则静默丢数据：实测 4,138 行（64 个合约，如
        # TLMUSDT 2022-05-09 11:00:59）的 create_time 秒位非 0，其中 4,083 行
        # 是该合约该小时唯一的快照。不截断则匹配不上任何 ts_end，
        # 被静默记成 oi_missing=True，并把该合约的 OI 序列人为拉长。
        # 同一小时若真有多条（整点 + 迟到），按时间取最后一条。
        oi = oi.assign(ts_end=oi["ts"].dt.floor("h"))
        stats["oi秒位非零"] = int((oi["ts"].dt.second != 0).sum())
        c = (oi.sort_values("ts")[["ts_end", "sum_open_interest"]]
               .drop_duplicates(subset=["ts_end"], keep="last")
               .rename(columns={"sum_open_interest": "oi"}))
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
        # 毫秒位不恒为 0 —— 只能按整秒截断
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


def write_chunk(table: str, ym: str, df: pd.DataFrame, *, do_validate: bool) -> int:
    """写一个 chunk（与已有内容【合并】，不是覆盖）。

    逐合约处理意味着同一个 chunk 会被写入 len(pool) 次，每次只带一个合约的增量。
    所以必须读回已有内容、合并、去重、排序后再写 —— 单纯的覆盖会让文件里
    只剩最后一个合约的数据。

    返回合并后的总行数。
    """
    df = conform(df, table)
    key = list(LAYER2_SCHEMAS[table].primary_key)
    cols = [c.name for c in LAYER2_SCHEMAS[table].columns]
    year = ym[:4]
    out = L2 / table / f"year={year}" / f"chunk={ym}.parquet"
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
    # .part 名里带 PID：两个进程同时跑时不会互相覆盖暂存文件
    tmp = out.with_name(f"{out.name}.{os.getpid()}.part")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp,
                   compression="zstd")
    os.replace(tmp, out)
    return len(df)


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
    ap.add_argument("--keep-existing", action="store_true",
                    help="不要清掉已有产出（只在 --subset 冒烟时用；默认全量重建）")
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

    # ---- 全量重建：先清掉本步骤的旧产出 ----
    # 不能依赖 write_chunk 的"读回合并"：本轮没处理的合约会在目录里留【旧代码/旧输入】
    # 的行，而且没人能发现 —— 实测 --subset 连跑两次后，目录里还留着上一次的合约，
    # 收尾的交叉校验是对整个目录做的，照样打印"三张网格表一致: 是"。
    # 必须显式给 --keep-existing 才保留旧产出（冒烟用）。
    if not args.keep_existing:
        for tname in LAYER2_SCHEMAS:
            d_old = L2 / tname
            if d_old.exists():
                n_old = sum(1 for _ in d_old.rglob("*.parquet"))
                shutil.rmtree(d_old)
                log(f"  清掉旧产出 {tname}（{n_old} 个文件，全量重建）")

    # ---- 逐合约建表，按【批】合并落盘 ----
    # 内存约束：不能把所有合约攒到最后（2,400 万行）。
    # 性能约束：也不能每个合约都读回全部 57 个 chunk 重写一遍
    #          （285 × 57 ≈ 10 万次"读回+合并+重写"，二次方）。
    # 折中：每 --batch 个合约攒一批合并一次。缓冲区峰值 ≈ batch × 一个合约。
    agg: Counter = Counter()
    chunks_written: dict[str, set[str]] = {t: set() for t in LAYER2_SCHEMAS}
    pend: dict[str, dict[str, list[pd.DataFrame]]] = {
        t: defaultdict(list) for t in LAYER2_SCHEMAS
    }
    pend_syms = 0

    def flush() -> None:
        nonlocal pend, pend_syms
        for tname in LAYER2_SCHEMAS:
            for ym, parts in pend[tname].items():
                write_chunk(tname, ym, pd.concat(parts, ignore_index=True),
                            do_validate=not args.no_validate)
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
    log(f"        oi 秒位非零（已截断到整点）{agg['oi秒位非零']:,}")
    written = {t: len(chunks_written[t]) for t in LAYER2_SCHEMAS}
    # 表的总行数【从磁盘读】，不是本次写入数 —— 本轮没碰到的 chunk 也有行，
    # 而 funding 是事件表（每批只写它那个月的行），累计写入数会严重低报。
    rows_total = {t: sum(pq.read_metadata(str(f)).num_rows
                         for f in (L2 / t).rglob("*.parquet"))
                  for t in LAYER2_SCHEMAS}
    for tname in LAYER2_SCHEMAS:
        log(f"    {tname:<16} {written[tname]:>3} 个 chunk   "
            f"{rows_total[tname]:>12,} 行")

    # ---- 空产出必须报错，不能"绿灯通过" ----
    # 实测：--raw-root 指向空目录时，0 个文件、0 行，旧的交叉校验仍然打印
    # "三张网格表一致: 是" 并 exit 0 —— 空的第 2 层会被 Step 5/6 继续消费。
    if sum(rows_total.values()) == 0:
        log("")
        log(f"  ✗ 产出为 0 行 —— 检查 --raw-root 是否指对了：{RAW}")
        return 4
    if agg["klines_缺失"]:
        log("")
        log(f"  ✗ 有 {agg['klines_缺失']} 个合约在 raw 里没有 klines 文件 —— "
            f"它们会得到整表 NaN。拒绝以'成功'结束。")
        return 4

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

    log("")
    log("=" * 78)
    log("运行摘要")
    log("=" * 78)
    log(f"  候选池合约            {len(pool):>10,}")
    for tname in LAYER2_SCHEMAS:
        log(f"  {tname:<20} {rows_total[tname]:>10,} 行   {written[tname]:>3} chunk")
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
