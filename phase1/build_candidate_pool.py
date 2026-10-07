#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_candidate_pool —— 选出「后面要为哪些合约下数据」

它在 Phase 1 中的位置：Step 0–2（枚举归档 / 硬过滤 / 候选池）。

做什么
------
  1. 枚举归档（S3 列表接口）→ 全部存在过的 USDT 永续合约
  2. 硬过滤 → 剔非 USDT 本位、名称怪象、稳定币、非加密资产（股票/ETF/商品/外汇）
  3. 拉月频 klines（只为读 quote_volume）→ 过草稿闸 → 逐月算流动性排名
     → 取各月前 K → 并集 = 候选池

为什么需要它
------------
Phase 1 最终要为候选池合约下「日频 OI + mark/index/funding」，实测 336,650 个文件。
不先筛一遍就会对全部 679 个合约下，绝大部分是浪费。
本脚本用几分钟的轻量下载，换掉后面大部分浪费。

产出
----
  data/00_config/archive_contracts.csv     Step 0 的归档清单（逐合约一行 + 分类）
  data/03_reference/candidate_pool.csv     候选池名单（一列 symbol）
  data/00_config/manifest.parquet          逐文件下载状态，供断点续传

不产出 master.parquet —— 它是 D1 产出，且要等 Step 3 下载完才有内容。

用法
----
  python phase1/build_candidate_pool.py --out-root data --sample-end 2026-08-31
  # 只用缓存重算排名：
  python phase1/build_candidate_pool.py --out-root data --sample-end 2026-08-31 --skip-download
  # 冒烟/核验：
  python phase1/build_candidate_pool.py --out-root /tmp/x --sample-end 2026-08-31 --subset A B C

设计参数（四条闸与排名）见 config.py 的 docstring；下载参数见本文件顶部的常量。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根：config.py / lib/
import config as cfg_mod                                     # noqa: E402

# 注：本脚本不调用 lib.schema.validate() —— 它只从 klines 里读 quote_volume，
# 不构造任何齐备的 DataFrame。schema 契约从 Step 4（建第 2 层表）起强制。

# ============================================================================
# 常量（下载参数）
# ============================================================================

S3_API = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CDN = "https://data.binance.vision"

CONCURRENCY = 32          # 实测 16→32 吞吐已饱和
READ_TIMEOUT = 45         # s；实测 max=45.8s 是极端长尾
RETRIES = 3               # 合计最多 3 次尝试
BACKOFF_BASE = 2          # 2^attempt 秒

# 本脚本在 phase1/ 下，项目根是上一级
ROOT = Path(__file__).resolve().parent.parent
# 产出根目录：由 --out-root 显式指定（configure_paths() 里解析）。
# 原为环境变量 P11_DATA_ROOT —— 已删除：环境变量不跨 shell 保留，
# 曾因此把冒烟结果写进正式目录。
DATA = ROOT / "data"
# 月频 klines 的原始 zip 暂存 —— 断点续传靠它。
# 名字原为 `_p11_cache`：p11 是脚本改名前的旧前缀，与本流程无关，故改为 `_cache`
# （与 Step 3 的 `data/raw/_cache` 同名同义：都是"读一次就丢"的下载暂存）。
# 放在 00_config/ 下是因为它不能落在校验和扫描的子目录里（见
# build_deliverables.py 的 checksum_targets()）。
CACHE_DIR = DATA / "00_config" / "_cache"
MANIFEST = DATA / "00_config" / "manifest.parquet"
CANDIDATE_POOL = DATA / "03_reference" / "candidate_pool.csv"
ARCHIVE = DATA / "00_config" / "archive_contracts.csv"    # Step 0 的产出
DROPPED = DATA / "00_config" / "dropped_contracts.csv"    # Step 1 的产出（剔除明细）
KEPT = DATA / "00_config" / "kept_contracts.csv"          # Step 1 的产出（通过名单）


def configure_paths(out_root: Path) -> None:
    """按 --out-root 定全部产出路径。必须在 main() 最开头调用。

    改动最小的等价替换：原来交给环境变量的那层目录，现在交给命令行参数，
    产出布局一字不变（CACHE_DIR / MANIFEST / CANDIDATE_POOL / 三个 Step 1
    产出 全都跟着根目录走）。
    """
    global DATA, CACHE_DIR, MANIFEST, CANDIDATE_POOL, ARCHIVE, DROPPED, KEPT
    DATA = out_root.resolve()
    CACHE_DIR = DATA / "00_config" / "_cache"
    MANIFEST = DATA / "00_config" / "manifest.parquet"
    CANDIDATE_POOL = DATA / "03_reference" / "candidate_pool.csv"
    ARCHIVE = DATA / "00_config" / "archive_contracts.csv"
    DROPPED = DATA / "00_config" / "dropped_contracts.csv"
    KEPT = DATA / "00_config" / "kept_contracts.csv"

