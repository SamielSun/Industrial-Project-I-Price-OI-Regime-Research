# Phase 5 — HANDOFF（D4: simple strategy prototype + OOS report）

**读者**：接手 Phase 5 的 agent。读完这份文档应能独立实现、回测、评估；不需要再问设计问题。
**状态**：设计已冻结（见 §10 决策记录，Q1–Q25）。**按本文执行，不要重新设计。**

---

## 1. 目标与范围

### 目标
用 Phase 4 的 negative-funding 发现，做一个**可复现、成本后、样本外**的简单策略原型（D4），并给出 OOS 报告。

### 在范围内
- 3 条方向规则 **M1a / M1b / M2** + 1 条风险 overlay **M3**（定义见 §3）。
- long-only；10 并发；等名义本金；1× 杠杆。
- 27/27 训练/测试 + 3 折 walk-forward + 3 个月最终 holdout。
- 4 条 baseline；成本、funding carry、滑点；OOS Sharpe 为唯一显著性指标。
- 交付：`phase5/` 代码、OOS 报告、`phase5/REPRODUCE.md`。

### 明确不在范围内
- **D5（dashboard）**：独立工程。
- **D6（final report / presentation）**：写作阶段。
- market-neutral / long-short 版本。
- 逐对比回测（Phase 4 的 9 个通过项不各跑一遍）。
- high/extreme funding 规则（Phase 4 没一个过闸）。
- note 四问的“验证性”回测（Q1/Q2/Q4 未过闸，Q3 只有描述）。
- DSR / deflated Sharpe（用户明确不用；OOS Sharpe 为唯一指标）。

---

## 2. 数据与路径

### 输入（只读，不改）
| 路径 | 内容 |
|---|---|
| `data/06_event_study/events/events_1h.parquet` | headline 事件；`cell`、`in_universe`、`excl_reason`、`mkt_vol_state` |
| `data/06_event_study/panel/freq=1h/` | Phase 3 panel；`dir`、`cell`、`fund`、`y_raw`、`lrv` |
| `data/06_event_study/forward/freq=1h/` | `fwd_h`、`rv_h`、`ok_h` |
| `data/05_regime/regime_labels/freq=1h/` | `funding_negative/neutral/high/extreme`、`funding_p25/p75/p90` |
| `data/07_funding/base/p4_base_h={1,4,8,24}.parquet` | Phase 4 的 46 列基础表；`state`（0 neg / 1 neu / 2 high-only / 3 extreme）、`cell`、`dir`、`fwd`、`y_raw`、`rv`、`lrv`、`rev`、`mfe`、`mae`、`mdd`、`sym`、`month`、`hour` |
| `data/07_funding/tables/freq=1h/` | Phase 4 的表（只读参考，不改） |

### 相关文档（只读）
- `phase4_funding/GUIDANCE.md`：Phase 4 设计；§14 闸门。
- `phase4_funding/TABLES.md`：各表定义与 caveat。
- `phase3_event/infer.py`：`p_two`、`bh` 可复用；`fe_ols` 不用于回测。
- `lib/schema.py`：列契约。

### 输出（新建）
```
phase5/
  backtest.py            主回测
  rules.py               M1a/M1b/M2/M3 定义
  eval.py                OOS 指标与 baseline
  report.py              生成 OOS 报告（md + csv）
  REPRODUCE.md           命令、依赖、耗时
data/08_strategy/
  tables/                回测结果 csv
  figures/               可选：净值/回撤图
```

---

## 3. 事件与规则（冻结）

### 事件
- 沿用 Phase 4：`in_universe == True`、`excl_reason == "ok"`、`cell ∈ {1,2,3,4}`、`state == 0`（negative funding）。
- **不新增阈值**；不改 regime/funding 定义。
- 事件时间 = 事件 bar 的 `ts_end`（1h bar 收盘）。

### M1a（primary）
- 条件：`cell ∈ {3,4}`（R3/R4，价格下跌）且 `state == 0`。
- 方向：**long**。
- 持有：**1h**（Phase 4 P4-1a 的 h=1；证据：R3×neg contract +5.29bp/p_bh 0.033；R4×neg +2.47bp/0.024）。
- 入场：事件后下一根可用 bar 的开盘（见 §4 缺 bar）。
- 出场：入场 bar 之后第 1 根 bar 的收盘。

### M1b（primary）
- 条件同 M1a。
- 方向：long。
- 持有：**8h 和 24h 两个版本**（Phase 4 P4-3 的 rev：R3×neg h=8 +2.86pp/p_bh 0.0019；h=24 +2.64/0.0395；R4×neg h=1 +1.46/0.015）。
- 出场：第 8 / 第 24 根 bar 收盘。两个版本分别报告，不合并。

