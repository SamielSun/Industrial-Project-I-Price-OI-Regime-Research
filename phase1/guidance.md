# Phase 1 Guidance

> THEO / FTEC5910 — **Price + Open Interest Regime Signal**
> 更新：2026-10-02
> **本文件是 Phase 1 的唯一依据。未在此定义的参数，编码时不得自创。**
> 产出：**D1** — 干净、可复现、无前视的 Binance 永续面板数据集

---

## 0. 一页速览

**D1 是什么**：285 个 Binance USDT 本位永续、57 个月、逐小时的分析面板，
外加缺失报告、数据字典、校验和。

| 指标 | 数值 |
|---|---|
| 主面板 `features_1h` | **7,253,002 行 / 19 列 / 57 个月** |
| 合约数 | 候选池 **285**；曾当成员 **248** |
| 样本窗口 | `2021-12-01` ~ `2026-08-31` |
| 月度成员集 | 有成员的月份各 50 个，共 **2,700** 行 / 54 个月 |
| 磁盘 | **2.2 GB / 1,442 个文件** |
| 全流程实测 | 本地计算约 **26 分钟**（首次下载另需约 2 小时） |

**四件产出**

| # | 产出 | 位置 |
|---|---|---|
| ① | 干净面板 | `data/02_features/features_1h/` |
| ② | 缺失报告 | `data/04_qa/{missing_files,gaps,coverage}.parquet` |
| ③ | 数据字典 | `data/04_qa/data_dictionary.md` |
| ④ | 校验和 + 复现命令 | `data/04_qa/checksums.sha256` · `data/REPRODUCE.md` |

**非目标**：制度标注（Phase 2）· 事件研究（Phase 3）· 回测（Phase 5）。

**命名**：`Phase 1–5` = 项目阶段；`Step 0–6` = §2 的数据流；脚本按作用命名，不用编号。
`data/` 的 `00_`–`04_` 只是**阅读顺序**，不是依赖链。

---

## 1. 做完的东西放在哪

```
Industrial Programme I/
├─ config.py                 设计参数 —— 各阶段共用
├─ lib/schema.py             数据契约 —— 各阶段共用
├─ data/                     全部产出（Phase 2–5 的正式输入）
│   ├─ 00_config/            manifest · sample_end.json
│   ├─ 01_layer2/            4 张规范化源表
│   ├─ 02_features/          features_1h —— 分析面板
│   ├─ 03_reference/         候选池 + universe 四表
│   ├─ 04_qa/                缺失报告 + 字典 + 校验和
│   ├─ raw/                  五个源的原始 parquet
│   └─ REPRODUCE.md          六条重跑命令
├─ phase1/                   Phase 1 的代码 + 本文件
└─ research_archive/         导师 note · 文献 · 提交件
```

`data/` 不进版本控制（2.2 GB，可由 `REPRODUCE.md` 完全重建）。

---

## 2. 处理流程

### 2.1 总表

| Step | 脚本 | 输入 | 输出 | 实测 |
|---|---|---|---|---|
| **0** | `build_candidate_pool.py` | S3 列表接口 | 归档合约 **1,057** | 秒级 |
| **1** | 同上 | + `exchangeInfo` | 硬过滤后 **683** | 秒级 |
| **2** | 同上 | 月频 `klines`（**18,832** zip） | **候选池 285** | 缓存命中 119s |
| **3** | `fetch_market_data.py` | 候选池 + S3 列表 | `raw/` **1,144 文件 / 1.10 GB** | 约 111 分钟 |
| **4** | `build_layer2.py` | `raw/` | 4 张表 **228 文件 / 546.8 MB** | **847s** |
| **5** | `build_features.py` | 4 张表 | `features_1h` **57 文件** | **357s** |
| **6a** | `build_universe.py` | 面板 + 候选池 + manifest + **快照** | universe 四表 | **239s**（走快照） |
| **6b** | `build_qa.py` | 面板 + manifest | 缺失报告 + 字典 + 校验和 | **30s** |

**六条命令按此顺序执行，Step 6b 必须最后跑**（原因见 §5.2）。

**两个影响复现的环境事实**
- **下载只能用 Python 的 `urllib`** —— 本机 Windows schannel 故障，`curl` / `Invoke-WebRequest` 一律失败。
- **`s3-ap-northeast-1.amazonaws.com` 与 `www.binance.com` 的 DNS 被污染**，需要 VPN。
  `data.binance.vision`（CloudFront）不受影响。
- **需要 VPN 的步骤**：Step 0–3。
  **Step 6a 只要快照在就不需要网络**（§2.2 有说明；快照随代码进版本控制）。
- 依赖：Python 3.12 + `pandas` 2.3.3 / `pyarrow` 23.0.1。

### 2.2 逐步说明

---

#### Step 0–1 · 枚举与硬过滤

**输入**：S3 列表接口
`.../data.binance.vision?list-type=2&prefix=<前缀>&delimiter=/&max-keys=1000`
返回 XML，用 `IsTruncated` / `NextContinuationToken` 翻页。

**输出**：归档里**存在过**的全部合约 —— 实测 **1,057** 个（USDT 结尾 901），
落盘到 `data/00_config/archive_contracts.csv`（逐合约一行，含分类与 base/quote）。

**Step 1 的输出同样落盘**：`data/00_config/dropped_contracts.csv`
（218 行，逐合约记 `symbol` / `base_asset` / `reason` / `is_stablecoin`）。
为什么必须有：原来只落了计数（`sample_end.json` 的 `eligible_after_hard_filter`），
被剔除的**名单只打日志** —— 于是"`USDCUSDT` 是在哪一步被剔的"事后无法回答，
只能重跑重现，而重跑依赖 exchangeInfo 与归档两个外部状态，未必复现同一结果。

⚠️ **这个数必须落盘，不能只打日志。** 枚举结果曾经不一致：一次记 **893**、
一次记 **1,057**，差 164 个。而合约数只增不减，所以 893 必然是一次不完整枚举。
这个数又是「契约总数」这条基线，不落盘就无从对账，也无从判断某次运行漏了合约。

**后续实测（2026-10-04）**：连跑 3 次枚举，结果**完全相同**，均为 1,057
（并集 = 交集 = 1,057）。所以接口**当前是稳定的** —— 但那次不一致真实发生过，
且落盘成本几乎为零，所以 `archive_contracts.csv` 保留。

**⚠️ 合约清单只能来自归档枚举，不能用 `exchangeInfo`。** 后者只保留当前挂牌 +
近期退市（约 130 天）：683 个保留合约里只有 648 个能查到，查不到的 29 个正包含
`LUNAUSDT` 等样本期内最重要的事件标的 —— **用它当清单会制造幸存者偏差。**

**Step 1 处理**：五条硬过滤 —— 非 USDT 本位、名称怪象（交割 / `SETTLED` 后缀）、
稳定币、代币化传统金融（分类字段判据）。实测 **1,057 → 683**：

| 判据（代码条件） | 拦下 |
|---|---|
| `s.endswith("USDT")` 为假（非 USDT 结尾） | **156** |
| `not (ct=="PERPETUAL" and ut=="COIN")`（非加密资产） | **215** |
| `base_asset in stablecoin_bases`（稳定币） | **3** |
| `'_' in s or 'SETTLED' in s`（交割 / SETTLED） | **0** |
归档里混着美股（`TSLAUSDT`）、港韩 A 股、ETF、商品、指数（`DEFIUSDT`）、外汇，
不先过滤会让结论无法解释。

⚠️ 上表能算出来，靠的是 `archive_contracts.csv` 与分类表快照都含
`base_asset` / `quote_asset` —— 缺这两个字段时第一条判据的剔除数无法重现。

---

#### Step 2 · 候选池

**输入**：683 个合约 + 月频 `klines`（**18,832 个 zip**，这一步只下 `klines`）。

