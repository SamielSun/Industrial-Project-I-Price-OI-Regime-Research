"""Phase 3 · 实验 12 —— 事件路径（事件前后各 24 小时的累计超额收益）

    python phase3_event/experiment/event_path.py

问题：四格事件在 T 之前和之后的累计超额收益长什么样？
  · 之前的一段用来检查"事件是不是把已经发生的行情拿来当信号"
  · 之后的一段是市场对事件的反应速度

口径：
  · 小时收益 r_t = log(close_t / close_{t-1})，逐小时减去全市场等权均值（与主口径一致）
  · 累计从 T−24 起算，k = −24 … +24，共 49 个点
  · 缺价的格子按 0 收益处理（合约基本连续）
  · SE 按合约聚类；样本 = headline（与实验 1 同）
  · **不截尾**（路径要看真实轨迹，截尾会把尾部削掉）
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "phase3_event"))


PANEL = ROOT / "data/06_event_study/panel/freq=1h"
WIDE = ROOT / "data/06_event_study/wide/close.parquet"
TABLE_DIR = ROOT / "data/06_event_study/tables/freq=1h"
KS = np.arange(-24, 25)


def main() -> int:
    t0 = time.time()
    c = pd.read_parquet(WIDE)
    ts = pd.to_datetime(c["ts"], utc=True)
    syms = [s for s in c.columns if s != "ts"]
    close = c[syms].to_numpy("float64")
    n_t, n_s = close.shape
    print(f"价格宽表 {n_t:,} 小时 × {n_s} 合约", flush=True)

    panel = pd.read_parquet(PANEL / "h=1.parquet")
    # panel 的 symbol 是编码；宽表的列是币名，必须显式映射，不能假设顺序一致
    smap = pd.read_parquet(PANEL / "symbols.parquet")
    code2name = dict(zip(smap["code"].to_numpy("int64"), smap["symbol"].to_numpy()))
    col_of = {s: i for i, s in enumerate(syms)}
    name_of_code = np.array([code2name.get(i) for i in range(285)], dtype=object)
    t0c = pd.Timestamp(ts.iloc[0])
    hours = ((ts - t0c).dt.total_seconds() // 3600).to_numpy("int64")

    # 市场基准 = label-ok 池（与 build.py 的 market_stats 同源，每小时约 176-244 个合约）。
    # 不是 panel 池：panel 只含价格越阈的合约（约 50 个/小时），两者的小时均值在
    # 剧烈波动时可差 ±20-26bp，那样算出来的超额与 y_raw 不同口径。
    pool = np.zeros(close.shape, dtype=bool)
    _lab_dir = ROOT / "data/05_regime/regime_labels/freq=1h"
    _n_lab = 0
    for _p in sorted(_lab_dir.rglob("*.parquet")):
        _d = pd.read_parquet(_p, columns=["symbol", "ts_end", "excl_reason"])
        _d = _d[_d["excl_reason"] == "ok"]
        _col = _d["symbol"].map(col_of)
        _h = ((_d["ts_end"] - t0c).dt.total_seconds() // 3600).astype("int64")
        _m = _col.notna() & (_h >= 0) & (_h < n_t)
        pool[_h[_m].to_numpy(), _col[_m].astype("int64").to_numpy()] = True
        _n_lab += int(_m.sum())
    print(f"pool 掩码 {int(pool.sum()):,} 个 (小时, 合约)，label-ok 行 {_n_lab:,}", flush=True)

    # 逐小时对数超额收益的累加：exc_h = ln r_h − 池内同时刻等权均值，再 cumsum
    lr = np.zeros_like(close)
    lr[1:] = np.log(np.where((close[1:] > 0) & (close[:-1] > 0),
                             close[1:] / np.where(close[:-1] > 0, close[:-1], 1.0), 1.0))
    ok = np.isfinite(lr) & pool
    lr = np.where(ok, lr, 0.0)
    n_ok = ok.sum(axis=1)
    mu = lr.sum(axis=1) / np.maximum(n_ok, 1)
    exc = lr - mu[:, None]
    cs = np.concatenate([np.zeros((1, n_s)), np.cumsum(exc, axis=0)], axis=0)


    rows, gate = [], []

    def check(name, cond, detail=""):
        gate.append((bool(cond), name, detail))

    ev = panel[panel["cell"] > 0].reset_index(drop=True)
    print(f"事件 {len(ev):,} 个", flush=True)
    for cell in (1, 2, 3, 4):
        s = ev[ev["cell"] == cell]
        t_idx = s["hour"].to_numpy("int64")
        j_idx = np.array([col_of[name_of_code[c]] for c in s["symbol"].to_numpy("int64")],
                         dtype="int64")
        keep = (t_idx - 24 >= 0) & (t_idx + 24 < n_t)
        t_idx, j_idx = t_idx[keep], j_idx[keep]
        # 每个事件的 49 个累计值：cs 的差分（窗口不完整的事件用 keep 过滤）
        lo = cs[t_idx - 24, j_idx]
        cum = np.stack([cs[t_idx + k, j_idx] - lo for k in KS], axis=1)
        n_ev = len(t_idx)
        mean = cum.mean(axis=0)
        se = np.empty(len(KS))
        for i in range(len(KS)):
            sc = np.bincount(j_idx, weights=(cum[:, i] - mean[i]), minlength=n_s)
            se[i] = math.sqrt(float(np.sum(sc ** 2))) / n_ev
        # 相对事件时刻（k=0）的累计：左图收在 0，右图从 0 出发
        rel = cum - cum[:, [24]]
        mean_rel = rel.mean(axis=0)
        se_rel = np.empty(len(KS))
        for i in range(len(KS)):
            sc = np.bincount(j_idx, weights=(rel[:, i] - mean_rel[i]), minlength=n_s)
            se_rel[i] = math.sqrt(float(np.sum(sc ** 2))) / n_ev
        for i, k in enumerate(KS):
            rows.append({"sample": "headline", "cell": f"R{cell}", "k": int(k),
                         "mean": float(mean[i]), "se": float(se[i]),
                         "ci_lo": float(mean[i] - 1.96 * se[i]),
                         "ci_hi": float(mean[i] + 1.96 * se[i]),
                         "mean_rel": float(mean_rel[i]), "se_rel": float(se_rel[i]),
                         "ci_lo_rel": float(mean_rel[i] - 1.96 * se_rel[i]),
                         "ci_hi_rel": float(mean_rel[i] + 1.96 * se_rel[i]),
                         "n": int(n_ev)})
        print(f"  R{cell}: {n_ev:,} 个事件，k=0 累计 {mean[24]*1e4:+.1f}bp，"
              f"k=+24 累计 {mean[-1]*1e4:+.1f}bp", flush=True)
        check(f"R{cell} 的事件数 > 10,000", n_ev > 10_000, f"{n_ev:,}")
        check(f"R{cell} 的累计在 k=−24 处为 0", abs(float(mean[0])) < 1e-12, f"{mean[0]:.1e}")
        check(f"R{cell} 的 SE 在 k>−24 全部为正", bool((se[1:] > 0).all()),
              f"min {se[1:].min():.2e}")

    out = pd.DataFrame(rows)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(TABLE_DIR / "event_path.parquet", index=False)
    out.to_csv(TABLE_DIR / "event_path.csv", index=False, encoding="utf-8-sig")

    check("行数 = 4 格 × 49 个 k", len(out) == 196, f"{len(out)}")
    n_pass = sum(x for x, _, _ in gate)
    for x, n, d in gate:
        print(f"  [{'PASS' if x else 'FAIL'}] {n}  {d}")
    print(f"闸门 PASS {n_pass}/{len(gate)}；耗时 {time.time()-t0:.0f}s")
    return 0 if n_pass == len(gate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
