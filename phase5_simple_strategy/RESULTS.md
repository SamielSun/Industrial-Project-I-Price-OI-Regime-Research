# Phase 5 -- results (D4)

**判定：Phase 5 未通过。**

> **in-sample 声明**：本设计在看过全样本结果之后写定（GUIDANCE.md §8）。
> 下列所有数字都是 in-sample，**不构成盲测样本外结论**。回测覆盖全样本，不留切分。

---

## 0. 结论

- **A1**（primary）：净 Sharpe **-0.62**（95% CI [-1.34, 0.17]），毛 Sharpe 0.73，每笔毛边际 10.38bp vs 20bp 成本，t = -1.33 → **未通过**。
- **B1**（reference）：净 Sharpe **-1.41**（95% CI [-2.10, -0.63]），毛 Sharpe 1.24，每笔毛边际 9.26bp vs 20bp 成本，t = -3.00 → 参照臂，不设失败线。

失败判据（GUIDANCE.md §10）：只有主臂设失败线，净 Sharpe < 0.5 或 |t| < 1.5。

---

## 1. 主结果（表 1）

全样本 2022-03 .. 2026-08（54 个月）。cost* = 每笔毛边际（bp，分母为名义本金）；成本固定 20bp 往返。

| arm | variant | n_trades | skip_overlap | skip_cap | price_bp | fund_bp | cost_bp | net_bp | cost_star_bp | gross_sharpe | net_sharpe | ci_lo | ci_hi | ann_ret | ann_vol | mdd |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A1 | base | 20602 | 7884 | 0 | 8.79 | 1.59 | 20.00 | -9.62 | 10.38 | 0.73 | -0.62 | -1.34 | 0.17 | -0.09 | 0.14 | -0.47 |
| B1 | base | 36047 | 0 | 0 | 9.32 | -0.06 | 20.00 | -10.74 | 9.26 | 1.24 | -1.41 | -2.10 | -0.63 | -0.16 | 0.12 | -0.54 |

## 2. baseline 对比（表 2）

同一全样本、同方向、同持有期、同 universe。

| arm | n_trades | cost_star_bp | gross_sharpe | net_sharpe | ci_lo | ci_hi |
|---|---:|---:|---:|---:|---:|---:|
| A1 (this arm) | 20602 | 10.38 | 0.73 | -0.62 | -1.34 | 0.17 |
| B1 (this arm) | 36047 | 9.26 | 1.24 | -1.41 | -2.10 | -0.63 |
| A1:price_alone | 129428 | 2.41 | 0.25 | -1.72 | -2.56 | -0.82 |
| A1:price_oi | 79041 | 2.86 | 0.28 | -1.58 | -2.43 | -0.66 |
| A1:oi_alone | 113174 | -2.38 | -0.07 | -2.05 | -2.95 | -1.10 |
| A1:funding_alone | 65724 | 3.84 | 0.34 | -1.50 | -2.28 | -0.69 |
| A1:random | 24791 | -7.93 | -0.73 | -2.96 | -3.81 | -2.10 |
| B1:price_alone | 277344 | -2.57 | -0.36 | -6.73 | -7.62 | -5.98 |
| B1:price_oi | 130446 | 0.40 | 0.11 | -5.44 | -6.38 | -4.70 |
| B1:oi_alone | 255857 | -1.60 | -0.24 | -8.39 | -9.77 | -7.33 |
| B1:funding_alone | 201144 | -0.72 | -0.04 | -6.52 | -7.98 | -5.50 |
| B1:random | 35267 | 0.44 | 0.16 | -7.60 | -8.97 | -6.43 |
| buy_and_hold |  |  | -0.17 | 0.57 | -1.08 | 0.73 |

---

## 3. by-regime / by-asset（表 3）

| arm | dim | key | n | price_bp | fund_bp | net_bp |
|---|---|---|---:|---:|---:|---:|
| A1 | cell | 4 | 20602 | 8.79 | 1.59 | -9.06 |
| A1 | state | 0 | 20602 | 8.79 | 1.59 | -9.06 |
| A1 | mkt_vol | high | 8771 | 19.34 | 1.24 | 1.98 |
| A1 | mkt_vol | low | 5281 | 4.83 | 2.50 | -12.63 |
| A1 | mkt_vol | mid | 6362 | -4.93 | 1.38 | -23.14 |
| A1 | mkt_vol | unknown | 188 | 72.05 | 0.60 | 52.59 |
| B1 | cell | 4 | 36047 | 9.32 | -0.06 | -10.14 |
| B1 | state | 0 | 13031 | 17.05 | 0.17 | -3.86 |
| B1 | state | 1 | 14361 | 4.47 | -0.06 | -14.00 |
| B1 | state | 2 | 3114 | 1.90 | -0.24 | -17.17 |
| B1 | state | 3 | 5541 | 8.63 | -0.50 | -10.97 |
| B1 | mkt_vol | high | 36047 | 9.32 | -0.06 | -10.14 |

按合约（每臂 net_bp 最差 8 个与最好 8 个）：

