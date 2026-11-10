"""Phase 3 · build —— 三个构建步骤合一个文件

    python phase3_event/build.py forward --freq 1h    # 前向面板 → data/06_event_study/forward/
    python phase3_event/build.py events  --freq 1h    # 事件表   → data/06_event_study/events/
    python phase3_event/build.py panel                # 分析面板 → data/06_event_study/panel/

三步顺序是硬性的：前向面板 → 事件表 → 分析面板。
实验脚本只读 panel/，不再重算任何数据。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402

# ----------------------------------------------------------------------
# 第 1 步 · 前向面板（fwd / rv / 路径极值 / ok）
# ----------------------------------------------------------------------
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config as cfg_mod  # noqa: E402

EVENT = cfg_mod.EVENT
HORIZONS = tuple(EVENT.horizons)
EXPECTED_ROWS = {"1h": 7_252_717, "4h": 1_813_036, "8h": 906_426, "1d": 302_008}
EXPECTED_EVENTS = {"1h": 923_235, "4h": 227_107, "8h": 112_292, "1d": 37_585}
T_START = time.time()

def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.0f}s] {msg}", flush=True)

def read_panel(in_root: Path) -> pd.DataFrame:
    files = sorted((in_root / "02_features" / "features_1h").rglob("*.parquet"))
    if not files:
        raise SystemExit(f"找不到面板：{in_root / '02_features' / 'features_1h'}")
    d = pd.concat(
        [pd.read_parquet(p, columns=["symbol", "ts", "close", "high", "low"]) for p in files],
        ignore_index=True,
    )
    log(f"面板 {len(d):,} 行、{d.symbol.nunique()} 个合约")
    return d

def read_labels(in_root: Path, freq: str) -> pd.DataFrame:
    root = in_root / "05_regime" / "regime_labels" / f"freq={freq}"
    files = sorted(root.rglob("*.parquet"))
    if not files:
        raise SystemExit(f"找不到标签表：{root}")
    d = pd.concat(
        [pd.read_parquet(p, columns=["symbol", "ts_end", "regime"]) for p in files],
        ignore_index=True,
    )
    log(f"标签 {len(d):,} 行（freq={freq}）")
    return d

def lead(a: np.ndarray, k: int) -> np.ndarray:
    """out[i] = a[i + k]，越界补 NaN。"""
    if k == 0:
        return a.copy()
    pad = np.full((k, a.shape[1]), np.nan, dtype=a.dtype)
    return np.concatenate([a[k:], pad], axis=0)

def roll(a: np.ndarray, h: int, how: str) -> np.ndarray:
    """窗口 [i-h+1, i] 的聚合搬到行 i-(h-1)：即"从第 i 行起的 h 行"。"""
    r = getattr(pd.DataFrame(a).rolling(h), how)().to_numpy()
    return lead(r, h - 1)

def mdd(eq: np.ndarray, h: int) -> np.ndarray:
    """净值 eq 在窗口内的最大峰谷回撤；峰值从入场（净值 1.0）起算。"""
    peak = np.maximum(eq, 1.0)
    worst = np.minimum(0.0, eq / peak - 1.0)
    for j in range(1, h):
        cur = lead(eq, j)
        peak = np.maximum(peak, cur)
        worst = np.minimum(worst, cur / peak - 1.0)
    return worst

def run_fp() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 · 前向面板")
    ap.add_argument("--freq", default="1h")
    ap.add_argument("--in-root", default="data")
    ap.add_argument("--out-root", default="data/06_event_study")
    args = ap.parse_args()

    in_root, out_root = Path(args.in_root).resolve(), Path(args.out_root).resolve()
    freq = args.freq

    panel = read_panel(in_root)
    labels = read_labels(in_root, freq)

    symbols = sorted(panel.symbol.unique())
    colmap = {s: i for i, s in enumerate(symbols)}
    grid = pd.date_range(panel.ts.min(), panel.ts.max() + pd.Timedelta("1h"), freq="1h", tz="UTC")
    log(f"宽表网格 {len(grid):,} 小时：{grid[0]} … {grid[-1]}")

    def wide(name: str) -> np.ndarray:
        x = panel[["ts", "symbol", name]].drop_duplicates(["ts", "symbol"])
        w = x.pivot(index="ts", columns="symbol", values=name).reindex(grid)
        return w[symbols].to_numpy("float32")

    close, high, low = wide("close"), wide("high"), wide("low")
    del panel
    valid = ~np.isnan(close)
    entry = np.concatenate([np.full((1, close.shape[1]), np.nan, dtype="float32"), close[:-1]])
    entry_ok = np.concatenate([np.zeros((1, close.shape[1]), bool), valid[:-1]])
    lr2 = np.log(close / entry) ** 2

    (out_root / "wide").mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({"ts": grid, **{s: close[:, i] for i, s in enumerate(symbols)}}),
        out_root / "wide" / "close.parquet",
    )
    log(f"价格宽表已写出：{out_root / 'wide' / 'close.parquet'}")

    hour = ((labels.ts_end - grid[0]).dt.total_seconds() // 3600).astype("int64").to_numpy()
    if hour.min() < 0 or hour.max() >= len(grid):
        raise SystemExit(f"决策时刻越界：{hour.min()} … {hour.max()} / 网格 {len(grid)}")
    jj = labels.symbol.map(colmap).to_numpy().astype("int64")

    result = {
        "symbol": labels.symbol.to_numpy(),
        "ts_end": labels.ts_end.to_numpy(),
        "freq": freq,
    }
    for h in HORIZONS:
        fwd = lead(close, h - 1) / entry - 1.0
        rv = np.sqrt(roll(lr2, h, "sum"))
        exc_max = roll(high, h, "max") / entry - 1.0
        exc_min = roll(low, h, "min") / entry - 1.0
        ok = (roll(valid.astype("float32"), h, "sum") == h) & entry_ok
        mdl = mdd(close / entry, h)
        mds = mdd(2.0 - close / entry, h)
        for name, arr in [
            (f"fwd_{h}h", fwd),
            (f"rv_{h}h", rv),
            (f"exc_max_{h}h", exc_max),
            (f"exc_min_{h}h", exc_min),
            (f"mdl_{h}h", mdl),
            (f"mds_{h}h", mds),
        ]:
            result[name] = arr[hour, jj]
        result[f"ok_{h}h"] = ok[hour, jj]
        del fwd, rv, exc_max, exc_min, ok, mdl, mds

    out = pd.DataFrame(result)
    del result
    log(f"前向面板 {len(out):,} 行 × {out.shape[1]} 列")

    base = out_root / "forward" / f"freq={freq}"
    n = 0
    for (year, month), part in out.groupby([out.ts_end.dt.year, out.ts_end.dt.month], sort=True):
        d = base / f"year={year}"
        d.mkdir(parents=True, exist_ok=True)
        part.to_parquet(d / f"chunk={year}-{month:02d}.parquet", index=False)
        n += 1
    log(f"写出 {n} 个分区到 {base}")

    # ---------------- 闸门 ----------------
    lines = [f"build_forward_panel · freq={freq} · {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    bad = 0

    def check(label: str, ok: bool, detail: str) -> None:
        nonlocal bad
        bad += 0 if ok else 1
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {label}: {detail}")

    check("行数", len(out) == EXPECTED_ROWS[freq], f"{len(out):,} / 期望 {EXPECTED_ROWS[freq]:,}")
    dup = int(out.duplicated(["symbol", "ts_end"]).sum())
    check("(symbol, ts_end) 唯一", dup == 0, f"重复 {dup}")

    event = labels.regime.isin(["R1", "R2", "R3", "R4"]).to_numpy()
    check("事件数", int(event.sum()) == EXPECTED_EVENTS[freq],
          f"{int(event.sum()):,} / 期望 {EXPECTED_EVENTS[freq]:,}")

    ok_rates = {}
    for h in HORIZONS:
        r = float(np.mean(out[f"ok_{h}h"].to_numpy()[event]))
        ok_rates[h] = r
        check(f"ok_{h}h 覆盖率", r >= 0.995, f"{r:.4%}")
    if freq == "1h":
        check("ok_1h 覆盖率 ≈ 99.9973%", abs(ok_rates[1] - 0.999973) < 5e-5, f"{ok_rates[1]:.4%}")
        check("ok_24h 覆盖率 ≈ 99.8632%", abs(ok_rates[24] - 0.998632) < 5e-5, f"{ok_rates[24]:.4%}")

    f1 = out["fwd_1h"].to_numpy()[event]
    m1, s1 = float(np.nanmean(f1)), float(np.nanstd(f1))
    if freq == "1h":
        check("mean(fwd_1h) ≈ 1.654e-4", abs(m1 - 1.654e-4) <= 1.654e-4 * 0.05, f"{m1:.4e}")
        check("std(fwd_1h) ≈ 2.193e-2", abs(s1 - 2.193e-2) <= 2.193e-2 * 0.05, f"{s1:.4e}")

    ident = float(np.nanmax(np.abs(out["rv_1h"].to_numpy()[event] - np.abs(np.log1p(f1)))))
    check("rv_1h ≡ |log(1+fwd_1h)|", ident < 1e-6, f"max 差 {ident:.2e}")

    a24, b24 = out["rv_24h"].to_numpy()[event], out["rv_1h"].to_numpy()[event]
    m = np.isfinite(a24) & np.isfinite(b24)
    check("rv_24h ≥ rv_1h", bool((a24[m] >= b24[m]).all()), f"违例 {int((a24[m] < b24[m]).sum())}")

    body = "\n".join(lines) + "\n"
    print(body)
    print(f"[gate] build_forward_panel {freq}: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return 0 if bad == 0 else 1

# ----------------------------------------------------------------------
# 第 2 步 · 事件表（四格 + 命中 / 续势 / 路径）
# ----------------------------------------------------------------------
import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import config as cfg_mod  # noqa: E402


def cross_sectional_demean(df: pd.DataFrame, value_col: str,
                           hour_col: str = "hour",
                           out_col: str = "excess") -> tuple[pd.DataFrame, pd.Series]:
    """逐小时减去该小时 value_col 的等权均值，写进 out_col（原地，返回同一对象）。

    **这就是主口径 `y_raw` 的定义**，全项目只此一处实现。
    n_per_hour = 该小时参与去均值的非 NaN 行数。去均值基必须是全市场池
    （每小时约 173 个合约）；只用事件行会得到 7 个，两种做法差 44%。
    """
    v = df[value_col].to_numpy("float64")
    h = df[hour_col].to_numpy("int64")
    ok = np.isfinite(v)
    codes, uniq = pd.factorize(h)
    n = len(uniq)
    cnt = np.bincount(codes[ok], minlength=n).astype("float64")
    tot = np.bincount(codes[ok], weights=v[ok], minlength=n)
    mean = np.where(cnt > 0, tot / np.where(cnt > 0, cnt, 1.0), np.nan)
    df[out_col] = v - mean[codes]
    return df, pd.Series(cnt, index=uniq, name="n_per_hour")

EVENT = cfg_mod.EVENT
HORIZONS = tuple(EVENT.horizons)
REGIMES = ("R1", "R2", "R3", "R4")
EXPECTED_EVENTS = {"1h": 923_235, "4h": 227_107, "8h": 112_292, "1d": 37_585}
EXPECTED_BY_REGIME = {"1h": {"R1": 267_080, "R2": 184_686, "R3": 164_126, "R4": 307_343}}
LABEL_COLS = [
    "symbol", "ts_end", "regime", "excl_reason", "price_change", "oi_change",
    "price_thr", "oi_thr", "in_universe", "mkt_vol_state",
]
T_START = time.time()

def log(msg: str) -> None:
    print(f"[{time.time() - T_START:6.0f}s] {msg}", flush=True)

def in_sorted(keys: np.ndarray, table: np.ndarray) -> np.ndarray:
    """keys 的每个元素是否精确等于 table（已升序、无重复）里的某个元素。"""
    pos = np.searchsorted(table, keys)
    return (pos < table.size) & (table[np.minimum(pos, table.size - 1)] == keys)

def market_stats(fwd_files, sym_index, pool_key, n_hours, t0) -> dict:
    """全市场 pool 上的逐小时等权均值（市场中性化的去均值基）。

    ⚠️ 均值必须在 pool（label-ok 的全部有效行）上算，不能只在事件行上算 ——
    事件行的横截面均值不是"全市场"的（SPEC §二）。算出的 mu 供事件行按 hour 取值。

    返回 {h: {"mu": 按 hour 索引的均值数组（无观测的小时为 NaN）,
              "n": pool 行数, "dev": 去均值后逐小时均值的最大绝对值,
              "gap": 两条独立实现算出的均值之差}}
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
        # 两条独立实现（bincount vs factorize）算出来的必须是同一个均值
        exc = cross_sectional_demean(pd.DataFrame({"hour": hour, "fwd": x}), "fwd")[0]["excess"].to_numpy()
        gap = float(np.abs((x - exc) - mu[hour]).max())
        dev = float(np.abs(np.bincount(hour, weights=exc, minlength=n_hours)[nz] / cnt[nz]).max())
        stats[h] = {"mu": mu, "n": int(hour.size), "dev": dev, "gap": gap}
        log(f"h={h:2d}: pool {hour.size:,} 行 / {int(nz.sum()):,} 个小时，"
            f"|mu| 中位 {np.nanmedian(np.abs(mu)) * 1e4:.2f}bp，"
            f"逐小时均值 max|·| {dev:.1e}")
        del hour, x, exc, cnt
    return stats

