# Phase 5 -- OOS report (D4)

**判定：Phase 5 未通过。**

> **in-sample 声明**：本设计在看过全样本结果之后写定（GUIDANCE.md §8）。
> 下列所有数字都是 in-sample，**不构成盲测样本外结论**。切分只用于报告分段稳定性。

---

## 0. 结论

- **A1**（primary）：净 Sharpe **-1.48**（95% CI [-2.46, -0.51]），毛 Sharpe -0.15，每笔毛边际 -2.25bp vs 20bp 成本，t = -2.22 → **未通过**。
- **B1**（reference）：净 Sharpe **-0.98**（95% CI [-2.08, 0.23]），毛 Sharpe 1.75，每笔毛边际 12.81bp vs 20bp 成本，t = -1.47 → 参照臂，不设失败线。

失败判据（GUIDANCE.md §10）：只有主臂设失败线，净 Sharpe < 0.5 或 |t| < 1.5。

---

## 1. 主结果（表 1）

测试窗口 2024-06 .. 2026-08（27 个月）。cost* = 每笔毛边际（bp，分母为名义本金）；成本固定 20bp 往返。

| arm | variant | n_trades | skip_overlap | skip_cap | price_bp | fund_bp | cost_bp | net_bp | cost_star_bp | gross_sharpe | net_sharpe | ci_lo | ci_hi | ann_ret | ann_vol | mdd |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 | base | 10741 | 3973 | 0 | -4.49 | 2.24 | 20.00 | -22.25 | -2.25 | -0.15 | -1.48 | -2.46 | -0.51 | -0.21 | 0.14 | -0.50 |
| A1 | V1 | 10728 | 3958 | 28 | -0.86 | 2.96 | 20.00 | -17.90 | 2.10 | 0.13 | -1.06 | -2.12 | -0.05 | -0.18 | 0.17 | -0.43 |
| B1 | base | 16379 | 0 | 0 | 12.78 | 0.03 | 20.00 | -7.19 | 12.81 | 1.75 | -0.98 | -2.08 | 0.23 | -0.10 | 0.11 | -0.25 |
| B1 | V1 | 16358 | 0 | 21 | 14.69 | 0.06 | 20.00 | -5.25 | 14.75 | 1.67 | -0.60 | -1.72 | 0.68 | -0.08 | 0.13 | -0.23 |

分折（walk-forward）与最后 3 个月（2026-06..08，属于主测试窗口的 in-sample 子区间，不是留出集）：

| window | arm | variant | n_trades | net_bp | cost_star_bp | gross_sharpe | net_sharpe |
|---|---|---|---:|---:|---:|---:|---:|
| fold1 | A1 | base | 3652 | 6.99 | 26.99 | 2.50 | 0.64 |
| fold1 | A1 | V1 | 3639 | 13.56 | 33.56 | 2.44 | 0.97 |
| fold1 | B1 | base | 10923 | -14.97 | 5.03 | 1.12 | -3.16 |
| fold1 | B1 | V1 | 10895 | -14.76 | 5.24 | 1.07 | -2.83 |
| fold2 | A1 | base | 3865 | -19.38 | 0.62 | 0.04 | -1.26 |
| fold2 | A1 | V1 | 3854 | -14.37 | 5.63 | 0.35 | -0.89 |
| fold2 | B1 | base | 7459 | -1.17 | 18.83 | 3.19 | -0.20 |
| fold2 | B1 | V1 | 7445 | 1.08 | 21.08 | 3.13 | 0.17 |
| fold3 | A1 | base | 3373 | -26.70 | -6.70 | -0.46 | -1.83 |
| fold3 | A1 | V1 | 3373 | -29.67 | -9.67 | -0.56 | -1.71 |
| fold3 | B1 | base | 2947 | -21.87 | -1.87 | -0.12 | -1.39 |
| fold3 | B1 | V1 | 2947 | -24.40 | -4.40 | -0.23 | -1.25 |
| final3m | A1 | base | 888 | -2.02 | 17.98 | 1.46 | -0.16 |
| final3m | A1 | V1 | 888 | 3.23 | 23.23 | 1.41 | 0.20 |
| final3m | B1 | base | 2252 | -16.43 | 3.57 | 0.81 | -3.60 |
| final3m | B1 | V1 | 2243 | -17.42 | 2.58 | 0.49 | -3.24 |

