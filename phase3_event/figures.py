"""Phase 3 · figures —— 从 table 生成图（不硬编码任何数字）

规则（GUIDANCE §四）：**画被检验的那个量，不是背景量。**

    f1a 实验 1：Δ 收益均值 + 95% CI
    f1b 实验 2：中位数差（**无误差棒**——不检验）
    f1c 实验 3：比基准高百分之多少 + 95% CI
    f2  实验 5–7 的池起来价差 + 实验 9 的三个 Δ
    f3  实验 13：各组收益水平（描述用，**不带误差棒**）
    f4  实验 12：事件路径（前后各 24h，带 95% CI）
    f5  实验 11：路径风险 MFE vs MAE（描述用，**不带误差棒**）
    f6  实验 4：续势 / 反转比例（描述用，**不带误差棒**）
    f7  实验 1b：价格 × OI 的 2×2 四个简单效应 + 交互（95% CI）
    f8  实验 15：IC 衰减（Newey-West 95% CI，本节不判定）
"""
from __future__ import annotations

import re
import os
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TBL = ROOT / "data/06_event_study/tables/freq=1h"
DECK = os.environ.get("P3_DECK") == "1"          # 演示版：不画下方数据表，输出到 figures_deck/
FIG = (ROOT / "data/06_event_study/figures_deck") if DECK else (ROOT / "data/06_event_study/figures")
DPI = 200
CELLS = ("R1", "R2", "R3", "R4")
COLORS = {"R1": "#2b6cb0", "R2": "#2f855a", "R3": "#c05621", "R4": "#b83280"}
# 旧版本留下的文件名，必须删掉，否则用户会打开旧图以为"图没变"（旧图必须删）
STALE = (
    "f16_bycount.png",
    "f05_09_baselines.png",
    "f15_ic_decay.png",
    "f02_median_table.png",
    "f02_median_return.png",
    "f10b_volatility_level.png",
    "f10a_return_level.png",
    "f10_cell_profile.png",
    "f1a_mean_return.png",
    "f7_factor_2x2.png",
    "f1b_median_return.png",
    "f1c_volatility.png",
    "f6_cont_rev.png",
    "f2_baselines.png",
    "f5_path_risk.png",
    "f4_event_path.png",
    "f3_levels.png",
    "f10_by_symbol.png",
    "f11_by_state.png",
    "f8_ic_decay.png",
    "f9_bycount.png",
    "f4_ic_decay.png",
    "f8_factor_2x2.png",
    "f7_cont_rev.png",
    "f6_path_risk.png",
    "f5_event_path.png",
    "f9_factor_2x2.png",
    "f8_cont_rev.png",
    "f7_path_risk.png",
    "f6_event_path.png",
    "f1d_reversal_slope.png",
    "f5_decile_match.png","f2_five_spreads.png",)


def read_table(name: str) -> pd.DataFrame:
    """读表：优先 parquet，没有 pyarrow 就退回同名的 CSV。"""
    pq, csv = TBL / f"{name}.parquet", TBL / f"{name}.csv"
    try:
        return pd.read_parquet(pq)
    except Exception:
        if not csv.exists():
            raise SystemExit(f"找不到 {pq}，也没有 {csv}")
        return pd.read_csv(csv)


GROUP_TINTS = ("#f7fafc", "#eaf0f6")      # 相邻组交替；同组同色


def _row_tints(rows) -> list:
    """按第一列的分组标签给每行定一个底色：同一组用同一种底色，相邻组交替。"""
    out, cur, idx, prev = [], None, 0, None
    for r in rows:
        lbl = str(r[0])
        # 分组键 = 第一列去掉数字/期限后的前缀（"R1  h=4" → "R1"；"Price only" → "Price only"）
        key = re.split(r"[\s（(]", lbl.strip(), maxsplit=1)[0]
        if key != cur:
            if cur is not None:
                idx += 1
            cur = key
        out.append(GROUP_TINTS[idx % 2])
    return out


def style_table(ax, rows, header, fs=6.4):
    """统一风格的表格：表头灰底加粗，同组行同色，相邻组交替。"""
    ax.axis("off")
    tb = ax.table(cellText=rows, colLabels=header, cellLoc="center",
                  bbox=[0.0, 0.0, 1.0, 1.0])
    tb.auto_set_font_size(False)
    tb.set_fontsize(fs)
    tints = _row_tints(rows)
    for (r, c), cell in tb.get_celld().items():
        cell.set_linewidth(0.4)
        cell.set_edgecolor("#cbd5e0")
        if r == 0:
            cell.set_facecolor("#dde5ee")
            cell.set_text_props(weight="bold")
        else:
            cell.set_facecolor(tints[r - 1])
    return tb


def _attach_table(fig, header, rows, title=None, fs=6.4):
    """在图的**下方**加一条数据表（上图下表格）。

    画布按行数加高，主图压到上半部，表放新增的下半部——
    这样不会挤掉原有的坐标轴标签和图注。
    """
    w, h = fig.get_size_inches()
    extra = 0.34 + 0.30 * (len(rows) + 1)
    fig.set_size_inches(w, h + extra)
    band = extra / (h + extra)
    fig.subplots_adjust(bottom=band + 0.10)           # 给底部子图的 x 轴标签留位
    ax = fig.add_axes([0.045, 0.075, 0.91, max(band - 0.09, 0.05)])
    style_table(ax, rows, header, fs=fs)
    if title:
        ax.text(0.0, 1.03, title, transform=ax.transAxes, fontsize=6.8,
                ha="left", va="bottom", color="#2d3748")


def save(fig, name, table=None):
    """table=(header, rows[, title]) → 在图下方附一张数据表（上图下表格）。"""
    if table and not DECK:
        try:
            _attach_table(fig, table[0], table[1], table[2] if len(table) > 2 else None)
        except Exception as exc:                      # 表画不出来也不能影响出图
            print(f"    [warn] {name} 的表没画上：{exc}")
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / name, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


