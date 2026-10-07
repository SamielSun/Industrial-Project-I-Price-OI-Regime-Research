# Phase 1 数据层 —— 实施说明（D1）

**目标**：为 THEO「Price + Open Interest Regime Signal」准备干净、对齐、无前视的 1h 面板。

**样本**：`2021-12-01` .. `2026-08-31`（57 个月）。起点由 OI 归档的断崖唯一定死 —— 实测 103 个合约从 2021-12 才有 OI。

**非目标**：制度标注（Phase 2）· 事件研究（Phase 3）· 回测（Phase 5）。

**一句话**：从 Binance 归档下载 5 个源 → 规范化成 4 张 1h 表 → 合成 19 列密集面板 → 逐月四条资格闸选出 PIT 成员集。

---

## 0. 一页速览

### 六条命令（全部必填 `--out-root`）

```bash
python phase1/build_candidate_pool.py --out-root data --sample-end 2026-08-31   # Step 0–2
python phase1/fetch_market_data.py    --out-root data --sample-end 2026-08-31   # Step 3
python phase1/build_layer2.py   --out-root data --sample-end 2026-08-31         # Step 4
python phase1/build_features.py --out-root data --sample-end 2026-08-31         # Step 5
python phase1/build_universe.py --out-root data --sample-end 2026-08-31         # Step 6a
python phase1/build_qa.py       --out-root data --sample-end 2026-08-31         # Step 6b
```

自测：`python config.py`（8 项）· `python -m lib.schema`（65 项）
核验：`python phase1/build_qa.py --out-root data --sample-end 2026-08-31 --verify`

### 数字账（改代码后这里必须同步）

```
归档合约        1,057
USDT 结尾         901
硬过滤后          683        剔除 218（非加密 215 + 稳定币 3）
候选池            285        逐月 top-50 并集
有数据的          677        候选池 + 落选，但只有候选池被下载
Step 4 四张表   23,933,500 行 / 228 文件 / 546.9 MB
features_1h   7,253,002 行 / 57 文件 / 541.6 MB / 19 列
四闸全过          8,938      16,245 个 (合约,月) 单元中
成员集            2,700      54 月 × 50，涉及 249 个合约
缺失文件             67      归档里确实不存在
校验和            1,442      文件数
```

### 关键常量（`config.py`）

```
sample_start = 2021-12-01     K = 50                liq_window_days = 30
min_history_bars = 2160       闸 2①  90 天
min_oi_coverage = 0.90        闸 3①  OI 覆盖率
max_oi_gap_hours = 48         闸 3②  最长连续缺失
require_live_at_month_start   闸 2②  月初仍在交易
stablecoin_bases              11 个 baseAsset
```

### 两个不变量

1. **PIT**：任何决策只用 `ts_end` 时刻之前的信息。流动性窗口 `[月初−30d, 月初)` **严格开区间**。
2. **缺失如实记录**：D1 的干净**不靠"没有缺失"证明，靠"缺失被完整记录"证明**。

---

## 1. 产出在哪

```
data/
├─ 00_config/                       配置与账本（非交付数据）
│   ├─ manifest.parquet             355,810 行：逐文件下载台账
│   ├─ archive_contracts.csv        1,057 行：归档枚举（Step 0）
│   ├─ kept_contracts.csv             683 行：硬过滤通过（Step 1）
│   ├─ dropped_contracts.csv          218 行：硬过滤剔除 + 原因（Step 1）
│   └─ _cache/klines/               527.7 MB：Step 0–2 的下载缓存（可删，见 §5）
├─ raw/                             1,144 文件 / 1,130.1 MB   Step 3
│   ├─ klines/symbol=XX.parquet         285 个
│   ├─ markPriceKlines/symbol=XX.parquet  284
│   ├─ indexPriceKlines/symbol=XX.parquet 284
│   ├─ fundingRate/symbol=XX.parquet      285
│   └─ metrics/year=YYYY.parquet            6 个（按年，不分合约）
├─ 01_layer2/                         228 文件 / 546.9 MB   Step 4
│   └─ {klines_1h,mark_index_1h,oi_1h,funding}/year=Y/chunk=Y-M.parquet
├─ 02_features/features_1h/            57 文件 / 541.6 MB   Step 5
│   └─ year=Y/chunk=Y-M.parquet
├─ 03_reference/                                          Step 2 & 6a
│   ├─ candidate_pool.csv            285 行（Step 2）
│   ├─ master.parquet                285 × 11（Step 6a）
│   ├─ universe_eligibility.parquet  16,245 × 22（Step 6a）
│   ├─ universe_membership.parquet    2,700 × 8（Step 6a）
│   └─ member_changes.parquet            57 × 6（Step 6a）
└─ 04_qa/                                                 Step 6b
    ├─ missing_files.parquet    67 行
    ├─ gaps.parquet          4,880 行
    ├─ coverage.parquet      1,425 行
    ├─ data_dictionary.md
    ├─ checksums.sha256      1,442 行
    └─ ../REPRODUCE.md
```

**交付物**：`01_layer2/` · `02_features/` · `03_reference/` · `04_qa/`（含 `REPRODUCE.md`）。
`00_config/` 是账本不是数据，但 `manifest` 是审计凭据。

---

## 2. 处理流程

### 2.1 总表

| Step | 脚本 | 输入 | 输出 | 实测 |
|---|---|---|---|---|
| **0** | `build_candidate_pool.py` | S3 列表接口 | 归档 **1,057** | 1.7s |
| **1** | 同上 | + `exchangeInfo` | 硬过滤 **683** | 秒级 |
| **2** | 同上 | 月频 `klines`（**18,832** zip） | 候选池 **285** | 缓存命中 119s |
| **3** | `fetch_market_data.py` | 候选池 + S3 列表 | `raw/` **1,144 文件 / 1.13 GB** | 约 111 分钟 |
| **4** | `build_layer2.py` | `raw/` | 4 张表 **228 文件 / 546.9 MB** | 847s |
| **5** | `build_features.py` | 4 张表 + 候选池 | `features_1h` **57 文件** | 357s |
| **6a** | `build_universe.py` | 面板 + 候选池 + **快照** | universe 四表 | 115s |
| **6b** | `build_qa.py` | 面板 + manifest | 缺失报告 + 字典 + 校验和 | 21s |

**只有 Step 0–3 需要 VPN**（S3 枚举 + CDN 下载）。Step 4–6b 纯本地；
Step 6a 的闸 4 判据走快照，**离线可复现**。

### 2.2 Step 0 · 枚举归档

**输入**：S3 列表接口（一次 HTTP GET，无文件、无鉴权）
**输出**：`archive_contracts.csv` 1,057 行

```
GET https://s3-ap-northeast-1.amazonaws.com/data.binance.vision
    ?list-type=2&prefix=data/futures/um/monthly/klines/&delimiter=/
```

`delimiter=/` 让 S3 返回"一层目录"：合约名在 `<CommonPrefixes>` 里，该层 `<Key>` 数为 0。
分页靠 `IsTruncated` / `NextContinuationToken`。实测第 1 页 1,000 个 + 第 2 页 57 个 = **1,057**。

