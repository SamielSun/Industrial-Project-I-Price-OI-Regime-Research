#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
regime_generator —— Phase 2 主脚本：三频率 regime 标签 + 四张表 + 一张图

它在项目中的位置：Phase 2（给 features_1h 标注 price/OI 四状态 + funding 四档 +
市场条件），交付物 D2 的主体。

做什么
------
  读 data/02_features/features_1h
    → 逐合约算 1h 的逐点有效掩码 / 变化量 / 滚动分位阈值 / regime
    → 按 UTC 整点重采样出 4h / 8h 标签（存量取桶右端，见 §4.1）
    → 挂 funding 状态（结算序列上算分位，按阶跃铺到小时，§1.1）
    → 挂市场条件（三步配方，§5.1）
    → 挂 in_universe（按 ts_end 的月，§6.2）
    → 写 data/05_regime/regime_labels/freq=.../year=/chunk=.parquet（171 个）
    → 四张表 + 一张图 + data_dictionary.md + checksums.sha256
    → 写 phase2_regime/REPRODUCE.md

⚠️ 三条实现上必须守住的约束
  1. **按合约的连续序列算，不能按 chunk（月）独立算。** 4h/8h 的决策时刻在上一天
     （月初时是上个月）还有前一个决策点。
  2. **先屏蔽，再算阈值。** 顺序反了，被剔除的观测会污染阈值分布（§3.3）。
  3. **最短历史用时间判据（距首条 ≥30 天），不是观测数。** funding 序列不规则，
     "30 天"无法用固定观测数表达（§1.2）。

设计参数见 config.py 的 RegimeConfig；完整依据见 phase3_event/PHASE3_GUIDANCE.md。

用法
----
  python phase2_regime/regime_generator.py --out-root <data 绝对路径>
  python phase2_regime/regime_generator.py --out-root data --subset BTCUSDT LITUSDT
  python phase2_regime/regime_generator.py --out-root data --freqs 4h --no-validate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import gc
import re
import sys
import time
from collections import Counter, defaultdict

# 控制台是 GBK：本文件里有 9 处 '⚠️'（U+26A0/U+FE0F），GBK 编不了 —— 一旦打印就崩。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根
import config as cfg_mod                                          # noqa: E402
from lib.schema import REGIME_LABELS, SchemaViolation, validate    # noqa: E402

HOUR_NS = 3_600_000_000_000
DAY_NS = 86_400_000_000_000
# 1d = note 第 64 行点名的 robustness 轴（"Daily aggregation for robustness"）。
# 决策时刻落在 UTC 00:00，与 ts_end % fh == 0 的规则天然兼容。
FREQ_HOURS = {"1h": 1, "4h": 4, "8h": 8, "1d": 24}
OUT_COLS = [c.name for c in REGIME_LABELS.columns]

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
IN = DATA
FE_DIR = DATA / "02_features" / "features_1h"
OUT = DATA / "05_regime"
MEMBERSHIP = DATA / "03_reference" / "universe_membership.parquet"

T_START = time.time()
LOG: list[str] = []


def log(msg: str) -> None:
    line = f"[{time.time() - T_START:6.0f}s] {msg}"
    print(line, flush=True)
    LOG.append(line)


def configure(out_root: Path, in_root: Path, subset: list[str] | None, freqs: list[str]):
    """out_root = 产出位置；in_root = 读取位置（冒烟时两者不同，见 --in-root）。"""
    global DATA, IN, FE_DIR, OUT, MEMBERSHIP
    DATA = out_root.resolve()
    IN = in_root.resolve()
    FE_DIR = IN / "02_features" / "features_1h"
    OUT = DATA / "05_regime"
    MEMBERSHIP = IN / "03_reference" / "universe_membership.parquet"


# ============================================================================
# 读入：面板（逐合约切片）+ 时点 universe
# ============================================================================

def read_membership() -> tuple[dict[tuple[str, str], bool], dict[str, set[str]], dict[tuple[str, str], bool]]:
    """返回 (成员集合, 逐月成员, ...)。month 是【决策时刻】的月。"""
    if not MEMBERSHIP.exists():
        raise FileNotFoundError(f"找不到 {MEMBERSHIP}")
    m = pq.read_table(str(MEMBERSHIP), partitioning=None).to_pandas()
    by_month: dict[str, set[str]] = {k: set(g["symbol"]) for k, g in m.groupby("month")}
    keys = {(r.symbol, r.month) for r in m.itertuples(index=False)}
    return keys, by_month, {}


def chunk_month(path: Path) -> str:
    return re.search(r"chunk=(\d{4}-\d{2})", path.name).group(1)


def panel_files() -> list[Path]:
    fs = sorted(FE_DIR.rglob("*.parquet"))
    if not fs:
        raise FileNotFoundError(f"找不到面板：{FE_DIR}")
    return fs


# ============================================================================
# 市场条件（§5.1 三步配方）
# ============================================================================

