#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_market_data —— 为候选池合约下载全部可用历史，存成 raw 数据

它在 Phase 1 中的位置：Step 3（见 PHASE1_GUIDANCE.md §1.1 进度表与 §4 流水线）。

做什么
------
  1. 读候选池（297 个合约）
  2. 逐个源【枚举归档】，拿到真实存在的文件清单（不靠日期推算 —— 见下方"为什么"）
  3. 下载 + 【就地解压】→ 攒批 → 落 raw parquet → 删掉这批 zip
  4. 逐文件写 manifest（含 raw_written_at 进度戳），供断点续传

  5 个源（全部 1h，除 metrics 为 5 分钟快照）：
    月频 klines / markPriceKlines / indexPriceKlines / fundingRate
    日频 metrics（OI，只保留 24 个整点快照）

产出
----
  data/raw/klines/symbol=XXX.parquet            1h bar（12 列，源原样）
  data/raw/markPriceKlines/symbol=XXX.parquet
  data/raw/indexPriceKlines/symbol=XXX.parquet
  data/raw/fundingRate/symbol=XXX.parquet
  data/raw/metrics/year=YYYY.parquet            OI 整点快照
  data/00_config/manifest.parquet               本步骤的记录

为什么是"一遍过"而不是"先全下、再统一解压"
--------------------------------------------
两阶段写法要读两遍磁盘（34.4 万个 zip），而第二遍没有任何进度记录 ——
中断一次就要从头解压 60 分钟。实测：下载 41 分钟 + 转换 60 分钟。

一遍过把 zip 读一次就丢，并给每个文件打 raw_written_at：
  中断后重跑只重做"没打戳的"，损失 < 1 分钟
  缓存随进度自然释放，跑完 _cache/ 为空 —— 不需要事后再删

为什么每个源都要枚举，而不是用 klines 的月份推算
------------------------------------------------
实测：有 9 个合约（AGIXUSDT / BLZUSDT / BNXUSDT / FTMUSDT / LINAUSDT /
OCEANUSDT / REEFUSDT / RENUSDT / UNFIUSDT）的 indexPrice 与 fundingRate
【全部在 2025-07 同一个月截止】，而 klines 一直到 2026-08 都有。
9 个合约同时断供只可能是归档侧的批量空洞。
另有 13 个合约的 markPrice 在合约下架后仍多写了 12–23 个月空行。

所以清单必须来自枚举，不能推算。

用法
----
  python phase1_data/fetch_market_data.py --sample-end 2026-08-31
  P3_DATA_ROOT=/tmp/x python phase1_data/fetch_market_data.py \\
      --sample-end 2026-08-31 --subset BTCUSDT ETHUSDT     # 冒烟
  python phase1_data/fetch_market_data.py --sample-end 2026-08-31 --list-only
  python phase1_data/fetch_market_data.py --sample-end 2026-08-31 --keep-cache

依据：PHASE1_GUIDANCE.md §2（工程规则）§3（数据源）§5.3（下载参数）§8.3（缺失分类）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根：config.py / lib/
import config as cfg_mod                                     # noqa: E402

# ============================================================================
# 常量（依据见 §5.3）
# ============================================================================

S3_API = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
CDN = "https://data.binance.vision"

CONCURRENCY = 32
READ_TIMEOUT = 45
RETRIES = 3
BACKOFF_BASE = 2

# 攒够这么多行就落盘一次。50 万行 ≈ 几十 MB，安全。
FLUSH_ROWS = 500_000

# 同时留在磁盘上的 zip 数量上限。超出就先落盘一批再继续。
# 这是"一遍过"能保持磁盘占用有界的关键：缓存不会被撑到 3.9 GB。
CACHE_SOFT_LIMIT = 20_000

# 线程池在途任务上限（保持内存有界）
INFLIGHT = CONCURRENCY * 8

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("P3_DATA_ROOT", ROOT / "data"))
RAW = DATA / "raw"
CACHE = RAW / "_cache"
MANIFEST = DATA / "00_config" / "manifest.parquet"
CANDIDATE_POOL = DATA / "03_reference" / "candidate_pool.csv"
RUN_INFO = DATA / "00_config" / "sample_end.json"

# 月频源：(名字, 是否有 {interval}/ 层)。依据 §3.2 —— 漏掉该层就 404。
MONTHLY_SOURCES = [
    ("klines", "1h"),
    ("markPriceKlines", "1h"),
    ("indexPriceKlines", "1h"),
    ("fundingRate", None),
]
DAILY_SOURCE = "metrics"