⚠️ **S3 列表不是 Binance 设计的 API** —— 它是 AWS 基础设施读 Binance 的 bucket。
Binance 官方仓库只文档化"网站下载"与"直链"，没有合约清单端点。**所以枚举结果必须落盘**。

⚠️ **枚举必须可复核**：实测曾一次记 893、一次记 1,057，差 164 个。合约数只增不减，
所以 893 必然是**不完整枚举**。现在同时落盘合约总数与 USDT 结尾数两个数。

⚠️ `prefix` 必须传**原始合约名**，不编码 —— S3 内部会 `urlencode` 一次，提前编码成双重编码，
服务端解码后拿到字面量 `%E5%B8%81…`，**永远匹配不到真实 key，且不留任何记录**。

### 2.3 Step 1 · 硬过滤

**输入**：901 个 USDT 结尾合约 + `exchangeInfo` 4 字段 + `stablecoin_bases`
**输出**：`kept_contracts.csv` 683 行 + `dropped_contracts.csv` 218 行

```
901 − 215（非加密资产）− 3（稳定币）= 683

剔除明细（218）：
  TRADIFI_PERPETUAL/EQUITY      174      PERPETUAL/INDEX     3
  TRADIFI_PERPETUAL/HK_EQUITY    15      稳定币               3
  TRADIFI_PERPETUAL/KR_EQUITY     8      （FRAXUSDT USDCUSDT USTCUSDT）
  TRADIFI_PERPETUAL/COMMODITY     8      TRADIFI_PERPETUAL/CN_EQUITY  2
  TRADIFI_PERPETUAL/PREMARKET     4      TRADIFI_PERPETUAL/FX         1
```

**判据只有分类字段** —— 不设名字黑名单：

| 字段 | 加密（放行） | 其他（拦下） |
|---|---|---|
| `contractType` | `PERPETUAL` | `TRADIFI_PERPETUAL` · `CURRENT_QUARTER` · `NEXT_QUARTER` |
| `underlyingType` | `COIN` | `EQUITY` `HK_EQUITY` `KR_EQUITY` `CN_EQUITY` `COMMODITY` `PREMARKET` `FX` `INDEX` |

**通过 ⇔ 两个字段同时命中。** 名称会骗人：`COINUSDT`（Coinbase）`MSTRUSDT` `HOODUSDT`
`JPMUSDT` 都是 `TRADIFI_PERPETUAL/EQUITY`；`BTCDOMUSDT` 看着像 BTC，实为市值占比合成指数。

⚠️ **故意的例外：`PAXGUSDT` / `XAUTUSDT` 放行。** Binance 标它们 `PERPETUAL/COIN`。
这是对的 —— 它们是**链上发行的加密原生合约**（24/7、无收盘时段），结构上与加密永续无区别。
实测 `PAXGUSDT` 是成员 11 个月（2025-10 ~ 2026-08，rank 13–49）。

⚠️ **稳定币名单是手工维护的，因为没有任何单一官方来源是完整的。** 三源对比（覆盖归档稳定币）：

| 来源 | 覆盖 |
|---|---|
| 本名单（11 个 baseAsset） | `USDC` `FRAX` `USTC` |
| CoinGecko 稳定币板块 | 加 `BOB` |
| **Binance 官方 `stablecoin` 标签** | **只有 `USDC`**（且只打在现货对上） |

官方标签反而是**最少的**，不能单独用。名单里 `USDT` / `EUR` 已被移除（归档里 baseAsset
为它们的合约各 0 个）；`BOB` 曾纳入后撤回（只有单一来源 + 现货无交易对 + `BOBUSDT`
状态已是 `SETTLING`）。

### 2.4 Step 2 · 候选池

**输入**：683 个合约 + 月频 `klines`（**18,832** zip）
**输出**：`candidate_pool.csv` 285 行（一列 `symbol`）

```
阶段 A  683 次 S3 list（每合约一次）→ 677 个有窗口内数据，0 个列目录失败
阶段 B  下载 18,832 个 zip 到 _cache/klines/，两轮 + 断点续传
阶段 C  逐月 M：liq = median(该月全部小时的 quote_volume)    ← 整月，约 720 根 1h bar
                → 过草稿闸：上月有效小时数 >= 360
                → 按 liq 降序取前 K = 50
        候选池 = 各月前 50 名的并集
```

**草稿闸只有一条**：`bars[M−1] >= 360`（`24 × 15` 小时）。
`i < 1` 单独挡掉样本首月。实测拦截 **967 个 (合约,月)**。

原设计还有第二条「到 M 月初已有 ≥ 1 个月数据」，**实测拦不到任何东西，已删除**：

| | 挡下数 |
|---|---|
| 只有它挡下 | **0** |
| 只有 `bars>=360` 挡下 | 290 |
| 两个都挡 | 677（全在 2021-12） |

原因：合约的数据月份**天然连续**，上月有 bar 就意味着之前也有，前者恒被后者蕴含。

**为什么必须有闸**：防的是**流动性极好的新上市合约**。实测 2023-05：

| 名次 | 合约 | 当月 liq 中位 |
|---|---|---|
| 1 | `BTCUSDT` | 343,448,934 |
| 2 | `ETHUSDT` | 163,997,375 |
| **3** | **`1000PEPEUSDT`** | **41,805,004** ← 被闸挡下 |
| **8** | **`SUIUSDT`** | **11,072,299** ← 被闸挡下 |

没有闸，它们就是当月成员 —— 而 regime 阈值要用 rolling 分位估，几天数据估出来的是噪声。

**流动性用中位数而非平均**：单小时 `quote_volume` 能被拉高 **15 倍**（`BTCUSDT 2023-05`：
中位 3.43 亿、最大 51.6 亿、平均被右尾拉高 44%），个别合约平均/中位达 **5.0 倍**。
中位数衡量"典型小时能不能进得去"，这正是交易成本的意义。换指标会换掉成员：
`mean`/`sum` 换掉 8 个（2023-05）、`p25` 换掉 2–4 个、`median(trades)` 换掉 10–16 个。

**Step 2 与 Step 6a 的分工**：Step 2 的 top-50 是**并集**（曾经进过就留下），
只为控制 Step 3 的下载量。真正的成员集是 Step 6a 用同样的排名但过完四条闸后重新选的。

### 2.5 Step 3 · 下载 raw 数据

**输入**：`candidate_pool.csv`（285）+ 5 个源的归档
**输出**：`raw/` 1,144 文件 / 1,130.1 MB + manifest 追加 336,978 行

五个源：

```
monthly/klines/{SYM}/1h/              月频 1h bar
monthly/markPriceKlines/{SYM}/1h/     标记价
monthly/indexPriceKlines/{SYM}/1h/    指数价
monthly/fundingRate/{SYM}/            资金费率（★ 无 {interval}/ 层）
daily/metrics/{SYM}/                  5 分钟 OI 快照
```