def build_market_state(by_month: dict[str, set[str]], cfg) -> pd.Series:
    """市场状态序列（按 ts_end 索引）：low / mid / high / unknown。

    = (high − low) / close 的每小时【横截面中位】 → 24h 平滑 →
      trailing 1 年（8,760h）的 1/3、2/3 分位。

    为什么用 (high−low)/close 而不是 |ret|：|ret| 只看净路径 —— 一根 bar 冲高 3% 又
    回到原点时 |ret| ≈ 0，会被判成"最安静"，而它显然很剧烈。(high−low)/close 能捕捉
    这种往返。代价是对坏 tick 更敏感，靠横截面中位挡掉单合约的异常值。

    ⚠️ 这是【分组变量】，不参与筛选 —— 不筛掉任何观测；决定哪些小时算事件的是
    label_contract() 里的 p70 阈值。

    unknown 有两类：市场序列还不存在（universe 首个成员月 2022-03）加上它的 30 天预热，
    以及 2024-10-28 21:00 UTC 那一小时（50 个成员 quote_volume 全为 0，截面为空）。
    """
    parts = []
    for f in panel_files():
        ym = chunk_month(f)
        ms = by_month.get(ym, set())
        if not ms:
            continue
        raw = pq.read_table(str(f), partitioning=None,
                            columns=["symbol", "ts", "close", "high", "low", "quote_volume",
                                     "bar_missing"]).to_pandas()
        d = raw[raw["symbol"].isin(ms)].sort_values(["symbol", "ts"], kind="stable")
        if d.empty:
            continue
        # 每根 bar 的区间幅度【自给自足】，不需要前一根 bar —— 所以月边界不需要补种子行。
        # （旧版用 pct_change 时才会踩到"每月第一根没有前值 → 01:00 被错标 unknown"的坑，
        #  换成 (high−low)/close 之后这个坑从根上消失了。）
        h_, l_, c_ = d["high"].to_numpy(float), d["low"].to_numpy(float), d["close"].to_numpy(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            d["bar_range"] = (h_ - l_) / c_    # 该小时的区间幅度（波动率代理）
        ok_hl = np.isfinite(h_) & np.isfinite(l_) & (l_ > 0) & (h_ >= l_)
        keep = ((~d["bar_missing"].to_numpy()) & (d["quote_volume"].to_numpy() > 0)
                & ok_hl & np.isfinite(d["bar_range"].to_numpy()))
        d = d[keep]
        if d.empty:
            continue
        # 索引用【ts_end】（= 该小时结束后才可得的决策时刻），不是 ts ——
        # 否则下游按 ts_end 查表会整体错开一小时。
        d["te"] = d["ts"] + pd.Timedelta(hours=1)
        parts.append(d.groupby("te")["bar_range"].median())
        del d
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated()]
    log(f"  市场截面序列 {len(s):,} 小时（篮子 = 时点 universe 成员）")

    sm = s.rolling(cfg.mkt_vol_smooth_hours,
                          min_periods=cfg.mkt_vol_smooth_hours // 2).mean()
    win = f"{cfg.mkt_vol_window_hours}h"
    q_lo, q_hi = cfg.mkt_vol_quantiles
    lo = sm.rolling(win).quantile(q_lo)
    hi = sm.rolling(win).quantile(q_hi)
    # 最短历史：时间判据，不是观测数
    enough = (sm.index - sm.index[0]) >= pd.Timedelta(days=cfg.mkt_vol_min_history_days)
    v = sm.to_numpy()
    vol = np.full(len(sm), "unknown", dtype=object)
    m = np.asarray(enough) & np.isfinite(v) & lo.notna().to_numpy() & hi.notna().to_numpy()
    vol[m & (v <= lo.to_numpy())] = "low"
    vol[m & (v > hi.to_numpy())] = "high"
    vol[m & (v > lo.to_numpy()) & (v <= hi.to_numpy())] = "mid"

    out = pd.Series(vol, index=sm.index)
    n = Counter(out.to_numpy())
    log(f"  市场状态：low {n['low']:,} / mid {n['mid']:,} / high {n['high']:,} / unknown {n['unknown']:,}"
        f"  （覆盖 {(len(out) - n['unknown']) / len(out):.4f}）")
    return out


# ============================================================================
# 单合约：标签
# ============================================================================

def rolling_q_by_time(s: pd.Series, window: str, q: float, min_days: int) -> np.ndarray:
    """时间窗滚动分位 + 时间判据的最短历史（距首条 < min_days 天的位置置 NaN）。"""
    r = s.rolling(window).quantile(q).to_numpy()
    if min_days > 0 and len(s):
        # 用 asi8（int64 纳秒）—— tz-aware 索引的 .to_numpy() 给的是 Timestamp 对象数组
        t = s.index.asi8
        gap_days = (t - t[0]) / DAY_NS
        r = np.where(gap_days >= min_days, r, np.nan)
    return r


def label_contract(sym: str, ts: np.ndarray, close: np.ndarray, oi: np.ndarray,
                   qv: np.ndarray, f_rate: np.ndarray,
                   mkt: pd.Series, member_keys: set, cfg,
                   freqs: tuple[str, ...]) -> dict[str, np.ndarray]:
    """返回 {freq: 该合约在该频率下的标签 DataFrame}。"""
    n = len(ts)
    bar_missing = ~np.isfinite(close)
    point_ok = (~bar_missing) & (qv > 0) & np.isfinite(oi) & (oi > 0)
    # 逐点失败的归因（§3.4 优先级：no_price > halt > no_oi）
    fail_at = np.full(n, "ok", dtype=object)
    fail_at[bar_missing] = "no_price"
    fail_at[(~bar_missing) & (qv == 0)] = "halt"
    fail_at[(~bar_missing) & (qv != 0) & ~(np.isfinite(oi) & (oi > 0))] = "no_oi"

    # ---- funding：结算序列（funding_rate 对齐 ts） ----
    fsel = np.isfinite(f_rate)
    f_ts = ts[fsel]
    f_rate_ok = f_rate[fsel]
    if len(f_ts):
        fser = pd.Series(f_rate_ok, index=pd.DatetimeIndex(f_ts))
        fp25 = rolling_q_by_time(fser, f"{cfg.funding_window_days}D", 0.25, cfg.funding_min_history_days)
        fp75 = rolling_q_by_time(fser, f"{cfg.funding_window_days}D", 0.75, cfg.funding_min_history_days)
        fp90 = rolling_q_by_time(fser, f"{cfg.funding_window_days}D", 0.90, cfg.funding_min_history_days)
    else:
        fp25 = fp75 = fp90 = np.full(0, np.nan)

    tsa = pd.DatetimeIndex(ts).asi8          # 用 asi8 避免 numpy 的 tz 警告
    te = tsa + HOUR_NS                       # ts_end
    te_hour = te // HOUR_NS
    month_of = pd.DatetimeIndex(te).strftime("%Y-%m")
    in_uni = np.array([(sym, mm) in member_keys for mm in month_of], dtype=bool)
    # ⚠️ 必须 tz-aware：mkt 的索引是 UTC，用 tz-naive 索引 reindex 会全部落空（静默）
    mkt_vals = mkt.reindex(pd.to_datetime(te, utc=True)).to_numpy()

    # fund lookup：最近一次 ts ≤ ts_end 的结算
    if len(f_ts):
        f_ns = pd.DatetimeIndex(f_ts).asi8
        fi = np.searchsorted(f_ns, te, side="right") - 1
    else:
        fi = np.full(n, -1, dtype=np.int64)

    out: dict[str, np.ndarray] = {}
    for f in freqs:                      # ⚠️ 用 CLI 覆盖后的 freqs，不是 cfg.freqs
        fh = FREQ_HOURS[f]
        # 决策时刻 = ts_end 落在 fh 的 UTC 整点上；dec_idx 是在本合约 1h 数组里的下标
        dec_idx = np.flatnonzero(te_hour % fh == 0)
        if len(dec_idx) == 0:
            continue
        dec_idx = dec_idx[1:]                    # §4.3 首桶整体丢弃（它没有前一个决策点）
        if len(dec_idx) == 0:
            continue
        # 跨度：f_hours + 1 根 1h 行，每一根都要有效（§3.3）
        # 变化窗 N 来自 RegimeConfig.n_bars（N=1 时 fh*nb == fh，产出与旧版逐字节相同）。
        # 跨度必须覆盖 N 根 bar：fh*nb + 1 根 1h 行。
        nb = cfg.n_bars
        need = fh * nb + 1
        span_cnt = pd.Series(point_ok.astype("float64")).rolling(need).sum().to_numpy()
        span_ok = span_cnt == need

        c = close[dec_idx]
        o = oi[dec_idx]
        ok_span = span_ok[dec_idx]
        # 只在有效的跨度上算变化量（span 外的 oi 可能为 0，会报除零）
        with np.errstate(divide="ignore", invalid="ignore"):
            pc = np.where(ok_span, c / close[dec_idx - fh * nb] - 1.0, np.nan)
            oc = np.where(ok_span, o / oi[dec_idx - fh * nb] - 1.0, np.nan)

        dec_ts_end = te[dec_idx]
        ser_pc = pd.Series(np.abs(pc), index=pd.DatetimeIndex(dec_ts_end))
        ser_oc = pd.Series(np.abs(oc), index=pd.DatetimeIndex(dec_ts_end))
        win = f"{cfg.window_days}D"
        thr_p = rolling_q_by_time(ser_pc, win, cfg.quantile_main, cfg.min_history_days)
        thr_o = rolling_q_by_time(ser_oc, win, cfg.quantile_main, cfg.min_history_days)

        regime = np.full(len(dec_idx), "undefined", dtype=object)
        lab = (np.abs(pc) > thr_p) & (np.abs(oc) > thr_o)
        regime[lab & (pc > 0) & (oc > 0)] = "R1"
        regime[lab & (pc > 0) & (oc < 0)] = "R2"
        regime[lab & (pc < 0) & (oc > 0)] = "R3"
        regime[lab & (pc < 0) & (oc < 0)] = "R4"

        # excl_reason：自身失败 → span_gap → warmup → ok
        reason = np.array(fail_at[dec_idx], dtype=object)
        reason[(reason == "ok") & ~ok_span] = "span_gap"
        reason[(reason == "ok") & ~np.isfinite(thr_p)] = "warmup"
        reason[(reason == "ok") & (regime == "undefined")] = "ok"   # 没过阈值但仍算 ok

        # funding 状态（阶跃：取最近一次结算的分位）
        fund_idx = fi[dec_idx]
        has_f = fund_idx >= 0
        f_rate_v = np.full(len(dec_idx), np.nan)
        f_rate_v[has_f] = f_rate_ok[fund_idx[has_f]]
        p25 = np.full(len(dec_idx), np.nan); p75 = p25.copy(); p90 = p25.copy()
        if len(f_ts):
            p25[has_f] = fp25[fund_idx[has_f]]
            p75[has_f] = fp75[fund_idx[has_f]]
            p90[has_f] = fp90[fund_idx[has_f]]
        good = np.isfinite(p25)
        neg = good & (f_rate_v <= p25)
        neu = good & (f_rate_v > p25) & (f_rate_v <= p75)
        hig = good & (f_rate_v > p75)
        ext = good & (f_rate_v > p90)

        mv = mkt_vals[dec_idx]
        out[f] = dict(
            symbol=np.full(len(dec_idx), sym, dtype=object),
            ts_end=dec_ts_end, freq=np.full(len(dec_idx), f, dtype=object),
            ts=dec_ts_end - fh * HOUR_NS,
            close=c, oi=o, price_change=pc, oi_change=oc,
            price_thr=thr_p, oi_thr=thr_o,
            regime=regime, excl_reason=reason,
            funding_negative=neg, funding_neutral=neu,
            funding_high=hig, funding_extreme=ext,
            funding_p25=p25, funding_p75=p75, funding_p90=p90,
            mkt_vol_state=np.where(np.isin(mv, ["low", "mid", "high"]), mv, "unknown"),
            in_universe=in_uni[dec_idx],
        )
    return out


def to_frame(d: dict[str, np.ndarray]) -> pd.DataFrame:
    df = pd.DataFrame(d)
    for c in REGIME_LABELS.columns:
        if c.dtype == "timestamp":
            df[c.name] = pd.to_datetime(df[c.name], utc=True)
        elif c.dtype == "float64":
            df[c.name] = df[c.name].astype("float64")
        elif c.dtype == "bool":
            df[c.name] = df[c.name].astype(bool)
        else:
            df[c.name] = df[c.name].astype("string")
    return df[OUT_COLS]


# ============================================================================
# 聚合：四张表 + 一张图 + 文档 + 校验和 + REPRODUCE
# ============================================================================

VALID_REASONS = ("ok", "warmup")      # 能算出变化量的行（warmup 只是没阈值）
REASONS = ("ok", "no_price", "halt", "no_oi", "span_gap", "warmup")
REGIMES = ("R1", "R2", "R3", "R4")
STATES = ("low", "mid", "high", "unknown")

NL = chr(10)


def tally(df: pd.DataFrame, sym: str, fq: str, K) -> None:
    """把一帧标签的统计累加进 K。内存里只留计数，不留数据。"""
    reason = df["excl_reason"].to_numpy()
    reg = df["regime"].to_numpy()
    state = df["mkt_vol_state"].to_numpy()
    ym = pd.DatetimeIndex(df["ts"]).strftime("%Y-%m").to_numpy()
    valid = np.isin(reason, VALID_REASONS)
    lab = reg != "undefined"

    K["rows"][(fq,)] += len(df)
    K["valid"][(fq,)] += int(valid.sum())
    K["lab"][(fq,)] += int(lab.sum())
    K["Srows"][(sym, fq)] += len(df)
    K["Svalid"][(sym, fq)] += int(valid.sum())
    K["Slab"][(sym, fq)] += int(lab.sum())
    for k, n in zip(*np.unique(reg, return_counts=True)):
        K["rc"][(fq, str(k))] += int(n)
    for k, n in zip(*np.unique(reason, return_counts=True)):
        K["ua"][(sym, fq, str(k))] += int(n)
    for r in REGIMES:
        K["Sreg"][(sym, fq, r)] += int((reg == r).sum())
    for st in np.unique(state):
        m = state == st
        K["Mvalid"][(fq, str(st))] += int((m & valid).sum())
        K["Mlab"][(fq, str(st))] += int((m & lab).sum())
        for r in REGIMES:
            K["Mreg"][(fq, str(st), r)] += int((m & (reg == r)).sum())
    del ym  # 按月的统计由 collect_month_tally() 从落盘文件回读，避免两份来源


def build_tables(K, syms, freqs) -> dict:
    r1 = []
    for fq in freqs:
        nv, nl = K["valid"][(fq,)], K["lab"][(fq,)]
        for r in REGIMES + ("undefined",):
            n = K["rc"][(fq, r)]
            if r == "undefined":
                # 表 1 只覆盖【有效观测】：undefined 行 = n_valid − n_labelled。
                # 不能直接用 K["rc"] 的计数 —— 那里面还含无效观测（no_price / halt /
                # no_oi / span_gap），而分母 n_valid 已把它们排除，分子含、分母不含，
                # 五行相加会超过 100%（实测 1h 100.53% → 1d 101.28%）。
                # 无效观测的归因在表 4（undefined_attribution），不在这里重复。
                n = nv - nl
            r1.append(dict(freq=fq, regime=r, n=n,
                           share_of_labelled=(n / nl if (r != "undefined" and nl) else np.nan),
                           share_of_valid=(n / nv if nv else np.nan)))
    r2 = []
    for s in syms:
        for fq in freqs:
            nr = K["Srows"][(s, fq)]
            if nr == 0:
                continue
            nv, nl = K["Svalid"][(s, fq)], K["Slab"][(s, fq)]
            d = dict(symbol=s, freq=fq, n_rows=nr, n_valid=nv, n_labelled=nl,
                     undefined_share_of_valid=((nv - nl) / nv if nv else np.nan))
            for r in REGIMES:
                n = K["Sreg"][(s, fq, r)]
                d["n_" + r] = n
                d[r + "_share_of_labelled"] = (n / nl if nl else np.nan)
            r2.append(d)
    r3 = []
    for fq in freqs:
        tv = K["valid"][(fq,)]
        for st in STATES:
            nv = K["Mvalid"][(fq, st)]
            if nv == 0:
                continue
            nl = K["Mlab"][(fq, st)]
            d = dict(mkt_vol_state=st, freq=fq, n_valid=nv,
                     share_of_total_valid=(nv / tv if tv else np.nan),
                     n_labelled=nl,
                     undefined_share_of_valid=((nv - nl) / nv if nv else np.nan))
            for r in REGIMES:
                n = K["Mreg"][(fq, st, r)]
                d["n_" + r] = n
                d[r + "_share_of_labelled"] = (n / nl if nl else np.nan)
            r3.append(d)
    r4 = []
    for fq in freqs:
        tr = K["rows"][(fq,)]
        for rs in REASONS:
            n = sum(K["ua"][(s, fq, rs)] for s in syms)
            r4.append(dict(level="global", symbol="", freq=fq, excl_reason=rs, n=n,
                           share_of_rows=(n / tr if tr else np.nan)))
    for s in syms:
        for fq in freqs:
            tr = K["Srows"][(s, fq)]
            if tr == 0:
                continue
            for rs in REASONS:
                n = K["ua"][(s, fq, rs)]
                r4.append(dict(level="symbol", symbol=s, freq=fq, excl_reason=rs, n=n,
                               share_of_rows=(n / tr if tr else np.nan)))
    return {"regime_counts": pd.DataFrame(r1), "by_asset": pd.DataFrame(r2),
            "by_market_condition": pd.DataFrame(r3),
            "undefined_attribution": pd.DataFrame(r4)}


MIN_FIG_RATE = 0.01     # 标注率低于此的月份不画（只可能是 warmup 未走完的首月）


def collect_month_tally(freqs) -> dict:
    """只读 regime + excl_reason 两列，按 (freq, 月) 累计。**图的唯一数据源。**

    刻意从落盘文件回读、而不是用生成时的内存累加器：图和表必须是同一份数据算出来的。
    """
    K = defaultdict(Counter)
    for fq in freqs:
        for p in sorted((OUT / "regime_labels" / f"freq={fq}").rglob("*.parquet")):
            d = pq.read_table(str(p), partitioning=None,
                              columns=["regime", "excl_reason"]).to_pandas()
            ym = p.stem.replace("chunk=", "")
            reason = d["excl_reason"].to_numpy()
            reg = d["regime"].to_numpy()
            K["Tvalid"][(fq, ym)] += int(np.isin(reason, VALID_REASONS).sum())
            K["Tlab"][(fq, ym)] += int((reg != "undefined").sum())
            for r in REGIMES:
                K["Treg"][(fq, ym, r)] += int((reg == r).sum())
    return K


def make_figure(K, freqs, path: Path) -> None:
    """上：四档组成（分母 = 标注数，四条线相加 = 1）
       下：该月标注率（分母 = 有效观测数，右轴）—— 它主要反映滚动阈值的滞后。

    ⚠️ 两条轴缺一不可：组成的分母本身在逐月变化，只看组成会把"哪些小时被标注了"
    的变化误读成"市场结构变了"。
    """
    n = len(freqs)
    # 左：时间序列；右：同一份数据的【年度汇总表】 —— 具体数字直接画进图里，不另存文件。
    # 57 个月的原始点没法逐格排版，年度（按月加总后再算占比）是唯一塞得进图的可读粒度。
    fig = plt.figure(figsize=(19.0, 3.20 * n))
    gs = fig.add_gridspec(n, 2, width_ratios=[2.85, 1.35], hspace=0.68, wspace=0.09)
    colors = {"R1": "#1f6fb4", "R2": "#2e9e5b", "R3": "#d68910", "R4": "#c0392b"}
    dropped = []
    for i, fq in enumerate(freqs):
        ax = fig.add_subplot(gs[i, 0])
        months = sorted({m for (f2, m) in K["Tlab"].keys() if f2 == fq})
        keep = []
        for m in months:
            tv = K["Tvalid"][(fq, m)]
            tl = K["Tlab"][(fq, m)]
            if tv and tl / tv >= MIN_FIG_RATE:
                keep.append(m)
            else:
                dropped.append(f"{fq}/{m}")
        x = pd.to_datetime(keep)
        lab = np.array([K["Tlab"][(fq, m)] for m in keep], dtype=float)
        for r in REGIMES:
            y = np.array([K["Treg"][(fq, m, r)] for m in keep], dtype=float)
            ax.plot(x, y / np.maximum(lab, 1), lw=1.6, color=colors[r], label=r)
        ax.set_ylim(0, 0.6)
        ax.set_xlim(pd.Timestamp(keep[0]), pd.Timestamp(keep[-1]))
        ax.grid(alpha=.25)
        ax.set_ylabel("share of labelled")
        ax.set_title(f"{fq}  ·  composition of labelled observations  "
                     f"(R1-R4 sum to 1, left axis)", fontsize=10, loc="left")

        ax2 = ax.twinx()
        rate = np.array([K["Tlab"][(fq, m)] / max(K["Tvalid"][(fq, m)], 1) for m in keep])
        ax2.plot(x, rate, lw=1.2, color="#777777", ls="--", alpha=.9,
                 label="labelling rate (right)")
        ax2.set_ylim(0, 0.25)
        ax2.tick_params(axis="y", labelsize=8)
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, fontsize=7.5, ncol=5, loc="upper right")

        # ---- 右：该频率的【年度数据表】 ----
        # ⚠️ 用 keep（图实际画的月份）聚合，不是 months —— 否则 warmup 首月会单独成一行，
        # 那一行的占比是极小样本的噪声，且与图里没有这个点自相矛盾。
        # ---- 转置：年份做列、指标做行。每格只放【一个】数，不用把 % 和计数挤在一起 ----
        years = sorted({m[:4] for m in keep})
        agg: dict[str, tuple[int, int, dict[str, int]]] = {}
        for yr in years:
            ms_y = [m for m in keep if m.startswith(yr)]
            agg[yr] = (sum(K["Tvalid"][(fq, m)] for m in ms_y),
                       sum(K["Tlab"][(fq, m)] for m in ms_y),
                       {r: sum(K["Treg"][(fq, m, r)] for m in ms_y) for r in REGIMES})
        # 末列 = 跨年合计（全期），让每行都有"总数"可读
        TOT = "total"
        t_valid = sum(agg[y][0] for y in years)
        t_lab = sum(agg[y][1] for y in years)
        t_reg = {r: sum(agg[y][2][r] for y in years) for r in REGIMES}
        cols = years + [TOT]
        def _cells(get, get_tot) -> list[str]:
            return [get(y) for y in years] + [get_tot()]
        rows = [["valid"] + _cells(lambda y: f"{agg[y][0]:,}", lambda: f"{t_valid:,}"),
                ["labelled"] + _cells(lambda y: f"{agg[y][1]:,}", lambda: f"{t_lab:,}")]
        for r in REGIMES:
            rows.append([f"n {r}"] + _cells(lambda y, r=r: f"{agg[y][2][r]:,}",
                                            lambda r=r: f"{t_reg[r]:,}"))
        for r in REGIMES:
            rows.append([f"{r} %"] + _cells(
                lambda y, r=r: f"{agg[y][2][r] / agg[y][1] * 100:.1f}%" if agg[y][1] else "—",
                lambda r=r: f"{t_reg[r] / t_lab * 100:.1f}%" if t_lab else "—"))
        rows.append(["% labelled"] + _cells(
            lambda y: f"{agg[y][1] / agg[y][0] * 100:.1f}%" if agg[y][0] else "—",
            lambda: f"{t_lab / t_valid * 100:.1f}%" if t_valid else "—"))

        axt = fig.add_subplot(gs[i, 1])
        axt.axis("off")
        axt.set_title(f"{fq}  ·  per year", fontsize=9.5, loc="left", pad=5, color="#333333")
        # 用 bbox 精确占位（loc="center" + scale 会让表溢出坐标区，压住标题和脚注）
        tb = axt.table(cellText=rows, colLabels=[""] + cols, cellLoc="center",
                       colWidths=[0.185] + [0.125] * len(cols),
                       bbox=[0.0, 0.115, 1.0, 0.80])
        tb.auto_set_font_size(False)
        tb.set_fontsize(7.2)
        for (rr, cc), cell in tb.get_celld().items():
            cell.set_linewidth(0.4)
            cell.set_edgecolor("#c8c8c8")
            if rr == 0:                                   # 表头
                cell.set_facecolor("#e8e8e8")
                cell.set_text_props(fontweight="bold", fontsize=7.6)
            elif cc == 0:                                 # 行名
                cell.set_facecolor("#f4f4f4")
                cell.set_text_props(fontweight="bold", fontsize=7.0)
            elif cc == len(cols):                         # 合计列灰底
                cell.set_facecolor("#dcdcdc")
                cell.set_text_props(fontweight="bold")
            elif rr <= len(REGIMES) + 2:                  # 计数块白底
                cell.set_facecolor("#ffffff")
            else:                                         # 占比块浅色底，两块一眼分开
                cell.set_facecolor("#eef4fb")


    fig.suptitle("Phase 2 regime labels — composition vs labelling rate "
                 "(with the yearly numbers alongside)", fontsize=11)

    # gridspec 已给了 hspace/wspace，不能再用 tight_layout（会和表格的坐标打架）
    fig.subplots_adjust(left=0.052, right=0.988, top=0.912, bottom=0.030)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    if dropped:
        log(f"    图：略过 {len(dropped)} 个 warmup 月份 -> {', '.join(dropped)}")