**处理**
```
逐月 M：liq = median(该月全部小时的 quote_volume)      ← 整月，约 720 根 1h bar
        → 过草稿闸：上月(M−1)有效小时数 >= 360        ← 只用 M 之前的数据，无前视
        → 按 liq 降序取前 K = 50
候选池 = 各月前 50 名的并集
```

**草稿闸只有一条**：`bars[M−1] >= 360`（即 `24 × 15` 小时，半个月）。
`i < 1` 单独挡掉样本首月（没有"上一个月"可比）。实测拦截 **967 个 (合约,月)**。

原设计有第二条「闸 A：到 M 月初为止窗口内已有 ≥ 1 个月数据」，**实测拦不到任何东西，已删除**：

| | 挡下的 (合约,月) |
|---|---|
| 只有闸 A 挡下 | **0** |
| 只有闸 B 挡下 | 290 |
| 两个都挡 | 677（全在 `2021-12`，样本首月无历史） |

原因是合约的数据月份**天然连续** —— 上月有 bar 就意味着之前也有，闸 A 恒被闸 B 蕴含。
连 3 个「上月在册但 bar < 360 且更早有数据」的边界合约（`ICPUSDT 2022-10` 仅 94 bar、
`BNXUSDT 2023-03` 仅 154、`TLMUSDT 2023-04` 仅 36）也全部由闸 B 挡下。
删除后逐 (合约,月) 判定与逐月成员集**完全一致**（0 处差异，候选池仍 285）。

**为什么必须有这条闸**：防的是**流动性极好的新上市合约**。实测 `2023-05`：

| 名次 | 合约 | 当月 liq 中位 |
|---|---|---|
| 1 | `BTCUSDT` | 343,448,934 |
| 2 | `ETHUSDT` | 163,997,375 |
| **3** | **`1000PEPEUSDT`** | **41,805,004** ← 被闸挡下 |
| **8** | **`SUIUSDT`** | **11,072,299** ← 被闸挡下 |

`1000PEPEUSDT` 在 190 个合约里**排第 3**，但没有闸它就是当月成员 —— 而它的 regime
阈值要用 rolling 分位估，几天数据估出来的是噪声。各月被挡数 1~19 个，随新币上市节奏波动。

**流动性用中位数而非平均**：单小时 `quote_volume` 能被拉高 **15 倍**（`BTCUSDT 2023-05`：
中位 3.43 亿、最大 51.6 亿、平均被右尾拉高 44%），个别合约平均/中位达 **5.0 倍**。
中位数衡量"典型小时能不能进得去"，这正是交易成本的意义。换指标会换掉成员：
`mean`/`sum` 换掉 8 个（2023-05）、`p25` 换掉 2~4 个、`median(trades)` 换掉 10~16 个
（后者换了维度——笔数 vs 金额）。

**输出**：`data/03_reference/candidate_pool.csv` —— 一列 `symbol`，285 行。
```
symbol
1000BONKUSDT
1000FLOKIUSDT
...
币安人生USDT          ← 归档里有中文名合约，URL 与文件系统都要能处理
```

**它代表什么**：**下载范围**，不是"好合约名单" —— 一个币只有排进过某月前 50
才可能成为样本，所以候选池 = 所有前 50 名的并集。**它同时是成员集的下界**：
这一步只能做闸 2 的草稿版（闸 3 要 OI 数据，那时还没下），Step 6a 会用完整四条闸再筛。

**为什么只下 `klines`**：产出只是一个排名，排名只用 `quote_volume`。
mark / index / funding 归 Step 3。**`premiumIndexKlines` 永不下载。**

---

#### Step 3 · 精筛下载

**输入**：候选池 285 个合约 + S3 列表接口（确定该有哪些文件）。

**处理**：只对候选池合约下载五个源，**一遍过**（§6.1）。

**输出**：`data/raw/` —— **1,144 个 parquet / 1.10 GB**
```
raw/klines/symbol=XXX.parquet           285 个   1h bar，12 列源原样
raw/markPriceKlines/symbol=XXX.parquet  284 个   同上
raw/indexPriceKlines/symbol=XXX.parquet 284 个   同上
raw/fundingRate/symbol=XXX.parquet      285 个   结算事件（4h 或 8h）
raw/metrics/year=YYYY.parquet             6 个   整点 OI 快照，按年合并
```

**它代表什么**：zip 已就地解压清理，**原始 zip 不保留**。这一步之后不再需要网络。

- **没有 `premiumIndexKlines`**：12 列中 8 列恒为 0 或常量。
- **`metrics` 只留整点与 3 列**（`symbol` `create_time` `sum_open_interest`）。源是
  5 分钟网格、8 列，本项目只用整点 OI。
- **`metrics` 按年合并、其他按合约**：`metrics` 是**逐合约逐日**的文件
  （下载范围共 **305,454 个**），逐日存会得到 30 多万个小文件。
- **进度记录**：`data/00_config/manifest.parquet`，逐文件一行（§7.3）。

---

#### Step 4 · 第 2 层（4 张规范化源表）

**输入**：`data/raw/` 的 1,144 个 parquet。

**处理**：统一时间戳、类型、列名 → 按 `(symbol, 月)` 分块落盘。

**输出**：`data/01_layer2/` —— **228 个文件 / 546.8 MB**，
路径 `{表名}/year=YYYY/chunk=YYYY-MM.parquet`。

| 表 | 主键 | 频率 | 行数 | 列 |
|---|---|---|---|---|
| `klines_1h` | `(symbol, ts)` | 1h 原生 | 7,567,853 | `symbol` `ts` `ts_end` `open` `high` `low` `close` `volume` `quote_volume` `trades` `taker_buy_volume` `taker_buy_quote_volume` |
| `mark_index_1h` | `(symbol, ts)` | 1h 原生 | 7,567,853 | `symbol` `ts` `ts_end` `mark_close` `index_close` |
| `oi_1h` | `(symbol, ts)` | 5m→1h | 7,567,853 | `symbol` `ts` `ts_end` `oi` `oi_missing` |
| `funding` | `(symbol, ts_funding)` | 4h/8h 事件 | 1,229,941 | `symbol` `ts_funding` `funding_rate` `funding_interval_hours` |

`klines_1h`（2022-01，前两行真值）
```
        symbol         ts      ts_end      open      high       low     close       volume  quote_volume   trades
  1000SHIBUSDT 2022-01-01 00:00Z  ...01:00Z  0.033373  0.033890  0.033368  0.033823  522172816.0  17544580.0  28027.0
  1000SHIBUSDT 2022-01-01 01:00Z  ...02:00Z  0.033830  0.033988  0.033718  0.033799  483119781.0  16350770.0  25360.0
```
`oi_1h`（同 chunk）
```
        symbol         ts      ts_end           oi  oi_missing
  1000SHIBUSDT 2022-01-01 00:00Z  ...01:00Z  2.385715e+09       False
```
`funding`（同 chunk）—— **只有结算时刻有行**
```
        symbol ts_funding  funding_rate  funding_interval_hours
  1000SHIBUSDT 2022-01-01 00:00Z        0.0001                     8.0
  1000SHIBUSDT 2022-01-01 08:00Z        0.0001                     8.0
```

**它代表什么**：**四张表都以 `klines` 的网格为准** —— 前三张行数完全相同
（**7,567,853**），mark / index / OI 缺的小时留 `NaN`，**不发明行、也不删行**；
只有 `funding` 是稀疏事件表。**这就是第 2 层与 `features_1h` 的区别所在** ——
不在"稀疏 vs 密集"（两者都密集），而在**缺值怎么表达**：第 2 层用 `NaN`，
`features_1h` 另加布尔列把「源里没有」与「值为空」分开。

**三条口径**
- **都存 `ts_end` = `ts + 1h`**：区间终点 = OI 对齐时刻 = 决策时刻，也是 `funding`
  的 join 键。不存就要每次自己算，算错偏 1 小时且不报错。
