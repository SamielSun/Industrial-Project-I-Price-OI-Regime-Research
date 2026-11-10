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


def compute_coverage(d: pd.DataFrame) -> pd.DataFrame:
    """逐合约逐指标的覆盖率 = 非缺失小时 / 总小时。"""
    rows: list[dict] = []
    for s, g in d.groupby("symbol", sort=False):
        n_total = len(g)
        for metric, col in METRICS.items():
            n_bad = int(g[col].isna().sum()) if col.endswith("_close") \
                else int(g[col].sum())
            rows.append({"symbol": str(s), "metric": metric,
                         "coverage": (n_total - n_bad) / n_total if n_total else np.nan})
    return pd.DataFrame(rows)


def monthly_coverage(d: pd.DataFrame) -> pd.DataFrame:
    """逐月的整体覆盖率（四个源各一条线，与 §2 的表同口径）。

    除行加权均值（既有口径，保持不变）外，再算两列**稳健**口径：

    · `<src>_med`      合约等权的月中位数 —— 回答"典型合约是否完整"；
    · `<src>_below95`  覆盖率 < 0.95 的合约占比 —— 回答"有多少合约是真的残缺"。

    为什么必须加：行加权均值会被单个坏合约和小的月度分母放大。实测 2022-01 只有
    104 个合约，`ICPUSDT` 整月没有 OI，均值就从 1.0000 掉到 0.9904，而中位数仍是
    1.0000 —— 图上只看均值会读成"早期数据质量差"，其实是 1/104 的记账。

    阈值取 0.95：它把两类缺口分开了 ——
      · 多日归档洞（2 天 = 6.7% 缺失 → 0.933；3 天 → 0.893）落在 0.95 以下，进下图；
      · 单日全市场停摆（1 天 = 3.3% 缺失 → 0.967）落在 0.95 以上，只进上图的月中位数。
    0.999 则相反：早期 OI 那 0.1% 的零散缺口会把几乎每个合约都算成"不完整"，份额
    饱和在 0；0.99 又会让一次停摆把份额顶到 100%。
    """
    d = d.assign(ym=d["ts"].dt.strftime("%Y-%m"))
    srcs = list(METRICS)
    g = d.groupby("ym").agg(
        rows=("ts", "size"),
        klines=("bar_missing", lambda s: 1 - s.mean()),
        oi=("oi_missing", lambda s: 1 - s.mean()),
        mark=("mark_close", lambda s: 1 - s.isna().mean()),
        index=("index_close", lambda s: 1 - s.isna().mean()),
    )
    per = pd.DataFrame({
        "ym": d["ym"].to_numpy(),
        "symbol": d["symbol"].to_numpy(),
        "klines": (~d["bar_missing"].to_numpy()).astype("float64"),
        "oi": (~d["oi_missing"].to_numpy()).astype("float64"),
        "mark": d["mark_close"].notna().to_numpy().astype("float64"),
        "index": d["index_close"].notna().to_numpy().astype("float64"),
    }).groupby(["ym", "symbol"], sort=False)[srcs].mean()
    ym_level = per.index.get_level_values("ym")
    for c in srcs:
        g[f"{c}_med"] = per[c].groupby(level="ym").median()
        g[f"{c}_below95"] = (per[c] < 0.95).groupby(ym_level).mean()

    # ---- 逐日覆盖率 -> 月度【最差一天】-----------------------------------
    # 月均值（哪怕是中位数）会把一日事件摊到 744 小时里：2022-10-02 停摆一天，
    # 月度中位数只掉到 0.9677，读起来像"小抖动"；而 2022-02-26~28 三天的归档洞
    # 只影响 37% 的合约，中位数干脆不动。最差一天这个口径把两者都还原：
    # 停摆日 = 0%，三天洞 = 0.63（还有 63% 的合约有数据）。
    cov_day = pd.DataFrame({
        "day": d["ts"].dt.strftime("%Y-%m-%d").to_numpy(),
        "ym": d["ym"].to_numpy(),
        "klines": (~d["bar_missing"].to_numpy()).astype("float64"),
        "oi": (~d["oi_missing"].to_numpy()).astype("float64"),
        "mark": d["mark_close"].notna().to_numpy().astype("float64"),
        "index": d["index_close"].notna().to_numpy().astype("float64"),
    }).groupby(["day", "ym"])[srcs].mean()
    worst = cov_day.groupby(level="ym")[srcs].min()
    for c in srcs:
        g[f"{c}_worstday"] = worst[c]
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
    empty = {"hours": 0, "a_hours": 0, "a_pairs": 0, "a_traded": 0, "b_hours": 0,
             "out_n": 0, "out_inside": 0}
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

    # ---- 面板外的 404 探测：证明它们碰不到面板 --------------------------
    grid_lo = d.groupby("symbol")["ts"].min()
    grid_hi = d.groupby("symbol")["ts"].max()
    bad = man[man["status"] != "ok"].copy()
    out = {"out_n": 0, "out_inside": 0}
    if len(bad):
        bad["day"] = pd.to_datetime(
            bad["remote_path"].str.extract(r"-(\d{4}-\d{2}-\d{2})\.zip")[0],
            errors="coerce").dt.tz_localize("UTC")
        bad = bad.dropna(subset=["day"])
        lo = bad["symbol"].map(grid_lo).dt.floor("D")
        hi = bad["symbol"].map(grid_hi).dt.floor("D")
        inside = (bad["day"] >= lo) & (bad["day"] <= hi)
        out = {"out_n": int(len(bad)), "out_inside": int(inside.sum())}

    return {
        "hours": int(len(om)),
        "a_hours": int(a["hours"].sum()), "a_pairs": int(len(a)),
        "a_traded": int(a["traded"].sum()),
        "b_hours": int(b["hours"].sum()),
        **out,
    }


