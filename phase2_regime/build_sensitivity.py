#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_sensitivity —— Phase 2 的阈值稳健性交付物（表 5 + 图）

它在项目中的位置：D2 验收条款点名要 "Threshold sensitivity table across the 60th to
80th percentile range"，note 第 87 行另外点名了第二种方法（z-score based thresholds）。

⚠️ **它只做 note 那句话的【第一层】。** 三层划分是：
     L1（本脚本）  阈值变时【标签】怎么变        ← 只满足 D2 的字面
     L2（Phase 3） 阈值变时【事件研究结论】怎么变  ← note 那句话真正的落点
     L3（Phase 4/5）阈值变时【交互与回测】怎么变
   L1 里没有任何结果变量，"not optimized to fit the backtest" 这条禁令在纯标签表里
   无处安放 —— 所以 L2/L3 不是锦上添花，是必须补的。

做什么
------
  读 data/05_regime/regime_labels/（**不读面板、不重算标签**）
    → 每个合约按 ts_end 排出序列
    → 6 档分位阈值（滚动 90 日历天）+ 2 个 σ（同窗）
    → 分位法的标注数与四档组成
    → z 法：每个观测塌缩成 m = min(|pc|/σ_p, |oc|/σ_o)
    → 配对：z*(q) = m 降序第 N_q 个（闭式解，一次排序）
    → 表 5（method × threshold × freq）+ 一张双方法对照图

⚠️ 两条实测踩过的坑
  1. **分母用 excl_reason ∈ {ok, warmup}**，不是"σ 可用的行数"。warmup 行两条方法都
     标不了，但要计入分母才与主表同口径（用后者会让所有标注率虚高约 3%）。
  2. **warmup 用标签表存好的 excl_reason**，不要自己按"距首行 ≥30 天"重算 ——
     标签表每个合约第一行已经是第二个决策时刻，生成器的滚动窗也以它为起点。

用法
----
  python phase2_regime/build_sensitivity.py --out-root <data 绝对路径>
  python phase2_regime/build_sensitivity.py --out-root data --freqs 1h
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
# 控制台是 GBK：源码里有 '⚠️'（U+26A0/U+FE0F）和 '✓'（U+2713），GBK 编不了。
# 之前只是恰好没走到那些分支 —— 一旦打印就 UnicodeEncodeError 崩掉（实测崩过一次）。
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod                                          # noqa: E402

DAY_NS = 86_400_000_000_000
# ⚠️ 窗口与最短历史必须从 RegimeConfig 读，不能在这里写 "90D" / 30。
# 写死了会让改 config 只影响主脚本、不影响本脚本 —— 那正是"死参数"的另一种形态。
WINDOW = f"{cfg_mod.REGIME.window_days}D"
MIN_HISTORY_NS = cfg_mod.REGIME.min_history_days * DAY_NS
# ⚠️ 这三个必须【从 RegimeConfig 读】，不能在本地写一份。
# 本地写一份会让 config 里的字段成为死字段 —— snapshot() 把它写进 REPRODUCE.md
# 冒充设计参数，但改它其实不会有任何效果。Phase 1 的 config 就是因为这个删掉了
# parquet_compression / event_lookbacks / refresh_months。
QUANTILES = tuple(cfg_mod.REGIME.quantiles)
Z_THRESHOLDS = tuple(cfg_mod.REGIME.z_thresholds)
PRIMARY_Q = cfg_mod.REGIME.quantile_main
REGIMES = ("R1", "R2", "R3", "R4")
SUB = {"R1": "price up + OI up", "R2": "price up + OI down",
       "R3": "price down + OI up", "R4": "price down + OI down"}
VALID_REASONS = ("ok", "warmup")
NL = chr(10)

T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.0f}s] {msg}", flush=True)


