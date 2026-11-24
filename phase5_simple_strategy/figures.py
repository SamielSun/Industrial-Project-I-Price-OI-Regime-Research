"""Phase 5 -- figures (f01 equity/drawdown, f02 cost hurdle, f03 by year).

    python -m phase5_simple_strategy.figures

f01  cumulative net PnL and drawdown, both arms, full sample
f02  cost* (gross per trade) against the 20bp taker round trip
f03  executable per-trade PnL by year -- the decay story
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.lines import Line2D

from . import backtest as bt
from . import rules as R

TBL = bt.DATA / "08_strategy" / "tables"
FIG = bt.DATA / "08_strategy" / "figures"
COST = bt.COST_BP
C = {"A1": "#c0392b", "B1": "#2c6fbb"}


def f01_tearsheet(daily: pd.DataFrame, rules: pd.DataFrame) -> None:
    """Two-column tearsheet: NAV and underwater on the left, stats and
    break-even cost on the right."""
    m = rules[(rules.window == "main") & (rules.variant == "base")].set_index("arm")
    fig = plt.figure(figsize=(11.6, 7.0))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.5, 1.0], height_ratios=[1.55, 1.0],
                          hspace=0.28, wspace=0.22)
    ax_eq = fig.add_subplot(gs[0, 0])
    ax_dd = fig.add_subplot(gs[1, 0], sharex=ax_eq)
    ax_tb = fig.add_subplot(gs[:, 1])
    ax_tb.axis("off")

    rows = []
    for arm in ("A1", "B1"):
        d = daily[daily.arm == arm].copy()
        t_ = pd.to_datetime(d["date"])
        eq, _ = bt.equity_path(d)
        cum = eq / bt.EQUITY0 * 100 - 100
        gross = cum + d["cost"].cumsum().to_numpy() / bt.EQUITY0 * 100
        ax_eq.plot(t_, cum, color=C[arm], lw=1.6, label=arm)
        ax_eq.plot(t_, gross, color=C[arm], lw=0.8, ls="--", alpha=0.55)
        wealth = 1.0 + cum / 100.0
        ax_dd.plot(t_, (wealth / np.maximum.accumulate(wealth) - 1.0) * 100,
                   color=C[arm], lw=1.2)
        r = m.loc[arm]
        rows.append((arm, r["ann_ret"] * 100, r["ann_vol"] * 100, r["net_sharpe"],
                     r["mdd"] * 100, r["win_rate"] * 100, int(r["hold_h"]),
                     int(r["n_trades"]), r["exposure"] * 100, r["cost_star_bp"]))

    ax_eq.axhline(0, color="k", lw=0.8)
    for a_ in (ax_eq, ax_dd):
        a_.xaxis.set_major_locator(mdates.YearLocator())
        a_.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        a_.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=(1, 7)))
        a_.tick_params(axis="x", labelsize=8.5)
    ax_eq.set_ylabel("cumulative return, %")
    ax_eq.grid(alpha=0.3)
    handles = [Line2D([0], [0], color=C["A1"], lw=1.6, label="A1"),
           Line2D([0], [0], color=C["B1"], lw=1.6, label="B1"),
           Line2D([0], [0], color="0.4", lw=0.8, ls="--", label="gross of costs")]
    ax_eq.legend(handles=handles, fontsize=8.5, loc="lower left", frameon=False)
    ax_dd.axhline(0, color="k", lw=0.8)
    ax_dd.set_ylabel("drawdown, %")
    ax_dd.grid(alpha=0.3)

    # metrics table: portfolio-level numbers only, per-trade numbers are in Table 2
    labels = ["Annual return, %", "Volatility, %", "Max drawdown, %",
              "Win rate, %"]
    body = [[labels[0], "%.1f" % rows[0][1], "%.1f" % rows[1][1]],
            [labels[1], "%.1f" % rows[0][2], "%.1f" % rows[1][2]],
            [labels[2], "%.1f" % rows[0][4], "%.1f" % rows[1][4]],
            [labels[3], "%.1f" % rows[0][5], "%.1f" % rows[1][5]]]
    tb = ax_tb.table(cellText=body, colLabels=["", "A1", "B1"],
                     cellLoc="right", colLoc="right", colWidths=[0.56, 0.22, 0.22],
                     bbox=[0.02, 0.30, 0.96, 0.56])
    tb.auto_set_font_size(False)
    tb.set_fontsize(10.5)
    for (r_, c_), cell_ in tb.get_celld().items():
        cell_.set_linewidth(0.4)
        cell_.set_edgecolor("0.8")
        cell_.set_height(0.085 if r_ == 0 else 0.115)
        if c_ == 0:
            cell_.set_text_props(ha="left")
        if r_ == 0:
            cell_.set_text_props(weight="bold")

    fig.savefig(FIG / "f01_equity.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def f02_cost(rules: pd.DataFrame) -> None:
    m = rules[(rules.window == "main") & (rules.variant == "base")]
    fig, ax = plt.subplots(figsize=(8, 3.6))
    y = np.arange(len(m))
    ax.barh(y, m["cost_star_bp"].to_numpy(), color=[C.get(a, "#888") for a in m["arm"]])
    ax.axvline(COST, color="k", ls="--", lw=1.2, label=f"taker round trip {COST:.0f}bp")
    ax.axvline(0, color="k", lw=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{a} (hold {R.ARM_BY_NAME[a]['hold']}h)" for a in m["arm"]])
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
        ax.bar(np.arange(len(yrs)) + (i - 0.5) * w, d["cost_star_bp"].to_numpy(),
               width=w, color=C[arm], label=f"{arm} gross per trade")
    ax.axhline(0, color="k", lw=0.8)
    ax.axhline(COST, color="k", ls="--", lw=1.0, alpha=0.6,
               label="20bp round-trip cost")
    ax.set_xticks(range(len(yrs)))
    ax.set_xticklabels([str(y) for y in yrs])
    ax.set_ylabel("gross PnL per trade, bp (before cost)")
    ax.set_title("")
    ax.text(0.01, 0.02, "bars above the dashed line clear the 20bp round trip",
            transform=ax.transAxes, fontsize=8, color="0.35")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(FIG / "f03_year_decay.png", dpi=150)
    plt.close(fig)


def main() -> int:
    FIG.mkdir(parents=True, exist_ok=True)
    daily = pd.read_csv(TBL / "p5_daily.csv")
    rules = pd.read_csv(TBL / "p5_rules.csv")
    year = pd.read_csv(TBL / "p5_year.csv")
    f01_tearsheet(daily, rules)
    f02_cost(rules)
    f03_year(year)
    for p in sorted(FIG.glob("f0*.png")):
        print("written %s (%d bytes)" % (p.name, p.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())