def lane_panel(sub: pd.DataFrame, hs, title, ylab, color, *, scale=1e4, unit="bp",
               transform=None, show_ci=True, annotate=True, title_size=9.5):
    """一条 lane：每个前向期一个点 + 95% CI，实心 = |t| > 1.96。"""
    ax = plt.gca()
    sub = sub.set_index("h").reindex(hs)
    e = sub["estimate"].to_numpy("float64")
    lo = sub["ci_lo"].to_numpy("float64")
    hi = sub["ci_hi"].to_numpy("float64")
    t = sub["t"].to_numpy("float64")
    if transform is not None:
        e, lo, hi = (transform(v) for v in (e, lo, hi))
    e, lo, hi = e * scale, lo * scale, hi * scale
    x = np.arange(len(hs))
    ok = np.isfinite(e)
    sig = np.isfinite(t) & (np.abs(t) > 1.96)
    if show_ci:
        ax.errorbar(x[ok], e[ok], yerr=[e[ok] - lo[ok], hi[ok] - e[ok]], fmt="none",
                    ecolor=color, elinewidth=1.1, capsize=3, capthick=1.1, zorder=2)
    for k in np.flatnonzero(ok):
        ax.plot(x[k], e[k], "o", ms=5.2, color=color, zorder=3,
                mfc=color if sig[k] else "white", mew=1.2)
    ax.axhline(0.0, color="0.35", lw=0.9, zorder=1)
    if annotate:
        for k in np.flatnonzero(ok):
            up = e[k] >= 0
            # 标签放在区间的外面，不要压在误差棒上
            ypos = max(e[k], hi[k]) if up else min(e[k], lo[k])
            ax.annotate(f"{e[k]:+.2f}\nt {t[k]:+.2f}", (x[k], ypos),
                        textcoords="offset points", xytext=(0, 5 if up else -5),
                        ha="center", va="bottom" if up else "top",
                        fontsize=6.2, color=color, linespacing=1.15)
    ax.grid(axis="y", lw=0.3, alpha=0.4)
    ax.set_title(title, fontsize=title_size, loc="left", pad=2)
    ax.set_ylabel(ylab, fontsize=8.5)
    ax.tick_params(labelsize=7)
    ax.margins(y=0.34)
    # 标注写在区间外面，会比数据高/低一点——给它留出上方的空白，别被裁掉
    y0, y1 = ax.get_ylim()
    ax.set_ylim(y0, y1 + 0.20 * (y1 - y0))
    return ax


def lane_figure(rows, hs, suptitle, foot, unit, figsize=(7.4, 7.2), **kw):
    """rows: [(lane 名, sub DataFrame, 颜色)]，从上到下排列。"""
    fig, axes = plt.subplots(len(rows), 1, figsize=figsize, sharex=True)
    if len(rows) == 1:
        axes = [axes]
    for ax, (nm, sub, color) in zip(axes, rows):
        plt.sca(ax)
        lane_panel(sub, hs, nm, unit, color, **kw)
    axes[-1].set_xticks(np.arange(len(hs)))
    axes[-1].set_xticklabels([f"{h}h" for h in hs], fontsize=8)
    axes[-1].set_xlabel("forward horizon", fontsize=8.5)
    fig.suptitle(suptitle, fontsize=11, y=0.995)
    fig.text(0.5, 0.005, foot, ha="center", fontsize=7.0, color="0.35")
    fig.tight_layout(rect=(0, 0.02, 1, 0.985))
    return fig


