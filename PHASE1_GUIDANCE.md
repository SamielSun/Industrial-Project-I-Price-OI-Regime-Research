# Phase 1 Guidance

> 项目：THEO / FTEC5910 — **Price + Open Interest Regime Signal**
> 更新：2026-09-29
> **本文件是 Phase 1 编码的唯一依据。未在此定义的参数，编码时不得自创。**
> 产出：**D1** — 干净、可复现、无前视的 Binance 永续面板数据集

---

## 1. 目标与进度

**D1 = ① 干净面板（Parquet）② 缺失数据报告 ③ 数据字典 ④ 校验和 + 复现命令**

**非目标**：制度标注（Phase 2）· 事件研究（Phase 3）· 回测（Phase 5）

### 1.1 进度表

**命名约定**：`Phase 1–5` = 项目阶段；`Step 0–6` = §4 的数据流；**脚本按作用命名，不用编号**。

| Step | 脚本 | 产出 | 状态 |
|---|---|---|---|
| — | `config.py` · `lib/schema.py` | 设计参数 + 数据契约 | ✅ 已完成 |
| 0–2 | `phase1_data/build_candidate_pool.py` | **候选池名单**（285 个合约） | ✅ 已完成 |
| 3 | `phase1_data/fetch_market_data.py` | **raw 数据**（1.10 GB / 1,145 个 parquet） | ✅ 已完成 |
| 4 | `phase1_data/build_layer2.py` | 第 2 层 4 张规范化表 | ⬜ 待写 |
| 5 | `phase1_data/build_features.py` | `features_1h`（19 列密集网格） | ⬜ 待写 |
| 6 | `phase1_data/build_universe.py` | universe 表 + D1 全部产出物 | ⬜ 待写 |

⚠️ Step 4–6 的脚本名可在那一步调整。

**Step 2 实测：18,874 个文件 / 76 秒（缓存命中）/ 0 个未取得**（候选池 296 → 297 → 288 → **285**）。

**Step 3 实测：345,472 个文件 / 两轮共 111 分钟 / 0 个 `retry_exhausted`。**
（首轮旧版写法 109 分钟；改进为"一遍过"后，增量只需 341 秒。见 §5.3）

---

## 2. 环境约束

| 项 | 约束 |
|---|---|
| **下载方式** | **只能用 Python**（`urllib`）。本机 Windows schannel 故障，`curl` 与 `Invoke-WebRequest` **一律失败** |
| 数据源 | `data.binance.vision`（文件直取，可达） |
| REST API | `fapi.binance.com` **不可达**，本项目**不需要** |
| 冻结的 `exchangeInfo` | `www.binance.com/fapi/v1/exchangeInfo`（Python 可达）—— 只用来取 `baseAsset`/`quoteAsset` 等元信息 |
| 依赖 | 标准库 + `pandas` / `pyarrow`（实为 2.3.3 / 23.0.1） |

**两条必须遵守的工程规则**：

**① 构造 URL 时路径段必须做百分号编码。**
归档里有中文名合约（`币安人生USDT`、`我踏马来了USDT`、`牛来USDT`、`龙虾USDT`）。
未编码的非 ASCII 字符会让 `urllib` 抛 `UnicodeEncodeError`：

```python
def quote_seg(seg: str) -> str:
    """非 ASCII 才编码 —— 普通合约名保持可读，与既有 manifest 一致。"""
    try:
        seg.encode("ascii")
    except UnicodeEncodeError:
        return urllib.parse.quote(seg, safe="")
    return seg
```

**② 只重试网络类失败。**
`socket`/`URLError`/超时可重试；`UnicodeEncodeError`、`ValueError` 是编程错误，
重试只会**把 bug 伪装成网络抖动**。`except Exception` 必须在它之前拦下这类异常。

这两条曾合起来造成一次静默数据丢失：4 个中文名合约全部失败、被记为
`retry_exhausted`，其中 19 个文件**真实存在**却被丢掉，候选池因此少了 1 个合约。

**探测资源是否存在时，必须带对照组** —— 否则无法区分「资源不存在」与「路径猜错」。

---

## 3. 数据源

### 3.1 枚举归档（唯一可靠的合约清单来源）

```
https://s3-ap-northeast-1.amazonaws.com/data.binance.vision
    ?list-type=2&prefix=<前缀>&delimiter=/&max-keys=1000
    [&continuation-token=<上一页的 NextContinuationToken>]
```

- 返回 XML，用 `IsTruncated` / `NextContinuationToken` 翻页
- **用途**：枚举归档里**存在过**的全部合约

⚠️ **不要用 `exchangeInfo` 当合约清单**：它只保留当前挂牌 + 近期退市（约 130 天），
更早下架的会被移除。实测 `exchangeInfo` 有 658 个 USDT 永续，**归档有 893 个**
—— 差的那 241 个正包含 `LUNAUSDT` 等样本期内最重要的事件标的。
用 `exchangeInfo` 会制造**幸存者偏差**。

