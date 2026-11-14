# Phase 4 — Funding × Regime 条件事件研究 · 实施指南

**状态。** 设计 v2，已锁定。本文件取代旧版 E1–E5（16-γ 原型及其后续），也取代 `HANDOFF.md` §3.5–3.7 中与本文件冲突的部分；导师的 idea note 是 Phase 4 的最终依据。本文件不含实现代码。

**核心原则。** Phase 3 是**无条件** event study（regime R 之后发生什么）；Phase 4 是**同一套 event study 的 funding 条件版本**（在 funding 状态 F 下，regime R 之后发生什么）。note 的四个问题和六行示例，是 Phase 4 条件网格上的**特定切片**；Phase 4 不依赖 Phase 3 的结论来回答它们。

**读者。** 实现者与学术导师。sponsor 看最终表格，不看本文件。

**标记说明。** 本文件的表格用文本标记，不是真底色（Markdown 不支持单元格底色；真底色需要 XLSX，本次不做）：

| 标记 | 含义 |
|---|---|
| 🔵 | note §7 的四个 example research questions 之一 |
| 🟡 | note §11 的六行 example output table 之一 |
| 🟣 | note §10 的 4×4 output（forward return + volatility by bucket） |
| — | 探索性，不对应 note 的具体问题 |

一个格可以同时有多个标记。

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

- 主交付物是**分层的 4×4 条件表现表**；note 的四个问题和六行是这张表上的切片。
- note 的 §9 baseline（price alone、OI alone、funding alone、random timing）属于 Phase 3：实验 5–9 与实验 8 已覆盖，Phase 4 不重复。
- note 没有规定回归、对比家族、多重校正或经济阈值；本文件的推断层是**项目**为了回答 note 与 Phase 5 闸门而加的，写作时标注。

---

## 1. 锁定设计

| 项 | 锁定选择 |
|---|---|
| 主对象 | **P4-1…P4-7** 的 funding 条件事件研究；note 的四个问题 + 六行是其中的预声明切片。 |
| Funding 状态 | 按 note 嵌套定义：`negative` f ≤ p25；`neutral` p25 < f ≤ p75；`high` f > p75（**包含 extreme**）；`extreme` f > p90。`high ⊇ extreme`。 |
| Regime | R1 价涨 + OI 增；R2 涨 + OI 减；R3 跌 + OI 增；R4 跌 + OI 减。 |
| Return 口径 | `fwd_h`（raw，note §8 A）与 `y_raw`（市场中性，Phase 3 headline）。判定用 `y_raw`；`fwd_h` 是 note 字面的描述口径。 |
| Volatility 口径 | 事件后 h 小时的已实现波动 `rv`；P4-2 报算术均值/中位数，推断用 `lrv = log(rv)`，报 `exp(对比) − 1` 的 %。 |
| Reversal/Continuation | `rev = 1{fwd_h · dir < 0}`（raw 符号，note §8 C 的定义）；`cont = 1 − rev`；LPM + FE。 |
| Path | MFE / MAE / MDD（events 表已有），按 cell 描述。 |
| Benchmark | 同方向、同 funding 档、价格超阈但**不是该 regime** 的行（cell 0 + 另一个 OI 状态）；用于 P4-5 的 β。 |
| Stress | R4 × market-vol state（low/mid/high）；**描述，不检验 "faster"**。 |
| 期限 | 1、4、8、24 小时。 |
| 权重 | event 等权为主；合约-日等权（one vote per contract-day）为稳健性。 |
| 推断 | 合约 + 月份双向固定效应；CGM 双向聚类 SE；每个（块 × 期限 × 权重）一个 BH 家族；逐对比/β 做 drop5。 |
| note 切片 | 四个问题 + 六行是各自块家族内的**预声明子集**；不另开小家族。 |
| Phase 5 闸门 | 任意 **P4-1a/P4-3 对比**（不限 note）在一种权重下过 BH 12 + drop5，且另一种权重**同号**即开；exploratory screening；P4-2 作 risk overlay；P4-5 作旁证。 |
| Out of scope | IC、绝对 bp/day、阈值优化、跨交易所、Phase 5 回测、by-symbol（Phase 3 保留）、4h/8h（后续）。 |