def run_ev() -> int:
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
        raise SystemExit(f"找不到前向面板：{fwd_root}（先跑 build.py forward）")
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

    # 中间量不落盘 —— exc_* / mdl_* / mds_* 只用于派生 mfe/mae/mdd
    drop = [c for h in HORIZONS for c in (f"exc_max_{h}h", f"exc_min_{h}h", f"mdl_{h}h", f"mds_{h}h")]
    events = events.drop(columns=[c for c in drop if c in events.columns])
    log(f"删掉 {len(drop)} 个中间列，剩 {events.shape[1]} 列")

    # ---- 新增两族列（SPEC §二）：市场中性收益、价格冲击幅度 ----
    hour_ev = events["hour"].to_numpy()
    for h in HORIZONS:
        fwd = events[f"fwd_{h}h"].to_numpy("float64")
        ok = events[f"ok_{h}h"].to_numpy(bool)
        # 事件行只是 pool 的子集：按 hour 取【全市场】均值，不是事件行自己的均值
        events[f"excess_fwd_{h}h"] = np.where(ok, fwd - stats[h]["mu"][hour_ev], np.nan)
    log(f"新增 {len(HORIZONS)} 列（excess_fwd × {len(HORIZONS)}），共 {events.shape[1]} 列")

    out = out_root / "events"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"events_{freq}.parquet"
    events.to_parquet(path, index=False)
    log(f"写出 {path}（{path.stat().st_size / 1e6:.0f} MB）")

    # ---------------- 闸门 ----------------
    lines = [f"build.py events · freq={freq} · {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
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

    # ---- 新增列的闸门 ----
    new_cols = [f"excess_fwd_{h}h" for h in HORIZONS]
    check("新列追加在末尾、原有列未重排", list(events.columns[-len(new_cols):]) == new_cols,
          f"{events.shape[1]} 列 = 原有 {events.shape[1] - len(new_cols)} + 新 {len(new_cols)}")
    for h in HORIZONS:
        s = stats[h]
        check(f"excess_fwd_{h}h 逐小时均值为 0", s["dev"] <= 1e-12,
              f"全市场 pool {s['n']:,} 行上 max|小时均值| = {s['dev']:.1e}"
              f"（demean 内部均值 vs 拼列均值 max 差 {s['gap']:.1e}）")
        lines.append(f"  [note] h={h:2d}: |mu| 中位 {np.nanmedian(np.abs(s['mu'])) * 1e4:.2f}bp")

    ok24 = events["ok_24h"].to_numpy(bool)
    raw24 = events["fwd_24h"].to_numpy("float64")[ok24]
    exc24 = events["excess_fwd_24h"].to_numpy("float64")[ok24]
    lines.append(f"  [note] h=24 市场中性：mean(fwd_24h) {np.nanmean(raw24) * 100:+.4f}% → "
                 f"mean(excess_fwd_24h) {np.nanmean(exc24) * 100:+.4f}%，"
                 f"调整量 {np.nanmean(raw24 - exc24) * 100:+.4f}pp（事件时点的全市场等权均值）")
    lines.append(f"  [note] 若只在事件行上算小时均值，每小时的组内和恒为 0、mean(excess) 必然 ≈ 0；"
                 f"本表的 {np.nanmean(exc24) * 100:+.4f}% 用的是全市场均值，所以不为 0")
    body = "\n".join(lines) + "\n"
    print(body)
    print(body)
    print(f"[gate] build.py events {freq}: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return 0 if bad == 0 else 1

# ----------------------------------------------------------------------
# 第 3 步 · 分析面板（headline × 状态 × 前向期）
# ----------------------------------------------------------------------
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

from config import EVENT  # noqa: E402

T0 = pd.Timestamp("2021-12-01", tz="UTC")
HORIZONS = list(EVENT.horizons)
LAB_ROOT = ROOT / "data/05_regime/regime_labels/freq=1h"
FWD_ROOT = ROOT / "data/06_event_study/forward/freq=1h"
OUT_ROOT = ROOT / "data/06_event_study/panel/freq=1h"

LAB_COLS = ["symbol", "ts_end", "price_change", "oi_change", "price_thr", "oi_thr",
            "in_universe", "excl_reason",
            "funding_negative", "funding_neutral", "funding_high", "funding_extreme"]

def _hour(ts: pd.Series) -> np.ndarray:
    return ((ts - T0).dt.total_seconds() // 3600).to_numpy("int64")

def load_labels():
    files = sorted(LAB_ROOT.rglob("*.parquet"))
    syms: set[str] = set()
    for p in files:
        syms.update(pd.read_parquet(p, columns=["symbol"])["symbol"].unique().tolist())
    sym_index = {s: i for i, s in enumerate(sorted(syms))}
    n_sym = len(sym_index)

    parts = []
    n_label = n_ok = 0
    for p in files:
        L = pd.read_parquet(p, columns=LAB_COLS)
        n_label += len(L)
        L = L.loc[L["excl_reason"].to_numpy() == "ok"]
        n_ok += len(L)
        parts.append(pd.DataFrame({
            "hour": _hour(L["ts_end"]),
            "symbol": L["symbol"].map(sym_index).to_numpy("int32"),
            "price_change": L["price_change"].to_numpy("float64"),
            "oi_change": L["oi_change"].to_numpy("float64"),
            "price_thr": L["price_thr"].to_numpy("float64"),
            "oi_thr": L["oi_thr"].to_numpy("float64"),
            "uni": L["in_universe"].to_numpy(dtype=bool),
            "fneg": L["funding_negative"].to_numpy(dtype=bool),
            "fmid": L["funding_neutral"].to_numpy(dtype=bool),
            "fhi": L["funding_high"].to_numpy(dtype=bool),
            "fext": L["funding_extreme"].to_numpy(dtype=bool),
        }))
    d = pd.concat(parts, ignore_index=True)
    d["key"] = d["hour"].to_numpy("int64") * n_sym + d["symbol"].to_numpy("int64")
    return sym_index, n_sym, d, {"n_files": len(files), "n_label": n_label, "n_ok": n_ok}

def load_forward_h(sym_index: dict[str, int], h: int):
    n_sym = len(sym_index)
    files = sorted(FWD_ROOT.rglob("*.parquet"))
    keys, fwd, rv, ok = [], [], [], []
    for p in files:
        F = pd.read_parquet(p, columns=["symbol", "ts_end", f"fwd_{h}h", f"rv_{h}h", f"ok_{h}h"])
        keys.append(_hour(F["ts_end"]) * n_sym + F["symbol"].map(sym_index).to_numpy("int64"))
        fwd.append(pd.to_numeric(F[f"fwd_{h}h"], errors="coerce").to_numpy("float64"))
        rv.append(pd.to_numeric(F[f"rv_{h}h"], errors="coerce").to_numpy("float64"))
        ok.append(np.asarray(pd.to_numeric(F[f"ok_{h}h"], errors="coerce").fillna(0)
                             .to_numpy("float64") > 0.5))
    return (np.concatenate(keys), np.concatenate(fwd), np.concatenate(rv), np.concatenate(ok))

def run_pn() -> int:
    t0 = time.time()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    sym_index, n_sym, lab, meta = load_labels()
    print(f"标签表 {meta['n_files']} 分区 / {meta['n_label']:,} 行 → label-ok {meta['n_ok']:,} 行",
          flush=True)
    pd.DataFrame({"code": np.arange(n_sym),
                  "symbol": sorted(sym_index, key=sym_index.get)}).to_parquet(
        OUT_ROOT / "symbols.parquet", index=False)

    pool_keys = np.sort(lab["key"].to_numpy("int64"))
    if np.unique(pool_keys).size != pool_keys.size:
        raise SystemExit("池子里 (hour, symbol) 重复")
    lab = lab.loc[np.argsort(lab["key"].to_numpy("int64"), kind="stable")].reset_index(drop=True)
    lab_keys = lab["key"].to_numpy("int64")

    gate = []

    def check(name, cond, detail=""):
        gate.append((bool(cond), name, detail))

    check("池子 = 7,010,789 行", lab_keys.size == 7_010_789, f"{lab_keys.size:,}")
    check("符号表 = 285 个合约", n_sym == 285, str(n_sym))

    for h in HORIZONS:
        fkey, fwd, rv, ok = load_forward_h(sym_index, h)
        pos = np.searchsorted(lab_keys, fkey)
        hit = pos < lab_keys.size
        hit[hit] = lab_keys[pos[hit]] == fkey[hit]
        k = fkey[hit]
        order = np.argsort(k, kind="stable")
        k, f, r, o = k[order], fwd[hit][order], rv[hit][order], ok[hit][order]

        df, nph = cross_sectional_demean(pd.DataFrame({"hour": k // n_sym, "fwd": f}),
                                        "fwd", out_col="exc")
        exc = df["exc"].to_numpy("float64")
        # 去均值自检：逐小时均值必须为 0（残差在 1e-16 量级）
        hz = (k // n_sym).astype("int64")
        hz = hz - hz.min()
        okf = np.isfinite(exc)
        cnt_h = np.bincount(hz[okf])
        tot_h = np.bincount(hz[okf], weights=exc[okf])
        nz_h = cnt_h > 0                     # 空小时不进分母，否则 0/0 = NaN
        resid = float(np.abs(tot_h[nz_h] / cnt_h[nz_h]).max())

        m = np.searchsorted(lab_keys, k)
        sub = lab.iloc[m]
        keep = sub["uni"].to_numpy(dtype=bool) & o & np.isfinite(exc)
        pc = sub["price_change"].to_numpy("float64")[keep]
        pt = sub["price_thr"].to_numpy("float64")[keep]
        oc = sub["oi_change"].to_numpy("float64")[keep]
        ot = sub["oi_thr"].to_numpy("float64")[keep]
        rvk = r[keep]

        dirv = np.where(pc > pt, 1, np.where(pc < -pt, -1, 0)).astype("int8")
        oi3 = np.where(np.abs(oc) > ot, np.sign(oc), 0).astype("int8")
        cell = np.where(dirv == 0, -1,
                        np.where(oi3 == 0, 0,
                                 np.where(dirv > 0, np.where(oi3 > 0, 1, 2),
                                          np.where(oi3 > 0, 3, 4)))).astype("int8")
        fund = np.full(len(pc), -1, dtype="int8")
        for code, col in ((0, "fneg"), (1, "fmid"), (2, "fhi"), (3, "fext")):
            fund[sub[col].to_numpy(dtype=bool)[keep]] = code

        panel = pd.DataFrame({
            "symbol": sub["symbol"].to_numpy("int32")[keep],
            "hour": sub["hour"].to_numpy("int32")[keep],
            "dir": dirv, "oi3": oi3, "cell": cell, "fund": fund,
            "y_raw": exc[keep],                 # 市场中性，**不截尾**（唯一口径）
            "lrv": np.where(rvk > 0, np.log(np.where(rvk > 0, rvk, 1.0)), np.nan),
        })
        panel.to_parquet(OUT_ROOT / f"h={h}.parquet", index=False)

        n_ev = int((cell > 0).sum())
        print(f"  h={h:<3} 面板 {len(panel):,} 行 / 合约 {panel['symbol'].nunique()} / "
              f"事件 {n_ev:,} / 价格超阈 {int((cell >= 0).sum()):,} / "
              f"去均值基 {float(nph.median()):.0f} 行/小时", flush=True)
        check(f"h={h} 去均值后逐小时均值为 0", resid < 1e-12, f"max|小时均值| {resid:.1e}")
        check(f"h={h} 去均值基中位数 ∈ [150,200]", 150 <= nph.median() <= 200,
              f"{nph.median():.0f}")
        check(f"h={h} 面板只含 headline 行", bool((sub["uni"].to_numpy(dtype=bool)[keep]).all()), f"{len(panel):,} 行")
        check(f"h={h} cell 取值合法", bool(np.isin(np.unique(cell), [-1, 0, 1, 2, 3, 4]).all()),
              f"{sorted(np.unique(cell).tolist())}")

    n_pass = sum(x for x, _, _ in gate)
    lines = ["event_study · build_panel（分析面板）", ""]
    lines += [f"  [{'PASS' if x else 'FAIL'}] {n}  {d}" for x, n, d in gate]
    lines.append(f"\n闸门汇总：PASS {n_pass} / FAIL {len(gate) - n_pass}")
    print("\n".join(lines))
    for x, n, d in gate:
        print(f"[{'PASS' if x else 'FAIL'}] {n}  {d}")
    print(f"闸门汇总：PASS {n_pass} / FAIL {len(gate) - n_pass}；耗时 {time.time()-t0:.0f}s")
    return 0 if n_pass == len(gate) else 1


# ============================================================================
# 入口
# ============================================================================
def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 3 · build")
    ap.add_argument("step", choices=["forward", "events", "panel"])
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    sys.argv = [sys.argv[0]] + a.rest
    return {"forward": run_fp, "events": run_ev, "panel": run_pn}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
