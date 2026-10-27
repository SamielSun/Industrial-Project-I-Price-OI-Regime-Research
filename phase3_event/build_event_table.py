"""Phase 3 · build_event_table —— 事件表

把 Phase 2 的标签表与 build_forward_panel 的前向面板 join 起来，算方向、路径、三分类，
筛出 R1–R4 的事件行写盘。

口径见 phase3_event/PHASE3_GUIDANCE.md §一、§六，以及 DECISIONS.md。

v2 新增三族列（SPEC §二），追加在原有列之后，原有列一列不动：
    excess_fwd_{h}h   fwd_{h}h 逐小时减去【全市场等权均值】（stats_core.cross_sectional_demean）。
                      均值在全部有效行上算 —— label 层 excl_reason == "ok" 的 7,010,789 行，
                      再与各频率的 ok_{h}h 取交集（1h 的 h=24 为 7,002,655 行）。
                      ⚠️ 不能只在 923,235 个事件行上算横截面均值：事件子集不是"全市场"。
    winsor_fwd_{h}h   excess_fwd_{h}h 的 1%/99% 截尾。阈值同样取自全市场 pool（与均值同一个
                      总体），事件行只是取值子集 —— 这样对照行 / 基准行与事件行用的是同一组阈值。
    shock             abs(price_change) / price_thr，价格冲击幅度；事件行恒 ≥ 1。

用法：
    python phase3_event/build_event_table.py --freq 1h
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))          # phase3_event/：stats_core
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # 项目根：config
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402
from stats_core import (  # noqa: E402
    WINSOR_LOWER,
    WINSOR_UPPER,
    cross_sectional_demean,
    kurtosis,
)

EVENT = cfg_mod.EVENT
HORIZONS = tuple(EVENT.horizons)
REGIMES = ("R1", "R2", "R3", "R4")
EXPECTED_EVENTS = {"1h": 923_235, "4h": 227_107, "8h": 112_292, "1d": 37_585}
EXPECTED_BY_REGIME = {"1h": {"R1": 267_080, "R2": 184_686, "R3": 164_126, "R4": 307_343}}
LABEL_COLS = [
    "symbol", "ts_end", "regime", "excl_reason", "price_change", "oi_change",
    "price_thr", "oi_thr", "in_universe", "mkt_vol_state",
    "funding_negative", "funding_neutral", "funding_high", "funding_extreme",
    "funding_p25", "funding_p75", "funding_p90",
]
T_START = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.0f}s] {msg}", flush=True)


def in_sorted(keys: np.ndarray, table: np.ndarray) -> np.ndarray:
    """keys 的每个元素是否精确等于 table（已升序、无重复）里的某个元素。"""
    pos = np.searchsorted(table, keys)
    return (pos < table.size) & (table[np.minimum(pos, table.size - 1)] == keys)


def market_stats(fwd_files, sym_index, pool_key, n_hours, t0) -> dict:
    """全市场 pool 上的逐小时等权均值与 1%/99% 截尾阈值。

    ⚠️ 均值必须在 pool（label-ok 的全部有效行）上算，不能只在事件行上算 ——
    事件行的横截面均值不是"全市场"的（SPEC §二）。算出的 mu 供事件行按 hour 取值。

    返回 {h: {"mu": 按 hour 索引的均值数组（无观测的小时为 NaN）, "lo"/"hi": 截尾阈值,
              "n": pool 行数, "dev": 去均值后逐小时均值的最大绝对值,
              "gap": 两条独立实现算出的均值之差, "clip": pool 里被压的观测占比}}
    """
    n_sym = len(sym_index)
    parts = {h: ([], []) for h in HORIZONS}
    for p in fwd_files:
        f = pd.read_parquet(
            p, columns=["symbol", "ts_end"]
            + [f"ok_{h}h" for h in HORIZONS] + [f"fwd_{h}h" for h in HORIZONS]
        )
        hour = ((f.ts_end - t0).dt.total_seconds() // 3600).to_numpy("int64")
        inpool = in_sorted(hour * n_sym + f.symbol.map(sym_index).to_numpy("int64"), pool_key)
        for h in HORIZONS:
            m = inpool & f[f"ok_{h}h"].to_numpy(bool)
            parts[h][0].append(hour[m])
            parts[h][1].append(f[f"fwd_{h}h"].to_numpy("float64")[m])
    log(f"pool 前向取值完毕（{len(fwd_files)} 个分区）")

    stats = {}
    for h in HORIZONS:
        hour = np.concatenate(parts[h][0])
        x = np.concatenate(parts[h][1])
        del parts[h]
        # 逐小时等权均值 = 每小时的和 ÷ 有效行数（等权 = 一行一票，不按 OI / 成交额加权）
        cnt = np.bincount(hour, minlength=n_hours)
        nz = cnt > 0
        mu = np.full(n_hours, np.nan)
        mu[nz] = np.bincount(hour, weights=x, minlength=n_hours)[nz] / cnt[nz]
        # stats_core 的实现（原地写入 excess 列）—— 两条路算出来的必须是同一个均值
        exc = cross_sectional_demean(pd.DataFrame({"hour": hour, "fwd": x}), "fwd")[0]["excess"].to_numpy()
        gap = float(np.abs((x - exc) - mu[hour]).max())
        dev = float(np.abs(np.bincount(hour, weights=exc, minlength=n_hours)[nz] / cnt[nz]).max())
        # 与 stats_core.winsorize(exc) 同一组分位、同一个 clip 语义。阈值要留下：
        # 事件行是 pool 的子集，必须按同一组阈值压，不能按事件行自己的分位压。
        lo, hi = (float(v) for v in np.nanquantile(exc, [WINSOR_LOWER, WINSOR_UPPER]))
        clip = float(np.mean(np.clip(exc, lo, hi) != exc))
        stats[h] = {"mu": mu, "lo": lo, "hi": hi, "n": int(hour.size),
                    "dev": dev, "gap": gap, "clip": clip}
        log(f"h={h:2d}: pool {hour.size:,} 行 / {int(nz.sum()):,} 个小时，"
            f"|mu| 中位 {np.nanmedian(np.abs(mu)) * 1e4:.2f}bp，"
            f"截尾 [{lo:+.4%}, {hi:+.4%}]，逐小时均值 max|·| {dev:.1e}")
        del hour, x, exc, cnt
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 · 事件表")
    ap.add_argument("--freq", default="1h")
    ap.add_argument("--in-root", default="data")
    ap.add_argument("--out-root", default="data/06_event_study")
    args = ap.parse_args()

    in_root, out_root = Path(args.in_root).resolve(), Path(args.out_root).resolve()
    freq = args.freq
    t0 = pd.Timestamp("2021-12-01", tz="UTC")

    lab_root = in_root / "05_regime" / "regime_labels" / f"freq={freq}"
    files = sorted(lab_root.rglob("*.parquet"))
    if not files:
        raise SystemExit(f"找不到标签表：{lab_root}")
    labels = pd.concat([pd.read_parquet(p, columns=LABEL_COLS) for p in files], ignore_index=True)
    log(f"标签 {len(labels):,} 行")

    # ---- 全市场 pool：label 层 excl_reason == "ok" 的行（1h 为 7,010,789 行） ----
    # 逐小时均值要在这群行上算。编成 int64 键（hour × 合约数 + 合约号），供前向面板分片判成员。
    sym_index = {s: i for i, s in enumerate(sorted(labels.symbol.unique()))}
    n_sym = len(sym_index)
    lab_hour = ((labels.ts_end - t0).dt.total_seconds() // 3600).to_numpy("int64")
    n_hours = int(lab_hour.max()) + 1
    pool = labels.excl_reason.eq("ok").to_numpy()
    pool_key = np.sort(lab_hour[pool] * n_sym + labels.symbol.map(sym_index).to_numpy("int64")[pool])
    log(f"全市场 pool（label-ok）{int(pool.sum()):,} 行 / {n_sym} 个合约 / {n_hours:,} 个小时位")
    del lab_hour, pool

    ev = labels[labels.regime.isin(REGIMES)].copy()
    del labels
    log(f"事件 {len(ev):,} 行")

    # ---- 前向面板：先在 pool 上算均值与阈值，再逐文件 join 事件行 ----
    fwd_root = out_root / "forward" / f"freq={freq}"
    fwd_files = sorted(fwd_root.rglob("*.parquet"))
    if not fwd_files:
        raise SystemExit(f"找不到前向面板：{fwd_root}（先跑 build_forward_panel.py）")
    stats = market_stats(fwd_files, sym_index, pool_key, n_hours, t0)
    del sym_index, pool_key

    # ---- 逐文件 join 前向面板：只保留事件行，控制内存 ----
    parts = []
    for p in fwd_files:
        f = pd.read_parquet(p).drop(columns=["freq"])
        m = ev.merge(f, on=["symbol", "ts_end"], how="inner", validate="1:1")
        if len(m):
            parts.append(m)
    events = pd.concat(parts, ignore_index=True)
    del parts
    if len(events) != len(ev):
        raise SystemExit(f"join 行数错：{len(events):,} != 事件 {len(ev):,}（内连接应一一对应）")
    events = events.sort_values(["symbol", "ts_end"], kind="stable").reset_index(drop=True)
    log(f"join 后 {len(events):,} 行 × {events.shape[1]} 列")

    # ---- 派生列 ----
    events["freq"] = freq
    events["hour"] = ((events.ts_end - t0).dt.total_seconds() // 3600).astype("int64")
    events["d"] = np.sign(events.price_change.to_numpy()).astype("int8")

    for h in HORIZONS:
        f = events[f"fwd_{h}h"].to_numpy(dtype="float64")
        okmask = events[f"ok_{h}h"].to_numpy(dtype=bool)
        d = events["d"].to_numpy()
        pc = events["price_change"].to_numpy()
        sig = np.sign(f)
        events[f"y_sig_{h}h"] = (d * f).astype("float32")

        def masked(vals: np.ndarray, mask=okmask) -> pd.Series:
            out = vals.astype("float32")
            out[~mask] = np.nan
            return pd.Series(out, index=events.index)

        events[f"mfe_{h}h"] = masked(np.where(d > 0, events[f"exc_max_{h}h"], -events[f"exc_min_{h}h"]))
        events[f"mae_{h}h"] = masked(np.where(d > 0, events[f"exc_min_{h}h"], -events[f"exc_max_{h}h"]))
        events[f"mdd_{h}h"] = masked(np.where(d > 0, events[f"mdl_{h}h"], events[f"mds_{h}h"]))
        events[f"hit_{h}h"] = masked(((sig == d) & (f != 0)).astype("float32"))
        events[f"cont_{h}h"] = masked((sig == np.sign(pc)).astype("float32"))
        events[f"rev_{h}h"] = masked((sig == -np.sign(pc)).astype("float32"))
        events[f"flat_{h}h"] = masked((f == 0).astype("float32"))

    # D6：中间量不落盘 —— exc_* / mdl_* / mds_* 只用于派生 mfe/mae/mdd
    drop = [c for h in HORIZONS for c in (f"exc_max_{h}h", f"exc_min_{h}h", f"mdl_{h}h", f"mds_{h}h")]
    events = events.drop(columns=[c for c in drop if c in events.columns])
    log(f"删掉 {len(drop)} 个中间列，剩 {events.shape[1]} 列")

    # ---- 新增三族列（SPEC §二）：市场中性收益、截尾收益、价格冲击幅度 ----
    hour_ev = events["hour"].to_numpy()
    for h in HORIZONS:
        fwd = events[f"fwd_{h}h"].to_numpy("float64")
        ok = events[f"ok_{h}h"].to_numpy(bool)
        # 事件行只是 pool 的子集：按 hour 取【全市场】均值，不是事件行自己的均值
        events[f"excess_fwd_{h}h"] = np.where(ok, fwd - stats[h]["mu"][hour_ev], np.nan)
    for h in HORIZONS:
        events[f"winsor_fwd_{h}h"] = np.clip(events[f"excess_fwd_{h}h"].to_numpy("float64"),
                                             stats[h]["lo"], stats[h]["hi"])
    events["shock"] = np.abs(events.price_change.to_numpy("float64")) / events.price_thr.to_numpy("float64")
    log(f"新增 9 列（excess_fwd/winsor_fwd × {len(HORIZONS)} + shock），共 {events.shape[1]} 列")

    out = out_root / "events"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"events_{freq}.parquet"
    events.to_parquet(path, index=False)
    log(f"写出 {path}（{path.stat().st_size / 1e6:.0f} MB）")

    # ---------------- 闸门 ----------------
    lines = [f"build_event_table · freq={freq} · {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    bad = 0

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数", len(events) == EXPECTED_EVENTS[freq], f"{len(events):,} / 期望 {EXPECTED_EVENTS[freq]:,}")
    counts = events.regime.value_counts()
    exp = EXPECTED_BY_REGIME.get(freq)
    if exp:
        got = {r: int(counts.get(r, 0)) for r in REGIMES}
        check("R1–R4 计数", got == exp, f"{got}")
    check("d == 0 的行数", int((events.d == 0).sum()) == 0, f"{int((events.d == 0).sum())}")
    for h in HORIZONS:
        rate = float(1 - events[f"ok_{h}h"].mean())
        check(f"n_invalid_{h}h 占比", rate <= 0.005, f"{rate:.4%}")
    for h in HORIZONS:
        m = events[f"ok_{h}h"].to_numpy()
        mfe = events[f"mfe_{h}h"].to_numpy()[m]
        mae = events[f"mae_{h}h"].to_numpy()[m]
        exc = int(((mfe < 0) | (mae > 0)).sum())
        lines.append(f"  [note] mfe/mae 符号例外 h={h}: {exc} ({exc / max(int(m.sum()), 1):.4%})")
        mdd = events[f"mdd_{h}h"].to_numpy()[m]
        check(f"mdd <= 0 恒成立 h={h}", bool(np.all(mdd <= 0)), f"违例 {int((mdd > 0).sum())}")
        chk = events[f"cont_{h}h"].to_numpy()[m] + events[f"rev_{h}h"].to_numpy()[m] + events[f"flat_{h}h"].to_numpy()[m]
        check(f"cont+rev+flat = 1 h={h}", bool(np.allclose(chk, 1.0, atol=1e-6)), f"最大偏差 {np.abs(chk - 1).max():.2e}")
        hh = events[f"hit_{h}h"].to_numpy()[m]
        cc = events[f"cont_{h}h"].to_numpy()[m]
        check(f"hit == cont h={h}", bool(np.array_equal(hh, cc)), "（四状态上两者是同一个数）")

    # ---- 新增三族列的闸门 ----
    new_cols = ([f"excess_fwd_{h}h" for h in HORIZONS]
                + [f"winsor_fwd_{h}h" for h in HORIZONS] + ["shock"])
    check("新列追加在末尾、原有列未重排", list(events.columns[-len(new_cols):]) == new_cols,
          f"{events.shape[1]} 列 = 原有 {events.shape[1] - len(new_cols)} + 新 {len(new_cols)}")
    for h in HORIZONS:
        s = stats[h]
        check(f"excess_fwd_{h}h 逐小时均值为 0", s["dev"] <= 1e-12,
              f"全市场 pool {s['n']:,} 行上 max|小时均值| = {s['dev']:.1e}"
              f"（demean 内部均值 vs 拼列均值 max 差 {s['gap']:.1e}）")
        lines.append(f"  [note] h={h:2d}: |mu| 中位 {np.nanmedian(np.abs(s['mu'])) * 1e4:.2f}bp；"
                     f"pool 上被压 {s['clip']:.2%}（口径 {WINSOR_LOWER:.0%}/{WINSOR_UPPER:.0%}）；"
                     f"截尾阈值 [{s['lo']:+.4%}, {s['hi']:+.4%}]")

    ok24 = events["ok_24h"].to_numpy(bool)
    raw24 = events["fwd_24h"].to_numpy("float64")[ok24]
    exc24 = events["excess_fwd_24h"].to_numpy("float64")[ok24]
    win24 = events["winsor_fwd_24h"].to_numpy("float64")[ok24]
    n_clip = int(((exc24 < stats[24]["lo"]) | (exc24 > stats[24]["hi"])).sum())
    check("winsor_fwd_24h 峰度 < 20", kurtosis(win24) < 20,
          f"峰度 {kurtosis(win24):.1f}（原始 fwd_24h {kurtosis(raw24):.1f} / excess_fwd_24h {kurtosis(exc24):.1f}）")
    win_all = events["winsor_fwd_24h"].to_numpy("float64")
    raw_all = events["fwd_24h"].to_numpy("float64")
    for r in REGIMES:
        mr = ok24 & events.regime.eq(r).to_numpy()
        lines.append(f"  [note] winsor_fwd_24h 峰度 {r}: {kurtosis(win_all[mr]):.1f}"
                     f"（原始 fwd_24h {kurtosis(raw_all[mr]):.1f}）")
    shock = events["shock"].to_numpy()
    check("shock >= 1", bool(shock.min() >= 1.0),
          f"min {shock.min():.6f} / p1 {np.percentile(shock, 1):.4f} / 中位 {np.median(shock):.3f} / max {shock.max():.0f}")
    lines.append(f"  [note] h=24 市场中性：mean(fwd_24h) {np.nanmean(raw24) * 100:+.4f}% → "
                 f"mean(excess_fwd_24h) {np.nanmean(exc24) * 100:+.4f}%，"
                 f"调整量 {np.nanmean(raw24 - exc24) * 100:+.4f}pp（事件时点的全市场等权均值）")
    lines.append(f"  [note] 若只在事件行上算小时均值，每小时的组内和恒为 0、mean(excess) 必然 ≈ 0；"
                 f"本表的 {np.nanmean(exc24) * 100:+.4f}% 用的是全市场均值，所以不为 0")
    lines.append(f"  [note] winsor_fwd_24h 阈值取自全市场 [{stats[24]['lo']:+.4%}, {stats[24]['hi']:+.4%}]，"
                 f"事件行被压 {n_clip:,} 行（{n_clip / ok24.sum():.2%}）")
    lo_e, hi_e = (float(v) for v in np.nanquantile(exc24, [WINSOR_LOWER, WINSOR_UPPER]))
    lines.append(f"  [note] 口径敏感性（不落盘）：若改用事件行自身分位 [{lo_e:+.4%}, {hi_e:+.4%}]，"
                 f"峰度 {kurtosis(np.clip(exc24, lo_e, hi_e)):.1f} —— 本表不取这一组，"
                 f"因为对照行 / 基准行要用同一组阈值")

    body = "\n".join(lines) + "\n"
    docs = out_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / f"step4_checks_{freq}.txt").write_text(body, encoding="utf-8")
    print(body)
    print(f"[gate] build_event_table {freq}: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