---

## 2. 定义与样本

### 2.1 样本

继承 Phase 1–3 的冻结口径；不重建。

| 项 | 值 |
|---|---|
| Universe | 月度 top-50（过去 30 天报价成交额），四道闸；249 个合约；54 个月（2022-03 … 2026-08）。 |
| 事件 | 1h bar，|Δprice| 与 |ΔOI| 同时超过该合约过去 90 天 p70（≥30 天历史）。 |
| Headline | `in_universe` 且 `excl_reason == "ok"`；`cell ∈ {1,2,3,4}`；events 共 256,079 行；其中 h=1 有有效前向收益 256,076 行（3 行无 h=1 forward），再减 219 个无 funding 状态 = 255,857。 |
| 无 funding 状态 | 219 个事件（0.09%）四个 funding bool 全 False（p25 缺失）；从 P4 全部块排除并报告。 |
| P4 样本（h=1） | 255,857 行。h=4/8/24 只差 `ok_{h}h` 的损失。 |
| 合约-月 | 2,700 = 50 × 54。 |
| lrv 缺失 | h=1：2,244 行（0.9%）；只在波动率块剔除。 |

### 2.2 Regime

`cell` 1–4，沿用 Phase 2/3 定义，不改。

### 2.3 Funding 状态——嵌套，不是分区

每个合约，过去 90 日历天的结算 funding 序列，取 p25 / p75 / p90，从最近一次结算起按阶梯函数取值。严格 `>`（note 说 "above"）；不要改成 `≥`。

```
negative : f ≤ p25
neutral  : p25 < f ≤ p75
high     : f > p75        # 包含 extreme
extreme  : f > p90        # high 的子集
```

四列**不是互斥的**。p75 == p90 时，`high` 与 `extreme` 是同一批行。

仅用于估计，定义四个互斥潜在状态：

```
s0 = negative
s1 = neutral
s2 = high-only   (p75 < f ≤ p90)
s3 = extreme     (f > p90)
```

报告的 `high` 列是并集 `s2 ∪ s3`；均值按样本量加权。互斥状态进 P4-7 附录和 P4-5/P4-3 的估计。

### 2.4 Outcome 与数据来源

| 变量 | 来源 | 说明 |
|---|---|---|
| `fwd_h` | `events/events_1h.parquet`（或 `forward/freq=1h`） | raw 前向收益，`close_{t+h}/close_t − 1`。 |
| `y_raw` | `panel/freq=1h/h={h}.parquet` | 市场中性前向收益（减同时刻全市场池 7,010,789 行等权均值）。 |
| `rv_h` / `lrv` | `events` / `panel` | 已实现方差 / `log(rv)`。 |
| `rev_h` / `cont_h` / `hit_h` | `events` | Phase 3 已算好的 0/1；同时用 `fwd_h · dir` 重算并校验。 |
| `mfe_h` / `mae_h` / `mdd_h` | `events` | Phase 3 实验 11 的路径列。 |
| `mkt_vol_state` | `events` / `labels` | low / mid / high / unknown。 |
| funding 状态 | `labels`（`funding_negative/neutral/high/extreme`、p25/p75/p90） | 按 `(symbol, ts_end)` 关联。 |
| benchmark（cell 0） | `panel` + `forward` | 同方向、同 funding 档、价格超阈但 OI 安静的行。 |

关联键统一用 `(symbol, ts_end)`；panel 的 `symbol` code 通过 `panel/freq=1h/symbols.parquet` 映射；`hour` 通过 `ts_end = 2021-12-01 UTC + hour 小时` 映射。

单位：收益 bp（×1e4）；波动水平 %（rv × 100）；波动对比 %（`exp(Δlog rv) − 1`）；反转/延续概率用百分点（pp）或 0–1 小数。

### 2.5 权重

- **Event 等权**：每个事件行一个观测；note 的事件研究单位。
- **合约-日等权**：每个 `(symbol, UTC 日, regime, 互斥 funding 状态)` 一个观测；组内平均因变量；同样的 FE 模型跑在组均值上。日 = `hour // 24`（Phase 3 实验 15）。
- 对嵌套 `high` 列：event 权重用事件数；合约-日权重用合约-日-格数。不要混。
- 合约-日权重是 note §5 "daily aggregation for robustness" 的 Phase 4 对应物；单独的日聚合（可选块，不在 P4-1…P4-7 里）不在锁定设计内。