- **OI 对齐规则是 `ts_end == create_time`**（实测：TLMUSDT 2021-12-01 的
  bar `[00:00,01:00)` 的 `oi` = 102,744,323 = `create_time` 01:00 的快照）。
  ⚠️ **`create_time` 秒位必须截断** —— 见 §4.1 规则 7。
- **`klines_1h.trades` 来自源列 `count`**（改名）。
- **`mark_index_1h` 合并 mark 与 index**：两者都以 `klines` 网格为准，
  `(symbol, ts)` 集合一致。⚠️ 但**缺值率不同**（mark 0.28% vs index 3.00%），
  合表后大量"mark 有值而 index 为 `NaN`"是正常的。


---

#### Step 5 · `features_1h`（分析面板）

**输入**：`data/01_layer2/` 的 4 张表 + 候选池名单。

**处理**
```
1. 密集网格：对每个候选池合约，从第一根 bar 铺到最后【正成交额】日的 23:00
2. 死尾裁剪：合约停止交易后的零成交空行全部丢弃（原因见 §4.2）
3. 四表 LEFT JOIN 到网格上
```

**输出**：`data/02_features/features_1h/year=YYYY/chunk=YYYY-MM.parquet`
—— **57 个文件 / 541.5 MB / 7,253,002 行 / 19 列**

行数恒等式：`7,567,853（源行） − 321,737（死尾） + 6,886（补网格） = 7,253,002`

**19 列**
```
symbol  ts  ts_end  open  high  low  close  volume  quote_volume  trades
taker_buy_volume  taker_buy_quote_volume  oi  mark_close  index_close
funding_rate  funding_interval_hours  bar_missing  oi_missing
```

**join 关系**
```sql
features_1h = klines_1h
    LEFT JOIN mark_index_1h ON (symbol, ts)
    LEFT JOIN oi_1h          ON (symbol, ts)
    LEFT JOIN funding        ON (symbol, ts_end = ts_funding)
```

**三类行的真值**（BTCUSDT / ICPUSDT，2022-01）
```
结算小时   ts = 2022-01-01 00:00Z  close = 46650.01  oi = 74940.944  funding_rate = 0.0001  interval = 8.0
普通小时   ts = 2022-01-01 01:00Z  close = 46766.78  oi = 74695.212  funding_rate = NaN     interval = 8.0
缺 OI      ICPUSDT  ts = 2022-01-01 00:00Z  close = 25.00  oi = NaN  oi_missing = True
```

**它代表什么**：**这是 Phase 2–5 唯一的输入**。每个 `(symbol, ts)` 恰好一行，
可以不做任何对齐检查就按小时 rolling / shift。

| 列 | 语义 |
|---|---|
| `ts` / `ts_end` | bar 起点 / 区间终点。**决策发生在 `ts_end`** |
| `oi` | `OI(ts_end)`，**张数** |
| `funding_rate` | **只在结算小时非空** → 全表 **83.4%** 为 null。结构性的，不是缺失 |
| `bar_missing` / `oi_missing` | 该小时在源表里没有对应行。**值列为 null 时的原因标记** |

**⚠️ 结算周期不是恒定的 8 小时**：实测每合约众数间隔 **4h = 142 个，8h = 142 个，
1h = 1 个**（91 个合约中途改过）。所以 `funding_rate` 非空的整点是
`00/04/08/12/16/20`（两组叠加）。**判"是不是结算小时"要读
`funding_interval_hours`，不要硬编码小时表。**

**`funding_rate` 不 ffill，`funding_interval_hours` 要 ffill**：前者是**结算事件**，
填上一个值会让 Phase 2 误以为"每小时都有资金费率"；后者描述当前生效的周期。

**不存的源列**：`sum_open_interest_value`（与 `oi × close` 冗余）· 4 个大户多空比
字段（2022 全年大面积为空）· `ignore`（恒为 0）· mark/index 的 OHLC 与
`volume` / `count`（`volume = 0`、`count = 3600`，常量）。

**派生量一律不做**：`price_change` / `oi_change` 及 lookback 全放 Phase 2 ——
否则改一次参数就要重跑整条数据层。**范围**：只含候选池 285 个合约，
但候选池合约的**所有小时**都保留。

**Phase 2 的 horizon 规划值**：`(1, 4, 8, 24)` 小时。原先登记在
`config.py` 的 `event_lookbacks` 字段里，因 Phase 1 全程不使用（只被
`snapshot()` 序列化进 `sample_end.json` 冒充设计参数）已删除，规划信息记在此处。
Phase 2 定义这些列时，应把它们放进**当时的** `config.py`（那时它才是真设计参数）。

---

#### Step 6a · Universe（资格判定 + PIT 成员）

**输入**：`data/02_features/features_1h/` + `data/03_reference/candidate_pool.csv`
+ `data/00_config/manifest.parquet`（决定评测哪些合约）
+ **`phase1/exchange_info_snapshot.json`**（闸 4 的判据）。

**闸 4 的判据走快照，不是每次联网取。** 顺序是：`--refresh-exchange-info` →
联网取并覆盖快照；否则先读快照；快照不存在才联网取。**取数来源与指纹记进
`sample_end.json`**，事后可核「这次用的是哪个 oracle」。

为什么必须落快照：**否则 D1 的复现性被一次网络请求绑架** ——
换台机器重跑，Binance 只要新增一个分类或下架一个合约，闸 4 的判定就可能不同，
而你无法从产出里判断两次结果是否同源。实测三种情况：用快照 **239s**、
联网取 **451s**、断网且无快照 **4952s**（重试超时拖长）。

快照只存闸 4 读的两个字段（`contractType` / `underlyingType`，920 条 / 79 KB），
不存全量 payload。`--no-schema-note` 仍可用于忽略判据的冒烟。
`exchangeInfo` 取不到、返回 < 300 条（残包）、或快照指纹不符，都会 **exit 3**，
不静默降级 —— 降级的后果是闸 4 全部放行，代币化股票会混进成员集。

**处理**：**逐月**评测全归档 679 个合约的资格状态（§3.1），
对通过的合约按流动性排名取前 50。

**输出**：`data/03_reference/` 四个文件

| 文件 | 行数 | 粒度 | 作用 |
|---|---|---|---|
| `master.parquet` | 679 | 一合约一行 | 台账：生命周期、分类、是否入池 |
| `universe_eligibility.parquet` | 38,703 | 679 × 57 月 | **逐月四条闸的判定与理由**（审计用） |
| `universe_membership.parquet` | 2,700 | 50 × 54 月 | 最终成员集 |
| `member_changes.parquet` | 57 | 一月一行 | 进出记录与换手率 |

`universe_eligibility` 的列 —— 每个闸一路布尔 + 汇总：
```
symbol month base_asset in_pool liq bars_before last_active oi_cov oi_max_gap_h
oi_null_days obs_days active_days  g1 g2a live g2 g3a g3b g3 g4 eligible fail_reason rank
```

**两行真值 —— 同一合约、相邻两月、结论反转**
```
LUNAUSDT 2022-05  bars_before=3624  last_active=2022-05-12  g2a=T live=T g2=T  eligible=True   rank=3
LUNAUSDT 2022-06  bars_before=3912  last_active=2022-05-12  g2a=T live=F g2=F  eligible=False  fail_reason=not_trading
```
`bars_before` 从 3,624 涨到 **3,912** 却仍 **> 2,160** —— **只数 bar 数永远挡不住
死合约**。这就是闸 2② 存在的理由（§3.2）。

`universe_membership`（前 2 行）
```
     symbol   month  rank           liq  bars_before  oi_cov  oi_max_gap_h  active_days
   BTCUSDT  2022-03   1.0  4.649077e+08         2160     1.0             0           30
   ETHUSDT  2022-03   2.0  2.154402e+08         2160     1.0             0           30
```

