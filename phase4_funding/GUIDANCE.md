# Phase 4 — Funding × Regime 交互 · 实施指南

**状态。** 设计已锁定。本文件规定 Phase 4 做什么、怎么做。与 `HANDOFF.md` §3.5–3.7 冲突时以本文件为准；导师的 idea note 是 Phase 4 的最终依据。本文件不含实现代码。

**读者。** 实现者与学术导师。sponsor 看最终表格，不看本文件。

**被取代的产物。** 旧的 `l1_cellmeans` / `l2_interactions` 表（16-γ 设计）已在清理中删除；E1/E2 取代它们，不要引用旧表。

---

## 0. note 要求什么

note 对 Phase 4 的唯一直接定义在 §10：

> **Phase 4: Funding Interaction**
> - Split each regime by funding state: negative, neutral, high, and extreme.
> - Output: 4x4 table of price/OI regimes versus funding states with forward return and volatility by bucket.
>
> （译：把每个 regime 按 funding 状态拆成 negative / neutral / high / extreme 四档；输出 price/OI regime × funding state 的 4×4 表，按 bucket 给 forward return 和 volatility。）

两段支撑材料都明确是示例：

> **§7** — "Funding should be used as a conditioning variable, not necessarily as the primary signal."
>
> （译：funding 应作为条件变量，而不一定是主信号。）
>
> **§7 Example research questions:**
> - Does Price Up + OI Up perform better when funding is neutral?
> - Does Price Up + OI Up become a reversal signal when funding is extreme?
> - Does Price Down + OI Down mean-revert faster after high liquidation/funding stress?
> - Does Price Down + OI Up predict continuation when funding is still neutral?
>
> （译：① Price Up + OI Up 在 funding 为 neutral 时表现更好吗？② Price Up + OI Up 在 funding 为 extreme 时是否变成反转信号？③ Price Down + OI Down 在高清算/funding 压力后是否更快均值回归？④ Price Down + OI Up 在 funding 仍为 neutral 时是否预测延续？）

> **§11 Example Output Table** — 六行 — "These are hypotheses, not conclusions."
>
> （译：示例输出表，六行；"这些是假设，不是结论。"）

对 Phase 4 的含义：

- 交付物是一张**分层的 4×4 条件表现表**，不是模型。
- 示例只是这张表的切片，不是完整的假设清单。
- note 没有规定回归、对比家族、多重校正或经济阈值。
- note §9 的 baseline（price alone、OI alone、funding alone、random timing）属于 Phase 3：实验 5–9 与实验 8 已经覆盖，Phase 4 不重复。
- E2 的 12 个 within-regime 对比是**项目**对 note 示例问题的形式化，不是 note 的要求；它存在是因为项目需要一个预先声明的推断层来支撑 Phase 5 闸门。写作时必须标注这一点。

---

## 1. 锁定设计

| 项 | 锁定选择 |
|---|---|
| 主对象 | **E1**：4×4 条件面。**E2**：12 个 within-regime funding 对比。 |
| Funding 状态 | 按 note 嵌套定义：`negative` f ≤ p25；`neutral` p25 < f ≤ p75；`high` f > p75（**包含 extreme**）；`extreme` f > p90。`high ⊇ extreme`。 |
| Regime | R1 价涨 + OI 增；R2 涨 + OI 减；R3 跌 + OI 增；R4 跌 + OI 减。 |
| 收益口径 | `fwd_h`（raw，note §8 A）与 `y_raw`（市场中性，Phase 3 headline）。判定用 `y_raw`；`fwd_h` 是 note 字面的描述口径。 |
| 波动口径 | 事件后 h 小时的已实现波动 `rv`。E1 报 `rv` 的算术平均与中位数（Phase 3 口径）。E2 用 `lrv = log(rv)`，报 `exp(对比) − 1` 的 %。 |
| 期限 | 1、4、8、24 小时。 |
| 权重 | event 等权为主；合约-日等权（one vote per contract-day）为稳健性。 |
| 推断 | 合约 + 月份双向固定效应；CGM 双向聚类 SE；每个 12 检验家族内 BH；逐对比 drop5。**不做 16-γ ANOVA。** |
| 表内统计量 | 均值 + 中位数；均值的聚类 CI；n 单独一张表。E1 不挂 p 值。 |
| Phase 5 闸门 | 只看收益：任意 `y_raw` 对比过 BH 12 + drop5 即开。波动不 gate，只作风险 overlay。 |
| Out of scope | baseline、IC、绝对 bp/day、β 附录、16-γ 交互、阈值优化、跨交易所、Phase 5 回测、R4 stress（Phase 3 实验 14b）。 |

