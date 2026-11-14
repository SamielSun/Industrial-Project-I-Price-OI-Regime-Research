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
    d = d[d["outcome"].isin(["y_raw", "rev"])].copy()
    d["sig"] = (d["p_bh"] < 0.05) & (d["t_drop5"].abs() > 1.96)
    cells = [(r, f) for r in ["R1", "R2", "R3", "R4"] for f in FUNDS]
    ypos = {c: i for i, c in enumerate(cells)}
    ev_col, ct_col = "#2b6cb0", "#c05621"
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 7.2), sharey=True)
    for ax, dv, xlab, ttl in (
            (axes[0], "y_raw", "beta, bp (y_raw)", "P4-5a · return gap (bp)"),
            (axes[1], "rev", "beta, pp (rev)", "P4-5b · reversal gap (pp)")):
        for i, (r, f) in enumerate(cells):
            ax.axhspan(i - 0.5, i + 0.5,
                       color="#f5f9ff" if r in ("R1", "R2", "R3") else "white",
                       zorder=0)
        s = d[(d["outcome"] == dv) & d["sig"]]
        for w, color, dy in (("event", ev_col, -0.16),
                             ("contract_day", ct_col, 0.16)):
            q = s[s["weighting"] == w]
            for h, mk in MARKERS.items():
                z = q[q["h"] == h]
                yv = [ypos[(r, f)] + dy
                      for r, f in zip(z["regime"], z["funding"])]
                ax.errorbar(z["beta"], yv, xerr=1.96 * z["se"], fmt=mk,
                            color=color, ms=4.4, lw=0.9, capsize=2,
                            mec="white", mew=0.3, zorder=3)
        ax.axvline(0, color="0.35", lw=0.8, zorder=1)
        ax.set_yticks(range(len(cells)))
        ax.set_yticklabels([f"{r} × {f}" for r, f in cells], fontsize=6.8)
        ax.set_xlabel(xlab, fontsize=8.5)
        ax.set_title(ttl, fontsize=9.5)
        ax.grid(axis="x", lw=0.3, alpha=0.4)
        ax.tick_params(labelsize=7)
        ax.set_ylim(-0.6, len(cells) - 0.4)
    handles = [
        Line2D([0], [0], color=ev_col, lw=1.2, label="event"),
        Line2D([0], [0], color=ct_col, lw=1.2, label="contract-day"),
    ]
    handles += [Line2D([0], [0], color="0.25", ls="", marker=mk, ms=4.5,
                       label=f"{h}h") for h, mk in MARKERS.items()]
    handles.append(Patch(facecolor="#f5f9ff", edgecolor="0.7",
                         label="note slice (R1-R3)"))
    fig.legend(handles=handles, loc="lower center", ncol=7, fontsize=7,
               frameon=False, bbox_to_anchor=(0.5, 0.004))
    fig.suptitle("P4-5 · significant cells only (BH16 + drop5)", fontsize=11)
    fig.text(0.5, 0.045,
             "Only cell × h × weighting points passing BH16 + drop5 are drawn; "
             "blank = not significant.  Full table: p4_5_beta.csv.  Positive = "
             "regime beats the same-direction, same-funding benchmark; rev "
             "positive = more reversal.", ha="center", fontsize=6.6,
             color="#4a5568")
    fig.tight_layout(rect=(0, 0.09, 1, 0.94))
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "f04_beta_significant.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {OUT / 'f04_beta_significant.png'}")


if __name__ == "__main__":
    f_p4_4()
    f_p4_5()