⚠️ **四个源的路径模板不同**，`fundingRate` 既没有 `{interval}/` 层、文件名里还重复源名：

```
klines / mark / index : monthly/{src}/{sym}/{itv}/{sym}-{itv}-{ym}.zip
fundingRate           : monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip
```

⚠️ **清单必须逐源枚举，不能推算**：实测 9 个合约（`AGIXUSDT` `BLZUSDT` `BNXUSDT`
`FTMUSDT` `LINAUSDT` `OCEANUSDT` `REEFUSDT` `RENUSDT` `UNFIUSDT`）的 `indexPrice` 与
`fundingRate` **全部在 2025-07 同一个月截止**，而它们的 klines 一直到 2026-08 都有。
9 个合约同时断供只可能是归档侧的批量空洞。另有 13 个合约的 `markPrice` 在下架后
仍多写 12–23 个月空行。

**一遍过**（禁止"先全下再统一解压"）：

```
下载 → 就地解压 → 按 (源, 合约) 攒批 → 落 raw parquet → 释放这批缓存 → 打戳
                                                              ↑ 断点续传靠它
```

| | 两阶段 | 一遍过 |
|---|---|---|
| 磁盘读 | 2 遍（34.4 万个 zip） | **1 遍** |
| 中断损失 | 从头解压 60 分钟 | **< 1 分钟** |
| 缓存释放 | 需手动删 | **随进度自动，跑完为空** |

**打戳与删缓存必须走同一条代码路径**（都在 `stamp()` 里）—— 某分支打了戳却忘了删缓存，
缓存永久残留；反之则重复下载。

⚠️ **解析失败必须抛异常，不能返回 `None`**：原来"下载到了但读不懂"和"压缩包里没有
整点行"走同一分支（打戳 `ok` + 释放缓存），于是 **813 个 (合约,月) 被永久记为完成而
`raw/` 里一行都没有、缓存也已删除、无法追查**。

⚠️ **`metrics` 只保留 24 个整点快照**：原始每个合约每天 288 条（5 分钟一条），
筛 `minute == 0` 后 24 条。丢掉的 6 列里，`sum_open_interest_value` 与 `oi × 价格` 冗余，
4 个 ratio 字段 2022 全年大面积为空。

⚠️ **`metrics` 会多下"末月之后的第一天"**：让最后一根 bar 的 OI 不为空。末月取自
**klines**（合约是否在交易的权威判据），不是 metrics —— `LUNAUSDT` 的 metrics 有跨到
2024-06 的孤立残留，而 klines 止于 2022-05。

### 2.6 Step 4 · 第 2 层（4 张规范化表）

**输入**：`raw/` 1,144 文件 + 候选池
**输出**：`01_layer2/` 228 文件 / 546.9 MB

| 表 | 主键 | 列 | 行数 | 性质 |
|---|---|---|---|---|
| `klines_1h` | `(symbol, ts)` | 12 | 7,567,853 | **网格定义者** |
| `mark_index_1h` | `(symbol, ts)` | 5 | 7,567,853 | 左连到网格 |
| `oi_1h` | `(symbol, ts)` | 5 | 7,567,853 | 左连到网格 |
| `funding` | `(symbol, ts_funding)` | 4 | **1,229,941** | **事件表** |

**核心规则：网格 = `klines_1h` 实际存在的 ts。** 稀疏，不发明行。
三张网格表都用**左连接到这个网格** —— 这一条同时自然处理了两件脏事：

| 脏事 | 被什么挡掉 |
|---|---|
| 下架合约 mark/index 多写的尾部行 | klines 没有那些 ts |
| `LUNAUSDT` 的 OI 孤立残留（跨到 2024-06） | 同上 |

实测左连接**丢弃 278,578 行**（mark 131,947 + index 146,631），涉及 204 / 285 个合约。
丢得最多的是 `LUNAUSDT`（39,305 行）。

**`oi` 终点对齐**：`bar [ts, ts_end)` 配 `OI(ts_end)`。

```python
grid = k["ts"]                                     # 网格
o["ts_end"] = grid + 1h
oi["ts_end"] = oi["ts"].dt.floor("h")              # ★ 秒位必须截断
o = o.merge(oi, on="ts_end", how="left")
o["ts"] = o["ts_end"] - 1h
```

⚠️ **`create_time` 的秒位不恒为 0**（实测 4,138 行 / 64 个合约，如
`TLMUSDT 2022-05-09 11:00:59`），其中 **1,147 行是该合约该小时唯一的快照**。
不截断则匹配不上任何 `ts_end`，被静默记成 `oi_missing=True`，并把该合约的 OI 序列人为拉长。

**`funding` 是事件表，不连网格**。落在**结算时刻起的那根 bar**（`ts_funding == klines.ts`）。
`calc_time` 的毫秒位不恒为 0（`BTCUSDT` 有 2,240 行），**只能按整秒截断**。

**落盘按 `year=/chunk=YYYY-MM`**，逐合约写入意味着同一 chunk 会被写 285 次，
所以 `write_chunk` **必须读回合并**（单纯覆盖会让文件里只剩最后一个合约的数据）。
`partitioning=None` 关掉 pyarrow 从目录名推断分区列的行为。

### 2.7 Step 5 · `features_1h`（19 列密集面板）

**输入**：4 张表 + 候选池
**输出**：`02_features/features_1h/` 57 文件 / 7,253,002 行 / 541.6 MB

```
features_1h = klines_1h
    LEFT JOIN mark_index_1h ON (symbol, ts, ts_end)
    LEFT JOIN oi_1h          ON (symbol, ts, ts_end)
    LEFT JOIN funding        ON (symbol, ts)         ← funding 没有 ts_end
```

**四件事**：

| # | 做什么 | 实测 |
|---|---|---|
| 1 | **密集化**：`date_range(g0, g1)` 铺连续小时 | **+6,886 行** |
| 2 | **裁死尾**：`g1 = 最后一个正成交额日的 23:00` | **−321,737 行（4.25%）** |
| 3 | **派生两个标记** | `bar_missing` 6,886 · `oi_missing` 32,514 |
| 4 | **funding 两列分开处置** | 见下 |

**下界用第一根 bar（无条件），上界用最后有成交日的 23:00** —— 因为死尾只出现在末端。

⚠️ **死尾是什么**：合约下架后归档**继续写「整月零成交空行」到样本末端** ——
`volume`/`quote_volume`/`count` 全 0，`close` 冻在最后一价。实测 `WAVESUSDT`：
最后成交 2024-06-11，归档写到 2026-08-31，死尾 **19,464 行（占该合约 46.9%）**。
**不裁的后果**：Phase 2 算 `rolling.std()` 时死区 `std = 0`，会被当成"零波动"这个真信号 ——
它看起来完全合法，会通过所有检查。

⚠️ **全程零成交的合约必须丢掉**：它的 `last_day` 是 `NaT`，
`pd.date_range(g0, NaT)` 会抛 `ValueError` **直接终止整个运行**。