# metrics 原始 8 列里只保留前两列（其余 6 列 2022 全年大面积为空，§7.3 决定不用）
METRICS_KEEP = ["create_time", "sum_open_interest"]

MONTH_RE = re.compile(r"-(\d{4}-\d{2})\.zip$")
DAY_RE = re.compile(r"-(\d{4}-\d{2}-\d{2})\.zip$")

_MONTH_RE_WINDOW: tuple[str, str] = ("", "")
T_START = time.time()


def log(msg: str) -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


# ============================================================================
# 网络层（§2 的两条工程规则）
# ============================================================================

def quote_seg(seg: str) -> str:
    """非 ASCII 才编码。归档里有中文名合约（币安人生USDT 等）。"""
    try:
        seg.encode("ascii")
    except UnicodeEncodeError:
        return urllib.parse.quote(seg, safe="")
    return seg


class FatalUrlError(RuntimeError):
    """不可重试的错误（编程错误）。必须炸出来，不许降级成"网络失败"。"""


def http(url: str, *, method: str = "GET") -> bytes:
    """带重试与退避的请求。

    ⚠️ 只重试【网络类】失败。编程错误立刻抛 —— 否则会把 bug 伪装成网络抖动
    （曾因此把 19 个真实存在的文件静默丢成 retry_exhausted）。
    """
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": "p3/2.0"})
            with urllib.request.urlopen(req, timeout=READ_TIMEOUT) as r:
                return r.read() if method == "GET" else b""
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise                       # 确定的答案，不重试
            last = e
        except (UnicodeEncodeError, UnicodeDecodeError, ValueError) as e:
            raise FatalUrlError(f"URL 不可用（非网络问题，不重试）：{url!r} -> {e}") from e
        except Exception as e:              # noqa: BLE001  网络类，可重试
            last = e
        if attempt < RETRIES - 1:
            time.sleep(BACKOFF_BASE ** attempt + random.random())
    assert last is not None
    raise last


def s3_keys(prefix: str) -> list[str]:
    """S3 列表（自动翻页），返回全部 <Key>。"""
    out: list[str] = []
    token: str | None = None
    while True:
        q = {"list-type": "2", "prefix": prefix, "max-keys": "1000"}
        if token:
            q["continuation-token"] = token
        body = http(f"{S3_API}?{urllib.parse.urlencode(q)}").decode("utf-8", "replace")
        out += re.findall(r"<Key>(.*?)</Key>", body)
        trunc = re.findall(r"<IsTruncated>(.*?)</IsTruncated>", body)
        if not (trunc and trunc[0] == "true"):
            return out
        nxt = re.findall(r"<NextContinuationToken>(.*?)</NextContinuationToken>", body)
        if not nxt:
            return out
        token = nxt[0]


# ============================================================================
# 路径构造
# ============================================================================

def monthly_path(src: str, interval: str | None, sym: str, ym: str) -> str:
    """月频文件的 URL 路径。四个源的命名规则【不同】，不能套用。

    实测（§3.2）：
      klines / markPriceKlines / indexPriceKlines
          monthly/{src}/{sym}/{itv}/{sym}-{itv}-{ym}.zip
      fundingRate（无 {itv}/ 层）
          monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip
                                       ^^^^^^^^^^^ 文件名里是源名，不是空
    """
    qs = quote_seg(sym)
    if interval:
        return f"/data/futures/um/monthly/{src}/{qs}/{interval}/{qs}-{interval}-{ym}.zip"
    return f"/data/futures/um/monthly/{src}/{qs}/{qs}-{src}-{ym}.zip"


def metrics_path(sym: str, day: str) -> str:
    qs = quote_seg(sym)
    return f"/data/futures/um/daily/metrics/{qs}/{qs}-metrics-{day}.zip"


def raw_out(src: str, sym_or_year: str) -> Path:
    """raw 下落盘位置。月频一币一文件；日频按年一文件（避免 29.7 万个小文件）。

    ⚠️ 文件名用【原始合约名】，不做百分号编码 —— quote_seg 是给 URL 用的。
    在文件系统上编码会让 币安人生USDT 变成 symbol=%E5%B8%81...，可读性尽失，
    而且任何按文件名反查合约的代码都要多一层解码。
    """
    if src == DAILY_SOURCE:
        return RAW / src / f"year={sym_or_year}.parquet"
    return RAW / src / f"symbol={sym_or_year}.parquet"