# 闸 4 的判据：只有 exchangeInfo 的分类字段，不设手工名单。
#
#     contractType    PERPETUAL（加密）   vs  TRADIFI_PERPETUAL（传统金融）
#     underlyingType  COIN（加密）        vs  EQUITY / HK_EQUITY / KR_EQUITY /
#                                            CN_EQUITY / COMMODITY / PREMARKET /
#                                            FX / INDEX
#     通过 ⇔ contractType == "PERPETUAL" 且 underlyingType == "COIN"
#
# 为什么不用手工名单：首版列了 35 个，漏进 21 个代币化标的；补齐后仍漏
# GOOGLUSDT / SPYUSDT / NBISUSDT，另漏 25 个当时不在池里的。结构性缺陷是
# 【池子按排名滚动，新标的随时进池】—— 每轮都要人工重核，必然出错。
#
# 该判据同时排掉 PERPETUAL/INDEX 的合成指数永续（DEFIUSDT / BTCDOMUSDT /
# ALLUSDT）—— 合成品，不是单一资产。
#
# 故意的例外：PAXGUSDT / XAUTUSDT 被标成 PERPETUAL/COIN，按此判据放行。
# 它们是链上发行的加密原生合约（24/7、无收盘时段），结构上与加密永续无区别。
#
# ⚠️ 局限：exchangeInfo 只含【当前挂牌】的合约，已下架的查不到。
#    实测池里查不到的合约全部是加密资产，故不另设名单；若将来发现查不到的
#    里面有非加密资产，在这里补一个 {symbol} 集合。



# ============================================================================
# 小工具
# ============================================================================

def log(msg: str) -> None:
    print(msg, flush=True)


def month_list(start: str, end: str) -> list[str]:
    """['2021-12', ..., '2026-08']，闭区间。"""
    y0, m0 = map(int, start.split("-"))
    y1, m1 = map(int, end.split("-"))
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def http(url: str, *, method: str = "GET") -> bytes:
    """带重试与退避的请求。失败抛最后一次异常（由调用方分类）。

    ⚠️ 只重试【网络类】失败。编程错误（未编码的 URL、非法参数）必须立刻炸，
    不许被 `except Exception` 吞成"重试耗尽"。归档里有中文名合约
    （`币安人生USDT` 等），URL 中未编码的非 ASCII 字符会抛
    UnicodeEncodeError —— 曾因此把 19 个真实存在的文件静默丢成失败。
    """
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "theo-phase1/1.0"})
            with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as r:
                return r.read() if method == "GET" else b""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise                       # 确定的答案，不重试
            last = e
        except (UnicodeEncodeError, UnicodeDecodeError, ValueError) as e:
            # 不可重试：重试只会把编程错误伪装成网络抖动
            raise RuntimeError(f"URL 不可用（非网络问题，不重试）：{url!r} -> {e}") from e
        except Exception as e:              # noqa: BLE001  网络类，可重试
            last = e
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF_BASE ** attempt + random.random())
    assert last is not None
    raise last


def quote_seg(seg: str) -> str:
    """把路径段编码进 URL。

    普通合约名原样返回（可读性 + 与既有 manifest 一致）；
    中文名等非 ASCII 必须编码（`币安人生USDT` -> `%E5%B8%81...`）。
    """
    try:
        seg.encode("ascii")
    except UnicodeEncodeError:
        return urllib.parse.quote(seg, safe="")
    return seg


def monthly_klines_path(sym: str, ym: str) -> str:
    """月频 klines 的 URL 路径。所有 URL 构造必须走这里。"""
    q = quote_seg(sym)
    return f"/data/futures/um/monthly/klines/{q}/1h/{q}-1h-{ym}.zip"


# ============================================================================
# Step 0 —— 枚举归档
# ============================================================================