---

## 2. 定义与样本

### 2.1 样本

继承 Phase 1–3 的冻结口径；不重建。

| 项 | 值 |
|---|---|
| Universe | 按过去 30 天报价成交额排名的月度 top-50，四道闸；249 个合约；54 个月（2022-03 … 2026-08）。 |
| 事件 | 1h bar，|Δprice| 与 |ΔOI| 同时超过该合约过去 90 天 p70（≥30 天历史）。 |
| Headline 样本 | `in_universe` 且 `excl_reason == "ok"`；`cell ∈ {1,2,3,4}`；h=1 有 256,076 个有有效前向收益的事件行。 |
| 无 funding 状态 | 219 个事件（0.09%）四个 funding bool 全 False（p25 缺失）。从 E1/E2/E5 排除；报告数量。 |
| E1/E2 样本（h=1） | 255,857 行。h=4/8/24 只差 `ok_{h}h` 的损失。 |
| 合约-月 | 2,700 = 50 个合约 × 54 个月。 |
| lrv 缺失 | h=1：2,244 个事件行（0.9%）；只在波动率分析中剔除。 |

### 2.2 Regime

`cell` 1–4，沿用 Phase 2/3 的定义，不改。

### 2.3 Funding 状态——嵌套，不是分区

每个合约，过去 90 日历天的结算 funding 序列，取 p25 / p75 / p90，从最近一次结算起按阶梯函数取值。严格 `>`（note 说 "above"）；不要改成 `≥`。

```
negative : f ≤ p25
neutral  : p25 < f ≤ p75
high     : f > p75        # 包含 extreme
extreme  : f > p90        # high 的子集
```

四列**不是互斥的**。当 p75 == p90 时，`high` 与 `extreme` 是同一批行。

仅用于估计，定义四个互斥的潜在状态：

```
s0 = negative
s1 = neutral
s2 = high-only   (p75 < f ≤ p90)
s3 = extreme     (f > p90)
```

报告的 `high` 列是并集 `s2 ∪ s3`；它的均值是 `s2` 与 `s3` 均值的样本量加权平均。互斥状态不进主表；它们是 E5 的附录拆分，也是 E2 的估计基础。

### 2.4 收益与波动因变量

- `fwd_h = close_{t+h} / close_t − 1`。**不在 panel 里**；从 `data/06_event_study/forward/freq=1h`（或 `events/events_1h.parquet`）按 `(symbol, ts_end)` 关联。panel 的 `symbol` code 通过 `panel/freq=1h/symbols.parquet` 映射成字符串；`hour` 通过 `ts_end = 2021-12-01 UTC + hour 小时` 映射。
- `y_raw` 已在 panel 里：`fwd_h` 减去同时刻全市场池（7,010,789 行）的等权均值。市场中性、不截尾、不翻正。
- `rv_h` 是事件后 h 小时的已实现方差；`lrv = log(rv_h)`。两者都在 forward/panel 管线里；panel 携带 `lrv`。

单位：收益用 bp（×1e4）；波动水平用 %（rv × 100）；波动对比用 %（`exp(Δlog rv) − 1`）。

### 2.5 权重

- **Event 等权**：每个事件行一个观测。这是 note 的事件研究单位。
- **合约-日等权**：每个 `(symbol, UTC 日, regime, 互斥 funding 状态)` 一个观测；组内对因变量取均值；同样的 FE 模型跑在组均值上。日 = `hour // 24`，与 Phase 3 实验 15 一致。
- 对嵌套的 `high` 列：event 权重下，并集均值用事件数加权；合约-日权重下，用合约-日-格数加权。不要混。
- 合约-日权重是 note §5 "daily aggregation for robustness" 在 Phase 4 的对应物。单独的日聚合 4×4（E6）可选，不在锁定设计里；Phase 3 实验 15 已覆盖 regime 层的日聚合。

---

## 3. 估计量与记号