**两个标记的关系**：

```
bar_missing = 该小时在 klines_1h 中无对应行（密集化补出来的）      6,886 (0.095%)
oi_missing  = bar_missing  OR  该小时无 OI 快照                  32,514 (0.448%)
              bar_missing ⊂ oi_missing
```

分水岭：`oi_missing` 的 32,514 行里只有 6,886 行同时 `bar_missing`，
另外 **25,628 行是"bar 有、币安没发 OI 快照"**（涉及 187 个合约）—— 这才是真缺失。
所以只有 `oi_missing` 被用作闸 3 的输入，`bar_missing` 只进缺失报告。

**funding 两列的处置不同**：

| 列 | 处置 | 非空率 | 语义 |
|---|---|---|---|
| `funding_rate` | **不填充** | **16.65%** | **事件**："这一期收了多少钱" |
| `funding_interval_hours` | **seed + ffill** | **99.65%** | **状态**："当前规则是什么" |

填 `funding_rate` 就是**发明数据** —— 让 Phase 2 以为"每小时都有资金费率"。
所以 `build_qa.py` **不把它当缺口检测**。

**`funding_interval_hours` 的 seed**（`ffill` 救不了网格开头）：

```
g0 到首次网格内结算之间的小时，LEFT JOIN 找不到任何结算行 → NaN，而 ffill 上面没有值可传。
所以先 fillna(网格外最后一次结算的 interval) 再 ffill。
实测 55 个合约有网格外结算，其中 54 个真有空白期（典型 6 小时：
上线 02:00、首次结算 08:00）。若不 seed，这 6 小时会误留 null。
```

**剩下 0.35%（25,124 行 / 118 个合约）是真 null** —— 该合约**首次结算之前**的小时，
那时币安确实没公布过周期。例如 `TLMUSDT`：klines 从 2021-12 开始、funding 从 2023-03 才开始
（中间 9 个月零成交，合约消失又回来）。

⚠️ **`funding_interval_hours` 是状态量但不是恒定量**：142 个合约众数周期 4h、142 个 8h、
1 个 1h，且 **91 个合约中途改过周期**。实测 `1000XECUSDT` 2026-07-13 从 8h 改 1h ——
切换点前后 `ffill` 出来的值分别是 8 和 1，读起来是干净的。

**两阶段提交**：先写 `features_1h.new/`，全部成功后才 `os.replace` 换成正式目录。
理由是原版在建任何东西**之前**就 `rmtree` 整个面板，中途异常会留下一份
**"看起来合法"的残缺面板**（每个 chunk 都过了 `validate()`），而各 chunk 的行数与
`04_qa/` 的报告还停留在上一轮，下游无从察觉。

### 2.8 Step 6a · Universe（四条闸 + PIT 成员集）

**输入**：`features_1h`（只读 7 列）+ `candidate_pool.csv`（285）+ `exchangeInfo` 快照
**输出**：`03_reference/` 四张表

**评测范围 = 候选池 285 个合约**（不是全部归档合约）。精筛只回答"候选池里谁能当成员"；
更早的排除在 Step 1（`dropped_contracts.csv` 218 个）与 Step 2（没进过月度 top-50）里记账。

```
57 个月 × 285 合约 = 16,245 个 (合约, 月) 单元
```

**逐月评测，窗口 `[月初 − 30 天, 月初)` 严格开区间**：

```python
cut = 月初;  lo = cut - 30d
w = d[(d["ts"] >= lo) & (d["ts"] < cut)]          # ★ 不能碰月初之后
liq          = w.groupby("symbol")["quote_volume"].median()
oi_cov       = 1 - w.groupby("symbol")["oi_missing"].mean()
oi_max_gap_h = max_run_true(w.groupby("symbol")["oi_missing"])
```

**四条闸**：

| 闸 | 判据 | 阈值 | 单条拦下 |
|---|---|---|---|
| **1** | 非稳定币（按 `base_asset`） | — | **0** |
| **2①** | 截至月初已有 ≥ N 根 1h bar | `2160`（90 天） | **6,484** |
| **2②** | 最后活跃日 ≥ 月初（仍在交易） | `require_live_at_month_start` | **804** |
| **3①** | trailing 30 天 OI 覆盖率 ≥ N | `0.90` | **6,496** |
| **3②** | trailing 30 天最长连续缺失 ≤ N 小时 | `48` | **77** |
| **4** | 非加密资产 | 分类字段 | **0** |

「单条拦下」是**独立计数**（同一单元可被多闸拦下），不能相加。
闸 2① 与闸 3① 几乎拦住同一批（新合约既无 90 天历史，也无 30 天 OI）。

**逐闸递进漏斗**：

```
起点                      16,245
过闸 1  非稳定币            16,245   (−0)
过闸 2① 历史够               9,761   (−6,484)
过闸 2② 仍在交易             9,008   (−7,237)
过闸 3① OI覆盖够             8,975   (−7,270)
过闸 3② 缺口够短             8,938   (−7,307)
过闸 4  加密资产             8,938   (−7,307)
```

**闸 1 与闸 4 拦 0 是意料之中** —— 候选池在 Step 1 就被同一套判据筛过。
保留它们是为了让 `eligibility` 表里**四闸判定齐全**，将来若 Step 1 判据改动能立刻显现。

⚠️ **闸 2 必须有第二条**：合约死后 bar 数**不再增长**而阈值固定，于是
`3,912 > 2,160` **永远成立**。实测 `LUNAUSDT`（2022-05-12 停止交易）在单条件下
从 2022-07 起每月都"通过"，会一直留在成员集里贡献同一个冻结的价格。

⚠️ **闸 3 用「最长连续缺失」而不只是覆盖率**：中位最长缺口只有 1h，但
**> 48h 的有 62 段 / 46 个合约，最长 7,573h**。覆盖率看不出这种整段断供。

⚠️ **闸 3 不得用那 4 个衍生字段**（`count_toptrader_*` 等）—— 2022 全年大面积为空，
会误杀整年。必须用 `sum_open_interest` 本身的空值率。

**排名**：`E[E["eligible"] & E["liq"].notna()]` 按当月 `liq` 降序取前 `K=50`。
排名用**当月**流动性是"选择"（谁是本月最好），本来就该用当月数据，不是前视。

**四张产出**：

| 表 | 形状 | 内容 |
|---|---|---|
| `master.parquet` | **285 × 10** | 一币一行的元信息 |
| `universe_eligibility.parquet` | **16,245 × 22** | 每个单元的全部判定，**审计核心** |
| `universe_membership.parquet` | **2,700 × 8** | 成员集 |
| `member_changes.parquet` | **57 × 6** | 一月一行的进出记录 |

```
master 的 10 列：
  symbol base_asset
  first_bar last_bar n_bars n_months last_active     ← 时间跨度
  contract_type underlying_type in_exchange_info      ← 分类元信息
```