---

## 3. 估计量与记号

对 regime `r` 与互斥 funding 状态 `s`，令 `m_{r,s}` 为扣合约+月份 FE 后的格均值：

```
y_it = Σ_{r,s} m_{r,s} · 1{regime=r, state=s} + α_contract + λ_month + ε_it
```

16 个互斥格 dummy 是分区；与 FE 常数有一个共线（16 个 dummy 之和恒为 1）。丢一个参照格（R4 × s3），估 15 个系数，16 个 `m` 只识别到常数；所有报告量都是差，常数抵消。

嵌套格均值：

```
μ(r, neg)     = m_{r,s0}
μ(r, neu)     = m_{r,s1}
μ(r, high)    = w2·m_{r,s2} + w3·m_{r,s3},   w2 = n_{r,s2}/(n_{r,s2}+n_{r,s3}), w3 = 1 − w2
μ(r, extreme) = m_{r,s3}
```

`n` 是当前权重下该格的观测数（事件行或合约-日-格）；权重是实现的样本量，视为固定。

对比与 β 的 SE 都是 15 个系数的线性组合，用 CGM 协方差：

```
V = V_contract + V_month − V_contract×month
SE(c) = sqrt(c' V c)
```

**P4-3 的 LPM**：因变量 `rev` 是 0/1；同样的 15 个格 dummy + 合约/月 FE；系数是概率差；SE 用同一 CGM。`cont = 1 − rev` 同表报告（`cont` 的概率 = `1 − rev` 的概率；hit rate 与 `cont` 在事件方向上一致，Phase 3 已验）。

**P4-5 的 β**：对每个 regime `r`、funding 列 `f`，样本 = 该 regime 的行 + 同方向、同 `f`、非该 regime 的 benchmark 行（cell 0 + 另一个 OI 状态）；dummy=1 为该 regime，0 为 benchmark；合约/月 FE；β 是「控制构成后，该 regime 相对同向 benchmark 的超额」。16 个 β（4 regime × 4 funding 列）。

---

## 4. 实验地图（主表）

| ID | 实验块 | 主 outcome | 样本 | 主要对比 | 推断 | note |
|---|---|---|---|---|---|---|
| **P4-1** | 条件收益 | `fwd_h`、`y_raw` 均值/中位数 | headline | **P4-1a**：12 个 within-regime（各 funding 档 vs neutral）；**P4-1b**：out of scope（未做） | FE + CGM；BH 12；drop5 | 🔵🟡 |
| **P4-2** | 条件波动 | `rv` 水平、`lrv` 对比 | headline | 12 个 within-regime | FE + CGM；BH 12；drop5 | 🟣 |
| **P4-3** | 条件反转/延续 | `rev`、`cont` | headline | 12 个 within-regime；另报 benchmark 水平 | LPM + FE；BH 12；drop5 | 🔵🟡 |
| **P4-4** | 条件路径 | MFE / MAE / MDD | headline | 按 cell | 描述（均值/中位数/p10/p90） | 🟡 |
| **P4-5** | 条件 β | `y_raw`/`fwd` 与 `rev` vs benchmark | regime + benchmark | 16 β × 2 outcome | FE/LPM + CGM；BH 16；drop5 | 🔵🟡 |
| **P4-6** | 条件 stress（最小） | R4 × market-vol | R4 | 按 state | 描述（不检验 faster） | 🟡 |
| **P4-7** | 稳健性 | all | all | nested vs disjoint、event vs 合约-日、drop5、薄格 | 诊断 | — |

**图例**：🔵 = §7 问题；🟡 = §11 六行；🟣 = §10 output；— = 探索性。

---

## 5. note 切片地图

### 5.1 §7 的四个问题