### 3.2 六个源

| 源 | 日频 | 月频 | 表头 |
|---|---|---|---|
| `klines` | ✅ | ✅ | `open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore` |
| `markPriceKlines` | ✅ | ✅ | 同上（12 列） |
| `indexPriceKlines` | ✅ | ✅ | 同上（12 列） |
| `premiumIndexKlines` | ✅ | ✅ | 同上。**不用**（见 §3.5） |
| `metrics`（OI） | ✅ | ❌ **无** | `create_time, symbol, sum_open_interest, sum_open_interest_value, count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio` |
| `fundingRate` | ❌ **无** | ✅ | `calc_time, funding_interval_hours, last_funding_rate` |

**路径模板**

```
{CDN}/data/futures/um/{monthly|daily}/{source}/{SYM}/{interval}/{SYM}-{interval}-{period}.zip
                                     ↑ 只有 4 个源有这一层         ↑ 只有这些源有
```

| 源 | 有 `{interval}/` 层 | 完整路径（BTCUSDT，已实测） |
|---|---|---|
| `klines` | ✅ | `monthly/klines/BTCUSDT/1h/BTCUSDT-1h-2023-03.zip` |
| `markPriceKlines` | ✅ | `monthly/markPriceKlines/BTCUSDT/1h/BTCUSDT-1h-2023-03.zip` |
| `indexPriceKlines` | ✅ | `monthly/indexPriceKlines/BTCUSDT/1h/BTCUSDT-1h-2023-03.zip` |
| `premiumIndexKlines` | ✅ | 同形 |
| **`metrics`** | ❌ | `daily/metrics/BTCUSDT/BTCUSDT-metrics-2023-03-01.zip` |
| **`fundingRate`** | ❌ | `monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2023-03.zip` |

⚠️ 有该层的 4 个源**必须有** —— 漏掉就 404（这一步极易漏）。
⚠️ `fundingRate` 的文件名里是**源名本身**，不是空、也不是 interval：
`BTCUSDT-fundingRate-2023-03.zip`。写成 `BTCUSDT-2023-03.zip` 会**全部 404**
—— 实测这样丢掉过 10,157 个文件。
⚠️ `metrics` 同理：`BTCUSDT-metrics-2023-03-01.zip`。

**归档实际存在的源**（S3 目录实测）：

| 粒度 | 源 |
|---|---|
| `monthly` | `klines` · `markPriceKlines` · `indexPriceKlines` · `premiumIndexKlines` · **`fundingRate`** · `aggTrades` · `trades` · `bookTicker` |
| `daily` | `klines` · `markPriceKlines` · `indexPriceKlines` · `premiumIndexKlines` · **`metrics`** · `aggTrades` · `trades` · `bookTicker` · `bookDepth` |

- `monthly/metrics` **不存在**；`daily/fundingRate` **不存在**
- `liquidationSnapshot` 在 `um` 下**完全不存在**；`bookTicker` 只覆盖约 316 个合约

**「月频 / 日频」指文件的打包粒度，不是 bar 周期** —— 两者装的都是 1h bar。
真正只有日频数据的只有 `metrics`。

### 3.3 表头有无 → 必须逐文件检测

| 源 | `2021-12` | `2022-03` | `2022-09` 起 |
|---|---|---|---|
| `klines` | 无表头 | 有 | 有 |
| `markPriceKlines` / `indexPriceKlines` / `premiumIndexKlines` | 无 | **无** | 有 |
| `metrics` / `fundingRate` | **始终有** | | |

```python
# 唯一正确的方式。不可按日期硬编码
first = raw.split("\n", 1)[0].split(",", 1)[0].strip()
has_header = not first.lstrip("-").replace(".", "").isdigit()
```

### 3.4 时间戳

```
open_time  = H                 # 官方 "Kline start time"  → 我们的 ts
close_time = H + 1h - 1ms      # 官方 "Kline close time"，毫秒部分恒为 .999
区间终点    = H + 1h            # 数据里没有，需自己算 = ts_end
bar1.open_time - bar0.close_time = 1 ms   # 相邻 bar 无缝
```

时间戳为**毫秒 int**（`metrics.create_time` 例外，是字符串）。全程 **UTC**。

### 3.5 OI 快照网格

实测（BTC / ETH / SOL / DOGE，跨 2021-12 / 2022-03 / 2023-06 / 2024-05 / 2026-06）**全部一致**：

- 每日文件 **288 行数据 + 1 行表头**
- 100% 落在 5 分钟网格（`00:00, 00:05, …, 23:55`，末行恒为 `23:55:00`）
- 整点快照必然存在
- `sum_open_interest` 是**时点存量值**（非区间累计量）
- 发布延迟 **1–3 分钟** → 对「bar 收盘后决策」的设计**不构成前视**

### 3.6 样本窗口与硬约束