**它代表什么**：`membership` 是**唯一的择时口径** —— Phase 2–5 的分组、Phase 3 的
事件样本、Phase 5 的回测标的都从它出发。`eligibility` 不是分析表，是**给人审计用的**。
**候选池 285 个的去向**：曾通过四条闸 **280**、曾当成员 **248**、通过闸但从未排进
前 50 的 **32**（含 `XAUTUSDT`，排名 55/64）。**`membership` 只有 54 个月**（样本前 3 个月所有合约都"历史不足"，
保留在 `eligibility` 里可查可解释）。

---

#### Step 6b · 质量与审计

**输入**：`features_1h` + `data/00_config/manifest.parquet`。
**处理**：检测用「日」，呈现用「连续缺口区间」，五类指标逐一算缺口与覆盖率。

**输出**：`data/04_qa/` 五件 + `data/REPRODUCE.md`

| 文件 | 行数 | 回答什么 |
|---|---|---|
| `missing_files.parquet` | 67 | **文件层**：归档里根本不存在的文件 |
| `gaps.parquet` | 4,881 | **记录层**：哪里断了、断多久 |
| `coverage.parquet` | 1,425 | **汇总层**：整体质量（285 × 5 指标） |
| `data_dictionary.md` | — | 逐字段字典 + 全部已知口径 |
| `checksums.sha256` | 1,442 | 产出完整性 |
| `REPRODUCE.md` | — | 六条重跑命令 |

`gaps.parquet`（前三行）
```
       symbol metric           gap_start             gap_end  hours   days  started_before_sample
1000BONKUSDT  index  2026-06-29 00:00Z  2026-06-29 23:00Z   24.0  1.000                  False
1000BONKUSDT   mark  2026-06-29 00:00Z  2026-06-29 23:00Z   24.0  1.000                  False
1000BONKUSDT     oi  2024-02-16 13:00Z  2024-02-16 22:00Z   10.0  0.417                  False
```

| 指标 | 缺口段数 | 覆盖率中位 | 说明 |
|---|---|---|---|
| `klines` | 92 | 1.0000 | 92 段 = 6,886 行补网格（`bar_missing`） |
| `oi` | 819 | 0.9997 | 最长 7,573h（`币安人生USDT`） |
| `mark` | 621 | 0.9981 | |
| `index` | 826 | 0.9977 | |
| `oi_zero` | 2,523 | 0.9997 | 值为 0，**不是缺失**；2,523 段全部只持续 1 小时 |

**它代表什么**：D1 的"干净"**不靠"没有缺失"证明，靠"缺失被完整记录"证明** ——
归档本身有空洞（67 个文件确实不存在），如实报出来比假装完整更可信。
**`funding_rate` 不做缺口检查**：只在结算时刻有值，检查它会产生约 117 万个假缺口。


---

## 3. Universe 构造

### 3.1 四条资格闸

**逐月评测。用全生命周期统计量作闸会引入前视。**

| # | 判据 | 阈值 | 单条拦下 |
|---|---|---|---|
| **1** | 非稳定币（按 `base_asset`，不按符号字面） | — | **0** |
| **2①** | 截至 M 月初已有 ≥ N 根 1h bar | `min_history_bars = 2160`（90 天） | **28,942** |
| **2②** | **最后活跃日 ≥ M 月初**（仍在交易） | `require_live_at_month_start` | **23,262** |
| **3①** | trailing 30 天 OI 覆盖率 ≥ N | `min_oi_coverage = 0.90` | **28,964** |
| **3②** | trailing 30 天最长连续缺失 ≤ N 小时 | `max_oi_gap_hours = 48` | **87** |
| **4** | 非加密资产（分类字段判据） | `contractType` + `underlyingType` | **0**（见下） |

「单条拦下」是**各闸独立计数**（同一合约月可被多条拦下），不能相加。
闸 2① 与闸 3① 几乎拦住同一批（新合约既无 90 天历史，也无 30 天 OI）。

**逐闸递进的实测漏斗**（候选池 285 × 57 = **16,245** 合约月）
```
闸1  通过  16,245
闸2① 通过   9,761
闸2  通过   9,008      ← ①② 同时满足
闸3  通过   8,938      ← 闸1·2①·2②·3①·3② 同时满足
闸4  通过   8,938      ← 分类字段在候选池内无人可拦
```
**闸 1 与闸 4 的「单条拦下 = 0」都是意料之中**：候选池在 Step 1 就已用同一套
判据剔掉了稳定币与非加密资产，所以这两条闸的作用在 **683 的全归档层面**
（闸 4 在 Step 1 拦下 **215** 个 USDT 代币化标的）。
**闸 3② 是最锋利的边界** —— 只剔 87 行，但剔掉的全是真正不可用的合约。

**闸 4 的判据只有分类字段，不设名字黑名单**

| 字段 | 加密资产（放行） | 其他（拦下） |
|---|---|---|
| `contractType` | `PERPETUAL` | `TRADIFI_PERPETUAL` · `CURRENT_QUARTER` · `NEXT_QUARTER` |
| `underlyingType` | `COIN` | `EQUITY` · `HK_EQUITY` · `KR_EQUITY` · `CN_EQUITY` · `COMMODITY` · `PREMARKET` · `FX` · `INDEX` |

**通过闸 4 ⇔ 两个字段同时命中。** 实测拦下的东西（快照口径）：
`TRADIFI_PERPETUAL` **212** 个（`EQUITY` 174 · `HK_EQUITY` 15 · `KR_EQUITY` 8 ·
`COMMODITY` 8 · `PREMARKET` 4 · `CN_EQUITY` 2 · `FX` 1），
另加 **3** 个 `PERPETUAL` 但分类是 `INDEX` 的合成指数永续
（`DEFIUSDT` `BTCDOMUSDT` `ALLUSDT`）—— 它们是合成品，不是单一资产。
理由是**代币化股票有交易时段**：闭市时它不波动，OI 与资金费率的语义会变，
1 小时 regime 会被外部时段切断。上面每个都符合这个理由。

⚠️ **故意的例外：`PAXGUSDT` / `XAUTUSDT` 放行。** Binance 把它们标成
`PERPETUAL` / `COIN`，按分类字段判据自然放行 —— 这是对的，因为它们是
**链上发行的加密原生合约**（24/7 交易、无收盘时段），结构上与加密永续无区别，
属于 note 所说的 `crypto perpetual futures`。实测 `PAXGUSDT` 是成员 **11 个月**
（2025-10 ~ 2026-08，rank 13–49），`XAUTUSDT` 排名 55/64 未入选。

⚠️ **`exchangeInfo` 只含当前挂牌合约**：29 个已下架合约查不到，走
`DELISTED_NON_CRYPTO` 兜底名单（**当前为空** —— 实测查不到的全是加密资产）。
⚠️ 分类表里有 **656** 个 USDT 本位加密合约，本地只有 **650** 个 —— 差的 6 个是
在两次取数之间下架的。**这正是判据必须落快照的原因**（§2.2 Step 6a）。

**两个易错点**：闸 2 用 bar 数而非 `onboard_date`（上市与 OI 归档不同步）；
闸 3 用 `sum_open_interest` 本身的空值率，**不得**用那 4 个衍生字段
（2022 全年大面积为空，会误杀整年）。

### 3.2 闸 2 为什么必须有第二条

**只数 bar 数不够**：合约死后 bar 数不再增长，而阈值固定，于是 `3,912 > 2,160`
**永远成立**。实测 `LUNAUSDT`（2022-05-12 停止交易）在单条件下从 2022-07 起
每月都"通过"，会一直留在成员集里贡献同一个冻结的价格。
**必须同时要求"月初仍在交易"** —— 实测把滞后从 ∞ 降到 0。

**为什么是 2,160 根**：导师 note §6 要求 regime 阈值用 rolling 60/70 分位、
§7 要求 funding 状态用 trailing 25/75/90 分位。2,160 个观测足以估 p90，720 太薄。
**代价**：样本前 3 个月所有合约都"历史不足"，成员集为空（保留在 `eligibility` 里）。