## 2. baseline 对比（表 2）

同一测试窗口、同方向、同持有期、同 universe。

| arm | n_trades | cost_star_bp | gross_sharpe | net_sharpe | ci_lo | ci_hi |
|---|---:|---:|---:|---:|---:|---:|
| A1 (this arm) | 10741 | -2.25 | -0.15 | -1.48 | -2.46 | -0.51 |
| B1 (this arm) | 16379 | 12.81 | 1.75 | -0.98 | -2.08 | 0.23 |
| A1:price_alone | 64234 | 0.57 | 0.06 | -2.11 | -3.24 | -0.88 |
| A1:price_oi | 39283 | -0.55 | -0.06 | -2.05 | -3.22 | -0.81 |
| A1:oi_alone | 56609 | -1.07 | -0.13 | -2.48 | -3.70 | -1.21 |
| A1:funding_alone | 35024 | -3.82 | -0.38 | -2.31 | -3.38 | -1.20 |
| A1:random | 12880 | -12.19 | -1.32 | -3.46 | -4.69 | -2.22 |
| B1:price_alone | 138040 | 2.09 | 0.80 | -6.45 | -8.08 | -5.26 |
| B1:price_oi | 64849 | 1.14 | 0.34 | -5.31 | -7.02 | -4.18 |
| B1:oi_alone | 126342 | 1.25 | 0.57 | -8.40 | -10.24 | -6.94 |
| B1:funding_alone | 105404 | 0.82 | 0.36 | -7.73 | -9.10 | -6.53 |
| B1:random | 16099 | 1.13 | 0.45 | -7.04 | -8.42 | -5.81 |
| buy_and_hold |  |  | -0.51 | -0.51 | -1.71 | 0.75 |

---

## 3. by-regime / by-asset（表 3）

| arm | dim | key | n | price_bp | fund_bp | net_bp |
|---|---|---|---:|---:|---:|---:|
| A1 | cell | 4 | 10741 | -4.49 | 2.24 | -22.25 |
| A1 | state | 0 | 10741 | -4.49 | 2.24 | -22.25 |
| A1 | mkt_vol | high | 4669 | 8.39 | 1.34 | -10.27 |
| A1 | mkt_vol | low | 2561 | -7.02 | 3.90 | -23.12 |
| A1 | mkt_vol | mid | 3511 | -19.76 | 2.22 | -37.54 |
| B1 | cell | 4 | 16379 | 12.78 | 0.03 | -7.19 |
| B1 | state | 0 | 6783 | 12.97 | 0.21 | -6.82 |
| B1 | state | 1 | 6789 | 12.91 | -0.05 | -7.14 |
| B1 | state | 2 | 1087 | 9.35 | -0.12 | -10.77 |
| B1 | state | 3 | 1720 | 13.68 | -0.30 | -6.62 |
| B1 | mkt_vol | high | 16379 | 12.78 | 0.03 | -7.19 |

按合约（每臂 net_bp 最差 8 个与最好 8 个）：