| 问题 | Phase 4 切片 | 类型 | note |
|---|---|---|---|
| Q1 R1 在 neutral 时更好？ | P4-1a `C1/C2/C3(R1)`（neutral vs 其他档，符号反读）+ P4-5a `β(R1, neu)` | 均值/β | 🔵 |
| Q2 R1 在 extreme 时 reversal？ | P4-3 `C3(R1)`（ext vs neu 的反转概率）+ P4-1a `C3(R1)`（均值符号）+ P4-5b `β(R1, ext)` | 概率/均值/β | 🔵 |
| Q3 R4 在 stress 后更快 mean-revert？ | P4-6 `R4 × market-vol`（**描述，不检验 faster**）+ P4-4 `R4` 路径 + P4-1a `R4` 的 1/4/8/24h 梯度 | 描述/路径 | 🔵 |
| Q4 R3 在 neutral 时 continuation？ | P4-3 `C1/C2/C3(R3)`（neutral vs 其他档；cont = 1−rev）+ P4-1a `C1/C2/C3(R3)` + P4-5b `β(R3, neu)` | 概率/均值/β | 🔵 |

### 5.2 §11 的六行

| §11 行 | Phase 4 切片 | note |
|---|---|---|
| R1 + neutral → continuation | P4-1a `(R1, neu)` 均值 + P4-3 `(R1, neu)` 的 `cont` | 🟡 |
| R1 + extreme positive → crowded reversal | P4-3 `C3(R1)` + P4-1a `C3(R1)` + P4-5b `β(R1, ext)` | 🟡 |
| R2 + any → short-covering exhaustion | P4-1a R2 四档 profile + P4-3 R2 四档 `rev/cont` | 🟡 |
| R3 + neutral → downside continuation | P4-1a `(R3, neu)` 均值 + P4-3 `(R3, neu)` 的 `cont` | 🟡 |
| R3 + extreme negative → short-squeeze | P4-1a `C1(R3)`（negative vs neutral）+ P4-3 `C1(R3)` | 🟡 |
| R4 + stress / high vol → mean reversion | P4-6（描述，不检验 faster）+ P4-4 | 🟡 |

### 5.3 §10 的 4×4 output

| note §10 | Phase 4 切片 | note |
|---|---|---|
| 4×4 table，forward return + volatility by bucket | **P4-1 + P4-2** 的全部 4×4 面 | 🟣 |

### 5.4 代理口径

- **extreme negative**：标签没有单边 extreme-negative 档；note 的 "extreme negative" 在 R3 short-squeeze 上用 `negative`（f ≤ p25）代理。表注写明。
- **liquidation / stress**：没有 liquidation 数据；P4-6 用 market-vol state（low/mid/high）代理；只做描述，不检验 "faster"。表注写明。

---

## 6. P4-1 — 条件收益

**目的。** note §10 的 return 切片；Q1/Q2/Q4 的均值层。

**样本。** P4 样本（§2.1），一次一个期限。

### 6.1 4×4 面

行 R1–R4；列 `negative / neutral / high（含 extreme）/ extreme`。每格：

| 字段 | 定义 |
|---|---|
| `fwd_mean`、`fwd_median` | raw 前向收益，bp（输出已 ×1e4）。 |
| `y_raw_mean`、`y_raw_median` | 市场中性 `y_raw`，bp（输出已 ×1e4）。 |
| CI | 均值的 95% CI，CGM 双向聚类。描述性。 |

n 另表：`n_obs`（事件行或合约-日-格）、`n_cdays`、`n_cmonths`。对嵌套 `high`：`n_obs` 是 `s2+s3` 之和；`n_cdays`/`n_cmonths` 是并集唯一数（不要加 `s2` 与 `s3` 的计数）。

### 6.2 对比

**P4-1a：within-regime（正式，note 家族）**

对每个 regime `r`，三个 funding 档 vs neutral：

```
C1(r) = μ(r, negative) − μ(r, neutral)
C2(r) = μ(r, high)     − μ(r, neutral)    # high 含 extreme
C3(r) = μ(r, extreme)  − μ(r, neutral)    # high 的子集
```

12 个对比；`y_raw` 进 BH 家族；`fwd` 只报描述性 CI（不进 BH，不报 p_bh）。派生尾部增量 `C4(r) = μ(r, extreme) − μ(r, high) = w2·(m_{r,s3} − m_{r,s2})` 只作解读，不进家族。

**P4-1b：out of scope（未做；note 不依赖）**

### 6.3 家族与表