⚠️ **已知局限（已接受）**：`live` 用**全样本**的 `last_active >= 月初`，
回答的是"月初之后还交易过"而非"月初当下在交易"。实测 26 个合约月 / 6 段停摆
属此类（如 `LITUSDT` 2025-02 停摆 10 个月仍 `live=True`），其中只有 1 个进入排名
（rank 154 > 50），**对成员集零影响**。改纯 PIT 判据要引入一个任意的回溯窗口参数
并新增 12 个成员，故保留现状并声明。

### 3.3 闸 3 为什么用「连续缺失长度」

| 候选判据 | 实测 | 结论 |
|---|---|---|
| OI 覆盖率 | 中位 0.9997；`coverage.parquet` 里 < 0.90 的合约 **6 个** | ✅ 采用 |
| **最长连续缺失** | 中位 1h；**> 48h 的 62 段 / 46 个合约**，最长 7,573h | ✅ **采用** |
| `oi == 0` 比例 | 中位 0.0292%，**最高仅 0.2556%** | ❌ 不用作闸 |
| 最长冻结 | p90 = 10h，仅 1 个合约 > 12h | ❌ 不用作闸 |

**「缺 1 小时」与「缺 48 小时」对滚动窗口的破坏完全不同** —— 前者影响 1 个观测，
后者让 48 个观测全无 OI。所以判据用**连续长度**，不是比例。

**`oi == 0` 为什么不进闸**：它是**全市场发布事件**，不是单个合约的缺陷
（实测 2022-03-07 一天 105 个合约同时为 0）。用它作闸会误杀被波及的正常合约。
**记入缺失报告，不进闸。**

**闸 3② 剔除的行长什么样**
```
    ICPUSDT  2022-02  oi_cov = 0.0  oi_max_gap_h = 720
   LITUSDT  2025-05  oi_cov = 0.0  oi_max_gap_h = 720
币安人生USDT  2026-03  oi_cov = 0.0  oi_max_gap_h = 720
```

⚠️ **闸 3 的分母是"窗口内面板里存在的小时数"，不是 720** —— 死尾已裁掉，
合约死后的小时不算"缺失"。实测 `LUNAUSDT 2022-06` 报 `oi_cov = 0.966`，
而那个窗口 30 天里有 19 天根本没有数据。这些行今天全被闸 2 挡住
（`eligible = 0`），但**审计表里的数字偏乐观**，读 `eligibility` 时要留意。

### 3.4 流动性为什么不设闸

导师 note 原文是 `Exclude illiquid contracts where transaction costs dominate` ——
这是**可交易性**判断，需要盘口数据；归档只有 OHLCV，**测不到成本**。
而 note 自己提供了更好的机制：`Top 30–50 liquid`。
**按流动性排名取前 K 即是流动性筛选。**

⚠️ **`(high − low) / close` 不是交易成本的代理** —— 它是**已实现波动率**
（BTCUSDT 逐小时中位 **0.5656%**），比真实价差高两个数量级。
`coverage.parquet` 的 `median_daily_qv` 是逐小时 `quote_volume` 中位数，不设闸。

### 3.5 PIT 规则与成员口径

```
每月 M：
  1. liq(sym, 月初) = median(quote_volume) over [月初 − 30 天, 月初)   ← 严格开区间
  2. 四条资格闸（逐月重评）
  3. 通过的合约按 liq 降序排名，取前 K = 50（无缓冲带）
  4. 成员集在 M 月内【冻结】
成员集 = 每个刷新期 50 个（逐月浮动）
候选池 = 曾入过成员集的并集（285）= Step 2 的产出 = 下载范围
```

- **`liq` 逐日滚动，成员集按月冻结**，两件事必须分开。
- **流动性度量全程用月频 `klines`，不换源** —— 口径不一致会成循环定义。
- **不写下架名单。** 下架合约由闸 2② 自然淘汰；**存活期的完整历史留在样本里**
  （`LUNAUSDT` 就是靠这条留在 2022-05）。
- **`oi` 用 `OI(ts_end)`**，发布延迟 1–3 分钟，对"bar 收盘后决策"不构成前视。
- **恒等式**：一个币只有排进前 K 才可能成为样本 ⇒ 候选池 = 所有前 K 名的并集。
- **换手率**：K=50 / 30 天窗口 / 月度刷新 → **月换手均值 18.7%（中位 16.0%），
  年化约 224%**。这是加密市场流动性排名的真实性质，不是噪声 ——
  它支撑 Phase 2 用**月度**而非日度重算成员集。


---

## 4. 数据质量：不处理就会静默算错的事

### 4.1 八个静默错误

**共同点：它们都不报错，只会让数值悄悄变错。**

| # | 规则 | 不做的后果 |
|---|---|---|
| 1 | **读入后按时间戳排序** | 近期文件非单调（存在负间隔），`shift(1)` 静默算错 |
| 2 | **去重** | `2020-09`~`2021-06` 有完全一致的副本行（576 行 / 288 唯一） |
| 3 | **区分「确认 404」与「超时」** | 网络抖动被误记为缺失，永久漏文件 |
| 4 | **逐文件检测表头有无** | 按日期硬编码必然错（§4.3） |
| 5 | **URL 路径段编码，文件路径不编码** | 中文合约名让 `urllib` 抛 `UnicodeEncodeError`；编码进文件名毫无收益 |
| 6 | **缓存键必须含源名** | 四个源共用同一键，后到的源命中前一个源的缓存 |
| 7 | **OI 的 `create_time` 秒位必须截断** | 1,147 行 OI 被静默丢成 `oi_missing` |
| 8 | **"没尝试过"不得写成"未取得"** | 1,074 个假缺失污染缺失报告 |

**规则 8**：Step 2 用 `--skip-download` 重算排名、或补跑轮没覆盖到某些项时，
manifest 的 `status` 初值会被当终态写进去。实测 18,832 项**全在缓存里**
（摘要自报"新下载 0、已取得 18,832"），manifest 却有 **1,074 行 `retry_exhausted`**，
而 `build_qa.py` 把一切非 `ok` 记录当缺失 —— 于是 `missing_files.parquet` 报了
**1,141 个缺失文件（真值 67）**。这 1,074 行对应的 30 个合约（`AAVEUSDT` `ADAUSDT`
`APEUSDT` …，恰好是归档枚举的字母序前 30 个）数据**完整无缺**，各自都有
24,000–41,640 根 bar。

两道修复：① 初值只按"文件在不在"判定，`retry_exhausted` 只留给**确实尝试过且失败**
的项，摘要里"未尝试"单列一类；② `build_qa.py` 自查 —— 状态说"没取得"、文件却在
缓存里的行**不算缺失**，并打出告警。

**规则 3 的两层含义**：① `retry_exhausted` 是**待办**不是缺失，
**不得进入最终缺失报告**；② `parse_zip` 的失败**必须抛异常**，不能返回 `None` ——
原来"下载到了但读不懂"和"压缩包里没有整点行"走同一分支（打戳 `ok` + 释放缓存），
于是 813 个 (合约,月) 被永久记为完成而 `data/raw` 里一行都没有、缓存也已删除、无法追查。
现在解析失败归 `retry_exhausted`，**保留缓存、不打戳**。

**规则 5 的反向陷阱**：`quote_seg()` 只用于 **CDN 下载 URL**。S3 列表接口的
`prefix` 必须传**原始合约名** —— 它内部的 `urlencode` 会编码一次，提前编码就成了
双重编码，服务端解码后拿到字面量 `%E5%B8%81…`，永远匹配不到真实 key。
**后果不是报错，而是该合约一个文件都枚举不到、且不留任何 manifest 记录** ——
实测这样静默丢掉过 1 个候选池合约（`币安人生USDT`）的全部 mark / index / OI。

**规则 7 的细节**：`create_time` 秒位不恒为 0（实测 **4,138 行 / 64 个合约**，
如 `TLMUSDT 2022-05-09 11:00:59`），其中 **1,147 行是该合约该小时唯一的快照**。
不截断就匹配不上任何 `ts_end`，被静默记成 `oi_missing=True`，并把该合约的 OI
序列人为拉长。**修法是 `floor("h")` 之后再合并。**

