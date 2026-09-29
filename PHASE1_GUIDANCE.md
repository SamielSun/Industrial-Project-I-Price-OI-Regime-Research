# Phase 1 Guidance

> 项目：THEO / FTEC5910 — **Price + Open Interest Regime Signal**
> 版本：**v3.0（定稿）**　更新：2026-09-29
> 本文档是 Phase 1 编码的**唯一依据**。未在此定义的参数，编码时不得自创。
> 产出：**D1** — 干净、可复现、无前视的 Binance 永续面板数据集

---

## 0. 目标与非目标

**目标**：D1 = ① 干净面板（Parquet）② 缺失数据报告 ③ 数据字典 ④ 校验和 + 复现命令

**非目标**：制度标注（Phase 2）· 事件研究（Phase 3）· 回测（Phase 5）· 调参拟合结果

---

## 1. 环境硬约束

| 项 | 约束 |
|---|---|
| **下载方式** | **只能用 Python**（`urllib` / `ssl` / `zipfile`）。本机 Windows schannel 故障，`curl` 与 `Invoke-WebRequest` **一律失败（连 github 都失败）** |
| 数据源 | `data.binance.vision`（可达） |
| REST API | `fapi.binance.com` **不可达**，本项目**不需要** |
| **目录枚举** | ❌ **S3 列表 API 返回空** → 只能「按已知路径探测存在性」。**因此 `manifest` 是"远端有哪些文件"的唯一本地知识** |
| 合约清单 | `www.binance.com/fapi/v1/exchangeInfo`（Python 可达，658 个 USDT 永续） |
| 依赖 | 全部用标准库 + `pandas` / `pyarrow` |

**探测资源是否存在时，必须带对照组**（同批放入已知存在的路径）。否则无法区分
"资源不存在"与"路径猜错"。

---

## 2. 数据源清单与实测属性

### 2.1 六个源

| 源 | 日频 | 月频 | 表头（已实测，多时代一致） |
|---|---|---|---|
| `klines` | ✅ | ✅ | `open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore` |
| `markPriceKlines` | ✅ | ✅ | 同上（12 列） |
| `indexPriceKlines` | ✅ | ✅ | 同上（12 列） |
| `metrics`（OI） | ✅ | ❌ **无** | `create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio` |
| `fundingRate` | ❌ **无** | ✅ | `calc_time, funding_interval_hours, last_funding_rate` |
| `premiumIndexKlines` | ✅ | ✅ | 同 klines；**不用**（见 §2.5） |

**路径模板**

```
月频  /data/futures/um/monthly/{source}/{SYM}/{SYM}-{interval}-{YYYY-MM}.zip
日频  /data/futures/um/daily/{source}/{SYM}/{SYM}-{interval}-{YYYY-MM-DD}.zip
      （metrics 无 interval 段：{SYM}-metrics-{date}.zip；fundingRate 同理）
```

**「月频 / 日频」指文件打包粒度，不是 bar 周期** —— 两者装的都是 1h bar（funding 除外）。

### 2.2 表头「有无」各不相同 → 必须逐文件检测

| 源 | `2021-12` | `2022-03` | `2022-09` 起 |
|---|---|---|---|
| `klines` | 无表头 | 有 | 有 |
| `markPriceKlines` / `indexPriceKlines` | 无 | **无** | 有 |
| `metrics` / `fundingRate` | **始终有** | | |

```python
# 唯一正确的检测方式（不可按日期硬编码）
first = raw.split("\n", 1)[0].split(",", 1)[0].strip()
has_header = not first.lstrip("-").replace(".", "").isdigit()
```

### 2.3 时间戳

```
open_time  = H                # 官方："Kline start time"  → 我们的 ts
close_time = H + 1h - 1ms     # 官方："Kline close time"（毫秒部分恒为 .999）
区间终点    = H + 1h           # 数据里没有，需自己算 = ts_end
bar1.open_time - bar0.close_time = 1 ms    # 相邻 bar 无缝
```

所有时间戳为**毫秒**（`int`）。全程 **UTC**，禁用本地时间。

### 2.4 OI 快照网格（已实测）

