#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_universe —— Step 6：逐期资格判定 + PIT 成员集 + master 表

它在 Phase 1 中的位置：Step 6（见 phase1/guidance.md §2.2 Step 6a 与 §3）。

做什么
------
  逐月（`sample_start` .. `sample_end`）走四条资格闸 → 按 liq 排名 → 取前 K → 成员集冻结。

  评测窗口：`[月初 − liq_window_days, 月初)` —— **严格开口，否则前视**。

四条闸（§6.1）
--------------
  闸 1  非稳定币（按 baseAsset）
  闸 2  ① 截至月初 bar 数 ≥ 2160（90 天）
        ② 最后活跃日 ≥ 月初（仍在交易）
        ⚠️ ② 必需 —— 合约死后 bar 数冻结而阈值固定，只数 bar 数会永远通过
  闸 3  ① trailing 30 天 OI 覆盖率 ≥ 0.90
        ② trailing 30 天最长连续缺失 ≤ 48h
  闸 4  非代币化传统金融资产（exchangeInfo 判据）

  流动性不设闸 —— note 的 `Top 30–50 liquid` 由排名承担。

产出（`data/03_reference/`）
---------------------------
  master.parquet                一币一行（285 个候选池合约）
  universe_eligibility.parquet  一币一月（候选池 × 全部月份，含失败原因）
  universe_membership.parquet   一币一月（成员）
  member_changes.parquet        一月一行（进出记录）

用法
----
  python phase1/build_universe.py --out-root <data> --sample-end 2026-08-31
  python phase1/build_universe.py --out-root /tmp/x --fe-root <data> \\
      --sample-end 2026-08-31 --subset BTCUSDT LUNAUSDT      # 冒烟
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根
import config as cfg_mod                                     # noqa: E402

# ============================================================================
# 路径（由 --out-root 显式指定，不用环境变量 —— 见 Step 4 的说明）
# ============================================================================

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FE = DATA / "02_features" / "features_1h"
RAW = DATA / "raw"
REF = DATA / "03_reference"
RUN_INFO = DATA / "00_config" / "sample_end.json"
CANDIDATE_POOL = ROOT / "data" / "03_reference" / "candidate_pool.csv"

T_START = time.time()


def configure_paths(out_root: Path, fe_root: Path | None, pool: Path | None) -> None:
    global DATA, FE, RAW, REF, RUN_INFO, CANDIDATE_POOL
    DATA = out_root.resolve()
    FE = ((fe_root or (DATA / "02_features")) / "features_1h").resolve()
    RAW = (DATA / "raw").resolve()
    REF = DATA / "03_reference"
    RUN_INFO = DATA / "00_config" / "sample_end.json"
    CANDIDATE_POOL = (pool or (ROOT / "data" / "03_reference"
                               / "candidate_pool.csv")).resolve()


def log(msg: str) -> None:
    el = time.time() - T_START
    print(f"[{int(el)//60:02d}:{int(el)%60:02d}] {msg}", flush=True)


# ============================================================================
# 小工具
# ============================================================================

def month_list(start: str, end: str) -> list[str]:
    """['2021-12', ..., '2026-08']，闭区间。

    入参可以是 'YYYY-MM' 或 'YYYY-MM-DD'（`cfg.sample_start` 是后者）。
    """
    y0, m0 = int(start[:4]), int(start[5:7])
    y1, m1 = int(end[:4]), int(end[5:7])
    out, y, m = [], y0, m0
    while (y, m) <= (y1, m1):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def max_run_true(a: np.ndarray) -> int:
    """布尔数组里最长连续 True 的长度。"""
    if not a.any():
        return 0
    idx = np.flatnonzero(np.diff(np.concatenate([[0], a.astype(np.int8), [0]])) != 0)
    return int((idx[1::2] - idx[0::2]).max())


def fetch_exchange_info() -> dict[str, dict]:
    """取 exchangeInfo（闸 4 的判据来源）。失败返回空 dict 并告警。"""
    url = "https://www.binance.com/fapi/v1/exchangeInfo"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=45) as r:
                data = json.loads(r.read())
            return {x["symbol"]: x for x in data.get("symbols", [])}
        except Exception as e:                    # noqa: BLE001
            if attempt == 2:
                log(f"    ⚠️ exchangeInfo 取不到：{type(e).__name__}: {e}")
                return {}
            time.sleep(2 ** attempt)
    return {}


# ============================================================================
# exchangeInfo 快照（闸 4 的判据必须可复现）
# ============================================================================