### 4.2 下架合约：`klines` 不停，`funding` / `mark` / `index` 会停

**合约下架后，`klines` 归档会一直写「整月零成交的空行」到样本末端；
而 `funding` / `mark` / `index` 在下架时就断了。**

| 合约 | `klines` 末月 | 末月成交额 | `funding` 末月 |
|---|---|---|---|
| `AGIXUSDT` | 2026-08 | **0** | 2025-06 |
| `FTMUSDT` | 2026-08 | **0** | 2025-06 |
| `MATICUSDT` | 2024-09 | 3.8 亿（正常） | **2026-08** ← 方向相反 |

规模：**446 个 (合约, 月) 组合整月零成交，涉及 38 个合约**。

**三个直接后果**
1. **判活看 trailing 30 天的 `quote_volume`**，不看有没有 bar，也不看
   `exchangeInfo` 的 `status`。死合约的退出靠闸 2②。
2. **`funding` 表允许超出 `klines` 网格**（实测 7,911 行 / 0.64%，其中 6,916 行是
   下架合约的尾部结算）。它是事件表，**不按网格裁**。
3. **`index` 的覆盖率缺口主要来自这里** —— 死尾的 321,737 行里 **84.9%** 的
   `index` 空值落在其中；`mark` 不受影响（只有 3.3%）。这也是 `features_1h`
   要**裁死尾**的原因。

### 4.3 表头有无：必须逐文件检测

| 源 | 2021-12 | 2022-03 | 2022-09 起 |
|---|---|---|---|
| `klines` | 无表头 | 有 | 有 |
| `markPriceKlines` / `indexPriceKlines` | 无 | **无** | 有 |
| `metrics` / `fundingRate` | **始终有** | | |

```python
first = raw.split("\n", 1)[0].split(",", 1)[0].strip()
has_header = not first.lstrip("-").replace(".", "").isdigit()   # 不可按日期硬编码
```

### 4.4 缺失报告的口径

**检测用「日」，呈现用「连续缺口区间」。** 纯月粒度太粗（`覆盖率 29/30` 看不出
缺的是哪天）；纯日粒度表爆炸（约 200 万行，99% 是「正常」）。

`gaps.parquet` 按 `(symbol, metric, gap_start)` 排序 —— 按长度降序会把同一合约的
缺口打散，看不出"这个合约在哪段时间整体劣化"。`started_before_sample` 列区分
「从样本起点就缺」与「中途坏了」。

| category | 算真缺失？ |
|---|---|
| `confirmed_404` | ✅ 是（实测 67 条，全部是 `metrics`） |
| `retry_exhausted` | ❌ **不是** —— 是待办 |
| `retry_exhausted` 但文件在缓存里 | ❌ **不算** —— `status` 写坏了，见 §4.1 规则 8 |
| `partial_rows`（行数 < 288）· `field_empty` · `zero_volume` | ⚠️ 记录 |


### 4.5 其它已知脏点

| 位置 | 问题 | 处理 |
|---|---|---|
| 个别日期 | 缺失，或 287 行而非 288 | 记入缺失报告 |
| **2022 全年** | 4 个大户多空比字段大面积空 | **不存这些列** |
| 新币首日 | 从半天开始 | 按可用天数判定，非按上币日 |
| 零成交额月 | 文件存在但 `quote_volume = 0` | 该合约该月不该进成员集 |
| `oi = 0` | 2,523 行 / 48 天 | 全市场事件，记入缺失报告 |
| 冻结的 `oi` | 仅 1 个合约 > 12h | 记入缺失报告 |

---

## 5. 数据契约与验收

### 5.1 类型与 `validate()`

```
"string"    →  pandas "string"        "float64"   →  pandas float64
"timestamp" →  datetime64[ns, UTC]    "bool"      →  pandas bool
```
**整数一律用 float64**（精确到 2^53；`int8/…` 不支持 NaN）。
**全部数据列允许 null**，唯一例外：**标识列强制非空** ——
主键为空即损坏（`NaT` 在 join 时静默匹配不上，那些行会无声消失）。

```python
from lib.schema import validate, SchemaViolation
validate(df, "features_1h")      # 失败抛 SchemaViolation，一次报全部问题
```

九条结构检查：列名与**顺序** · dtype · 标识列非空 · 主键**无重复** · 主键**已排序** ·
**无整列为空** · 标识列落在整小时 · `ts_end − ts == 1h` · 标识列 tz-aware UTC。

**不做值域与跨列一致性检查**（`oi_value / oi / close ≈ 1` 等）——
它们是统计判断、阈值需标定。上面九条已覆盖会导致数值异常的**根因**。

⚠️ 「无整列为空」**只在一个 chunk 含多个合约时才判** ——
单合约某月本来就可能整列无数据（实测 `TLMUSDT` 2022-07 归档里一根 OI 都没有），
否则 `--subset <单合约>` 的冒烟必然误报。

**时间戳口径**
```
open_time  = H                 # 官方 "Kline start time"  → 我们的 ts
close_time = H + 1h − 1ms      # 毫秒部分恒为 .999
区间终点    = H + 1h            # 数据里没有，自己算 = ts_end
```
毫秒 int（`metrics.create_time` 例外，是字符串）。全程 **UTC**。
**OI 快照网格**：每日文件 **288 行 + 1 行表头**，100% 落在 5 分钟网格，
整点快照必然存在，`sum_open_interest` 是**时点存量值**。

### 5.2 自测与产出完整性

```bash
python config.py            # 8 项：validate_sample_end 行为 + Config frozen
python -m lib.schema        # 65 项：round-trip / validate 放行 / validate 捕获 / 结构自检

# 重算 1,442 个产出文件的 SHA256；0 个不一致则退出码 0
python phase1/build_qa.py --out-root data --sample-end 2026-08-31 --verify
```
**实测：`核验 1,442 个文件：全部一致`，退出码 0。**

**校验和是本流程最后一个写盘动作** —— 它此前写入的每一个文件
（含 `00_config/sample_end.json` 的运行元信息）都被纳入哈希。
因此**重跑 Step 3–6a 之后必须重跑 Step 6b**，否则校验和失效。

### 5.3 端到端复现

```bash
# 见 data/REPRODUCE.md，六条命令
python phase1/build_candidate_pool.py --out-root data --sample-end 2026-08-31  # Step 0–2
python phase1/fetch_market_data.py    --out-root data --sample-end 2026-08-31  # Step 3
python phase1/build_layer2.py   --out-root data --sample-end 2026-08-31
python phase1/build_features.py --out-root data --sample-end 2026-08-31
python phase1/build_universe.py --out-root data --sample-end 2026-08-31
python phase1/build_qa.py       --out-root data --sample-end 2026-08-31
```

**`--out-root` 六个脚本全部必填，不是可选项** —— 环境变量不跨 shell 保留，
早期用环境变量重定向（`P11_DATA_ROOT` / `P3_DATA_ROOT`，脚本改名前的旧前缀），
导致冒烟结果三次污染正式目录。显式参数无法"忘记设置"。
Step 0–2 与 Step 3 必须传**同一个** `--out-root`，否则 Step 3 找不到候选池和 klines 缓存。

**全项目实际存在的 CLI 参数共 20 个**（`python phase1/<脚本>.py --help` 可核对）：

