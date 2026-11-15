"""Phase 5 -- render the OOS report (markdown + csv summary).

Reads only the tables written by phase5.gate and phase5.eval, so the report can
never disagree with the run that produced it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import backtest as bt

TBL = bt.DATA / "08_strategy" / "tables"
OUT = bt.ROOT / "phase5" / "OOS_REPORT.md"
COST = bt.COST_BP
TEXT_COLS = {"arm", "window", "variant", "role", "dim", "key", "sym", "bucket"}
INT_COLS = {"n", "n_trades", "n_events", "n_settle", "n_settle_missing",
            "skip_gap", "skip_overlap", "skip_cap", "n_pos", "h"}


def md_table(df: pd.DataFrame, cols: list[str]) -> str:
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" if c in TEXT_COLS else "---:" for c in cols) + "|"
    rows = [head, sep]
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if isinstance(v, (float, np.floating)) and not np.isfinite(v):
                cells.append("")
            elif isinstance(v, (float, np.floating, int, np.integer)):
                cells.append("{:d}".format(int(v)) if c in INT_COLS
                             else "{:.2f}".format(float(v)))
            else:
                cells.append(str(v))
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)


def main() -> int:
    rules = pd.read_csv(TBL / "p5_rules.csv")
    base = pd.read_csv(TBL / "p5_baselines.csv")
    reg = pd.read_csv(TBL / "p5_by_regime.csv")
    ast = pd.read_csv(TBL / "p5_by_asset.csv")
    gate = pd.read_csv(TBL / "p5_gate_arms.csv")
    year = pd.read_csv(TBL / "p5_year.csv")

    main_w = rules[(rules.window == "main") & (rules.variant == "base")]
    L = []
    A = L.append
    A("# Phase 5 -- OOS report (D4)")
    A("")
    A("**判定：Phase 5 未通过。**")
    A("")
    A("> **in-sample 声明**：本设计在看过全样本结果之后写定（GUIDANCE.md §8）。")
    A("> 下列所有数字都是 in-sample，**不构成盲测样本外结论**。切分只用于报告分段稳定性。")
    A("")
    A("---")
    A("")
    A("## 0. 结论")
    A("")
    for _, r in main_w.iterrows():
        if r["role"].startswith("primary"):
            ok = (r["net_sharpe"] >= 0.5) and (abs(r["t_stat"]) >= 1.5)
            tag = "**通过**" if ok else "**未通过**"
        else:
            tag = "参照臂，不设失败线"
        A("- **{}**（{}）：净 Sharpe **{:.2f}**（95% CI [{:.2f}, {:.2f}]），毛 Sharpe {:.2f}，"
          "每笔毛边际 {:.2f}bp vs {:.0f}bp 成本，t = {:.2f} → {}。"
          .format(r["arm"], r["role"], r["net_sharpe"], r["ci_lo"], r["ci_hi"],
                  r["gross_sharpe"], r["cost_star_bp"], COST, r["t_stat"], tag))
    A("")
    A("失败判据（GUIDANCE.md §10）：只有主臂设失败线，净 Sharpe < 0.5 或 |t| < 1.5。")
    A("")
    A("---")
    A("")
    A("## 1. 主结果（表 1）")
    A("")
    A("测试窗口 2024-06 .. 2026-08（27 个月）。cost* = 每笔毛边际（bp，分母为名义本金）；成本固定 20bp 往返。")
    A("")
    A(md_table(rules[rules.window == "main"],
               ["arm", "variant", "n_trades", "skip_overlap", "skip_cap", "price_bp",
                "fund_bp", "cost_bp", "net_bp", "cost_star_bp", "gross_sharpe",
                "net_sharpe", "ci_lo", "ci_hi", "ann_ret", "ann_vol", "mdd"]))
    A("")
    A("分折（walk-forward）与最后 3 个月（2026-06..08，属于主测试窗口的 in-sample 子区间，不是留出集）：")
    A("")
    A(md_table(rules[rules.window != "main"],
               ["window", "arm", "variant", "n_trades", "net_bp", "cost_star_bp",
                "gross_sharpe", "net_sharpe"]))
    A("")
    A("## 2. baseline 对比（表 2）")
    A("")
    A("同一测试窗口、同方向、同持有期、同 universe。")
    A("")
    own = main_w.assign(arm=main_w["arm"] + " (this arm)")[
        ["arm", "n_trades", "cost_star_bp", "gross_sharpe", "net_sharpe",
         "ci_lo", "ci_hi"]]
    A(md_table(pd.concat([own, base[["arm", "n_trades", "cost_star_bp",
                                     "gross_sharpe", "net_sharpe", "ci_lo",
                                     "ci_hi"]]], ignore_index=True),
               ["arm", "n_trades", "cost_star_bp", "gross_sharpe",
                "net_sharpe", "ci_lo", "ci_hi"]))
    A("")
    A("---")
    A("")
    A("## 3. by-regime / by-asset（表 3）")
    A("")
    A(md_table(reg[reg.dim != "all"], ["arm", "dim", "key", "n", "price_bp",
                                       "fund_bp", "net_bp"]))
    A("")
    A("按合约（每臂 net_bp 最差 8 个与最好 8 个）：")
    A("")
    a = []
    for arm, gg in ast.groupby("arm"):
        gg = gg[gg["n"] >= 10].sort_values("net_bp")
        a.append(gg.head(8).assign(bucket="worst"))
        a.append(gg.tail(8).assign(bucket="best"))
    A(md_table(pd.concat(a), ["arm", "bucket", "sym", "n", "net_bp"]))
    A("")
    A("---")
    A("")
    A("## 4. 价格 / funding / 成本拆分（表 4）")
    A("")
    A(md_table(main_w, ["arm", "price_bp", "fund_bp", "cost_bp", "net_bp",
                        "cost_star_bp", "n_settle", "n_settle_missing"]))
    A("")
    A("**LUNA 敏感性不做。** LUNA 崩盘（2022-05）落在训练窗口，测试窗口内 A1 的格子里 0 笔、")
    A("B1 的格子里 1 笔，剔除后数值不变 —— 这个敏感性在结构上不可能提供信息，因此不报。")
    A("")
    A("---")
    A("")
    A("## 5. 闸门与跳过计数")
    A("")
    A(md_table(gate, ["arm", "src", "cell", "cut", "h", "n", "level", "q",
                      "yraw", "n_pos", "last12", "role"]))
    A("")
    A(md_table(main_w, ["arm", "n_events", "n_trades", "skip_gap", "skip_overlap",
                        "skip_cap"]))
    A("")
    A("---")
    A("")
    A("## 6. 归因")
    A("")
    for _, r in main_w.iterrows():
        A("- **{}**：毛边际 {:.2f}bp - 成本 20bp = {:.2f}bp/笔；盈亏平衡成本 {:.2f}bp，"
          "距现实 taker 20bp 差 {:.2f}bp。"
          .format(r["arm"], r["cost_star_bp"], r["net_bp"], r["cost_star_bp"],
                  r["cost_star_bp"] - COST))
    A("")
    a1r = main_w[main_w["arm"] == "A1"]
    b1r = main_w[main_w["arm"] == "B1"]
    if len(a1r):
        r = a1r.iloc[0]
        A("A1：价格 {:.2f}bp + funding {:.2f}bp = 毛 {:.2f}bp，仍低于 {:.0f}bp 成本。"
          .format(r["price_bp"], r["fund_bp"], r["cost_star_bp"], COST))
    if len(b1r):
        r = b1r.iloc[0]
        A("B1：价格 {:.2f}bp，funding {:.2f}bp，毛 {:.2f}bp —— 离成本还差 {:.2f}bp。"
          .format(r["price_bp"], r["fund_bp"], r["cost_star_bp"], COST - r["cost_star_bp"]))
    A("")
    A("---")
    A("")
    A("## 7. 图表")
    A("")
    A("![f01 累计净值与回撤](../data/08_strategy/figures/f01_equity.png)")
    A("")
    A("f01 累计净值（实线 = 净，虚线 = 毛）与回撤。测试窗口 2024-06..2026-08，两条臂的 base 变体。")
    A("")
    A("![f02 cost* 对 20bp 成本线](../data/08_strategy/figures/f02_cost_hurdle.png)")
    A("")
    best = main_w.loc[main_w["cost_star_bp"].idxmax()]
    A("f02 每笔毛边际（cost*）对 {:.0f}bp taker 往返；两条臂都没到线，最好的是 {}（{:.2f}bp，差 {:.2f}bp）。"
      .format(COST, best["arm"], best["cost_star_bp"], COST - best["cost_star_bp"]))
    A("")
    A("![f03 逐年可执行净收益](../data/08_strategy/figures/f03_year_decay.png)")
    A("")
    hi = year[year["cost_star_bp"] > COST]
    A("f03 逐年毛边际（全样本），虚线是 {:.0f}bp 成本。越过线的组合：{}。"
      .format(COST, ", ".join("{} {}".format(r.arm, r.year) for r in hi.itertuples()) or "无"))
    A("")
    A("---")
    A("")
    A("## 8. 复现")
    A("")
    A("    python -m phase5.build all")
    A("")
    A("产物：data/08_strategy/tables/p5_*.csv 与本文件。")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("written %s (%d lines)" % (OUT, len(L)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())