```
eligibility 的 22 列：
  symbol month base_asset
  liq bars_before last_active oi_cov oi_max_gap_h oi_null_days obs_days active_days
  g1 g2a live g2 g3a g3b g3 g4 eligible               ← 四闸的逐项判定
  fail_reason rank
```

⚠️ **`master` 不含任何流动性指标** —— 成员集排名用的是 `membership.liq`
（当月每小时 `quote_volume` 的中位）。曾有一列 `median_daily_qv`（全样本期每天成交额的中位），
因全研究无人读取、且与 `liq` 秩相关 0.9916（只多一个量纲差）、又属**回看统计量**
（不能用于筛选），已删除以免被误当作筛选依据。

**成员集 2,700 = 54 月 × 50，涉及 249 个合约。**
54 个月而非 57：`2021-12` / `2022-01` / `2022-02` 成员数为 0 ——
`min_history_bars = 2160` 的预期代价，样本才开跑不到 90 天。

**候选池 285 → 成员 249**：36 个候选池合约一个月的成员都没当过。
从单元格看：16,245 → 2,700（只剩 16.6%）。

### 2.9 Step 6b · QA（缺失报告 + 字典 + 校验和）

**输入**：`features_1h` + `manifest`
**输出**：`04_qa/` 5 个文件 + `REPRODUCE.md`

| 文件 | 行数 | 回答什么 |
|---|---|---|
| `missing_files.parquet` | **67** | 文件层：归档里根本不存在的文件 |
| `gaps.parquet` | **4,880** | 记录层：哪里断了、断多久 |
| `coverage.parquet` | **1,425** | 汇总层：285 × 5 指标 |
| `data_dictionary.md` | — | 逐字段字典 |
| `checksums.sha256` | **1,442** | 产出完整性 |

**缺失分类口径**：

| category | 算真缺失？ |
|---|---|
| `confirmed_404` | ✅ 是（实测 67 条，全部是 `metrics`） |
| `retry_exhausted` | ❌ 不是 —— 是待办 |
| `retry_exhausted` 但文件在缓存里 | ❌ **不算** —— `status` 写坏了 |
| `partial_rows` · `field_empty` · `zero_volume` | ⚠️ 记录 |

⚠️ **Step 6b 必须在最后跑**：校验和是它的最后一个写盘动作，此前写入的每一个文件都被纳入哈希。
重跑 Step 3–6a 会使校验和失效，需重跑 Step 6b 重新生成 —— **且要先重建再 `--verify`**
（`--verify` 只核验、不写文件）。

⚠️ **不检测 `funding_rate`** —— 它只在结算时刻有值（**83.35% 的行天生为 NaN**，
即 6,045,512 行），检查它会产生 600 万个假缺口。
**不检测 `funding_interval_hours`** —— 已前向填充。

**`gaps.parquet` 的构成**（4,880 段）：

| metric | 段数 | 覆盖率中位 | 说明 |
|---|---|---|---|
| `oi_zero` | **2,523** | 0.9997 | 值为 0，**不是缺失**；每段只持续 **1 小时** |
| `index` | 826 | 0.9977 | |
| `oi` | 818 | 0.9997 | 最长一段 **7,573h**（`币安人生USDT`） |
| `mark` | 621 | 0.9981 | |
| `klines` | 92 | 1.0000 | 即 6,886 行补网格（`bar_missing`） |

`gaps.hours` 的分布：中位 **1h**、75 分位 24h、最大 7,573h —— 大部分缺口只持续 1 小时。

---

## 3. 数据质量：不处理就会静默算错的事

### 3.1 九个静默错误

**共同点：它们都不报错，只会让数值悄悄变错。**

| # | 规则 | 不做的后果 |
|---|---|---|
| 1 | **读入后按时间戳排序** | 近期文件非单调（存在负间隔），`shift(1)` 静默算错 |
| 2 | **去重** | `2020-09`~`2021-06` 有完全一致的副本行（576 行 / 288 唯一） |
| 3 | **区分「确认 404」与「超时」** | 网络抖动被误记为缺失，永久漏文件 |
| 4 | **逐文件检测表头有无** | 按日期硬编码必然错 |
| 5 | **URL 段编码，文件路径不编码** | 中文合约名让 `urllib` 抛 `UnicodeEncodeError` |
| 6 | **缓存键必须含源名** | 四个源共用同一键，后到的源命中前一个源的缓存 |
| 7 | **OI 的 `create_time` 秒位必须截断** | 1,147 行 OI 被静默丢成 `oi_missing` |
| 8 | **"没尝试过"不得写成"未取得"** | 1,074 个假缺失污染缺失报告 |
| 9 | **`oi` / `volume` 单位是「币」不是「张」** | Phase 2 误判数量级 |

**规则 3 的两层含义**：① `retry_exhausted` 是**待办**不是缺失，不得进入缺失报告；
② `parse_zip` 的失败**必须抛异常**，不能返回 `None` —— 否则"下载到了但读不懂"会被
打戳 `ok` + 释放缓存，813 个 (合约,月) 被永久记为完成而 `raw/` 里一行都没有。

**规则 5 的反向陷阱**：`quote_seg()` 只用于 **CDN 下载 URL**。S3 列表接口的 `prefix`
必须传**原始合约名**（见 §2.2）。后果不是报错，而是**该合约一个文件都枚举不到、
且不留任何 manifest 记录** —— 实测这样静默丢掉过 1 个候选池合约的全部 mark / index / OI。

**规则 8 的来历**：Step 2 用 `--skip-download` 重算排名时，manifest 的 `status` 初值
会被当终态写进去。实测 18,832 项**全在缓存里**（摘要自报"新下载 0"），manifest 却有
**1,074 行 `retry_exhausted`**，而 `build_qa.py` 把一切非 `ok` 记录当缺失 ——
于是 `missing_files.parquet` 报了 **1,141 个缺失（真值 67）**。
两道修复：① 初值只按"文件在不在"判定，摘要里"未尝试"单列一类；
② `build_qa.py` 自查 —— 状态说"没取得"、文件却在缓存里的行**不算缺失**。

**规则 9 的判据**：`metrics` 同时给了 `sum_open_interest` 与 `sum_open_interest_value`。
`BTCUSDT 2026-06-15 00:00`：`101,604.664 × 65,591.40 = 6,664,392,158` ≈
`value = 6,668,710,356`（差 0.06%，因为 close 是小时收盘）。
另一条独立证据：`klines` 的 `quote_volume / volume == close`（全样本 99.13% 的行成立）。
若 `volume` 是"张"（1 张 = 0.001 BTC），比值应为 59.90 而非 59,900。

### 3.2 下架合约：`klines` 不停，`funding`/`mark`/`index` 会停

合约下架后，归档对 `klines` **继续写「整月零成交空行」到样本末端**，
而 `fundingRate` / `markPrice` / `indexPrice` **直接停止**。

所以有两条处理路径，缺一不可：

| 现象 | 处理 | 在哪一步 |
|---|---|---|
| klines 死尾（零成交空行） | **按 `g1` 裁掉** | Step 5 |
| mark/index 尾部多写 | **左连接到 klines 网格，自然丢弃** | Step 4 |
| OI 孤立残留（`LUNAUSDT` 跨到 2024-06） | 同上 | Step 4 |