| 类别 | 参数 | 出现处 | 默认 |
|---|---|---|---|
| 样本窗口 | `--sample-end` | **六个脚本全部，全部必填** | 无 |
| 路径 | `--out-root` | **六个脚本全部，全部必填** | 无 |
| 路径 | `--raw-root` `--l2-root` `--fe-root` `--pool` `--manifest` | 见下表 | 项目内默认 |
| 冒烟 | `--subset` | Step 0–2/3/4/5/6a | 无 |
| 冒烟 | `--batch` | Step 4/5 | 30 |
| 断点 | `--skip-download` | 仅 Step 0–2 | 关 |
| 断点 | `--keep-cache` `--list-only` `--jobs` | 仅 Step 3 | 关 / 关 / 32 |
| 断点 | `--keep-existing` | 仅 Step 4 | 关 |
| 网络 | `--refresh-exchange-info` `--exchange-info` | 仅 Step 6a | 快照 |
| 校验 | `--no-validate` | Step 4/5 | 关（开着才校验） |
| 校验 | `--no-schema-note` | 仅 Step 6a | 关 |
| 校验 | `--verify` | 仅 Step 6b | 关 |

逐脚本对照（`--help` 的权威输出）：

| 脚本 | 参数 |
|---|---|
| `build_candidate_pool.py` | `--out-root` `--sample-end` `--skip-download` `--subset` |
| `fetch_market_data.py` | `--out-root` `--sample-end` `--subset` `--list-only` `--keep-cache` `--jobs` |
| `build_layer2.py` | `--out-root` `--raw-root` `--pool` `--sample-end` `--subset` `--keep-existing` `--batch` `--no-validate` |
| `build_features.py` | `--out-root` `--l2-root` `--pool` `--sample-end` `--subset` `--batch` `--no-validate` |
| `build_universe.py` | `--out-root` `--fe-root` `--pool` `--manifest` `--sample-end` `--subset` `--no-schema-note` `--refresh-exchange-info` `--exchange-info` |
| `build_qa.py` | `--out-root` `--fe-root` `--manifest` `--sample-end` `--verify` |

**已删除的过时机制**（早期设计提过、现已不存在，照旧文档用会直接报错）：

| 已删 | 原形态 | 现在用什么 |
|---|---|---|
| `--no-refresh` | `config.py` 提到的 CLI 参数 | 从未实现；刷新走 `--refresh-exchange-info` |
| `--symbols` | 同上 | 从未实现；局部运行走 `--subset` |
| `P11_DATA_ROOT` | Step 0–2 的环境变量 | `--out-root`（必填） |
| `P3_DATA_ROOT` | Step 3 的环境变量 | `--out-root`（必填） |
| `--refresh` | `build_universe.py` 注释里的写法 | 那是 **Python 函数参数名**，CLI 是 `--refresh-exchange-info` |
| `parquet_compression` | `config.py` 字段 | 从未被读取；七个写盘点各自硬编码 `zstd` |
| `event_lookbacks` | `config.py` 字段 | Phase 1 不用；规划值 `(1,4,8,24)` 记在 §2.2 Step 5 |

**`config.py` 里不含非设计参数**：能进 `config_snapshot` 的每个字段都必须被至少
一处代码读取。方向是**删掉死字段**，而不是为了凑快照去用它们。

**下载缓存有两个，性质不同**：

| 缓存 | 由谁产生 | 大小（实测） | 会不会自动清 |
|---|---|---|---|
| `data/raw/_cache/` | Step 3 | 跑完 **0 字节** | ✅ `stamp()` 里 `drop_cache()`，落盘即释放 |
| `data/00_config/_cache/klines/` | Step 0–2 | **527.7 MB / 18,874 zip** | ❌ **不会**，没有释放逻辑 |

第二个（名字原为 `_p11_cache`，`p11` 是脚本改名前的旧前缀，已改名为 `_cache`，
与 Step 3 那个同名同义）是 **Step 2 为算流动性而下的月频 klines zip**：

- **只被 `build_candidate_pool.py` 读写**，其余五个步骤都不碰
- **删掉不影响任何产出**：候选池 285 个合约全在 `data/raw/klines/` 里；
  它也不进 `checksums.sha256`（`checksum_targets()` 明确排除）
- **但删了要付代价**：下次重跑 Step 0–2 会重下这 18,832 个文件（约 5 分钟，需 VPN）
- 里面有 **394 个落选合约**的 klines（679 − 285），改 `K` / 延长窗口重算时还要用

**建议留着**：它不参与校验和、不影响交付，唯一作用是省重跑时间。

**Step 4 与 Step 5 是全量重建**（先清旧产出）。`--subset` 加 `--keep-existing`
才是"只处理部分合约"的冒烟模式，此时收尾的交叉校验只对该批次有意义。

**Step 6a 的判据来自快照**，所以离线可复现。要更新判据（例如到了新月份、
Binance 新增了合约分类）才需要联网：
```bash
python phase1/build_universe.py --out-root data --sample-end 2026-08-31 \
       --refresh-exchange-info          # 联网重取并覆盖快照
```

---

## 6. 时间优化

**全流程本地计算约 26 分钟**（Step 4 = 847s，Step 5 = 357s，Step 6a = 239s，Step 6b = 30s）。
四个优化点，各自的收益都是实测的：

### 6.1 一遍过：下载即解压（Step 3，最大的一个）

```
✓ 一遍过   下载 → 就地解压 → 攒批 → 落盘 → 释放缓存 → 打进度戳
                                                    ↑ 断点续传靠它
```

**禁止「先全下到缓存、再统一解压」的两阶段写法**

| | 两阶段 | 一遍过 |
|---|---|---|
| 磁盘读 | 2 遍 | **1 遍** |
| 中断损失 | 从头重来 | **< 1 分钟** |
| 缓存释放 | 需手动删 | **随进度自动，跑完为空** |

**打戳与删缓存必须走同一条代码路径**（都放在 `stamp()` 里）。
若某分支打了戳却忘了删缓存，缓存永久残留；反之则重复下载。

### 6.2 按合约预分组，不做逐合约全表扫描

两个地方踩过同一个坑，修法相同：

| 位置 | 反面写法 | 实测 | 改为 | 实测 |
|---|---|---|---|---|
| Step 4 读 `metrics` | 每个合约重读 6 个年度文件 | **289s** | 读一次 + 按合约预分组 | **< 2s** |
| Step 6a 建 `master` | 679 次全表布尔过滤 | **310s** | 一次 `groupby(symbol)` | **48s** |

**判据：只要出现"对每个合约扫一遍全表"，就一定会慢一个数量级。**

### 6.3 单遍读盘 + 原子写

Step 5/6a 都是"读一次全部 chunk → 内存里聚合 → 按合约切片",不在循环里反复
`read_parquet`。每个 chunk 先写 `.part`（**名字带 PID**）再 `os.replace`。

### 6.4 下载参数

| 参数 | 值 | 依据 |
|---|---|---|
| 并发 | **32** | 实测 16 → 32 吞吐已饱和 |
| 读取超时 | **45 s** | 实测极端长尾 45.8 s |
| 重试次数 | **3** | 只重试网络类失败 |
| 退避 | `2^attempt` 秒 + 0–1 s 抖动 | 抖动必需 —— 并发同时失败会成尖峰 |

**跑完对未取得项再补一轮**，把问题在同一次运行内解决。

**VPN 的代价**：CDN 吞吐 **140 → 89 文件/秒（慢 36%）**；并发 32 时约 13% 请求瞬时失败。

⚠️ **枚举结果曾经漏过合约** —— 实测一次 893、一次 1,057，差 164 个。合约数只增
不减，所以前者是不完整枚举。（2026-10-04 连跑 3 次均为 1,057，当前稳定。）
**所以 Step 0 的产出必须落盘**（`archive_contracts.csv`），
且枚举结果要与「该合约是否已有数据」交叉验证，要能对单个合约补抓。

---

## 7. 增量更新

### 7.1 数据源优先级

```
对每个 (symbol, 时间戳):
    该月的【月频文件】在 manifest 中 status = ok   →  用月频
    否则                                          →  用日频补
    两者都没有                                     →  该时间戳不存在
```
因**月频 = 日频拼接（逐值完全相同）**，两者可自由混用，**增量不必等月份结束**。

**发布节奏（`Last-Modified` 实测）**：日频 `metrics` 每天 06:39 GMT；
日频 klines / mark / index 每天 08:00–08:34 GMT；月频 `fundingRate` 次月 1 日 08:24 GMT；
月频 klines / mark / index 次月 2 日 09:00–12:00 GMT。
→ **刷新的合适时点：每天 UTC 09:00 之后。**