# 快照存四个字段：闸 4 判据（contractType / underlyingType）+
# Step 1 硬过滤需要的（baseAsset / quoteAsset）。
# 为什么不存全量：全量 payload 是 9 个顶层键 × 920 条 × 40 个字段（几 MB），
# 绝大部分与判据无关。但也不能只存闸 4 要的两个 —— 实测这样会导致
# **Step 1 的过滤明细无法从产出重现**（"非 USDT 本位"要看 quoteAsset，
# "稳定币"要看 baseAsset），于是 893 → 679 这条链对不上账。
EI_FIELDS = ("contractType", "underlyingType", "baseAsset", "quoteAsset")


def ei_digest(info: dict[str, dict]) -> str:
    """对「合约 → 分类」映射取指纹。用来证明本次用的 oracle 与快照逐字节一致。

    只对闸 4 读的字段做哈希，且按 symbol 排序 —— 否则 Binance 调整 JSON 里
    无关字段的顺序就会让指纹变化，失去验证意义。
    """
    canon = {s: [info[s].get(f) for f in EI_FIELDS] for s in sorted(info)}
    blob = json.dumps(canon, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def ei_snapshot_path() -> Path:
    """快照位置：与代码同目录（这个文件要进版本控制）。

    ⚠️ 不能放 <out-root>/00_config/ —— data/ 整体被 .gitignore 排除，
    那样快照不进版本控制，等于没解决"判据不可复现"的问题。
    D1 的复现性不该依赖一次成功的网络请求。
    """
    return Path(__file__).resolve().parent / "exchange_info_snapshot.json"


def read_ei_snapshot(p: Path) -> tuple[dict[str, dict], dict]:
    """读快照。文件中途被截断或哈希对不上都拒绝使用 —— 宁可取不到也不能用半个 oracle。"""
    d = json.loads(p.read_text(encoding="utf-8"))
    info = d.get("classifications") or {}
    if len(info) < 300:
        raise SystemExit(f"{p} 只有 {len(info)} 条分类（< 300）—— 快照损坏，拒绝使用。")
    want = d.get("digest", "")
    got = ei_digest(info)
    if want and got != want:
        raise SystemExit(f"{p} 的指纹不符：记录 {want[:12]}… 实算 {got[:12]}… —— 拒绝使用。")
    return info, d


def write_ei_snapshot(p: Path, info: dict[str, dict]) -> None:
    payload = {
        "note": "闸 4 的判据。只存 contractType / underlyingType，其余字段与闸 4 无关。",
        "source": "https://www.binance.com/fapi/v1/exchangeInfo",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "n_symbols": len(info),
        "digest": ei_digest(info),
        "classifications": {s: {f: info[s].get(f) for f in EI_FIELDS}
                            for s in sorted(info)},
    }
    tmp = p.with_name(f"{p.name}.{os.getpid()}.part")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1,
                              sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def load_or_fetch_exchange_info(refresh: bool,
                                path: Path | None) -> tuple[dict[str, dict], dict]:
    """闸 4 的 oracle：优先用快照，可选强制刷新。

    顺序：CLI 给了 --refresh-exchange-info → 联网取并写快照；否则先读快照；
    快照不存在才联网取。联网失败时回落到快照，让**离线也能复现已发布的 D1** ——
    原来离线只能 exit 3，D1 的复现性被一次网络请求绑架。
    """
    p = path or ei_snapshot_path()
    src = {"snapshot_path": str(p), "from": "", "fetched_at": "", "digest": ""}

    if refresh or not p.exists():
        log(f"  {'--refresh-exchange-info：' if refresh else '快照不存在，'}联网取 exchangeInfo…")
        info = fetch_exchange_info()
        if len(info) < 300:
            log(f"    ⚠️ 只拿到 {len(info)} 条 —— 疑似残包或网络不可达。")
            if p.exists():
                info, d = read_ei_snapshot(p)
                src["from"] = "snapshot_fallback"
                src["fetched_at"] = d.get("fetched_at", "")
                src["digest"] = d.get("digest", "")
                log(f"    回落到快照（{len(info)} 条，取于 {src['fetched_at']}）。")
                return info, src
            log("    且没有可用快照 —— 拒绝继续（闸 4 会把代币化资产全放行）。")
            return {}, src
        write_ei_snapshot(p, info)
        _, d = read_ei_snapshot(p)          # 回读，保证记录的就是落盘的那份
        src["from"] = "live"
        src["fetched_at"] = d.get("fetched_at", "")
        src["digest"] = d.get("digest", "")
        log(f"    取到 {len(info)} 条，已写入快照 {p.name}")
        return info, src

    info, d = read_ei_snapshot(p)
    src["from"] = "snapshot"
    src["fetched_at"] = d.get("fetched_at", "")
    src["digest"] = d.get("digest", "")
    log(f"  用快照 {p.name}：{len(info)} 条，取于 {src['fetched_at']}")
    return info, src



# ============================================================================
# 主流程
# ============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Step 6 —— universe 构造")
    ap.add_argument("--out-root", required=True, help="产出根目录（必填）")
    ap.add_argument("--fe-root", default=None,
                    help="features 的读取位置（默认 <out-root>/02_features）。冒烟时指向正式目录")
    ap.add_argument("--pool", default=None, help="候选池 CSV 路径")
    ap.add_argument("--sample-end", required=True, help="样本截止日，必须是月末")
    ap.add_argument("--subset", nargs="+", default=None, help="只处理这些合约（冒烟）")
    ap.add_argument("--no-schema-note", action="store_true",
                    help="跳过 exchangeInfo（闸 4 失效，全部合约按加密资产放行）")
    ap.add_argument("--refresh-exchange-info", action="store_true",
                    help="强制联网重取 exchangeInfo 并覆盖快照（默认用快照；"
                         "快照不存在才联网）")
    ap.add_argument("--exchange-info", default=None,
                    help="快照文件路径（默认 phase1/exchange_info_snapshot.json）")
    args = ap.parse_args()

    configure_paths(Path(args.out_root),
                    Path(args.fe_root) if args.fe_root else None,
                    Path(args.pool) if args.pool else None)
    cfg = cfg_mod.Config()
    cfg_mod.validate_sample_end(args.sample_end)

    log("=" * 80)
    log(f"build_universe   sample_end={args.sample_end}")
    log(f"  产出根目录 : {DATA}")
    log(f"  features   : {FE}")
    log("=" * 80)

    # ---- 读 features_1h 的标记列（不用读 19 列全量）----
    t0 = time.time()
    parts = []
    for f in sorted(FE.rglob("*.parquet")):
        parts.append(pq.read_table(str(f), columns=[
            "symbol", "ts", "quote_volume", "oi", "oi_missing",
            "mark_close", "index_close", "bar_missing"],
            partitioning=None).to_pandas())
    d = pd.concat(parts, ignore_index=True).sort_values(["symbol", "ts"])
    d["day"] = d["ts"].dt.floor("D")
    log(f"  读入 features_1h：{len(d):,} 行 / {d['symbol'].nunique()} 个合约"
        f"   耗时 {time.time()-t0:.0f}s")

    pool = [l.strip() for l in CANDIDATE_POOL.read_text(encoding="utf-8").split()
            if l.strip() and l != "symbol"]
    if args.subset:
        pool = [s for s in pool if s in set(args.subset)]
        if not pool:
            log(f"--subset 里的合约都不在候选池中：{args.subset}")
            return 2

    # 资格评测的对象 = 【候选池】，不是全部归档合约。
    # 精筛这一步只关心"候选池里谁能当成员"，落选的合约在 Step 2 就被排除了，
    # 它们的账在 archive_contracts.csv（1,057）与 dropped_contracts.csv（218）里。
    # （曾按 manifest 的 klines 记录扩到 677 个合约，为的是给落选者留一条
    #   not_in_candidate_pool 的记录；那样 eligibility 有 58% 的行是"无数据所以
    #   不通过"，信息量低，已收窄。）
    all_syms = sorted(pool)
    pool_set = set(pool)
    months = month_list(cfg.sample_start, args.sample_end)
    log(f"  评测对象 {len(all_syms)} 个合约（= 候选池）")
    log(f"  评测月份 {months[0]} .. {months[-1]}（{len(months)} 个）")

    # ---- 逐合约的派生量（与月份无关）----
    daily = (d.groupby(["symbol", "day"])["quote_volume"].sum()
              .reset_index().rename(columns={"quote_volume": "qv"}))
    daily["act"] = daily["qv"] > 0
    last_act = daily[daily["act"]].groupby("symbol")["day"].max()

    # ---- exchangeInfo（闸 4）----
    log("")
    ei_src = {"from": "skipped", "snapshot_path": "", "fetched_at": "", "digest": ""}
    if args.no_schema_note:
        info = {}
        log("  --no-schema-note：跳过 exchangeInfo —— 闸 4 失效，全部合约放行。"
            "仅供离线跑通流程，不可用于正式产出。")
    else:
        info, ei_src = load_or_fetch_exchange_info(
            args.refresh_exchange_info,
            Path(args.exchange_info) if args.exchange_info else None)
        # 不能静默降级：没有 exchangeInfo 就没有 underlyingType，
        # 闸 4 会把【全部】代币化资产判成加密资产放进池子。
        # 两种失败都要拦住：完全取不到（0 条），以及截断但合法的残包 ——
        # 后者会让闸 4 对缺记录的合约静默放行。
        if len(info) < 300:
            log("")
            log(f"  ✗ exchangeInfo 只有 {len(info)} 条（< 300）—— 取不到或残包，拒绝继续。")
            log("    需要 VPN（www.binance.com 的 DNS 被污染，见 guidance §2.1）；")
            log("    或从版本控制里取回 phase1/exchange_info_snapshot.json；")
            log("    若只想跑通流程做冒烟，加 --no-schema-note。")
            return 3

    # ---- 稳定币（闸 1）----
    stable = set(cfg.stablecoin_bases)

    # ---- 逐月 ----
    log("")
    log("逐月评测…")
    # 每天是否活跃（预计算成 {symbol: set[date]}，避免循环里反复过滤）
    act_by_sym: dict[str, set] = {
        s: set(g["day"].dt.date) for s, g in daily[daily["act"]].groupby("symbol")
    }
    bars_cum: dict[str, np.ndarray] = {
        s: np.sort(g["ts"].values) for s, g in d.groupby("symbol")
    }

    elig_rows: list[dict] = []
    t0 = time.time()
    for mi, m in enumerate(months):
        cut = pd.Timestamp(m + "-01", tz="UTC")
        lo = cut - pd.Timedelta(days=cfg.liq_window_days)
        w = d[(d["ts"] >= lo) & (d["ts"] < cut)]
        liq = w.groupby("symbol")["quote_volume"].median()
        cov = w.groupby("symbol")["oi_missing"].apply(lambda s: 1 - s.mean())
        mruns = w.groupby("symbol")["oi_missing"].apply(
            lambda s: max_run_true(s.to_numpy()))
        oi_null_days = (w.assign(nul=w["oi"].isna())
                         .groupby(["symbol", "day"])["nul"].max()
                         .groupby("symbol").sum())
        win_days_all = pd.date_range(lo, cut, freq="D", inclusive="left").date
        cut_np = np.datetime64(cut.tz_convert(None))

        for s in all_syms:
            base = s[:-4] if s.endswith("USDT") else s
            rec = info.get(s)
            arr = bars_cum.get(s, np.array([], dtype="datetime64[ns]"))
            r: dict = {
                "symbol": s, "month": m, "base_asset": base,
                "in_pool": s in pool_set,
                "liq": float(liq[s]) if s in liq.index and pd.notna(liq.get(s)) else np.nan,
                "bars_before": int(np.searchsorted(arr, cut_np)),
                "last_active": last_act.get(s, pd.NaT),
                "oi_cov": float(cov[s]) if s in cov.index else np.nan,
                "oi_max_gap_h": int(mruns[s]) if s in mruns.index else 0,
                "oi_null_days": int(oi_null_days.get(s, 0)),
                "obs_days": int(w[w["symbol"] == s]["day"].nunique()),
                "active_days": len(act_by_sym.get(s, set()) & set(win_days_all)),
            }

            # ---- 四条闸 ----
            g1 = base not in stable
            live = (pd.notna(r["last_active"]) and r["last_active"] >= cut)
            g2a = r["bars_before"] >= cfg.min_history_bars
            g2 = g2a and (live or not cfg.require_live_at_month_start)
            g3a = (pd.notna(r["oi_cov"]) and r["oi_cov"] >= cfg.min_oi_coverage)
            g3b = r["oi_max_gap_h"] <= cfg.max_oi_gap_hours
            g3 = g3a and g3b
            # 闸 4 的判据【只有分类字段】。代币化股票/ETF/商品/外汇是
            # TRADIFI_PERPETUAL，3 个合成指数永续是 PERPETUAL/INDEX，都被挡住。
            # 故意的例外：PAXG/XAUT 被标成 PERPETUAL/COIN，按此判据放行 ——
            # 它们是链上发行的加密原生合约（24/7、无收盘时段），
            # 属于 note 所说的 "crypto perpetual futures"；
            # 反之代币化股票有交易时段，闭市时 OI/资金费率语义会变。
            # 分类表里查不到的（实测 29 个）按加密资产处理：它们是已下架的合约
            # （exchangeInfo 只含当前挂牌），而池里的非加密标的都是近年才上的，
            # 不会出现在下架名单里。
            g4 = rec is None or (rec.get("contractType") == "PERPETUAL"
                                 and rec.get("underlyingType") == "COIN")

            reasons = []
            if not g1:
                reasons.append("stablecoin")
            if not g2a:
                reasons.append("insufficient_history")
            if not live and cfg.require_live_at_month_start:
                reasons.append("not_trading")
            if not g3a:
                reasons.append("oi_coverage_low")
            if not g3b:
                reasons.append("oi_gap_too_long")
            if not g4:
                reasons.append("non_crypto")

            r.update({"g1": g1, "g2a": g2a, "live": live, "g2": g2,
                      "g3a": g3a, "g3b": g3b, "g3": g3, "g4": g4,
                      "eligible": bool(g1 and g2 and g3 and g4),
                      "fail_reason": "|".join(reasons)})
            elig_rows.append(r)
        if (mi + 1) % 10 == 0:
            log(f"    {mi+1}/{len(months)} 个月  已用 {time.time()-t0:.0f}s")

    E = pd.DataFrame(elig_rows)
    log(f"  评测完成，{len(E):,} 行  耗时 {time.time()-t0:.0f}s")

    # ---- 排名 ----
    # 排名【只在候选池内】—— 落选的 394 个合约没有数据，排名无意义
    E["rank"] = np.nan
    elig = E[E["in_pool"] & E["eligible"] & E["liq"].notna()].copy()
    elig["rank"] = elig.groupby("month")["liq"].rank(ascending=False, method="first")
    E = E.drop(columns=["rank"]).merge(
        elig[["symbol", "month", "rank"]], on=["symbol", "month"], how="left")

    M = E[E["rank"] <= cfg.K].copy()
    M["is_member"] = True
    M = M[["symbol", "month", "rank", "liq", "bars_before", "oi_cov",
           "oi_max_gap_h", "active_days"]].sort_values(["month", "rank"])
    log("")
    log(f"  成员：{len(M):,} 行   {M['month'].nunique()} 个月   "
        f"每月 {M.groupby('month').size().min()}–{M.groupby('month').size().max()} 个")

    # ---- member_changes ----
    prev: set[str] = set()
    chg = []
    for m in months:
        cur = set(M[M["month"] == m]["symbol"])
        chg.append({
            "month": m,
            "n_members": len(cur),
            "n_entered": len(cur - prev),
            "n_exited": len(prev - cur),
            "n_retained": len(cur & prev),
            "turnover": (len(cur - prev) / len(cur)) if cur else np.nan,
        })
        prev = cur
    C = pd.DataFrame(chg)

    # ---- master：一币一行，覆盖【候选池】----
    # 候选池的 285 个合约全部有数据（Step 3 只为它们下载），所以 has_data 恒 True。
    # 落选的合约不在这里 —— 它们的账在 archive_contracts.csv / dropped_contracts.csv。
    # 预分组：直接在 7.25M 行上按合约过滤会做 285 次全表扫描（实测 5 分钟）
    d_by_sym = {s: g for s, g in d.groupby("symbol", sort=False)}
    daily_by_sym = {s: g for s, g in daily.groupby("symbol", sort=False)}

    mrows = []
    for s in all_syms:
        base = s[:-4] if s.endswith("USDT") else s
        rec = info.get(s)
        sub = d_by_sym.get(s)
        daily_sub = daily_by_sym.get(s)
        has = sub is not None and len(sub) > 0
        mrows.append({
            "symbol": s,
            "base_asset": base,
            "in_pool": s in pool_set,
            "has_data": has,
            "first_bar": sub["ts"].min() if has else pd.NaT,
            "last_bar": sub["ts"].max() if has else pd.NaT,
            "n_bars": len(sub) if has else 0,
            "n_months": (sub["ts"].dt.strftime("%Y-%m").nunique() if has else 0),
            "last_active": last_act.get(s, pd.NaT),
            "median_daily_qv": (daily_sub["qv"].median()
                                if daily_sub is not None and len(daily_sub)
                                else np.nan),
            "contract_type": rec.get("contractType") if rec else None,
            "underlying_type": rec.get("underlyingType") if rec else None,
            "in_exchange_info": rec is not None,
            # 原 dropped_reason 已删除：它是"为什么这个合约从没当过成员"的一行摘要，
            # 但评测范围收窄到候选池后只剩 4 个非空值（never_eligible），
            # 且信息与 universe_eligibility 的【逐月 fail_reason】完全重复、粒度更粗。
            # 要查原因请读 universe_eligibility（每个 (合约,月) 都有 fail_reason）。
            # 原 not_in_candidate_pool 分支随评测范围收窄而不可达，一并删除。
        })
    MA = pd.DataFrame(mrows)

    # ---- 落盘 ----
    REF.mkdir(parents=True, exist_ok=True)
    outs = {
        "master.parquet": MA,
        "universe_eligibility.parquet": E,
        "universe_membership.parquet": M,
        "member_changes.parquet": C,
    }
    for name, df in outs.items():
        p = REF / name
        tmp = p.with_name(p.name + ".part")
        pq.write_table(pa.Table.from_pandas(df, preserve_index=False), tmp,
                       compression="zstd")
        os.replace(tmp, p)
        log(f"    -> {name:<34} {len(df):>8,} 行")

    # ---- 闸的挡截统计 ----
    log("")
    log("=" * 80)
    log("四条闸的挡截统计（累计，闭区间）")
    log("=" * 80)
    n = len(E)
    log(f"  评测总行数（合约×月）      {n:>9,}")
    log(f"  闸 1  稳定币                  {int((~E['g1']).sum()):>9,}")
    log(f"  闸 2① 历史不足               {int((~E['g2a']).sum()):>9,}")
    log(f"  闸 2② 已停止交易             {int((~E['live']).sum()):>9,}"
        f"   （仅统计历史已够的）")
    log(f"  闸 3① OI 覆盖率低            {int((~E['g3a']).sum()):>9,}")
    log(f"  闸 3② OI 连续缺失过长        {int((~E['g3b']).sum()):>9,}")
    log(f"  闸 4  非加密资产              {int((~E['g4']).sum()):>9,}")
    log(f"  四闸全过                     {int(E['eligible'].sum()):>9,}")
    log(f"  取前 K={cfg.K} 后成为成员   {len(M):>9,}")
    log("=" * 80)

    # ---- 运行元信息 ----
    RUN_INFO.parent.mkdir(parents=True, exist_ok=True)
    info_prev = {}
    if RUN_INFO.exists():
        try:
            info_prev = json.loads(RUN_INFO.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            # 不能吞：这个文件里同时存着 Step 0–5 与 QA 的元信息。
            # 读失败还往下走，就会用"只有 step_6"的内容覆盖掉全部历史。
            log(f"  ✗ {RUN_INFO.name} 解析失败：{e}")
            log("    拒绝覆盖 —— 它里面还有 Step 0–5 的元信息。请先修复或移走该文件。")
            return 5
    info_prev["step_6_build_universe"] = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "months": len(months),
        "eligibility_rows": len(E),
        "members": len(M),
        "members_per_month_min": int(M.groupby("month").size().min()) if len(M) else 0,
        "members_per_month_max": int(M.groupby("month").size().max()) if len(M) else 0,
        "months_without_members": [m for m in months
                                   if m not in set(M["month"])],
        "gate_blocks": {
            "g1_stablecoin": int((~E["g1"]).sum()),
            "g2a_insufficient_history": int((~E["g2a"]).sum()),
            "g2b_not_trading": int((~E["live"]).sum()),
            "g3a_oi_coverage": int((~E["g3a"]).sum()),
            "g3b_oi_gap": int((~E["g3b"]).sum()),
            "g4_non_crypto": int((~E["g4"]).sum()),
        },
        # 闸 4 的判据来源与指纹：事后可核"这次用的是哪个 oracle"，以及重跑是否一致
        "exchange_info": {
            "from": ei_src["from"],
            "n_records": len(info),
            "fetched_at": ei_src["fetched_at"],
            "digest": ei_src["digest"],
        },
    }
    tmp_ri = RUN_INFO.with_name(f"{RUN_INFO.name}.{os.getpid()}.part")
    tmp_ri.write_text(json.dumps(info_prev, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    os.replace(tmp_ri, RUN_INFO)
    log(f"\n  总耗时 {time.time()-T_START:.0f}s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except cfg_mod.ConfigViolation as e:
        print(f"\n参数校验失败：\n{e}", file=sys.stderr)
        raise SystemExit(2)