- **288 个/天**，100% 落在 5 分钟网格（`00:00, 00:05, …, 23:55`）
- **整点快照必然存在**（`00:00`/`01:00`/`08:00`/`16:00`/`23:00` 全部验证通过）
- `create_time` 为**时点存量值**的标签（官方确认，非区间累计量）
- 发布延迟 **1–3 分钟** → 对"bar 收盘后决策"的设计**不构成前视**

### 2.5 样本窗口与既有约束

| 项 | 事实 |
|---|---|
| **OI 归档起点** | **BTC = `2020-09-01`；其余主流币 = `2021-12-01`**（ETH/BNB/XRP/ADA/LINK/SOL/DOGE/AVAX 九个同日） |
| **主样本** | **`2021-12-01` 起**（含非 BTC 合约即被此锁死）。BTC 长历史**只做独立单币附录**，不吃进面板 |
| `mark`/`index`/`klines` 时间戳 | **完全重合**（BTC/ETH/SOL × 5 时代，零差异）→ 可自由 join |
| **月频 = 日频拼接** | **逐值完全相同**（BTCUSDT `2026-08`、`2024-06`，1,464 个时间戳零差异）→ 两源可混用 |
| 月频文件**并非每月都齐** | 实测 `2026-01` 的月频 klines 为 404 |
| 文件**不可变** | 同文件两次下载 sha256 一致 |
| `.CHECKSUM` | 三源均可得 |
| `premiumIndexKlines` | **不用**：其 12 列中 8 列为 0 或常量；基差可由 `mark_close/index_close − 1` 近似（实测中位差 **1e-5**）。改为校验项（§6.3） |
| `bookTicker` / `liquidationSnapshot` | **USDT 本位不存在**（多路径 + 对照组验证）。**不用强平数据** —— 去杠杆确认改用 **OI 单小时跌幅** + **已实现波动率**（§7.9） |

### 2.6 发布节奏（实测 `Last-Modified`）

| 数据 | 发布时点 |
|---|---|
| 日频 `metrics` | 每天 **06:39 GMT** |
| 日频 klines / mark / index | 每天 **08:00–08:34 GMT** |
| 月频 `fundingRate` | 次月 **1 日 08:24 GMT** |
| 月频 klines / mark / index | 次月 **2 日 09:00–12:00 GMT** |

**增量刷新的合适时点：每天 UTC 09:00 之后。**

---

## 3. 流水线（六步）

```
Step 0  exchangeInfo（1 次请求，秒级）
           ↓
Step 1  【硬过滤】剔稳定币、剔除从无 OI 归档的合约
        输入 658 个 USDT 永续 → 输出约 640 个
           ↓
Step 2  【算候选池】下载全部 640 个合约的【月频 klines】（约 2 小时）
        逐月算中位报价成交额 → 取前 K → 56 个月的并集
        输出：候选池（估算约 283 个，以实跑为准）
        ⚠️ 这批月频文件【保留】：它同时是 Step 4 里候选池合约的价格数据源
           ↓
Step 3  【精筛下载】只对候选池合约下载
        日频 metrics(OI) + 月频 funding / mark / index
           ↓
Step 4  合成第 2 层（4 张表，见 §8.2）
           ↓
Step 5  合成 features_1h（20 列，见 §8.3）
           ↓
Step 6  构造 universe 表（§7）
```

**为什么 features_1h 不含全部 648 个**：Step 2 已证明其余合约从未排进前 K，
**永远不可能成为样本**。

---

## 4. 参数（`config.py`，设计参数，`frozen=True`）

```python
K                 = 50        # 成员数
liq_window_days   = 30        # 流动性窗口
refresh_months    = 1         # 成员集刷新频率
min_history_bars  = 720       # 闸 2：30 天
min_oi_coverage   = 0.90      # 闸 3
min_active_days   = 15        # 闸 4
sample_start      = "2021-12-01"
buffer_L          = 0         # 不用排名缓冲带
```

**运行参数走 CLI，不进 config**：

```bash
--sample-end 2026-10-31    # 必填，无默认；必须是月末日
--no-refresh               # 可选，跳过下载只重建
--symbols BTCUSDT ETHUSDT  # 可选，调试用
```

