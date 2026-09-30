#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_features —— 建 features_1h（19 列密集网格）

它在 Phase 1 中的位置：Step 5（见 PHASE1_GUIDANCE.md §1.1 进度表与 §4 流水线）。

做什么
------
  把第 2 层的 4 张表合成一张分析面板：

      features_1h = klines_1h
          LEFT JOIN mark_index_1h ON (symbol, ts)
          LEFT JOIN oi_1h          ON (symbol, ts)
          LEFT JOIN funding        ON (symbol, ts_end = ts_funding)

产出
----
  data/02_features/features_1h/year=YYYY/chunk=YYYY-MM.parquet   57 个文件

四条核心规则
------------
1. **密集网格**，范围 [首根 bar, 最后一个正成交额日]。
   `klines_1h` 几乎本来就密集（抽样 788,731 行只有 5 处断点），
   实测密集化只补 6,855 行（0.09%）。

2. **裁掉死尾。** 下架合约的 `klines` 归档会一直写「整月零成交空行」到样本末端，
   共 310,466 行（4.10%），其 `oi_missing` 占 99.8%。
   按 `schema.py` 的 note（"覆盖 [oi_archive_start, last_active_date]"）裁掉。

3. **funding 的处理**：
   · `funding_rate` —— 只在结算时刻有值，**不填充**
   · `funding_interval_hours` —— 非结算小时填【上一次结算公布的区间】，首个结算前为 null
   · join 键是 `klines.ts == funding.ts_funding`（实测 100% 落在网格上）

4. **两个缺失标记**：
   · `bar_missing` —— 该小时在 `klines_1h` 中无对应行（密集化补出来的行）
   · `oi_missing` —— 该小时 OI 快照不存在（含"bar 本身就不存在"的情况）

用法
----
  python phase1_data/build_features.py --out-root <data 绝对路径> --sample-end 2026-08-31
  python phase1_data/build_features.py --out-root /tmp/x --l2-root <正式 data> \\
      --subset BTCUSDT --sample-end 2026-08-31      # 冒烟