| 项 | 事实 |
|---|---|
| **OI 归档起点** | **BTC = `2020-09-01`（连续 2220 天）；其余 284 个合约全部 = `2021-12-01`** |
| **主样本** | **`2021-12-01` 起**。BTC 的额外历史**不做附录、不吃进任何产出**（见下方说明） |
| `mark` / `index` / `klines` 时间戳 | **不完全重合** —— 实测双向不重合（`ICXUSDT` 有 96 小时只有 klines）。按 klines 左连接，缺处 `NaN` |
| **月频 = 日频拼接** | **逐值完全相同**（抽 BTC 2023-03 的 4 个日文件，96 行逐字节相等） |
| **月频 `fundingRate` 起点** | **`2020-01`** —— **早于** OI 起点，窗口内全程可用 |
| 月频 `klines` 起点 | `2020-01`（BTC 80 个月） |
| 月频文件**并非每月都齐** | 存在个别月份缺失 |
| 文件**不可变** | 同文件两次下载 sha256 一致 |
| `.CHECKSUM` | 各源均可得 |
| `premiumIndexKlines` | **不用**：12 列中 8 列为 0 或常量 |
| `fundingRate` 的 `calc_time` | **毫秒位不恒为 0**（实测 2240/5205 非零）→ 只能按**整秒截断** |
| `bookTicker` / `liquidationSnapshot` | **USDT 本位不存在**。去杠杆确认改用 **OI 单小时跌幅** + **已实现波动率** |

**`sample_start = 2021-12-01` 的由来（实测，非权衡）：**

OI 归档的首月分布是一个**断崖**：

```
2020-09      1 个合约   ← 只有 BTCUSDT
2021-11      0 个合约
─────────── 断崖 ───────────
2021-12    101 个合约   ← 批量开始
```

| 起点 | 有 OI 的合约 |
|---|---|
| 2020-01 | **0 / 285** |
| 2021-09 | **1 / 285** |
| **2021-12** | **102 / 285** |
| 2022-06 | 114 / 285 |

其余四源（`klines`/`mark`/`index`/`funding`）都有 101 个合约能回溯到 2020 ——
**唯一卡住的是 OI**。往前推可多得约 100 万根 bar，但那些 bar 的 **OI 覆盖率为 0.4%**。
本项目研究的是 **Price + Open Interest**，没有 OI 的历史段对核心信号无用，
只会制造"一个字段在 2020–2021 全空"的两段式面板。**所以起点由 OI 断崖唯一定死。**

**BTC 的 2020-01..2021-11 历史不做附录**（已决策）。事实核清：BTC 在那 23 个月里
五个源齐全（含 OI 从 `2020-09-01` 起连续无缺），技术上能做出 15 个月的完整 1h 面板。
但它是**单币样本**，对 285 个合约的面板研究增益有限，而代价是 Step 4/5 要多维护
一条与主面板窗口不同的数据路径。**不引入这个复杂度。**

### 3.7 发布节奏（`Last-Modified` 实测）

| 数据 | 发布时点 |
|---|---|
| 日频 `metrics` | 每天 **06:39 GMT** |
| 日频 klines / mark / index | 每天 **08:00–08:34 GMT** |
| 月频 `fundingRate` | 次月 **1 日 08:24 GMT** |
| 月频 klines / mark / index | 次月 **2 日 09:00–12:00 GMT** |

**增量刷新的合适时点：每天 UTC 09:00 之后。**

---

## 4. 流水线

```
Step 0  【枚举归档】S3 列表接口 → 全部存在过的合约
           ↓
Step 1  【硬过滤】剔非 USDT 本位、名称怪象、稳定币、代币化股票/商品
        实测 893 → 858
           ↓
Step 2  【算候选池】拉月频 klines → 过草稿闸 → 逐月算中位报价成交额排名
        → 取各月前 K 的并集 = 候选池
        实测 831 → 18,874 个文件 → **候选池 285 个**
           ↓
Step 3  【精筛下载】只对候选池合约：日频 metrics(OI) + 月频 funding / mark / index
           ↓
Step 4  【第 2 层】4 张规范化表（§7.2）
           ↓
Step 5  【features_1h】19 列密集网格（§7.3）
           ↓
Step 6  【universe】资格判定 + PIT 成员（§6）+ D1 产出物
```

**为什么 Step 2 只下 `klines`**：它的产出**只是一个排名**，排名只用 `quote_volume`。
mark/index/funding 归 Step 3（只对候选池合约）。**premium 永不下载。**

**Step 2 实测：首轮 463 秒（VPN）／缓存命中 76 秒。18,874 个文件，0 个未取得。**
`19,431 / 831 ≈ 23.4 个月/合约`（窗口有 57 个月）—— 多数合约上市较晚，没有全程数据。

---

## 5. 参数

### 5.1 设计参数（`config.py`，`frozen=True`）

```python
sample_start      = "2021-12-01"
K                 = 50
liq_window_days   = 30
refresh_months    = 1
buffer_L          = 0
min_history_bars  = 720       # 闸 2
min_oi_coverage   = 0.90      # 闸 3
min_active_days   = 15        # 闸 4
stablecoin_bases  = ("USDC","FDUSD","TUSD","BUSD","DAI","USDP","SUSD","USDD","PYUSD","EUR")
```