- P4-1a：每个 `(weighting, h)` 12 个对比，BH 12；`y_raw` 是判定口径；`fwd` 描述性。
- P4-1b：out of scope（未做）。
- drop5：对 P4-1a 的每个对比做（剔影响最大的 5 个合约后重估）。
- 表列：`estimate`、`se`、`t`、`p`、`p_bh`、`t_drop5`、`n_obs`、`n_cmonths`、`in_bh`、`note_marker`。

**输出。** `phase4_funding/tables/p4_1_surface.parquet`、`p4_1_contrasts.parquet`（含 1a/1b）+ `.csv`。

---

## 7. P4-2 — 条件波动

**目的。** note §10 的 volatility 切片；风险 overlay。

**样本。** P4 样本，剔除 `lrv` 缺失。

**面。** 4×4；每格 `rv_mean`、`rv_median`（算术口径，Phase 3 一致）、`lrv_mean`、n、CI。

**对比。** 12 个 within-regime（同 P4-1a 的 C1/C2/C3，因变量换成 `lrv`）；`exp(对比) − 1` 的 %；BH 12；drop5。

**note。** 🟣（§10 output）；不对应 §7 的具体问题。

**输出。** `phase4_funding/tables/p4_2_vol.parquet` + `.csv`。

---

## 8. P4-3 — 条件反转 / 延续

**目的。** Q2/Q4 的 reversal/continuation 概率；§11 的 reversal/exhaustion 行。

**定义。**

```
rev  = 1{ fwd_h · dir < 0 }
cont = 1 − rev
```

`dir ∈ {+1, −1}` 是事件方向（panel 的 `dir`；cell 0 的行也有方向）。用 raw `fwd_h` 的符号，这是 note §8 C 的定义；不要用 `y_raw` 的符号（市场中性会改符号）。校验：与 events 表的 `rev_h` 在 R1–R4 上逐行一致。

**样本。** P4 样本（cell 1–4）；`fwd_h` 有限。Benchmark（cell 0）只用于 P4-5；P4-3 不输出 benchmark 水平。

**估计。** LPM：`rev ~ 16 个格 dummy + 合约 FE + 月 FE`；12 个 within-regime 对比（C1/C2/C3）；BH 12；drop5。`cont` 同表报告（`1 − rev` 的概率；hit rate 与 cont 在事件方向上一致）。

**note 切片。** Q2（C3(R1)）、Q4（C1/C2/C3(R3)）、R1 extreme、R2 any、R3 neutral、R3 squeeze。

**输出。** `phase4_funding/tables/p4_3_reversal.parquet` + `.csv`。

---

## 9. P4-4 — 条件路径

**目的。** Q3 的「faster mean-revert」的路径证据；§11 R4 stress 行。

**样本。** P4 样本（`events` 表的 `mfe_h`/`mae_h`/`mdd_h`）。

**面。** 4×4；每格 `mfe_mean`、`mae_mean`、`mdd_mean`、`mdd_p10/p50/p90`、n；均值保留在主表。MFE/MAE 已按方向翻正（Phase 3 build 的口径）；MDD ≤ 0。

**与 Phase 3 的关系。** Phase 3 `descriptive_path` 是它的 marginal（4 state × 4 h，所有 funding 混合）；本块是同一张表按 funding 的条件分解。不重复检验、不做 reconciliation；均值被极端路径主导只作表注，`mdd_p10/p50/p90` 并列。

**推断。** 描述性，不做检验。

**「faster」的读法。** 用 1/4/8/24h 的收益/路径梯度 + MDD 的 p50 作为「回归速度」的代理；没有 survival/time-to-recovery 的正式检验；表注写明。

**note。** 🟡（Q3 / R4 stress）。

**输出。** `phase4_funding/tables/p4_4_path.parquet` + `.csv`；`phase4_funding/figures/f_p4_4_path.png`（4 regime 面板，MFE vs |MAE|，颜色 = funding，标记 = 期限，p50）。

---

## 10. P4-5 — 条件 β（vs benchmark）

**目的。** note 的「perform better」按 benchmark 读：控制同向 benchmark 后，regime 在某个 funding 档里还有没有信息。