TBL_DOC = [
    ("regime_counts", "Table 1 · counts and shares by freq x regime",
     "share_of_labelled is divided by n_labelled (null for the undefined row); "
     "share_of_valid is divided by n_valid, and the five regime rows sum to 100%. "
     "The table covers VALID observations only: the undefined row is n_valid - n_labelled, "
     "so the invalid rows (no_price / halt / no_oi / span_gap) are NOT counted here - their "
     "attribution is table 4."),
    ("by_asset", "Table 2 · four-regime composition per contract x freq",
     "n_valid counts rows whose change is computable (excl_reason in {ok, warmup}). "
     "undefined_share_of_valid is divided by n_valid; "
     "R*_share_of_labelled is divided by n_labelled."),
    ("by_market_condition", "Table 3 · four-regime composition by market condition x freq",
     "The unknown bucket is mandatory: it holds the observations with no market state, so "
     "share_of_total_valid sums to 100% across the four buckets and the reader does not have to "
     "ask where the remainder went. The buckets (low / mid / high) come from the cross-sectional "
     "median of (high - low) / close - a per-bar range, so a bar that swings up and comes back "
     "still counts as active - smoothed over 24h and cut at its own trailing one-year 1/3 and "
     "2/3 quantiles. This is a grouping variable only; it filters nothing, so no observation is "
     "dropped by it."),
    ("undefined_attribution", "Table 4 · where the undefined rows come from",
     "level is global or symbol. share_of_rows is divided by the total number of rows "
     "for that frequency (or that contract x frequency)."),
]