| 取值 | 依据 |
|---|---|
| `K=50` | 第 1 名与第 50 名流动性差 168 倍，切在合理档位 |
| `liq_window_days=30` | 实测月换手 **18.9%**（60 天为 13.0%，更稳但更滞后） |
| `refresh_months=1` | 滞后不进事件研究的问题，噪声才进 → 月度冻结 |
| `min_history_bars=720` | = 流动性窗口，**最小可行值** |
| `min_oi_coverage=0.90` | 允许 30 天缺 3 天。**不取 1.0** —— 存在全市场级偶发缺失 |
| `min_active_days=15` | 有成交天数分布**两极**（正常币 30/30，停摆币 0/30） |

**稳健性对照**：`liq_window_days ∈ {60, 90}`；`refresh_months = 3`。

### 5.2 运行参数（CLI，不进 config）

```bash
--sample-end 2026-10-31    # 必填，无默认；必须是月末日
```

**为什么强制显式**：若设默认值，就可能出现「忘了指定 → 结果没有明确样本边界」。
每个结果必须携带样本截止日。

**运行级元信息**写 `data/00_config/sample_end.json`（不冗余进 manifest）。

### 5.3 下载参数

| 参数 | 值 | 依据 |
|---|---|---|
| 并发 | **32** | 实测 16→32 吞吐已饱和 |
| 连接超时 | 15 s | |
| 读取超时 | **45 s** | 实测极端长尾 45.8s |
| 重试次数 | **3** | |
| 退避 | `2^attempt` 秒 + 0–1s 抖动 | 抖动必需 —— 并发同时失败会成尖峰 |

**跑完对未取得项再补一轮** —— 把问题在同一次运行内解决，避免等到下次运行。

**缓存必须原子写**：
```python
tmp = path + ".name" + ".part"; tmp.write_bytes(data); os.replace(tmp, path)
```

**缓存文件名必须含源名。** 键用 `{source}__{symbol}__{period}.zip`。
若键里没有源名（只用 `{symbol}/{period}`），四个源会**共用同一个键**，
后到的源会命中前一个源的缓存并把它当自己的数据 —— 静默的正确性灾难。

**⚠️ 百分号编码只用于 URL，绝不可用于文件路径。**
`quote_seg()` 是为 URL 服务的（中文合约名不编码会让 `urllib` 抛 `UnicodeEncodeError`）。
若把它顺手用在落盘路径上，`币安人生USDT` 会变成
`symbol=%E5%B8%81%E5%AE%89%E4%BA%BA%E7%94%9FUSDT.parquet` —— 可读性尽失，
且任何按文件名反查合约的代码都要多一层解码。**文件系统用原始名字即可**，
NTFS 完全支持 Unicode。实测踩过：两个源的文件被写成编码名。

#### 5.3.1 一遍过：下载即解压，不要"先全下再统一转换"

```
✗ 两阶段   下载 → 全部落缓存 → 再逐个重新打开解压 → 落盘
             41 分钟            60 分钟，且【无任何进度记录】

✓ 一遍过   下载 → 就地解压 → 攒批 → 落盘 → 释放缓存 → 打进度戳
                                                   ↑ 断点续传靠它
```

两阶段写法要读**两遍磁盘**，而且第二遍中断一次就要从头再来（实测 60 分钟）。
一遍过把 zip 读一次就丢，并给每个文件打 `raw_written_at`：

| | 两阶段 | 一遍过 |
|---|---|---|
| 磁盘读 | 2 遍 | **1 遍** |
| 中断损失 | 从头重来（60 分钟） | **< 1 分钟** |
| 缓存释放 | 需手动删 | **随进度自动，跑完为空** |
| 幂等 | 未验证 | **SHA256 逐字节一致** |

**打戳与删缓存必须走同一条路径。** 若某个分支打了戳却忘了删缓存，
缓存会永久残留；若某分支删了却忘了打戳，下次会重复下载。
实测踩过两次：先是"整组全 404 时 `buf_rows==0` 导致永不收尾"，
再是"`ok` 但无整点行的文件打了戳却没删缓存"。

#### 5.3.2 网络：DNS 污染与 VPN

**实测：中国大陆网络下 `s3-ap-northeast-1.amazonaws.com` 的 DNS 被污染**
（解析到 `130.211.15.150`，谷歌云段，TCP 443 超时）。`www.binance.com` 同样
（`128.242.245.244`）。`data.binance.vision`（CloudFront）不受影响。

| 环节 | 是否需要 VPN |
|---|---|
| **S3 枚举**（确定下载清单） | ✅ **需要** |
| CDN 文件下载 | ❌ 不需要 |
| 纯本地计算（Step 4–6） | ❌ 不需要 |

**VPN 的代价（实测）**：CDN 吞吐 **140 → 89 文件/秒（慢 36%）**；
并发 32 时约 13% 请求瞬时失败（重试可救）。