def main() -> int:
    # 旧版本留下的文件必须删掉，否则会打开旧图误以为"图没变"
    for _old in STALE:
        _fp = FIG / _old
        if _fp.exists():
            _fp.unlink()
            print(f"  删除旧图 {_old}", flush=True)

    d = read_table("exp1_4")
    e59 = read_table("exp5_9")
    ep = read_table("event_path")
    hs = sorted(int(v) for v in d["h"].dropna().unique())

    ci_foot = ("error bars = 95% CI (two-way clustered on contract + month);  "
               "filled marker = |t| > 1.96;  labels show the estimate and its t.")

    def _f_bp(row, scale=1e4, suffix="bp"):
        """一行 → '+2.51bp (+3.41)'；没有 t 的列只给数值。"""
        e = float(row["estimate"]) * scale
        if "t" not in row or not np.isfinite(row["t"]):
            return f"{e:+.2f}{suffix}"
        return f"{e:+.2f}{suffix} ({float(row['t']):+.2f})"

    def tab_lane(exp, *, pct=False, only_est=False, title=None):
        """把某个 experiment 的 4 格 × 4 期限排成「上图下表」用的表。"""
        sub = d[d["experiment"] == exp]
        rows = []
        for c in CELLS:
            s = sub[sub["cell"] == c].set_index("h")
            cells = []
            for h in hs:
                if h not in s.index:
                    cells.append("—")
                    continue
                e = float(s.loc[h, "estimate"])
                v = (f"{(np.exp(e) - 1.0) * 100.0:+.2f}%" if pct else f"{e * 1e4:+.2f}bp")
                cells.append(v if only_est else f"{v} ({float(s.loc[h, 't']):+.2f})")
            rows.append([c] + cells)
        return (["state"] + [f"{h}h" for h in hs], rows, title)

    def rows_of(exp):
        return [(c, d[(d["experiment"] == exp) & (d["cell"] == c)], COLORS[c]) for c in CELLS]

    # ---- Fig 1 平均收益 ----
    save(lane_figure(rows_of("1 收益·均值"), hs,
                     "Fig 1 · Mean forward return: each state vs the price-only benchmark",
                     ci_foot, "Δ excess return (bp)", figsize=(7.4, 7.6)),
         "f01_mean_return.png", table=tab_lane("1 收益·均值", title="estimate (t)"))

    if not DECK:          # Fig 2 本身是两张表，演示版用 pptx 原生表格代替
        # ---- Fig 2 均值表 + 中位数表（两张表，一张图）----
        _mean = d[d["experiment"] == "1 收益·均值"]
        _med = d[d["experiment"] == "2 收益·中位数"]

        def _tbl(ax, rows, header, fs=8.2):
            style_table(ax, rows, header, fs=fs)

        fig = plt.figure(figsize=(8.6, 5.4))
        fig.suptitle("Fig 2 · Mean vs median forward return: is the mean driven by a tail?",
                     fontsize=10.5, y=0.975)
        ax1 = fig.add_axes([0.07, 0.60, 0.86, 0.22])
        _rows = []
        for c in CELLS:
            s1 = _mean[_mean["cell"] == c].set_index("h")
            _rows.append([c] + [f"{float(s1.loc[h, 'estimate']) * 1e4:+.2f}bp ({float(s1.loc[h, 't']):+.2f})"
                                for h in hs])
        _tbl(ax1, _rows, ["state"] + [f"{h}h" for h in hs])
        ax1.set_title("mean Δ (bp) with t   —   experiment 1: FE-adjusted, vs dummy=0   [tested]",
                      fontsize=8.4, loc="left", pad=4)

        ax2 = fig.add_axes([0.07, 0.17, 0.86, 0.22])
        _rows = []
        for c in CELLS:
            s2 = _med[_med["cell"] == c].set_index("h")
            _rows.append([c] + [f"{float(s2.loc[h, 'estimate']) * 1e4:+.2f}bp  "
                                f"({float(s2.loc[h, 'share_negative']):.0%})" for h in hs])
        _tbl(ax2, _rows, ["state"] + [f"{h}h" for h in hs])
        ax2.set_title("median Δ (bp), bracket = share of contracts negative   —   experiment 2: "
                      "no FE, no test", fontsize=8.4, loc="left", pad=4)

        fig.text(0.5, 0.045, "Same benchmark in both tables: the other same-direction rows.\n"
                 "Mean is positive for R1/R4 at long horizons while the median is deeply negative — "
                 "the mean advantage comes from a right tail, not from the typical event.",
                 ha="center", fontsize=7.2, color="#4a5568")
        save(fig, "f02_mean_vs_median.png")

    # ---- Fig 3 波动（转成百分比）----
    def pct(v):
        return (np.exp(v) - 1.0) * 100.0

    save(lane_figure(rows_of("3 波动"), hs,
                     "Fig 3 · Realised volatility: how much higher than the benchmark",
                     ci_foot + "  The 1h column is the size of a one-bar move, not volatility.",
                     "% higher than benchmark", figsize=(7.4, 7.6),
                     scale=1.0, transform=pct),
         "f03_volatility.png",
         table=tab_lane("3 波动", pct=True, title="% higher than benchmark (t)"))

    # ---- Fig 5-7 + 四状态：四条多空价差，全部池化口径（实验 5 / 6 / 7 / 9 的水平）----
    singles = [("Price only", "5 纯价格", "#4a5568"),
               ("OI change only", "6 纯 OI", "#718096"),
               ("Funding only", "7 纯 funding", "#c53030"),
               ("Four-state  (R1 long / R4 short)", "四状态", "#2b6cb0")]
    fig, axes = plt.subplots(4, 1, figsize=(7.6, 7.2), sharex=True)
    for ax, (lbl, exp, col) in zip(axes, singles):
        plt.sca(ax)
        lane_panel(e59[e59["experiment"] == exp], hs, f"{lbl}  ·  pooled long-short spread",
                   "spread (bp)", col)
    axes[-1].set_xticks(np.arange(len(hs)))
    axes[-1].set_xticklabels([f"{h}h" for h in hs], fontsize=8)
    axes[-1].set_xlabel("forward horizon", fontsize=8.5)
    fig.suptitle("Fig 5-7 · Four long-short spreads on one estimator: three single-signal "
                 "baselines and the four-state label", fontsize=10.5, y=0.985)
    fig.text(0.5, 0.004, "Pooled spread = mean(long leg) − mean(short leg), no fixed effects, "
             "two-way clustered 95% CI.  Filled marker = |t| > 1.96.  Same estimator for all "
             "four panels; the daily version is Fig 9.", ha="center", fontsize=6.9, color="0.35")
    fig.tight_layout(rect=(0, 0.02, 1, 0.96))
    _rows = []
    for _lbl, _nm, _ in singles:
        _s = e59[e59["experiment"] == _nm].set_index("h")
        _rows.append([_lbl.split("(")[0].strip()] + [f"{float(_s.loc[h, 'estimate']) * 1e4:+.2f}bp "
                               f"({float(_s.loc[h, 't']):+.2f})" for h in hs])
    save(fig, "f05_07_singles.png",
         table=(["signal"] + [f"{h}h" for h in hs], _rows, "pooled spread, bp (t)"))

    # ---- Fig 9 四状态 vs 三条基线的同日差（只有 Δ，日频 NW）----
    diffs = [("Four-state − price  ·  same days", "四状态−纯价格", "#2b6cb0"),
             ("Four-state − OI  ·  same days", "四状态−纯 OI", "#2f855a"),
             ("Four-state − funding  ·  same days", "四状态−纯 funding", "#c05621")]
    fig, axes = plt.subplots(3, 1, figsize=(7.6, 5.8), sharex=True)
    for ax, (lbl, cell, col) in zip(axes, diffs):
        plt.sca(ax)
        lane_panel(e59[(e59["experiment"] == "9 Δ") & (e59["cell"] == cell)], hs,
                   lbl, "Δ spread (bp/period)", col)
    axes[-1].set_xticks(np.arange(len(hs)))
    axes[-1].set_xticklabels([f"{h}h" for h in hs], fontsize=8)
    axes[-1].set_xlabel("forward horizon", fontsize=8.5)
    fig.suptitle("Fig 9 · Four-state minus each single-signal baseline, same days (daily, "
                 "equal weight)", fontsize=10.5, y=0.985)
    fig.text(0.5, 0.004, "Δ = four-state minus that baseline on the same days.  Equal-weight daily "
             "spreads (each side >= 5 contracts), Newey-West lag 1.  The level of the four-state "
             "spread itself is the bottom panel of Fig 5-7.", ha="center", fontsize=6.9,
             color="0.35")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))
    _rows = []
    for _lbl, _nm, _ in diffs:
        _s = e59[(e59["experiment"] == "9 Δ") & (e59["cell"] == _nm)].set_index("h")
        _rows.append([_lbl.split("·")[0].strip()] +
                     [f"{float(_s.loc[h, 'estimate']) * 1e4:+.2f}bp ({float(_s.loc[h, 't']):+.2f})"
                      for h in hs])
    save(fig, "f09_four_state_vs_baselines.png",
         table=(["gap vs baseline"] + [f"{h}h" for h in hs], _rows,
                "same-day gap, bp (t) — daily, equal weight, Newey-West lag 1"))

    # ---- Fig 13 实验 13 水平：八条腿 × 四个期限（描述，无误差棒）----
    lv = e59[e59["experiment"] == "13 水平"]
    ORD = [("纯价格_long", "price long", "#2b6cb0"), ("纯价格_short", "price short", "#90cdf4"),
           ("纯 OI_long", "OI long", "#2f855a"), ("纯 OI_short", "OI short", "#9ae6b4"),
           ("纯 funding_long", "funding long", "#c05621"), ("纯 funding_short", "funding short", "#fbd38d"),
           ("四状态_long", "R1 (4-state long)", "#6b46c1"), ("四状态_short", "R4 (4-state short)", "#d6bcfa")]
    lvp = lv.pivot_table(index="cell", columns="h", values="estimate") * 1e4
    fig, axes = plt.subplots(1, 4, figsize=(13.0, 3.4), sharey=True)
    for ax, h in zip(axes, hs):
        vals = [float(lvp.loc[k, h]) if k in lvp.index else 0.0 for k, _, _ in ORD]
        ax.bar(np.arange(len(ORD)), vals, color=[c for _, _, c in ORD], width=0.72)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(np.arange(len(ORD)))
        ax.set_xticklabels(["price +", "price -", "OI +", "OI -",
                            "fund +", "fund -", "R1", "R4"], rotation=0, fontsize=6.8)
        ax.set_title(f"h = {int(h)}h", fontsize=9.5)
        ax.tick_params(labelsize=7)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
    axes[0].set_ylabel("mean excess return (bp)", fontsize=8.5)
    fig.suptitle("Fig 13 · Level of each single leg (long / short) at every horizon — "
                 "both legs of every spread, no test", fontsize=10.5)
    fig.text(0.5, 0.005, "Bar = mean market-neutral forward return of that leg (+ = long side, "
             "- = short side).  At 1h the legs "
             "straddle zero; from 8h on all eight are negative, which is why every long-short "
             "spread in Fig 5-9 is close to zero.",
             ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.92))
    _rows = []
    for k, lbl, _ in ORD:
        if k in lvp.index:
            _rows.append([lbl] + [f"{float(lvp.loc[k, h]):+.2f}bp" for h in hs])
    save(fig, "f13_levels.png",
         table=(["leg"] + [f"{h}h" for h in hs], _rows,
                "mean market-neutral forward return by leg — descriptive, no test"))

    # ---- Fig 12 事件路径（实验 12） ----
    fig, ax = plt.subplots(1, 2, figsize=(9.8, 3.6), sharey=True)
    eph = ep[ep["sample"] == "headline"]
    for c in CELLS:
        s = eph[eph["cell"] == c].sort_values("k")
        k = s["k"].to_numpy()
        m = s["mean_rel"].to_numpy() * 1e4
        lo = s["ci_lo_rel"].to_numpy() * 1e4
        hi = s["ci_hi_rel"].to_numpy() * 1e4
        for j, sel in enumerate((k <= 0, k >= 0)):
            ax[j].plot(k[sel], m[sel], lw=1.3, color=COLORS[c], label=c)
            ax[j].fill_between(k[sel], lo[sel], hi[sel], color=COLORS[c], alpha=0.15, lw=0)
    for j, (ttl, xl) in enumerate((("Before the event", "hours before (k)"),
                                   ("After the event", "hours after (k)"))):
        ax[j].axhline(0, color="k", lw=0.8)
        ax[j].axvline(0, color="k", ls="--", lw=0.8)
        ax[j].set_title(ttl, fontsize=9.5)
        ax[j].set_xlabel(xl, fontsize=8.5)
        ax[j].tick_params(labelsize=7)
        ax[j].grid(axis="y", lw=0.3, alpha=0.4)
    ax[0].set_ylabel("cumulative excess return (bp), relative to event", fontsize=8.5)
    ax[0].legend(fontsize=7.5, ncol=2, frameon=False)
    fig.suptitle("Fig 12 · Event path: cumulative excess return ±24 hours around the event "
                 "(bp, mean with 95% CI)", fontsize=10.5)
    fig.tight_layout()
    _ks = [-24, -4, 0, 4, 24]
    _rows = []
    for c in CELLS:
        _s = eph[eph["cell"] == c].set_index("k")
        _rows.append([c] + [f"{float(_s.loc[k, 'mean_rel']) * 1e4:+.1f}" if k in _s.index else "—"
                            for k in _ks])
    tbl4 = (["state"] + [f"k={k}" for k in _ks], _rows,
            "cumulative excess return (bp) relative to the event — descriptive, no test")
    save(fig, "f12_event_path.png", table=tbl4)

    # ---- Fig 8 安慰剂：真实值 vs 同合约随机时刻（实验 8）----
    plc = read_table("placebo")
    fig, axes = plt.subplots(1, 4, figsize=(12.6, 3.6), sharey=True)
    for ax, c in zip(axes, CELLS):
        s = plc[plc["cell"] == c].sort_values("h")
        xv = np.arange(len(s))
        lo = s["rnd_p5"].to_numpy("float64")
        hi = s["rnd_p95"].to_numpy("float64")
        ax.fill_between(xv, lo, hi, color="#a0aec0", alpha=0.35, lw=0, label="random p5-p95")
        ax.plot(xv, s["rnd_p50"].to_numpy("float64"), ls="--", lw=1.1, color="#718096",
                label="random median")
        act = s["actual"].to_numpy("float64")
        out = (act > hi) | (act < lo)
        ax.plot(xv, act, "-", lw=1.4, color=COLORS[c], label="actual (event)")
        ax.plot(xv[~out], act[~out], "o", ms=5.5, mfc="white", mec=COLORS[c], mew=1.6)
        ax.plot(xv[out], act[out], "o", ms=6.0, mfc=COLORS[c], mec=COLORS[c])
        for k in np.flatnonzero(out):
            pv = float(s["p_placebo"].to_numpy()[k])
            lab = f"p={pv:.3f}" if pv >= 0.002 else "p<0.002"   # 0 = 没抽到，读作分辨率先限
            ax.annotate(lab, (k, act[k]), textcoords="offset points", xytext=(0, 8),
                        fontsize=6.2, ha="center", color=COLORS[c])
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(xv)
        ax.set_xticklabels([f"{int(h)}h" for h in s["h"]], fontsize=8)
        ax.set_xlabel("forward horizon", fontsize=8.5)
        ax.set_title(c, fontsize=9.5)
        ax.tick_params(labelsize=7.5)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
    axes[0].set_ylabel("forward return (bp)", fontsize=8.5)
    axes[0].legend(fontsize=6.4, frameon=False, loc="lower left")
    fig.suptitle("Fig 8 · Placebo: event time vs random hours for the same contracts "
                 "(band = p5-p95 of 1,000 draws)", fontsize=10.5)
    fig.text(0.5, 0.005, "Solid line = the event's mean; shaded band = the same contracts at "
             "random hours.  Filled marker = outside the band.  p = two-sided empirical p from "
             "1,000 draws; \"p<0.002\" means no draw reached the actual value (resolution floor).", ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    _rows = []
    for c in CELLS:
        s = plc[plc["cell"] == c].set_index("h")
        _rows.append([c] + [f"{float(s.loc[h, 'actual']):+.2f} "
                            f"[{float(s.loc[h, 'rnd_p5']):+.2f},{float(s.loc[h, 'rnd_p95']):+.2f}]"
                            for h in hs])
    save(fig, "f08_placebo.png",
         table=(["state"] + [f"{h}h" for h in hs], _rows,
                "actual bp [random p5, p95] — visualise, do not re-test"))

    # ---- Fig 10 每格的基本面：收益（中性 / 原始）+ 波动（实验 10，描述）----
    _dc = read_table("descriptive_core")
    if "sample" in _dc:
        _dc = _dc[_dc["sample"] == "headline"]
    core10 = _dc.set_index(["cell", "h"])
    x = np.arange(len(hs))
    fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.4))
    PANELS = (
        (axes[0], "mean_excess", 1e4, "return: vs market (market-neutral)", "forward return (bp)"),
        (axes[1], "mean_raw", 1e4, "return: raw price change", "forward return (bp)"),
        (axes[2], "mean_rv", 1e2, "volatility level (non-annualised)", "mean realised volatility (%)"),
    )
    for ax, col, scale, ttl, ylab in PANELS:
        for c in CELLS:
            ax.plot(x, [float(core10.loc[(c, h), col]) * scale for h in hs],
                    "o-", color=COLORS[c], ms=4.0, lw=1.5, label=c)
        if col != "mean_rv":
            ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{h}h" for h in hs], fontsize=8)
        ax.set_xlabel("forward horizon", fontsize=8.5)
        ax.set_ylabel(ylab, fontsize=8.5)
        ax.set_title(ttl, fontsize=9)
        ax.tick_params(labelsize=7.5)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
    axes[0].legend(fontsize=7.5, frameon=False, ncol=2)
    fig.suptitle("Fig 10 · What each regime looks like: return vs market, raw price move, "
                 "and volatility (descriptive — no test)", fontsize=10.5)
    fig.text(0.5, 0.005, "Cell means over all R1-R4 events, no FE, no benchmark.  The middle panel "
             "can rise while the left one falls: the coins rose but lagged the market.",
             ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))
    _rows = []
    for c in CELLS:
        n1 = int(core10.loc[(c, hs[0]), "n"])
        _rows.append([f"{c}  return, vs market (n={n1:,})"] +
                     [f"{float(core10.loc[(c, h), 'mean_excess']) * 1e4:+.2f}bp" for h in hs])
        _rows.append([f"{c}  return, raw price"] +
                     [f"{float(core10.loc[(c, h), 'mean_raw']) * 1e4:+.2f}bp" for h in hs])
        _rows.append([f"{c}  volatility"] +
                     [f"{float(core10.loc[(c, h), 'mean_rv']) * 1e2:.2f}%" for h in hs])
    save(fig, "f10_levels.png",
         table=(["state / metric"] + [f"{h}h" for h in hs], _rows,
                "cell means — descriptive, no test"))

    # ---- Fig 11 路径风险（实验 11）：MFE vs MAE ----
    dp = read_table("descriptive_path")
    dph = dp[dp["sample"] == "headline"] if "sample" in dp else dp
    fig, axes = plt.subplots(1, 1, figsize=(6.6, 4.6))
    axes = [axes]
    for ax, (xcol, ycol, ttl) in zip(axes, (
            ("mfe_p50", "mae_p50", "median (p50) excursion — the typical path"),)):
        for i, c in enumerate(CELLS):
            s = dph[dph["cell"] == c].sort_values("h")
            xv = s[xcol].to_numpy() * 100.0
            yv = s[ycol].to_numpy() * 100.0
            ax.plot(xv, yv, "o-", color=COLORS[c], ms=4.5, lw=0.8, label=c)
            # 四个状态在 h=1 几乎重合，所以按状态给不同方向的偏移，避免标签叠在一起
            dx, dy = ((5, 4), (6, -9), (-19, 4), (-20, -9))[i]
            for k, h in enumerate(s["h"].to_numpy()):
                ax.annotate(f"{int(h)}h", (xv[k], yv[k]), textcoords="offset points",
                            xytext=(dx, dy), fontsize=5.8, color=COLORS[c])
        vals = np.abs(np.r_[dph[xcol].to_numpy(), dph[ycol].to_numpy()]) * 100.0
        lim = float(np.nanmax(vals)) * 1.25
        ax.plot([0, lim], [0, -lim], ls="--", lw=0.8, color="0.5")
        ax.axhline(0, color="0.3", lw=0.7)
        ax.axvline(0, color="0.3", lw=0.7)
        ax.set_xlim(0, lim)
        ax.set_ylim(-lim, 0)
        ax.set_xlabel("MFE — maximum favourable excursion (%)", fontsize=8.5)
        ax.set_ylabel("MAE — maximum adverse excursion (%)", fontsize=8.5)
        ax.set_title(ttl, fontsize=9.5)
        ax.tick_params(labelsize=7)
        ax.grid(lw=0.3, alpha=0.4)
        ax.legend(fontsize=7.5, frameon=False, loc="lower right")
    fig.suptitle("Fig 11 · Path risk by state: typical (p50) path "
                 "(descriptive — no test)",
                 fontsize=10.5)
    fig.text(0.5, -0.02,
             "Dashed line = y = −x (symmetric excursion).  Only medians are plotted: the "
             "unconditional mean is dominated by a few extreme paths (worst drawdown −382%), and a "
             "second panel cannot show the tail without mixing two different quantiles.",
             ha="center", fontsize=6.8, color="0.35")
    fig.tight_layout()
    _rows = []
    for c in CELLS:
        _s = dph[dph["cell"] == c].set_index("h")
        for met, col in (("MFE p50", "mfe_p50"), ("MAE p50", "mae_p50"), ("MDD p50", "mdd_p50")):
            _rows.append([f"{c}  {met}"] +
                         [f"{float(_s.loc[h, col]) * 100:+.2f}%" for h in hs])
    tbl5 = (["state / metric"] + [f"{h}h" for h in hs], _rows,
            "median (p50) excursion in % — typical path; p10/p90 quantiles live in descriptive_path.parquet")
    save(fig, "f11_path_risk.png", table=tbl5)

    # ---- Fig 4 反转概率：左 = 纯统计，右 = 相对基准的差（实验 4）----
    core = read_table("descriptive_core")
    core = core[core["sample"] == "headline"] if "sample" in core else core
    rv = read_table("rev_prob")

    def _tbl4(ax, rows, header, fs=7.0):
        style_table(ax, rows, header, fs=fs)

    fig = plt.figure(figsize=(10.8, 6.4))
    axd = fig.add_axes([0.055, 0.615, 0.40, 0.25])
    axb = fig.add_axes([0.545, 0.615, 0.40, 0.25])
    xv = np.arange(len(hs))
    for c in CELLS:
        sc = core[core["cell"] == c].set_index("h")
        axd.plot(xv, [float(sc.loc[h, "p_rev"]) * 100.0 for h in hs], "o-",
                 color=COLORS[c], ms=4.0, lw=1.5, label=c)
    axd.axhline(50, color="k", lw=0.8, ls=":")
    axd.set_title("descriptive: reversal rate (%)", fontsize=9.5)
    axd.set_ylabel("P(reversal) %", fontsize=8.5)
    axd.legend(fontsize=7.5, frameon=False, ncol=2)
    for c in CELLS:
        sb = rv[rv["cell"] == c].sort_values("h")
        est = sb["estimate"].to_numpy("float64") * 100.0
        se = sb["se"].to_numpy("float64") * 100.0
        sig = np.abs(sb["t"].to_numpy("float64")) > 1.96
        axb.errorbar(xv, est, yerr=1.96 * se, fmt="none", ecolor=COLORS[c], capsize=3, lw=1.0)
        axb.plot(xv, est, "-", lw=1.1, color=COLORS[c], alpha=0.75)
        axb.plot(xv[~sig], est[~sig], "o", ms=5, mfc="white", mec=COLORS[c], mew=1.5)
        axb.plot(xv[sig], est[sig], "o", ms=5.5, mfc=COLORS[c], mec=COLORS[c])
    axb.axhline(0, color="k", lw=0.8)
    axb.set_title("vs benchmark: delta reversal probability (pp, 95% CI)", fontsize=9.5)
    axb.set_ylabel("delta P(reversal), pp", fontsize=8.5)
    for ax in (axd, axb):
        ax.set_xticks(xv)
        ax.set_xticklabels([f"{h}h" for h in hs], fontsize=8)
        ax.set_xlabel("forward horizon", fontsize=8.5)
        ax.tick_params(labelsize=7.5)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
    fig.suptitle("Fig 4 · Reversal behaviour: the raw rate (left) and the tested gap "
                 "vs the same-direction benchmark (right)", fontsize=10.5)
    fig.text(0.5, 0.015, "Left is descriptive (no test, no FE).  Right is the LPM estimate with "
             "contract+month FE and two-way clustered SE; filled marker = |t| > 1.96.  "
             "Continuation = 1 - reversal - flat, and flat is only 0.2-0.9%.",
             ha="center", fontsize=6.8, color="#4a5568")

    _rows = []
    for c in CELLS:
        sc = core[core["cell"] == c].set_index("h")
        _rows.append([c] + [f"{float(sc.loc[h, 'p_rev']) * 100:.2f}%  "
                            f"({float(sc.loc[h, 'p_cont']) * 100:.2f}%)" for h in hs])
    if not DECK:          # 演示版不画图内表（改用 pptx 原生表格）
        ax1 = fig.add_axes([0.09, 0.245, 0.82, 0.155])
        _tbl4(ax1, _rows, ["state"] + [f"{h}h" for h in hs])
        ax1.set_title("reversal % (continuation % in brackets) — descriptive, no test",
                      fontsize=8.0, loc="left", pad=3)
        _rows = []
        for c in CELLS:
            sb = rv[rv["cell"] == c].set_index("h")
            _rows.append([c] + [f"{float(sb.loc[h, 'estimate']) * 100:+.2f}pp "
                                f"({float(sb.loc[h, 't']):+.2f})" for h in hs])
        ax2 = fig.add_axes([0.09, 0.055, 0.82, 0.155])
        _tbl4(ax2, _rows, ["state"] + [f"{h}h" for h in hs])
        ax2.set_title("delta vs same-direction benchmark (pp), with t — LPM + contract/month FE",
                      fontsize=8.0, loc="left", pad=3)

    save(fig, "f04_cont_rev.png")
    # ---- Fig 1b 2×2 因子（1b）：四个简单效应 + 交互 ----
    fb = read_table("exp1_4")
    fb = fb[fb["experiment"] == "1b 因子对比"]
    order = ["OI|价格上 (R1-R2)", "OI|价格下 (R3-R4)", "价格|OI增 (R1-R3)", "价格|OI减 (R2-R4)"]
    en = {order[0]: "OI | price up  (R1-R2)", order[1]: "OI | price down (R3-R4)",
          order[2]: "price | OI up  (R1-R3)", order[3]: "price | OI down (R2-R4)"}
    cols9 = ["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"]
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 4.0),
                             gridspec_kw={"width_ratios": (1.35, 1.0)})
    x = np.arange(len(hs))
    ax = axes[0]
    for k, nm in enumerate(order):
        s = fb[fb["cell"] == nm].set_index("h").reindex(hs)
        e_ = s["estimate"].to_numpy("float64") * 1e4
        lo = (s["estimate"] - 1.96 * s["se"]).to_numpy("float64") * 1e4
        hi = (s["estimate"] + 1.96 * s["se"]).to_numpy("float64") * 1e4
        ax.errorbar(x + (k - 1.5) * 0.11, e_, yerr=[e_ - lo, hi - e_], fmt="o-",
                    ms=3.6, lw=0.9, capsize=2.2, color=cols9[k], label=en[nm])
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}h" for h in hs])
    ax.set_title("simple effects (95% CI)", fontsize=9.5)
    ax.set_xlabel("forward horizon", fontsize=8.5)
    ax.set_ylabel("difference (bp)", fontsize=8.5)
    ax.tick_params(labelsize=7)
    ax.grid(axis="y", lw=0.3, alpha=0.4)
    ax.legend(fontsize=6.4, frameon=False, loc="upper left")
    ax = axes[1]
    s = fb[fb["cell"] == "交互 (R1-R2)-(R3-R4)"].set_index("h").reindex(hs)
    e_ = s["estimate"].to_numpy("float64") * 1e4
    lo = (s["estimate"] - 1.96 * s["se"]).to_numpy("float64") * 1e4
    hi = (s["estimate"] + 1.96 * s["se"]).to_numpy("float64") * 1e4
    ax.errorbar(x, e_, yerr=[e_ - lo, hi - e_], fmt="s-", ms=4.6, lw=1.2,
                capsize=2.6, color="#4c4c4c")
    ax.axhline(0, color="k", lw=0.8)
    for k, h in enumerate(hs):
        ax.annotate(f"t {s.loc[h, 't']:+.2f}", (x[k], e_[k]), textcoords="offset points",
                    xytext=(0, 7), fontsize=6.4, ha="center", color="#4c4c4c")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{h}h" for h in hs])
    ax.set_title("interaction  (R1-R2) − (R3-R4)", fontsize=9.5)
    ax.set_xlabel("forward horizon", fontsize=8.5)
    ax.set_ylabel("difference of differences (bp)", fontsize=8.5)
    ax.tick_params(labelsize=7)
    ax.grid(axis="y", lw=0.3, alpha=0.4)
    fig.suptitle("Fig 1b · Price × OI 2×2 factor: does either dimension add information?", fontsize=10.5)
    fig.tight_layout()
    _rows = []
    for _nm in order + ["交互 (R1-R2)-(R3-R4)"]:
        _s = fb[fb["cell"] == _nm].set_index("h")
        _rows.append([en.get(_nm, "interaction")] +
                     [f"{float(_s.loc[h, 'estimate']) * 1e4:+.2f}bp ({float(_s.loc[h, 't']):+.2f})"
                      for h in hs])
    tbl7 = (["effect"] + [f"{h}h" for h in hs], _rows, "bp (t)")
    save(fig, "f01b_factor_2x2.png", table=tbl7)

    # ---- Fig 15 上排：日内持续性梯度；下排：小时 vs 币-日 两种加权（实验 15），四期限 ----
    bc = read_table("robust_daily_bycount")
    rd = read_table("robust_daily")
    e1 = read_table("exp1_4")
    hourly = e1[e1["experiment"] == "1 收益·均值"]
    daily = rd[rd["experiment"] == "15 日频·收益"]

    fig, axes = plt.subplots(2, len(hs), figsize=(13.2, 6.2))
    fig.subplots_adjust(hspace=0.55, wspace=0.30)

    # 上排：日内持续性（原始日均值，无 FE）
    for col, hh in enumerate(hs):
        ax = axes[0, col]
        sub = bc[bc["h"] == hh]
        for c in CELLS:
            s = sub[sub["cell"] == c].sort_values("bucket")
            ax.plot(s["bucket"], s["daymean"] * 1e4, marker="o", ms=3.6, lw=1.4,
                    color=COLORS[c], label=c)
        ax.axhline(0, color="k", lw=0.8)
        ax.set_xticks([1, 2, 3, 4, 5])
        ax.set_xticklabels(["1", "2", "3", "4", "5+"], fontsize=7)
        ax.set_title(f"persistence  ·  h = {hh}h", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
        if col == 0:
            ax.set_ylabel("day-level mean (bp)\nraw, no FE", fontsize=7.5)
            ax.legend(fontsize=6.4, frameon=False, ncol=2, loc="upper left")

    # 下排：两种加权（哑铃图，带币月 FE）
    for col, hh in enumerate(hs):
        ax = axes[1, col]
        for i, c in enumerate(CELLS):
            hv = float(hourly[(hourly["cell"] == c) & (hourly["h"] == hh)]["estimate"].iloc[0]) * 1e4
            dv = float(daily[(daily["cell"] == c) & (daily["h"] == hh)]["estimate"].iloc[0]) * 1e4
            ax.plot([hv, dv], [i, i], "-", color="0.62", lw=1.4, zorder=1)
            ax.plot(hv, i, "o", ms=6, mfc="white", mec=COLORS[c], mew=1.6, zorder=2)
            ax.plot(dv, i, "o", ms=6, color=COLORS[c], zorder=3)
        ax.axvline(0, color="k", lw=0.9)
        ax.set_yticks(range(len(CELLS)))
        ax.set_yticklabels(CELLS if col == 0 else [""] * len(CELLS), fontsize=7.5)
        ax.set_ylim(-0.55, len(CELLS) - 0.45)
        ax.set_title(f"weighting  ·  h = {hh}h", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(axis="x", lw=0.3, alpha=0.4)
        if col == 0:
            ax.set_ylabel("Delta vs benchmark (bp)\nafter contract+month FE", fontsize=7.5)

    axes[1, 0].set_xlabel("Delta vs benchmark, bp", fontsize=7.5)
    axes[0, 0].set_xlabel("hours the state appeared that day", fontsize=7.5)
    for col in range(len(hs)):
        axes[1, col].set_xlabel("Delta vs benchmark, bp", fontsize=7.5)

    fig.suptitle("Fig 15 · The return result depends on weighting and on within-day persistence",
                 fontsize=10.5, y=0.98)
    fig.text(0.5, 0.006, "Top row: raw day-level means, no fixed effects - bucket = how many hours " +
             "that contract showed the state that day (y-axis differs by panel).  Bottom row: the " +
             "same regression as Exp 1, re-estimated with one vote per contract-day (filled) instead " +
             "of per hour (hollow); the sign flips in all four regimes at every horizon.",
             ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.035, 1, 0.945))

    _rows = []
    for c in CELLS:
        _r = [c]
        for hh in hs:
            hv = float(hourly[(hourly["cell"] == c) & (hourly["h"] == hh)]["estimate"].iloc[0]) * 1e4
            ht = float(hourly[(hourly["cell"] == c) & (hourly["h"] == hh)]["t"].iloc[0])
            dv = float(daily[(daily["cell"] == c) & (daily["h"] == hh)]["estimate"].iloc[0]) * 1e4
            dt = float(daily[(daily["cell"] == c) & (daily["h"] == hh)]["t"].iloc[0])
            _r += [f"{hv:+.2f} ({ht:+.2f})", f"{dv:+.2f} ({dt:+.2f})"]
        _rows.append(_r)
    save(fig, "f15_bycount.png",
         table=(["state"] + [f"{h}h {k}" for h in hs for k in ("hourly", "day")],
                _rows, "Delta vs benchmark, bp (t) - same regression, two observation units"))

# ---- Fig 14a 跨合约分布（合约等权；每个合约一票）----
    bs = read_table("descriptive_by_symbol")
    MIN_N = 30
    kept_total = int(bs[bs["h"] == 1]["symbol"].nunique())
    xv14 = np.arange(len(hs))
    fig, axes = plt.subplots(2, 2, figsize=(9.4, 5.8), sharex=True, sharey=True)
    for ax, c in zip(axes.ravel(), CELLS):
        s = bs[(bs["cell"] == c) & (bs["n"] >= MIN_N)]
        med, lo, hi, mu_ = [], [], [], []
        for h in hs:
            v = s[s["h"] == h]["mean_excess"].to_numpy("float64") * 1e4
            med.append(float(np.median(v)))
            lo.append(float(np.percentile(v, 25)))
            hi.append(float(np.percentile(v, 75)))
            mu_.append(float(v.mean()))
        ax.fill_between(xv14, lo, hi, color=COLORS[c], alpha=0.22, lw=0,
                        label="p25-p75 across contracts")
        ax.plot(xv14, med, "-", color=COLORS[c], lw=1.7, label="median contract")
        ax.plot(xv14, mu_, "--", color="#c53030", lw=1.2, label="mean across contracts")
        ax.axhline(0, color="k", lw=0.8)
        kept = s[s["h"] == hs[0]]["symbol"].nunique()
        ax.set_title(f"{c}   ({kept}/{kept_total} contracts with n≥{MIN_N})", fontsize=9)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)
    for ax in axes[-1]:
        ax.set_xticks(xv14)
        ax.set_xticklabels([f"{h}h" for h in hs], fontsize=8)
        ax.set_xlabel("forward horizon", fontsize=8.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("per-contract mean excess (bp)", fontsize=8.5)
    axes[0, 0].legend(fontsize=6.6, frameon=False, loc="lower left")
    fig.suptitle("Fig 14a · Dispersion across contracts: one dot per contract, contract-weighted "
                 "(descriptive — no test)", fontsize=10)
    fig.text(0.5, 0.005, "Each contract contributes ONE value (its own mean excess return in that "
             "state), so this is the 'does it work for a random coin?' view.  Compare with Fig 10, "
             "which weights every event equally.", ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    _rows = []
    for c in CELLS:
        s = bs[(bs["cell"] == c) & (bs["n"] >= MIN_N)].set_index("h")
        med = [f"{np.median(s.loc[h, 'mean_excess'].to_numpy('float64')) * 1e4:+.1f}bp" for h in hs]
        muv = [f"{s.loc[h, 'mean_excess'].to_numpy('float64').mean() * 1e4:+.1f}bp" for h in hs]
        _rows.append([f"{c}  median contract"] + med)
        _rows.append([f"{c}  mean (contract-weighted)"] + muv)
    save(fig, "f14a_by_symbol.png",
         table=(["state / statistic"] + [f"{h}h" for h in hs], _rows,
                "per-contract mean excess return, bp — descriptive, no test"))

    # ---- Fig 14b 分市场波动状态（行等权；组内所有事件一票）----
    stt14 = read_table("descriptive_by_state")
    from matplotlib.colors import to_rgb

    def _shade(col, w):
        r, g, b = to_rgb(col)
        return (1 - w + w * r, 1 - w + w * g, 1 - w + w * b)

    fig, axes = plt.subplots(2, 2, figsize=(9.4, 5.8), sharex=True, sharey=True)
    for ax, c in zip(axes.ravel(), CELLS):
        for s_, w in (("low", 0.40), ("mid", 0.70), ("high", 1.00)):
            v = [float(stt14[(stt14["cell"] == c) & (stt14["state"] == s_) &
                             (stt14["h"] == h)]["mean_excess"].iloc[0]) * 1e4 for h in hs]
            ax.plot(xv14, v, "o-", ms=3.6, lw=1.5, color=_shade(COLORS[c], w),
                    label=f"market vol {s_}")
        ax.axhline(0, color="k", lw=0.8)
        ax.set_title(c, fontsize=9)
        ax.grid(axis="y", lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)
    for ax in axes[-1]:
        ax.set_xticks(xv14)
        ax.set_xticklabels([f"{h}h" for h in hs], fontsize=8)
        ax.set_xlabel("forward horizon", fontsize=8.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("mean excess return (bp)", fontsize=8.5)
    axes[0, 0].legend(fontsize=6.6, frameon=False, loc="lower left")
    fig.suptitle("Fig 14b · Level by market-volatility regime: low / mid / high, every event "
                 "weighted equally (descriptive — no test)", fontsize=10)
    fig.text(0.5, 0.005, "Same y-axis as Fig 14a.  Here rows are weighted equally inside each "
             "regime bucket, so it answers 'does the sign survive in a different market "
             "environment?', not 'does it work for a random coin?'.", ha="center",
             fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.94))
    _rows = []
    for c in CELLS:
        for s_ in ("low", "mid", "high"):
            v = [f"{float(stt14[(stt14['cell'] == c) & (stt14['state'] == s_) &
                                (stt14['h'] == h)]['mean_excess'].iloc[0]) * 1e4:+.2f}bp" for h in hs]
            _rows.append([f"{c}  {s_} vol"] + v)
    save(fig, "f14b_by_state.png",
         table=(["state / bucket"] + [f"{h}h" for h in hs], _rows,
                "mean excess return by market-vol regime, bp — descriptive, no test"))

    print(f"共 {len(list(FIG.glob('*.png')))} 张图 → {FIG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