def cpath(src: str, sym: str, period: str) -> Path:
    """缓存文件名。同样是【文件系统】，用原始合约名，不编码。"""
    return CACHE / f"{src}__{sym}__{period}.zip"


# ============================================================================
# Step 3a —— 枚举：每个源真实存在哪些文件
# ============================================================================

def enum_monthly(src: str, interval: str | None, sym: str) -> set[str]:
    """月频源该合约的可用月份（窗口内）。返回 set['YYYY-MM']。"""
    qs = quote_seg(sym)
    mid = f"{interval}/" if interval else ""
    keys = s3_keys(f"data/futures/um/monthly/{src}/{qs}/{mid}")
    lo, hi = _MONTH_RE_WINDOW
    out = set()
    for k in keys:
        if not k.endswith(".zip"):           # 排除 .zip.CHECKSUM
            continue
        m = MONTH_RE.search(k)
        if m and lo <= m.group(1) <= hi:
            out.add(m.group(1))
    return out


def enum_metrics(sym: str) -> set[str]:
    """日频 metrics 该合约的可用日期（窗口内）。返回 set['YYYY-MM-DD']。"""
    qs = quote_seg(sym)
    keys = s3_keys(f"data/futures/um/daily/metrics/{qs}/")
    lo, hi = _MONTH_RE_WINDOW
    out = set()
    for k in keys:
        if not k.endswith(".zip"):
            continue
        m = DAY_RE.search(k)
        if m and lo <= m.group(1)[:7] <= hi:
            out.add(m.group(1))
    return out


# ============================================================================
# 解析（表头有无【逐文件检测】，不可按日期硬编码 —— §3.3）
# ============================================================================

KLINES_COLS = ["open_time", "open", "high", "low", "close", "volume",
               "close_time", "quote_volume", "count", "taker_buy_volume",
               "taker_buy_quote_volume", "ignore"]
FUND_COLS = ["calc_time", "funding_interval_hours", "last_funding_rate"]


def parse_zip(blob: bytes) -> pd.DataFrame | None:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            body = z.read(z.namelist()[0]).decode()
    except Exception:                        # noqa: BLE001
        return None
    lines = body.strip().split("\n")
    if not lines:
        return None
    first = lines[0].split(",", 1)[0].strip()
    has_header = not first.lstrip("-").replace(".", "").isdigit()
    df = pd.read_csv(io.StringIO(body), header=0 if has_header else None)
    if not has_header:
        n = df.shape[1]
        df.columns = (KLINES_COLS if n == 12 else FUND_COLS)[:n]
    return df


def to_hourly_metrics(df: pd.DataFrame | None) -> pd.DataFrame | None:
    """只留 24 个【整点】快照（Q1 选乙）。"""
    if df is None or df.empty:
        return None
    df = df[[c for c in METRICS_KEEP if c in df.columns]].copy()
    df["create_time"] = pd.to_datetime(df["create_time"], utc=True, format="mixed")
    out = df[df["create_time"].dt.minute == 0]
    return out if not out.empty else None


# ============================================================================
# 抓取（下载 + 就地解压）。返回 (status, blob_bytes, df)
# ============================================================================

def grab(src: str, sym: str, period: str, remote: str) -> tuple[str, int, pd.DataFrame | None]:
    """下载（或读缓存）并就地解压。

    status: ok / confirmed_404 / retry_exhausted
    """
    p = cpath(src, sym, period)
    if p.exists():
        data = p.read_bytes()
        df = parse_zip(data)
        if src == DAILY_SOURCE:
            df = to_hourly_metrics(df)
        return "ok", len(data), df
    try:
        blob = http(CDN + remote)
    except urllib.error.HTTPError as e:
        return ("confirmed_404" if e.code == 404 else "retry_exhausted"), 0, None
    except FatalUrlError:
        raise
    except Exception:                        # noqa: BLE001  网络类
        return "retry_exhausted", 0, None
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".part")
    tmp.write_bytes(blob)                    # 先落缓存，中断后可续
    os.replace(tmp, p)
    n = len(blob)
    df = parse_zip(blob)                     # ← 就地解压，blob 随即丢弃
    if src == DAILY_SOURCE:
        df = to_hourly_metrics(df)
    return "ok", n, df