对 regime `r` 与互斥 funding 状态 `s`，令 `m_{r,s}` 为扣掉合约+月份固定效应后的格均值：

```
y_it = Σ_{r,s} m_{r,s} · 1{regime=r, state=s} + α_contract + λ_month + ε_it
```

16 个互斥格 dummy 是分区；与 FE 常数有一个共线（16 个 dummy 之和恒为 1）。丢掉一个参照格（R4 × s3），估 15 个系数，16 个 `m` 只识别到常数；所有报告量都是差，常数会抵消。

报告的嵌套格均值：

```
μ(r, neg)     = m_{r,s0}
μ(r, neu)     = m_{r,s1}
μ(r, high)    = w2·m_{r,s2} + w3·m_{r,s3},   w2 = n_{r,s2}/(n_{r,s2}+n_{r,s3}), w3 = 1 − w2
μ(r, extreme) = m_{r,s3}
```

`n` 是当前权重下该格的观测数（事件行或合约-日-格）。权重是实现的样本量，视为固定。

对比向量及其 SE 是 15 个系数的线性组合，用 CGM 协方差：

```
V = V_contract + V_month − V_contract×month
SE(c) = sqrt(c' V c)
```

12 个对比的 `c` 见 §5.2。

---

## 4. E1 —— 4×4 条件面

**目的。** note 的字面输出：按 bucket 给 forward return 与 volatility。

**样本。** E1/E2 样本（§2.1），一次一个期限。

**表布局。** 行 R1–R4；列 `negative / neutral / high（含 extreme）/ extreme`；每个期限、每种权重一张表。

每格报告：

| 字段 | 定义 |
|---|---|
| `fwd_mean`、`fwd_median` | 原始前向收益，bp。 |
| `y_mean`、`y_median` | 市场中性 `y_raw`，bp。 |
| `rv_mean`、`rv_median` | 已实现波动水平，%（`rv` 的算术均值/中位数；Phase 3 口径）。 |
| CI | 每个均值的 95% CI，按合约与月份 CGM 双向聚类。描述性；E1 不挂 p 值。 |

另附一张 4×4 的 n 表，每格报告：

| 字段 | 定义 |
|---|---|
| `n_obs` | 事件行（event 权重）或合约-日-格组（合约-日权重）。 |
| `n_cdays` | 格内唯一 `(symbol, UTC 日)` 数。 |
| `n_cmonths` | 格内唯一 `(symbol, 日历月)` 数。 |

对嵌套列：`high` 的 `n_obs` 是 `s2` 与 `s3` 之和；`n_cdays` 与 `n_cmonths` 是并集上的**唯一**计数（一个合约-日可能同时含 `s2` 和 `s3`，不要把两者相加）。

**h=1 的预期锚点（event 权重，y_raw）**——用于校验：

| 格 | n 行数 | 合约-月数 |
|---|---:|---:|
| negative（全 regime） | 93,489 | 9,499 |
| neutral（全 regime） | 123,907 | 9,461 |
| high-only（全 regime） | 18,834 | 3,377 |
| extreme（全 regime） | 19,627 | 2,777 |
| high（含 extreme，全 regime） | 38,461 | 4,471（格级；不同 regime 的并集会重叠） |
| R1 × neutral | 37,038 | 2,384 |
| R1 × high（含 extreme） | 13,184 | 1,183（并集唯一数，不是 902+752） |
| R1 × extreme | 6,905 | 752 |
| R3 × extreme | 2,416 | 584（最薄的互斥格） |

400 合约-月闸（旧 handoff §3.7）保留为**标记**，不是过滤：低于 400 的格打标。h=1 最薄的互斥格是 584，所以没有格被标记；仍然要报告这个检查。

**输出。** `phase4_funding/tables/e1_surface.parquet` + `.csv`，长表：每行一个 `(weighting, h, regime, funding)`。

---

## 5. E2 —— within-regime funding 对比

**目的。** 对 note 的 row-wise 示例问题做正式读数：在每个 regime 内部，表现如何随 funding 状态变化？这是项目的操作化，不是 note 的要求。

**样本。** 与 E1 同一批行，每个期限、每种权重。

**因变量。**

- `y_raw`：主口径，进 BH 家族。
- `fwd_h`：note 字面的描述口径，报估计 + 95% CI，**不进 BH，不报 p_bh**。
- `lrv`：波动率，进单独的 BH 家族，报 `exp(对比) − 1` 的 %。