| 取值 | 依据 |
|---|---|
| `K=50` | 第 1 名与第 50 名流动性差 168 倍，切在合理档位 |
| `liq_window_days=30` | 实测月换手 **18.9%**（60 天为 13.0%，更稳但更滞后）。取 30 天换时效性 |
| `refresh_months=1` | 滞后不进事件研究的问题，噪声才进 → 月度冻结 |
| `min_history_bars=720` | 恰好 = 流动性窗口，**最小可行值**；再小算不出 30 天中位 |
| `min_oi_coverage=0.90` | 允许 30 天缺 3 天。**不取 1.0** —— 存在全市场级偶发缺失（如 `2025-04-15`），100% 会误杀全部合约 |
| `min_active_days=15` | 有成交天数分布**两极**（正常币 30/30，停摆币 0/30），任何 10–90% 阈值都能切开 |

**稳健性对照**：`liq_window_days ∈ {60, 90}`；`refresh_months = 3`；
`K=30` 算候选池。

---

## 5. 资格闸（四条，逐期、无前视）

**必须是「逐期」判定** —— 用全生命周期的统计量（如整体覆盖率）作闸会引入前视。

| # | note 原文 | 判据 |
|---|---|---|
| **1** | Exclude **stablecoins** | 按 `base_asset` 判定，**不按符号字面** |
| **2** | Exclude **tokens with insufficient history** | 截至 M 月初已有 **≥ 720 根** 1h bar |
| **3** | Exclude contracts with **unreliable OI data** | trailing 30 天内 `sum_open_interest` **非空天数占比 ≥ 0.90** |
| **4** | Exclude **illiquid contracts** | trailing 30 天内 **≥ 15 天** `quote_volume > 0` |

**排序即第二层流动性闸**：通过四条闸后取流动性前 K。

### 5.1 三个易错点

**闸 1**：按 `base_asset` 判。`USDCUSDT`/`BUSDUSDT` 剔除，`BTCUSDT`/`ETHUSDT` 保留。

**闸 2**：用**bar 数**而非 `onboard_date` —— 合约上市与 OI 归档**不同步**（实测 BTC 差约 3 个月）。

**闸 3**：用 **`sum_open_interest` 本身的空值率**，**不得**用那 4 个衍生字段（大户多空比等）——
它们 **2022 全年大面积为空**，用作闸会把 2022 整年误杀。

**闸 4 不设绝对流动性门槛**：由「正成交额天数 + 前 K 排名」共同承担。
样本早期通过闸 1–3 的合约可能少于 K（实测 2022-01 仅 119 个），
**作为描述统计报出实际入样合约的最低流动性**（实测 2022-01 第 50 名为 `2,488,185 USDT/小时`）。

### 5.2 为什么不用「覆盖率粗筛」

用全生命周期覆盖率筛选会**误杀合法样本**（实测 90% 门槛下会剔除 203 个曾入前 50 的合约），
且**本身违反 PIT**（判断覆盖率需要知道合约的完整生命周期）。

**正确的下载集定义 = 所有刷新期前 K 名的并集**（恒等式：一个币只有排进前 K 才可能成为样本）。

| 用于算候选池的 K | 候选池规模 | 日频 metrics 下载 | 耗时 |
|---|---|---|---|
| 30 | 约 197 | 约 21.7 万 | 约 6.4 h |
| **50** | **约 283** | **约 31.1 万** | **约 9.1 h** |
| 100 | 约 452 | 约 49.7 万 | 约 14.5 h |

⚠️ 上表为估算值，**管线 Step 2 实跑后须回填确切数字**。

---

## 6. 数据质量规则

### 6.1 三个静默错误（必须处理，不会报错）

| # | 规则 | 实测依据 |
|---|---|---|
| a | **读入后立即按时间戳排序** | 近期文件非单调（2026-06/08/09 有 22–48 处负间隔）。不排序则 `shift(1)` **静默算错** |
| b | **去重** | `2020-09`→`2021-06` 每天 576 行 / 288 唯一，逐组比对为**完全一致副本** |
| c | **区分「确认 404」与「超时」** | 网络抖动会被误记为缺失（`2026-01-01` 曾被误判） |