### 3.3 表头有无：必须逐文件检测

Binance 归档的 CSV **在部分文件里有表头、部分没有**，且分界不是按日期整齐划分的，
所以必须逐文件检测第一行第一个字段是否数字：

```python
first = lines[0].split(",", 1)[0].strip()
has_header = not first.lstrip("-").replace(".", "").isdigit()
```

无表头时按**列数**匹配三个已知模板（klines 12 列 / funding 3 列 / metrics 8 列），
列数都不匹配就抛 `ParseError` —— 市场级突发事件会让归档里出现**空成员**或列数对不上的残包。

### 3.4 其它已知脏点

| 位置 | 问题 | 处理 |
|---|---|---|
| 个别日期 | 缺失，或 287 行而非 288 | 记入缺失报告 |
| metrics 的 `create_time` | 秒位非 0（4,138 行 / 64 合约） | `floor("h")` 后合并 |
| funding 的 `calc_time` | 毫秒位非 0（`BTCUSDT` 2,240 行） | `floor("s")` |
| `oi = 0` | 2,523 行 / 55 天 / 249 个合约 | 全市场事件，记入缺失报告，**不进闸** |
| 冻结的 `oi` | 仅 1 个合约 > 12h | 记入缺失报告 |
| **整月零成交** | raw **446** 个 (合约,月)；裁死尾后剩 **20** 个 | 剩下的 20 个是**中间段**（合约消失又回来），排名天然排除（`median=0`） |
| `metrics` 不完整的天 | 1,190 个 (合约,天) 非 24 小时（2026 年占 151） | 记入缺失报告 |
| `mark`/`index` 的归档空洞 | `BTCUSDT` 有 4 / 9 处 25h~49h 间隔 | 记入缺失报告 |

**"整月零成交"的两个口径要分清**：raw 里 446 个，其中绝大多数属于**死尾**
（被 Step 5 裁掉）；`features_1h` 里剩下的 20 个才是**中间段**——
`TLMUSDT`（2022-07 ~ 2023-02，9 个月）、`LITUSDT`（2025-02 ~ 11，10 个月）、
`ICPUSDT`（2022-07 ~ 08）。这些合约消失又回来，Phase 2 可按 `quote_volume == 0` 过滤。

### 3.5 一个已知的重复下载（不影响产出）

`klines` 被下载了**两遍** —— Step 2 与 Step 3 的缓存路径规则不同，无法复用：

```
Step 2  data/00_config/_cache/klines/{SYM}/{YM}.zip
Step 3  data/raw/_cache/{src}__{sym}__{period}.zip
```

代价是约 424 MB，占 Step 3 的 5%。可优化（让 Step 3 检查 Step 2 的缓存并搬过来），
但改动会引入新的路径耦合，**暂不做**。

---

## 4. 数据契约与验收

### 4.1 类型与 `validate()`

`lib/schema.py` 是**列契约的唯一权威**，定义 11 张表的列名 / 顺序 / 语义类型 / 主键。

**语义类型只有 4 个**：

| 语义 | pandas dtype | 说明 |
|---|---|---|
| `string` | `"string"` | 不绑 `string[pyarrow]` 后端 |
| `float64` | `float64` | **整数也用 float64** —— `int8/16/32/64` 不支持 NaN |
| `timestamp` | `datetime64[ns, UTC]` | |
| `bool` | `bool` | |

**数据列全部允许 null** —— `funding_rate` 只在结算小时非空是设计要求。
唯一例外：每张表的**标识列**强制非空（`NaT` 在 join 时静默匹配不上，行会无声消失）。

**用它的步骤**：Step 4 和 Step 5 全量使用。Step 0–3、6a、6b 不用
（Step 3 抄了一份列名，是一处技术债）。

`validate()` 的九项检查：列名与**顺序**一致 · dtype 一致 · 标识列非空 · 主键无重复 ·
主键已排序 · 无整列为空 · 标识列落在整小时 · `ts_end − ts == 1h` · 标识列 tz-aware UTC。

**不做**值域与跨列一致性检查 —— 那是统计判断、阈值需标定，属质量巡检而非结构契约。

⚠️ **第 6 项（无整列为空）在单合约子集下要放宽** —— `--subset` 时合法地会有全空列
（如 `TLMUSDT 2022-07`），所以加了 `n_syms > 1` 的条件。

### 4.2 自测与产出完整性

```bash
python config.py            # 8 项：validate_sample_end 行为 + Config frozen
python -m lib.schema        # 65 项：结构自检 + validate 放行/捕获 + schema 关系
```

每个脚本都有 **"拒绝以成功结束"** 的检查：

| 脚本 | 条件 | 退出码 |
|---|---|---|
| `build_layer2.py` | 产出 0 行 / 有合约缺 klines | 4 |
| `build_features.py` | 产出 0 行 / 有候选池合约没进面板 | 4 |
| 六脚本全部 | `--sample-end` 非法 | 2 |

⚠️ 实测踩过：`--raw-root` 指向空目录时，0 个文件、0 行，旧的交叉校验仍打印
"三张网格表一致: 是"并 exit 0 —— **空的第 2 层会被 Step 5/6 继续消费**。

### 4.3 端到端复现

见 §0 的六条命令，或 `data/REPRODUCE.md`（由 Step 6b 生成）。

**Step 4 与 Step 5 是全量重建**（先清旧产出）。`--subset` 加 `--keep-existing`
才是"只处理部分合约"的冒烟模式，此时收尾的交叉校验只对该批次有意义。

**Step 6a 的判据来自快照**，所以离线可复现。要更新判据（新月份 / Binance 新增分类）
才需要联网：

```bash
python phase1/build_universe.py --out-root data --sample-end 2026-08-31 --refresh-exchange-info
```

⚠️ **`exchangeInfo` 快照的时间错配**：本次快照取于 `2026-10-04`，比 `sample_end`
晚 34 天。它含样本期后才上市的合约（不在候选池里，不影响结果），
而样本期内下架的 14 个合约查不到 → 走"兜底放行"（`rec is None` 按加密资产处理）。
这 14 个实测都是加密资产，**当前无误判**。

### 4.4 CLI 参数（全项目 20 个）

| 类别 | 参数 | 出现处 |
|---|---|---|
| 样本窗口 | `--sample-end` | **六个脚本全部必填** |
| 路径 | `--out-root` | **六个脚本全部必填** |
| 路径 | `--raw-root` `--l2-root` `--fe-root` `--pool` | Step 4/5/6a |
| 冒烟 | `--subset` | Step 0–2/3/4/5/6a |
| 冒烟 | `--batch` | Step 4/5（默认 30） |
| 断点 | `--skip-download` | 仅 Step 0–2 |
| 断点 | `--keep-cache` `--list-only` `--jobs` | 仅 Step 3 |
| 断点 | `--keep-existing` | 仅 Step 4 |
| 网络 | `--refresh-exchange-info` `--exchange-info` | 仅 Step 6a |
| 校验 | `--no-validate` | Step 4/5 |
| 校验 | `--no-schema-note` | 仅 Step 6a（跳过 exchangeInfo） |
| 校验 | `--verify` | 仅 Step 6b |