**⚠️ VPN 下 S3 列表接口不稳定。** 同一个请求，时返回 22 个键、时返回 0 个键。
实测因此静默丢掉了 1 个中文名合约（`币安人生USDT`）的全部数据。
**应对**：枚举结果必须与"该合约是否已有数据"交叉验证；对单合约失败要能单独补抓，
不能只依赖一次枚举。**中文名合约（百分号编码路径）尤其容易触发。**

---

## 6. Universe 构造

### 6.1 五条资格闸（逐期、无前视）

**必须是逐期判定** —— 用全生命周期的统计量（如整体覆盖率）作闸会引入前视。

| # | 判据 | 阈值 |
|---|---|---|
| **1** | 非稳定币（按 `base_asset` 判，不按符号字面） | — |
| **2** | 截至 M 月初已有 ≥ N 根 1h bar | `min_history_bars = 720` |
| **3** | trailing 30 天内 `sum_open_interest` 非空天数占比 ≥ N | `min_oi_coverage = 0.90` |
| **4** | trailing 30 天内 `quote_volume > 0` 的天数 ≥ N | `min_active_days = 15` |
| **5** | 非代币化传统金融资产（**本项目追加**） | `exchangeInfo` 判据，见下 |

**闸 5 的必要性**：归档里有大量**代币化传统金融资产** —— 美股（`TSLAUSDT` `NVDAUSDT`
`GOOGLUSDT` 等）、港韩 A 股（`TENCENTUSDT` `SAMSUNGUSDT` `KORUUSDT`）、
ETF（`SPYUSDT` `QQQUSDT` `SOXLUSDT`）、商品（`XAUUSDT` 金、`XAGUSDT` 银、
`CLUSDT` 原油）、指数（`DEFIUSDT` `BTCDOMUSDT` `ALLUSDT` `BLUEBIRDUSDT`）、
外汇（`USDBRLUSDT`）。它们能通过闸 1–4，但**不是加密资产**，混入会让结论无法解释。

**判据用 `exchangeInfo` 的分类字段，不用手工名单：**

| 字段 | 加密资产 | 传统金融 |
|---|---|---|
| `contractType` | `PERPETUAL` | `TRADIFI_PERPETUAL` |
| `underlyingType` | `COIN` | `EQUITY` · `HK_EQUITY` · `KR_EQUITY` · `CN_EQUITY` · `COMMODITY` · `PREMARKET` · `FX` · `INDEX` |

**通过闸 5 ⇔ `contractType == "PERPETUAL"` 且 `underlyingType == "COIN"`。**
实测这一条在归档里剔掉 **216 个**非加密资产，保留 684 个。

⚠️ **为什么不用手工名单**：首版名单 35 个，漏进 21 个代币化标的；补齐到 55 个后，
仍漏掉 `GOOGLUSDT`/`SPYUSDT`/`NBISUSDT`，也漏掉 25 个当时不在池里的。
**手工名单的结构性缺陷是：候选池按排名滚动，新标的随时可能进池** ——
每轮都要重新人工核对，必然出错。API 判据一次到位，且自动跟进新增标的。

⚠️ 该判据也排掉 `PERPETUAL/INDEX` 的**指数永续** —— 它们是合成品，不是单一资产。

⚠️ **局限**：`exchangeInfo` 只含**当前挂牌**的合约，已下架的查不到。
脚本里留了 `DELISTED_NON_CRYPTO` 兜底名单（当前为空 —— 实测池里查不到的那些
合约全部是加密资产）。**新增合约时要复核**，脚本跑完会打印分类剔除统计供核对。

**闸 2 / 闸 3 的两个易错点**：

- **闸 2 用 bar 数，不用 `onboard_date`** —— 合约上市与 OI 归档**不同步**（BTC 差约 3 个月）
- **闸 3 用 `sum_open_interest` 本身的空值率**，**不得**用那 4 个衍生字段
  （大户多空比等）—— 它们 **2022 全年大面积为空**，用作闸会把 2022 整年误杀

**排序即第二层流动性闸**：通过五条闸后取流动性前 K。

### 6.2 PIT 规则

```
每月 M：
  Step 1  排名量 liq(sym, 月初) = median(quote_volume) over [月初−30天, 月初)
                                                          ↑ 严格开口，否则前视
  Step 2  五条资格闸（§6.1）
  Step 3  对通过闸的合约按 liq 降序排名
  Step 4  取前 K = 50（无缓冲带）
  Step 5  成员集在 M 月内【冻结】
```

**关键 1**：`liq` **逐日滚动**更新（保证无前视），成员集**按月冻结**
（避免成员标记变成噪声）。这两件事必须分开。

**关键 2**：**流动性度量的数据源全程用月频 klines，不换源** ——
口径不一致会成循环定义。

**关键 3**：**不要写 `if delisted: remove`**。下架币的处理是自然的 ——
合约停止交易后，闸 4 自然不通过（无正成交额），成员表下月落选。
**下架币存活期的完整历史留在样本里。**