### 6.2 已知脏点

| 位置 | 问题 | 处理 |
|---|---|---|
| `2025-04-15` | 缺失 | 记入报告 |
| 部分日期 | 287 行而非 288 | 标记 |
| **`2022` 全年** | 4 个大户多空比字段大面积空 | **不存这些列** |
| 新币首日 | 从半天开始（WIF 首行 `14:20`） | 按可用天数判定，非按上币日 |
| **零成交额月** | 文件存在但 `quote_volume = 0` | 闸 4 的判据 |

### 6.3 一致性检查（构建时执行）

| # | 检查 | 判据 |
|---|---|---|
| a | 每币每日 OI 行数 | 去重后 = 288；偏离即标记 |
| b | 时间戳落格 | 应 100% 落在 5 分钟网格 |
| c | **OI 价格一致性** | `oi_value / oi ÷ close ≈ 1`（`oi_value` 存在的意义） |
| d | **基差一致性** | `\|premium_close − (mark_close/index_close − 1)\| > 1e-3` 即告警（实测最大 1.2e-3） |
| e | 缺口报告 | 见 §9 |

---

## 7. Universe 构造规则

### 7.1 为什么 PIT，以及「rebalance」的概念错位

**这是事件研究，不是投资组合** —— 无权重、无换手成本、变动频率只影响"采样是否正确"。
不存在 `rebalance`，只有**成员集刷新**。

### 7.2 规则

```
每月 M：
  Step 1  排名量 liq(sym, 月初) = median(quote_volume) over [月初−30天, 月初)
                                                          ↑ 严格开口，否则前视
  Step 2  四条资格闸（§5）
  Step 3  对通过闸的合约按 liq 降序排名
  Step 4  取前 K = 50（无缓冲带）
  Step 5  成员集在 M 月内【冻结】
```

**关键**：`liq` 逐日滚动更新（保证无前视）；成员集按月冻结（避免成员标记变成噪声）。两件事分开。

### 7.3 流动性度量的数据源

**Step 2 与 Step 6 都用月频 klines 的 `quote_volume`，不换源。**
理由：口径必须一致（否则成循环定义）；月频对全部 640 个合约都可算，无选择效应。

### 7.4 「事实上已下架」的识别（= 闸 4 的判据）

`exchangeInfo` 的 `status` 是**当前值**，不能用于判断历史。
改用 `quote_volume == 0` —— 纯历史、无前视。

实测：出现 0 成交额的 (币, 月) 占 3.6%；其中连续 ≥3 个月的币 10/11；
最长案例 `ALPACAUSDT` 连续 **13 个月**。

### 7.5 下架币怎么退（**不要**写 `if delisted`）

```
2022-05 月初：LUNAUSDT 排名第 8 → 在成员集内
2022-05-13  ：合约结束 → 面板中该行自然终止，成员表记 2022-05 member=TRUE
2022-06 月初：闸 4 不通过（6 月无正成交额）→ 落选
```

**下架币 1–5 月的完整历史留在样本里。**

### 7.6 换手率（实测，如实报出）

K=50、30 天窗口、月度刷新 → **月换手 18.9%**（年化约 227%）。
这是加密市场流动性排名的**真实性质**，非噪声。已在 60 天窗口与季度刷新下复现主结果。

### 7.7 成员变动表（必需交付物）

```
月份     进入              退出          原因
2022-01  (首次建仓 50 个)   —             初始
2022-05  —                 LUNAUSDT      合约结束
2022-08  PEPEUSDT          GALAUSDT      排名跌出 50
```

**没有这张表，审阅者无法验证 PIT 是真做了还是只写了一句话。**

### 7.8 报告用的一句话

> *The universe is reconstructed on a point-in-time basis: membership is determined solely
> by trailing 30-day median quote volume observed strictly before each refresh date
> (monthly), with no rank buffer. Contracts are retained until they cease trading,
> identified by zero quote volume. The download pool is the union of all monthly top-50
> sets, which by construction contains every contract that can ever enter the sample;
> no future information enters the selection.*

