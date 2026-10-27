"""Phase 3 · ic_decay_v2 —— 实验 15：IC 衰减（四状态 vs 纯价格动量并排）

口径（D13/D14/D17）：
- 每小时在**该小时的横截面**上算 Spearman 秩相关，再在时间序列上求均值。
- 四状态分数：R1=+1、R4=−1、其余（R2/R3/非事件）=0。
- 纯价格动量分数：sign(price_change)（全部有效行，不看 regime）。
- 收益用原始前向收益（IC 衡量排序信息，与收益尺度无关，所以不中性化、不截尾）。
- 标准误：Newey-West，滞后 = h（前向窗口重叠）。不用按合约聚类——IC 是单一时间序列。

用法：
    python phase3_event/ic_decay_v2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import EVENT  # noqa: E402

LABEL_DIR = ROOT / "data/05_regime/regime_labels/freq=1h"
CLOSE = ROOT / "data/06_event_study/wide/close.parquet"
TABLE_DIR = ROOT / "data/06_event_study/tables/freq=1h"
DOC_DIR = ROOT / "data/06_event_study/docs"

MIN_CONTRACTS = EVENT.ic_min_contracts
HORIZONS = list(EVENT.horizons)


def load_labels() -> pd.DataFrame:
    fs = sorted(LABEL_DIR.glob("**/*.parquet"))
    d = pd.concat(
        [pd.read_parquet(f, columns=["symbol", "ts_end", "price_change", "regime",
                                     "excl_reason", "in_universe"]) for f in fs],
        ignore_index=True,
    )
    d = d[d["excl_reason"] == "ok"].reset_index(drop=True)
    d["four"] = np.where(d["regime"] == "R1", 1.0, np.where(d["regime"] == "R4", -1.0, 0.0))
    d["price"] = np.sign(d["price_change"].to_numpy(dtype="float64"))
    return d


def price_lookup() -> pd.Series:
    close = pd.read_parquet(CLOSE)
    ts = pd.to_datetime(close["ts"], utc=True)
    long = close.drop(columns=["ts"]).set_axis(ts, axis=0).stack(dropna=True)
    long.index.names = ["ts", "symbol"]
    return long.astype("float64")


def forward_return(d: pd.DataFrame, px: pd.Series, h: int) -> np.ndarray:
    """P(T) = ts_end−1h 那一行；fwd_h = P(T+h)/P(T) − 1。"""
    step = pd.Timedelta("1h")
    key_t = pd.MultiIndex.from_arrays([d["ts_end"] - step, d["symbol"]])
    key_f = pd.MultiIndex.from_arrays([d["ts_end"] + (h - 1) * step, d["symbol"]])
    p_t = px.reindex(key_t).to_numpy()
    p_f = px.reindex(key_f).to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        return p_f / p_t - 1.0


def spearman_by_hour(d: pd.DataFrame, y: np.ndarray, score: str) -> pd.Series:
    ok = np.isfinite(y)
    frame = pd.DataFrame({"hour": d.loc[ok, "hour"].to_numpy(),
                          "s": d.loc[ok, score].to_numpy(),
                          "y": y[ok]})
    g = frame.groupby("hour", sort=True)
    rs = g["s"].rank()
    ry = g["y"].rank()
    ds = rs - rs.groupby(frame["hour"]).transform("mean")
    dy = ry - ry.groupby(frame["hour"]).transform("mean")
    key = frame["hour"]
    cov = (ds * dy).groupby(key).sum()
    vx = (ds * ds).groupby(key).sum()
    vy = (dy * dy).groupby(key).sum()
    cnt = g["y"].size()
    ic = cov / np.sqrt(vx * vy)
    keep = (cnt >= MIN_CONTRACTS) & (vx > 0) & (vy > 0) & ic.notna()
    return ic[keep]


def nw_se(x: np.ndarray, lag: int) -> float:
    T = x.size
    xc = x - x.mean()
    var = float(xc @ xc) / T
    for l in range(1, lag + 1):
        w = 1.0 - l / (lag + 1.0)
        var += 2.0 * w * float(xc[l:] @ xc[:-l]) / T
    return float(np.sqrt(max(var, 0.0) / T))


def main() -> int:
    d = load_labels()
    d["hour"] = ((d["ts_end"] - pd.Timestamp("2021-12-01", tz="UTC")) // pd.Timedelta("1h")).astype("int64")
    px = price_lookup()

    rows = []
    for sample, mask in (("headline", d["in_universe"].to_numpy(dtype=bool)),
                         ("full", np.ones(len(d), dtype=bool))):
        sub = d[mask].reset_index(drop=True)
        for h in HORIZONS:
            y = forward_return(sub, px, h)
            ics = {k: spearman_by_hour(sub, y, k) for k in ("four", "price")}
            joint = pd.concat(ics, axis=1).dropna()
            got = {}
            for k, ser in ics.items():
                x = ser.to_numpy()
                got[k] = (float(x.mean()), nw_se(x, h), int(x.size))
                rows.append(dict(sample=sample, h=h, score=k, n_hours=int(x.size),
                                 mean_ic=got[k][0], se_nw=got[k][1], t=got[k][0] / got[k][1]))
            dif = (joint["price"] - joint["four"]).to_numpy()
            rows.append(dict(sample=sample, h=h, score="price_minus_four", n_hours=int(dif.size),
                             mean_ic=float(dif.mean()), se_nw=nw_se(dif, h),
                             t=float(dif.mean() / nw_se(dif, h))))
            print(f"  {sample:<9} h={h:<3} 四状态 {got['four'][0]:+.4f} (t {got['four'][0]/got['four'][1]:+6.1f})"
                  f"   纯价格 {got['price'][0]:+.4f} (t {got['price'][0]/got['price'][1]:+6.1f})"
                  f"   差 {dif.mean():+.4f}   n_hours {got['price'][2]:,}")

    out = pd.DataFrame(rows)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(TABLE_DIR / "ic_decay_v2.parquet", index=False)
    out.to_csv(TABLE_DIR / "ic_decay_v2.csv", index=False, encoding="utf-8-sig")

    gate = []
    def check(name, cond, detail=""):
        gate.append((bool(cond), name, detail))

    # headline 只有 33,400 个小时满足"横截面 >= 20 个合约"；full 是 40,312。
    # 39,459 是 headline 的**全部**小时数，不是能算 IC 的那部分——别混。
    for sample, expect in (("headline", 33_400), ("full", 40_312)):
        s = out[(out["sample"] == sample) & (out["score"] == "four")]["n_hours"]
        check(f"{sample} 的小时数在 {expect:,} 附近（±5%）",
              bool(np.all(np.abs(s / expect - 1) < 0.05)), f"{sorted(s.unique())}")
    check("全部 IC 落在 [−1, 1]", bool(out["mean_ic"].abs().max() <= 1.0),
          f"max|IC| {out['mean_ic'].abs().max():.4f}")
    check("全部 NW 标准误 > 0", bool((out["se_nw"] > 0).all()), f"min se {out['se_nw'].min():.3e}")
    check("行数 = 2 样本 × 4 h × 3 分数", bool(len(out) == 24), f"{len(out)} 行")

    h1 = out[(out["sample"] == "headline") & (out["h"] == 1)].set_index("score")
    check("★ h=1 纯价格 IC 绝对值大于四状态（v1: −0.0369 vs −0.0204）",
          bool(abs(h1.loc["price", "mean_ic"]) > abs(h1.loc["four", "mean_ic"])),
          f"price {h1.loc['price','mean_ic']:+.4f} vs four {h1.loc['four','mean_ic']:+.4f}")
    check("★ h=1 两个 IC 都为负（横截面反转）",
          bool(h1.loc["price", "mean_ic"] < 0 and h1.loc["four", "mean_ic"] < 0),
          f"{h1.loc['price','mean_ic']:+.4f} / {h1.loc['four','mean_ic']:+.4f}")

    DOC_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["event_study · ic_decay_v2（实验 15）", "",
             "推断：Newey-West，滞后 = h（不用按合约聚类——IC 是单一时间序列）",
             "口径：原始前向收益（不中性化、不截尾）；四状态 R1=+1 / R4=−1 / 其余=0；纯价格 = sign(price_change)", "",
             out.to_string(index=False, float_format=lambda v: f"{v:+.6f}"), ""]
    n_pass = sum(ok for ok, _, _ in gate)
    for ok, name, detail in gate:
        lines.append(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail}")
    lines.append(f"\n闸门汇总：PASS {n_pass} / FAIL {len(gate) - n_pass}")
    (DOC_DIR / "step11_checks_ic.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(f"[{'PASS' if o else 'FAIL'}] {n}  {dd}" for o, n, dd in gate))
    print(f"闸门汇总：PASS {n_pass} / FAIL {len(gate) - n_pass}")
    return 0 if n_pass == len(gate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
