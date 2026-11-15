"""Phase 5 -- figures.  Reads only the CSVs written by gate/eval.

    python -m phase5.figures

f01  cumulative net PnL and drawdown, both arms, main test window
f02  cost* (gross per trade) against the 20bp taker round trip
f03  executable per-trade PnL by year -- the decay story
f04  gate funnel: 96 cells -> 10 -> 6 -> 2
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import backtest as bt

TBL = bt.DATA / "08_strategy" / "tables"
FIG = bt.DATA / "08_strategy" / "figures"
COST = 20.0
C = {"A1": "#c0392b", "B1": "#2c6fbb"}


def f01_equity(daily: pd.DataFrame) -> None:
    fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True,
                           gridspec_kw=dict(height_ratios=[2, 1]))
    for arm in ("A1", "B1"):
        d = daily[(daily.arm == arm) & (daily.variant == "base")].copy()
        if d.empty:
            continue
        t = pd.to_datetime(d["date"])
        net = d["net"].cumsum() / bt.EQUITY0 * 100
        gross = (d["price"] + d["funding"]).cumsum() / bt.EQUITY0 * 100
        ax[0].plot(t, net, color=C[arm], lw=1.6, label=f"{arm} net (20bp)")
        ax[0].plot(t, gross, color=C[arm], lw=1.0, ls="--", alpha=0.75,
                   label=f"{arm} gross")
        eq = 100 + net
        ax[1].plot(t, eq / eq.cummax() * 100 - 100, color=C[arm], lw=1.2,
                   label=f"{arm}")
    ax[0].axhline(0, color="k", lw=0.8)
    ax[0].set_ylabel("cumulative PnL, % of initial capital")
    ax[0].set_title("A1 and B1, main test window 2024-06..2026-08 (in-sample)")
    ax[0].legend(fontsize=8, ncol=2)
    ax[0].grid(alpha=0.3)
    ax[1].set_ylabel("drawdown, %")
    ax[1].legend(fontsize=8)
    ax[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG / "f01_equity.png", dpi=150)
    plt.close(fig)


def f02_cost(rules: pd.DataFrame) -> None:
    m = rules[(rules.window == "main") & (rules.variant == "base")]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    y = np.arange(len(m))
    ax.barh(y, m["cost_star_bp"].to_numpy(), color=[C.get(a, "#888") for a in m["arm"]])
    ax.axvline(COST, color="k", ls="--", lw=1.2, label=f"taker round trip {COST:.0f}bp")
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{a} (hold {h}h)" for a, h in
                        zip(m["arm"], [8, 1][: len(m)])])
    for i, v in enumerate(m["cost_star_bp"].to_numpy()):
        if v >= 0:
            ax.text(v + 0.4, i, f"{v:.2f}", va="center", ha="left", fontsize=9)
        else:
            ax.text(v / 2.0, i, f"{v:.2f}", va="center", ha="center",
                    fontsize=9, color="white")
    ax.set_xlabel("cost* = gross PnL per trade, bp of notional")
    ax.set_title("Break-even cost vs the 20bp taker round trip")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(FIG / "f02_cost_hurdle.png", dpi=150)
    plt.close(fig)


def f03_year(year: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4))
    yrs = sorted(year["year"].unique())
    w = 0.38
    for i, arm in enumerate(("A1", "B1")):
        d = year[year.arm == arm].set_index("year").reindex(yrs)
        ax.bar(np.arange(len(yrs)) + (i - 0.5) * w, d["net_bp"].to_numpy(),
               width=w, color=C[arm], label=f"{arm} net per trade")
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(COST, color="k", ls="--", lw=1.0, alpha=0.6,
               label="20bp round-trip cost")
    ax.set_xticks(range(len(yrs)))
    ax.set_xticklabels([str(y) for y in yrs])
    ax.set_ylabel("net PnL per trade, bp")
    ax.set_title("Executable net PnL per trade by year (full sample)")
    ax.text(0.01, 0.02, "only A1 in 2023 clears the 20bp round trip",
            transform=ax.transAxes, fontsize=8, color="0.35")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(FIG / "f03_year_decay.png", dpi=150)
    plt.close(fig)


def f04_funnel(gate: pd.DataFrame) -> None:
    n0 = len(gate)
    n1 = int(gate["G1"].sum())
    n2 = int((gate["G1"] & gate["G2"] & gate["G3"]).sum())
    n3 = int(gate["gate_pass"].sum())
    labels = ["cells tested", "G1 level significant", "G1+G2+G3", "G4 stable = arms"]
    vals = [n0, n1, n2, n3]
    fig, ax = plt.subplots(figsize=(8, 2.8))
    cols = ["#95a5a6", "#7f8c8d", "#5d6d7e", "#c0392b"]
    ax.barh(range(4)[::-1], vals, color=cols)
    for i, v in enumerate(vals):
        ax.text(v + 1.5, 3 - i, str(v), va="center", fontsize=10)
    ax.set_yticks(range(4)[::-1])
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlim(0, max(vals) * 1.12)
    ax.set_xlabel("number of cells")
    ax.set_title("Gate funnel (HANDOFF sec.2, G0-G5)")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(FIG / "f04_gate_funnel.png", dpi=150)
    plt.close(fig)


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(TBL / "p5_daily.csv")
    rules = pd.read_csv(TBL / "p5_rules.csv")
    year = pd.read_csv(TBL / "p5_year.csv")
    gate = pd.read_csv(TBL / "p5_gate.csv")
    f01_equity(daily)
    f02_cost(rules)
    f03_year(year)
    f04_funnel(gate)
    for p in sorted(FIG.glob("f0*.png")):
        print("written %s (%d bytes)" % (p.name, p.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())