### 7.9 去杠杆事件确认（替代强平数据）

| 用途 | 替代指标 | 来源 |
|---|---|---|
| R4「价跌 OI 降」的确认 | **OI 单小时跌幅**（`oi_change` 左尾） | metrics |
| 导师 note §11 的 "Stress / High Vol" 条件 | **已实现波动率**分位状态 | klines |

`OI` 单小时跌幅**本身就是去杠杆最直接的度量**，优于强平笔数。
**强平数据不适合做流动性度量**（它是事件驱动，不是持续属性）。

---

## 8. 对齐与 Schema

### 8.1 对齐规则

> **事件 bar `H`（收盘于 `H+1h`）配 `OI(H+1h)`。**

让 `price_change` 与 `oi_change` 落在**同一个时间区间**上：

```
price_change 用 bar(H).close vs bar(H-1h).close   → 度量 [H-1h, H]
oi_change    用 OI(H)     vs OI(H-1h)             → 同样 [H-1h, H]   ✅
```

**OI 取值列**：`sum_open_interest`（**张数**）。
**不用** `sum_open_interest_value`（会把价格变动混进 OI 变化）。

#### ⚠️ 月末边界：必须跨月取数

```
2026-08 最后一根 bar = 08-31 23:00 → 需要 OI(09-01 00:00)
但 08-31 的 metrics 文件最大时间戳 = 08-31 23:55
  → 该快照在【下一个月】的文件里
```

**逐月独立处理会每月丢最后一根 bar（4.8 年约丢 58 根/合约）。** 同
理适用于日频：`daily/metrics/{d}` 的最后快照是 `d 23:55`，需从 `{d+1}` 取。

### 8.2 第 2 层：4 张规范化表

| # | 表 | 主键 | 频率 | 源 | 列 |
|---|---|---|---|---|---|
| 1 | `klines_1h` | `(symbol, ts)` | 1h 原生 | `klines` 月频 | `ts_end`, OHLC, `volume`, `quote_volume`, `trades`, `taker_buy_volume`, `taker_buy_quote_volume` |
| 2 | `mark_index_1h` | `(symbol, ts)` | 1h 原生 | `markPriceKlines` + `indexPriceKlines` | `ts_end`, `mark_close`, `index_close` |
| 3 | `oi_1h` | `(symbol, ts)` | 5m→1h 对齐 | `metrics` 日频 | `ts_end`, `oi`, `oi_value`, `oi_missing` |
| 4 | `funding` | `(symbol, ts_funding)` | 8h 事件 | `fundingRate` 月频 | `funding_rate`, `funding_interval_hours` |

**不存的源**：

| 源 | 理由 |
|---|---|
| `premiumIndexKlines` | 8/12 列为 0 或常量；基差可由 mark/index 近似（中位差 1e-5） |
| `oi_5m` 全量 | 主分析不用；行数约 1.4 亿（`oi_1h` 的 11 倍）。**不保留 RAW** |
| mark/index 的 OHLC 与 `volume`/`count` | 实测 `volume=0`、`count=3600`（常量） |

### 8.3 `features_1h`

**主键** `(symbol, ts)`　**分区** `year=YYYY/chunk=YYYY-MM.parquet`

| # | 列 | 类型 | 单位 | 语义 |
|---|---|---|---|---|
| 1 | `symbol` | string | — | 合约 |
| 2 | `ts` | datetime64[ns, UTC] | — | **bar 起点 `H`** |
| 3 | `ts_end` | datetime64[ns, UTC] | — | `ts + 1h`；**区间终点 = OI 对齐时刻** |
| 4–7 | `open` `high` `low` `close` | float64 | USDT | |
| 8 | `volume` | float64 | 基础资产 | |
| 9 | `quote_volume` | float64 | USDT | 流动性度量原料 |
| 10 | `trades` | int64 | 笔 | |
| 11 | `taker_buy_volume` | float64 | 基础资产 | |
| 12 | `taker_buy_quote_volume` | float64 | USDT | |
| 13 | **`oi`** | float64 | **张** | `OI(ts_end)` |
| 14 | `oi_value` | float64 | USDT | 一致性校验用 |
| 15 | `mark_close` | float64 | USDT | |
| 16 | `index_close` | float64 | USDT | |
| 17 | `funding_rate` | float64 | 小数 | **仅 `00/08/16` 非空** |
| 18 | `funding_interval_hours` | int8 | 小时 | **仅结算时刻非空** |
| 19 | `bar_missing` | bool | — | 该小时 kline 原始行不存在 |
| 20 | `oi_missing` | bool | — | 该小时 OI 快照不存在 |

