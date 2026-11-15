# PHASE 3 复现说明

> **状态（2026-10-28）**：16 个实验全部落盘，7 个实验脚本 + 1 个画图脚本，闸门全过。
> `exp5_9.py` 已按新定义重写（实验 5/6/7/9 + 13）；实验 8 单独一个脚本（安慰剂），`figures.py` 已按「画被检验的量」重写，
> `descriptive.py` 的收益口径已从截尾同步到不截尾（`excess_fwd`）。
> **截尾那一整套已经删掉了**：面板只剩 8 列，`stats_core.py` 已并入 `build.py`。

## 运行顺序

```
# ---- 输入层（可选：输入已在盘上；重建约 2 分钟）----
python phase3_event/build.py forward --freq 1h          # 57 秒，前向面板 7,252,717 行
python phase3_event/build.py events  --freq 1h          # 48 秒，事件表 923,235 行 × 65 列

# ---- 分析面板（拼一次，落盘，之后所有实验只读）----
python phase3_event/build.py panel                      # 29 秒，18 项闸门，输出 8 列

# ---- 实验（读 panel/ 与冻结输入，不重算数据；下列时长是 2026-10-28 实测）----
python phase3_event/experiment/exp1_4.py                #  86 秒  实验 1/2/3 + 1b（1b 是 2×2 因子，含 BH 与 drop5）
python phase3_event/experiment/exp5_9.py                #  39 秒  实验 5/6/7/9 + 13
python phase3_event/experiment/exp8_placebo.py          #  23 秒  实验 8（安慰剂；种子见下）
python phase3_event/experiment/event_path.py            #   2 秒  实验 12
python phase3_event/experiment/descriptive.py           #  45 秒  实验 4/10/11/14（rev_prob 要 join panel+forward + 双向 FE）
python phase3_event/experiment/robust_daily.py          #  36 秒  实验 15（日频汇总稳健性）

# ---- 图 ----
python phase3_event/figures.py                          #   4 秒  15 张图（Fig 1 / 1b / 2 / 3 / 4 / 5-7 / 8 / 9 / 10 / 11 / 12 / 13 / 14a / 14b / 15）
```

**整条链从头跑一遍约 6.6 分钟**（2026-10-28 实测：57 + 48 + 29 + 86 + 39 + 23 + 25 + 2 + 45 + 36 + 4 = 394 秒），
十一步全部 exit 0，闸门全过（forward / events 各自 PASS、面板 18/18、exp5_9 13/13、
event_path 13/13、descriptive 96/96、robust_daily 17/17）。

**随机性全部由 `config.EVENT` 固定**：`random_draws = 1000`（抽多少轮）、`random_seed = 20240501`（种子，实验 8 用 `random_seed + h`）。实测连跑两次 `exp8_placebo.py`，16 行数值列哈希完全一致。

Python：`C:\miniconda\python.exe`（有 pyarrow）。只出图的话装 pandas + matplotlib 就够，
`figures.py` 有 CSV fallback（没有 pyarrow 也能画）。

## 目录结构

```
phase3_event/
  build.py                 ★ 三个构建步骤：forward / events / panel（唯一的口径实现；
                             含市场中性化 cross_sectional_demean —— 主口径 `y_raw` 的定义）
  infer.py                 推断：demean2 / cgm_cov / fe_ols / bh / p_two
  figures.py               15 张图
  GUIDANCE.md       要做什么 + 结果（16 个实验，唯一权威）
  REPRODUCE.md             本文件
  experiment/              实验（读 panel/ 与冻结输入，不重算数据）
    exp1_4.py              实验 1–3 + 1b（1b 是 2×2 因子，含 BH 与 drop5）
    exp5_9.py              实验 5/6/7/9 + 13
exp8_placebo.py        实验 8（安慰剂）
        event_path.py          实验 12
    descriptive.py         实验 4（反转概率）/ 10 / 11 / 14（分合约、分市场）
    robust_daily.py        实验 16（日频汇总稳健性：观测压到「合约×日×格」；另出 robust_daily_bycount，按「当天该状态出现几个小时」分桶）

data/06_event_study/
  forward/  events/  wide/     输入（只读，约 1.8 GB；Phase 3 只用 freq=1h 那一份）
  panel/freq=1h/h={1,4,8,24}.parquet    ★ 分析面板（8 列，1.97M 行/期）
  panel/freq=1h/symbols.parquet          合约编码表
  tables/freq=1h/              各实验输出（12 张表 × parquet+csv = 24 个文件）
  figures/                     15 张图
```