### 6.3 候选池 ≠ 成员集

```
成员集    = 每个刷新期 50 个（逐月浮动）
候选池    = 曾入过成员集的并集（实测 285 个）= Step 2 的产出 = 下载范围
```

**恒等式**：一个币只有排进前 K 才可能成为样本 ⇒ 候选池 = 所有前 K 名的并集。
不需要任何额外门槛。

**Step 2 的候选池是下界，不是最终成员集** —— 它只能做闸 2 与闸 4 的宽松草稿版
（闸 3 需要 OI 数据，那时还没下）。Step 6 会用完整五条闸再筛一次。

### 6.4 换手率（如实报出）

K=50、30 天窗口、月度刷新 → **月换手 18.9%**（年化约 227%）。
这是加密市场流动性排名的**真实性质**，非噪声。

---

## 7. 数据契约

> **权威定义在 `lib/schema.py`。** 本节讲语义，类型以代码为准。

### 7.1 类型词汇表

```
"string"    →  pandas "string"（原生，不绑 pyarrow 后端）
"float64"   →  pandas float64
"timestamp" →  pandas datetime64[ns, UTC]
"bool"      →  pandas bool
```

- **整数一律用 float64**：float64 精确表示到 2^53；而 `int8/int16/...` 不支持 NaN
- **全部数据列允许 null**。唯一例外：**标识列强制非空** ——
  主键为空即损坏（NaT 在 join 时静默匹配不上，那些行会无声消失）

### 7.2 第 2 层：4 张规范化表

| 表 | 主键 | 频率 | 源 | 列 |
|---|---|---|---|---|
| `klines_1h` | `(symbol, ts)` | 1h 原生 | `klines` 月频 | `symbol`, `ts`, `ts_end`, OHLC, `volume`, `quote_volume`, `trades`, `taker_buy_volume`, `taker_buy_quote_volume` |
| `mark_index_1h` | `(symbol, ts)` | 1h 原生 | `markPriceKlines` + `indexPriceKlines` | `symbol`, `ts`, `ts_end`, `mark_close`, `index_close` |
| `oi_1h` | `(symbol, ts)` | 5m→1h 对齐 | `metrics` 日频 | `symbol`, `ts`, `ts_end`, `oi`, `oi_missing` |
| `funding` | `(symbol, ts_funding)` | 8h 事件 | `fundingRate` 月频 | `symbol`, `ts_funding`, `funding_rate`, `funding_interval_hours` |

- **四张表都存 `ts_end`**（= `ts + 1h`）：它是区间终点 / OI 对齐时刻 / 决策时刻 /
  `funding` 的 join 键。不存的话 join 前要自己算，算错偏 1 小时且不报错。
- **第 2 层是稀疏的** —— 只存源里真实存在的行，不发明行。密集网格是 `features_1h` 的职责。
- **`mark_index_1h` 合并 mark 与 index**：实测两者时间戳完全重合，分表无收益。
- **`klines_1h.trades` 来自源列 `count`**（改名）。

### 7.3 `features_1h`

**主键** `(symbol, ts)`　**分区** `year=YYYY/chunk=YYYY-MM.parquet`　**密集网格**

**19 列**：
`symbol` `ts` `ts_end` `open` `high` `low` `close` `volume` `quote_volume`
`trades` `taker_buy_volume` `taker_buy_quote_volume` `oi`
`mark_close` `index_close` `funding_rate` `funding_interval_hours`
`bar_missing` `oi_missing`

| 列 | 语义 |
|---|---|
| `ts` | bar 起点 `H` |
| `ts_end` | `ts + 1h`；区间终点 = OI 对齐时刻 = 决策时刻 |
| `oi` | `OI(ts_end)`，**张数**（源列 `sum_open_interest`） |
| `funding_rate` / `funding_interval_hours` | **仅 `00/08/16` 非空** |
| `bar_missing` | 该小时在 `klines_1h` 中无对应行 |
| `oi_missing` | 该小时 OI 快照不存在 |

```sql
features_1h = klines_1h
    LEFT JOIN mark_index_1h ON (symbol, ts)
    LEFT JOIN oi_1h          ON (symbol, ts)
    LEFT JOIN funding        ON (symbol, ts_end = ts_funding)
```

**不存的源列**：

| 源列 | 理由 |
|---|---|
| `sum_open_interest_value` | 与 `oi × close` 冗余 |
| 4 个大户多空比字段 | 2022 全年大面积为空 |
| `ignore` | 恒为 0 |
| mark/index 的 OHLC 与 `volume`/`count` | `volume=0`、`count=3600`（常量） |

**派生量**（`price_change` / `oi_change` 及 lookback `N`）**一律放 Phase 2**
—— 否则改一次 `N` 就要重跑整条数据层。

**`features_1h` 只含候选池合约**，但候选池合约的**所有小时**都保留。

### 7.4 `validate()` 检查什么