**样本。** 对每个 `(regime r, funding 列 f)`：该 regime 的行 + 同方向、同 `f`、非该 regime 的 benchmark 行（cell 0 + 另一个 OI 状态）。

**估计。** dummy=1 为该 regime，0 为 benchmark；合约/月 FE；CGM。16 个 β（4 regime × 4 funding 列）。

**两个 outcome。**

- **P4-5a**：`y_raw`（主）与 `fwd`（描述）；β 是收益差（bp）。
- **P4-5b**：`rev`（LPM）；β 是反转概率差（pp）。

**家族。** 每个 `(weighting, h, outcome)` 16 个 β，BH 16；drop5。

**note 切片。** Q1 的 `β(R1, neu)`、Q2 的 `β(R1, ext)`、Q4 的 `β(R3, neu)`；§11 R1/R3 行。

**输出。** `phase4_funding/tables/p4_5_beta.parquet` + `.csv`（全 384 行）；`phase4_funding/figures/f04_beta_forest.png`：2 个面板（return / reversal），**y = cell × horizon（64 行）**，**只画 BH16 + drop5 显著点**；颜色 = event / contract-day，h 写在 y 标签；不标 note 底色。

---

## 11. P4-6 — R4 × market-vol（最小描述）

**Q3 的定位。** note 的 Q3 是唯一问「mean-revert faster」的问题；没有 liquidation 数据、没有 first-touch/survival，**不能正式检验「faster」**。本块只做一张描述表，标 **descriptive — not a test of faster**。

**表。** R4 × `mkt_vol_state ∈ {low, mid, high}` × 1/4/8/24h：

- `y_raw` 均值（bp）；
- `rev` 比例（%）；
- `mdd_p50`（bp）；
- n / 合约-月；`unknown`（mkt_vol 未定义）单列。

**不做。** 不做 R4 × funding stress 第二层、不做小家族、不做图、不做 survival/time-to-recovery；Q3 在报告里标 **descriptive only**。

**note。** 🟡（Q3 / R4 stress）。

**输出。** `phase4_funding/tables/p4_6_stress.parquet` + `.csv`。

---

## 12. P4-7 — 稳健性

- **5 类拆分（一次做完）**：`negative / neutral`（full）、`high_only / extreme`（non-degenerate，p75 < p90）、`degenerate`（p75 == p90，high=extreme）；5 类互斥且穷尽；`high` = high_only + extreme + degenerate（三桶相加）；`mdd_p50` 是分位数、不可加权。
- **权重**：event 与合约-日并排；5 类的计数按当前权重。
- **drop5**：对 P4-1a/P4-2/P4-3/P4-5 的每个对比/β。
- **薄格**：非退化 extreme 的 n_cmonths 全部 >400；退化桶在 h=1 只有 217–316 合约-月（R1 292、R2 236、R3 217、R4 316），必须标；h=1 的 full R3×extreme 仍是 584，R1×extreme 752。
- **退化**：p75==p90 占 56.96% 事件行 / 65.4% 事件样本合约-月 / 48.9% 全 label；`high` 与 `extreme` 在退化行上是同一批。
- **无 funding 状态**：219 行排除。
- **raw vs y_raw**：P4-1/P4-2/P4-5a 报两列；判定用 `y_raw`，`fwd` 描述。

**输出。** `phase4_funding/tables/p4_7_disjoint.parquet` + `.csv`（192 行：6 个 label = 5 类 + high，× 4 h × 2 weight × 4 regime）、`p4_7_diagnostics.csv`、`exp7_validation.csv`。

---

## 13. 推断与多重性

| 块 | 家族 | 检验数 | 判定口径 | drop5 |
|---|---|---|---:|---|
| P4-1a | 每个 `(weighting, h)` | 12 | `y_raw` | 是 |
| P4-1b | — | — | out of scope（未做） | — |
| P4-2 | 每个 `(weighting, h)` | 12 | `lrv` | 是 |
| P4-3 | 每个 `(weighting, h)` | 12 | `rev` | 是 |
| P4-5a | 每个 `(weighting, h, outcome)` | 16 | `y_raw`（`fwd` 描述） | 是 |
| P4-5b | 每个 `(weighting, h)` | 16 | `rev` | 是 |
| P4-4 / P4-6 | 无 | — | 描述 | — |