### M2（exploratory）
- 条件：`cell ∈ {1,2}`（R1/R2，价格上涨）且 `state == 0`。
- 方向：long。
- 持有：**1h / 4h / 8h**（Phase 4 P4-3：R1×neg h=1 −1.84pp/0.015、h=4 −1.86/0.011；R2×neg h=8 −2.46/0.039）。
- **必须标 exploratory**：P4-1a 的收益层不支持 R1/R2 negative；只有 rev 层。

### M3（risk overlay，不单独成方向规则）
- 在 M1a/M1b/M2 之上叠加。
- target-vol：`size = clip(target_vol / lrv_at_entry, 0.5, 1.5) × base_size`；`target_vol` 由**训练期**的 `lrv` 分位决定。
- 单合约 ≤20% 只在 M3 生效。
- 不设止损；止损只作为“敏感性”另报一版。

### 硬性禁止
- 不把 9 个通过项逐个回测。
- 不加 high/extreme 规则。
- 不做 note 四问的 confirmatory 回测。

---

## 4. 回测协议（冻结）

### 入场
- 事件后**下一根 bar 的开盘**；市价单。
- **缺 bar 处理**：
  - 缺口 ≤ 2 根 bar：用**下一根可用 bar 的开盘**入场，持有期从该 bar 起算；
  - 缺口 > 2 根 bar / 合约下架：跳过，计数。
- 不用 stale price、不 impute。

### 出场
- 持有到 `入场 bar + h` 的收盘；h 见各规则。
- 合约下架：最后一个可交易 bar 收盘平仓。
- 主回测**不加止损**；止损版只作敏感性。

### 重叠
- 同一合约已有未平仓时，**不新开、不加仓**；只保留第一笔。
- 不同合约可并发，最多 10 笔。

### 成本
- 手续费：**taker 0.05%/边**（市价单）；敏感性版 0.02% maker。
- 滑点：**5bp/边**；敏感性版 2bp。
- 成本在入场和出场各计一次。

### Funding carry
- 持仓跨过 00:00/08:00/16:00 UTC 结算点时，按当时 funding rate 收/付；negative funding 时 long **收**。
- 按结算点整笔，不 pro-rata。
- 缺 funding 的结算点按 **0 carry** 处理，计数。
- 报告必须拆：**价格 PnL / funding PnL / 成本** 三段。

### Universe
- 只用 `in_universe == True` 的事件；不做事后放宽。

### 异常值
- 主回测**不 winsorise、不剔除**（Phase 3 冻结口径）。
- 另报“剔除 LUNA 后”的敏感性一行。

---

## 5. 组合与仓位（冻结）

- 初始资金：**$100,000**（比例不变，金额可调）。
- 等名义本金：每笔 **10%**（$10k）。
- 最多 **10 并发**；第 11 个跳过，计数。
- **1× 杠杆**：总敞口 ≤ 100%。
- 单合约 ≤20%：**只在 M3 overlay 生效**；M1/M2 基础版不触发。
- 不做再平衡；仓位持有到期。

---

## 6. OOS 与预注册（冻结）

- **主切分**：训练 2022-03..2024-09（27 个月），测试 2024-10..2026-08（27 个月）。
- **规则在训练期冻结**；测试期**只跑一次**，不重选、不调参。
- **3 折 walk-forward**（附录，稳健性）：
  - 折1 训练 2022-03..2023-08 / 测试 2023-09..2024-05；
  - 折2 训练 2023-03..2024-08 / 测试 2024-09..2025-05；
  - 折3 训练 2024-03..2025-08 / 测试 2025-09..2026-05。
- **最终 holdout**：2026-06..2026-08，只在最后报一次，不参与任何选择。
- **唯一显著性指标：OOS Sharpe**（普通 Sharpe，附 bootstrap CI）。**不做 DSR、不做 Bonferroni。**
- 全样本/训练期 Sharpe 不报为 headline。

---

## 7. 指标与 baseline（冻结）

### 指标（每个规则 × 每个版本）
- OOS Sharpe（唯一显著性指标）
- 年化收益、年化波动
- 最大回撤（MDD）
- 换手
- 成本后净收益
- 价格 PnL / funding PnL / 成本 拆分
- by-regime、by-asset
- n 笔数、跳过数（按原因）、缺失结算点数