def s3_list(prefix: str, delimiter: str | None = "/") -> list[str]:
    """S3 列表（自动翻页）。返回全部 <Key> 与 <Prefix>。"""
    out: list[str] = []
    token: str | None = None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if delimiter:
            q["delimiter"] = delimiter
        if token:
            q["continuation-token"] = token
        body = http(f"{S3_API}?{urllib.parse.urlencode(q)}").decode("utf-8", "replace")
        out += re.findall(r"<Key>(.*?)</Key>", body)
        out += [p for p in re.findall(r"<Prefix>(.*?)</Prefix>", body) if p != prefix]
        trunc = re.findall(r"<IsTruncated>(.*?)</IsTruncated>", body)
        if not (trunc and trunc[0] == "true"):
            return out
        nxt = re.findall(r"<NextContinuationToken>(.*?)</NextContinuationToken>", body)
        if not nxt:
            return out
        token = nxt[0]


def enumerate_archive() -> tuple[set[str], set[str], dict]:
    """返回 (归档里的全部合约名, 其中 USDT 本位的, exchangeInfo 元信息)。"""
    log("Step 0  枚举归档（S3 列表接口）…")
    t0 = time.time()
    names = s3_list("data/futures/um/daily/klines/", delimiter="/")
    syms = {n.rstrip("/").split("/")[-1] for n in names if n.rstrip("/").split("/")[-1]}
    log(f"        归档合约总数 {len(syms)}   耗时 {time.time()-t0:.1f}s")

    # exchangeInfo：只为拿 base/quote/underlyingType 等元信息，不用它当合约清单
    # ⚠️ 这里【不过滤】contractType —— 闸 4 需要看 TRADIFI_PERPETUAL 才能排除它
    ex_url = "https://www.binance.com/fapi/v1/exchangeInfo"
    info = {s["symbol"]: s for s in json.loads(http(ex_url))["symbols"]}
    log(f"        exchangeInfo 元信息 {len(info)} 条")

    usdt = {s for s in syms if s.endswith("USDT")}
    log(f"        以 USDT 结尾 {len(usdt)}   非 USDT 结尾 {len(syms)-len(usdt)}")
    return syms, usdt, info


def persist_archive(syms: set[str], info: dict) -> Path:
    """把归档枚举结果落盘 —— Step 0 的产出必须持久化。

    为什么必须有这个文件（而不是只打日志）：
      枚举结果曾经在不同运行之间不一致 —— 实测一次 893、一次 1,057，差 164 个。
      所以"归档里有几个合约"这个数本身就可能是一次不完整枚举的结果。
      不落盘就无法对账，也无从判断某次运行是不是漏了合约。
      （2026-10-04 连跑 3 次均为 1,057，当前稳定；但那两次不一致发生过，
        且合约数只增不减，所以落盘这件事不能省。）

    同时记录【非 USDT 结尾】的合约，它们是 Step 1 第一条判据的剔除对象 ——
    只存 USDT 结尾的话，这条判据的剔除数就永远算不出来。
    """
    rows = []
    for s in sorted(syms):
        rec = info.get(s, {})
        rows.append({
            "symbol": s,
            "is_usdt": s.endswith("USDT"),
            "contract_type": rec.get("contractType") or "",
            "underlying_type": rec.get("underlyingType") or "",
            "base_asset": rec.get("baseAsset") or "",
            "quote_asset": rec.get("quoteAsset") or "",
            # 查不到 = 已下架（exchangeInfo 只含当前挂牌）
            "in_exchange_info": bool(rec),
        })
    df = pd.DataFrame(rows)
    tmp = ARCHIVE.with_name(f"{ARCHIVE.name}.{os.getpid()}.part")
    df.to_csv(tmp, index=False)
    os.replace(tmp, ARCHIVE)
    return ARCHIVE


