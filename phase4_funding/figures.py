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


def f_p4_4() -> None:
    d = pd.read_parquet(TBL / "p4_4_path.parquet")
    d = d[d["weighting"] == "event"]
    rows = []
    for h in HORIZONS:
        for f in FUNDS:
            s = d[(d["h"] == h) & (d["funding"] == f)]
            rows.append(s["mfe_median"].to_numpy() * 1e4)
            rows.append(-s["mae_median"].to_numpy() * 1e4)
    lim = float(np.nanmax(np.concatenate(rows))) * 1.08

    fig, axes = plt.subplots(2, 2, figsize=(9.2, 7.4), sharex=True, sharey=True)
    for ax, r in zip(axes.ravel(), ["R1", "R2", "R3", "R4"]):
        for f in FUNDS:
            s = (d[(d["regime"] == r) & (d["funding"] == f)]
                 .set_index("h").reindex(HORIZONS))
            x = s["mfe_median"].to_numpy() * 1e4
            y = -s["mae_median"].to_numpy() * 1e4
            ax.plot(x, y, color=COLORS[f], lw=0.8, alpha=0.65, zorder=2)
            for i, h in enumerate(HORIZONS):
                ax.scatter(x[i], y[i], marker=MARKERS[h], s=26,
                           color=COLORS[f], edgecolor="white", lw=0.4, zorder=3)
        ax.plot([0, lim], [0, lim], ls="--", lw=0.8, color="0.5")
        ax.set_title(r, fontsize=10)
        ax.set_xlim(0, lim)
        ax.set_ylim(0, lim)
        ax.grid(lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7.5)
    for ax in axes[-1]:
        ax.set_xlabel("MFE — median (p50), bp", fontsize=8.5)
    for ax in axes[:, 0]:
        ax.set_ylabel("|MAE| — median (p50), bp", fontsize=8.5)

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

    fig.suptitle("P4-4 · Conditional path: MFE vs |MAE| by funding "
                 "(median, event-weighted; descriptive — no test)", fontsize=10.5)
    fig.text(0.5, 0.005,
             "Dashed line = MFE = |MAE| (symmetric path).  p50 plotted; cell means "
             "(mfe/mae/mdd) are in p4_4_path.csv, not demoted.  Phase 3 "
             "descriptive_path is this table's funding-weighted marginal.",
             ha="center", fontsize=6.8, color="#4a5568")
    fig.tight_layout(rect=(0, 0.03, 1, 0.93))

    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f_p4_4_path.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f_p4_4_path.png'}")


if __name__ == "__main__":
    f_p4_4()