| arm | bucket | sym | n | net_bp |
|---|---|---|---:|---:|
| A1 | worst | PLAYUSDT | 11 | -440.95 |
| A1 | worst | JASMYUSDT | 11 | -282.39 |
| A1 | worst | PYTHUSDT | 11 | -230.05 |
| A1 | worst | IPUSDT | 21 | -222.08 |
| A1 | worst | HIGHUSDT | 37 | -188.77 |
| A1 | worst | EIGENUSDT | 56 | -167.99 |
| A1 | worst | 1000FLOKIUSDT | 61 | -121.73 |
| A1 | worst | SIRENUSDT | 41 | -120.70 |
| A1 | best | MASKUSDT | 19 | 95.25 |
| A1 | best | UBUSDT | 36 | 110.44 |
| A1 | best | MOODENGUSDT | 14 | 116.97 |
| A1 | best | NOTUSDT | 35 | 119.77 |
| A1 | best | SKYAIUSDT | 31 | 146.18 |
| A1 | best | LABUSDT | 16 | 146.38 |
| A1 | best | BONDUSDT | 10 | 178.15 |
| A1 | best | ESPORTSUSDT | 11 | 1097.28 |
| B1 | worst | SIRENUSDT | 12 | -385.49 |
| B1 | worst | RIVERUSDT | 14 | -355.20 |
| B1 | worst | AI16ZUSDT | 10 | -149.92 |
| B1 | worst | SKYAIUSDT | 33 | -105.31 |
| B1 | worst | STRKUSDT | 11 | -105.25 |
| B1 | worst | LABUSDT | 12 | -100.25 |
| B1 | worst | PIPPINUSDT | 10 | -100.24 |
| B1 | worst | 1MBABYDOGEUSDT | 16 | -86.10 |
| B1 | best | BONDUSDT | 23 | 49.66 |
| B1 | best | SANDUSDT | 24 | 52.46 |
| B1 | best | MOODENGUSDT | 22 | 63.25 |
| B1 | best | REEFUSDT | 23 | 73.84 |
| B1 | best | PLAYUSDT | 20 | 77.81 |
| B1 | best | JASMYUSDT | 21 | 87.32 |
| B1 | best | FRONTUSDT | 10 | 89.07 |
| B1 | best | SPXUSDT | 20 | 133.80 |

---

## 4. 价格 / funding / 成本拆分（表 4）

| arm | price_bp | fund_bp | cost_bp | net_bp | cost_star_bp | n_settle | n_settle_missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | -4.49 | 2.24 | 20.00 | -22.25 | -2.25 | 15421 | 14 |
| B1 | 12.78 | 0.03 | 20.00 | -7.19 | 12.81 | 2888 | 1 |

**LUNA 敏感性不做。** LUNA 崩盘（2022-05）落在训练窗口，测试窗口内 A1 的格子里 0 笔、
B1 的格子里 1 笔，剔除后数值不变 —— 这个敏感性在结构上不可能提供信息，因此不报。

---

## 5. 闸门与跳过计数

| arm | src | cell | cut | h | n | level | q | yraw | n_pos | last12 | role |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B1 | P3 | R4 | high | 1 | 36047 | 10.01 | 0.01 | 0.99 | 5 | 0.27 | reference (no funding condition) |
| A1 | P4 | R4 | neg | 8 | 28486 | 17.86 | 0.00 | 2.94 | 4 | 2.57 | primary (note hypothesis) |

| arm | n_events | n_trades | skip_gap | skip_overlap | skip_cap |
|---|---:|---:|---:|---:|---:|
| A1 | 14714 | 10741 | 0 | 3973 | 0 |
| B1 | 16379 | 16379 | 0 | 0 | 0 |

---

## 6. 归因

- **A1**：毛边际 -2.25bp - 成本 20bp = -22.25bp/笔；盈亏平衡成本 -2.25bp，距现实 taker 20bp 差 -22.25bp。
- **B1**：毛边际 12.81bp - 成本 20bp = -7.19bp/笔；盈亏平衡成本 12.81bp，距现实 taker 20bp 差 -7.19bp。

A1：价格 -4.49bp + funding 2.24bp = 毛 -2.25bp，仍低于 20bp 成本。
B1：价格 12.78bp，funding 0.03bp，毛 12.81bp —— 离成本还差 7.19bp。

---

## 7. 图表

![f01 累计净值与回撤](../data/08_strategy/figures/f01_equity.png)

f01 累计净值（实线 = 净，虚线 = 毛）与回撤。测试窗口 2024-06..2026-08，两条臂的 base 变体。

![f02 cost* 对 20bp 成本线](../data/08_strategy/figures/f02_cost_hurdle.png)

f02 每笔毛边际（cost*）对 20bp taker 往返；两条臂都没到线，最好的是 B1（12.81bp，差 7.19bp）。

![f03 逐年可执行净收益](../data/08_strategy/figures/f03_year_decay.png)

f03 逐年毛边际（全样本），虚线是 20bp 成本。越过线的组合：A1 2023。

---

## 8. 复现

    python -m phase5_simple_strategy.build all

产物：data/08_strategy/tables/p5_*.csv 与本文件。