def write_dictionary(path: Path, tables: dict) -> None:
    L = ["# Data Dictionary — Phase 2 (D2)", "",
         "data/05_regime/ · produced by phase2_regime/regime_generator.py", "",
         "**Scope: column definitions only.** For completeness, see the tables themselves.",
         "", "---", "", "## 1. regime_labels/ — the labelled panel", "",
         "Partitioned freq={1h,4h,8h}/year=YYYY/chunk=YYYY-MM.parquet. "
         "The chunk month comes from ts (bar start), same as features_1h, "
         "so one observation lands in the same chunk in both tables.", "",
         "| Column | Type | Meaning |", "|---|---|---|"]
    for c in REGIME_LABELS.columns:
        L.append(f"| {c.name} | {c.dtype} | {(c.note or '').strip()} |")
    L += ["", "### Rules that shaped these columns", "",
          "- **The four funding booleans are overlapping conditions, not a partition.** "
          "funding_high is (f > p75) and funding_extreme is (f > p90), so "
          "funding_high is a superset of funding_extreme. Both being true on the same row "
          "is normal, not a bug.",
          "- **in_universe uses the month of ts_end** (the decision instant), because "
          "universe_membership.month is the decision instant, not the bar.",
          "- **The first bucket of each contract at each frequency is dropped** — "
          "it has no previous decision instant, and its flow sums would be partial.",
          "- **excl_reason is mutually exclusive.** Priority: the row's own failure, "
          "then span_gap, then warmup, then ok.",
          "- **The minimum history is a duration, not an observation count** "
          "(at least 30 days from the first row of the series).", "",
          "### Reading the labels", "",
          "**Row order.** The labels are partitioned by the month of `ts`, so concatenating every "
          "chunk does **not** give rows ordered by `(symbol, ts_end)` - it gives month-by-month "
          "blocks. Any forward-looking calculation (forward return, next-regime lookup, "
          "reversal/continuation probability) must sort by `symbol, ts_end` first, otherwise the "
          "window silently crosses into another contract. Within a chunk each contract's rows are "
          "contiguous and in time order, which is why the problem only appears after a cross-chunk "
          "concat.", "",
          "**Forward returns need no extra data.** `close` is the price at the decision instant "
          "`ts_end`, so `close.shift(-h) / close - 1` within a contract gives the h-bar forward "
          "return. Phase 3 does not need to re-read the Phase 1 panel except for `quote_volume`, "
          "which is deliberately not carried here.", "",
          "---", "", "## 2. tables/", ""]
    for name, title, note in TBL_DOC:
        df = tables[name]
        L += [f"### {name}.parquet / .csv", "", f"{title}  ({len(df):,} rows)", "", note, "",
              "| Column | Type |", "|---|---|"]
        for c in df.columns:
            L.append(f"| {c} | {df[c].dtype} |")
        L.append("")
    L += ["---", "", "## 3. figures/", "",
          "| File | What |", "|---|---|",
          "| threshold_sensitivity.png | Two rows x four frequencies. TOP: each regime as a share of "
          "ALL valid observations (grey dashed = labelling rate). BOTTOM: each regime as a share within "
          "the labelled set (the mix; the four sum to 100%). Per-panel numbers = each label's largest "
          "move across the six thresholds, in pp. |",
          "| regime_share_over_time.png | Two axes per panel, one panel per frequency. "
          "LEFT: composition of labelled observations (R1-R4, sums to 1). "
          "RIGHT, grey dashed: the labelling rate = share of VALID observations that received a "
          "label. It tracks the trailing threshold LAGGING a volatility jump, NOT event frequency. "
          "Months with labelling rate below 1% (the warm-up ramp, e.g. 2021-12) are omitted. |",
          ""]
    path.write_text(NL.join(L) + NL, encoding="utf-8", newline=NL)