```sql
features_1h = klines_1h
    LEFT JOIN mark_index_1h ON (symbol, ts)
    LEFT JOIN oi_1h          ON (symbol, ts)
    LEFT JOIN funding        ON (symbol, ts_end = ts_funding)
```

**不加的列**：4 个 OI 衍生字段（2022 大面积为空）· `ignore`（恒为 0）·
`ingested_at`（每次重建都变，破坏复现比对）· `is_funding_hour` 之类标记
（下游由 `hour % 8 == 0` 推出）。

**派生量**（`price_change` / `oi_change` 及 lookback `N`）**一律放 Phase 2**
—— 否则改一次 `N` 就要重跑 10+ 小时的数据层。

**「不加 PIT 过滤」≠「包含全部合约」**：`features_1h` **只含候选池合约**，
但候选池合约的**所有小时**都保留。

```python
assert set(features_1h.symbol.unique()) == set(candidate_pool)
```

---

## 9. 增量更新

### 9.1 数据源优先级规则

```
对每个 (symbol, 时间戳):
    该月的【月频文件】在 manifest 中 status = ok   →  用月频
    否则                                        →  用日频补
    两者都没有                                   →  该时间戳不存在
```

因**月频 = 日频拼接（逐值相同）**，两者可自由混用，**增量不必等月份结束**。

### 9.2 流程

```
run_pipeline.py --sample-end YYYY-MM-DD

【A】更新合约清单      exchangeInfo → master
【B】确定该有哪些文件   候选池 × 存续期 × [sample_start, sample_end]
【C】与 manifest 对账   跳过 status=ok；跳过 confirmed_404（TTL 内）
【D】下载缺失的         月频（若有）+ 日频（补不完整月）
【E】增量建第 2 层      只解析 layer2_built_at 为空的文件
【F】增量建 features_1h upsert 到受影响的 chunk
【G】建 universe 表
```

**`sample_end` 决定裁剪边界，不决定数据来源。**

### 9.3 `manifest` 表结构

| 列 | 含义 |
|---|---|
| `source` / `symbol` / `period` / `granularity` | 定位 |
| `remote_path` / `filename` | **重下时唯一依据**（无法枚举远端目录） |
| `status` | `ok` / `confirmed_404` / `retry_exhausted` |
| `checksum_official` / `checksum_verified` / `bytes` | 校验 |
| `first_seen_at` / `last_probed_at` / `downloaded_at` | 时间戳 |
| `layer2_built_at` | 是否已并入第 2 层（**增量解析的入口**） |

### 9.4 三个边界

**① `confirmed_404` 需 TTL 重探（7 天）**

月频文件在次月 1–2 日才发布，且**并非每月都齐**。
若永久缓存 404 会**永久漏掉**该文件。已发布的文件不会消失，重探代价小。

**② `upsert` 而非覆盖**

新月份数据落在已有年份分区里：读现有 chunk → 合并 → 按主键去重（新数据优先）→ 原子写回。

**③ chunk 按「月」切**

因 `sample_end` 只用完整月，月是天然原子单位：**完整月的 chunk 一旦写完永不改变**，
每次增量只重写"受影响的那一两个 chunk"。

| 状态 | 哪些 | 行为 | 不变量 |
|---|---|---|---|
| **frozen** | 除最后 1 个外全部 | 写完不改 | 行数按 `(chunk, symbol)` 固定 |
| **hot** | `sample_end` 所在月 | 每次追加 | 行数单调增 |

⚠️ 新上市合约首月不满整月（`WIFUSDT` 2024-01 仅 116 行）。
**行数不变量按 `(chunk, symbol)` 判定，不按 chunk 总行数。**