def hard_filter(usdt: set[str], info: dict, cfg: cfg_mod.Config,
                subset: list[str] | None = None) -> tuple[list[str], dict]:
    """Step 1 —— 硬过滤。返回 (通过硬过滤的合约, 剔除原因)。

    subset 非空时只处理这些合约（冒烟测试用）。
    """
    log("Step 1  硬过滤…")
    kept, dropped = [], {}

    def drop(s: str, why: str) -> None:
        dropped.setdefault(why, []).append(s)

    pool = sorted(set(usdt) & set(subset)) if subset else sorted(usdt)
    for s in pool:
        rec = info.get(s, {})
        base = rec.get("baseAsset") or ""
        quote = rec.get("quoteAsset") or ""
        # 过滤：非 USDT 本位（USDC / BUSD）
        # ⚠️ 实测 0 命中：本函数的输入已经是 endswith("USDT") 的集合，
        #    其 quoteAsset 必为 USDT。保留作为防御（枚举路径若改动则生效）。
        if quote and quote != "USDT":
            drop(s, f"非 USDT 本位（{quote}）")
            continue
        # 过滤：名称怪象（交割合约、SETTLED 后缀）
        # ⚠️ 实测 0 命中 —— 别被它误导。归档里确实有 70 个这种名字
        #    （BTCUSDT_210326 等交割合约 53 个、AERGOUSDTSETTLED 等 17 个），
        #    但它们【都不以 USDT 结尾】，在 enumerate_archive 那一步
        #    就被 endswith("USDT") 滤掉了，压根没进这个函数。
        #    保留作为防御：若将来改去枚举 delivery/ 段，这条会生效。
        if "_" in s or "SETTLED" in s:
            drop(s, "交割合约/SETTLED 后缀")
            continue
        # 过滤：稳定币（按 base_asset，不按符号字面）
        #      —— 对应资格闸 1，只是提前在 Step 1 做掉
        if base and base in cfg.stablecoin_bases:
            drop(s, "稳定币")
            continue
        # 过滤：非加密资产 —— 对应资格闸 4，判据只有分类字段
        #      （理由与例外见文件头）
        if rec:
            ct = rec.get("contractType")
            ut = rec.get("underlyingType")
            if ct != "PERPETUAL" or ut != "COIN":
                drop(s, f"非加密资产（{ct}/{ut}）")
                continue
        kept.append(s)

    for why, ss in sorted(dropped.items(), key=lambda kv: -len(kv[1])):
        log(f"        剔除 {len(ss):4d}  {why}")
    log(f"        保留 {len(kept)}")
    return kept, dropped


def persist_dropped(dropped: dict, kept: list, cfg: cfg_mod.Config) -> tuple:
    """把 Step 1 的【两个输出】都落盘 —— 它们必须可独立审计。

    原来只落了计数（sample_end.json 的 eligible_after_hard_filter），
    两个名单都只打日志。后果："USDCUSDT 是在哪一步被剔的"、
    "通过硬过滤的 683 个到底是谁" 都事后无法回答，只能重跑重现 ——
    而重跑依赖 exchangeInfo 与归档两个外部状态，未必能复现同一结果。

    ⚠️ 通过名单也不能省：master.parquet 是它的【真子集】
    （677 ⊂ 683，差的 6 个是通过硬过滤但归档里没有 klines 的合约），
    所以从下游反推不出完整的通过名单。
    """
    out = []
    # ---- 1. 通过的名单 ----
    if kept:
        kdf = pd.DataFrame({"symbol": sorted(kept)})
        kdf["base_asset"] = [s[:-4] if s.endswith("USDT") else s
                             for s in kdf["symbol"]]
        tmp = KEPT.with_name(f"{KEPT.name}.{os.getpid()}.part")
        kdf.to_csv(tmp, index=False)
        os.replace(tmp, KEPT)
        out.append(KEPT)
    # ---- 2. 被剔除的明细 ----
    rows = []
    for why, ss in sorted(dropped.items()):
        for s in sorted(ss):
            base = s[:-4] if s.endswith("USDT") else s
            rows.append({
                "symbol": s,
                "base_asset": base,
                "reason": why,
                "is_stablecoin": base in cfg.stablecoin_bases,
            })
    if rows:
        df = pd.DataFrame(rows).sort_values(["reason", "symbol"], ignore_index=True)
        tmp = DROPPED.with_name(f"{DROPPED.name}.{os.getpid()}.part")
        df.to_csv(tmp, index=False)
        os.replace(tmp, DROPPED)
        out.append(DROPPED)
    return tuple(out)


# ============================================================================
# 可用月份（S3 列表一次拿全，不需要逐月探测）
# ============================================================================

_MONTH_RE = re.compile(r"-1h-(\d{4})-(\d{2})\.zip$")


def available_months(sym: str) -> list[str] | None:
    """该合约在归档里有哪几个月频 klines。None = 列目录失败。

    注意：必须【逐项】匹配，不能把 key 列表 join 成一个字符串——
    那样 `\\.zip$` 会被后继内容破坏，永远匹配不到行尾。
    """
    for attempt in range(RETRIES):
        try:
            keys = s3_list(f"data/futures/um/monthly/klines/{sym}/1h/", delimiter=None)
            out: set[str] = set()
            for k in keys:
                m = _MONTH_RE.search(k)
                if m:
                    out.add(f"{m.group(1)}-{m.group(2)}")
            return sorted(out)
        except Exception:                    # noqa: BLE001
            if attempt == RETRIES - 1:
                return None
            time.sleep(BACKOFF_BASE ** attempt + random.random())
    return None