### 5.1 对比

对每个 regime `r`（4 个）与每个 funding 状态 `f ∈ {negative, high, extreme}`（3 个），都以 `neutral` 为参照：

```
C1(r) = μ(r, negative) − μ(r, neutral)
C2(r) = μ(r, high)     − μ(r, neutral)    # high 含 extreme
C3(r) = μ(r, extreme)  − μ(r, neutral)    # high 的子集
```

每个 `(dv, h, weighting)` 有 12 个对比。三个对比按构造相关（high 集合包含 extreme 集合）；BH 对 12 个一起做。

派生的尾部增量，只作解读（不单独检验）：

```
C4(r) = μ(r, extreme) − μ(r, high) = w2 · (m_{r,s3} − m_{r,s2})
```

在正文或附录里与 C2/C3 并排报告；不要加进 BH 家族。

### 5.2 估计步骤

1. 构造 16 个互斥格 dummy（`regime × {s0,s1,s2,s3}`）。
2. event 权重：在事件行上估 FE 模型。
   合约-日权重：先聚合到 `(symbol, day, regime, state)` 的组均值，再在组均值上估同一个 FE 模型。
3. 取 15 个系数与 CGM 协方差；用当前权重的计数 `w2`、`w3` 组成嵌套均值 `μ(r, high)`。
4. 构造 12 个对比向量 `c`；估计 = `c'β`，SE = `sqrt(c'Vc)`，`t = estimate/SE`，`p` 双侧正态。
5. BH 在 12 个对比内、按 `(dv, h, weighting)` 分别做；`y_raw` 与 `lrv` 各自一个家族；`fwd` 是描述性，不做 BH。
6. `t_drop5`：对每个对比，计算影响函数 `ψ_c = (X̃ c) · û`；按 `|Σ ψ_c|` 给合约打分；剔掉最大的 5 个；重新估 FE 模型与对比；报告 `t`。
7. 对过了 BH 的对比，标记 `|t_drop5| ≤ 1.96` 的情况。

### 5.3 表

每行一个 `(weighting, dv, h, regime, contrast)`：

| 列 | 含义 |
|---|---|
| `estimate` | `y_raw`/`fwd` 用 bp；`lrv` 用 log 点。 |
| `estimate_pct` | 仅 `lrv`：`(exp(estimate) − 1) × 100`。 |
| `se` | CGM 聚类 SE，估计尺度。 |
| `t`、`p` | 双侧。 |
| `p_bh` | 12 个内的 BH；`fwd` 为 `NA`。 |
| `t_drop5` | 剔 5 个合约后的 t；`fwd` 不计算则为 `NA`。 |
| `n_obs`、`n_cmonths` | 对比的格规模（high 用并集）。 |
| `in_bh` | `y_raw`、`lrv` 为 `TRUE`；`fwd` 为 `FALSE`。 |

**输出。** `phase4_funding/tables/e2_contrasts.parquet` + `.csv`。

---

## 6. E3 —— column profile（描述性）

**目的。** 4×4 的另一条边际：在每个 funding 状态内部，四个 regime 怎么比？这是描述性 context，不是第二个检验家族。

**样本。** 与 E1 相同。

**表。** 每个 `(h, weighting)` 一张：行 = funding 状态 `negative / neutral / high / extreme`；列 = R1–R4。每格报 `fwd_mean`、`y_mean`、`rv_mean`，以及各均值的聚类 95% CI；n 另表。

不挂 p 值。如果 column profile 出现强模式，后续可补一组「regimes vs R4 within funding state」的对比，但不在锁定设计里。

**输出。** `phase4_funding/tables/e3_column_profile.parquet` + `.csv`。

---

## 7. E4 —— 假设映射

**目的。** 用 E1/E2 的输出去读 note §11 的六个示例行。六行是锚点，不是完整假设集；其余格是 exploratory。

每个锚点报告：

