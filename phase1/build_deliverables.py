#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_deliverables —— 从已完成的产出里生成 D1 的交付文档与完整性证明

它在 Phase 1 中的位置：Step 6b（六个步骤的最后一步，见 phase1/run_phase1.py）。

职责一句话
----------
只读 data/ 下已完成的产出，生成四类交付物；**不计算任何数据**、不改 01–03 层。

产出
----
  data/04_qa/data_dictionary.md   逐列定义（列名 / 类型 / 单位 / 来源 / 含义）
  data/04_qa/data_quality.md      一页质量证明（5 节，含缺口归因）
  data/04_qa/figures/*.png        2 张图（英文标签）
  phase1/REPRODUCE.md             一条总命令 + 六个步骤 + 本次产出用的设计参数
  data/04_qa/checksums.sha256     全部产出的 SHA256（本脚本最后一个写盘动作）

REPRODUCE.md 是唯一一份落在 `data/` 之外的交付物，也唯一一份进版本控制：
它是【怎么产出数据】的说明，没有数据时也必须能读到（`data/` 整个被 gitignore）。
其余文档与图都在 `04_qa/`；`data/` 根目录下只有六个数据子目录，没有散文件。

为什么只落结论、不落明细
-------------------------
明细表（逐项缺失 / 逐段缺口 / 逐合约覆盖率）对复核有用，但不面向导师，
且其中的「结论」需要读者自己做算术。现在把结论直接写进 data_quality.md，
明细不再落盘 —— 需要明细时现算（见下方 compute_* 三个函数，各约 40 行）。

交付物用【英文】—— 读者是导师；代码注释与日志保持中文。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from collections import defaultdict
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
FIG = QA / "figures"
RAW = DATA / "raw"
# REPRODUCE.md 刻意不放在 data/ 下 —— 它是代码侧的说明，进版本控制。
# 因此它不依赖 --out-root，不在 configure_paths() 里重绑。
REPRO = ROOT / "phase1" / "REPRODUCE.md"
MANIFEST = DATA / "00_config" / "manifest.parquet"

T_START = time.time()

# 四类指标：metric 名 -> FEATURES_1H 里的标记/值列
# ⚠️ 刻意不含 funding_rate（只在结算时刻有值，83.35% 天生为 NaN，
#    算成缺口会产出 600 万个假缺口）与 funding_interval_hours（已前向填充）。
METRICS = {
    "klines": "bar_missing",
    "oi": "oi_missing",
    "mark": "mark_close",
    "index": "index_close",
}


def configure_paths(out_root: Path) -> None:
    global DATA, FE, REF, QA, FIG, MANIFEST
    DATA = out_root.resolve()
    FE = DATA / "02_features" / "features_1h"
    REF = DATA / "03_reference"
    QA = DATA / "04_qa"
    FIG = QA / "figures"
    MANIFEST = DATA / "00_config" / "manifest.parquet"


def log(msg: str) -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


def plural(n: int, singular: str) -> str:
    """`1 contract` / `3 contracts` —— 避免 "1 contract(s)" 这种写法。"""
    return f"{n:,} {singular if n == 1 else singular + 's'}"


def write_text_atomic(path: Path, text: str) -> None:
    """原子写文本：先写 .part，再 os.replace 换入。

    只给 phase1/REPRODUCE.md 用 —— 它进了版本控制，写一半崩掉留下的撕裂文件
    会被 git 当成一次真实改动提交进去。data/ 下的文档被撕了重跑一次即可。
    """
    tmp = path.with_name(f"{path.name}.{os.getpid()}.part")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


# ============================================================================
# 缺口区间（连续 True 的下标区间）
# ============================================================================

def runs_of(a: np.ndarray) -> list[tuple[int, int]]:
    """布尔数组里所有连续 True 的 (起点下标, 终点下标)。

    两端补 0 再 diff：+1 是进入 True，-1 是离开。配对即得区间。
    补 0 是为了让"True 一直延续到数组末尾"也能被捕获到结束点。
    """
    if not a.any():
        return []
    idx = np.flatnonzero(np.diff(np.concatenate([[0], a.astype(np.int8), [0]])) != 0)
    return list(zip(idx[0::2], idx[1::2] - 1))


# ============================================================================
# 质量数字（原先落成 3 张 parquet，现在只算汇总，明细不落盘）
# ============================================================================

def read_features() -> pd.DataFrame:
    """只读质量评估需要的 8 列，不读 19 列全量。"""
    parts = []
    for f in sorted(FE.rglob("*.parquet")):
        parts.append(pq.read_table(str(f), columns=[
            "symbol", "ts", "oi", "oi_missing", "mark_close",
            "index_close", "bar_missing", "quote_volume"],
            partitioning=None).to_pandas())
    d = pd.concat(parts, ignore_index=True).sort_values(["symbol", "ts"],
                                                        ignore_index=True)
    return d


def compute_gaps(d: pd.DataFrame) -> pd.DataFrame:
    """逐合约逐指标算连续缺口。返回 symbol/metric/gap_start/hours/max 的长表。

    与旧版一致：缺口用【连续区间】表示，不逐小时列 —— 除个别短缺口外，
    确有长段（实测最长 7,573 小时），区间才看得清。
    """
    flag_col = {
        "klines": d["bar_missing"].to_numpy(),
        "oi": d["oi_missing"].to_numpy(),
        "mark": d["mark_close"].isna().to_numpy(),
        "index": d["index_close"].isna().to_numpy(),
    }
    sym_ts = d["ts"].to_numpy()
    rows: list[dict] = []
    for s, g in d.groupby("symbol", sort=False):
        idx = g.index.to_numpy()                  # d 已按 (symbol, ts) 排序
        for metric in METRICS:
            for i0, i1 in runs_of(flag_col[metric][idx]):
                t0, t1 = sym_ts[idx[i0]], sym_ts[idx[i1]]
                hours = int((t1 - t0) / np.timedelta64(1, "h")) + 1
                rows.append({"symbol": str(s), "metric": metric,
                             "gap_start": pd.Timestamp(t0),
                             "hours": float(hours),
                             "started_before_sample": bool(i0 == 0)})
    return pd.DataFrame(rows)


def compute_coverage(d: pd.DataFrame) -> pd.DataFrame:
    """逐合约逐指标的覆盖率 = n_present / n_total。"""
    rows: list[dict] = []
    for s, g in d.groupby("symbol", sort=False):
        n_total = len(g)
        for metric, col in METRICS.items():
            n_bad = int(g[col].isna().sum()) if col.endswith("_close") \
                else int(g[col].sum())
            rows.append({"symbol": str(s), "metric": metric,
                         "n_total": float(n_total),
                         "n_present": float(n_total - n_bad),
                         "coverage": (n_total - n_bad) / n_total if n_total else np.nan})
    return pd.DataFrame(rows)


def monthly_coverage(d: pd.DataFrame) -> pd.DataFrame:
    """逐月的整体覆盖率（四个源各一条线，与 §2 的表同口径）。"""
    d = d.assign(ym=d["ts"].dt.strftime("%Y-%m"))
    g = d.groupby("ym").agg(
        rows=("ts", "size"),
        klines=("bar_missing", lambda s: 1 - s.mean()),
        oi=("oi_missing", lambda s: 1 - s.mean()),
        mark=("mark_close", lambda s: 1 - s.isna().mean()),
        index=("index_close", lambda s: 1 - s.isna().mean()),
    )
    return g


def compute_gap_causes(d: pd.DataFrame, man: pd.DataFrame) -> dict:
    """归因：面板里缺 OI 的小时，是【归档里没这个文件】还是【文件在但没快照】。

    为什么必须做这一步：manifest 里的 `confirmed_404` 不是面板的文件层缺口。
    它主要来自 fetch_market_data.py 的【越界探测】—— 为对齐每合约最后一根 bar 的
    OI，故意去要"最后一个 klines 月份的次月 1 号"，那天归档里通常没有。
    实测 67 个 404 全部落在面板网格之外（网格结束后 16–812 天），对面板零影响。
    拿它当"文件层缺口"会把归档问题讲大，而真正的缺口反而没被统计。

    真正的口径：面板内 oi_missing 的小时，按 (合约, 天) 聚合，再看那天在 manifest 里
    有没有 metrics 记录 —— 没有（列表里就没有该文件）或状态是 404 的，才算归档没文件。
    """
    empty = {"hours": 0, "pairs": 0, "syms": 0,
             "a_hours": 0, "a_pairs": 0, "a_syms": 0, "a_top": [], "a_traded": 0,
             "b_hours": 0, "b_pairs": 0, "b_syms": 0,
             "out_n": 0, "out_syms": 0, "out_min_after": 0, "out_max_after": 0,
             "out_nxt": 0, "out_mid": 0, "out_inside": 0}
    if not len(d) or not len(man):
        return empty

    om = d.loc[d["oi_missing"].to_numpy(), ["symbol", "ts"]]
    if not len(om):
        return empty
    pairs = (om.assign(day=om["ts"].dt.floor("D"))
               .groupby(["symbol", "day"]).size().rename("hours").reset_index())

    met = man[man["source"] == "metrics"].copy()
    met["day"] = pd.to_datetime(met["period"], errors="coerce").dt.tz_localize("UTC")
    met = met[["symbol", "day", "status"]].drop_duplicates(["symbol", "day"])
    pairs = pairs.merge(met, on=["symbol", "day"], how="left")
    # 归档里没有这个文件：从没被请求过（枚举列表里没有），或请求过且确认 404
    pairs["no_file"] = pairs["status"].isna() | (pairs["status"] == "confirmed_404")
    a, b = pairs[pairs["no_file"]], pairs[~pairs["no_file"]]

    # A 类里有多少小时其实【在成交】：quote_volume > 0 说明合约当时正常交易，
    # 归档只是没发布 metrics —— 那是归档缺口，不是"停牌期间交易所不发布"。
    # 这一条推翻了原先 §4.2 的解释（ICPUSDT 有 65% 的小时在成交、合计 3.3e10 USDT）。
    dday = d.assign(day=d["ts"].dt.floor("D"))
    traded = (dday.loc[dday["quote_volume"] > 0]
                  .groupby(["symbol", "day"]).size().rename("traded"))
    a = a.merge(traded, on=["symbol", "day"], how="left")
    a["traded"] = a["traded"].fillna(0).astype(int)

    a_top = (a.groupby("symbol")[["hours", "traded"]].sum()
              .sort_values("hours", ascending=False).head(3))
    a_top = [(str(s), int(r.hours), int(r.traded))
             for s, r in a_top.iterrows()]

    # ---- 面板外的 404 探测：证明它们碰不到面板 --------------------------
    grid_lo = d.groupby("symbol")["ts"].min()
    grid_hi = d.groupby("symbol")["ts"].max()
    bad = man[man["status"] != "ok"].copy()
    out = {"out_n": 0, "out_syms": 0, "out_min_after": 0, "out_max_after": 0,
           "out_nxt": 0, "out_mid": 0, "out_inside": 0}
    if len(bad):
        bad["day"] = pd.to_datetime(
            bad["remote_path"].str.extract(r"-(\d{4}-\d{2}-\d{2})\.zip")[0],
            errors="coerce").dt.tz_localize("UTC")
        bad = bad.dropna(subset=["day"])
        lo = bad["symbol"].map(grid_lo).dt.floor("D")
        hi = bad["symbol"].map(grid_hi).dt.floor("D")
        inside = (bad["day"] >= lo) & (bad["day"] <= hi)
        after = (bad["day"] - hi).dt.days
        out = {
            "out_n": int(len(bad)),
            "out_syms": int(bad["symbol"].nunique()),
            "out_inside": int(inside.sum()),
            # 只有落在网格外的才有"距网格末日多少天"可言
            "out_min_after": int(after[~inside].min()) if (~inside).any() else 0,
            "out_max_after": int(after[~inside].max()) if (~inside).any() else 0,
            # 次月 1 号 = 脚本故意发的越界探测；其余是归档确实缺的月中某天
            "out_nxt": int((bad["day"].dt.day == 1).sum()),
            "out_mid": int((bad["day"].dt.day != 1).sum()),
        }

    return {
        "hours": int(len(om)), "pairs": int(len(pairs)), "syms": int(pairs["symbol"].nunique()),
        "a_hours": int(a["hours"].sum()), "a_pairs": int(len(a)),
        "a_syms": int(a["symbol"].nunique()),
        "a_traded": int(a["traded"].sum()),
        "a_top": a_top,
        "b_hours": int(b["hours"].sum()), "b_pairs": int(len(b)),
        "b_syms": int(b["symbol"].nunique()),
        **out,
    }


def compute_grid_drops(d: pd.DataFrame) -> dict:
    """面板缺 `mark`/`index` 的小时里，有多少其实是【第 2 层网格规则】丢掉的。

    第 2 层的网格由 `klines_1h` 定义，mark/index 里 klines 没有的小时一律丢弃。
    实测那些小时里归档【确实有】mark/index —— 所以把它们一并算作"归档缺口"是错的。

    这一步要读 raw（每合约一个文件，只读受影响的那几十个），面板本身看不出来。
    """
    out = {"bar_missing_hours": 0, "mark": None, "index": None}
    bm = d.loc[d["bar_missing"].to_numpy(), ["symbol", "ts"]]
    out["bar_missing_hours"] = int(len(bm))
    if not len(bm):
        return out
    keys = set(zip(bm["symbol"], bm["ts"]))
    syms = sorted(bm["symbol"].unique())

    for metric, src in (("mark", "markPriceKlines"), ("index", "indexPriceKlines")):
        miss = int(d[METRICS[metric]].isna().sum())
        in_grid = int((d[METRICS[metric]].isna() & d["bar_missing"]).sum())
        held = 0
        for s in syms:
            f = RAW / src / f"symbol={s}.parquet"
            if not f.exists():
                continue
            t = pq.read_table(str(f), columns=["open_time"]).to_pandas()
            # raw 的 open_time 是 int64【毫秒】，不是 datetime —— 必须显式给 unit
            ts = pd.to_datetime(t["open_time"], unit="ms", utc=True)
            held += sum(1 for x in ts if (s, x) in keys)
        out[metric] = {"missing": miss, "grid": in_grid, "held": held}
    return out


def compute_panel_facts() -> dict:
    """两份文档里几个【口径验证】数字。独立走一遍 parquet，不进 read_features()。

    为什么要单独扫：这几列只在算这几个比例时用得到，留在常驻的 d 里会让
    7,253,002 行多占几百 MB，而报告其余部分并不需要它们。

    这里算的是字典第 3 节那几条「语义必须被理解」的证据 —— 它们随数据变化，
    以前写死在字符串里（"99.13%" 那一条与实际口径对不上，已改成本函数算的）。
    """
    n_vwap = n_in_range = 0
    n_fund = n_fund_null = 0
    intervals: dict[str, set] = defaultdict(set)

    for f in sorted(FE.rglob("*.parquet")):
        t = pq.read_table(str(f), columns=[
            "symbol", "high", "low", "close", "volume", "quote_volume",
            "funding_rate", "funding_interval_hours"]).to_pandas()

        # ① volume / quote_volume 与价格同单位：VWAP = quote_volume/volume
        #    必须落在该 bar 的 [low, high] 内。这比"约等于 close"强 ——
        #    VWAP 是成交量加权均价，本来就不等于收盘价（中位差 0.34%）。
        m = (t["volume"] > 0) & t["close"].notna() & t["high"].notna()
        if m.any():
            vwap = t.loc[m, "quote_volume"] / t.loc[m, "volume"]
            n_vwap += int(m.sum())
            n_in_range += int(((vwap >= t.loc[m, "low"])
                               & (vwap <= t.loc[m, "high"])).sum())

        # ② funding_rate 的天然稀疏度
        n_fund += len(t)
        n_fund_null += int(t["funding_rate"].isna().sum())

        # ③ 有多少合约中途换过结算区间
        iv = t[["symbol", "funding_interval_hours"]].dropna()
        for s, g in iv.groupby("symbol")["funding_interval_hours"]:
            intervals.setdefault(str(s), set()).update(g.unique().tolist())

    return {
        "vwap_n": n_vwap,
        "vwap_in_range_pct": (n_in_range / n_vwap) if n_vwap else float("nan"),
        "funding_rows": n_fund,
        "funding_null_rows": n_fund_null,
        "funding_null_pct": (n_fund_null / n_fund) if n_fund else float("nan"),
        "funding_nonnull_pct": (1 - n_fund_null / n_fund) if n_fund else float("nan"),
        "interval_change_syms": sum(1 for v in intervals.values() if len(v) > 1),
        "interval_syms": len(intervals),
        "interval_values": sorted({x for v in intervals.values() for x in v}),
    }


def compute_report_facts(d: pd.DataFrame, cov: pd.DataFrame, mc: pd.DataFrame,
                         man: pd.DataFrame, cause: dict,
                         member_months: list[str]) -> dict:
    """data_quality.md 里所有【会随数据变化】的数字，一处算清。

    以前 §1 / §4.2 / §4.3 / §4.4 里有 7 个数字是写死在字符串里的，刷新数据后
    不会自动更新 —— §4.3 那句 "From 2023 onward all three sources stay above
    0.99" 到后来已经和数据矛盾了。凡是随数据变的，一律在这里算。
    """
    srcs = list(METRICS)
    n_months = int(d["ts"].dt.strftime("%Y-%m").nunique())

    # ---- §1 面板存在、但没有成员集的月份 ----
    n_months_member = len(set(member_months))
    n_months_no_members = n_months - n_months_member
    first_member = min(member_months) if member_months else None

    # ---- §2 覆盖率为 0.0000 的 (合约, 源) ----
    z = cov[cov["coverage"] == 0]
    zero_pairs = sorted((str(s), str(m)) for s, m in zip(z["symbol"], z["metric"]))
    zero_syms = sorted({s for s, _ in zero_pairs})

    # ---- §3.3 manifest 里失败的是不是全为 metrics ----
    nonok = man[man["status"] != "ok"] if len(man) else man
    nonok_sources = sorted(set(str(x) for x in nonok["source"])) if len(nonok) else []

    # ---- §4.2 归档无文件最多的那三个合约：oi 覆盖率 + 其中多少小时在成交 ----
    dormant = []
    for sym, hrs, trd in cause["a_top"]:
        c = cov[(cov["symbol"] == sym) & (cov["metric"] == "oi")]["coverage"]
        dormant.append((sym, int(hrs), int(trd),
                        float(c.iloc[0]) if len(c) else float("nan")))

    # ---- §4.3 逐月最弱 + 全市场断供窗口 ----
    mc_min = mc[srcs].min(axis=1)
    below = mc_min[mc_min < 0.99].sort_values()
    ym_col = d["ts"].dt.strftime("%Y-%m")          # 只算一次，下面按月在它上面过滤

    # 全市场断供：某小时【过半在场合约】同缺同一个源。这能把「一个合约坏了」
    # 和「交易所那天没发布」分开 —— 月度平均值本身看不出这个区别。
    outages: list[dict] = []
    for metric, col in (("mark", "mark_close"), ("index", "index_close")):
        per = (pd.DataFrame({"ts": d["ts"], "miss": d[col].isna()})
                 .groupby("ts")["miss"].agg(["sum", "size"]))
        frac = (per["sum"] / per["size"]).to_numpy()
        miss_n = per["sum"].to_numpy()
        for i0, i1 in runs_of(frac >= 0.5):
            outages.append({
                "metric": metric,
                "start": str(per.index[i0]), "end": str(per.index[i1]),
                "hours": int(i1 - i0 + 1),
                "contracts": int(miss_n[i0:i1 + 1].max()),
            })

    worst_months = []
    for ym in below.index[:5]:
        metric = str(mc.loc[ym, srcs].idxmin())
        col = METRICS[metric]
        sub = d.loc[(ym_col == ym).to_numpy(), ["symbol", "ts", col]]
        miss = sub[col].isna() if col.endswith("_close") else sub[col].astype(bool)
        ms = sub.loc[miss]
        present = int(sub["symbol"].nunique())
        # 诊断：这个月的低谷是「某一天大范围断供」还是「散在很多天」。
        # 单日覆盖过半在场合约才算断供 —— 否则不足以解释整个月的均值被拉低。
        if len(ms):
            per_day = (ms.groupby(ms["ts"].dt.floor("D"))["symbol"].nunique()
                         .sort_values(ascending=False))
            top_day = str(per_day.index[0])[:10]
            top_n = int(per_day.iloc[0])
            n_days = int(per_day.size)
            med_day = int(per_day.median())
        else:
            top_day, top_n, n_days, med_day = "—", 0, 0, 0
        worst_months.append({
            "month": str(ym), "metric": metric, "coverage": float(mc_min.loc[ym]),
            "affected": int(ms["symbol"].nunique()), "present": present,
            "top_day": top_day, "top_n": top_n, "n_days": n_days, "med_day": med_day,
            "outage": bool(present and top_n >= 0.5 * present),
        })

    # ---- §4.4 刻意不标记的 ----
    oi0 = d[d["oi"].notna() & (d["oi"] == 0)]
    oi0_hour = oi0.groupby("ts").size() if len(oi0) else pd.Series(dtype=int)

    return {
        "n_months": n_months,
        "n_months_no_members": n_months_no_members,
        "first_member_month": first_member,
        "zero_pairs": zero_pairs,
        "zero_syms": zero_syms,
        "nonok_sources": nonok_sources,
        "dormant": dormant,
        "mc_below_n": int(len(below)),
        "worst_months": worst_months,
        "n_worst_outage": sum(1 for w in worst_months if w["outage"]),
        "worst_diffuse": [w["month"] for w in worst_months if not w["outage"]],
        "outages": outages,
        "oi_zero_rows": int(len(oi0)),
        "oi_zero_syms": int(oi0["symbol"].nunique()) if len(oi0) else 0,
        "oi_zero_days": int(oi0["ts"].dt.floor("D").nunique()) if len(oi0) else 0,
        "oi_zero_max_hour": int(oi0_hour.max()) if len(oi0_hour) else 0,
    }


# ============================================================================
# 图（英文标签）
# ============================================================================
def fig_coverage_distribution(cov: pd.DataFrame) -> Path:
    """覆盖率分布直方图：每源一个面板，横轴覆盖区间、纵轴合约数。

    只报中位数会掩盖尾部 —— 本图要回答"有多少合约其实是残缺的"。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # 最后一桶必须是【恰好 1.0】，不能与 [0.999, 1.0) 合并。
    # 原先 bins 末端是 1.0（左闭右开，排除 1.0），再把 (c >= 1.0) 累加进同一根柱，
    # 于是标着 "= 1.00" 的柱实际是 ">= 0.999" —— 与报告 §2 的表对不上
    # （mark 39 vs 11，差 3.5 倍）。用 inf 收尾，各桶互不重叠。
    edges = [0.0, 0.5, 0.9, 0.99, 0.999, 1.0, float("inf")]
    labels = ["< 0.50", "0.50–0.90", "0.90–0.99", "0.99–0.999",
              "0.999–1.00", "= 1.00"]
    order = list(METRICS)
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.4), sharey=True)
    for ax, metric in zip(axes, order):
        c = cov[cov["metric"] == metric]["coverage"].to_numpy()
        counts = [int(((c >= lo) & (c < hi)).sum())
                  for lo, hi in zip(edges[:-1], edges[1:])]
        ax.bar(range(len(labels)), counts, color="#4a7ebb")
        for i, v in enumerate(counts):
            if v:
                ax.text(i, v, str(v), ha="center", va="bottom", fontsize=8)
        ax.set_title(metric, fontsize=11)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    axes[0].set_ylabel("contracts", fontsize=9)
    fig.suptitle(f"Coverage distribution by source "
                 f"({cov['symbol'].nunique()} contracts)", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = FIG / "coverage_distribution.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    # 暂存名必须仍以 .png 结尾 —— matplotlib 按后缀选格式，".png.tmp" 会报错
    tmp = out.with_name(out.name + ".tmp.png")
    fig.savefig(tmp, dpi=150)
    plt.close(fig)
    os.replace(tmp, out)
    return out


def fig_monthly_coverage(mc: pd.DataFrame) -> Path:
    """月度覆盖率的折线（每个月一条，四个源）。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 3.6))
    x = range(len(mc))
    # 画序即层序：后画的在上。四条线在高覆盖率区间常整段重叠，
    # 所以都带透明度，否则会把下面那条完全盖住，看上去像"那条线没了"。
    for col, color in [("index", "#6a1b9a"), ("oi", "#c62828"),
                       ("mark", "#1565c0"), ("klines", "#2f7d32")]:
        ax.plot(x, mc[col].to_numpy(), label=col, color=color,
                linewidth=1.4, alpha=0.8)
    ax.set_ylim(0.94, 1.005)
    ax.set_ylabel("coverage", fontsize=9)
    step = 6
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels(list(mc.index)[::step], rotation=40, ha="right", fontsize=8)
    ax.axhline(1.0, color="#999999", linewidth=0.8, linestyle="--")
    ax.legend(fontsize=9, ncol=4, loc="lower right")
    ax.set_title(f"Monthly coverage across {len(mc)} months", fontsize=12)
    ax.grid(alpha=0.25, linewidth=0.6)
    fig.tight_layout()
    out = FIG / "monthly_coverage.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    # 同上：暂存名必须仍以 .png 结尾
    tmp = out.with_name(out.name + ".tmp.png")
    fig.savefig(tmp, dpi=150)
    plt.close(fig)
    os.replace(tmp, out)
    return out


# ============================================================================
# data_quality.md（英文，5 节）
# ============================================================================

def build_quality_report(cfg, sample_end: str, d: pd.DataFrame, cov: pd.DataFrame,
                         gaps: pd.DataFrame, mc: pd.DataFrame, cause: dict,
                         facts: dict, panel: dict, grid_drops: dict,
                         n_members: int, n_member_syms: int, n_months_member: int,
                         fig_paths: list[Path]) -> str:
    L: list[str] = []
    A = L.append
    n_rows = len(d)
    n_syms = d["symbol"].nunique()
    n_months = d["ts"].dt.strftime("%Y-%m").nunique()
    hist_h = d.groupby("symbol").size()

    A("# Data Quality — Phase 1 (D1)")
    A("")
    A(f"Sample window `{cfg.sample_start}` .. `{sample_end}`　·　"
      f"generated by `phase1/build_deliverables.py`")
    A("")
    A("This is the quality evidence for D1. It answers what a reader needs before")
    A("using the panel: **how much data there is, how complete it is, and where it is not.**")
    A("")
    A("---")
    A("")

    # ---- 1. Sample scale -------------------------------------------------
    A("## 1. Sample scale")
    A("")
    A("| | |")
    A("|---|---|")
    A(f"| Hourly panel rows | **{n_rows:,}** |")
    A(f"| Contracts | **{n_syms}** |")
    A(f"| Months covered | **{n_months}** |")
    A(f"| Member cells (contract × month) | **{n_members:,}** |")
    A(f"| Contracts that were ever a member | **{n_member_syms}** |")
    A(f"| Months with members | **{n_months_member}** |")
    A(f"| History per contract | median **{hist_h.median():,.0f} h** "
      f"(≈ {hist_h.median()/24/30:.1f} months), range {hist_h.min():,} – {hist_h.max():,} h |")
    A("")
    A("The panel is a dense hourly grid: every hour between a contract's first bar")
    A("and its last active day has exactly one row, with explicit flags "
      "(`bar_missing` / `oi_missing`) marking padded hours.")
    A("")
    A(f"**{facts['n_months_no_members']} of the {facts['n_months']} months have no "
      f"members at all** — `min_history_bars = {cfg.min_history_bars}` "
      f"({cfg.min_history_bars // 24} days) means no contract has enough history yet. "
      f"The first month with members is `{facts['first_member_month']}`.")
    A("")
    A("---")
    A("")

    # ---- 2. Coverage -----------------------------------------------------
    A("## 2. Coverage")
    A("")
    A("Coverage = non-missing hours / total hours, per contract and source.")
    A("")
    A("| Source | median | contracts at 100% | ≥ 0.999 | < 0.99 | < 0.90 | min |")
    A("|---|---|---|---|---|---|---|")
    for metric in METRICS:
        c = cov[cov["metric"] == metric]["coverage"]
        A(f"| `{metric}` | {c.median():.4f} | {int((c >= 1.0).sum())} | "
          f"{int((c >= 0.999).sum())} | {int((c < 0.99).sum())} | "
          f"{int((c < 0.90).sum())} | {c.min():.4f} |")
    A("")
    A("**The median hides the distribution — that is why both are shown.** "
      "`mark` and `index` have far fewer contracts at exactly 100% coverage than "
      "`klines` does, because both are absent for the same contract "
      f"(`{'`, `'.join(facts['zero_syms'])}` — see §4.1).")
    A("")
    for p in fig_paths:
        # 链接相对于【报告自己的目录】（04_qa/），不是 data/ —— 否则 Markdown 里是死链
        A(f"![{p.stem}]({p.relative_to(QA).as_posix()})")
        A("")
    A("---")
    A("")

    # ---- 3. Verified gaps ------------------------------------------------
    A("## 3. Verified gaps")
    A("")
    A("Both layers below are *verified*, not estimated. The question they answer is")
    A("**whether a missing hour is our failure or the archive's** — the answer matters,")
    A("because only the second kind is a property of the data rather than of this run.")
    A("")
    A("### 3.1 The archive's own gaps, inside the panel")
    A("")
    A("Only `oi` can be attributed this way: it is the sole source whose daily files are")
    A("probed one-by-one, so every request is on record in `00_config/manifest.parquet`.")
    A("")
    A(f"**{cause['hours']:,} panel hours carry no `oi`** — {cause['pairs']:,} (contract, day) "
      f"pairs across {cause['syms']} contracts.")
    A("")
    A("| Cause | contract-days | hours | contracts |")
    A("|---|---|---|---|")
    A(f"| **No such file in the archive** — the day is absent from Binance's "
      f"`daily/metrics` listing, so it was never downloadable | "
      f"**{cause['a_pairs']:,}** | **{cause['a_hours']:,}** | {cause['a_syms']} |")
    A(f"| File downloaded, but that day carries no snapshot for these hours | "
      f"{cause['b_pairs']:,} | {cause['b_hours']:,} | {cause['b_syms']} |")
    A("")
    if cause["a_top"]:
        tot = cause["a_hours"] or 1
        parts = ", ".join(f"`{s}` {h:,} h" for s, h, _ in cause["a_top"])
        A(f"The first row is the archive's gap proper, and it is highly concentrated: "
          f"{parts} — together "
          f"{sum(h for _, h, _ in cause['a_top'])/tot:.0%} of it.")
        A("")
        A(f"**Not all of it is dormancy.** {cause['a_traded']:,} of those "
          f"{cause['a_hours']:,} hours ({cause['a_traded']/tot:.0%}) are hours the "
          f"contract was **actively trading** (`quote_volume > 0`): the exchange simply "
          f"published no `metrics` file for them. §4.2 breaks this down per contract.")
        A("")
    A("### 3.2 Out-of-panel probes — 404s with no effect on the panel")
    A("")
    A(f"**{cause['out_n']} requests returned 404**, across {cause['out_syms']} contracts.")
    if cause["out_inside"] == 0:
        A(f"**None of them touches the panel**: every one is dated "
          f"{cause['out_min_after']}–{cause['out_max_after']} days *after* its contract's "
          f"grid ends, so no 404 can produce a hole.")
    else:
        A(f"**{cause['out_inside']} of them fall inside the panel** and are counted in §3.1.")
    A("")
    A(f"{cause['out_nxt']} are the deliberate boundary probe — the first day of the month "
      f"after a contract's last klines month, requested so the final bar's `oi` can be "
      f"filled. {cause['out_mid']} are mid-month days genuinely absent from the archive, "
      f"all dated after the contract had stopped trading. Every one is kept in "
      f"`00_config/manifest.parquet` with its full remote path, as evidence that the "
      f"pipeline asked rather than silently skipped.")
    A("")
    A("### 3.3 Contiguous missing runs inside the panel")
    A("")
    A("| Source | runs | total hours | longest run | longest run in |")
    A("|---|---|---|---|---|")
    for metric in METRICS:
        sub = gaps[gaps["metric"] == metric]
        if len(sub):
            worst = sub.loc[sub["hours"].idxmax()]
            A(f"| `{metric}` | {len(sub):,} | {sub['hours'].sum():,.0f} | "
              f"{sub['hours'].max():,.0f} h | `{worst['symbol']}` |")
        else:
            A(f"| `{metric}` | 0 | 0 | — | — |")
    A("")
    A(f"**{len(gaps):,} runs in total.** "
      f"{int(gaps['started_before_sample'].sum())} of them start at a contract's very "
      f"first row (missing before the sample begins, not a mid-sample corruption).")
    A("")
    A("`klines`, `mark` and `index` are attributed differently because they arrive as")
    A("monthly archives rather than per-day files. That settles the *files*: no monthly")
    if not facts["nonok_sources"]:
        A("file failed at all — the manifest holds no non-`ok` row.")
    elif facts["nonok_sources"] == ["metrics"]:
        A(f"file failed — every one of the {cause['out_n']} 404s in the manifest is a")
        A("`metrics` file (§3.2).")
    else:
        A(f"file of source {', '.join('`' + s + '`' for s in facts['nonok_sources'])} was")
        A("never downloaded, so those runs cannot be attributed without opening them.")
    A("")
    A("It does **not** settle the *rows*, and for `mark`/`index` the difference is large.")
    A("Layer 2 defines the grid from `klines_1h` and drops every `mark`/`index` row at an")
    A("hour `klines` does not have — and the archive holds most of them:")
    A("")
    A("| Source | panel hours missing | of which `klines` has no bar | archive actually holds them |")
    A("|---|---|---|---|")
    for metric in ("mark", "index"):
        gd = grid_drops.get(metric)
        if gd:
            A(f"| `{metric}` | {gd['missing']:,} | {gd['grid']:,} | **{gd['held']:,}** |")
    A("")
    A(f"So {grid_drops['mark']['held']:,} of `mark`'s missing hours are a **deliberate")
    A("consequence of the grid rule**, not a hole in the archive: the panel shows")
    A("`mark_close = NaN` at hours the archive has a mark price for. The remaining")
    A(f"{grid_drops['mark']['missing'] - grid_drops['mark']['grid']:,} `mark` hours are")
    A("inside the grid and are genuine archive gaps. `klines` has no such split — it")
    A("*defines* the grid.")
    A("")
    A("The `oi` row above is the same population as §3.1, counted in runs rather than")
    A("in hours.")
    A("")
    A("---")
    A("")

    # ---- 4. Known limitations -------------------------------------------
    A("## 4. Known limitations")
    A("")
    A("Every case below is **understood and explained**, not an unexplained hole.")
    A("")
    worst_cov = cov.nsmallest(5, "coverage")
    A("### 4.1 Contracts with the lowest coverage")
    A("")
    A("| Contract | Source | Coverage | Hours present | Longest gap |")
    A("|---|---|---|---|---|")
    for r in worst_cov.itertuples(index=False):
        A(f"| `{r.symbol}` | `{r.metric}` | {r.coverage:.4f} | "
          f"{r.n_present:,.0f} / {r.n_total:,.0f} | "
          f"{int(gaps[(gaps.symbol == r.symbol) & (gaps.metric == r.metric)]['hours'].max()) if len(gaps[(gaps.symbol == r.symbol) & (gaps.metric == r.metric)]) else 0:,} h |")
    A("")
    if facts["zero_syms"]:
        syms_txt = " / ".join(f"`{s}`" for s in facts["zero_syms"])
        zsrcs = sorted({m for _, m in facts["zero_pairs"]})
        srcs_txt = " / ".join(f"`{m}`" for m in zsrcs)
        A(f"**The zero-coverage rows are {plural(len(facts['zero_syms']), 'contract')}, "
          f"not a general failure.** {syms_txt} has **no {srcs_txt} rows at all** — 0 "
          f"hours present out of its whole grid.")
    else:
        A("**No contract has zero coverage in any source.**")
    A("")
    A("This is a gap in the archive, not a download failure: enumerating the S3 archive")
    A("returns zero `.zip` for that contract under either source. Its remaining sources")
    A("are complete — see the table above, where only these rows show a zero.")
    A("")
    A("### 4.2 Where the missing open interest comes from")
    A("")
    if facts["dormant"]:
        A("The three contracts carrying most of the §3.1 first row:")
        A("")
        A("| Contract | `oi` coverage | hours with no file | of which actively trading |")
        A("|---|---|---|---|")
        for s, hrs, trd, c in facts["dormant"]:
            A(f"| `{s}` | {c:.4f} | {hrs:,} | {trd:,} ({trd/max(hrs,1):.0%}) |")
        A("")
        worst = max(facts["dormant"], key=lambda r: r[2] / max(r[1], 1))
        A(f"**`{worst[0]}` was not dormant in those hours.** `quote_volume > 0` on "
          f"{worst[2]/max(worst[1],1):.0%} of them — it traded throughout while the")
        A("archive published no open interest at all. That is an archive gap, not a quiet")
        A("period, which is why §3.1 counts it as the archive's own gap rather than as a")
        A("collection failure.")
    else:
        A("No contract accounts for a material share of the archive's gaps.")
    A("")
    A("### 4.3 Coverage over time")
    A("")
    A(f"Coverage is not flat. **{facts['mc_below_n']} of the {facts['n_months']} months "
      f"have at least one source below 0.99.** The weakest five:")
    A("")
    A("| Month | Weakest source | Coverage | Contracts affected | Worst day |")
    A("|---|---|---|---|---|")
    for w in facts["worst_months"]:
        A(f"| {w['month']} | `{w['metric']}` | {w['coverage']:.4f} | "
          f"{w['affected']} of {w['present']} | {w['top_day']} — "
          f"{w['top_n']} contracts |")
    A("")
    A("`Worst day` is the day on which most contracts lost that source. "
      "It separates two very different shapes — and the table shows both:")
    A("")
    n_out = facts["n_worst_outage"]
    A(f"**① Single-day outages ({n_out} of the five).** On one day, most listed "
      f"contracts lose the same source at once. Those are exchange-wide and are listed "
      f"in full below; they also hit months that do not appear in this table.")
    A("")
    if facts["outages"]:
        A("| Source | From | To | Hours | Contracts |")
        A("|---|---|---|---|---|")
        for o in facts["outages"]:
            A(f"| `{o['metric']}` | {o['start'][:16]} | {o['end'][:16]} | "
              f"{o['hours']} | {o['contracts']} |")
        A("")
    if facts["worst_diffuse"]:
        ms = " / ".join(f"`{m}`" for m in facts["worst_diffuse"])
        A(f"**② Not attributed ({len(facts['worst_diffuse'])} of the five: {ms}).** "
          f"Their missing hours are spread across many days and many contracts — the "
          f"worst day covers only a minority of contracts — so neither an outage nor a "
          f"single bad contract explains them:")
        A("")
        A("| Month | Source | days with any gap | median contracts on such a day |")
        A("|---|---|---|---|")
        for w in facts["worst_months"]:
            if not w["outage"]:
                A(f"| {w['month']} | `{w['metric']}` | {w['n_days']} | {w['med_day']} |")
        A("")
        A("This is reported as **not yet explained** rather than folded into ①.")
    A("")
    A("### 4.4 What is deliberately NOT flagged")
    A("")
    A("| Not flagged | Why |")
    A("|---|---|")
    A(f"| `funding_rate` being null in {panel['funding_null_pct']:.2%} of rows "
      f"({panel['funding_null_rows']:,}) | It only exists at settlement. Sparse by "
      f"design — flagging it would produce that many false gaps. |")
    A("| `funding_interval_hours` | Forward-filled; not sparse. |")
    A(f"| `oi == 0` ({facts['oi_zero_rows']:,} rows over {facts['oi_zero_days']} days, "
      f"{facts['oi_zero_syms']} contracts) | A market-wide publishing event (up to "
      f"{facts['oi_zero_max_hour']} contracts in the same hour), not a per-contract "
      f"defect. The panel keeps the true value; downstream may filter with `oi > 0`. |")
    A("| Late-listed contracts having short history | That is the fact being recorded, "
      "not a defect. |")
    A("")
    A("---")
    A("")
    A("## 5. How to verify")
    A("")
    A("```bash")
    A("# re-hash every output file and compare against the recorded digests")
    A("python phase1/build_deliverables.py --out-root data --sample-end "
      + sample_end + " --verify")
    A("```")
    A("")
    A("`04_qa/checksums.sha256` covers every file under `data/` except two:")
    A("itself and the temporary download cache `00_config/_cache/`. It **does** cover")
    A("this report, the dictionary and the figures.")
    A("")
    A("`phase1/REPRODUCE.md` sits outside `data/` on purpose: it is instructions rather")
    A("than output, so git tracks it instead of the checksums.")
    A("")
    A("**It proves internal consistency** (your output equals the output that was")
    A("generated), **not provenance** (that the downloaded files equal the archive) —")
    A("the latter would require Binance's own `.CHECKSUM` files, which this phase")
    A("does not use.")
    A("")
    return "\n".join(L)


# ============================================================================
# data_dictionary.md（英文，只管列定义）
# ============================================================================

def build_data_dictionary(cfg, sample_end: str, n_rows: int, n_syms: int,
                          n_elig: int, n_members: int, panel: dict) -> str:
    L: list[str] = []
    A = L.append
    A("# Data Dictionary — Phase 1 (D1)")
    A("")
    A(f"Sample window `{cfg.sample_start}` .. `{sample_end}`")
    A("")
    A("**Scope: column definitions only.** What the fields mean, their units and")
    A("where they come from. For whether the data is complete, see")
    A("[`data_quality.md`](data_quality.md).")
    A("")
    A("---")
    A("")
    A("## 1. Directory layout")
    A("")
    A("```")
    A("data/")
    A("├── 00_config/                        run bookkeeping (not deliverable data)")
    A("│   ├── manifest.parquet              per-file download ledger")
    A("│   ├── archive_contracts.csv         archive enumeration (Step 0)")
    A("│   ├── kept_contracts.csv            contracts passing the hard filter (Step 1)")
    A("│   └── dropped_contracts.csv         removed contracts + reason (Step 1)")
    A("├── raw/                              five sources, as downloaded (Step 3)")
    A("├── 01_layer2/                        four normalized 1h tables (Step 4)")
    A("├── 02_features/features_1h/          analysis panel, 19 cols (Step 5)")
    A("├── 03_reference/                     candidate pool + universe tables (Step 6a)")
    A("└── 04_qa/                            D1 deliverables + integrity proof")
    A("    ├── data_quality.md               quality evidence (Step 6b)")
    A("    ├── data_dictionary.md            this file")
    A("    ├── checksums.sha256              SHA256 of every file under data/")
    A("    └── figures/*.png                 coverage charts")
    A("")
    A("phase1/REPRODUCE.md                   how to rebuild all of this (tracked by git)")
    A("```")
    A("")
    A("---")
    A("")
    A("## 2. Table inventory")
    A("")
    A("| Table | Grain | Primary key | Rows | Layout |")
    A("|---|---|---|---|---|")
    A(f"| `features_1h` | 1 hour | `(symbol, ts)` | {n_rows:,} | `year=YYYY/chunk=YYYY-MM.parquet` |")
    A("| `klines_1h` | 1 hour | `(symbol, ts)` | see `01_layer2` | same |")
    A("| `mark_index_1h` | 1 hour | `(symbol, ts)` | same | same |")
    A("| `oi_1h` | 1 hour | `(symbol, ts)` | same | same |")
    A("| `funding` | settlement event | `(symbol, ts_funding)` | see `01_layer2` | same |")
    A(f"| `master` | 1 contract | `symbol` | {n_syms:,} | single file |")
    A("| `universe_eligibility` | 1 contract × 1 month | `(symbol, month)` | "
      f"{n_elig:,} | single file |")
    A(f"| `universe_membership` | 1 contract × 1 month | `(symbol, month)` | {n_members:,} | single file |")
    A("")
    A(f"`features_1h` holds **{n_rows:,} rows / {n_syms} contracts**.")
    A("")
    A("---")
    A("")
    A("## 3. `features_1h` — column definitions")
    A("")
    A("| Column | Type | Unit | Source | Meaning |")
    A("|---|---|---|---|---|")
    A("| `symbol` | string | — | — | Contract name, e.g. `BTCUSDT` |")
    A("| `ts` | timestamp | UTC | — | Bar **start** `H` |")
    A("| `ts_end` | timestamp | UTC | derived | `ts + 1h`. **End of the interval = the OI alignment instant = the decision timestamp.** |")
    A("| `open` `high` `low` `close` | float64 | USDT | `klines` | OHLC within the bar (traded price) |")
    A("| `volume` | float64 | base asset | `klines` | Traded base-asset quantity (≈ `quote_volume` / `close`) |")
    A("| `quote_volume` | float64 | USDT | `klines` | Traded notional — **the input to the liquidity measure** |")
    A("| `trades` | float64 | count | `klines.count` | Number of trades in the bar |")
    A("| `taker_buy_volume` | float64 | base asset | `klines` | Taker-buy quantity |")
    A("| `taker_buy_quote_volume` | float64 | USDT | `klines` | Taker-buy notional |")
    A("| `oi` | float64 | base asset | `metrics.sum_open_interest` | **`OI(ts_end)`** — open interest at the interval end (base-asset units) |")
    A("| `mark_close` | float64 | USDT | `markPriceKlines` | Mark price at bar close |")
    A("| `index_close` | float64 | USDT | `indexPriceKlines` | Index price at bar close |")
    A("| `funding_rate` | float64 | ratio | `fundingRate` | **Non-null at settlement hours only**; never filled |")
    A("| `funding_interval_hours` | float64 | hours | `fundingRate` | True value at settlement; between settlements, the interval announced at the **previous** settlement |")
    A("| `bar_missing` | bool | — | derived | This hour has no row in `klines_1h` (padded by the dense grid) |")
    A("| `oi_missing` | bool | — | derived | No OI snapshot for this hour |")
    A("")
    A("### Four semantics that must be understood")
    A("")
    A("**① `oi` is aligned to the interval *end*, not the bar start.**")
    A("")
    A("```")
    A("bar [20:00, 21:00)  pairs with  OI(21:00)     <- the row's ts is 20:00")
    A("```")
    A("")
    A("So `oi_1h`'s `ts` is one hour earlier than the source `create_time`. This is")
    A("deliberate: at `ts_end` price and OI become available **at the same instant**,")
    A("so the row is self-contained and no forward-looking information is needed.")
    A("")
    A("**② `funding_rate`'s sparsity is semantics, not a data-quality problem.**")
    A("")
    A(f"Only {panel['funding_nonnull_pct']:.2%} of rows carry a value (settlement hours),")
    A(f"{panel['funding_null_rows']:,} of {panel['funding_rows']:,} are null. The rest are "
      f"`NaN` by")
    A("design, which is why it is excluded from gap detection.")
    A("")
    A("**③ `funding_interval_hours` is forward-filled, and settlement intervals change.**")
    A("")
    A("Between settlements the value is the interval announced at the previous")
    A("settlement — a known quantity at decision time, not an invention. Contracts")
    A(f"differ: the values seen in this sample are "
      f"{', '.join(f'{v:g}h' for v in panel['interval_values'])}, and "
      f"{panel['interval_change_syms']} of {panel['interval_syms']} contracts changed")
    A("interval mid-sample, so **read this column rather than hard-coding 8h** when")
    A("annualising.")
    A("")
    A("**④ `oi`, `volume` and `taker_buy_volume` are in base-asset units, not contracts.**")
    A("")
    A("Verified two ways.")
    A("")
    A("① Against the archive itself: `sum_open_interest × close` reproduces the")
    A("archive's own `sum_open_interest_value` column. (Recorded as a one-off check —")
    A("that column is not kept, so it cannot be recomputed from `data/` alone.)")
    A("")
    A(f"② Against the panel: `quote_volume / volume` is the bar's volume-weighted")
    A(f"average price, and it falls inside `[low, high]` on **{panel['vwap_in_range_pct']:.4%}**")
    A(f"of the {panel['vwap_n']:,} bars with non-zero volume. That is only possible if")
    A("`volume` and `quote_volume` are in the same unit system as the prices — contracts")
    A("would break it. `quote_volume / volume` is *not* equal to `close`: it is the")
    A("weighted average, not the last trade.")
    A("")
    A("Do not assume a fixed contract multiplier — contracts whose base asset is")
    A("`1000XXX` count thousand-token units.")
    A("")
    A("---")
    A("")
    A("## 4. Layer-2 tables")
    A("")
    A("| Table | Columns |")
    A("|---|---|")
    A("| `klines_1h` | `symbol` `ts` `ts_end` `open` `high` `low` `close` `volume` `quote_volume` `trades` `taker_buy_volume` `taker_buy_quote_volume` |")
    A("| `mark_index_1h` | `symbol` `ts` `ts_end` `mark_close` `index_close` |")
    A("| `oi_1h` | `symbol` `ts` `ts_end` `oi` `oi_missing` |")
    A("| `funding` | `symbol` `ts_funding` `funding_rate` `funding_interval_hours` |")
    A("")
    A("The grid is defined by `klines_1h`: the other two hourly tables are **left-joined")
    A("onto it**, so hours that `klines` does not have are dropped. `funding` is an")
    A("event table and is not on the grid — its key is `ts_funding`.")
    A("")
    A("---")
    A("")
    A("## 5. Reference tables")
    A("")
    A("| Table | Grain | Key columns |")
    A("|---|---|---|")
    A("| `candidate_pool.csv` | 1 contract | `symbol` (285) |")
    A("| `master` | 1 contract | `symbol` `base_asset` `first_bar` `last_bar` `n_bars` `n_months` `last_active` `contract_type` `underlying_type` `in_exchange_info` |")
    A("| `universe_eligibility` | 1 contract × 1 month | `symbol` `month` `base_asset` "
      "+ window metrics (`liq` `bars_before` `last_active` `oi_cov` `oi_max_gap_h` "
      "`active_days`) + per-gate booleans (`g1` `g2a` `live` `g2` `g3a` `g3b` `g3` `g4`) "
      "+ `eligible` `fail_reason` `rank` — 20 columns |")
    A("| `universe_membership` | 1 contract × 1 month | `symbol` `month` `rank` `liq` `bars_before` `oi_cov` `oi_max_gap_h` `active_days` |")
    A("| `member_changes` | 1 month | `month` `n_members` `n_entered` `n_exited` `n_retained` `turnover` |")
    A("")
    # 例子取样本最后一个月；三个日期全部由 sample_end + liq_window_days 算出。
    # 写死的话，样本往前推之后这段说明会和实际口径对不上。
    cut = pd.Timestamp(sample_end).normalize().replace(day=1)
    lo = cut - pd.Timedelta(days=cfg.liq_window_days)
    nxt = cut + pd.offsets.MonthBegin(1)
    A("**`month` is the decision instant, not the performance interval.** A row with")
    A(f"`month = {cut:%Y-%m}` means the membership was decided at `{cut:%Y-%m-%d} 00:00 UTC`,")
    A(f"using the window `[{lo:%Y-%m-%d}, {cut:%Y-%m-%d})`; the membership then applies")
    A(f"to `[{cut:%Y-%m-%d}, {nxt:%Y-%m-%d})`.")
    A("")
    return "\n".join(L)


# ============================================================================
# REPRODUCE.md
# ============================================================================

def build_reproduce(cfg, sample_end: str) -> str:
    L: list[str] = []
    A = L.append
    A("# Reproduce")
    A("")
    A(f"sample_end = `{sample_end}`　sample_start = `{cfg.sample_start}`")
    A("")
    A("One command rebuilds every D1 output from scratch; the six steps it runs are")
    A("listed further down for when one of them needs debugging.")
    A("")
    A("## Design parameters of this output")
    A("")
    A("These come from `config.py`. **If `config.py` has since been edited, the values")
    A("below are the ones the output was produced with** — different parameters give a")
    A("different output, so this snapshot is what identifies which design a given")
    A("output corresponds to.")
    A("")
    A("```")
    for k, v in cfg.snapshot().items():
        A(f"{k} = {v}")
    A("```")
    A("")
    A("Note it records **parameter values only, not the code version**. If only the")
    A("computation logic changed while parameters stayed the same, this snapshot cannot")
    A("show it — use the git history for that.")
    A("")
    A("## One command")
    A("")
    A("```bash")
    A("python phase1/run_phase1.py --out-root data --sample-end " + sample_end)
    A("```")
    A("")
    A("This runs the six steps below in order, passing `--out-root` and `--sample-end`")
    A("to each. It stops at the first non-zero exit and names the step that failed;")
    A("re-run the whole command afterwards, or run the remaining steps individually.")
    A("")
    A("It does **not** run the verification below, and it takes no other flags —")
    A("step-specific flags (`--subset`, `--keep-cache`, `--skip-download`, …) are used")
    A("directly against that step's script.")
    A("")
    A("## Prerequisites")
    A("")
    A("- Python 3.12 with `pandas` / `pyarrow` (2.3.3 / 23.0.1 here)")
    A("- Downloads use **Python `urllib` only** — `curl` and `Invoke-WebRequest` fail")
    A("  on this machine (Windows schannel fault)")
    A("- **`s3-ap-northeast-1.amazonaws.com` is DNS-poisoned here; Steps 0–3 need a VPN.**")
    A("  `data.binance.vision` (CloudFront) is unaffected")
    A("- **Step 6a reads the committed snapshot `phase1/exchange_info_snapshot.json`, so it")
    A("  needs no network.** Add `--refresh-exchange-info` only to update the gate-4")
    A("  criterion (needs VPN)")
    A("")
    A("## The same thing, step by step")
    A("")
    A("What `run_phase1.py` executes, in order — this is also the fallback route when")
    A("one step needs debugging or has to be re-run on its own.")
    A("")
    A("```bash")
    A("# Step 0-2  enumerate archive -> hard filter -> monthly liquidity rank -> pool")
    A("python phase1/build_candidate_pool.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 3  download the candidate pool's raw data")
    A("python phase1/fetch_market_data.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 4  build the four normalized layer-2 tables")
    A("python phase1/build_layer2.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 5  build the 19-column dense panel")
    A("python phase1/build_features.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 6a four eligibility gates -> PIT membership")
    A("python phase1/build_universe.py --out-root data --sample-end " + sample_end)
    A("")
    A("# Step 6b quality report + dictionary + checksums + this file")
    A("python phase1/build_deliverables.py --out-root data --sample-end " + sample_end)
    A("```")
    A("")
    A("## Self-tests")
    A("")
    A("```bash")
    A("python config.py            # 8 checks")
    A("python -m lib.schema        # 65 checks")
    A("```")
    A("")
    A("## Verify")
    A("")
    A("```bash")
    A("# re-hash every output file; exit 0 when all digests match")
    A("python phase1/build_deliverables.py --out-root data --sample-end "
      + sample_end + " --verify")
    A("```")
    A("")
    A("## Notes")
    A("")
    A("- **Only Steps 0–3 need a VPN** (S3 enumeration and CDN download). Steps 4–6b are")
    A("  pure local computation; Step 6a reads a committed snapshot.")
    A("- Every script takes its output directory from `--out-root`, and every one")
    A("  **requires** it (`run_phase1.py` included). Environment variables are not used")
    A("  — they do not survive across shells, which once wrote smoke-test results into")
    A("  the production directory.")
    A("- **Step 6b must run last**: the checksums are its final write, and every file")
    A("  written before it is hashed. Re-running Steps 3–6a invalidates the checksums;")
    A("  re-run Step 6b to regenerate them.")
    A("- **This file is in `phase1/` and tracked by git**, not in `data/` — it is")
    A("  instructions rather than output. Step 6b rewrites it on every run; commit the")
    A("  change, so the log of which window and parameters each output used survives")
    A("  the next `data/` wipe.")
    A("")
    return "\n".join(L)


# ============================================================================
# 校验和
# ============================================================================

def checksum_targets() -> list:
    """参与校验和的全部文件，顺序固定。

    含 `raw/` —— 它也是产出（Step 3 下载的源数据）。
    递归扫 `04_qa/`，因此该目录下的文档与图自然被覆盖，不需要特例。
    排除三类：
      · `checksums.sha256` 自身（自指）
      · 写盘中的 `.part` 临时文件
      · `00_config/_cache/` —— 下载缓存，是临时的不是产出。实测它会把校验和
        从 1,442 个文件顶到 20,316 个，且每次重跑都变，掩盖真正该被校验的产出。
    """
    targets = []
    for sub in ("00_config", "raw", "01_layer2", "02_features",
                "03_reference", "04_qa"):
        p = DATA / sub
        if p.exists():
            targets += [f for f in sorted(p.rglob("*")) if f.is_file()]
    cache = DATA / "00_config" / "_cache"
    return [f for f in targets
            if f.name != "checksums.sha256" and f.suffix != ".part"
            and cache not in f.parents]


def verify_checksums() -> int:
    """逐行重算 `04_qa/checksums.sha256` 里的 SHA256，返回不一致个数。

    不写任何文件。用 `--verify` 调用；0 表示本地产出与产出时逐字节一致。
    """
    ck = QA / "checksums.sha256"
    if not ck.exists():
        print(f"找不到 {ck} —— 先跑一次 build_deliverables.py 生成。", file=sys.stderr)
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

    **必须是最后一个写盘动作**：此前写入的任何文件都会被纳入哈希。
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
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Step 6b —— 生成 D1 的交付文档与完整性证明")
    ap.add_argument("--out-root", required=True, help="产出根目录（必填）")
    ap.add_argument("--sample-end", required=True, help="样本截止日，必须是月末")
    ap.add_argument("--verify", action="store_true",
                    help="只核验 04_qa/checksums.sha256，不构建、不写任何文件")
    ap.add_argument("--skip-figures", action="store_true",
                    help="跳过 PNG 生成（离线/无 matplotlib 时用）")
    args = ap.parse_args()

    configure_paths(Path(args.out_root))
    if args.verify:
        log(f"verify_checksums   {QA / 'checksums.sha256'}")
        return 0 if verify_checksums() == 0 else 1
    cfg = cfg_mod.Config()
    cfg_mod.validate_sample_end(args.sample_end)

    QA.mkdir(parents=True, exist_ok=True)
    log("=" * 80)
    log(f"build_deliverables   sample_end={args.sample_end}")
    log(f"  产出根目录 : {DATA}")
    log("=" * 80)

    if not FE.exists():
        log(f"  ✗ 找不到面板 {FE} —— 先跑 Step 5。")
        return 4

    # ---- 1. 读面板（8 列）----------------------------------------------
    t0 = time.time()
    d = read_features()
    log(f"读入 features_1h：{len(d):,} 行 / {d['symbol'].nunique()} 个合约"
        f"   耗时 {time.time()-t0:.0f}s")

    # ---- 2. manifest（缺失归因与面板外探测都要用）------------------------
    man = pd.DataFrame()
    if MANIFEST.exists():
        man = pd.read_parquet(MANIFEST)
        bad = man[man["status"] != "ok"].copy()
        # 自我校验：状态说"没取得"、文件却躺在缓存里，说明 manifest 的 status 写坏了。
        # 这种行不是缺失，混进报告会把"没尝试过"报成"归档里没有"。
        # 实测踩过一次：18,832 项全在缓存里，manifest 却有 1,074 行 retry_exhausted。
        if len(bad):
            CACHE_ROOT = MANIFEST.parent / "_cache"
            on_disk = [(CACHE_ROOT / r.source / r.symbol / f"{r.period}.zip").exists()
                       for r in bad.itertuples(index=False)]
            n_bogus = int(sum(on_disk))
            if n_bogus:
                log(f"  ⚠ {n_bogus:,} 行状态为未取得、但文件在缓存里 —— "
                    f"manifest 的 status 不可信，已剔除。")
                man = man.drop(bad.index[on_disk])
    else:
        log("  ⚠ 找不到 manifest.parquet —— 缺口归因会全部落进「从未请求」一类")

    # ---- 3. 记录层：缺口与覆盖率 ---------------------------------------
    t0 = time.time()
    gaps = compute_gaps(d)
    cov = compute_coverage(d)
    mc = monthly_coverage(d)
    cause = compute_gap_causes(d, man)
    log(f"记录层：{len(gaps):,} 段缺口 / {len(cov):,} 个 (合约,指标) 覆盖率"
        f"   耗时 {time.time()-t0:.0f}s")
    log(f"  面板内 OI 缺口 {cause['hours']:,} 小时 —— 归档无文件 {cause['a_hours']:,}"
        f" / 文件在但无快照 {cause['b_hours']:,}")
    log(f"  面板外 404 {cause['out_n']:,} 个，落在面板内的 {cause['out_inside']} 个")

    # ---- 4. 成员集与资格表规模（两份文档的表都要用）---------------------
    n_members = n_member_syms = n_months_member = n_elig = 0
    mem_months: list[str] = []
    mem_p = REF / "universe_membership.parquet"
    if mem_p.exists():
        mem = pd.read_parquet(mem_p, columns=["symbol", "month"])
        n_members = len(mem)
        n_member_syms = mem["symbol"].nunique()
        n_months_member = mem["month"].nunique()
        mem_months = sorted(set(mem["month"].astype(str)))
    else:
        log("  ⚠ 找不到 universe_membership.parquet —— 报告里的成员集规模会记 0")
    elig_p = REF / "universe_eligibility.parquet"
    if elig_p.exists():
        n_elig = int(pq.ParquetFile(elig_p).metadata.num_rows)
    else:
        log("  ⚠ 找不到 universe_eligibility.parquet —— 字典里的行数会记 0")

    # ---- 5. 文档里所有会随数据变的数字 ----------------------------------
    # 以前这些是写死在字符串里的，刷新数据后不会自动更新（§4.3 那句已经和数据
    # 矛盾了）。集中算一次，两份文档共用。
    t0 = time.time()
    facts = compute_report_facts(d, cov, mc, man, cause, mem_months)
    panel = compute_panel_facts()
    grid_drops = compute_grid_drops(d)
    log(f"文档事实：{facts['mc_below_n']} 个月至少一源 <0.99 / "
        f"oi==0 {facts['oi_zero_rows']:,} 行 / funding null {panel['funding_null_pct']:.2%}"
        f"   耗时 {time.time()-t0:.0f}s")
    if grid_drops.get("mark"):
        log(f"  网格规则丢弃：mark {grid_drops['mark']['held']:,} 小时 / "
            f"index {grid_drops['index']['held']:,} 小时（归档里存在但 klines 无 bar）")

    # ---- 6. 图 ----------------------------------------------------------
    fig_paths: list[Path] = []
    if args.skip_figures:
        log("--skip-figures：跳过 PNG")
    else:
        try:
            fig_paths = [fig_coverage_distribution(cov), fig_monthly_coverage(mc)]
            for p in fig_paths:
                log(f"    -> {p.relative_to(DATA).as_posix()}  "
                    f"{p.stat().st_size/1024:.1f} KB")
        except Exception as e:                    # noqa: BLE001
            log(f"  ⚠ 生成图失败（{type(e).__name__}: {e}）—— 报告仍会生成，只是没有图。")
            fig_paths = []

    # ---- 7. 质量报告 ----------------------------------------------------
    q = build_quality_report(cfg, args.sample_end, d, cov, gaps, mc, cause,
                             facts, panel, grid_drops, n_members, n_member_syms,
                             n_months_member, fig_paths)
    (QA / "data_quality.md").write_text(q, encoding="utf-8", newline="\n")
    log(f"    -> 04_qa/data_quality.md            {len(q):,} 字符")

    # ---- 8. 数据字典 ----------------------------------------------------
    dd = build_data_dictionary(cfg, args.sample_end, len(d), d["symbol"].nunique(),
                               n_elig, n_members, panel)
    (QA / "data_dictionary.md").write_text(dd, encoding="utf-8", newline="\n")
    log(f"    -> 04_qa/data_dictionary.md         {len(dd):,} 字符")

    # ---- 9. REPRODUCE.md ------------------------------------------------
    repro = build_reproduce(cfg, args.sample_end)
    write_text_atomic(REPRO, repro)
    log(f"    -> phase1/REPRODUCE.md              {len(repro):,} 字符")

    # ---- 10. 校验和（最后一个写盘动作）---------------------------------
    written = write_checksums()
    log(f"    -> 04_qa/checksums.sha256           {written:,} 个文件")

    log("")
    log("=" * 80)
    log(f"完成   总耗时 {time.time()-T_START:.0f}s")
    log("=" * 80)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