- note 的四个问题 + 六行是各自块家族内的**预声明子集**；不另开小家族，避免「特例化」。
- 探索性格（P4-5 的非 note β）在同一家族内，会稀释 note 切片的 power；这是 comprehensiveness 的代价，报告时说明。（P4-1b 未做。）
- `p_bh` 是家族内 BH；`t_drop5` 是逐对比/β 的条件稳健性；`|t| > 1.96` 不等于过闸，必须看 `p_bh` 与 `t_drop5`。

---

## 14. Phase 5 闸门

**锁定规则（single, exploratory screening）。** Phase 5 开，当且仅当 **P4-1a 或 P4-3 的任意一个对比**（不限 note 切片）满足：

1. 在**至少一种权重**下，在其 12 检验家族内过 BH（`p_bh < 0.05`）且扛住 drop5（`|t_drop5| > 1.96`）；
2. 在**另一种权重**下，估计**同号**（不要求显著）。

任意期限都算；不设 bp 阈值；**不做跨家族 BH 校正；实际搜索数 192（P4-1a 96 + P4-3 96）**。非 note 切片的通过项是 discovery（note 没假设到的问题），照常报告，不另设闸门。

- **P4-2**（波动）不 gate；作 risk overlay（仓位/止损宽度）。
- **P4-5**（β）不单独 gate；作「regime 是否还有信息」的旁证。
- **P4-4/P4-6** 描述性，不 gate。

**当前结果（P4-1a + P4-3，全部 h；共 9 个通过项）：**

- **P4-1a（`y_raw`）**：R3×negative、R4×negative（h=1）；contract-day 过 BH12 + drop5，event 同号。
- **P4-3（`rev`）**：R4×negative（h=1，两权重都过）、R1×negative（h=1/4）、R2×negative（h=8）、R3×negative（h=8/24）。
- 搜索数：P4-1a 96 + P4-3 96 = 192；9 个通过项都集中在 negative 列，high/extreme 无。

闸门句：

> Phase 5 由 R3/R4×negative（`y_raw` + `rev`）和 R1/R2×negative（`rev`）解锁；Phase 5 只跑 M1（down-regime negative → long）和 M2（up-regime negative → long）+ vol overlay；exploratory，不是 confirmatory；必须 out-of-sample。

性质说明：这是 **exploratory screening**，不是 confirmatory。BH 是家族内（每个块 × 期限 × 权重 12 个），**不控制 12×4×2 的全搜索**；因此：

- 通过项是 Phase 5 的**探索性候选**，不能写成 confirmatory；
- Phase 5 的回测必须 **out-of-sample**；
- 报告里同时给出未通过的 note 切片，避免只报通过项。

如果没有对比通过，Phase 5 不启动；这是有效的 Phase 4 结论。

---

## 15. Out of scope

- Baseline：price alone、OI alone、funding alone、random timing——Phase 3 实验 5–9 / 8。
- IC：note 的条件句；信号是阈值标签，不是 ranked score。
- 绝对 bp/day funding 尺度、β 的绝对尺度版本、阈值优化（p60/p70）——Phase 2/3 已处理或 note 没有。
- 跨交易所、Phase 5 回测、by-symbol（Phase 3 保留）、4h/8h 标签（后续）。
- liquidation 数据（没有）；P4-6 用 market-vol 代理（描述，不检验）。

---

## 16. 输出

```
phase4_funding/
  GUIDANCE.md                       本文件
  REPRODUCE.md                      命令顺序、依赖、耗时、caveat
  TABLES.md                         每张表的定义与 caveat
  tables/
    p4_0_validation.csv
    p4_1_surface.parquet/.csv
    p4_1_contrasts.parquet/.csv     P4-1a（y_raw/fwd）
    p4_2_vol.parquet/.csv
    p4_2_contrasts.parquet/.csv
    p4_3_reversal.parquet/.csv
    p4_4_path.parquet/.csv
    p4_5_beta.parquet/.csv
    p4_6_stress.parquet/.csv
    p4_7_diagnostics.csv
    p4_7_disjoint.parquet/.csv
    exp1_2_validation.csv
    exp3_validation.csv
    exp4_validation.csv
    exp5_validation.csv
    exp6_validation.csv
    exp7_validation.csv
  figures/
    f01_return_level.png            2×4 heatmap：y_raw 均值，event/contract × 4 h
    f02_vol_level.png               2×4 heatmap：lrv 均值，同布局
    f03_difference_forest.png       3 面板：P4-1a(h=1)/P4-2(h=24)/P4-3(h=1) 的 12 对比
    f04_beta_forest.png             P4-5 的显著点 forest（2 面板，y = cell × horizon）
    f_p4_4_path.png                 两行：上 = MFE vs MAE（Phase 3 Fig 11 样式）；下 = MDD p50 vs horizon；4 regime 面板
```