def q_by_time(s: pd.Series, q: float, age_ok: np.ndarray, window: str | None = None) -> np.ndarray:
    window = window or WINDOW
    """滚动分位 + 时间判据的最短历史。与 regime_generator.rolling_q_by_time 同算法。"""
    r = s.rolling(window).quantile(q).to_numpy()
    return np.where(age_ok, r, np.nan)


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 2 —— 阈值稳健性（表 5 + 图）")
    ap.add_argument("--out-root", required=True, help="产出根目录（必填）")
    ap.add_argument("--in-root", default=None, help="读取位置（默认 = --out-root）")
    ap.add_argument("--freqs", nargs="+", default=None, help="只跑这些频率")
    args = ap.parse_args()

    out_root = Path(args.out_root).resolve()
    in_root = Path(args.in_root or args.out_root).resolve()
    lab_root = in_root / "05_regime" / "regime_labels"
    out_dir = out_root / "05_regime"
    if not lab_root.exists():
        raise SystemExit(f"找不到标签表：{lab_root}（先跑 regime_generator.py）")
    # 频率顺序：1h 是主频率，1d 是 note 点名的稳健性对照 —— 不要用目录名的字母序
    # （那会得到 1d, 1h, 4h, 8h，把主频率塞进角落）
    FREQ_ORDER = ("1h", "4h", "8h", "1d")
    have = {p.name.split("=")[1] for p in lab_root.glob("freq=*")}
    freqs = args.freqs or [f for f in FREQ_ORDER if f in have]

    log("=" * 78)
    log("build_sensitivity   Phase 2 · 阈值稳健性（L1：标签层）")
    log(f"  分位扫描 : {', '.join(f'p{int(q*100)}' for q in QUANTILES)}")
    log(f"  z 门槛   : {', '.join(f'{z:.2f}' for z in Z_THRESHOLDS)}")
    log(f"  频率     : {', '.join(freqs)}")
    log("=" * 78)

    rows: list[dict] = []
    max_dev = 0.0                    # 自检：重算 p70 与标签表 price_thr 的最大相对偏差

    for fq in freqs:
        t0 = time.time()
        files = sorted((lab_root / f"freq={fq}").rglob("*.parquet"))
        d = pd.concat([pq.read_table(str(p), partitioning=None,
                                     columns=["symbol", "ts_end", "price_change", "oi_change",
                                              "excl_reason", "price_thr", "oi_thr"]).to_pandas()
                       for p in files], ignore_index=True)
        d = d.sort_values(["symbol", "ts_end"], kind="stable")
        sym = d["symbol"].to_numpy()
        te = pd.DatetimeIndex(d["ts_end"])
        pc = d["price_change"].to_numpy(dtype="float64")
        oc = d["oi_change"].to_numpy(dtype="float64")
        st_p = d["price_thr"].to_numpy(dtype="float64")
        st_o = d["oi_thr"].to_numpy(dtype="float64")
        valid = np.isin(d["excl_reason"].to_numpy(), VALID_REASONS)
        n_valid = int(valid.sum())
        del d

        code = np.full(len(pc), -1, dtype=np.int8)
        code[(pc > 0) & (oc > 0)] = 0
        code[(pc > 0) & (oc < 0)] = 1
        code[(pc < 0) & (oc > 0)] = 2
        code[(pc < 0) & (oc < 0)] = 3

        Nq = np.zeros(len(QUANTILES), dtype=np.int64)
        Cq = np.zeros((len(QUANTILES), 4), dtype=np.int64)
        M = np.full(len(pc), np.nan)
        starts = np.flatnonzero(np.r_[True, sym[1:] != sym[:-1]])
        bounds = np.r_[starts, len(sym)]

        for a, b in zip(bounds[:-1], bounds[1:]):
            idx = pd.DatetimeIndex(te[a:b])
            age = (idx.asi8 - idx.asi8[0]) >= MIN_HISTORY_NS
            ap_ = pd.Series(np.abs(pc[a:b]), index=idx)
            ao_ = pd.Series(np.abs(oc[a:b]), index=idx)
            vp = np.abs(pc[a:b]); vo = np.abs(oc[a:b])
            for j, q in enumerate(QUANTILES):
                tp = q_by_time(ap_, q, age); to = q_by_time(ao_, q, age)
                if q == PRIMARY_Q:
                    # ---- 自检：重算的 p70 必须与标签表存的阈值一致 ----
                    for rec, sto in ((tp, st_p[a:b]), (to, st_o[a:b])):
                        m = np.isfinite(rec) & np.isfinite(sto)
                        if m.any():
                            rel = np.abs(rec[m] - sto[m]) / np.maximum(np.abs(sto[m]), 1e-300)
                            max_dev = max(max_dev, float(rel.max()))
                # lab = 两条轴都过阈值（与 regime_generator 的 lab 同义）
                lab = (vp > tp) & (vo > to)
                Nq[j] += int(lab.sum())
                for r in range(4):
                    Cq[j, r] += int((lab & (code[a:b] == r)).sum())
            sp = pd.Series(pc[a:b], index=idx).rolling(WINDOW).std().to_numpy()
            so = pd.Series(oc[a:b], index=idx).rolling(WINDOW).std().to_numpy()
            v = age & np.isfinite(sp) & (sp > 0) & np.isfinite(so) & (so > 0)
            M[a:b][v] = np.minimum(vp[v] / sp[v], vo[v] / so[v])

        fin = np.isfinite(M)
        n_z_ok = int(fin.sum())
        m_asc = np.sort(M[fin])
        order = np.argsort(-M[fin], kind="stable")
        c_desc = code[fin][order]

        def z_counts(thr: float) -> tuple[int, np.ndarray]:
            """|z| > thr（严格大于）—— 用于 note 点名的固定门槛。"""
            k = int(len(m_asc) - np.searchsorted(m_asc, thr, side="right"))
            return k, np.bincount(c_desc[:k], minlength=4)

        def z_top(k: int) -> np.ndarray:
            """按 m 取前 k 个 —— 配对用，精确等于分位法在 q 上的标注量。"""
            return np.bincount(c_desc[:int(k)], minlength=4)

        # ---- 配对：z*(q) = m 降序第 N_q 个（闭式解，一次排序） ----
        m_desc = M[fin][order]
        # 前提：分位法标注集 ⊆ m 可用集，所以 Nq[j] <= len(m_desc)。两者用同一个 age 掩码；
        # σ 只在窗口内非空点 < 2 时才是 NaN，而 age >= 30 天时至少 30 个点。故必然成立。
        zstar = [float(m_desc[Nq[j] - 1]) for j in range(len(QUANTILES))]

        # ---- 表 5 的行 ----
        for j, q in enumerate(QUANTILES):
            nl = int(Nq[j])
            r = dict(method="percentile", threshold=f"p{int(q*100)}", freq=fq,
                     n_valid=n_valid, n_labelled=nl,
                     labelled_share_of_valid=nl / n_valid,
                     undefined_share_of_valid=1 - nl / n_valid,
                     z_equiv=round(zstar[j], 4))
            for k, rn in enumerate(REGIMES):
                r[f"n_{rn}"] = int(Cq[j, k])
                r[f"{rn}_share_of_labelled"] = Cq[j, k] / nl if nl else np.nan
                r[f"{rn}_share_of_valid"] = Cq[j, k] / n_valid if n_valid else np.nan
            rows.append(r)
            # ---- 配对行：**同样标注量**下的 z 法。§6.4 要的"配对照"就在这一行 ----
            cm = z_top(nl)
            rm = dict(method="zscore_matched", threshold=f"z*={zstar[j]:.4f}", freq=fq,
                      n_valid=n_valid, n_labelled=nl,
                      labelled_share_of_valid=nl / n_valid,
                      undefined_share_of_valid=1 - nl / n_valid,
                      z_equiv=round(zstar[j], 4))
            for k, rn in enumerate(REGIMES):
                rm[f"n_{rn}"] = int(cm[k])
                rm[f"{rn}_share_of_labelled"] = cm[k] / nl if nl else np.nan
                rm[f"{rn}_share_of_valid"] = cm[k] / n_valid if n_valid else np.nan
            rows.append(rm)
        for zt in Z_THRESHOLDS:
            nl, cc = z_counts(zt)
            r = dict(method="zscore", threshold=f"|z|>{zt:.2f}", freq=fq,
                     n_valid=n_valid, n_labelled=nl,
                     labelled_share_of_valid=nl / n_valid,
                     undefined_share_of_valid=1 - nl / n_valid,
                     z_equiv=np.nan)
            for k, rn in enumerate(REGIMES):
                r[f"n_{rn}"] = int(cc[k])
                r[f"{rn}_share_of_labelled"] = cc[k] / nl if nl else np.nan
                r[f"{rn}_share_of_valid"] = cc[k] / n_valid if n_valid else np.nan
            rows.append(r)

        log(f"  {fq}: {len(pc):,} 行 · 有效 {n_valid:,} · m 可用 {n_z_ok:,} · "
            f"z* = {', '.join(f'{z:.3f}' for z in zstar)}  ({time.time() - t0:.0f}s)")
        del pc, oc, st_p, st_o, M, m_asc, order, c_desc, code

    # ---- 自检结果 ----
    log(f"  自检：重算 p70 与标签表 price_thr/oi_thr 的最大相对偏差 = {max_dev:.3e}")
    if not (max_dev < 1e-9):
        log("  ⚠️ 相对偏差过大 —— 重算路径与主脚本不一致，后面的分位结果不可信")
        return 3

    T = pd.DataFrame(rows)
    T = T[["method", "threshold", "freq", "n_valid", "n_labelled", "labelled_share_of_valid",
           "undefined_share_of_valid"] + [f"n_{r}" for r in REGIMES]
          + [f"{r}_share_of_labelled" for r in REGIMES]
          + [f"{r}_share_of_valid" for r in REGIMES] + ["z_equiv"]]
    # ---- 回归自检：p70 那一列必须复现 §7 / §1.3 的必报数字（1h）----
    # 这几个基准值是人工确认过的。数据若被【合法】重建，它们应当不变；变了就说明
    # 表和图不再同源，必须人工确认后再更新这里 —— 所以是回归测试，不是断言。
    REF_1H = {"n_valid": 7_214_627, "n_labelled": 923_235,
              "R1": 0.0370, "R2": 0.0256, "R3": 0.0227, "R4": 0.0426}
    if "1h" in freqs:
        r70 = T[(T.method == "percentile") & (T.freq == "1h") & (T.threshold == "p70")].iloc[0]
        devs = []
        if int(r70["n_valid"]) != REF_1H["n_valid"]:
            devs.append(f"n_valid {int(r70['n_valid']):,} != {REF_1H['n_valid']:,}")
        if int(r70["n_labelled"]) != REF_1H["n_labelled"]:
            devs.append(f"n_labelled {int(r70['n_labelled']):,} != {REF_1H['n_labelled']:,}")
        for rn in REGIMES:
            got_, exp_ = float(r70[f"{rn}_share_of_valid"]), REF_1H[rn]
            if abs(got_ - exp_) > 5e-5:
                devs.append(f"{rn} {got_:.4%} != {exp_:.4%}")
        log("  回归自检（1h p70 == §7 必报数字）：" + ("一致 ✓" if not devs else "⚠️ " + "; ".join(devs)))
        if devs:
            log("  ⚠️ 与 §7 基准不符 —— 若数据被合法重建，人工确认后再更新 REF_1H")
            return 4

    (out_dir / "tables").mkdir(parents=True, exist_ok=True)
    (out_dir / "figures").mkdir(parents=True, exist_ok=True)
    T.to_parquet(str(out_dir / "tables" / "threshold_sensitivity.parquet"), index=False)
    T.to_csv(str(out_dir / "tables" / "threshold_sensitivity.csv"),
             index=False, encoding="utf-8-sig")
    log(f"  表 threshold_sensitivity: {len(T)} 行 x {len(T.columns)} 列")

    # ---- 图：两行 × 四频率 ----
    #   上行 = 各 regime 占【全部有效观测】的比重  → 看"样本量效应"（阈值在干它该干的事）
    #   下行 = 各 regime 占【该档标注样本】的比重  → 看"组成"，四条线相加 = 100%
    # 下行才是"阈值对标签占比影响不大"的直接证据；上行只是把总量效应摆出来做对照。
    QS = [f"p{int(q * 100)}" for q in QUANTILES]              # p55..p80，从左到右变严
    colors = {"R1": "#1f6fb4", "R2": "#2e9e5b", "R3": "#d68910", "R4": "#c0392b"}
    fig, axes = plt.subplots(2, len(freqs), figsize=(15.4, 7.6), squeeze=False)
    fig.suptitle("Threshold sensitivity — how the four labels move as the threshold goes p55 -> p80",
                 fontsize=13.5, y=0.988)
    fig.text(0.5, 0.922,
             "TOP row: each regime as a share of ALL valid observations (dominated by the sample-size effect).\n"
             "BOTTOM row: each regime as a share WITHIN the labelled set — the mix itself; these four sum to 100% "
             "at every point. Each label's largest move over the six thresholds is printed inside the panel.",
             ha="center", va="top", fontsize=9.5, color="#333333", linespacing=1.5)
    for col, fq in enumerate(freqs):
        pp = T[(T.method == "percentile") & (T.freq == fq)].set_index("threshold").reindex(QS)
        cnt = pp[[f"n_{r}" for r in REGIMES]].to_numpy(float)
        nv = float(pp["n_valid"].iloc[0])
        sh_all = cnt / nv
        sh_lab = cnt / cnt.sum(axis=1, keepdims=True)
        x = np.arange(len(QS))
        for row, (sh, ylab) in enumerate([(sh_all, "share of all valid obs"),
                                          (sh_lab, "share within labelled set")]):
            ax = axes[row][col]
            for k, rn in enumerate(REGIMES):
                ax.plot(x, sh[:, k], "o-", color=colors[rn], lw=1.9, ms=5, zorder=3)
            if row == 0:
                ax.plot(x, sh.sum(axis=1), color="#888888", lw=1.4, ls="--", zorder=2)
                ax.set_ylim(0, 0.26)
                ax.set_title(f"{fq}   labelling rate {sh.sum(axis=1)[0]:.1%} -> {sh.sum(axis=1)[-1]:.1%}",
                             fontsize=9, loc="left")
            else:
                ax.set_ylim(0, 0.48)
                pp_range = {rn: (sh[:, k].max() - sh[:, k].min()) * 100 for k, rn in enumerate(REGIMES)}
                worst = max(pp_range, key=pp_range.get)
                ax.set_title(f"{fq}   max change {pp_range[worst]:.1f}pp ({worst})", fontsize=9, loc="left")
                # 每条线的变化幅度摆在左上角（右端会互相压住）。用户要的就是这四行数字。
                for j, rn in enumerate(REGIMES):
                    ax.text(0.025, 0.978 - 0.072 * j,
                            f"{rn}  {pp_range[rn]:>4.1f} pp", transform=ax.transAxes,
                            va="top", ha="left", fontsize=7.6, color=colors[rn])
                ax.set_xlim(-0.3, len(QS) - 0.7)
            if row == 0:
                ax.set_xlim(-0.3, len(QS) - 0.7)
            ax.set_xticks(x); ax.set_xticklabels(QS, fontsize=8.5)
            ax.grid(alpha=.22)
            ax.set_ylabel(ylab, fontsize=8)
            if row == 1:
                ax.set_xlabel("threshold   (looser -> stricter)", fontsize=8)
        log(f"  {fq} 组成（占标注样本）："
            + " | ".join(f"{rn} " + " ".join(f"{v*100:.1f}" for v in sh_lab[:, k])
                         for k, rn in enumerate(REGIMES)))
    handles = [Line2D([], [], color=colors[r], marker="o", lw=1.9, label=f"{r}  {SUB[r]}")
               for r in REGIMES]
    handles.append(Line2D([], [], color="#888888", lw=1.4, ls="--", label="labelling rate (top row only)"))
    fig.legend(handles=handles, fontsize=8.5, ncol=5, loc="lower center",
               bbox_to_anchor=(0.5, 0.004), frameon=False)
    plt.tight_layout(rect=(0, 0.048, 1, 0.872))
    plt.savefig(str(out_dir / "figures" / "threshold_sensitivity.png"), dpi=135)
    plt.close(fig)
    log("  图 threshold_sensitivity.png（上：占全部观测 / 下：占标注样本）")

    # ---- 刷新校验和 ----
    lines = []
    for p in sorted(out_dir.rglob("*")):
        if p.is_file() and p.name != "checksums.sha256":
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            lines.append(f"{h.hexdigest()}  {p.relative_to(out_dir).as_posix()}")
    (out_dir / "checksums.sha256").write_text(NL.join(lines) + NL,
                                              encoding="utf-8", newline=NL)
    log(f"  checksums.sha256 刷新（{len(lines):,} 个文件）")
    log(f"  总耗时 {time.time() - T_START:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
