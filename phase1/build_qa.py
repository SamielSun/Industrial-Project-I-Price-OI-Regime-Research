#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_qa —— Step 6 的第二部分：缺失数据报告 + 数据字典 + 校验和 + 复现命令

它在 Phase 1 中的位置：D1 的产出物部分（见 phase1/guidance.md §8.3 与 §12）。

做什么
------
  1. missing_files.parquet   文件层：manifest 里下载失败的源文件
  2. gaps.parquet            记录层：连续缺口区间（5 类指标）
  3. coverage.parquet        记录层：逐合约逐指标的覆盖率
  4. data_dictionary.md      数据字典
  5. checksums.sha256        全部产出文件的校验和
  6. REPRODUCE.md            从零复现的命令

五类指标
--------
  klines     bar_missing == True          klines 9 列价格量缺失
  oi         oi_missing  == True          OI 快照缺失
  mark       mark_close  isna()           mark 价格缺失
  index      index_close isna()           index 价格缺失
  oi_zero    oi == 0 且非 missing         OI 快照为 0（市场级发布事件）

⚠️ **不检测 `funding_rate`** —— 它只在结算时刻有值（83.4% 的行天生为 NaN），
   算成缺口会产出 117 万段假缺口。它的稀疏性是语义，不是数据质量问题。
⚠️ **不检测 `funding_interval_hours`** —— 前向填充，不存在缺口。

排序：`gaps.parquet` 按 `(symbol, metric, gap_start)` —— 同一合约的缺口相邻，
人工按合约查最方便。（不按长度降序：那会让同一合约的多段缺口散开。）

用法
----
  python phase1/build_qa.py --out-root <data> --sample-end 2026-08-31
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根
import config as cfg_mod                                     # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FE = DATA / "02_features" / "features_1h"
REF = DATA / "03_reference"
QA = DATA / "04_qa"
MANIFEST = DATA / "00_config" / "manifest.parquet"
RUN_INFO = DATA / "00_config" / "sample_end.json"
L2 = DATA / "01_layer2"
RAW = DATA / "raw"

T_START = time.time()

# 五类指标：(列名, 判据函数名, 说明)
METRICS = {
    "klines": "bar_missing",
    "oi": "oi_missing",
    "mark": "mark_close",
    "index": "index_close",
    "oi_zero": "oi_zero",
}


def configure_paths(out_root: Path, fe_root: Path | None,
                    manifest: Path | None) -> None:
    global DATA, FE, REF, QA, MANIFEST, RUN_INFO, L2, RAW
    DATA = out_root.resolve()
    FE = ((fe_root or (DATA / "02_features")) / "features_1h").resolve()
    REF = DATA / "03_reference"
    QA = DATA / "04_qa"
    MANIFEST = (manifest or (DATA / "00_config" / "manifest.parquet")).resolve()
    RUN_INFO = DATA / "00_config" / "sample_end.json"
    L2 = DATA / "01_layer2"
    RAW = DATA / "raw"


def log(msg: str) -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


# ============================================================================
# 缺口区间
# ============================================================================