| arm | bucket | sym | n | net_bp |
|---|---|---|---:|---:|
| A1 | worst | LUNAUSDT | 11 | -1997.19 |
| A1 | worst | PLAYUSDT | 11 | -440.95 |
| A1 | worst | REEFUSDT | 17 | -400.32 |
| A1 | worst | IPUSDT | 21 | -222.08 |
| A1 | worst | EIGENUSDT | 56 | -167.99 |
| A1 | worst | ALICEUSDT | 36 | -164.61 |
| A1 | worst | HIGHUSDT | 48 | -151.33 |
| A1 | worst | COMPUSDT | 15 | -127.95 |
| A1 | best | BLURUSDT | 44 | 124.48 |
| A1 | best | BLZUSDT | 32 | 129.79 |
| A1 | best | RSRUSDT | 10 | 132.74 |
| A1 | best | MINAUSDT | 17 | 138.35 |
| A1 | best | SKYAIUSDT | 31 | 146.18 |
| A1 | best | LABUSDT | 16 | 146.38 |
| A1 | best | BONDUSDT | 10 | 178.15 |
| A1 | best | ESPORTSUSDT | 11 | 1097.28 |
| B1 | worst | LUNAUSDT | 10 | -557.42 |
| B1 | worst | SIRENUSDT | 12 | -385.49 |
| B1 | worst | RIVERUSDT | 14 | -355.20 |
| B1 | worst | AI16ZUSDT | 10 | -149.92 |
| B1 | worst | HNTUSDT | 20 | -134.33 |
| B1 | worst | SKYAIUSDT | 33 | -105.31 |
| B1 | worst | STRKUSDT | 11 | -105.25 |
| B1 | worst | LABUSDT | 12 | -100.25 |
| B1 | best | ROSEUSDT | 16 | 59.97 |
| B1 | best | MOODENGUSDT | 22 | 63.25 |
| B1 | best | FLMUSDT | 14 | 65.76 |
| B1 | best | CKBUSDT | 33 | 74.25 |
| B1 | best | PLAYUSDT | 20 | 77.81 |
| B1 | best | CELRUSDT | 40 | 82.78 |
| B1 | best | FRONTUSDT | 10 | 89.07 |
| B1 | best | SPXUSDT | 20 | 133.80 |

---

## 4. 价格 / funding / 成本拆分（表 4）

| arm | price_bp | fund_bp | cost_bp | net_bp | cost_star_bp | n_settle | n_settle_missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| A1 | 8.79 | 1.59 | 20.00 | -9.62 | 10.38 | 25641 | 14 |
| B1 | 9.32 | -0.06 | 20.00 | -10.74 | 9.26 | 5606 | 1 |

**LUNA 敏感性不做。** LUNA 崩盘（2022-05）在全样本内，A1 的格子里 0 笔、B1 的格子里 1 笔，
剔除后数值不变 —— 这个敏感性在结构上不可能提供信息，因此不报。

---

## 5. 闸门与跳过计数

| arm | src | cell | cut | h | n | level | q | yraw | n_pos | last12 | role |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| B1 | P3 | R4 | high | 1 | 36047 | 10.01 | 0.02 | 0.99 | 5 | 0.27 | reference (no funding condition) |
| A1 | P4 | R4 | neg | 8 | 28486 | 17.86 | 0.01 | 2.94 | 4 | 2.57 | primary (note hypothesis) |

| arm | n_events | n_trades | skip_gap | skip_overlap | skip_cap |
|---|---:|---:|---:|---:|---:|
| A1 | 28486 | 20602 | 0 | 7884 | 0 |
| B1 | 36047 | 36047 | 0 | 0 | 0 |

---

## 6. 归因

- **A1**：毛边际 10.38bp - 成本 20bp = -9.62bp/笔；盈亏平衡成本 10.38bp，距现实 taker 20bp 差 -9.62bp。
- **B1**：毛边际 9.26bp - 成本 20bp = -10.74bp/笔；盈亏平衡成本 9.26bp，距现实 taker 20bp 差 -10.74bp。

A1：价格 8.79bp + funding 1.59bp = 毛 10.38bp，仍低于 20bp 成本。
B1：价格 9.32bp，funding -0.06bp，毛 9.26bp —— 离成本还差 10.74bp。

---

## 7. 图表

![f01 累计净值与回撤](../data/08_strategy/figures/f01_equity.png)

f01 累计净值（实线 = 净，虚线 = 毛）与回撤。全样本 2022-03..2026-08，两条臂。

![f02 cost* 对 20bp 成本线](../data/08_strategy/figures/f02_cost_hurdle.png)

f02 每笔毛边际（cost*）对 20bp taker 往返；两条臂都没到线，最好的是 A1（10.38bp，差 9.62bp）。

![f03 逐年可执行净收益](../data/08_strategy/figures/f03_year_decay.png)

f03 逐年毛边际（全样本），虚线是 20bp 成本。越过线的组合：A1 2023。

---

## 8. 复现

    python -m phase5_simple_strategy.build all

产物：data/08_strategy/tables/p5_*.csv 与本文件。