### 9.5 缓存必须原子写

```python
tmp = path + ".tmp"
json.dump(snapshot, open(tmp, "w"))
os.replace(tmp, path)          # 加锁取快照后再写
```

**依据**：曾因在迭代中直接 `json.dump` 导致字典变更异常 + 文件截断，
**3,500 条已下载结果全部丢失**。

---

## 10. 磁盘布局

```
data/
│
├─ 00_config/                         构建元信息
│   ├─ sample_end.json                {"sample_end": "...", "config_hash": "..."}
│   └─ manifest.parquet               增量下载的唯一依据
│
├─ 01_layer2/                         4 张规范化源表（小时粒度）
│   ├─ klines_1h/year=YYYY/chunk=YYYY-MM.parquet
│   ├─ mark_index_1h/year=YYYY/chunk=YYYY-MM.parquet
│   ├─ oi_1h/year=YYYY/chunk=YYYY-MM.parquet
│   └─ funding/year=YYYY/chunk=YYYY-MM.parquet
│
├─ 02_features/
│   └─ features_1h/year=YYYY/chunk=YYYY-MM.parquet
│
└─ 03_reference/                      分析与审计用的参考表
    ├─ master.parquet                  一币一行（658）
    ├─ universe_eligibility.parquet    一币一行（约 283）
    ├─ universe_membership.parquet     (symbol, date)
    └─ member_changes.parquet          进/出记录
```

**不保留 RAW 归档**（`oi_5m` 全量、zip 镜像均不存）。**不需要抽样验证步骤。**

**`universe_*` 放 `03_reference/`**：其粒度是**日**（`(symbol, date)`）与**合约**（`symbol`），
与 `features_1h` 的**小时**粒度不同，不能混放。

| 路径 | 预期行数 | 预期体积 |
|---|---|---|
| `01_layer2/klines_1h/` | 约 1,250 万 | 约 150 MB |
| `01_layer2/mark_index_1h/` | 约 1,250 万 | 约 60 MB |
| `01_layer2/oi_1h/` | 约 1,250 万 | 约 80 MB |
| `01_layer2/funding/` | 约 150 万 | 约 10 MB |
| `02_features/features_1h/` | 约 1,250 万 | 约 300 MB |
| `03_reference/` | 658 + 283 + 49 万 + 几百 | 约 6 MB |
| `00_config/manifest` | 约 35 万 | 约 20 MB |
| **合计** | | **约 630 MB** |

**磁盘已确认 > 30 GB 可用。**

---

## 11. 下载工程要求

| # | 要求 | 依据 |
|---|---|---|
| a | **自适应并发 + 重试** | 并发 16→32 吞吐仅 6.25→7.90 文件/秒，**已饱和**；延迟 p50=1.1s 但 **max=45.8s** → 固定线程池会大量空转 |
| b | **失败分类记账** | `confirmed_404` / `retry_exhausted` 严格分开 |
| c | **断点续传 + 原子写缓存** | §9.5 |
| d | `.CHECKSUM` 校验 | D1 验收要求 |
| e | 禁用 `curl` / `Invoke-WebRequest` | §1 |

---

## 12. 产出物（D1）

| # | 产出 | 形式 |
|---|---|---|
| a | 干净面板数据集 | `02_features/features_1h/` |
| b | **缺失数据报告** | 见 §12.1 |
| c | 数据字典 | 字段名、单位、频率、来源路径、语义、已知问题 |
| d | 校验和记录 | `manifest.parquet` |
| e | `master` 表 | `03_reference/` |
| f | `universe_eligibility` 表 | `03_reference/`，建议进报告附录 |
| g | `universe_membership` 表 | `03_reference/` |
| h | **成员变动表** | `03_reference/member_changes` |
| i | `manifest` | `00_config/` |
| j | `sample_end` 记录 | `00_config/sample_end.json` |
| k | 复现命令 | `python run_pipeline.py --sample-end <日期>` |

### 12.1 缺失数据报告的粒度 ✅

**检测用「日」，呈现用「连续缺口区间」**（不按日、也不按月）。