```python
from lib.schema import validate, SchemaViolation
validate(df, "features_1h")      # 失败抛 SchemaViolation，一次报全部问题
```

| # | 检查 | 挡住的静默错误 |
|---|---|---|
| 1 | 列名与**顺序**完全一致 | 列错位 |
| 2 | dtype 与语义类型一致 | 类型漂移 |
| 3 | 标识列**非空** | NaT 在 join 时静默不匹配，行无声消失 |
| 4 | 主键**无重复** | 源文件存在完全一致的副本行 |
| 5 | 主键**已排序** | 源文件时间戳非单调 |
| 6 | **无整列为空** | 整列解析失败 |
| 7 | 标识列落在**整小时** | 毫秒/秒单位搞混 |
| 8 | `ts_end − ts == 1h` | 同上，独立第二道 |
| 9 | 标识列为 tz-aware **UTC** | naive datetime |

**失败时一次报全部问题**，不是遇到第一个就停。

**不做的检查**：值域与跨列一致性（`oi_value/oi/close ≈ 1` 等）——
它们是统计判断、阈值需标定。上面九条结构检查已覆盖会导致数值异常的**根因**。

---

## 8. 数据质量规则

### 8.1 三个静默错误（必须处理，不会报错）

| # | 规则 | 说明 |
|---|---|---|
| a | **读入后立即按时间戳排序** | 近期文件非单调（存在负间隔）。不排序则 `shift(1)` 静默算错 |
| b | **去重** | `2020-09`→`2021-06` 有完全一致的副本行（576 行 / 288 唯一）。去重但**记录数量** |
| c | **区分「确认 404」与「超时」** | 网络抖动会被误记为缺失 |

### 8.2 已知脏点

| 位置 | 问题 | 处理 |
|---|---|---|
| 个别日期 | 缺失，或 287 行而非 288 | 记入缺失报告 |
| **2022 全年** | 4 个大户多空比字段大面积空 | **不存这些列** |
| 新币首日 | 从半天开始 | 按可用天数判定，非按上币日 |
| 零成交额月 | 文件存在但 `quote_volume = 0` | 闸 4 的判据 |

### 8.3 缺失数据报告

**检测用「日」，呈现用「连续缺口区间」**（不按日、也不按月）。

- 纯月粒度太粗：`覆盖率 29/30` 看不出缺的是哪天
- 纯日粒度表爆炸：约 200 万行，99% 是「正常」

**缺口区间表**（相邻缺失日合并成一条）：

| symbol | source | gap_start | gap_end | days | category |
|---|---|---|---|---|---|
| BTCUSDT | metrics | 2025-04-15 | 2025-04-15 | 1 | `confirmed_404` |

**五类必须严格区分**：

| category | 算真缺失? |
|---|---|
| `confirmed_404` | ✅ 是 |
| **`retry_exhausted`** | ❌ **不是** —— 是待办，**不得进入最终缺失报告** |
| `partial_rows`（行数 < 288） | ⚠️ 记录 |
| `field_empty` | ⚠️ 记录 |
| `zero_volume` | ⚠️ 记录 |

**另配覆盖率汇总表**：明细回答「哪里缺」，汇总回答「整体质量如何」。

---

## 9. 增量更新

### 9.1 数据源优先级

```
对每个 (symbol, 时间戳):
    该月的【月频文件】在 manifest 中 status = ok   →  用月频
    否则                                        →  用日频补
    两者都没有                                   →  该时间戳不存在
```

因**月频 = 日频拼接（逐值相同）**，两者可自由混用，**增量不必等月份结束**。

### 9.2 流程

```
【A】更新合约清单      归档枚举 → 新增/下架的合约
【B】确定该有哪些文件    候选池 × 存续期 × [sample_start, sample_end]
【C】与 manifest 对账    跳过 status=ok；跳过 confirmed_404（TTL 内）
【D】下载缺失的          月频（若有）+ 日频（补不完整月）
【E】增量建第 2 层       只处理尚未并入的文件
【F】增量建 features_1h  upsert 到受影响的 chunk
【G】建 universe 表
```

**`sample_end` 决定裁剪边界，不决定数据来源。**

### 9.3 `manifest` 表结构

| 列 | 含义 |
|---|---|
| `source` / `symbol` / `period` / `granularity` | 定位 |
| `remote_path` / `filename` | **重下时唯一依据** |
| `status` | `ok` / `confirmed_404` / `retry_exhausted` |
| `checksum_official` / `checksum_verified` / `bytes` | 校验 |
| `first_seen_at` / `last_probed_at` / `downloaded_at` | 时间戳 |
| `dup_rows_removed` | 该文件解析时去除的重复行数 |
| `layer2_built_at` | 是否已并入第 2 层（增量解析的入口） |

### 9.4 三个边界

**① `confirmed_404` 需 TTL 重探（7 天）**
月频文件在次月 1–2 日才发布，且并非每月都齐。若永久缓存 404 会**永久漏掉**该文件。