> `events/` 下只有 `events_1h.parquet`。原来的 `events_{4h,8h,1d}.parquet` 是 2026-10-26 的旧 schema
> （缺 `excess_fwd_*`，带 4 个 `y_sig_*`），连主口径的因变量都没有，**已删除**；
> 要做那个频率用 `build.py forward/events --freq <f>` 重建。

## 分析面板的列

| 列 | 含义 |
|---|---|
| `symbol`, `hour` | 键（合约编码 / ts_end 的整小时）；`(symbol, hour)` 唯一 |
| `dir` | +1 价格超阈上涨 / −1 下跌 / **0 价格没超阈** |
| `oi3` | +1 OI 超阈增加 / 0 安静 / −1 减少 |
| `cell` | −1 价格没超阈 / 0 价格超阈但 OI 安静 / 1–4 = R1–R4 |
| `fund` | −1 无状态 / 0 低于 p25 / 1 中间 / 2 高于 p75 / 3 高于 p90 |
| **`y_raw`** | **市场中性、不截尾**（**唯一口径**，所有判定实验都用它）|
| `lrv` | `log(rv_h)`，不中性化不截尾 |

## 定死的口径（改任何一个都要重跑全部实验）

| 项 | 值 |
|---|---|
| 主样本 | headline：256,079 个事件（h=24 有效 255,807）|
| 事件定义 | 价格和 OI **都**超过该合约自己过去 90 天的第 70 分位 |
| 前向期 | 1 / 4 / 8 / 24 小时，四个等权，同一结构全部做 |
| 收益 | 市场中性（每小时减全市场 7,010,789 行的等权均值）、**不截尾、不翻正** |
| 波动 | `log(rv)`，不中性化不截尾 |
| 估计（实验 1–3）| 合约 + 月份**双向固定效应**，迭代到两个方向组均值都 < **1e-7** |
| 估计（实验 5–9）| **不加任何固定效应**，池起来比组均值（组合口径）|
| 标准误 | **双向聚类**（CGM）：`V = V_合约 + V_月份 − V_合约×月份` |
| 判定 | `\|t\| > 1.96`；BH 家族：实验 1/3 各 16 个、实验 4（反转概率）16 个、1b 20 个、5–9 共 28 个、16 每个指标 16 个（收益 + 波动共 32）（实验 2 不检验）|
| 结果表 | **11 列**：`experiment, h, cell, estimate, se, ci_lo, ci_hi, t, p, p_bh, t_drop5` |

**容差是 1e-7，不是 1e-12**：1e-12 要 23 轮去均值、整个流程 4 分钟变 79 分钟，结果一致。

## 实验 9 的时段口径（唯一一处与最初设计不同的地方）

最初定「每小时、每边至少 5 个合约」。四状态每小时平均只有 2.2 个 R1、2.6 个 R4，
按这个规则筛完四条信号的交集只剩 **5 个小时**——跑不出来。
现在改成 **时段 = 自然日（24 小时）、每边 ≥5 个不同合约**：交集 710–711 天，
等权逐日价差，Newey-West 滞后 1。可行性对照表在 `GUIDANCE.md` §9。

## 四条口径陷阱（都踩过）

1. **分区键不一致会静默丢数据**：标签表与前向面板的月界行落在不同 chunk，逐分区 merge
   会丢 9,446 行。一律用全局键 `hour * n_sym + code`。
2. **去均值基必须是全市场池**：7,010,789 行、每小时约 173 个合约。只用事件行会变成
   7 个合约/小时，结果差 44%。
3. **截尾不是中性变换**：h=1 时 R1 的事件被压 3.36%、它的同向池子只压 1.34%，
   一刀下去砍事件砍得更多，会让均值的差缩小甚至变号。**所以主口径不截尾。**
4. **funding 的 extreme ⊂ high**：`fund` 字段是互斥分区（extreme 单独一档），
   但价差要「高于 p75 含 extreme」的重叠口径：`fhi = (fund == 2) | (fund == 3)`。

## 口径提醒

- headline 与 full **嵌套**，不能相加、不能并列做多重检验
- 价差估计量**只用在被比较的两组行上**：参照组（OI 安静行、funding 中间档）进样本会把
  结果拉偏（同一批数据：正确做法 −0.94bp、混了参照组 −0.08bp）
- 描述层（实验 10、11、13、14）**不报 p / t / SE**；实验 12 只有按合约聚类的 SE 与 95% 区间；实验 15 只有 Newey-West 的 SE 与 t、无 p 值
- 新估计量先做**已知答案验证**：`exp5_9.self_test()` 构造已知 +5bp 的假数据，
  并验证 `t_drop5` 真的重估（顺手抓到过一个把结果压成 0 的 bug）
- 表里单位一律小数；×100 = 百分数，×1e4 = bp