def compute_grid_drops(d: pd.DataFrame) -> dict:
    """面板缺 `mark`/`index`/`oi` 的小时里，有多少其实是【第 2 层网格规则】丢掉的。

    第 2 层的网格由 `klines_1h` 定义，mark/index/oi 里 klines 没有的小时一律丢弃。
    实测那些小时里归档【确实有】数据 —— 所以把它们一并算作"归档缺口"是错的。

    这一步要读 raw，面板本身看不出来。三个源分两条路径：mark/index 是每合约一个
    文件（只读受影响的那几十个），oi 在 metrics 年度文件里、且按 `ts_end` 对齐。

    返回的 `days` 让文档能说明丢弃集中在哪几天（根因见 data_quality.md §3①）。
    """
    out: dict = {"mark": None, "index": None, "oi": None}
    bm = d.loc[d["bar_missing"].to_numpy(), ["symbol", "ts"]]
    if not len(bm):
        return out
    keys = set(zip(bm["symbol"], bm["ts"]))
    syms = sorted(bm["symbol"].unique())

    for metric, src in (("mark", "markPriceKlines"), ("index", "indexPriceKlines")):
        miss = int(d[METRICS[metric]].isna().sum())
        in_grid = int((d[METRICS[metric]].isna() & d["bar_missing"]).sum())
        held = 0
        # 按日期计数：文档要说明这些丢弃【集中在哪几天】—— 根因是归档那几天本身缺 bar，
        # 而不是数据零星散落。只在已有的读循环里顺手记，不额外读文件。
        days: dict[str, int] = {}
        for s in syms:
            f = RAW / src / f"symbol={s}.parquet"
            if not f.exists():
                continue
            t = pq.read_table(str(f), columns=["open_time"]).to_pandas()
            # raw 的 open_time 是 int64【毫秒】，不是 datetime —— 必须显式给 unit
            ts = pd.to_datetime(t["open_time"], unit="ms", utc=True)
            for x in ts:
                if (s, x) in keys:
                    held += 1
                    k = x.strftime("%Y-%m-%d")
                    days[k] = days.get(k, 0) + 1
        out[metric] = {"missing": miss, "grid": in_grid, "held": held, "days": days}

    # ---- oi：走【另一条读路径】才能算 ----
    # 两个不同点：① 合并键是 `ts_end`，不是 `ts`（第 2 层 `o.merge(c, on="ts_end")`）；
    # ② 来源是 metrics 的【年度文件】，不是每合约一个文件。
    # 不把它算出来的话，§3① 的网格规则列表会漏掉 OI，§3② 也会把"被网格丢掉、
    # 归档其实有快照"的小时误报成快照缺口。
    bm_oi = d.loc[d["bar_missing"].to_numpy() & d["oi_missing"].to_numpy(),
                  ["symbol", "ts"]].copy()
    if len(bm_oi):
        bm_oi["ts_end"] = bm_oi["ts"] + pd.Timedelta(hours=1)
        need = set(zip(bm_oi["symbol"], bm_oi["ts_end"]))
        want = set(bm_oi["ts_end"])
        held_oi = 0
        for f in sorted((RAW / "metrics").glob("year=*.parquet")):
            t = pq.read_table(str(f), columns=["symbol", "create_time"]).to_pandas()
            # 先按时间戳把 700 万行砍到几百行，再逐个查 —— 直接建全量 set 会慢一个量级
            t = t[t["create_time"].isin(want)]
            held_oi += sum(1 for k in zip(t["symbol"], t["create_time"]) if k in need)
        out["oi"] = {"missing": int(d["oi_missing"].sum()),
                     "grid": int(len(bm_oi)), "held": held_oi, "days": {}}
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
        "vwap_in_range_pct": (n_in_range / n_vwap) if n_vwap else float("nan"),
        "funding_null_pct": (n_fund_null / n_fund) if n_fund else float("nan"),
        "funding_nonnull_pct": (1 - n_fund_null / n_fund) if n_fund else float("nan"),
        "interval_change_syms": sum(1 for v in intervals.values() if len(v) > 1),
        "interval_values": sorted({x for v in intervals.values() for x in v}),
    }


