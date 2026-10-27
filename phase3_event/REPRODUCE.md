# PHASE 3 复现说明

> **状态（2026-10-27）**：v2 管线已全部跑通。八个脚本、七个闸门文件，全部 PASS。
> v1 的产物在 data/06_event_study/_archive_v1/，**只读留档，不要引用**。

## 运行顺序

```
python phase3_event/build_forward_panel.py --freq 1h     # 1. 前向面板（已有，7,252,717 行）
python phase3_event/build_event_table.py   --freq 1h     # 2. 事件表（已有，923,235 行 × 73 列）
python phase3_event/confirmatory.py                      # 3. 四个确认性检验（104 项闸门）
python phase3_event/oi_increment.py                      # 4. 六格 OI 增量（38 项，15 秒）
python phase3_event/descriptive.py                       # 5. 描述层 9/10/11/14（101 项，14 秒）
python phase3_event/baselines_v2.py                      # 6. 四条基线 + 五价差（114 项，11 分钟）
python phase3_event/figures_v2.py                        # 7. 事件路径 + 8 张图（51 项）
python phase3_event/ic_decay_v2.py                       # 8. IC 衰减（7 项，5 分钟）
```

## 产物

| 路径 | 内容 |
|---|---|
| tables/freq=1h/confirmatory_{return,vol,slope}.parquet | 实验 1–4 |
| tables/freq=1h/oi_increment.parquet | 实验 5（六格） |
| tables/freq=1h/descriptive_{core,path,by_symbol,by_state}.parquet | 实验 9/10/11/14 |
| tables/freq=1h/baselines_v2.parquet、baselines_spread.parquet | 实验 13 + 五价差 |
| tables/freq=1h/event_path_v2.parquet | 实验 12（392 行 = 2 样本 × 4 格 × 49 个 k） |
| tables/freq=1h/ic_decay_v2.parquet | 实验 15（24 行） |
| figures/f1…f8.png | 8 张图，全部从上面的表读出来 |
| docs/step{4,7,8,9,10,11,12}_*.txt | 七个闸门文件 |

## 冻结口径（D13–D20，改口径必须先改 DECISIONS.md）

| 项 | 值 |
|---|---|
| 主样本 | headline（256,079 事件）；full 只作稳健性 |
| 前向期 | 24h 为主，1/4/8h 并列 |
| 收益 | **市场中性**（逐小时减全市场等权均值）+ **全池 1%/99% 截尾** |
| 波动 | log(rv_h)，不中性化、不截尾 |
| 推断 | **只按合约聚类**（CGM 单向）；无 block bootstrap、无双向 |
| 单位 | 内部小数；×100 = 百分数，×1e4 = bp |
| 判定 | 普通显著性（等价性检验已取消，D15.2） |

## 闸门索引

| 文件 | 校验 |
|---|---|
| step4_checks_1h.txt | 事件表 923,235 行、R1–R4 计数、恒等式、截尾峰度 |
| step7_checks_confirmatory.txt | 四个检验与独立复算逐位对拍（最大偏差 4.9e-11） |
| step8_checks_oi_increment.txt | 六格；对照行口径与事件表**逐位相等**（偏差 0） |
| step9_checks_descriptive.txt | p_cont ≡ hit_rate、mdd ≤ 0、表里无 p 值 |
| step10_checks_baselines.txt | 五条基线的 n 锚点、funding 四档、每个 SE > 0 |
| step11_checks_ic.txt | 小时数对齐 v1（33,400 / 40,312）、h=1 价格 IC 更强 |
| step12_checks_figures.txt | 每张图的源表、行数、图内 n 与表内 n 对照 |

## 五条实测的坑（写脚本前必读）

1. **对照行必须用全市场池去均值**（7,010,789 行、每小时 173 个合约）。只用事件行去均值会得到 7 个，DiD 差 44%。
2. **截尾阈值全池算一次、所有组共用**。按格内算会让 R1−R4 的 DiD 变号（+2.30 → −1.74 → +0.78bp）。
3. **标签表与前向面板的分区键不一致**（月界那行落在不同 chunk）。逐分区 merge 会静默丢 9,446 个前向值，并把阈值算偏。
4. **六格只能用在含 OI 安静的样本上**。事件子样本里 OI 全超阈，q²≡1、P·q²≡P，矩阵秩只有 4。
5. **wide/close.parquet 的 ts 是 bar 开盘时刻**，存的是 ts+1h 的收盘。所以 P(T) 在 hour−1 行，错一格会让 price_change 差 4.5。

## 口径提醒

- headline 与 full **嵌套**（headline ⊂ full），不能相加、不能并列做多重检验
- excl_reason == ok 才算有效行
- p_cont ≡ hit_rate 是恒等式，不是独立证据
- 路径列（mfe/mae/mdd）**未截尾**，均值被极端路径主导，只看 p10/p50/p90
- 所有绝对水平都是负的（截尾不对称把池均值压到 −8.4bp），**必须对随机基线读，不能对 0 读**