### Baseline（6 条）
1. **price-alone**：同方向、同持有期，不看 OI/funding。
2. **random timing**：同频率、同持有期，随机入场（固定 seed）。
3. **buy-and-hold perp**：等权持有 universe。
4. **OI-alone**：同方向、同持有期，只看 OI。
5. **funding-alone**：同方向、同持有期，只看 funding。
6. **price+OI（不含 funding）**：同方向、同持有期，用 price+OI 的 2×2 信号，用来回答 funding 是否有增量。

### 报告表格（至少 4 张）
1. 主结果：M1a/M1b/M2/M3 × 收益/Sharpe/MDD/换手/成本。
2. baseline 对比（6 条）。
3. by-regime / by-asset。
4. 价格 vs funding vs 成本拆分。

---

## 8. 失败标准（冻结）

- **M1a/M1b**：OOS Sharpe < 0.5 **或** t < 1.5 → 判定失败；Phase 5 停，Phase 4 结论保持（只有波动稳）。
- **M2**：OOS Sharpe < 0 → 标“不可用”；不作为 Phase 5 的正面结论。
- **M3**：不设失败线；只报“相对 M1/M2 的增量”。
- 若失败，报告仍要交（负结果也是 D4 的交付），并明确写“Phase 5 未通过”。

---

## 9. 交付物与验收（冻结）

### 交付
1. `phase5/` 可复现回测代码：**一条命令**跑完训练 + 测试 + 报告。
2. OOS 报告（§7 的 4 张表 + 失败/通过判定）。
3. `phase5/REPRODUCE.md`：命令、依赖、耗时、数据前置。
4. 代码只读 Phase 1–4 的 `data/`，**不修改任何 Phase 1–4 文件**。

### 验收（三条全满足才算完成）
- 一条命令从 `data/` 重建全部结果，无手工步骤；
- 报告含 4 张表、6 条 baseline、M1a/M1b/M2/M3 分列、跳过/缺失计数；
- OOS 判定明确写“通过/未通过”，且规则未在测试期改动。

### 不要求
- dashboard、最终报告/presentation、DSR、market-neutral 版本。

---

## 10. 决策记录（Q1–Q25，已冻结）

| # | 决策 | 结果 |
|---|---|---|
| Q1 | handoff 范围 | D4 + OOS 报告；D5/D6 不在内 |
| Q2 | 策略类型 | **只做 long-only**，不做 market-neutral |
| Q3 | 规则集合 | **C：M1 + M2 + M3 overlay** |
| Q4 | 入场/出场/止损/重叠 | 下一根开盘；到期收盘；主回测无止损；同合约只留第一笔 |
| Q5 | 组合 | 10 并发、等名义 10%、1×；20% 只在 M3 |
| Q6 | 显著性 | **只用 OOS Sharpe**；不做 DSR |
| Q7 | 失败标准 | M1 OOS Sharpe <0.5 或 t<1.5 失败；M2 <0 不可用；M3 无 |
| Q8 | baseline | price-alone / random / buy-and-hold / OI-alone / funding-alone / price+OI |
| Q9 | handoff 形式 | **纯文档** |
| Q10 | D5/D6 | 显式 out of scope |
| Q11 | 事件 | phase 4 的 `cell` + `state==0` + universe；不新增阈值 |
| Q12 | 切分 | 27/27 + 3 折 walk-forward + 3 个月 final holdout |
| Q13 | 成本 | taker 0.05%/边 + 5bp 滑点；敏感性 0.02% + 2bp |
| Q14 | funding | 按结算点整笔；拆价格/funding/成本 |
| Q15 | universe | 限定当月 `in_universe` |
| Q16 | 异常值 | 主回测不 winsorise；LUNA 敏感性一行 |
| Q17 | 指标 | OOS Sharpe + 年化/波动/MDD/换手/成本后/拆分/by-regime/by-asset |
| Q18 | M3 | target-vol = target/lrv，截断 [0.5,1.5] |
| Q19 | 文档结构 | 10 节 |
| Q20 | 验收 | 一条命令 + OOS 报告 + REPRODUCE |
| Q21 | 缺 bar | ≤2 根用下一根可用；>2 跳过；计数 + 敏感性 |
| Q22 | 下架 | 最后可交易 bar 收盘平仓 |
| Q23 | 满仓 | 跳过，计数 |
| Q24 | funding 缺 | 0 carry，计数 |
| Q25 | 报告表 | 4 张表 |

---

## 11. 给接手 agent 的最后一句话

Phase 5 是**对一个探索性发现的 OOS 检验**，不是 note 假设的确认。规则已经冻结；你的工作是**忠实实现、如实报告**，包括失败。不要为了让结果好看而调窗口、调阈值、剔除事件、或换 Sharpe 口径。