def write_checksums(root: Path) -> int:
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name != "checksums.sha256":
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            lines.append(f"{h.hexdigest()}  {p.relative_to(root).as_posix()}")
    (root / "checksums.sha256").write_text(NL.join(lines) + NL, encoding="utf-8", newline=NL)
    return len(lines)


def write_reproduce(cfg, freqs, args, agg, n_chunks, n_ck, elapsed: float,
                   smoke: bool = False) -> None:
    """缩进式代码块（markdown 支持），避免在生成本文件时引入反引号。

    ⚠️ REPRODUCE.md 属于【正式交付物】，路径绑定在脚本旁边，不受 --out-root 控制。
    冒烟运行不能覆盖它，所以 --subset 时改写进 out-root（只描述冒烟那一次）。
    """
    p = ((OUT / "REPRODUCE.smoke.md") if smoke
         else (Path(__file__).resolve().parent / "REPRODUCE.md"))
    L = ["# Phase 2 — how to rebuild data/05_regime/", "",
         "    python phase2_regime/regime_generator.py --out-root data", "",
         "## Prerequisites", "",
         "- C:\\miniconda\\python.exe (3.12) with pandas / numpy / pyarrow / matplotlib",
         "- data/02_features/features_1h/ and data/03_reference/universe_membership.parquet "
         "must already exist (built by Phase 1)",
         "- **No network access needed** — Phase 2 only reads what Phase 1 downloaded",
         "- ~2 GB RAM. The panel is processed **contract by contract**; "
         "the full 7.25M-row panel is never materialised", "",
         "## Options", "", "| Flag | Meaning |", "|---|---|",
         "| --out-root | **required** — output root (the data/ directory) |",
         "| --in-root | where to read from (defaults to --out-root). Use it for a smoke run "
         "so a subset does not overwrite the real output |",
         "| --subset | process only these contracts (smoke test) |",
         "| --freqs | only these frequencies (1h / 4h / 8h) |",
         "| --batch | contracts per flush (default 20) |",
         "| --no-validate | skip the per-chunk schema validation |", "",
         "Smoke test (writes nothing into data/):", "",
         "    python phase2_regime/regime_generator.py "
         "--out-root %TEMP%\\p2smoke --in-root data --subset BTCUSDT LITUSDT MYXUSDT",
         "", "## Design parameters used for this run", "",
         "    " + NL.join(json.dumps(cfg.snapshot(), ensure_ascii=False, indent=1).split(NL)),
         "", "Every field carries its evidence in the docstrings of config.py; "
         "the full reasoning is in phase3_event/PHASE3_GUIDANCE.md.", "",
         "## Output", "",
         "    data/05_regime/",
         "      regime_labels/freq={1h,4h,8h,1d}/year=YYYY/chunk=YYYY-MM.parquet",
         "      tables/*.parquet + *.csv",
         "      figures/regime_share_over_time.png",
         "      data_dictionary.md",
         "      checksums.sha256",
         "", "## Run summary", "", "| | |", "|---|---|",
         f"| frequencies | {', '.join(freqs)} |",
         f"| label rows written | {agg['rows']:,} |",
         f"| parquet chunks | {n_chunks} |",
         "| schema validation | " + ("skipped" if args.no_validate else f"{n_ck} chunks checked, 0 failed") + " |",
         f"| wall time | {elapsed:.0f} s |", "",
         "## Related command", "",
         "    python phase2_regime/build_sensitivity.py --out-root data",
         "",
         "Adds table 5 (threshold_sensitivity.parquet/.csv) and threshold_sensitivity.png, "
         "then refreshes checksums.sha256. It reads the label tables written above and "
         "recomputes nothing else.", "",
         "checksums.sha256 covers everything under data/05_regime/ except itself. "
         "It is **not** merged into Phase 1's data/04_qa/checksums.sha256 — "
         "D1's certificate stays frozen.", ""]
    p.write_text(NL.join(L) + NL, encoding="utf-8", newline=NL)


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 2 —— 建 regime 标签 + 表 + 图")
    ap.add_argument("--out-root", required=True, help="产出根目录（必填）")
    ap.add_argument("--in-root", default=None,
                    help="读取位置（默认 = --out-root）。冒烟时指向正式 data/，"
                         "避免 3 个合约的产出把正式面板替换掉")
    ap.add_argument("--subset", nargs="+", default=None, help="只处理这些合约（冒烟）")
    ap.add_argument("--freqs", nargs="+", default=None, help="只跑这些频率")
    ap.add_argument("--batch", type=int, default=20, help="每多少个合约落盘一次")
    ap.add_argument("--no-validate", action="store_true", help="跳过 schema 校验")
    ap.add_argument("--figures-only", action="store_true",
                    help="只从已落盘的标签表重绘图（不重算标签/表）。改图样式时用")
    args = ap.parse_args()

    cfg = cfg_mod.REGIME
    freqs = tuple(args.freqs) if args.freqs else cfg.freqs
    for f in freqs:
        if f not in FREQ_HOURS:
            raise SystemExit(f"未知频率 {f!r}；可选 {sorted(FREQ_HOURS)}")
    configure(Path(args.out_root), Path(args.in_root or args.out_root),
              args.subset, list(freqs))

    log("=" * 78)
    log("regime_generator   Phase 2")
    log(f"  产出根目录 : {DATA}")
    log(f"  读取位置   : {IN}" + ("   （冒烟：与产出分离）" if IN != DATA else ""))
    log(f"  频率       : {', '.join(freqs)}")
    log(f"  参数快照   : {json.dumps(cfg.snapshot(), ensure_ascii=False)}")
    log("=" * 78)

    if args.figures_only:
        if not (OUT / "regime_labels").exists():
            raise SystemExit(f"--figures-only 需要已有产出，但 {OUT / 'regime_labels'} 不存在")
        t0 = time.time()
        make_figure(collect_month_tally(freqs), freqs,
                    OUT / "figures" / "regime_share_over_time.png")
        n = write_checksums(OUT)
        log(f"  图已重绘（{time.time() - t0:.0f}s）· checksums.sha256 刷新（{n:,} 个文件）")
        return 0

    member_keys, by_month, _ = read_membership()
    log(f"  时点 universe：{len(by_month)} 个月 · {len(member_keys):,} 个 (合约×月) 单元")

    mkt = build_market_state(by_month, cfg)

    # ---- 逐合约读入（流式）----
    slices: dict[str, list] = defaultdict(list)
    for i, f in enumerate(panel_files(), 1):
        t = pq.read_table(str(f), partitioning=None,
                          columns=["symbol", "ts", "close", "oi", "quote_volume", "funding_rate"])
        sym = t.column("symbol").to_pandas().astype("category")
        ts = t.column("ts").to_pandas().to_numpy()
        cl = t.column("close").to_pandas().to_numpy(dtype="float32")
        oi = t.column("oi").to_pandas().to_numpy(dtype="float32")
        qv = t.column("quote_volume").to_pandas().to_numpy(dtype="float32")
        fr = t.column("funding_rate").to_pandas().to_numpy(dtype="float32")
        codes = sym.cat.codes.to_numpy(); cats = sym.cat.categories
        order = np.argsort(codes, kind="stable"); cb = codes[order]
        bnd = np.flatnonzero(np.r_[True, cb[1:] != cb[:-1], True])
        for a, bb in zip(bnd[:-1], bnd[1:]):
            s = order[a:bb]
            slices[str(cats[cb[a]])].append((ts[s], cl[s], oi[s], qv[s], fr[s]))
        del t, sym, ts, cl, oi, qv, fr, codes, order, cb
        if i % 15 == 0:
            log(f"    读面板 {i}/{len(panel_files())}")
    syms = sorted(slices)
    if args.subset:
        want = set(args.subset)
        syms = [s for s in syms if s in want]
        if not syms:
            raise SystemExit(f"--subset 里的合约都不在面板中：{args.subset}")
    log(f"  面板读毕：{len(syms)} 个合约待处理")

    # ---- 落盘准备 ----
    # ⚠️ **不做任何目录级的移动/替换。** 实测（本机 Windows + 沙箱环境）：
    #   · 产出顶层目录 regime_labels 与其父 05_regime 改名 → ERROR_ACCESS_DENIED
    #   · regime_labels/freq=1h 也被持续锁定（freq=4h / freq=8h 却可以）
    #   · 但目录【内部】的建/删/改名，以及【文件】的 os.replace 全部可行
    # 所以每个 chunk 先写成 .parquet.tmp，关闭后再 os.replace 就位 —— 逐文件原子，
    # 不需要动任何目录。首次运行时这套 bug 不会暴露（目录本来就不存在）。
    d_out = OUT / "regime_labels"
    d_out.mkdir(parents=True, exist_ok=True)
    (OUT / "tables").mkdir(parents=True, exist_ok=True)
    (OUT / "figures").mkdir(parents=True, exist_ok=True)

    writers: dict[str, pq.ParquetWriter] = {}
    buf: dict[str, list[pd.DataFrame]] = defaultdict(list)
    agg = Counter()
    K = defaultdict(Counter)          # 表/图的累加器：K["rc"][(freq, regime)] += n
    t0 = time.time()

    tmp_of: dict[str, Path] = {}

    def flush():
        for key, frames in list(buf.items()):
            df = pd.concat(frames, ignore_index=True)
            table = pa.Table.from_pandas(df, preserve_index=False)
            if key not in writers:
                fq, ym = key.split("|")
                d = d_out / f"freq={fq}" / f"year={ym[:4]}"
                d.mkdir(parents=True, exist_ok=True)
                tmp_of[key] = d / f"chunk={ym}.parquet.tmp"
                writers[key] = pq.ParquetWriter(str(tmp_of[key]), table.schema,
                                                compression="zstd")
            writers[key].write_table(table)
            agg["rows"] += len(df)
        buf.clear()

    for k, sym in enumerate(syms, 1):
        parts = slices.pop(sym)
        ts = np.concatenate([p[0] for p in parts])
        cl = np.concatenate([p[1] for p in parts]).astype("float64")
        oi = np.concatenate([p[2] for p in parts]).astype("float64")
        qv = np.concatenate([p[3] for p in parts]).astype("float64")
        fr = np.concatenate([p[4] for p in parts]).astype("float64")
        res = label_contract(sym, ts, cl, oi, qv, fr, mkt, member_keys, cfg, freqs)
        for fq, d in res.items():
            df = to_frame(d)
            tally(df, sym, fq, K)
            # 分区按 ts（bar 起点）的月 —— 与 features_1h 一致，同一行落在同一个 chunk。
            # 若按 ts_end 分，每月最后一行会溢到下个月的 chunk 里。
            ym = pd.DatetimeIndex(df["ts"]).strftime("%Y-%m")
            for m, g in df.groupby(ym, sort=True):
                buf[f"{fq}|{m}"].append(g)
        del ts, cl, oi, qv, fr, parts, res
        if k % args.batch == 0:
            flush()
            log(f"    {k}/{len(syms)} 个合约  已写 {agg['rows']:,} 行")
            gc.collect()
    flush()
    for w in writers.values():
        w.close()
    # 全部关闭后再逐个就位：每个文件的窗口只有一条 os.replace
    for key, tmp in tmp_of.items():
        fq, ym = key.split("|")
        final = d_out / f"freq={fq}" / f"year={ym[:4]}" / f"chunk={ym}.parquet"
        try:
            os.replace(str(tmp), str(final))
        except PermissionError:                      # 极少数情况下 replace 被拒
            if final.exists():
                final.unlink()
            os.rename(str(tmp), str(final))
    log(f"  标签落盘完成：{agg['rows']:,} 行 / {len(writers)} 个 chunk，耗时 {time.time() - t0:.0f}s")
    # 清掉本次没产出的旧 chunk（只在全量运行时做，--subset 会误删）
    if not args.subset:
        keep = set(tmp_of)
        dropped = 0
        for p in sorted(d_out.rglob("*.parquet")):
            parts = p.relative_to(d_out).parts
            k = f"{parts[0].split('=')[1]}|{p.stem.replace('chunk=', '')}"
            if k not in keep:
                p.unlink()
                dropped += 1
        # 顺带清掉崩溃残留的 .tmp —— rglob("*.parquet") 匹配不到 "*.parquet.tmp"
        for p in sorted(d_out.rglob("*.parquet.tmp")):
            p.unlink()
            dropped += 1
        if dropped:
            log(f"  清理了 {dropped} 个本次未产出的旧 chunk / 残留 tmp")

    # ---- 校验 ----
    n_checked = 0
    bad = 0
    if not args.no_validate:
        t0 = time.time()
        bad = 0
        for p in sorted(d_out.rglob("*.parquet")):
            df = pq.read_table(str(p), partitioning=None).to_pandas()
            n_checked += 1
            try:
                # ts/ts_end 间隔随 freq 变，故关掉内建的「恒 1h」检查。
                # price_thr / oi_thr 是【派生列】：1d 的 2021-12 整块在 30 天预热内，
                # 一根可标注的观测都没有，两列合法地全为 NaN —— 不是解析失败。
                validate(df, REGIME_LABELS, check_ts_end=False,
                         all_null_ok_cols=("price_thr", "oi_thr"))
            except SchemaViolation as e:
                bad += 1
                log(f"    x {p.name}: {e}")
        log(f"  schema 校验：{bad} 个 chunk 失败（共 {n_checked} 个），耗时 {time.time() - t0:.0f}s")
        # ⚠️ 校验失败【不再提前返回】—— 继续把表/图/文档写完，最后用退出码报错。
        # 否则一次校验误报会让 6 分钟的计算全部白跑。

    # ---- 四张表 ----
    tables = build_tables(K, syms, freqs)
    for name, df in tables.items():
        df.to_parquet(str(OUT / "tables" / f"{name}.parquet"), index=False)
        df.to_csv(str(OUT / "tables" / f"{name}.csv"), index=False, encoding="utf-8-sig")
        log(f"  表 {name:<22} {len(df):>7,} 行 x {len(df.columns):>2} 列")

    # ---- 图（数据源 = 落盘的标签表，与上面四张表同源）----
    monthK = collect_month_tally(freqs)
    for fq in freqs:
        lab_m = sum(v for (f2, _), v in monthK["Tlab"].items() if f2 == fq)
        lab_t = int(tables["regime_counts"].query("freq == @fq and regime != 'undefined'")["n"].sum())
        assert lab_m == lab_t, f"{fq}：图用的标注合计 {lab_m:,} 与表 1 的 {lab_t:,} 不符"
    make_figure(monthK, freqs, OUT / "figures" / "regime_share_over_time.png")
    log(f"  图 regime_share_over_time.png（月度合计已与表 1 对平）")

    # ---- 文档 + 校验和 + REPRODUCE ----
    write_dictionary(OUT / "data_dictionary.md", tables)
    n_files = write_checksums(OUT)
    log(f"  data_dictionary.md · checksums.sha256（{n_files:,} 个文件）")
    write_reproduce(cfg, freqs, args, agg, len(writers), n_checked, time.time() - T_START,
                    smoke=bool(args.subset))
    log("  REPRODUCE.md")

    log(f"  总耗时 {time.time() - T_START:.0f}s")
    if bad:
        log(f"  ⚠️ 有 {bad} 个 chunk 未通过 schema 校验，退出码 3")
        return 3
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SchemaViolation as e:
        print(f"\nschema 校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(3)