### 7.2 流程

```
【A】更新合约清单（需 VPN）→【B】定该有哪些文件 →【C】与 manifest 对账
【D】下载缺失的 →【E】重建第 2 层 →【F】重建 features_1h →【G】重建 universe → 重跑 Step 6b
```
**`sample_end` 只决定裁剪边界，不决定数据来源。**

### 7.3 `manifest` 表结构

`data/00_config/manifest.parquet` —— 逐文件一行，断点续传的唯一依据。

| 列 | 含义 |
|---|---|
| `source` / `symbol` / `period` / `granularity` | 定位 |
| `remote_path` / `filename` | **重下时唯一依据** |
| `status` | `ok` / `confirmed_404` / `retry_exhausted` |
| `bytes` / `downloaded_at` | 大小与下载时刻 |
| `raw_written_at` | **已并入 `raw/` 的进度戳** |

**manifest 中途就会落盘**（每 2,000 个文件一次），不是跑完才写 ——
否则 SIGKILL / 断电会丢掉全部进度戳，而缓存早已删除，下次要把几十万个文件重下。

### 7.4 四个边界

**① `confirmed_404` 需要 TTL 重探 —— 尚未实现，是已知缺口。**
月频文件在次月 1–2 日才发布，且并非每月都齐，永久缓存 404 会**永久漏掉**该文件。
现状：67 条 `confirmed_404` 里有 **32 条带 `raw_written_at` 戳**，而续传逻辑把"有戳"
当已完成，于是这 32 条**永久跳过**。**换月增量前要补 TTL。**

**② 增量 `features_1h` 需要 upsert —— 当前是全量重建，是已知缺口。**
正确做法是"读现有 chunk → 合并 → 按主键去重 → 原子写回"；现状每次重建 57 个
chunk（约 357 秒）。**正确性没问题，代价是时间。**

**③ chunk 按「月」切，完整月的 chunk 写完永不改变。**

| 状态 | 哪些 | 行为 | 不变量 |
|---|---|---|---|
| **frozen** | 除最后 1 个外全部 | 写完不改 | 行数按 `(chunk, symbol)` 固定 |
| **hot** | `sample_end` 所在月 | 每次追加 | 行数单调增 |

⚠️ 新上市合约首月不满整月。**行数不变量按 `(chunk, symbol)` 判定，不按 chunk 总行数。**

**④ 第 2 层的构建顺序是硬性要求**：增量时 `layer2_built_at` 是**单一时间戳**，
必须**最后写，且失败时不写**。否则 `mark` 成功而 `index` 失败时，该文件会被标记为
「已建」，**`index` 的数据永久丢失且不报错**。

---

## 8. 关键决策与预设问题

### 8.1 为什么样本从 `2021-12-01` 开始

**由 OI 归档的断崖唯一定死，不是权衡结果**

```
各起点的 OI 覆盖率          OI 首月分布（当前产出可核）
  2020-01    0 / 285         2021-12   103 个   ← 断崖
  2021-09    1 / 285         2022-01     1 个
  2021-12  103 / 285         2022-02     3 个
  2022-06  114 / 285         2022-03     3 个
```
2021-12 那 103 个的明细：**100 个恰好始于 `2021-12-01`**，3 个在 12 月下旬
（`ICPUSDT` `PEOPLEUSDT` `ROSEUSDT`）。另有 1 个池内合约完全没有 OI 数据。

其余四源（`klines` / `mark` / `index` / `funding`）都有 102 个合约能回溯到 2020 ——
**唯一卡住的是 OI**。往前推可多得约 100 万根 bar，但那段 OI 覆盖率仅 0.4%，
而本项目研究的是 **Price + Open Interest**。

⚠️ **左列的断崖数字来自归档侧侦察探测，不在当前产出里。** Step 3 按样本窗口
裁剪下载范围，所以 `raw/metrics/` 最早只有 2021-12 —— 左列无法从现有产出复核，
右列可以。

**BTC 的 2020-01 ~ 2021-11 历史不做附录**（已决策）：五个源齐全、技术上能做出
**23 个月**单币 1h 面板，但对 285 币的面板研究增益有限，代价是多维护一条
窗口不同的数据路径。**不引入这个复杂度。**

### 8.2 关键的取舍表

| 决策 | 选择 | 代价 / 被放弃的 |
|---|---|---|
| 初始样本窗口 | `2021-12-01` | 放弃约 100 万根 bar（OI 覆盖 0.4%） |
| 月度成员数 | 前 50 | 第 1 名与第 50 名流动性差 **205 倍**（中位） |
| 成员集刷新 | 月度冻结 | 月换手 18.7%，滞后一个月 |
| 历史长度 | 2,160 bar | 样本前 3 个月无成员 |
| OI 质量 | 覆盖率 + 连续长度双闸 | 剔掉 46 个合约 |
| 流动性 | **只靠排名，不设闸** | 无法度量真实交易成本 |
| 数据分层 | 源表与面板分离 | 多一层磁盘（546.8 MB） |
| 派生量 | 全部推到 Phase 2 | Phase 2 每次改参数要重算，数据层不用重跑 |
| 死尾 | 裁掉 | 与 `funding` 的越界行口径不同，需在字典里说明 |
| `live` 判据 | 全样本 `last_active` | 非纯 PIT（§3.2 已声明，对成员集零影响） |

### 8.3 预设问题

**Q：候选池 285 个，为什么成员只有 2,700 行（50 × 54）？**
候选池是"曾进过前 50 的并集"，是**下界**。每月只有 50 个在册，样本前 3 个月
因历史不足为空。285 个里曾通过全部闸的 280 个，真正当过成员的 248 个。

**Q：怎么证明没有前视？**
① `liq` 用严格开区间 `[月初−30天, 月初)`；② 四条闸逐月重评；③ `oi` 用
`OI(ts_end)`，发布延迟 1–3 分钟，bar 收盘后可得；④ 成员集按月冻结。
**一处例外已在 §3.2 声明**：`live` 用全样本 `last_active`（对成员集零影响）。

**Q：`funding_rate` 83.4% 是 null，是不是只该在 `00/08/16` 有值？**
不是。它是**结算事件**，只在结算小时有值，非空占 16.65%。
更要紧的是**结算周期不恒定**：实测 142 个合约是 4h（`00/04/08/12/16/20`）、
142 个是 8h、1 个是 1h。**硬编码 `00/08/16` 会漏掉一半合约的一半结算** ——
必须读 `funding_interval_hours`。

**Q：`oi == 0` 怎么处理？**
记入缺失报告（`metric = "oi_zero"`，逐小时），**不进闸** —— 它是全市场发布事件
（实测 2022-03-07 一天 105 个合约同时为 0），用作闸会误杀被波及的正常合约。
发生率中位 0.029%，最高 0.256%。

**Q：为什么要分第 2 层和 `features_1h` 两层？**
**口径可分别审计**：第 2 层回答"源里到底有什么"（用 `NaN`），`features_1h`
回答"分析时看到什么"（密集、对齐、带缺失标记）。合并成一层后，
"这个 NaN 是源里没有，还是我们对齐错了"就无法回答。

**Q：`(high − low) / close` 能不能当交易成本代理？**
不能。它是**已实现波动率**（BTCUSDT 逐小时中位 0.5656%），比真实价差高两个
数量级。`coverage.parquet` 的 `median_daily_qv` 是逐小时成交额中位数，不设闸。

**Q：整个流程要跑多久？增量呢？**
首次约 2.5–3 小时（Step 2 约 8 分钟 + Step 3 约 111 分钟 + Step 4–6b 约 26 分钟）；
增量只加一个月约 **10 分钟**。**换月增量前要先补 §7.4 的两个缺口（TTL 重探、upsert）。**

必须读 `funding_interval_hours`。