**已删除的过时机制**（照旧文档用会报错）：

| 已删 | 原形态 | 现在用什么 |
|---|---|---|
| `--no-refresh` `--symbols` | 早期文档提到的 CLI | 从未实现 |
| `P11_DATA_ROOT` `P3_DATA_ROOT` | 环境变量 | `--out-root`（必填） |
| `--manifest` | `build_universe.py` 的参数 | 评测范围收窄后不再需要 |
| `master.dropped_reason` | 列 | 读 `eligibility.fail_reason` |
| `master.in_pool` `master.has_data` | 常量列 | 已删 |
| `--refresh` | `build_universe.py` 注释里的写法 | 那是函数参数名，CLI 是 `--refresh-exchange-info` |

---

## 5. 时间与空间

### 5.1 四个优化点（收益都是实测的）

| # | 优化 | 反面写法 | 实测 |
|---|---|---|---|
| 1 | **一遍过：下载即解压** | 先全下到缓存再统一解压 | 磁盘读 2 遍 → **1 遍**；中断损失 60 min → **< 1 min** |
| 2 | **按合约预分组** | 每个合约重读/全表扫描一遍 | Step 4 读 metrics **289s → < 2s**；Step 6a 建 master **310s → 48s** |
| 3 | **单遍读盘 + 原子写** | 循环里反复 `read_parquet` | 每个 chunk 先写 `.part`（名字带 PID）再 `os.replace` |
| 4 | **逐合约建、按批落盘** | 全攒到最后 / 每个合约都读回重写 | 内存峰值 ≈ 30 个合约；避免 285 × 57 次读写 |

**判据：只要出现"对每个合约扫一遍全表"，就一定会慢一个数量级。**

### 5.2 下载参数

| 参数 | 值 | 依据 |
|---|---|---|
| 并发 | **32** | 实测 16 → 32 吞吐已饱和 |
| 读取超时 | **45 s** | 实测极端长尾 45.8 s |
| 重试次数 | **3** | 只重试网络类失败 |
| 退避 | `2^attempt` 秒 + 0–1 s 抖动 | 抖动必需 —— 并发同时失败会成尖峰 |
| 在途上限 | `CONCURRENCY × 8 = 256` | 保持内存有界（Step 3） |

### 5.3 两个缓存，性质不同

| 缓存 | 由谁产生 | 大小 | 会自动清吗 |
|---|---|---|---|
| `data/raw/_cache/` | Step 3 | 跑完 **0 字节** | ✅ `stamp()` 里 `drop_cache()`，落盘即释放 |
| `data/00_config/_cache/klines/` | Step 0–2 | **527.7 MB / 18,874 zip** | ❌ 不会，没有释放逻辑 |

第二个是 Step 2 为算流动性而下的月频 klines：

- **只被 `build_candidate_pool.py` 读写**，其余五个步骤都不碰
- **删掉不影响任何产出**：候选池 285 个全在 `data/raw/klines/`；也不进 `checksums.sha256`
- **但删了要付代价**：下次重跑 Step 0–2 会重下 18,832 个文件（约 5 分钟，需 VPN）
- 里面有 **392 个落选合约**的 klines，改 `K` / 延长窗口重算时还要用

**建议留着** —— 它不参与校验和、不影响交付，唯一作用是省重跑时间。

---

## 6. `manifest.parquet`：归档层的逐文件账本

**写入（2 处）**：

| 步骤 | 写什么 | 行数 |
|---|---|---|
| Step 2 | `source=klines, granularity=monthly` | **18,832** |
| Step 3 | 另外 4 个源 + `metrics` | **336,978** |
| | 合计 | **355,810** |

**读取（3 处）**：

| 谁 | 用来做什么 |
|---|---|
| Step 2 | 读-改-写时保留其他源的记录 |
| **Step 3** | **断点续传** —— `raw_written_at` 有戳就跳过 |
| **Step 6b** | **缺失报告** —— `status != "ok"` |

（Step 6a 曾用它确定评测范围，收窄为候选池后已不需要。）

**10 列**：`source` `symbol` `period` `granularity` `remote_path` `filename`
`status` `bytes` `downloaded_at` `raw_written_at`

两边都是**读-改-写**：各自只替换自己那些键，另一个源的行原样保留。

⚠️ **`raw_written_at` 的语义是"解压后的数据真的落进 `raw/` 了吗"** ——
所以 Step 2 写的 18,832 行这一列**全是空**（它只下 zip 到缓存，解压是 Step 3 做的）。
判断 klines 是否成功要看 `status` 列。

⚠️ **Step 3 的跳过条件有两个，理由不同**：`raw_written_at` 有戳 = "做完了"；
`confirmed_404` = "确认归档里没有"。混为一谈会永久漏文件。

⚠️ **manifest 中途就会落盘**（每 2,000 个文件一次）—— 否则 SIGKILL / 断电会丢掉
全部进度戳，而缓存早已删除，下次要把几十万个文件重下。

### 6.1 为什么要落"设计参数快照"

**问题**：`checksums.sha256` 只覆盖 `data/` 下的文件，**不覆盖 `config.py`**（它在项目根）。
所以如果 `config.py` 被改过，就没有任何产出能说明"这份 D1 是用哪套参数跑的"。

**做法**：`build_qa.py` 把 `cfg.snapshot()`（9 个设计参数）写进 **`data/REPRODUCE.md`** 的
「本次产出用的设计参数」一节。

⚠️ **它只记参数值，不记代码版本** —— 若只是计算逻辑改了而参数未变，
这份快照看不出差别，那要靠 git 历史。

**历史说明**：这些元信息原先由 `data/00_config/sample_end.json` 记录（21 个键，
六个脚本各写一部分）。该文件已删除，理由是：

- **纯"只写不读"** —— 代码里没有任何一处读取它的值做决策，6 处读取全是为了
  读-改-写自保（不覆盖别的步骤的键）。读者始终是人，不是代码。
- **部分键不可信** —— `status_counts` / `files_per_source` / `files_total` 是
  一次失败的 Step 3 运行留下的，与 manifest 的真实状态矛盾。
- **命名不一致** —— Step 3/4 用扁平键 + `step` 字符串，Step 5/6a/6b 用嵌套字典键。
- 它承载的信息，绝大部分可从产出本身重建（各表行数、`04_qa/` 各文件行数、manifest 的状态分布）。
  唯一不可替代的 `config_snapshot` 已移入 `REPRODUCE.md`。

---

## 7. 关键决策与预设问题

### 7.1 为什么样本从 `2021-12-01` 开始

**不是权衡结果，是被数据唯一定死的。**