def runs_of(a: np.ndarray) -> list[tuple[int, int]]:
    """布尔数组里所有连续 True 的 (起点下标, 终点下标)。"""
    if not a.any():
        return []
    idx = np.flatnonzero(np.diff(np.concatenate([[0], a.astype(np.int8), [0]])) != 0)
    return list(zip(idx[0::2], idx[1::2] - 1))


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Step 6 —— 缺失报告 + 数据字典 + 校验和")
    ap.add_argument("--out-root", required=True, help="产出根目录（必填）")
    ap.add_argument("--fe-root", default=None, help="features 读取位置（冒烟用）")
    ap.add_argument("--manifest", default=None, help="manifest 路径（冒烟用）")
    ap.add_argument("--sample-end", required=True, help="样本截止日，必须是月末")
    ap.add_argument("--verify", action="store_true",
                    help="只核验 04_qa/checksums.sha256，不构建、不写任何文件")
    args = ap.parse_args()

    configure_paths(Path(args.out_root),
                    Path(args.fe_root) if args.fe_root else None,
                    Path(args.manifest) if args.manifest else None)
    if args.verify:
        log(f"verify_checksums   {QA / 'checksums.sha256'}")
        return 0 if verify_checksums() == 0 else 1
    cfg = cfg_mod.Config()
    cfg_mod.validate_sample_end(args.sample_end)

    QA.mkdir(parents=True, exist_ok=True)
    log("=" * 80)
    log(f"build_qa   sample_end={args.sample_end}")
    log(f"  产出根目录 : {DATA}")
    log(f"  QA 目录    : {QA}")
    log("=" * 80)

    # ---- 1. 文件层 ----
    man = pd.read_parquet(MANIFEST)
    bad = man[man["status"] != "ok"].copy()
    MF = bad[["source", "symbol", "period", "granularity",
              "status", "remote_path"]].rename(columns={"status": "category"})
    MF = MF.sort_values(["symbol", "period"], ignore_index=True)
    log("")
    log(f"文件层：{len(MF):,} 行（manifest 的非 ok 记录）")
    if len(MF):
        for c, n in MF["category"].value_counts().items():
            log(f"  {c:<20} {n:>6,}")
        log(f"  涉及合约 {MF['symbol'].nunique()} 个   按源 {dict(MF['source'].value_counts())}")

    # ---- 2. 记录层 ----
    log("")
    log("读 features_1h 的标记与值列…")
    t0 = time.time()
    parts = []
    for f in sorted(FE.rglob("*.parquet")):
        parts.append(pq.read_table(str(f), columns=[
            "symbol", "ts", "oi", "oi_missing", "mark_close", "index_close",
            "bar_missing", "quote_volume"], partitioning=None).to_pandas())
    d = pd.concat(parts, ignore_index=True).sort_values(["symbol", "ts"],
                                                        ignore_index=True)
    log(f"  {len(d):,} 行 / {d['symbol'].nunique()} 个合约   耗时 {time.time()-t0:.0f}s")

    # oi_zero：有值且为 0（不是 missing）
    d["oi_zero"] = (d["oi"].notna()) & (d["oi"] == 0)

    flag_col = {
        "klines": d["bar_missing"].to_numpy(),
        "oi": d["oi_missing"].to_numpy(),
        "mark": d["mark_close"].isna().to_numpy(),
        "index": d["index_close"].isna().to_numpy(),
        "oi_zero": d["oi_zero"].to_numpy(),
    }

    log("")
    log("逐合约逐指标算缺口与覆盖率…")
    t0 = time.time()
    gap_rows: list[dict] = []
    cov_rows: list[dict] = []
    sym_ts = d["ts"].to_numpy()
    for s, g in d.groupby("symbol", sort=False):
        idx = g.index.to_numpy()                  # d 已按 (symbol, ts) 排序
        n_total = len(idx)
        qv = g["quote_volume"].median()
        for metric in METRICS:
            sub = flag_col[metric][idx]
            n_bad = int(sub.sum())
            # `oi_zero` 逐小时记，其余记连续区间。
            # 理由：`oi_zero` 本质是【离散的坏点】—— 实测 92.8% 的段长就是 1 小时，
            # 只有一次全市场中断（2022-03-07 15:00 起，105 个合约各 10 小时）是连续的，
            # 而逐小时记录同样能看出它是连续的（10 行时刻相邻）。
            # `oi` / `klines` 等确有长段（最长 7,832 小时），用区间才合理。
            if metric == "oi_zero":
                segs = [(i, i) for i in np.flatnonzero(sub)]
            else:
                segs = runs_of(sub)
            max_h = 0.0
            for i0, i1 in segs:
                a, b_ = idx[i0], idx[i1]
                t0t, t1t = sym_ts[a], sym_ts[b_]
                hours = int((t1t - t0t) / np.timedelta64(1, "h")) + 1
                max_h = max(max_h, float(hours))
                gap_rows.append({
                    "symbol": str(s),
                    "metric": metric,
                    "gap_start": pd.Timestamp(t0t),
                    "gap_end": pd.Timestamp(t1t),
                    "hours": float(hours),
                    "days": round(hours / 24, 3),
                    # 缺口从该合约的第一行就开始 —— 区分"样本前就缺"与"中途损坏"
                    # （oi_zero 恒为 False：它是坏点，与样本边界无关）
                    "started_before_sample": bool(metric != "oi_zero"
                                                  and a == idx[0]),
                })
            present = n_total - n_bad
            cov_rows.append({
                "symbol": str(s),
                "metric": metric,
                "n_total": float(n_total),
                "n_present": float(present),
                "coverage": present / n_total if n_total else np.nan,
                "n_gaps": float(len(segs)),
                "max_gap_hours": max_h,
                "median_daily_qv": float(qv) if pd.notna(qv) else np.nan,
            })
    log(f"  完成，耗时 {time.time()-t0:.0f}s")

    G = pd.DataFrame(gap_rows)
    # 排序：同一合约的缺口相邻，人工按合约查最方便
    G = G.sort_values(["symbol", "metric", "gap_start"], ignore_index=True)
    V = pd.DataFrame(cov_rows).sort_values(["symbol", "metric"], ignore_index=True)

    log("")
    log("缺口统计：")
    for m, n in G["metric"].value_counts().items():
        sub = G[G["metric"] == m]
        log(f"  {m:<9} {n:>6,} 段   总 {sub['hours'].sum():>10,.0f} 小时"
            f"   最长 {sub['max_gap_hours'].max() if False else sub['hours'].max():>7,.0f} 小时"
            f"   最长那条: {sub.loc[sub['hours'].idxmax(), 'symbol']}")
    log("")
    log("覆盖率（中位）：")
    for m in METRICS:
        c = V[V["metric"] == m]["coverage"]
        log(f"  {m:<9} {c.median():.4f}   <0.99 的合约 {int((c < 0.99).sum()):>4}"
            f"   <0.90 的 {int((c < 0.90).sum()):>4}")

    # ---- 3. 落盘 ----
    outs = {"missing_files.parquet": MF, "gaps.parquet": G, "coverage.parquet": V}
    log("")
    for name, df in outs.items():
        p = QA / name
        tmp = p.with_name(p.name + ".part")
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp,
                       compression="zstd")
        os.replace(tmp, p)
        log(f"    -> 04_qa/{name:<26} {len(df):>8,} 行  {p.stat().st_size/1024:8.1f} KB")

    # ---- 4. 数据字典 ----
    dd = build_data_dictionary(cfg, args.sample_end, len(d), d["symbol"].nunique(),
                              MF, G, V)
    (QA / "data_dictionary.md").write_text(dd, encoding="utf-8", newline="\n")
    log(f"    -> 04_qa/data_dictionary.md          {len(dd):,} 字符")

    # ---- 5. 复现命令 ----
    # REPRODUCE.md 放在产出根目录，不写项目根 —— 否则冒烟会污染正式目录
    repro = build_reproduce(cfg, args.sample_end)
    rp = DATA / "REPRODUCE.md"
    rp.write_text(repro, encoding="utf-8", newline="\n")
    log(f"    -> REPRODUCE.md                      {len(repro):,} 字符")

    # ---- 6. 运行元信息 ----
    # 必须在校验和【之前】写：否则 sample_end.json 每次都被算成不一致。
    n_ck = len(checksum_targets())            # 只数，不哈希，省一遍读盘
    prev = {}
    if RUN_INFO.exists():
        try:
            prev = json.loads(RUN_INFO.read_text(encoding="utf-8"))
        except Exception:                         # noqa: BLE001
            prev = {}
    prev["step_6_build_qa"] = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "missing_files": len(MF),
        "gaps": len(G),
        "coverage_rows": len(V),
        "checksums": n_ck,
    }
    RUN_INFO.parent.mkdir(parents=True, exist_ok=True)
    RUN_INFO.write_text(json.dumps(prev, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    # ---- 7. 校验和（最后一个写盘动作）----
    written = write_checksums()
    assert written == n_ck, f"checksum count drift: {written} != {n_ck}"
    log(f"    -> 04_qa/checksums.sha256            {written} 个文件")

    log("")
    log("=" * 80)
    log(f"完成   总耗时 {time.time()-T_START:.0f}s")
    log("=" * 80)
    return 0


# ============================================================================
# 数据字典
# ============================================================================

def build_data_dictionary(cfg, sample_end: str, n_fe_rows: int, n_syms: int,
                          MF, G, V) -> str:
    L = []
    A = L.append
    A("# 数据字典 · D1")
    A("")
    A(f"> sample_start = `{cfg.sample_start}`　sample_end = `{sample_end}`　"
      f"生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    A("")
    A("本项目研究 Binance **USDT 本位永续合约**上「价格 + 持仓量」的联合状态。")
    A("全部时间戳为 **UTC**。")
    A("")
    A("---")
    A("")
    A("## 1. 目录结构")
    A("")
    A("```")
    A("data/")
    A("├── 00_config/")
    A("│   ├── manifest.parquet              逐文件下载状态（断点续传的唯一依据）")
    A("│   └── sample_end.json               运行元信息")
    A("├── 01_layer2/                        第 2 层：4 张规范化源表")
    A("├── 02_features/features_1h/          分析面板（密集网格，19 列）")
    A("├── 03_reference/                     参考表")
    A("├── 04_qa/                            质量保证")
    A("└── raw/                              五个源的原始 parquet")
    A("")
    A("REPRODUCE.md                         从零复现的命令")
    A("```")
    A("")
    A("---")
    A("")
    A("## 2. 表清单")
    A("")
    A("| 表 | 粒度 | 主键 | 行数 | 分区 |")
    A("|---|---|---|---|---|")
    A(f"| `features_1h` | 1 小时 | `(symbol, ts)` | {n_fe_rows:,} | `year=YYYY/chunk=YYYY-MM.parquet` |")
    A("| `klines_1h` | 1 小时 | `(symbol, ts)` | 见 01_layer2 | 同上 |")
    A("| `mark_index_1h` | 1 小时 | `(symbol, ts)` | 同上 | 同上 |")
    A("| `oi_1h` | 1 小时 | `(symbol, ts)` | 同上 | 同上 |")
    A("| `funding` | 8 小时（结算事件） | `(symbol, ts_funding)` | 见 01_layer2 | 同上 |")
    A("| `master` | 1 合约 | `symbol` | 见 03_reference | 单文件 |")
    A("| `universe_eligibility` | 1 合约 × 1 月 | `(symbol, month)` | 见 03_reference | 单文件 |")
    A("| `universe_membership` | 1 合约 × 1 月 | `(symbol, month)` | 见 03_reference | 单文件 |")
    A("")
    A("---")
    A("")
    A("## 3. `features_1h` 逐列定义")
    A("")
    A("| 列 | 类型 | 单位 | 来源 | 说明 |")
    A("|---|---|---|---|---|")
    A("| `symbol` | string | — | — | 合约名，如 `BTCUSDT` |")
    A("| `ts` | timestamp | UTC | — | bar 起点 `H` |")
    A("| `ts_end` | timestamp | UTC | 派生 | `ts + 1h`；**区间终点 = OI 对齐时刻 = 决策时刻** |")
    A("| `open` `high` `low` `close` | float64 | USDT | `klines` | bar 内 OHLC |")
    A("| `volume` | float64 | 张 | `klines` | bar 内成交量（基础资产计） |")
    A("| `quote_volume` | float64 | USDT | `klines` | bar 内成交额 —— **流动性度量的原料** |")
    A("| `trades` | float64 | 笔 | `klines.count` | bar 内成交笔数 |")
    A("| `taker_buy_volume` | float64 | 张 | `klines` | 主动买成交量 |")
    A("| `taker_buy_quote_volume` | float64 | USDT | `klines` | 主动买成交额 |")
    A("| `oi` | float64 | 张 | `metrics.sum_open_interest` | **`OI(ts_end)`** —— 区间终点时刻的持仓量 |")
    A("| `mark_close` | float64 | USDT | `markPriceKlines` | 标记价收盘 |")
    A("| `index_close` | float64 | USDT | `indexPriceKlines` | 指数价收盘 |")
    A("| `funding_rate` | float64 | 比率 | `fundingRate` | **仅结算时刻有值**，不作填充 |")
    A("| `funding_interval_hours` | float64 | 小时 | `fundingRate` | 结算时刻为真实值；非结算小时为**上一次结算公布的区间** |")
    A("| `bar_missing` | bool | — | 派生 | 该小时在 `klines_1h` 中无对应行 |")
    A("| `oi_missing` | bool | — | 派生 | 该小时的 OI 快照不存在 |")
    A("")
    A("### 三个必须知道的语义")
    A("")
    A("**① `oi` 是「区间终点」的对齐值，不是 bar 起点的值。**")
    A("")
    A("```")
    A("bar [20:00, 21:00)  配  OI(21:00)     ← oi_1h 表里这一行的 ts = 20:00")
    A("```")
    A("")
    A("`oi_1h` 里 `ts` 比源 `create_time` **早 1 小时**，这是刻意的 ——")
    A("在 `ts_end` 这一刻，价格与 OI **同时可得**，不构成前视。")
    A("")
    A("**② `funding_rate` 的稀疏性是语义，不是质量问题。**")
    A("")
    A(f"全部行中只有约 **16.6%** 有值（结算时刻）。其余为 `NaN` 是设计使然。")
    A("**因此它不在缺失报告的检测范围内** —— 否则会产出上百万段假缺口。")
    A("")
    A("**③ `funding_interval_hours` 是前向填充的。**")
    A("")
    A("非结算小时的值 = 「上一次结算时公布的区间长度」。这**不是编造** ——")
    A("它是决策时刻可得的已知量。区间切换时（实测 95 个合约发生过）会有 1–3 小时")
    A("填的是旧值，这是已知的、不可避免的失真。")
    A("")
    A("---")
    A("")
    A("## 4. 覆盖面与已知缺口")
    A("")
    A(f"面板覆盖 **{n_syms} 个合约**、**{n_fe_rows:,} 行**。")
    A("")
    A("### 4.1 文件层")
    A("")
    if len(MF):
        A(f"**{len(MF)} 个源文件在归档里不存在**（`confirmed_404`），"
          f"涉及 {MF['symbol'].nunique()} 个合约。全部是 `metrics`（OI）的日文件。")
        A("")
        A("这是**归档自身的空洞**，不是下载失败。明细见 `04_qa/missing_files.parquet`。")
    else:
        A("无下载失败的文件。")
    A("")
    A("### 4.2 记录层")
    A("")
    A("| 指标 | 缺口段数 | 总缺失小时 | 最长一段 |")
    A("|---|---|---|---|")
    for m in METRICS:
        sub = G[G["metric"] == m]
        if len(sub):
            A(f"| `{m}` | {len(sub):,} | {sub['hours'].sum():,.0f} | "
              f"{sub['hours'].max():,.0f} 小时 |")
        else:
            A(f"| `{m}` | 0 | 0 | — |")
    A("")
    A("覆盖率（`n_present / n_total`）：")
    A("")
    A("| 指标 | 中位 | < 0.99 的合约 | < 0.90 的合约 |")
    A("|---|---|---|---|")
    for m in METRICS:
        c = V[V["metric"] == m]["coverage"]
        A(f"| `{m}` | {c.median():.4f} | {int((c < 0.99).sum())} | {int((c < 0.90).sum())} |")
    A("")
    A("### 4.3 覆盖率的缺口来源（已知，非缺陷）")
    A("")
    A("**下架合约的尾部。** 合约下架后 `klines` 归档仍会写「整月零成交的空行」到样本末端，")
    A("而 `funding` / `mark` / `index` 在下架时就断了。Step 5 已把死尾裁到「最后活跃日」，")
    A("但合约活着时若归档本身有洞，就会体现为 `mark` / `index` 的缺口。")
    A("")
    A("**`oi == 0` 是全市场发布事件。** 实测 48 天里出现过 OI 全市场为 0")
    A("（如 2022-03-07 一天 105 个合约同时为 0）。它的中位合约占比仅 0.029%，")
    A("**不能作为单合约的可靠性判据**，因此不在资格闸里，只在缺失报告里。")
    A("")
    A("---")
    A("")
    A("## 5. `universe_*` 的用法")
    A("")
    A("```python")
    A("import pandas as pd")
    A("m = pd.read_parquet('data/03_reference/universe_membership.parquet')")
    A("f = pd.read_parquet('data/02_features/features_1h/year=2024/chunk=2024-03.parquet')")
    A("panel = f.merge(m, on=['symbol', 'month'], how='inner')  # 只保留成员")
    A("```")
    A("")
    A("**`features_1h` 含全部候选池合约，不只是成员。** 若分析针对样本内成员，")
    A("必须与 `universe_membership` join —— 否则会把落选合约也算进去。")
    A("")
    A("**资格与成员的粒度是「月」，不是「日」。** 成员集在月内冻结")
    A(f"（`refresh_months = {cfg.refresh_months}`）；`liq` 逐日滚动，但只在月初取一次。")
    A("")
    A("**`member_changes` 的口径**：`month` 是**新成员集生效的月份**，")
    A("`n_entered` / `n_exited` 相对**上一个月**。")
    A("")
    A("---")
    A("")
    A("## 6. 缺失报告的读法")
    A("")
    A("`04_qa/gaps.parquet` 按 `(symbol, metric, gap_start)` 排序 ——")
    A("**同一合约的缺口相邻**，便于按合约排查。")
    A("")
    A("选读建议：")
    A("")
    A("| 目的 | 做法 |")
    A("|---|---|")
    A("| 看某个合约的概况 | 按 `symbol` 过滤，看 `coverage.parquet` |")
    A("| 看某个合约的全部缺口 | 按 `symbol` 过滤 `gaps.parquet`（已相邻） |")
    A("| 找真正严重的问题 | 在 `gaps.parquet` 里筛 `hours >= 24` |")
    A("| 判断缺口是否源于样本边界 | 看 `started_before_sample` 列 |")
    A("")
    A(f"完整 `gaps.parquet` 有 {len(G):,} 行，其中 `hours >= 24` 的只有 "
      f"{int((G['hours'] >= 24).sum()):,} 行。**单小时缺口占绝大多数** ——")
    A("它们保留在文件里供审计，但不应淹没长缺口。")
    A("")
    A("---")
    A("")
    A("## 7. 可复现性")
    A("")
    A("全部产出可由 `REPRODUCE.md` 的六条命令从零重建。")
    A("")
    A("`04_qa/checksums.sha256` 记录 `data/` 下**全部产出文件的 SHA256**，")
    A("包含 `raw/`（Step 3 下载的源数据）—— 共 1,440 个文件 / 2.2 GB。")
    A("")
    A("**它是内部一致性记录，不是来源证明。** 它只能验证「本地文件与产出时一致」，")
    A("不能验证「下载到的东西等于 Binance 归档里的东西」—— 那需要官方 `.CHECKSUM`。")
    A("")
    A("**校验应当 0 个不一致。** 校验和是本流程最后一个写盘动作，")
    A("它此前写入的每一个文件（含 `00_config/sample_end.json` 的运行元信息）都被纳入哈希。")
    A("不在名单里的只有 `checksums.sha256` 自身、`data/REPRODUCE.md`（在 `data/` 根，")
    A("不属于任何编号层）与写盘用的 `.part` 临时文件。")
    A("")
    return "\n".join(L)


# ============================================================================
# 校验和
# ============================================================================

def checksum_targets() -> list:
    """列出参与校验和的全部文件，顺序固定（供计数与哈希共用）。

    含 `raw/` —— 它也是产出（Step 3 下载的源数据），校验它能查出归档与本地不一致。
    排除 `checksums.sha256` 自身与写盘中的 `.part` 临时文件。
    1,440 个文件 / 2.2 GB，实测约 5 秒。
    """
    targets = []
    for sub in ("00_config", "raw", "01_layer2", "02_features",
                "03_reference", "04_qa"):
        p = DATA / sub
        if p.exists():
            targets += [f for f in sorted(p.rglob("*")) if f.is_file()]
    return [f for f in targets
            if f.name != "checksums.sha256" and f.suffix != ".part"]


def verify_checksums() -> int:
    """逐行重算 `04_qa/checksums.sha256` 里的 SHA256，返回不一致个数。

    不写任何文件。用 `--verify` 调用；0 表示本地产出与产出时逐字节一致。
    """
    ck = QA / "checksums.sha256"
    if not ck.exists():
        print(f"找不到 {ck} —— 先跑一次 build_qa.py 生成。", file=sys.stderr)
        return -1
    bad, n = [], 0
    for line in ck.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        h, rel = line.split("  ", 1)
        rel = rel.strip()
        p = DATA / rel
        n += 1
        if not p.exists():
            bad.append((rel, "缺失"))
            continue
        got = hashlib.sha256()
        with open(p, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                got.update(chunk)
        if got.hexdigest() != h:
            bad.append((rel, "内容不一致"))
    for rel, why in bad:
        log(f"  {why}  {rel}")
    log(f"核验 {n:,} 个文件：{'全部一致' if not bad else f'{len(bad)} 个不一致'}")
    return len(bad)


def write_checksums() -> int:
    """对 data/ 下所有产出文件算 SHA256，覆盖写 `04_qa/checksums.sha256`。

    **必须在最后一步调用**：此前写入的任何文件都会被纳入哈希。
    本函数之前若还有写入，校验必然报不一致。
    """
    targets = checksum_targets()
    lines = []
    for f in targets:
        h = hashlib.sha256()
        with open(f, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        lines.append(f"{h.hexdigest()}  {f.relative_to(DATA).as_posix()}")
    (QA / "checksums.sha256").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8", newline="\n")
    return len(lines)


# ============================================================================
# 复现命令
# ============================================================================

def build_reproduce(cfg, sample_end: str) -> str:
    L = []
    A = L.append
    A("# 复现命令")
    A("")
    A(f"sample_end = `{sample_end}`　sample_start = `{cfg.sample_start}`")
    A("")
    A("按顺序执行六条命令即可从零重建全部 D1 产出。")
    A("")
    A("## 前置")
    A("")
    A("- Python 3.12 + `pandas` / `pyarrow`（实为 2.3.3 / 23.0.1）")
    A("- 下载【只能用 Python 的 `urllib`】—— 本机 Windows schannel 故障，")
    A("  `curl` 与 `Invoke-WebRequest` 一律失败")
    A("- **`s3-ap-northeast-1.amazonaws.com` 与 `www.binance.com` 的 DNS 被污染**，")
    A("  需要 VPN。`data.binance.vision`（CloudFront）不受影响")
    A("")
    A("## 六条命令")
    A("")
    A("```bash")
    A("# Step 0–2  枚举归档 → 硬过滤 → 逐月流动性排名 → 候选池")
    A("python phase1/build_candidate_pool.py --sample-end " + sample_end)
    A("")
    A("# Step 3  下载候选池的 raw 数据（~34.7 万个文件 / 1.10 GB）")
    A("python phase1/fetch_market_data.py --sample-end " + sample_end)
    A("")
    A("# Step 4  建第 2 层 4 张规范化表")
    A("python phase1/build_layer2.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 5  建 features_1h（19 列密集网格）")
    A("python phase1/build_features.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 6a 四条资格闸 → universe 四张表")
    A("python phase1/build_universe.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 6b 缺失报告 + 数据字典 + 校验和")
    A("python phase1/build_qa.py --out-root data --sample-end " + sample_end)
    A("```")
    A("")
    A("## 自测")
    A("")
    A("```bash")
    A("python config.py            # 8 项")
    A("python -m lib.schema        # 65 项")
    A("```")
    A("")
    A("## 核验")
    A("")
    A("```bash")
    A("# 重算全部产出文件的 SHA256，0 个不一致则退出码 0")
    A("python phase1/build_qa.py --out-root data --sample-end " + sample_end + " --verify")
    A("```")
    A("")
    A("## 说明")
    A("")
    A("- **Step 2 与 Step 3 需要 VPN**（S3 枚举）。Step 4/5/6 是纯本地计算，不需要。")
    A("- Step 2 的月频 klines 缓存读完即删，**重跑会重新下载**（约 4 分钟）。")
    A("- 全部脚本的产出目录由 `--out-root` / `--skip-download` 等参数显式指定，")
    A("  **不依赖环境变量**（环境变量不跨 shell 保留，曾经因此把冒烟结果写进正式目录）。")
    A("- **Step 6b 必须在最后跑**：校验和是它的最后一个写盘动作，")
    A("  此前写入的每一个文件都被纳入哈希。重跑 Step 3–6a 会使校验和失效，")
    A("  需重跑 Step 6b 重新生成。")
    A("")
    return "\n".join(L)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