- **纯月粒度太粗**：`2025-04 覆盖率 29/30` 看不出缺的是哪天
- **纯日粒度表爆炸**：约 200 万行，其中 99% 是「正常」

**缺口区间表**（把相邻缺失日合并成一条）：

| symbol | data_type | gap_start | gap_end | days | category |
|---|---|---|---|---|---|
| BTCUSDT | metrics | 2025-04-15 | 2025-04-15 | 1 | `confirmed_404` |
| ALPACAUSDT | klines | 2025-05-01 | 2026-05-31 | 396 | `zero_volume` |

**预期几百到几千行，可逐行肉眼审。**

**五个类别必须严格区分**（把网络错误写成缺失是本项目真实犯过的错）：

| category | 算真缺失? |
|---|---|
| `confirmed_404` | ✅ 是 |
| **`retry_exhausted`** | ❌ **不是** —— 是待办，**不得进入最终缺失报告** |
| `partial_rows`（行数 < 288） | ⚠️ 记录 |
| `field_empty` | ⚠️ 记录 |
| `zero_volume` | ⚠️ 记录 |

**另配覆盖率汇总表**：明细回答「哪里缺」，汇总回答「整体质量如何」。

---

## 13. 一阶问题：事件在时间上高度聚集

**优先级高于 universe 调参。**

**实测（200 个币，`2025-07-15`）**：

| 指标 | 值 |
|---|---|
| 每小时触发 OI 事件的币数 · 中位 | **51** |
| 最密集一小时 | **91 个币同时触发** |
| **最稀疏一小时** | **29 个币** |
| 有效样本压缩比 | **约 52 : 1** |

1. **「50 个币同一小时触发」不是 50 个独立观测** → Phase 3 必须按**日历时点聚类**
   （`cov_type="cluster"`, `groups=date`），并按币种聚类做稳健性对照。
2. **分位数阈值根本没筛出事件**（最稀疏一小时也有 29 个币触发）
   → 阈值**必须实测标定**，不能拍分位数。

---

## 14. 早期观察（不属于 Phase 1 产出）

> 实测 4,800 个 (币, 小时)：**`dOI` 与同期 `dP` 的相关系数仅 +0.0044**（分币 −0.099 ~ +0.060）。
>
> **1 小时尺度上 OI 变化与价格变化几乎无关。** 这对导师 note 的核心前提是**前置负面信号**，
> 但**不能**据此下结论 —— 它测的是同期相关，非预测能力。留作 Phase 3 正式检验。

---

## 15. 实测结论的复现说明

> ⚠️ 侦察脚本已按要求删除。本文档的实测数字**当前无法一键复现**，下表给出重获方式。

| 结论 | 数据来源 | 重获方式 |
|---|---|---|
| OI = 5 分钟网格、288 点/天、整点存在 | `daily/metrics` | 下载任一日文件，去重排序后检查 |
| BTC OI 起点 `2020-09-01`；其余 `2021-12-01` | 同上，逐日 HEAD | 二分定位 |
| `2020-09`→`2021-06` 重复行 | 同上 | 按 `create_time` 计数 |
| 近期文件非单调 | 同上 | 排序前检查负间隔 |
| 大户多空比 2022 大面积空 | 同上 | 检查第 5–8 列 |
| `quote_volume == 0` 识别下架 | `monthly/klines` | 统计第 8 列为 0 的月份 |
| 候选池并集（K=50） | 同上 | 逐月排序取前 K，取并集 |
| 换手率矩阵 | 同上 | 按窗口 × 刷新频率组合模拟 |
| `dOI` vs `dP` 相关 +0.0044 | `daily/metrics` + `daily/klines` | 整点对齐后算相关系数 |
| 事件聚集度 | `daily/metrics`（200 币） | 每个整点统计越阈币数 |
| **月频 = 日频拼接** | `monthly` + `daily` klines | 逐时间戳比对（1,464 个零差异） |
| mark/index/klines 时间戳重合 | 三源月频 | 比对时间戳集合 |
| 强平/bookTicker 不存在 | 多路径 HEAD | **必须带对照组** |
| 表头有无的边界 | 多时代文件 | 检查首列是否为数字 |