依据：PHASE1_GUIDANCE.md §7.3（features_1h）§7.4（validate）§8.2.1（死尾）
"""

from __future__ import annotations

import argparse
import json
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
from lib.schema import FEATURES_1H, SchemaViolation, validate   # noqa: E402

# ============================================================================
# 路径（由 --out-root 显式指定，不用环境变量）
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
L2 = DATA / "01_layer2"
OUT = DATA / "02_features"
CANDIDATE_POOL = ROOT / "data" / "03_reference" / "candidate_pool.csv"
RUN_INFO = DATA / "00_config" / "sample_end.json"

T_START = time.time()


def configure_paths(out_root: Path, l2_root: Path | None,
                    pool: Path | None) -> None:
    global DATA, L2, OUT, CANDIDATE_POOL, RUN_INFO
    DATA = out_root.resolve()
    L2 = (l2_root or (DATA / "01_layer2")).resolve()
    OUT = DATA / "02_features"
    CANDIDATE_POOL = (pool or (ROOT / "data" / "03_reference"
                               / "candidate_pool.csv")).resolve()
    RUN_INFO = DATA / "00_config" / "sample_end.json"


def log(msg: str) -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


# ============================================================================
# 读第 2 层
# ============================================================================

def read_l2(table: str) -> pd.DataFrame:
    """读一张 layer2 表的全部 chunk。用 partitioning=None 关掉分区列推断。"""
    fs = sorted((L2 / table).rglob("*.parquet"))
    if not fs:
        raise FileNotFoundError(f"找不到 {L2 / table} 下的 parquet")
    return pd.concat(
        [pq.read_table(str(f), partitioning=None).to_pandas() for f in fs],
        ignore_index=True)


# ============================================================================
# 网格范围
# ============================================================================

def active_bounds(kl: pd.DataFrame) -> pd.DataFrame:
    """每个合约的网格范围：[首根 bar, 最后一个正成交额日的当日末] 。

    返回 DataFrame[symbol, g0, g1]。
    """
    d = kl[["symbol", "ts", "quote_volume"]].copy()
    d["day"] = d["ts"].dt.floor("D")
    pos = d[d["quote_volume"] > 0]
    last_day = pos.groupby("symbol")["day"].max().rename("last_day")
    g0 = d.groupby("symbol")["ts"].min().rename("g0")
    b = pd.concat([g0, last_day], axis=1)
    # 上界 = 最后一个正成交额日的 23:00（该日最后一根 bar）
    b["g1"] = b["last_day"] + pd.Timedelta(hours=23)
    return b.reset_index()


def dense_grid(sym: str, g0: pd.Timestamp, g1: pd.Timestamp) -> pd.DataFrame:
    ts = pd.date_range(g0, g1, freq="h", tz="UTC")
    return pd.DataFrame({"symbol": sym, "ts": ts,
                         "ts_end": ts + pd.Timedelta(hours=1)})


# ============================================================================
# 单合约建表
# ============================================================================

def build_symbol(sym: str, ks: dict, mis: dict, ois: dict, fus: dict,
                 g0: pd.Timestamp, g1: pd.Timestamp
                 ) -> tuple[pd.DataFrame, Counter]:
    """用【已按合约预分组】的切片建一个合约的 features 行。

    ks / mis / ois / fus 分别是 klines / mark_index / oi / funding 的
    {symbol: DataFrame} 字典，切片刻已去掉 symbol 列。
    """
    st: Counter = Counter()

    base = dense_grid(sym, g0, g1)
    st["网格行"] = len(base)

    # ---- klines_1h ----
    k = ks.get(sym)
    if k is not None:
        base = base.merge(k.drop_duplicates(subset=["ts"], keep="last"),
                          on=["ts", "ts_end"], how="left")
    else:
        for c in ("open", "high", "low", "close", "volume", "quote_volume",
                  "trades", "taker_buy_volume", "taker_buy_quote_volume"):
            base[c] = float("nan")
    base["bar_missing"] = base["close"].isna()
    st["bar_missing"] = int(base["bar_missing"].sum())

    # ---- mark_index_1h ----
    m = mis.get(sym)
    if m is not None:
        base = base.merge(m.drop_duplicates(subset=["ts"], keep="last"),
                          on=["ts", "ts_end"], how="left")
    else:
        base["mark_close"] = float("nan")
        base["index_close"] = float("nan")
    st["mark缺"] = int(base["mark_close"].isna().sum())
    st["index缺"] = int(base["index_close"].isna().sum())

    # ---- oi_1h ----
    o = ois.get(sym)
    if o is not None:
        base = base.merge(o.drop_duplicates(subset=["ts"], keep="last"),
                          on=["ts", "ts_end"], how="left")
    else:
        base["oi"] = float("nan")
        base["oi_missing"] = True
    # 两种"缺"：① 该 ts 在 oi_1h 里没有行（bar 本身不存在）② oi_1h 里 oi_missing=True。
    # ⚠️ 用 astype("boolean")（可空布尔）而不是 fillna —— join 全落空时该列会是
    #    object dtype（NaN），对它 fillna 会触发隐式降级警告且未来版本行为会变。
    base["oi_missing"] = (base["oi_missing"].astype("boolean").fillna(True)
                          | base["oi"].isna()).astype(bool)
    st["oi_missing"] = int(base["oi_missing"].sum())

    # ---- funding ----
    f = fus.get(sym)
    if f is not None:
        base = base.merge(
            f.drop_duplicates(subset=["ts_funding"], keep="last")
             .rename(columns={"ts_funding": "ts"}),
            on="ts", how="left")
        st["结算次数"] = int(base["funding_rate"].notna().sum())
        st["funding未join上"] = max(0, len(f) - st["结算次数"])
    else:
        base["funding_rate"] = float("nan")
        base["funding_interval_hours"] = float("nan")
        st["funding未join上"] = 0
    # interval 前向填充：非结算小时填【上一次结算公布的区间】
    before = int(base["funding_interval_hours"].isna().sum())
    base["funding_interval_hours"] = base["funding_interval_hours"].ffill()
    st["interval回填"] = before - int(base["funding_interval_hours"].isna().sum())
    st["interval首结算前"] = int(base["funding_interval_hours"].isna().sum())
    return base, st


# ============================================================================
# 落盘（与 Step 4 同机制：读回合并、partitioning=None、原子写）
# ============================================================================

COLS = [c.name for c in FEATURES_1H.columns]


def conform(df: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for col in FEATURES_1H.columns:
        name, s = col.name, df[col.name]
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
    return pd.DataFrame(out, columns=COLS)


def write_chunk(ym: str, df: pd.DataFrame, *, do_validate: bool) -> tuple[int, int]:
    """写一个 chunk（与已有内容合并）。返回 (本次新增行数, 合并后总行数)。"""
    df = conform(df)
    out = OUT / "features_1h" / f"year={ym[:4]}" / f"chunk={ym}.parquet"
    added = len(df)
    if out.exists():
        old = pq.read_table(str(out), partitioning=None).to_pandas()
        df = pd.concat([old[COLS], df], ignore_index=True)
    df = df[COLS].drop_duplicates(subset=["symbol", "ts"], keep="last")
    df = df.sort_values(["symbol", "ts"], ignore_index=True)
    if do_validate:
        validate(df, "features_1h")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp,
                   compression="zstd")
    os.replace(tmp, out)
    return added, len(df)


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Step 5 —— 建 features_1h（19 列密集网格）")
    ap.add_argument("--out-root", required=True, help="产出根目录（必填，见 Step 4 的说明）")
    ap.add_argument("--l2-root", default=None,
                    help="layer2 的读取位置（默认 <out-root>/01_layer2）。冒烟时指向正式目录")
    ap.add_argument("--pool", default=None, help="候选池 CSV 路径")
    ap.add_argument("--sample-end", required=True, help="样本截止日，必须是月末")
    ap.add_argument("--subset", nargs="+", default=None, help="只处理这些合约（冒烟）")
    ap.add_argument("--batch", type=int, default=30, help="每多少个合约合并落盘一次")
    ap.add_argument("--no-validate", action="store_true", help="跳过 validate()")
    args = ap.parse_args()

    configure_paths(Path(args.out_root),
                    Path(args.l2_root) if args.l2_root else None,
                    Path(args.pool) if args.pool else None)
    cfg = cfg_mod.Config()
    cfg_mod.validate_sample_end(args.sample_end)

    log("=" * 78)
    log(f"build_features   sample_end={args.sample_end}")
    log(f"  产出根目录 : {DATA}")
    log(f"  layer2 读取: {L2}")
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
    log(f"候选池 {len(pool)} 个合约")

    # 全量重建：先清掉本步骤的旧产出。
    # 不能依赖 write_chunk 的"读回合并" —— 本轮若裁掉了某些行（如死尾），
    # 旧的残留行会被合并进来，永远不会消失。
    d_out = OUT / "features_1h"
    if d_out.exists():
        n_old = sum(1 for _ in d_out.rglob("*.parquet"))
        import shutil
        shutil.rmtree(d_out)
        log(f"  清掉旧产出 {n_old} 个文件（全量重建）")

    # ---- 读 layer2 ----
    t0 = time.time()
    kl = read_l2("klines_1h")
    mi = read_l2("mark_index_1h")
    oi = read_l2("oi_1h")
    fu = read_l2("funding")
    log(f"  读入 layer2：klines {len(kl):,} / mark_index {len(mi):,} / "
        f"oi {len(oi):,} / funding {len(fu):,}   耗时 {time.time()-t0:.0f}s")

    bounds = active_bounds(kl)
    bmap = {r.symbol: (r.g0, r.g1) for r in bounds.itertuples(index=False)}
    log(f"  活跃区间：layer2 里有 {len(bmap)} 个合约（本次处理 {len(pool)} 个）")

    # ---- 按合约预分组（一次 groupby，避免循环里反复布尔过滤）----
    t0 = time.time()
    ks = {s: g.drop(columns=["symbol"]) for s, g in kl.groupby("symbol", sort=False)}
    mis = {s: g.drop(columns=["symbol"]) for s, g in mi.groupby("symbol", sort=False)}
    ois = {s: g.drop(columns=["symbol"]) for s, g in oi.groupby("symbol", sort=False)}
    fus = {s: g.drop(columns=["symbol"]) for s, g in fu.groupby("symbol", sort=False)}
    log(f"  预分组完成，耗时 {time.time()-t0:.0f}s")

    # ---- 逐合约建，按批合并 ----
    agg: Counter = Counter()
    rows_written = 0
    chunks: set[str] = set()
    pend: dict[str, list[pd.DataFrame]] = defaultdict(list)
    pend_syms = 0

    def flush() -> None:
        nonlocal pend, pend_syms, rows_written
        for ym, parts in pend.items():
            added, _ = write_chunk(ym, pd.concat(parts, ignore_index=True),
                                   do_validate=not args.no_validate)
            rows_written += added
            chunks.add(ym)
        pend = defaultdict(list)
        pend_syms = 0

    t0 = time.time()
    n_grid = n_trim = 0
    for i, sym in enumerate(pool, 1):
        if sym not in bmap:
            agg["无 klines"] += 1
            continue
        g0, g1 = bmap[sym]
        n_grid += 1
        df, st = build_symbol(sym, ks, mis, ois, fus, g0, g1)
        agg.update(st)
        # 统计裁掉了多少（原 klines 该合约在 g1 之后的行）
        kk = ks.get(sym)
        if kk is not None:
            n_trim += int((kk["ts"] > g1).sum())
        tpk = df["ts"].dt.strftime("%Y-%m")
        for ym, g in df.groupby(tpk, sort=False):
            pend[ym].append(g)
        pend_syms += 1
        if pend_syms >= args.batch:
            flush()
            log(f"    {i}/{len(pool)} 个合约  已用 {time.time()-t0:.0f}s")
    flush()
    log(f"  建表+落盘完成，耗时 {time.time()-t0:.0f}s")

    agg["裁掉死尾行"] = n_trim
    log("")
    log(f"  网格行数（合计）      {agg['网格行']:>12,}")
    log(f"  bar_missing          {agg['bar_missing']:>12,}")
    log(f"  oi_missing           {agg['oi_missing']:>12,}")
    log(f"  mark 缺              {agg['mark缺']:>12,}")
    log(f"  index 缺             {agg['index缺']:>12,}")
    log(f"  funding 结算         {agg['结算次数']:>12,}")
    log(f"  interval 回填        {agg['interval回填']:>12,}")
    log(f"  interval 首结算前为 null {agg['interval首结算前']:>9,}")
    log(f"  funding 未 join 上（网格外） {agg['funding未join上']:>7,}")
    log(f"  裁掉死尾行           {n_trim:>12,}")
    log(f"  无 klines 的合约     {agg['无 klines']:>12,}")

    # ---- 运行元信息 ----
    RUN_INFO.parent.mkdir(parents=True, exist_ok=True)
    old_info = {}
    if RUN_INFO.exists():
        try:
            old_info = json.loads(RUN_INFO.read_text(encoding="utf-8"))
        except Exception:                     # noqa: BLE001
            old_info = {}
    old_info.update({
        "sample_end": args.sample_end,
        "step_5_build_features": {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "candidate_pool_size": len(pool),
            "grid_rows": agg["网格行"],
            "chunks": len(chunks),
            "rows_written": rows_written,
            "bar_missing": agg["bar_missing"],
            "oi_missing": agg["oi_missing"],
            "dead_tail_trimmed": n_trim,
        },
    })
    RUN_INFO.write_text(json.dumps(old_info, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    log("")
    log("=" * 78)
    log("运行摘要")
    log("=" * 78)
    log(f"  候选池合约        {len(pool):>10,}")
    log(f"  网格行数          {agg['网格行']:>10,}")
    log(f"  落盘 chunk        {len(chunks):>10,}")
    log(f"  总耗时            {time.time()-T_START:>10.0f}s")
    log("=" * 78)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
    except SchemaViolation as e:
        print(f"\nschema 校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(3)