**② `upsert` 而非覆盖**
新月份数据会落在已有年份分区里：读现有 chunk → 合并 → 按主键去重 → 原子写回。

**③ chunk 按「月」切**
因 `sample_end` 只用完整月，月是天然原子单位：**完整月的 chunk 一旦写完永不改变**，
每次增量只重写受影响的那一两个 chunk。

| 状态 | 哪些 | 行为 | 不变量 |
|---|---|---|---|
| **frozen** | 除最后 1 个外全部 | 写完不改 | 行数按 `(chunk, symbol)` 固定 |
| **hot** | `sample_end` 所在月 | 每次追加 | 行数单调增 |

⚠️ 新上市合约首月不满整月。**行数不变量按 `(chunk, symbol)` 判定，不按 chunk 总行数。**

### 9.5 第 2 层的构建顺序是硬性要求

`layer2_built_at` 是**单一时间戳**，因此：

```
解析 mark ✓  →  解析 index ✓  →  合并  →  写 mark_index_1h parquet ✓
                                          →  最后写 layer2_built_at
```

时间戳必须**最后写**，且失败时**不写**。否则 `mark` 成功而 `index` 失败时，
该文件会被标记为「已建」，**`index` 的数据永久丢失且不报错**。

---

## 10. 文件夹结构

### 10.1 项目根目录

**代码平铺在根目录，数据在共享的根 `data/`。**

```
Industrial Programme I/
│
├─ config.py                     设计参数（Phase 2–5 也用，故在根）
├─ lib/schema.py                 数据契约（Phase 2–5 也用，故在根）
│
├─ phase1_data/                  Phase 1 的代码
│   └─ build_candidate_pool.py   ✅ 已产出
│
├─ data/                         全部产出（见 §10.2）
├─ outputs/                      图表与报告（Phase 3+ 才用）
├─ phase2_regime/ · phase3_event/ · phase4_funding/ · phase5_strategy/
│
├─ PHASE1_GUIDANCE.md            本文件
├─ DATA_RECON_2026-09-28.md      数据侦察实测报告
├─ research_archive/             规划期材料
└─ .vscode/ · .gitattributes · .gitignore · .git/
```

**为什么平铺、不按阶段分文件夹**：所有阶段**共享同一个 `data/`** ——
`features_1h` 是 Phase 2–5 的输入。若按阶段分文件夹，Phase 2 就要写
`../phase1_data/data/...`，跨目录引用很脆。

**`config.py` 与 `lib/schema.py` 在根目录** —— 它们跨阶段复用，
放 `phase1_data/` 会暗示只属 Phase 1。

**脚本从 `phase1_data/` 运行时的 import**：脚本首行加
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```
（Phase 2–5 同理用 `parent.parent`。）

### 10.2 `data/` 内部

```
data/
│
├─ 00_config/                         构建元信息
│   ├─ sample_end.json                {sample_end, config_snapshot, run_at, 各阶段计数}
│   └─ manifest.parquet               逐文件下载状态（断点续传的唯一依据）
│
├─ 01_layer2/                         4 张规范化源表（小时粒度）        ⬜ Step 4
│   ├─ klines_1h/year=YYYY/chunk=YYYY-MM.parquet
│   ├─ mark_index_1h/year=YYYY/chunk=YYYY-MM.parquet
│   ├─ oi_1h/year=YYYY/chunk=YYYY-MM.parquet
│   └─ funding/year=YYYY/chunk=YYYY-MM.parquet
│
├─ 02_features/                                                       ⬜ Step 5
│   └─ features_1h/year=YYYY/chunk=YYYY-MM.parquet
│
└─ 03_reference/                      分析与审计用的参考表
    ├─ candidate_pool.csv             ✅ 285 个合约
    ├─ master.parquet                 一币一行（893）                 ⬜ Step 3
    ├─ universe_eligibility.parquet   一币一行                        ⬜ Step 6
    ├─ universe_membership.parquet    (symbol, date)                  ⬜ Step 6
    └─ member_changes.parquet         进/出记录                       ⬜ Step 6
```

**不保留 RAW 归档**（zip 镜像、`oi_5m` 全量均不存）。
**下载缓存是临时的，用完即清。**

**`universe_*` 放 `03_reference/`**：其粒度是**日**与**合约**，
与 `features_1h` 的**小时**粒度不同，不能混放。

---

## 11. 自测

```bash
python config.py                    # 8 项：validate_sample_end 行为 + Config frozen
python -m lib.schema                # 65 项：round-trip / validate 放行 / validate 捕获 / 结构自检
python phase1_data/build_candidate_pool.py --sample-end 2026-08-31
```

**退出码 0 = 全过。**

`build_candidate_pool.py` 支持：
- `--skip-download` —— 只用已有缓存重算
- `--subset SYM [SYM ...]` —— 只处理指定合约（核验用）
- 环境变量 `P11_DATA_ROOT` —— 把产出重定向到别处（核验时不污染正式产出）