| 锚点（note §11） | 格 | 读什么 | 判定 |
|---|---|---|---|
| R1 + neutral → continuation | (R1, neutral) | `fwd` 均值/中位数符号；`y_raw` vs R1 其他 funding 格 | consistent / inconsistent / unclear |
| R1 + extreme positive → crowded reversal | (R1, extreme) | `fwd` 符号；C3(R1)；C4(R1) | consistent / inconsistent / unclear |
| R2 + any funding → short-covering exhaustion | R2 行 | 三个对比 C1/C2/C3(R2) ≈ 0（profile 平坦） | consistent / inconsistent / unclear |
| R3 + neutral → downside continuation | (R3, neutral) | `fwd` 符号；`y_raw` vs R3 其他 funding 格 | consistent / inconsistent / unclear |
| R3 + extreme negative → short-squeeze | (R3, negative) vs (R3, neutral) | C1(R3) > 0 | consistent / inconsistent / unclear |
| R4 + stress / high vol → mean reversion | 不是 funding 格 | out of scope；Phase 3 实验 14b | out of scope |

代理口径提醒：标签没有单边的 extreme-negative 档；note 的 "extreme negative" 在 R3 short-squeeze 锚点上用 `negative`（f ≤ p25）代理。表注要写明。

判定规则（定性，不新增检验）：

- **consistent**：观察到的方向与 note 的预期一致，且相关 `y_raw` 对比过 BH 12 + drop5（若适用对比）。
- **inconsistent**：方向相反，或对比显著地反向。
- **unclear**：方向一致但对比没过 BH/drop5，或格太薄；报告 n。

`fwd` 的符号是 note 字面的 continuation/reversal 读数；`y_raw` 是判定口径。六个锚点不是确认性家族，不要对它们做 BH。

**输出。** `phase4_funding/tables/e4_hypothesis_map.csv`。

---

## 8. E5 —— 退化诊断

**目的。** 披露在退化的 funding 日上 `high` 与 `extreme` 是同一批行，并提供 high-only vs extreme 的拆分。

### 8.1 表注（所有 E1/E2 表）

写明：

- 四个 funding 列是重叠条件，不是分区：`high = f > p75` 包含 `extreme = f > p90`。
- 在估计样本里，`p75 == p90` 占 **56.96%** 的事件行（h=1）与 **48.9%** 的合约-月；在这些行上 `high` 与 `extreme` 选到同一批观测，`high` 不含 high-only 行。
- 全标签（7,022,757 个 stated 行、285 个合约）：64.85% p75==p90、23.92% p25==p75、16.55% 三档全等；46.0% 的 stated 行是 `negative`。描述这张表时用上面的估计样本数字。
- 219 个无 funding 状态的事件已排除。
- 估计样本的 249 个合约里，206 个至少有一行事件落在 p75==p90 的行上。

### 8.2 附录拆分

一张 4×4 表（行 R1–R4；列 `negative / neutral / high-only / extreme`），给 `fwd_mean`、`y_mean`、`rv_mean` 与 n。这是互斥状态视角；主表保留 note 的嵌套列。

校验恒等式：E1 的 `high` 格均值必须等于 `w2 × high-only + w3 × extreme`（最大绝对差 < 1e-12）。

**输出。** `phase4_funding/tables/e5_disjoint.parquet` + `.csv`；`e5_overlap.csv`。

---

## 9. Phase 5 闸门

**锁定规则。** 只要 **12 个 `y_raw` within-regime funding 对比中至少一个在其 12 检验家族内过 BH（`p_bh < 0.05`）且扛住 drop5（`|t_drop5| > 1.96`）**，Phase 5 就开；任意期限、任意一种权重都算。不设 bp 阈值；不要求两种权重同号。

闸门不适用于波动率。波动对比照常报告；选定收益规则后，用作风险 overlay（仓位/止损宽度）。

报告里的闸门句：

> Phase 5 由 `<regime> × <funding>` 解锁，h = `<h>`，weighting = `<event|contract-day>`：`y_raw` 对比 = `<bp>`（t = `<t>`，p_bh = `<p>`，t_drop5 = `<t5>`）。

如果没有对比通过，Phase 5 不启动；这也是一个有效的 Phase 4 结论。

多重性说明：闸门是按家族做的。`y_raw` 有 8 个家族（4 个期限 × 2 种权重），每个家族各自 BH 12；8 个家族之间不做校正。这是与项目负责人一起锁定的、刻意偏宽松的选择，必须在闸门句里披露：家族、检验数，以及闸门不做跨期限/跨权重的 family-wise 校正。

---

## 10. Out of scope

