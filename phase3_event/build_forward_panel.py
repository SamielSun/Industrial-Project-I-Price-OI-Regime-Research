"""Phase 3 · build_forward_panel —— 前向面板

从 data/02_features/features_1h 建价格宽表（行 = 小时，列 = 合约），按标签表的决策时刻
（ts_end）取回四个前向期的度量：fwd / rv / exc_max / exc_min / mdl / mds / ok。

口径见 phase3_event/PHASE3_GUIDANCE.md §一 与 §六。

用法：
    python phase3_event/build_forward_panel.py --freq 1h
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


def main() -> int:
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
    docs = out_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / f"step3_checks_{freq}.txt").write_text(body, encoding="utf-8")
    print(body)
    print(f"[gate] build_forward_panel {freq}: {'PASS' if bad == 0 else 'FAIL'} ({bad} 项)")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