图规则：热力图画估计值；forest plot 画被检验的量 + 95% CI；P4-5 用 forest（y = cell × horizon），只画显著点，h 写在 y 标签。

---

## 17. 校验闸门

1. **n 对账。** h=1：255,857 行；互斥合计 93,489 / 123,907 / 18,834 / 19,627；唯一合约-月 2,572 / 2,447 / 1,048 / 899（总 2,700；9,499 / 9,461 / 3,377 / 2,777 是按 regime 重复计数的 cell 级求和）；R1 × neutral 2,384；R1 × extreme 752；R3 × extreme 584；R1 × high 13,184 / 1,183。
2. **关联。** P4-1/2 的 panel 行与 P4-3/4/5/6 的 events 行按 `(symbol, ts_end)` 一一对应；`fwd_h` 无缺失；`y_raw = fwd_h − 市场均值` 的小时内恒等式（标准差 < 1e-12）。
3. **High 并集。** `high` 均值 = `w2 × high-only + w3 × extreme`（< 1e-12），每个 `(h, weighting, regime)`。
4. **互斥合计。** 16 个互斥格的 n 等于 P4 样本量（每个 `(h, weighting)`）。
5. **对比恒等式。** C2 = `w2 × (high-only − neutral) + w3 × (extreme − neutral)`（< 1e-12）。
6. **rev/cont。** `rev + cont = 1`；`rev` 与 events 的 `rev_h` 在 R1–R4 上逐行一致；`cont` 与 `hit_h` 在事件方向上一致。
7. **β benchmark。** 每个 `(regime, funding)` 的 benchmark 行 = 同方向、同 funding、非该 regime 的行；样本量 > 0；dummy=1 的行数与 regime 行数一致。
8. **家族。** P4-1a/P4-2/P4-3 每个 `(weighting, h)` 12 个；P4-5a/b 16 个；`p_bh` 单调；note 切片在 §5 的切片表里都有 marker。
9. **权重。** event 与合约-日两张表格与定义一致；`high` 并集权重用当前权重的计数。
10. **退化。** p75==p90 占比 56.96%（行）/ 48.9%（合约-月）；`high` 并集 n 用唯一计数。
11. **样本闸。** 任何格 < 400 合约-月打标；h=1 最薄 584。
12. **无旧产物。** 旧的 `l1_cellmeans` / `l2_interactions` 不在 P4-1…P4-7 使用。

---

## 18. Checklist

- [x] 关联 `fwd_h` / `y_raw` / `rv` / `rev` / MFE-MAE-MDD / `mkt_vol_state` / funding 状态；校验 `(symbol, ts_end)` 与小时内恒等式。
- [x] 建 P4-1：4×4 面 + P4-1a（12，BH 12）+ n 表；P4-1b out of scope。
- [x] 建 P4-2：4×4 面 + 12 个 `lrv` 对比。
- [x] 建 P4-3：`rev/cont` 4×4 + 12 个 LPM 对比（不输出 benchmark 水平）。
- [x] 建 P4-4：MFE/MAE/MDD 4×4（描述）。
- [x] 建 P4-5：16 β × 2 outcome（mean、rev），BH 16、drop5。
- [x] 建 P4-6：R4 × market-vol 描述表（不检验 faster）。
- [x] 建 P4-7：nested/disjoint、权重、drop5、薄格、退化。
- [x] 出五张图。
- [x] 跑 §17 的 12 条校验。
- [x] 写 Phase 5 闸门句（9 个通过项、192 次搜索）。
- [x] 在表注里更新退化、proxy、weighting 披露。