def compute_report_facts(d: pd.DataFrame, cov: pd.DataFrame, mc: pd.DataFrame) -> dict:
    """data_quality.md 里所有【会随数据变化】的数字，一处算清。

    文档刻意保持短，所以这里只算它真正用到的几个量 —— 其余的中间统计不再保留，
    免得重演"算了却没人读"（审计时一次清掉过十几处）。

    不用 manifest：面板外的 404 探测对面板零影响，已经不写进文档了。
    """
    srcs = list(METRICS)

    # ---- 完全没有任何数据的合约 ----
    zero_syms = sorted({str(s) for s in cov.loc[cov["coverage"] == 0, "symbol"]})

    # ---- 有源跌破 0.99 的月份数（只用于运行日志）----
    mc_min = mc[srcs].min(axis=1)
    mc_below_n = int((mc_min < 0.99).sum())

    # ---- 全市场断供：某小时【过半在场合约】同缺同一个源 ----
    # 把「交易所那天没发布」与「一个合约坏了」分开 —— 月度均值看不出这个区别。
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

    # ---- oi == 0：刻意不标记的那一类 ----
    oi0 = d[d["oi"].notna() & (d["oi"] == 0)]

    # ---- `at 100%` 那一列有多脆弱：排除停摆日重算 ----
    # 只报 11 会让人误以为"只有 11 个合约的 mark 是完整的"。实测那 11 是被全市场
    # 停摆日压出来的：排除 4 个停摆日，mark/index 升到 236 / 186；单个停摆日也足以
    # 造成同样的错觉。不给出反事实，这一列就会被读成"数据大面积残缺"。
    #
    # 全用整数做：725 万行上 dt.strftime 造字符串要 40 多秒，是这一步原来的瓶颈。
    # 日码 = epoch 纳秒 // 一天的纳秒；再按合约做 np.bincount 加权求和。
    out_days = sorted({o["start"][:10] for o in outages})
    day_ns = 86_400_000_000_000
    codes = (d["ts"].dt.tz_convert("UTC").dt.tz_localize(None)
             .astype("int64").to_numpy() // day_ns)
    sym_codes, _ = pd.factorize(d["symbol"].to_numpy())
    n_sym = int(sym_codes.max()) + 1
    day_codes = [(dd, int(pd.Timestamp(dd, tz="UTC").value // day_ns)) for dd in out_days]
    at100_excl: dict = {}
    for metric, col in (("mark", "mark_close"), ("index", "index_close")):
        miss = d[col].isna().to_numpy()
        tot = np.bincount(sym_codes, weights=miss, minlength=n_sym)
        rem_all = tot.copy()
        best_n, best_d = 0, ""
        for dd, dc in day_codes:
            m = codes == dc
            per = np.bincount(sym_codes[m], weights=miss[m], minlength=n_sym)
            n = int(((tot - per) <= 0).sum())
            if n > best_n:
                best_n, best_d = n, dd
            rem_all -= per
        at100_excl[metric] = {"one_day": best_n, "one_day_name": best_d,
                              "all_days": int((rem_all <= 0).sum())}

    # ---- 有 bar 但零成交的小时：观测存在，但内容不是「价格没动」 ----
    # 这一条【不带任何标记】（bar_missing=False），是最容易被当成正常行的一类。
    # 停牌期间交易所继续按小时发 bar，价格冻结在最后成交价、量全部写 0。
    zero_trade = (d["quote_volume"].notna() & (d["quote_volume"] == 0)
                  & ~d["bar_missing"])
    zt_top = d.loc[zero_trade, "symbol"].value_counts().head(3)

    return {
        "zero_syms": zero_syms,
        "mc_below_n": mc_below_n,
        "outages": outages,
        "oi_zero_rows": int(len(oi0)),
        "at100_excl": at100_excl,
        "n_zero_trade": int(zero_trade.sum()),
        "zero_trade_top": zt_top,
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


def month_events(mc: pd.DataFrame, d: pd.DataFrame, thresh: float = 0.20) -> list[dict]:
    """逐月汇总数据缺口事件，供图上的竖线与图下说明使用。

    两类：
      ① 有"某一天"的缺口：某天 ≥thresh 的在场合约缺某个源（归档洞 / 停摆 / OI 断供）；
      ② 没有单日事件、但整月有 >10% 的合约缺某个源（合约级长缺口，如 2023-04 的 index）。

    完全按数据算，不写死日期 —— 换样本或重下数据后标注自动跟着走。
    """
    day = d["ts"].dt.strftime("%Y-%m-%d").to_numpy()
    cols = {"klines": d["bar_missing"].to_numpy(),
            "oi": d["oi_missing"].to_numpy(),
            "mark": d["mark_close"].isna().to_numpy(),
            "index": d["index_close"].isna().to_numpy()}
    per_day: dict[str, dict[str, float]] = {}
    for name, arr in cols.items():
        share = pd.Series(arr).groupby(day).mean()
        for dd, sh in share[share >= thresh].items():
            per_day.setdefault(dd, {})[name] = float(sh)

    by_month: dict[str, dict] = {}
    for dd, srcs in sorted(per_day.items()):
        m = by_month.setdefault(dd[:7], {"days": [], "srcs": {}})
        m["days"].append(dd)
        for k, v in srcs.items():
            m["srcs"][k] = max(m["srcs"].get(k, 0.0), v)

    out = []
    for ym, m in sorted(by_month.items()):
        days = sorted(m["days"])
        mm = days[0][5:7]
        if len(days) == 1:
            tag, when = days[0][5:], days[0]
        elif (pd.Timestamp(days[-1]) - pd.Timestamp(days[0])).days == len(days) - 1:
            tag = f"{mm}-{days[0][8:]}…{days[-1][8:]}"
            when = f"{ym}-{days[0][8:]}…{days[-1][8:]}"
        else:
            tag = mm + "-" + "/".join(d[8:] for d in days)
            when = ym + "-" + "/".join(d[8:] for d in days)
        srcs = dict(sorted(m["srcs"].items(), key=lambda kv: -kv[1]))
        bits = ", ".join(f"{k} {v:.0%}" for k, v in srcs.items())
        if "klines" in srcs:
            why = "klines archive hole (the grid is klines-defined, so the rest read NaN)"
        elif srcs and list(srcs)[0] == "oi":
            why = "exchange-wide OI gap"
        else:
            why = "exchange-wide outage"
        out.append({"month": ym, "tag": tag, "when": when,
                    "desc": f"{why}: {bits}"})

    # ---- ② 没有单日事件、但整月有相当比例合约缺源的月份 ----------------
    seen = {e["month"] for e in out}
    for ym, r in mc.iterrows():
        if ym in seen:
            continue
        low = {c: float(r[f"{c}_worstday"]) for c in METRICS
               if float(r[f"{c}_worstday"]) < 0.90}
        if not low:
            continue
        c = min(low, key=low.get)
        out.append({"month": ym, "tag": ym[2:], "when": ym,
                    "desc": f"{c} short all month: {100 * (1 - low[c]):.0f}% of contracts "
                            f"lack it even on the best-covered day (no single bad day)"})
    out.sort(key=lambda e: e["month"])
    return out


def fig_monthly_coverage(mc: pd.DataFrame, events: list[dict]) -> Path:
    """月度覆盖率：每个月画【最差一天】的覆盖率（四个源），事件用竖虚线标日期。

    为什么不用月均值/中位数：一个月有 700+ 小时，单日缺口会被摊薄到看不出——
    2022-10-02 停摆一天，月度中位数只掉到 0.9677；2022-02-26~28 的三天归档洞只
    影响 37% 的合约，中位数根本不动。改成"当月最差一天的覆盖率"以后，两种事件都
    按真实幅度显示：停摆日 → 0%，三天洞 → 63%（还有 63% 的合约有数据）。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"index": "#6a1b9a", "oi": "#c62828",
              "mark": "#1565c0", "klines": "#2f7d32"}
    x = np.arange(len(mc))
    months = list(mc.index)

    fig, ax = plt.subplots(figsize=(12.4, 6.9))
    fig.subplots_adjust(left=0.075, right=0.985, top=0.865, bottom=0.45)

    for c in ["index", "oi", "mark", "klines"]:
        ax.plot(x, 100 * mc[f"{c}_worstday"].to_numpy(), label=c, color=colors[c],
                linewidth=1.6, alpha=0.88, marker="o", markersize=2.6)
    ax.set_ylim(-5, 107)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("contracts covered (%)\non the month's worst day", fontsize=9)
    ax.axhline(100, color="#999999", linewidth=0.8, linestyle="--")
    ax.legend(fontsize=9, ncol=4, loc="lower left", framealpha=0.92)
    ax.grid(alpha=0.25, linewidth=0.6)
    step = 6
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels(months[::step], rotation=35, ha="right", fontsize=7.5)

    # ---- 事件：竖虚线 + 日期标签 ----
    for ev in events:
        if ev["month"] not in months:
            continue
        i = months.index(ev["month"])
        ax.axvline(i, color="#333333", linewidth=0.9, linestyle=(0, (3, 2)), alpha=0.8)
        ax.annotate(ev["tag"], xy=(i, 107), xycoords=("data", "data"),
                    xytext=(0, 3), textcoords="offset points",
                    rotation=90, ha="center", va="bottom", fontsize=7.5, color="#333333")

    fig.suptitle(f"Coverage by month ({len(mc)} months): share of contracts covered by each "
                 f"source on that month's worst day", fontsize=11.5)

    # ---- 图下说明 ----
    y0 = 0.325
    fig.text(0.075, y0 + 0.045,
             "Dashed lines: months with a day on which at least 20% of live contracts lack a "
             "source. Shares are measured on the panel grid:",
             fontsize=8.5, color="#222222")
    for k, ev in enumerate(events):
        yy = y0 - k * 0.028
        fig.text(0.075, yy, ev["when"], fontsize=8, color="#222222")
        fig.text(0.175, yy, ev["desc"], fontsize=8, color="#333333")
    fig.text(0.075, y0 - len(events) * 0.028 - 0.012,
             "The grid is defined by klines, so on the five klines-hole days the other three "
             "sources read NaN even though the raw archive holds them (§3 ①).",
             fontsize=7.5, color="#555555")

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
                         mc: pd.DataFrame, cause: dict,
                         facts: dict, grid_drops: dict,
                         n_members: int, n_member_syms: int, n_months_member: int,
                         fig_paths: list[Path]) -> str:
    """data_quality.md —— 总体概览 + 覆盖率 + 必须知道的缺。

    刻意保持短：读者要的是"能不能用、哪里有坑"，不是把每个中间量都摊开。
    明细仍在 facts / panel / cause / grid_drops 里算，只是不再全部落进文档。
    """
    L: list[str] = []
    A = L.append
    n_rows = len(d)
    n_syms = d["symbol"].nunique()
    n_months = int(mc.shape[0])
    hist_h = d.groupby("symbol").size()

    A("# Data Quality — Phase 1 (D1)")
    A("")
    A(f"Sample window `{cfg.sample_start}` .. `{sample_end}`　·　"
      f"generated by `phase1/build_deliverables.py`")
    A("")
    A("---")
    A("")

    # ---- 1. Overview -----------------------------------------------------
    A("## 1. Overview")
    A("")
    A("| | |")
    A("|---|---|")
    A(f"| Hourly panel rows | **{n_rows:,}** |")
    A(f"| Contracts / months | **{n_syms}** / **{n_months}** |")
    A(f"| Universe (contract × month) | **{n_members:,}** cells · "
      f"**{n_member_syms}** distinct contracts · over {n_months_member} months |")
    A(f"| History per contract | median **{hist_h.median():,.0f} h** "
      f"({hist_h.median()/24/30:.1f} months), range {hist_h.min():,} – {hist_h.max():,} h |")
    A("")
    A("The panel is a **dense hourly grid**: every hour from a contract's first bar to its")
    A("last active day has exactly one row. Missing hours are still rows — they carry the")
    A("`bar_missing` / `oi_missing` flags. So the row count above is the **grid size**, not")
    A("the number of real observations.")
    A("")
    A("---")
    A("")

    # ---- 2. Coverage -----------------------------------------------------
    A("## 2. Coverage")
    A("")
    A("Coverage = non-missing hours / total hours, per contract and source, measured **on the")
    A("panel grid** — §① explains why `mark` / `index` understate what the archive holds.")
    A("")
    A("| Source | median | at 100% | ≥ 0.999 | < 0.99 | min |")
    A("|---|---|---|---|---|---|")
    for metric in METRICS:
        c = cov[cov["metric"] == metric]["coverage"]
        A(f"| `{metric}` | {c.median():.4f} | {int((c >= 1.0).sum())} | "
          f"{int((c >= 0.999).sum())} | {int((c < 0.99).sum())} | {c.min():.4f} |")
    A("")
    ex = (facts.get("at100_excl") or {})
    out_days = sorted({o["start"][:10] for o in facts["outages"]})
    if ex.get("mark") and ex.get("index"):
        em, ei = ex["mark"], ex["index"]
        cm = int((cov[cov["metric"] == "mark"]["coverage"] >= 1.0).sum())
        ci = int((cov[cov["metric"] == "index"]["coverage"] >= 1.0).sum())
        A(f"**The `at 100%` column is brittle** — it is set by {len(out_days)} exchange-wide")
        A("outage days, each 24 h, on which most listed contracts lose both price sources:")
        A(f"{' · '.join('`' + x + '`' for x in out_days)}.")
        A(f"Excluding `{em['one_day_name']}` alone lifts `mark` / `index` from {cm} / {ci} to "
          f"{em['one_day']} / {ei['one_day']};")
        A(f"excluding all of them, to **{em['all_days']}** / **{ei['all_days']}**. "
          "Read the `≥ 0.999` column instead.")
        A("")
    # 「覆盖率不均匀」原先在 §3 单列一条，但它就是对表格 min 列的解释 —— 放在表格下更顺。
    oi_cov = cov[cov["metric"] == "oi"]
    n_low = int((oi_cov["coverage"] < 0.90).sum())
    worst = oi_cov.nsmallest(1, "coverage").iloc[0] if n_low else None
    if facts["zero_syms"]:
        z = " / ".join(f"`{s}`" for s in facts["zero_syms"])
        A(f"**Coverage is not uniform.** {z} has **no `mark` / `index` at all** — that is the")
        A("`min = 0.0000` in the table above"
          + (f", and {n_low} contracts have `oi` coverage below 0.90 (`{worst['symbol']}`)."
             if n_low else ". No contract has `oi` coverage below 0.90."))
        A("")
    A("**The median hides the distribution, which is why both are shown.** `klines` is")
    A("complete almost everywhere; `mark` and `index` commonly differ from it by a few")
    A("hours. The distribution and its stability over time:")
    A("")
    for p in fig_paths:
        # 链接相对于【报告自己的目录】（04_qa/），不是 data/ —— 否则 Markdown 里是死链
        A(f"![{p.stem}]({p.relative_to(QA).as_posix()})")
        A("")
    A("The second figure plots, for every month, the share of contracts that have a given")
    A("source **on that month's worst day**, so a one-day hole cannot be averaged away: the")
    A("2022-10-02 outage reads 0%, while the three-day `klines` hole of 2022-02-26…28 reads")
    A("63% (63% of contracts still had data). The dashed lines and the list underneath are")
    A("the seven months with a day on which at least 20% of live contracts lack a source:")
    A("two `klines` archive holes (§①), four exchange-wide outages (one of them index-only,")
    A("2022-07-31) and one exchange-wide OI gap (2024-02-16); a further month, 2023-04, has")
    A("a contract-level `index` gap rather than a bad day. The first months are **not**")
    A(f"incomplete (`{mc.index[0]}` reads {mc.iloc[0]['klines']:.4f} on `klines`); the older")
    A("\"early months look unstable\" reading came from averaging *rows* across a denominator")
    A("of about 100 contracts, which let one contract with no OI dominate the line.")
    A("")
    A("---")
    A("")

    # ---- 3. Gaps you must know -------------------------------------------
    A("## 3. Gaps you must know")
    A("")
    # 网格规则【一次讲清三个源】。旧版把 mark/index 与 oi 分在 ①② 两处各讲一遍。
    gd_m, gd_i = grid_drops.get("mark"), grid_drops.get("index")
    oi_held = (grid_drops.get("oi") or {}).get("held")
    if gd_m and gd_i:
        parts = [f"{gd_m['held']:,} `mark`", f"{gd_i['held']:,} `index`"]
        if oi_held:
            parts.append(f"{oi_held:,} `oi`")
        A("**① The grid rule drops data the archive holds.** Layer 2 builds the panel grid")
        A(f"from `klines`, so hours without a bar drop out of the other sources too: "
          f"{', '.join(parts)} hours.")
        A("They read `NaN` even though the value exists, and all of them are recoverable from")
        A("`data/raw/`.")
        top = sorted(gd_m["days"].items(), key=lambda kv: -kv[1])[:5]
        if top:
            listed = " · ".join(f"`{dt}`" for dt, _ in sorted(top))
            share = sum(n for _, n in top) / gd_m["held"]
            A(f"The `mark` drops are concentrated: five days carry {share:.0%} of them —")
            A(f"{listed} — because the `klines` archive itself is")
            A("missing bars there while `mark` / `index` / `metrics` exist.")
        A("")
    if cause["a_hours"]:
        frac = cause["a_traded"] / max(cause["a_hours"], 1)
        A(f"**② `oi` has real holes.** {cause['a_hours']:,} hours "
          f"({cause['a_pairs']:,} contract-days) have **no file in the")
        A(f"archive at all**, and in {frac:.0%} of those hours the contract was actively")
        if oi_held:
            A("trading. The genuine snapshot gaps — files that exist but carry no snapshot")
            A(f"for those hours — number **{cause['b_hours'] - oi_held:,}**.")
        else:
            A(f"trading. The rest of the `oi` gap — {cause['b_hours']:,} hours — is files that")
            A("exist but carry no snapshot for those hours.")
        A("")
    # 旧版【没有】这一条：不带任何标记、最容易被当成正常观测的一类。
    nz = facts.get("n_zero_trade") or 0
    if nz:
        zt = facts.get("zero_trade_top")
        who = (f"; `{zt.index[0]}` alone accounts for {zt.iloc[0]:,} of them"
               if zt is not None and len(zt) else "")
        A(f"**③ Hours that look like observations but are not.** {nz:,} hours carry a `klines`")
        A("bar with `quote_volume == 0` (and zero `trades`): the contract was halted and the")
        A(f"exchange kept publishing a frozen price{who}. They carry **no flag** —")
        A("`bar_missing` is `False` — and `close.pct_change()` returns exactly 0 on every one")
        A("of them. Filter with `quote_volume > 0` before any return or volatility work.")
        A("")
    # 旧 ⑤ 的两条 funding 在 data_dictionary.md 已有专节（含同一个 16.65% 的数），
    # 这里只留"该怎么做"的动作警告；`oi == 0` 那份字典里没有，必须留。
    A(f"**④ `oi == 0` is not a gap.** {facts['oi_zero_rows']:,} rows are a market-wide")
    A("publishing event, not a defect — downstream may filter with `oi > 0`. The funding")
    A("columns are sparse and forward-filled by design; see the data dictionary.")
    A("")
    A("---")
    A("")

    # ---- 4. How to verify -------------------------------------------------
    A("## 4. How to verify")
    A("")
    A("```bash")
    A("# re-hash every output file; exit 0 when all digests match")
    A("python phase1/build_deliverables.py --out-root data --sample-end "
      + sample_end + " --verify")
    A("```")
    A("")
    A("It re-hashes every file under `data/` except the temporary download cache")
    A("`00_config/_cache/`, and covers this report, the dictionary and the figures.")
    A("")
    A("**It proves internal consistency** (your output equals the output that was")
    A("generated), **not provenance** (that the downloaded files equal the archive) —")
    A("the latter would need Binance's own `.CHECKSUM` files, which this phase does not")
    A("use.")
    A("")
    return "\n".join(L)

# ============================================================================
# data_dictionary.md（英文，只管列定义）
# ============================================================================

def build_data_dictionary(cfg, sample_end: str, n_rows: int, n_syms: int,
                          n_elig: int, n_members: int, panel: dict) -> str:
    """data_dictionary.md —— 列定义 + 四条必须懂的语义。

    只管"每列是什么"。数据完不完整看 data_quality.md。
    """
    L: list[str] = []
    A = L.append
    A("# Data Dictionary — Phase 1 (D1)")
    A("")
    A(f"Sample window `{cfg.sample_start}` .. `{sample_end}`　·　"
      f"{n_rows:,} rows / {n_syms} contracts")
    A("")
    A("**Scope: column definitions only.** For whether the data is complete, see")
    A("[`data_quality.md`](data_quality.md).")
    A("")
    A("---")
    A("")
    A("## 1. Where everything is")
    A("")
    A("```")
    A("data/")
    A("├── 00_config/       bookkeeping — manifest.parquet (per-file download ledger)")
    A("│                    + archive / kept / dropped contract lists")
    A("├── raw/             the five sources exactly as downloaded (Step 3)")
    A("├── 01_layer2/       four normalized 1h tables (Step 4)")
    A("├── 02_features/     features_1h — the analysis panel (Step 5)")
    A("├── 03_reference/    candidate pool + universe tables (Step 6a)")
    A("└── 04_qa/           data_quality.md · this file · figures · checksums.sha256")
    A("")
    A("phase1/REPRODUCE.md  how to rebuild all of this (tracked by git)")
    A("```")
    A("")
    A("The four hourly tables are partitioned `year=YYYY/chunk=YYYY-MM.parquet`. Every")
    A("timestamp is UTC.")
    A("")
    A("---")
    A("")
    A("## 2. `features_1h` — the analysis panel")
    A("")
    A("| Column | Type | Unit | Source | Meaning |")
    A("|---|---|---|---|---|")
    A("| `symbol` | string | — | — | Contract name, e.g. `BTCUSDT` |")
    A("| `ts` | timestamp | UTC | — | Bar **start**, on the hour |")
    A("| `ts_end` | timestamp | UTC | derived | `ts + 1h` — the OI alignment instant |")
    A("| `open` `high` `low` `close` | float64 | USDT | `klines` | OHLC within the bar |")
    A("| `volume` | float64 | base asset | `klines` | Traded quantity of the base asset |")
    A("| `quote_volume` | float64 | USDT | `klines` | Traded notional — the liquidity input |")
    A("| `trades` | float64 | count | `klines` | Number of trades in the bar |")
    A("| `taker_buy_volume` | float64 | base asset | `klines` | Taker-buy quantity |")
    A("| `taker_buy_quote_volume` | float64 | USDT | `klines` | Taker-buy notional |")
    A("| `oi` | float64 | base asset | `metrics` | Open interest **at `ts_end`** |")
    A("| `mark_close` | float64 | USDT | `markPriceKlines` | Mark price at bar close |")
    A("| `index_close` | float64 | USDT | `indexPriceKlines` | Index price at bar close |")
    A("| `funding_rate` | float64 | ratio | `fundingRate` | Non-null **at settlement hours only**; never filled |")
    A("| `funding_interval_hours` | float64 | hours | `fundingRate` | Forward-filled between settlements (see ③) |")
    A("| `bar_missing` | bool | — | derived | This hour has no row in `klines_1h` (padded) |")
    A("| `oi_missing` | bool | — | derived | No OI snapshot for this hour |")
    A("")
    A("---")
    A("")
    A("## 3. Four semantics that must be understood")
    A("")
    A("**① `oi` is aligned to the interval *end*, not the bar start.**")
    A("")
    A("```")
    A("bar [20:00, 21:00)  pairs with  OI(21:00)     <- the row's ts is 20:00")
    A("```")
    A("")
    A("At `ts_end` price and OI become available **at the same instant**, so the row is")
    A("self-contained and needs no forward-looking information.")
    A("")
    A("**② `funding_rate`'s sparsity is semantics, not a data-quality problem.**")
    A("")
    A(f"Only {panel['funding_nonnull_pct']:.2%} of rows carry a value (settlement hours);")
    A("the rest are `NaN` by design — which is why it is excluded from gap detection.")
    A("")
    A("**③ `funding_interval_hours` is forward-filled, and the interval changes.**")
    A("")
    A("Between settlements the value is the interval announced at the previous settlement —")
    A(f"a known quantity at decision time, not an invention. This sample uses "
      f"{', '.join(f'{v:g}h' for v in panel['interval_values'])}, and "
      f"{panel['interval_change_syms']} contracts")
    A("changed interval mid-sample: **read this column rather than hard-coding 8h**.")
    A("")
    A("**④ `oi`, `volume` and `taker_buy_volume` are in base-asset units, not contracts.**")
    A("")
    A(f"`quote_volume / volume` is the bar's volume-weighted average price and falls inside")
    A(f"`[low, high]` on **{panel['vwap_in_range_pct']:.4%}** of bars — only possible if")
    A("`volume` and `quote_volume` share the price's unit system. Do not assume a fixed")
    A("contract multiplier: contracts whose base asset starts with `1000` count thousand")
    A("tokens per unit.")
    A("")
    A("---")
    A("")
    A("## 4. The other tables")
    A("")
    A("| Table | Grain | Key columns | Rows |")
    A("|---|---|---|---|")
    A("| `klines_1h` | 1 hour | `symbol` `ts` `ts_end` + OHLCV + taker volumes | same grid as `features_1h` |")
    A("| `mark_index_1h` | 1 hour | `symbol` `ts` `ts_end` `mark_close` `index_close` | same |")
    A("| `oi_1h` | 1 hour | `symbol` `ts` `ts_end` `oi` `oi_missing` | same |")
    A("| `funding` | settlement | `symbol` `ts_funding` `funding_rate` `funding_interval_hours` | event table, off-grid |")
    A(f"| `master` | contract | `symbol` `base_asset` `first_bar` `last_bar` `n_bars` `contract_type` | {n_syms} |")
    A(f"| `candidate_pool.csv` | contract | `symbol` | {n_syms} |")
    A(f"| `universe_eligibility` | contract × month | 20 cols: window metrics + gate booleans + `eligible` `rank` | {n_elig:,} |")
    A(f"| `universe_membership` | contract × month | `symbol` `month` `rank` `liq` `oi_cov` … | {n_members:,} |")
    A("| `member_changes` | month | `month` `n_members` `n_entered` `n_exited` `turnover` | 1 per month |")
    A("")
    A("The three hourly tables share **one grid**, defined by `klines_1h`; `funding` is an")
    A("event table and is not on it.")
    A("")
    A("**`month` is the decision instant, not the performance interval.** A row with")
    # 例子取样本最后一个月；三个日期全部由 sample_end + liq_window_days 算出 ——
    # 写死的话，样本往前推之后这段说明会和实际口径对不上。
    _cut = pd.Timestamp(sample_end).normalize().replace(day=1)
    _lo = _cut - pd.Timedelta(days=cfg.liq_window_days)
    _nxt = _cut + pd.offsets.MonthBegin(1)
    A(f"`month = {_cut:%Y-%m}` was decided at `{_cut:%Y-%m-%d} 00:00 UTC` using the window")
    A(f"`[{_lo:%Y-%m-%d}, {_cut:%Y-%m-%d})`, and applies to "
      f"`[{_cut:%Y-%m-%d}, {_nxt:%Y-%m-%d})`.")
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

    # ---- 3. 记录层：覆盖率与缺口归因 -----------------------------------
    t0 = time.time()
    cov = compute_coverage(d)
    mc = monthly_coverage(d)
    cause = compute_gap_causes(d, man)
    log(f"记录层：{len(cov):,} 个 (合约,指标) 覆盖率   耗时 {time.time()-t0:.0f}s")
    log(f"  面板内 OI 缺口 {cause['hours']:,} 小时 —— 归档无文件 {cause['a_hours']:,}"
        f" / 文件在但无快照 {cause['b_hours']:,}")
    log(f"  面板外 404 {cause['out_n']:,} 个，落在面板内的 {cause['out_inside']} 个")

    # ---- 4. 成员集与资格表规模（两份文档的表都要用）---------------------
    n_members = n_member_syms = n_months_member = n_elig = 0
    mem_p = REF / "universe_membership.parquet"
    if mem_p.exists():
        mem = pd.read_parquet(mem_p, columns=["symbol", "month"])
        n_members = len(mem)
        n_member_syms = mem["symbol"].nunique()
        n_months_member = mem["month"].nunique()
    else:
        log("  ⚠ 找不到 universe_membership.parquet —— 报告里的成员集规模会记 0")
    elig_p = REF / "universe_eligibility.parquet"
    if elig_p.exists():
        n_elig = int(pq.ParquetFile(elig_p).metadata.num_rows)
    else:
        log("  ⚠ 找不到 universe_eligibility.parquet —— 字典里的行数会记 0")

    # ---- 5. 文档里所有会随数据变的数字 ----------------------------------
    # 以前这些是写死在字符串里的，刷新数据后不会自动更新（有一句甚至已经和数据
    # 矛盾了）。集中算一次，两份文档共用。
    t0 = time.time()
    facts = compute_report_facts(d, cov, mc)
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
            fig_paths = [fig_coverage_distribution(cov),
                         fig_monthly_coverage(mc, month_events(mc, d))]
            for p in fig_paths:
                log(f"    -> {p.relative_to(DATA).as_posix()}  "
                    f"{p.stat().st_size/1024:.1f} KB")
        except Exception as e:                    # noqa: BLE001
            log(f"  ⚠ 生成图失败（{type(e).__name__}: {e}）—— 报告仍会生成，只是没有图。")
            fig_paths = []

    # ---- 7. 质量报告 ----------------------------------------------------
    q = build_quality_report(cfg, args.sample_end, d, cov, mc, cause,
                             facts, grid_drops, n_members, n_member_syms,
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