- Baseline：price alone、OI alone、funding alone、random timing——Phase 3 实验 5–9 与实验 8。
- IC：note 的 IC 是「若信号转成 ranked score」的条件句；本信号是阈值标签。
- 绝对 bp/day funding 尺度：note 没有。
- β 附录（regime vs 同向 benchmark within funding）：note 没有。
- 16-γ 交互 ANOVA：需要把 high/extreme 拆成互斥格，并把主效应从报告对象里扣掉；已拒绝。
- 阈值优化（p60/p70 网格）：Phase 2 已做阈值网格；p70 冻结。
- 跨交易所、Phase 5 回测、R4 stress（Phase 3 实验 14b）、4h/8h 标签（先做 1h，后续再说）。

---

## 11. 输出

```
phase4_funding/
  GUIDANCE.md                     本文件
  tables/
    e1_surface.parquet/.csv
    e2_contrasts.parquet/.csv
    e3_column_profile.parquet/.csv
    e4_hypothesis_map.csv
    e5_disjoint.parquet/.csv
    e5_overlap.csv
  figures/
    f01_return_heatmap.png        raw fwd 与 y_raw，4 horizons × 4 regimes × 4 funding
    f02_vol_heatmap.png           rv 均值，同样布局
    f03_contrast_forest.png       12 个对比 × DV/horizon/weighting，带 95% CI
```

图规则：热力图画估计值，并标记 `y_raw` 对比过 BH 12 + drop5 的格；forest plot 画 12 个对比与 95% CI，过 BH 的点用实心。不要画水平柱状图。

---

## 12. 校验闸门

写报告前必须跑：

1. **n 对账。** h=1 的 E1 n 与样本量审计一致：255,857 行；互斥合计 93,489 / 123,907 / 18,834 / 19,627；合约-月合计 9,499 / 9,461 / 3,377 / 2,777；R1 × neutral 2,384；R1 × extreme 752；最薄互斥格 584（R3 × extreme）。
2. **原始收益关联。** 每个小时内，`fwd_h − y_raw` 在所有事件上恒定（等于市场均值）；小时内标准差最大值 < 1e-12。同时检查关联覆盖全部 E1/E2 行（无缺失 `fwd_h`）。
3. **High 并集恒等式。** E1 的 `high` 均值 = `w2 × high-only + w3 × extreme`，在每个 `(h, weighting, regime)` 上最大绝对差 < 1e-12。
4. **互斥格合计。** 16 个互斥格的 n 在每个 `(h, weighting)` 上等于 E1/E2 样本量。
5. **对比恒等式。** C2(r) = `w2 × (high-only − neutral) + w3 × (extreme − neutral)`；最大绝对差 < 1e-12。
6. **BH 家族。** `y_raw` 与 `lrv` 每个 `(dv, h, weighting)` 恰好 12 个检验；`p_bh` 单调；`fwd` 没有 `p_bh`。
7. **权重。** event 与合约-日两张表的格与定义一致；合约-日的高并集权重用合约-日-格数，不用事件数。
8. **退化标记。** 在 E1/E2 样本上复算 p75==p90 的占比，匹配 56.96%（行）与 48.9%（合约-月）；high 并集的 n 用唯一计数，不用求和。
9. **样本闸。** h=1 没有格低于 400 合约-月；任何期限/权重出现低于 400 的格都要打标。
10. **无残留 16-γ 产物。** 旧的 `l1_cellmeans` / `l2_interactions` 不在 E1–E5 的任何地方使用。

---

## 13. Checklist

- [ ] 从 `forward/freq=1h` 关联 `fwd_h`；校验小时内恒等式。
- [ ] 建 E1 面：4 个期限 × 2 种权重 × {raw fwd、y_raw、rv}，含 mean/median/CI/n。
- [ ] 建 E5 互斥格与 overlap 统计；校验 high 并集恒等式。
- [ ] 建 E2 对比：每个 (dv, h, weighting) 12 个；`y_raw` 与 `lrv` BH 12；`fwd` 描述性；drop5。
- [ ] 建 E3 column profile。
- [ ] 建 E4 假设映射（六个锚点 + exploratory 格）。
- [ ] 出三张图。
- [ ] 跑校验闸门。
- [ ] 写 Phase 5 闸门句（或明确的「闸门未开」）。
- [ ] 在表注里更新退化披露。