# ============================================================================
# Step 2 —— 下载 + 排名
# ============================================================================

def cache_path(sym: str, ym: str) -> Path:
    return CACHE_DIR / "klines" / sym / f"{ym}.zip"


def download_one(sym: str, ym: str) -> tuple[str, str, str]:
    """下载一个文件到缓存。返回 (sym, ym, status)。

    status: 'cached'（本地已有）/ 'ok' / 'confirmed_404'（确定不存在）
            / 'retry_exhausted'（网络问题，**不等于缺失**）
    """
    p = cache_path(sym, ym)
    if p.exists():
        return sym, ym, "cached"
    url = CDN + monthly_klines_path(sym, ym)
    try:
        data = http(url)
    except urllib.error.HTTPError as e:
        return sym, ym, ("confirmed_404" if e.code == 404 else "retry_exhausted")
    except RuntimeError:                     # URL 编码等编程错误 —— 直接炸
        raise
    except Exception:                        # noqa: BLE001  网络类
        return sym, ym, "retry_exhausted"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".zip.part")
    tmp.write_bytes(data)
    os.replace(tmp, p)                       # 原子写
    return sym, ym, "ok"


def read_quote_volumes(sym: str, ym: str) -> list[float] | None:
    """读缓存 zip，返回该月各小时的 quote_volume。None = 读不了。"""
    p = cache_path(sym, ym)
    try:
        z = zipfile.ZipFile(p)
        body = z.read(z.namelist()[0]).decode()
    except Exception:                        # noqa: BLE001
        return None
    lines = body.strip().split("\n")
    if not lines:
        return None
    # 表头有无必须【逐文件检测】，不可按日期硬编码
    first = lines[0].split(",", 1)[0].strip()
    rows = lines[1:] if not first.lstrip("-").replace(".", "").isdigit() else lines
    out = []
    for ln in rows:
        f = ln.split(",")
        if len(f) < 12:
            continue
        try:
            out.append(float(f[7]))          # 第 8 列 = quote_volume
        except ValueError:
            pass
    return out or None


def build_monthly_stats(sym: str, months: list[str]) -> tuple[dict[str, float], dict[str, int]]:
    """逐月算 (中位小时报价成交额, 有效小时数)。"""
    liq: dict[str, float] = {}
    bars: dict[str, int] = {}
    for ym in months:
        v = read_quote_volumes(sym, ym)
        if v:
            liq[ym] = statistics.median(v)
            bars[ym] = len(v)
    return liq, bars


# ============================================================================
# 草稿闸（本脚本能做的一条）—— 其余需要 OI 数据，归 Step 3 / Step 6
#
# 排名是「对通过资格闸的合约排名」。本脚本只有 klines，所以只能做：
#   草稿闸（对应闸 2 的存在性）：上一个月有效小时数 >= 24*15
#
# 【故意宽松】（宁可多留）：本脚本是粗筛，过严会误杀合法样本；
# 过宽的代价只是 Step 3 多下一批，而 Step 6 会用完整四条闸再筛一次。
# 闸 3（OI 可靠性）与闸 4（代币化资产，已在 Step 1 处理）不在此。
#
# 原设计有第二条「草稿闸 A：到该月初为止窗口内已有 >= 1 个月数据」，
# 实测【拦不到任何东西】，已删除 —— 合约的数据月份天然连续，
# 上月有 bar 就意味着之前也有，闸 A 恒被闸 B 蕴含：
#   只有闸 A 挡下: 0 个 (合约,月)
#   只有闸 B 挡下: 290 个
#   两个都挡:      677 个（全在 2021-12，样本首月无历史）
# 删除后逐 (合约,月) 判定与逐月成员集【完全一致】（0 处差异，候选池仍 285）。
# 连 3 个「上月在册但 bar<360 且更早有数据」的边界合约（ICPUSDT 2022-10 仅 94 bar、
# BNXUSDT 2023-03 仅 154、TLMUSDT 2023-04 仅 36）也全部由闸 B 挡下。
# ============================================================================

DRAFT_MIN_BARS_IN_PREV_MONTH = 24 * 15  # = 360 小时，只要上个月还活着就放行