```
OI 归档的断崖：实测 103 个合约从 2021-12 才有 OI
2021-11 及之前：OI 只有零星几个合约，无法构造 regime
```

同理 `sample_end = 2026-08-31` 是当前可用的最后完整月（归档在次月 1–2 日才发布）。

### 7.2 关键取舍

| 决策 | 取 | 舍 | 理由 |
|---|---|---|---|
| 流动性窗口 | 月初前 30 天**严格开区间** | 含当月 | 含当月就是前视 |
| 成员刷新 | **月度** | 日度 | OI 归档是月频，日度重算无新信息 |
| 流动性闸 | **不设闸，靠排名** | 设绝对阈值 | note 的 "Top 30–50 liquid" 由排名承担 |
| 排名指标 | `median(quote_volume)` | `mean` / `sum` | 单小时能被拉高 15 倍；`sum` 对上市时长敏感 |
| 缺失表示 | `NaN` + 标记列 | 填充 | 填充等于发明数据 |
| `ts_end` 语义 | 区间终点 = OI 对齐时刻 = **决策时刻** | bar 起点 | 让 OI 与 close 的变化区间重合 |
| funding 周期 | 保留 `funding_interval_hours` | 硬编码 8h | 142 个合约是 4h，91 个中途改过 |
| 派生量 | **全部推到 Phase 2** | 在数据层算 | 改一次参数不必重跑数据层 |
| 评测范围 | 候选池 285 | 全部归档 677 | 精筛只管"池内谁能当成员" |

### 7.3 预设问题

**Q：为什么 Step 2 的候选池是 285，而 Step 6a 的成员只有 249 个合约？**
A：285 是**并集**（57 个月各自 top-50 的累积，只过草稿闸）；249 是**真正当过成员**的
（过完四条正式闸 + 排进前 50）。36 个候选池合约一个月的成员都没当过。

**Q：为什么 `universe_membership` 是 54 个月而不是 57？**
A：`2021-12` / `2022-01` / `2022-02` 三个月成员数为 0 —— `min_history_bars = 2160`
（90 天）的预期代价，样本才开跑不到 90 天。

**Q：为什么 `oi` 对齐到 `ts_end` 而不是 `ts`？**
A：`oi` 是**时刻量**（那一刻还挂着多少仓位），其它都是**区间量**。
对齐到 `ts_end` 让 `oi` 的变化区间与同一行 `close` 的变化区间**完全重合** ——
这是 Phase 2 能算"价格与持仓同步变动"的前提。`ts_end` 就是决策时刻。

**Q：为什么 `funding_rate` 不填充，而 `funding_interval_hours` 要填充？**
A：前者是**事件**（"这一期收了多少钱"），填了就是发明数据；后者是**状态**
（"当前规则是什么"），它本来就每时每刻成立。前者非空率 16.65%、后者 99.65%。

**Q：`bar_missing` 和 `oi_missing` 有什么区别？**
A：`bar_missing` = 密集化补出来的行（该小时在 `klines_1h` 里没有）；
`oi_missing` = `bar_missing` **或** 该小时无 OI 快照。
实测 `bar_missing` 6,886 ⊂ `oi_missing` 32,514，差的 25,628 行是
"bar 有、币安没发 OI 快照"（真缺失）。所以只有 `oi_missing` 被用作闸 3 的输入。

**Q：为什么闸 1 和闸 4 拦 0 还要保留？**
A：候选池在 Step 1 就被同一套判据筛过。保留是为了让 `eligibility` 表里
**四闸判定齐全**（6 个布尔列逐行有值），将来若 Step 1 判据改动能立刻显现。

**Q：`PAXGUSDT` / `XAUTUSDT` 是代币化黄金，为什么放行？**
A：Binance 标它们 `PERPETUAL/COIN`。它们是**链上发行的加密原生合约**
（24/7、无收盘时段），结构上与加密永续无区别。反之代币化股票有交易时段，
闭市时 OI 与资金费率的语义会变。

**Q：`exchangeInfo` 查不到的合约怎么办？**
A：按**加密资产**放行。它们是已下架的合约（`exchangeInfo` 只含当前挂牌），
而池里的非加密标的都是近年才上的，不会出现在下架名单里。实测候选池 285 个里有 14 个查不到，
全部是加密资产。代价是：若某个代币化股票在样本期内下架，会被误放行。

---

## 8. 已知缺口与增量更新规划

**当前 D1 是一次性全量构建，以下都未实现。**

### 8.1 `confirmed_404` 需要 TTL 重探

月频文件在**次月 1–2 日才发布，且并非每月都齐**，永久缓存 404 会**永久漏掉**该文件。
现状：67 条 `confirmed_404` 里有 **32 条带 `raw_written_at` 戳**，
而续传逻辑把"有戳"当已完成 → 这 32 条**永久跳过**。
**换月增量前必须补 TTL。**

### 8.2 增量 `features_1h` 需要 upsert

正确做法是"读现有 chunk → 合并 → 按主键去重 → 原子写回"；
现状每次重建 57 个 chunk（357s）。**正确性没问题，代价是时间。**

### 8.3 chunk 的 frozen / hot 划分

| 状态 | 哪些 | 行为 | 不变量 |
|---|---|---|---|
| **frozen** | 除最后 1 个外全部 | 写完不改 | 行数按 `(chunk, symbol)` 固定 |
| **hot** | `sample_end` 所在月 | 每次追加 | 行数单调增 |

⚠️ 新上市合约首月不满整月 —— **行数不变量按 `(chunk, symbol)` 判定，不按 chunk 总行数。**

### 8.4 数据源优先级：月频 ≡ 日频拼接

```
该月的【月频文件】在 manifest 中 status = ok  →  用月频
否则                                        →  用日频补
两者都没有                                   →  该时间戳不存在
```

因**月频 = 日频拼接（逐值完全相同）**，两者可自由混用，**增量不必等月份结束**。

**发布节奏（`Last-Modified` 实测）**：

| 源 | 发布时刻 |
|---|---|
| 日频 `metrics` | 每天 06:39 GMT |
| 日频 klines / mark / index | 每天 08:00–08:34 GMT |
| 月频 `fundingRate` | 次月 1 日 08:24 GMT |
| 月频 klines / mark / index | 次月 2 日 09:00–12:00 GMT |

→ **刷新的合适时点：每天 UTC 09:00 之后。**

### 8.5 增量流程

```
【A】更新合约清单（需 VPN）→【B】定该有哪些文件 →【C】与 manifest 对账
【D】下载缺失的 →【E】重建第 2 层 →【F】重建 features_1h →【G】重建 universe → 重跑 Step 6b
```

**`sample_end` 只决定裁剪边界，不决定数据来源。**

### 8.6 第 2 层的构建顺序是硬性要求

增量时 `layer2_built_at` 是**单一时间戳**，必须**最后写、且失败时不写**。
否则 `mark` 成功而 `index` 失败时，该文件会被标记为「已建」，
**`index` 的数据永久丢失且不报错**。（该戳本身尚未实现，留到真正做增量时再加。）
