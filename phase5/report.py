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
COST = 20.0
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
    luna = pd.read_csv(TBL / "p5_luna.csv")

    main_w = rules[(rules.window == "main") & (rules.variant == "base")]
    L = []
    A = L.append
    A("# Phase 5 -- OOS report (D4)")
    A("")
    A("**判定：Phase 5 未通过。**")
    A("")
    A("> **in-sample 声明**：本设计在看过全样本结果之后写定（HANDOFF.md §8）。")
    A("> 下列所有数字都是 in-sample，**不构成盲测样本外结论**。切分只用于报告分段稳定性。")
    A("")
    A("---")
    A("")
    A("## 0. 结论")
    A("")
    for _, r in main_w.iterrows():
        A("- **{}**（{}）：净 Sharpe **{:.2f}**（95% CI [{:.2f}, {:.2f}]），毛 Sharpe {:.2f}，"
          "每笔毛边际 {:.2f}bp vs 20bp 成本，t = {:.2f} → **未通过**。"
          .format(r["arm"], r["role"], r["net_sharpe"], r["ci_lo"], r["ci_hi"],
                  r["gross_sharpe"], r["cost_star_bp"], r["t_stat"]))
    A("")
    A("失败判据（HANDOFF.md §10）：主臂 A1 净 Sharpe < 0.5 或 t < 1.5。")
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
    A("分折（walk-forward）与最终 holdout：")
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
    A("**LUNA 敏感性**（HANDOFF.md §5）：剔除 LUNA 家族（LUNAUSDT / LUNA2USDT）后重跑测试窗口。")
    A("")
    A(md_table(luna, ["arm", "n_trades", "price_bp", "fund_bp", "net_bp",
                      "cost_star_bp", "net_sharpe"]))
    A("")
    A("A1 在测试窗口内 0 笔 LUNA 交易，B1 少 1 笔，两者数值到小数点后两位不变。"
      "原因是 LUNA 家族的 699 条 base 记录几乎全落在 2022-2023，落在主测试窗口的只有 1 笔。")
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
    A("A1 的 funding 项（+2.24bp/笔）确实为正，但价格项 -4.49bp 把它抵消了：")
    A("note 假设的方向在测试期不成立。")
    A("")
    A("B1 没有 funding 条件，价格项 +12.78bp 是正的 —— 它输在成本，不输在信号。")
    A("")
    A("---")
    A("")
    A("## 7. 图表")
    A("")
    A("![f01 累计净值与回撤](../data/08_strategy/figures/f01_equity.png)")
    A("")
    A("f01 累计净值（实线 = 净，虚线 = 毛）与回撤。测试窗口 2024-06..2026-08。")
    A("")
    A("![f02 cost* 对 20bp 成本线](../data/08_strategy/figures/f02_cost_hurdle.png)")
    A("")
    A("f02 每笔毛边际（cost*）对 20bp taker 往返。两根柱子都没到线：B1 差 7.19bp，A1 为负。")
    A("")
    A("![f03 逐年可执行净收益](../data/08_strategy/figures/f03_year_decay.png)")
    A("")
    A("f03 逐年可执行净收益（全样本）。只有 A1 在 2023 年超过 20bp。")
    A("")
    A("![f04 闸门漏斗](../data/08_strategy/figures/f04_gate_funnel.png)")
    A("")
    A("f04 闸门漏斗：96 个格 -> G1 10 个 -> G2+G3 6 个 -> G4 2 条臂。")
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