def draft_gate_ok(bars: dict[str, int], months: list[str], i: int) -> bool:
    """草稿闸。只用到第 i 个月【之前】的数据 —— 无前视。

    `i < 1` 是必须的：样本首月没有"上一个月"可比。
    `bars.get(prev, 0)` 的默认值处理两种"上月不存在"：
    合约尚未上市、合约已停止交易（归档里仍有文件但 bar 为 0）。
    """
    if i < 1:
        return False
    prev = months[i - 1]                       # 只看上月
    return bars.get(prev, 0) >= DRAFT_MIN_BARS_IN_PREV_MONTH


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="选出候选池合约名单")
    ap.add_argument("--out-root", required=True,
                    help="产出根目录（必填；与 Step 4–6b 同名同义）")
    ap.add_argument("--sample-end", required=True,
                    help="样本截止日，必须为月末日（如 2026-08-31）")
    ap.add_argument("--skip-download", action="store_true",
                    help="只用已有缓存重算排名，不发起下载")
    ap.add_argument("--subset", nargs="+", metavar="SYM",
                    help="只处理这些合约（冒烟测试用；正式运行不要传）")
    args = ap.parse_args()

    configure_paths(Path(args.out_root))                  # 路径定死在最前面
    cfg = cfg_mod.CONFIG
    cfg_mod.validate_sample_end(args.sample_end)          # 失败抛 ConfigViolation
    all_months = month_list(cfg.sample_start[:7], args.sample_end[:7])
    smoke = bool(args.subset)
    log("=" * 74)
    log(f"build_candidate_pool   sample_end={args.sample_end}   "
        f"窗口 {all_months[0]} .. {all_months[-1]}（{len(all_months)} 个月）"
        + ("   [冒烟模式：subset]" if smoke else ""))
    log(f"数据根目录: {DATA}")
    log("=" * 74)

    for d in (CACHE_DIR / "klines", CANDIDATE_POOL.parent):
        d.mkdir(parents=True, exist_ok=True)

    t_start = time.time()

    # ---- Step 0/1 ----
    syms, usdt, info = enumerate_archive()
    # Step 0 的产出落盘：归档清单是"契约总数"的唯一凭据，
    # 只打日志就无从对账（枚举结果曾一次 893、一次 1,057）
    ap_path = persist_archive(syms, info)
    log(f"        归档清单已落盘 {ap_path.name}（{len(syms)} 行）")
    kept, dropped = hard_filter(usdt, info, cfg, subset=args.subset)
    for p_ in persist_dropped(dropped, kept, cfg):
        n_ = sum(1 for _ in p_.open(encoding="utf-8")) - 1
        log(f"        Step 1 产出已落盘 {p_.name}（{n_} 行）")

    # ---- 可用月份（S3 列表，一次拿全）----
    log(f"\n列各合约的可用月份（{len(kept)} 个合约）…")
    t0 = time.time()
    avail: dict[str, list[str]] = {}
    failed_list: list[str] = []
    with ThreadPoolExecutor(CONCURRENCY) as ex:
        futs = {ex.submit(available_months, s): s for s in kept}
        for i, f in enumerate(as_completed(futs), 1):
            s = futs[f]
            m = f.result()
            if m is None:
                failed_list.append(s)
            else:
                # 只保留样本窗口内的月份
                ms = [x for x in m if all_months[0] <= x <= all_months[-1]]
                if ms:
                    avail[s] = ms
            if i % 100 == 0:
                log(f"        {i}/{len(kept)}  已用 {time.time()-t0:.0f}s")
    log(f"        完成 {len(avail)} 个合约有窗口内数据；"
        f"列目录失败 {len(failed_list)}")

    # ---- Step 2 下载 ----
    todo = [(s, ym) for s, ms in avail.items() for ym in ms]
    log(f"\nStep 2  下载 {len(todo)} 个月频 klines…")
    statuses: dict[str, int] = {}
    # 逐文件的最终状态。必须显式记录 —— 靠"缓存文件在不在"反推会把
    # 【已确认的 404】和【网络抖动】混为一谈，两者在缺失报告里处置完全不同。
    #
    # 初值【只按文件在不在】判定，不算作"尝试过"：文件在就是 cached，
    # 不在就是裸的 retry_exhausted。若这次走 --skip-download、或某几项没被补跑轮
    # 覆盖到，初值就会变成终态被写进 manifest —— 而 Step 6b 的缺失报告把 manifest
    # 里一切非 ok 记录当作缺失，于是"没尝试过"被误报成"缺失"。
    # 实测：18,832 项全在缓存里（摘要自报 cached=18,832、新下载 0），
    # manifest 却有 1,074 行 retry_exhausted，全部混进缺失报告。
    # 故初值用 cached（真值），retry_exhausted 只留给【确实尝试过且失败】的项。
    final_status: dict[tuple[str, str], str] = {
        (s_, ym_): ("cached" if cache_path(s_, ym_).exists() else "retry_exhausted")
        for s_, ym_ in todo}
    attempted: set[tuple[str, str]] = set()
    if args.skip_download:
        log("        --skip-download：跳过下载，只用已有缓存")
    else:
        t0 = time.time()
        done = 0
        with ThreadPoolExecutor(CONCURRENCY) as ex:
            futs = [ex.submit(download_one, s, ym) for s, ym in todo]
            for f in as_completed(futs):
                sy, ymy, st = f.result()
                final_status[(sy, ymy)] = st
                attempted.add((sy, ymy))
                statuses[st] = statuses.get(st, 0) + 1
                done += 1
                if done % 5000 == 0:
                    rate = done / max(time.time() - t0, 1)
                    log(f"        {done}/{len(todo)}  {rate:.1f} 文件/秒  "
                        f"已用 {time.time()-t0:.0f}s")
        log(f"        首轮完成，耗时 {time.time()-t0:.0f}s  状态 {statuses}")

        # 对未取得项补跑一轮（把问题在同一次运行内解决）
        retry = [(s, ym) for (s, ym) in todo if not cache_path(s, ym).exists()]
        if retry:
            log(f"        对 {len(retry)} 个未取得项补跑一轮…")
            t1 = time.time()
            with ThreadPoolExecutor(CONCURRENCY) as ex:
                for sy, ymy, st in ex.map(lambda t: download_one(*t), retry):
                    final_status[(sy, ymy)] = st
                    attempted.add((sy, ymy))
                    statuses["retry2_" + st] = statuses.get("retry2_" + st, 0) + 1
            log(f"        补跑完成，耗时 {time.time()-t1:.0f}s")
            # 补跑结果必须打出来：statuses 只在首轮之后打印过一次，
            # 不报的话 retry2_* 这份计数就没人看得见。
            r2 = {k[len("retry2_"):]: v for k, v in statuses.items()
                  if k.startswith("retry2_")}
            log(f"        补跑结果 {r2}")

    # ---- 排名 ----
    log("\n算逐月流动性排名（含草稿闸）…")
    stats: dict[str, tuple[dict[str, float], dict[str, int]]] = {}
    for s, ms in avail.items():
        liq_s, bars_s = build_monthly_stats(s, ms)
        if liq_s:
            stats[s] = (liq_s, bars_s)

    K = cfg.K
    union: set[str] = set()
    n_gated_month = 0
    for i, ym in enumerate(all_months):
        ranked = []
        for s, (liq_s, bars_s) in stats.items():
            if ym not in liq_s:
                continue
            if not draft_gate_ok(bars_s, all_months, i):
                n_gated_month += 1
                continue
            ranked.append((s, liq_s[ym]))
        ranked.sort(key=lambda kv: -kv[1])
        union |= {s for s, _ in ranked[:K]}
    log(f"        逐月排名完成；被草稿闸挡下的 (合约,月) 组合 {n_gated_month:,}")

    # ---- 产出 ----
    # 原子写：candidate_pool.csv 是 Step 3 的输入，撕裂的文件会让 Step 3
    # 静默处理一个被截断的池子（fetch 用 read_text().split() 读它，不会报错）。
    tmp = CANDIDATE_POOL.with_name(f"{CANDIDATE_POOL.name}.{os.getpid()}.part")
    pd.DataFrame({"symbol": sorted(union)}).to_csv(tmp, index=False)
    os.replace(tmp, CANDIDATE_POOL)

    # manifest：逐文件状态（核心字段），供断点续传与排查
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for s, ym in todo:
        p = cache_path(s, ym)
        exists = p.exists()
        st = final_status.get((s, ym), "retry_exhausted")
        if st == "cached":                   # 本次没下，但缓存就在那儿
            st = "ok"
        rows.append({
            "source": "klines",
            "symbol": s,
            "period": ym,
            "granularity": "monthly",
            "remote_path": monthly_klines_path(s, ym),
            "filename": f"{s}-1h-{ym}.zip",
            "status": st,
            "bytes": p.stat().st_size if exists else 0,
            "downloaded_at": now if exists else "",
            # 显式空串，不能让这一列落成 float64 全 NaN —— `nan or ""` 是 nan 而
            # bool(nan) 为 True，Step 3 会把全部 klines 误判成已落盘。
            "raw_written_at": "",
        })
    mf = pd.DataFrame(rows, columns=[
        "source", "symbol", "period", "granularity", "remote_path",
        "filename", "status", "bytes", "downloaded_at", "raw_written_at"])
    # 只替换本步骤自己的 (source=klines, granularity=monthly) 记录，
    # 其余（Step 3 的 mark/index/funding/metrics 明细）原样保留。
    #
    # ⚠️ 键空间与 Step 3 重叠：它也写 klines/monthly 的行。所以重写自己的行时
    # **必须把已有的 raw_written_at 带过来** —— 否则每次跑完 Step 0-2 都会清空
    # Step 3 的 klines 进度戳，下一轮 Step 3 要把池内约 1 万个 klines 文件全部重下
    # （实测 Step 3 的 1,676s 里绝大部分是这一次重复下载）。
    if MANIFEST.exists():
        old = pd.read_parquet(MANIFEST)
        for c in mf.columns:
            if c not in old.columns:
                old[c] = ""
        own = (old["source"] == "klines") & (old["granularity"] == "monthly")
        prev = old.loc[own, ["symbol", "period", "raw_written_at"]]
        stamp = {k: str(v) for k, v in
                 zip(zip(prev["symbol"], prev["period"]), prev["raw_written_at"])
                 if v is not None and not pd.isna(v) and str(v).strip()}
        mf["raw_written_at"] = [stamp.get((s, ym), "")
                                for s, ym in zip(mf["symbol"], mf["period"])]
        mf = pd.concat([old[~own][mf.columns], mf], ignore_index=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_name(MANIFEST.name + ".part")
    mf.to_parquet(tmp, engine="pyarrow", compression="zstd")
    os.replace(tmp, MANIFEST)
    n_fail = int((mf["status"] != "ok").sum())
    log(f"\nmanifest -> {MANIFEST}  ({len(mf):,} 行，非 ok {n_fail:,})")

    # ---- 运行摘要（★ 未取得 绝不能算进缺失）----
    # 没尝试过的项（--skip-download，或补跑轮没覆盖到）单列一类，与"尝试过但失败"
    # 分开报 —— 二者都写成 retry_exhausted 会把"没试"误报成"缺失"（见 final_status 处）。
    cnt: dict[str, int] = {}
    for k_, st_ in final_status.items():
        if k_ not in attempted and st_ == "retry_exhausted":
            st_ = "skipped_uncached"
        cnt[st_] = cnt.get(st_, 0) + 1
    n_cached = cnt.get("cached", 0)
    n_ok = cnt.get("ok", 0) + n_cached
    n_404 = cnt.get("confirmed_404", 0)
    n_retry = cnt.get("retry_exhausted", 0)
    n_skip = cnt.get("skipped_uncached", 0)
    log("\n" + "=" * 74)
    log("运行摘要")
    log("=" * 74)
    log(f"  归档合约（USDT 结尾）   {len(usdt):>8,}")
    log(f"  硬过滤后               {len(kept):>8,}")
    log(f"  有窗口内数据           {len(avail):>8,}")
    log(f"  待下载文件             {len(todo):>8,}")
    log(f"  本次新下载             {n_ok - n_cached:>8,}")
    log(f"  已取得（含缓存命中）      {n_ok:>8,}")
    log(f"  确认不存在 404         {n_404:>8,}   ← 归档空洞，非网络问题")
    log(f"  ★ 未取得（试过，待重试）  {n_retry:>8,}   ← 不等于缺失")
    log(f"  · 未尝试（本次没下）      {n_skip:>8,}   ← --skip-download 且缓存里没有")
    log(f"  ** 候选池（K={K} 并集）  {len(union):>8,} **")
    log(f"  总耗时                 {time.time()-t_start:.0f}s")
    log("=" * 74)
    log(f"  -> {CANDIDATE_POOL}")
    log(f"  -> {MANIFEST}")
    log("\n  下一步（Step 3）需要你核对：")
    log("    · 候选池规模是否合理")
    log("    · 代币化股票是否已全部剔除（闸 4 判据见文件头；实测池里分类表查不到的合约全是加密资产）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        # 参数错误不该甩 traceback —— 打清楚原因，退出码 2
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