# ============================================================================
# 落盘
# ============================================================================

def _atomic_parquet(df: pd.DataFrame, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp,
                   compression="zstd")
    os.replace(tmp, out)


def flush_monthly(src: str, sym: str, frames: list[pd.DataFrame]) -> None:
    """把某合约攒下的月频 frames 落盘。"""
    if not frames:
        return
    new = pd.concat(frames, ignore_index=True)
    out = raw_out(src, sym)
    if out.exists():
        try:
            new = pd.concat([pq.read_table(out).to_pandas(), new], ignore_index=True)
        except Exception:                    # noqa: BLE001
            pass
    tcol = "open_time" if "open_time" in new.columns else "calc_time"
    new = (new.drop_duplicates(subset=[tcol], keep="last")
              .sort_values(tcol, ignore_index=True))
    _atomic_parquet(new, out)


def drop_cache(keys_iter) -> None:
    """落盘成功后删除对应缓存。这是缓存不涨到 3.9 GB 的关键。"""
    for src, sym, period in keys_iter:
        cpath(src, sym, period).unlink(missing_ok=True)


def flush_metrics(year: str, df: pd.DataFrame) -> None:
    """把某一年的 OI 攒批落盘。"""
    out = raw_out(DAILY_SOURCE, year)
    if out.exists():
        try:
            df = pd.concat([pq.read_table(out).to_pandas(), df], ignore_index=True)
        except Exception:                    # noqa: BLE001
            pass
    df = (df.drop_duplicates(subset=["symbol", "create_time"], keep="last")
            .sort_values(["create_time", "symbol"], ignore_index=True))
    _atomic_parquet(df, out)


# ============================================================================
# 枚举阶段
# ============================================================================

def enumerate_all(pool: list[str], jobs: int) -> tuple[dict, dict]:
    monthly: dict[tuple[str, str], set[str]] = {}
    daily: dict[str, set[str]] = {}

    log(f"枚举月频源（{len(MONTHLY_SOURCES)} 源 × {len(pool)} 合约）…")
    t0 = time.time()
    with ThreadPoolExecutor(jobs) as ex:
        futs = {ex.submit(enum_monthly, src, itv, s): (src, s)
                for src, itv in MONTHLY_SOURCES for s in pool}
        done = 0
        for f in as_completed(futs):
            src, s = futs[f]
            try:
                monthly[(src, s)] = f.result()
            except Exception:                # noqa: BLE001
                monthly[(src, s)] = set()
            done += 1
            if done % 300 == 0:
                log(f"    {done}/{len(futs)}  已用 {time.time()-t0:.0f}s")
    log(f"    完成，耗时 {time.time()-t0:.0f}s")

    log(f"枚举日频 metrics（{len(pool)} 合约）…")
    t0 = time.time()
    with ThreadPoolExecutor(jobs) as ex:
        futs = {ex.submit(enum_metrics, s): s for s in pool}
        done = 0
        for f in as_completed(futs):
            s = futs[f]
            try:
                daily[s] = f.result()
            except Exception:                # noqa: BLE001
                daily[s] = set()
            done += 1
            if done % 100 == 0:
                log(f"    {done}/{len(pool)}  已用 {time.time()-t0:.0f}s")
    log(f"    完成，耗时 {time.time()-t0:.0f}s")
    return monthly, daily


# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Step 3 —— 下载候选池的市场数据")
    ap.add_argument("--sample-end", required=True,
                    help="样本截止日，必须是月末（如 2026-08-31）")
    ap.add_argument("--subset", nargs="+", default=None,
                    help="只处理这些合约（冒烟测试用）")
    ap.add_argument("--list-only", action="store_true", help="只枚举并打印清单")
    ap.add_argument("--keep-cache", action="store_true",
                    help="落盘后不删 zip 缓存（默认随进度删）")
    ap.add_argument("--jobs", type=int, default=CONCURRENCY)
    args = ap.parse_args()

    cfg = cfg_mod.Config()
    cfg_mod.validate_sample_end(args.sample_end)
    global _MONTH_RE_WINDOW
    _MONTH_RE_WINDOW = (cfg.sample_start[:7], args.sample_end[:7])

    log("=" * 76)
    log(f"fetch_market_data   sample_end={args.sample_end}   "
        f"窗口 {_MONTH_RE_WINDOW[0]} .. {_MONTH_RE_WINDOW[1]}")
    log(f"数据根目录: {DATA}")
    if args.subset:
        log(f"[冒烟模式] {len(args.subset)} 个合约")
    log("=" * 76)

    if not CANDIDATE_POOL.exists():
        log(f"找不到候选池 {CANDIDATE_POOL} —— 先跑 build_candidate_pool.py")
        return 2
    pool = [l.strip() for l in CANDIDATE_POOL.read_text(encoding="utf-8").split()
            if l.strip() and l != "symbol"]
    if args.subset:
        pool = [s for s in pool if s in set(args.subset)]
        if not pool:
            log(f"--subset 里的合约都不在候选池中：{args.subset}")
            return 2
    log(f"候选池 {len(pool)} 个合约")

    # ---- 枚举 ----
    monthly, daily = enumerate_all(pool, args.jobs)

    # ---- 任务清单 ----
    mjobs: list[tuple[str, str, str, str]] = []
    for src, itv in MONTHLY_SOURCES:
        for s in pool:
            for ym in sorted(monthly.get((src, s), ())):
                mjobs.append((src, s, ym, monthly_path(src, itv, s, ym)))

    # Q3(c)：每个合约【末月之后的第一天】—— 让最后一根 bar 的 OI 不为空。
    # 末月取自 klines（合约是否在交易的权威判据），不是 metrics ——
    # LUNAUSDT 的 metrics 有跨到 2024-06 的孤立残留，klines 才是 2022-05。
    djobs: list[tuple[str, str, str, str]] = []
    for s in pool:
        days = daily.get(s, set())
        if not days:
            continue
        for d in sorted(days):
            djobs.append((DAILY_SOURCE, s, d, metrics_path(s, d)))
        kmonths = monthly.get(("klines", s), set())
        anchor = max(kmonths) if kmonths else max(days)[:7]
        y, mo = int(anchor[:4]), int(anchor[5:7])
        nxt = date(y + (mo // 12), (mo % 12) + 1, 1).isoformat()
        if nxt not in days:
            djobs.append((DAILY_SOURCE, s, nxt, metrics_path(s, nxt)))

    jobs = mjobs + djobs
    by_src = Counter(j[0] for j in jobs)
    log("")
    log("任务清单：")
    for src, n in by_src.most_common():
        log(f"    {src:<20} {n:>8,}")
    log(f"    {'合计':<20} {len(jobs):>8,}")

    if args.list_only:
        log("--list-only：到此为止")
        return 0

    # ---- 断点续传：读回已知状态 ----
    status: dict[tuple[str, str, str], str] = {}
    written: dict[tuple[str, str, str], str] = {}
    size: dict[tuple[str, str, str], int] = {}
    if MANIFEST.exists():
        old = pd.read_parquet(MANIFEST)
        has_wr = "raw_written_at" in old.columns
        for r in old.itertuples(index=False):
            key = (r.source, r.symbol, r.period)
            st = getattr(r, "status", "") or ""
            # 注意：对【空列】hasattr 会返回 True，所以必须查列名而不是 hasattr
            wr = (getattr(r, "raw_written_at", "") or "") if has_wr else ""
            size[key] = int(getattr(r, "bytes", 0) or 0)
            if wr:
                written[key] = wr
                status[key] = st or "ok"
            elif st == "confirmed_404":
                status[key] = st

    todo_m = [j for j in mjobs if (j[0], j[1], j[2]) not in written]
    todo_d = [j for j in djobs if (j[0], j[1], j[2]) not in written]
    n_skip = len(jobs) - len(todo_m) - len(todo_d)
    log("")
    log(f"断点续传：已落盘 {n_skip:,} 个跳过；本次处理 "
        f"{len(todo_m)+len(todo_d):,} 个")

    interrupted = False
    n_ok = n_404 = n_retry = 0
    n_rows = 0

    def stamp(keys) -> None:
        """打进度戳。已是终态的 key 一律释放其缓存 —— 这是缓存不涨的关键。

        只有 stamp 这一条路径会删缓存，避免"某条分支打了戳但忘了删"。
        """
        now_ = datetime.now(timezone.utc).isoformat()
        released = []
        for k in keys:
            written.setdefault(k, now_)
            status.setdefault(k, "ok")
            if status.get(k) in ("ok", "confirmed_404"):
                released.append(k)
        if released and not args.keep_cache:
            drop_cache(released)

    # ---- 统一的攒批器：按 (源, 合约) 攒，落盘后立刻释放该合约的缓存 ----
    order: list[tuple[str, str]] = []
    buf: dict[tuple[str, str], list[tuple[str, pd.DataFrame]]] = defaultdict(list)
    buf_rows: Counter = Counter()
    pend: Counter = Counter()
    periods_of: dict[tuple[str, str], list[str]] = defaultdict(list)
    for src, sy, period, _ in todo_m + todo_d:
        if (src, sy) not in pend:
            order.append((src, sy))
        pend[(src, sy)] += 1
        periods_of[(src, sy)].append(period)

    def flush_one(key: tuple[str, str]) -> None:
        nonlocal n_rows
        items = buf.pop(key, [])
        buf_rows[key] = 0
        if not items:
            return
        src, sy = key
        if src == DAILY_SOURCE:
            df = pd.concat([d for _, d in items], ignore_index=True)
            df.insert(0, "symbol", sy)
            for yr, g in df.groupby(df["create_time"].dt.year):
                flush_metrics(str(yr), g.reset_index(drop=True))
            ks = [(src, sy, p) for p, _ in items]
        else:
            flush_monthly(src, sy, [d for _, d in items])
            ks = [(src, sy, p) for p, _ in items]
        n_rows += sum(len(d) for _, d in items)
        stamp(ks)

    def flush_all() -> None:
        for k in list(order):
            if buf_rows[k]:
                flush_one(k)

    def run_pass(todo, label: str) -> None:
        """下载 + 就地解压 + 按合约落盘。一遍过，无第二遍读盘。"""
        nonlocal n_ok, n_404, n_retry
        log("")
        log(f"{label}：{len(todo):,} 个文件…")
        t0 = time.time()
        it = iter(todo)
        exhausted = False
        done = 0
        with ThreadPoolExecutor(args.jobs) as ex:
            futs: dict[Future, tuple[str, str, str]] = {}
            while True:
                while not exhausted and len(futs) < INFLIGHT:
                    try:
                        src, sy, period, remote = next(it)
                    except StopIteration:
                        exhausted = True
                        break
                    futs[ex.submit(grab, src, sy, period, remote)] = (src, sy, period)
                if not futs:
                    break
                f = next(as_completed(list(futs)))
                src, sy, period = futs.pop(f)
                st, nbytes, df = f.result()
                key = (src, sy, period)
                status[key] = st
                size[key] = nbytes
                if st == "ok":
                    n_ok += 1
                    if df is not None and not df.empty:
                        buf[(src, sy)].append((period, df))
                        buf_rows[(src, sy)] += len(df)
                    else:
                        # 取到了，但没有整点行（或 zip 解析为空）—— 立刻打戳，
                        # 否则它会永远悬着，缓存也不释放
                        stamp([key])
                elif st == "confirmed_404":
                    n_404 += 1
                    stamp([key])
                else:
                    n_retry += 1
                pend[(src, sy)] -= 1
                done += 1
                # 该合约全部回来 → 收尾（落盘 + 打戳 + 清缓存）
                # 注意：即使 buf 为空也要收尾 —— 否则"整组都是 404"的组永远不打戳，
                # 缓存残留，且下次重跑会重新探测已知的 404。
                if pend[(src, sy)] == 0 and buf_rows[(src, sy)]:
                    flush_one((src, sy))
                # 缓存软上限：攒多了先落一批，别把磁盘撑爆
                if sum(buf_rows.values()) >= FLUSH_ROWS:
                    flush_all()
                if done % 2000 == 0:
                    log(f"    {done:,}/{len(todo):,}  已用 {time.time()-t0:.0f}s")
        flush_all()
        log(f"    完成，耗时 {time.time()-t0:.0f}s")

    try:
        run_pass(todo_m, "月频 klines/mark/index/funding")
        run_pass(todo_d, "日频 metrics (OI)")

        # 补跑一轮未取得项（§5.3：把问题在同一次运行内解决）
        remote_of = {(j[0], j[1], j[2]): j[3] for j in todo_m + todo_d}
        retry_jobs = [j for j in todo_m + todo_d
                      if status.get((j[0], j[1], j[2])) == "retry_exhausted"]
        if retry_jobs:
            for s_, sy_, p_ in (j[:3] for j in retry_jobs):
                written.pop((s_, sy_, p_), None)      # 允许重写
            counts: Counter = Counter((j[0], j[1]) for j in retry_jobs)
            for k_, c_ in counts.items():
                pend[k_] = c_                         # 重置计数，否则永不触发收尾
            log("")
            log(f"对 {len(retry_jobs):,} 个未取得项补跑一轮…")
            run_pass(retry_jobs, "补跑")
    except KeyboardInterrupt:
        interrupted = True
        log("")
        log("!!! 收到中断 —— 正在收尾已下载的数据…")
        try:
            flush_all()
        except Exception:                     # noqa: BLE001
            pass
        log("    收尾完成；重跑会从断点继续（已打 raw_written_at 的不会再下）")

    # ---- manifest ----
    now = datetime.now(timezone.utc).isoformat()
    rows = []
    for src, s, period, remote in jobs:
        key = (src, s, period)
        wr = written.get(key, "")
        rows.append({
            "source": src,
            "symbol": s,
            "period": period,
            "granularity": "daily" if src == DAILY_SOURCE else "monthly",
            "remote_path": remote,
            "filename": remote.rsplit("/", 1)[-1],
            "status": status.get(key, "retry_exhausted"),
            "bytes": size.get(key, 0),
            "downloaded_at": now if status.get(key) == "ok" else "",
            "raw_written_at": wr,
        })
    cols = ["source", "symbol", "period", "granularity", "remote_path",
            "filename", "status", "bytes", "downloaded_at", "raw_written_at"]
    mf = pd.DataFrame(rows, columns=cols)
    if MANIFEST.exists():
        old = pd.read_parquet(MANIFEST)
        for c in cols:
            if c not in old.columns:
                old[c] = ""
        keys = set(zip(mf["source"], mf["symbol"], mf["period"], mf["granularity"]))
        keep = [tuple(r) not in keys for r in
                old[["source", "symbol", "period", "granularity"]]
                .itertuples(index=False)]
        mf = pd.concat([old[keep][cols], mf], ignore_index=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST.with_name(MANIFEST.name + ".part")
    mf.to_parquet(tmp, engine="pyarrow", compression="zstd")
    os.replace(tmp, MANIFEST)

    n_written = sum(1 for k in jobs
                    if written.get((k[0], k[1], k[2])))
    # ---- 运行摘要 ----
    RUN_INFO.parent.mkdir(parents=True, exist_ok=True)
    RUN_INFO.write_text(json.dumps({
        "sample_end": args.sample_end,
        "sample_start": cfg.sample_start,
        "config_snapshot": cfg.snapshot(),
        "step": "fetch_market_data",
        "run_at": now,
        "interrupted": interrupted,
        "candidate_pool_size": len(pool),
        "files_total": len(jobs),
        "files_written": n_written,
        "files_per_source": dict(by_src),
        "status_counts": {"ok": n_ok, "confirmed_404": n_404,
                          "retry_exhausted": n_retry},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    log("")
    log("=" * 76)
    log("运行摘要")
    log("=" * 76)
    log(f"  候选池合约                 {len(pool):>8,}")
    log(f"  任务文件总数               {len(jobs):>8,}")
    log(f"  本次取得                   {n_ok:>8,}")
    log(f"  本次确认不存在 404          {n_404:>8,}   ← 归档空洞，进入缺失报告")
    log(f"  本次未取得（待重试）        {n_retry:>8,}")
    log(f"  累计已落盘 raw             {n_written:>8,}")
    log(f"  写入行数（本次）           {n_rows:>8,}")
    log(f"  总耗时                     {time.time()-T_START:>8.0f}s")
    log("=" * 76)
    seen = set()
    for src in list(by_src) + [DAILY_SOURCE]:
        if src in seen:
            continue
        seen.add(src)
        d = RAW / src
        if d.exists():
            fs = list(d.glob("*.parquet"))
            sz = sum(p.stat().st_size for p in fs)
            log(f"  {src:<20} {len(fs):>5} 个 parquet   {sz/2**30:7.3f} GB")
    if CACHE.exists():
        n = sum(1 for _ in CACHE.glob("*.zip"))
        log(f"  {'_cache（残留）':<20} {n:>5} 个 zip")
    log("")
    log("  下一步（Step 4）建 4 张标准 1h 表：")
    log("    klines_1h · mark_index_1h · oi_1h · funding")
    return 1 if interrupted else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
