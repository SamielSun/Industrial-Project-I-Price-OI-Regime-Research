"""Phase 4 · figures — P4-4 conditional path.

One figure: 4 panels (R1-R4), MFE vs |MAE| by funding (colour) and horizon
(marker), median (p50) path.  Cell means (kept in the main table) live in
p4_4_path.csv; the Phase 3 state-level path is this table's funding-weighted
marginal.
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

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TBL = ROOT / "phase4_funding/tables"
OUT = ROOT / "phase4_funding/figures"

FUNDS = ["negative", "neutral", "high", "extreme"]
COLORS = {"negative": "#b2182b", "neutral": "#2166ac",
          "high": "#e08214", "extreme": "#762a83"}
HORIZONS = [1, 4, 8, 24]
MARKERS = {1: "o", 4: "s", 8: "^", 24: "D"}
MARKERS_F = {"R1": "o", "R2": "s", "R3": "^", "R4": "D"}


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

    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.4), sharex=True, sharey=True)
    for ax, r in zip(axes.ravel(), ["R1", "R2", "R3", "R4"]):
        for f in FUNDS:
            s = (d[(d["regime"] == r) & (d["funding"] == f)]
                 .set_index("h").reindex(HORIZONS))
            x = s["mfe_median"].to_numpy() * 1e4
            y = s["mae_median"].to_numpy() * 1e4
            ax.plot(x, y, color=COLORS[f], lw=0.8, alpha=0.65, zorder=2)
            for i, h in enumerate(HORIZONS):
                ax.scatter(x[i], y[i], marker=MARKERS[h], s=26,
                           color=COLORS[f], edgecolor="white", lw=0.4, zorder=3)
        ax.plot([0, lim], [0, -lim], ls="--", lw=0.8, color="0.5")
        ax.set_title(r, fontsize=10)
        ax.set_xlim(0, lim)
        ax.set_ylim(-lim, 0)
        ax.grid(lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7.5)
    for ax in axes[-1]:
        ax.set_xlabel("MFE — median (p50), bp", fontsize=8.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("MAE — median (p50), bp", fontsize=8.5)

    fund_handles = [Line2D([0], [0], color=COLORS[f], lw=1.4, label=f)
                    for f in FUNDS]
    h_handles = [Line2D([0], [0], marker=MARKERS[h], color="0.25", ls="",
                        ms=5, label=f"{h}h") for h in HORIZONS]
    ax0 = axes[0, 0]
    leg1 = ax0.legend(handles=fund_handles, fontsize=7.2, frameon=False,
                      loc="upper left", title="funding", title_fontsize=7.2)
    ax0.add_artist(leg1)
    ax0.legend(handles=h_handles, fontsize=7.2, frameon=False,
               loc="lower right", title="horizon", title_fontsize=7.2)

    fig.suptitle("P4-4 · Conditional path: MFE vs MAE by funding "
                 "(median, event-weighted; descriptive — no test)", fontsize=10.5)
    fig.text(0.5, 0.005,
             "Dashed line = MAE = -MFE (symmetric path).  p50 plotted (Phase 3 Fig 11 "
             "convention: the mean is dominated by a few extreme paths); cell means are "
             "kept in p4_4_path.csv.  Phase 3 descriptive_path is this table's "
             "funding-weighted marginal.",
             ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f_p4_4_path.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f_p4_4_path.png'}")


def f_p4_5() -> None:
    d = pd.read_parquet(TBL / "p4_5_beta.parquet")
    d = d[(d["h"] == 1) & (d["weighting"] == "event")
          & (d["outcome"].isin(["y_raw", "rev"]))].copy()
    order = [(r, f) for r in ["R1", "R2", "R3", "R4"] for f in FUNDS]
    fig, axes = plt.subplots(1, 2, figsize=(10.8, 6.0), sharey=True)
    for ax, dv, xlab, ttl in (
            (axes[0], "y_raw", "beta, bp (y_raw)", "P4-5a · return gap (bp)"),
            (axes[1], "rev", "beta, pp (rev)", "P4-5b · reversal gap (pp)")):
        s = d[d["outcome"] == dv].set_index(["regime", "funding"])
        y = np.arange(len(order))
        for i, (r, f) in enumerate(order):
            row = s.loc[(r, f)]
            ax.errorbar(float(row["beta"]), i,
                        xerr=1.96 * float(row["se"]), fmt=MARKERS_F[r],
                        color=COLORS[f], ms=4.5, lw=0.9, capsize=2,
                        mec="white", mew=0.4, zorder=3)
        ax.axvline(0, color="0.35", lw=0.8, zorder=1)
        ax.set_yticks(y)
        ax.set_yticklabels([f"{r} {f}" for r, f in order], fontsize=6.8)
        ax.set_xlabel(xlab, fontsize=8.5)
        ax.set_title(ttl, fontsize=9.5)
        ax.grid(axis="x", lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7.2)
    axes[0].set_ylim(-0.6, len(order) - 0.4)
    fig.suptitle("P4-5 · Beta vs matched benchmark (same direction, same funding), "
                 "h=1, event-weighted", fontsize=10.5)
    fig.text(0.5, 0.01,
             "Positive = regime beats the same-direction, same-funding benchmark "
             "(cell 0 + the other OI state).  Bars = 95% CI.  BH 16 + drop5 for "
             "y_raw/rev; fwd is descriptive.", ha="center", fontsize=6.8,
             color="#4a5568")
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f04_beta_forest.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f04_beta_forest.png'}")


if __name__ == "__main__":
    f_p4_4()
    f_p4_5()
