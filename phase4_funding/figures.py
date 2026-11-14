"""Phase 4 · figures — P4-4 conditional path + P4-5 beta by cell.

P4-4: 4 panels, MFE vs MAE (p50) by funding/horizon.
P4-5: 4x4 small multiples (regime x funding), beta vs horizon, event/contract-day.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TBL = ROOT / "data/07_funding/tables/freq=1h"
OUT = ROOT / "data/07_funding/figures"

FUNDS = ["negative", "neutral", "high", "extreme"]
COLORS = {"negative": "#b2182b", "neutral": "#2166ac",
          "high": "#e08214", "extreme": "#762a83"}
HORIZONS = [1, 4, 8, 24]
MARKERS = {1: "o", 4: "s", 8: "^", 24: "D"}


def f_p4_4() -> None:
    d = pd.read_parquet(TBL / "p4_4_path.parquet")
    d = d[d["weighting"] == "event"]
    rows = []
    for h in HORIZONS:
        for f in FUNDS:
            s = d[(d["h"] == h) & (d["funding"] == f)]
            rows.append(s["mfe_median"].to_numpy() * 1e4)
            rows.append(s["mae_median"].to_numpy() * 1e4)
    lim = float(np.nanmax(np.abs(np.concatenate(rows)))) * 1.08

    fig, axes = plt.subplots(2, 4, figsize=(15.4, 7.8))
    for j, r in enumerate(["R1", "R2", "R3", "R4"]):
        ax = axes[0, j]
        for f in FUNDS:
            s = (d[(d["regime"] == r) & (d["funding"] == f)]
                 .set_index("h").reindex(HORIZONS))
            x = s["mfe_median"].to_numpy() * 1e4
            y = s["mae_median"].to_numpy() * 1e4
            ax.plot(x, y, color=COLORS[f], lw=0.8, alpha=0.65, zorder=2)
            for i, h in enumerate(HORIZONS):
                ax.scatter(x[i], y[i], marker=MARKERS[h], s=22,
                           color=COLORS[f], edgecolor="white", lw=0.4,
                           zorder=3)
        ax.plot([0, lim], [0, -lim], ls="--", lw=0.8, color="0.5")
        ax.set_title(r, fontsize=10)
        ax.set_xlim(0, lim)
        ax.set_ylim(-lim, 0)
        ax.grid(lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)
        ax.set_xlabel("MFE — p50, bp", fontsize=7.5)
        if j == 0:
            ax.set_ylabel("MAE — p50, bp", fontsize=8)

    for j, r in enumerate(["R1", "R2", "R3", "R4"]):
        ax = axes[1, j]
        for f in FUNDS:
            s = (d[(d["regime"] == r) & (d["funding"] == f)]
                 .set_index("h").reindex(HORIZONS))
            y = s["mdd_p50"].to_numpy() * 1e4
            ax.plot(HORIZONS, y, color=COLORS[f], lw=1.1, marker="o", ms=3.5,
                    label=f, zorder=3)
        ax.axhline(0, color="0.5", lw=0.7, ls="--", zorder=1)
        ax.set_xticks(HORIZONS)
        ax.set_xticklabels([f"{h}h" for h in HORIZONS], fontsize=7)
        ax.set_xlabel("horizon", fontsize=7.5)
        ax.grid(lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)
        if j == 0:
            ax.set_ylabel("MDD — p50, bp", fontsize=8)

    fund_handles = [Line2D([0], [0], color=COLORS[f], lw=1.4, label=f)
                    for f in FUNDS]
    axes[0, 0].legend(handles=fund_handles, fontsize=6.8, frameon=False,
                      title="funding", title_fontsize=6.8, loc="upper left")
    axes[1, 0].legend(handles=fund_handles, fontsize=6.8, frameon=False,
                      title="funding", title_fontsize=6.8, loc="lower left")
    h_handles = [Line2D([0], [0], marker=MARKERS[h], color="0.25", ls="",
                        ms=5, label=f"{h}h") for h in HORIZONS]
    axes[0, 3].legend(handles=h_handles, fontsize=6.8, frameon=False,
                      title="horizon", title_fontsize=6.8, loc="lower right")

    fig.suptitle("P4-4 · path and drawdown (event; descriptive — no test)",
                 fontsize=11)
    fig.text(0.5, 0.005,
             "Top: Phase 3 Fig 11 style, MFE vs MAE p50 (45° = symmetric).  "
             "Bottom: MDD p50 by horizon.  h=1 MDD = min(0, dir·fwd), no "
             "intrabar path; use h ≥ 4 for path MDD.  Means/medians/"
             "percentiles in p4_4_path.csv.",
             ha="center", fontsize=6.7, color="#4a5568")
    fig.tight_layout(rect=(0, 0.02, 1, 0.94))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f_p4_4_path.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f_p4_4_path.png'}")


def f_p4_5() -> None:
    d = pd.read_parquet(TBL / "p4_5_beta.parquet")
    d = d[d["outcome"].isin(["y_raw", "rev"])].copy()
    d["sig"] = (d["p_bh"] < 0.05) & (d["t_drop5"].abs() > 1.96)
    d["row"] = (d["regime"] + " × " + d["funding"] + "  "
                + d["h"].astype(str) + "h")
    order = [f"{r} × {f}  {h}h" for r in ["R1", "R2", "R3", "R4"]
             for f in FUNDS for h in HORIZONS]
    ypos = {k: i for i, k in enumerate(order)}
    fig, axes = plt.subplots(1, 2, figsize=(13.2, 10.5))
    for ax, dv, xlab, ttl in (
            (axes[0], "y_raw", "beta, bp (y_raw)",
             "P4-5a · return gap vs matched benchmark (bp)"),
            (axes[1], "rev", "beta, pp (rev)",
             "P4-5b · reversal gap vs matched benchmark (pp)")):
        s = d[d["outcome"] == dv]
        for w, color, ms, alpha in (
                ("event", "0.55", 2.8, 0.55),
                ("contract_day", "#c05621", 4.2, 1.0)):
            q = s[s["weighting"] == w]
            for _, r in q.iterrows():
                ax.errorbar(float(r["beta"]), ypos[r["row"]],
                            xerr=1.96 * float(r["se"]), fmt="o",
                            color=color, ms=ms, lw=0.7, capsize=1.8,
                            mfc=color if r["sig"] else "white", mec=color,
                            mew=0.5, alpha=alpha, zorder=3)
        ax.axvline(0, color="0.35", lw=0.8, zorder=1)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(order, fontsize=5.9)
        ax.set_ylim(-0.6, len(order) - 0.4)
        ax.set_xlabel(xlab, fontsize=8.5)
        ax.set_title(ttl, fontsize=9.5)
        ax.grid(axis="x", lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)
    handles = [
        Line2D([0], [0], color="0.55", lw=1.2, label="event"),
        Line2D([0], [0], color="#c05621", lw=1.2, label="contract-day"),
        Line2D([0], [0], color="0.25", ls="", marker="o", ms=4,
               markerfacecolor="0.25", label="BH16 + drop5"),
        Line2D([0], [0], color="0.25", ls="", marker="o", ms=4,
               markerfacecolor="white", label="not significant"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=7,
               frameon=False, bbox_to_anchor=(0.5, 0.005))
    fig.suptitle("P4-5 · all cells, BH16 + drop5 filled: forest", fontsize=11)
    fig.text(0.5, 0.035,
             "Event (gray): 0/16 significant.  Contract-day (orange): 5/16.  "
             "R1 neutral +2.35bp (event) vs -6.23bp (contract-day); the beta is "
             "weight-dependent, not one estimate.  Full table: p4_5_beta.csv.",
             ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.06, 1, 0.95))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f04_beta_forest.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f04_beta_forest.png'}")


def _level(df, value_col, n_col, title, cbar_label, cmap, fname, fmt, div):
    fig, axes = plt.subplots(2, 4, figsize=(15.2, 7.6),
                             sharex=True, sharey=True)
    if div:
        mx = float(np.nanmax(np.abs(df[value_col])))
        vmin, vmax = -mx, mx
    else:
        vmin, vmax = float(df[value_col].min()), float(df[value_col].max())
    im = None
    for i, w in enumerate(["event", "contract_day"]):
        for j, h in enumerate(HORIZONS):
            ax = axes[i, j]
            s = df[(df["weighting"] == w) & (df["h"] == h)]
            p = (s.pivot(index="regime", columns="funding", values=value_col)
                 .reindex(index=["R1", "R2", "R3", "R4"], columns=FUNDS))
            n = (s.pivot(index="regime", columns="funding", values=n_col)
                 .reindex(index=["R1", "R2", "R3", "R4"], columns=FUNDS))
            im = ax.imshow(p.values, cmap=cmap, aspect="auto",
                           vmin=vmin, vmax=vmax)
            for a in range(4):
                for b in range(4):
                    ax.text(b, a,
                            f"{p.values[a, b]:{fmt}}\n{int(n.values[a, b]):,}",
                            ha="center", va="center", fontsize=6.2)
            ax.set_xticks(range(4))
            ax.set_xticklabels(FUNDS, fontsize=6.4, rotation=25)
            ax.set_yticks(range(4))
            ax.set_yticklabels(["R1", "R2", "R3", "R4"], fontsize=7)
            ax.set_title(f"{w} · {h}h", fontsize=8)
            ax.tick_params(length=0)
    fig.subplots_adjust(left=0.06, right=0.9, top=0.88, bottom=0.1,
                        wspace=0.08, hspace=0.18)
    cax = fig.add_axes([0.925, 0.15, 0.015, 0.65])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label(cbar_label)
    fig.suptitle(title, fontsize=11, y=0.97)
    fig.text(0.5, 0.02,
             "Cell = mean; second line = n events.  high = union (incl extreme); "
             "extreme = subset.  Descriptive; no test.", ha="center",
             fontsize=6.8, color="#4a5568")
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / fname, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / fname}")


def f_p4_1_level() -> None:
    d = pd.read_parquet(TBL / "p4_1_surface.parquet").copy()
    _level(d, "y_raw_mean", "y_raw_n_obs",
           "P4-1 · return level (y_raw, bp): R1-R4 × funding, "
           "event/contract × 1/4/8/24h",
           "y_raw, bp", "RdBu_r", "f01_return_level.png", ".1f", True)


def f_p4_2_level() -> None:
    d = pd.read_parquet(TBL / "p4_2_vol.parquet").copy()
    _level(d, "lrv_mean", "lrv_n_obs",
           "P4-2 · volatility level (lrv = log rv): R1-R4 × funding, "
           "event/contract × 1/4/8/24h",
           "lrv", "viridis", "f02_vol_level.png", ".2f", False)


def f_p4_3_difference() -> None:
    a = pd.read_parquet(TBL / "p4_1_contrasts.parquet")
    a = a[(a["dv"] == "y_raw") & (a["h"] == 1)].copy()
    a["est"] = a["estimate"]
    a["se"] = a["se"]
    a["td"] = a["t_drop5"]
    b = pd.read_parquet(TBL / "p4_2_contrasts.parquet")
    b = b[b["h"] == 24].copy()
    b["est"] = b["estimate"] * 100
    b["se"] = b["se"] * 100
    b["td"] = b["t_drop5"]
    c = pd.read_parquet(TBL / "p4_3_reversal.parquet")
    c = c[c["h"] == 1].copy()
    c["est"] = c["rev_estimate_pp"]
    c["se"] = c["rev_se_pp"]
    c["td"] = c["rev_t_drop5"]

    kinds = ["negative - neutral", "high(incl ext) - neutral",
             "extreme - neutral"]
    short = ["neg-neu", "high-neu", "ext-neu"]
    order = [(r, k) for r in ["R1", "R2", "R3", "R4"] for k in kinds]
    labels = [f"{r} {s}" for r in ["R1", "R2", "R3", "R4"] for s in short]
    ypos = {k: i for i, k in enumerate(order)}

    fig, axes = plt.subplots(1, 3, figsize=(14.2, 6.4), sharey=True)
    panels = [
        (axes[0], a, "P4-1a · return difference (h=1, bp)", "bp"),
        (axes[1], b, "P4-2 · volatility difference (h=24, % of lrv)", "%"),
        (axes[2], c, "P4-3 · reversal difference (h=1, pp)", "pp"),
    ]
    for ax, d, ttl, unit in panels:
        for w, color in (("event", "#2b6cb0"),
                         ("contract_day", "#c05621")):
            q = d[d["weighting"] == w]
            for _, row in q.iterrows():
                y = ypos[(row["regime"], row["contrast"])]
                sig = (row["p_bh"] < 0.05) and (abs(row["td"]) > 1.96)
                ax.errorbar(float(row["est"]), y,
                            xerr=1.96 * float(row["se"]), fmt="o",
                            color=color, ms=3.6, lw=0.9, capsize=2,
                            mfc=color if sig else "white", mec=color,
                            mew=0.6, zorder=3)
        ax.axvline(0, color="0.35", lw=0.8, zorder=1)
        ax.set_yticks(range(len(order)))
        ax.set_yticklabels(labels, fontsize=5.8)
        ax.set_ylim(-0.6, len(order) - 0.4)
        ax.set_xlabel(unit, fontsize=8)
        ax.set_title(ttl, fontsize=9)
        ax.grid(axis="x", lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=6.5)
    handles = [
        Line2D([0], [0], color="#2b6cb0", lw=1.2, label="event"),
        Line2D([0], [0], color="#c05621", lw=1.2, label="contract-day"),
        Line2D([0], [0], color="0.25", ls="", marker="o", ms=4,
               markerfacecolor="0.25", label="BH12 + drop5"),
        Line2D([0], [0], color="0.25", ls="", marker="o", ms=4,
               markerfacecolor="white", label="not significant"),
    ]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=7,
               frameon=False, bbox_to_anchor=(0.5, 0.005))
    fig.suptitle("P4 · within-regime funding differences (vs neutral): "
                 "12 contrasts × event/contract", fontsize=11)
    fig.text(0.5, 0.04,
             "Difference = FE-adjusted (contract + month) minus neutral; "
             "positive = higher than neutral.  Bars = 95% CI.  Only one h per "
             "panel (return/rev h=1; vol h=24); full 4-h table in the CSVs.",
             ha="center", fontsize=6.6, color="#4a5568")
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f03_difference_forest.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f03_difference_forest.png'}")


if __name__ == "__main__":
    f_p4_4()
    f_p4_5()
    f_p4_1_level()
    f_p4_2_level()
    f_p4_3_difference()
