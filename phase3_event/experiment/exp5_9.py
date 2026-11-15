"""Phase 3 · 实验 5–9 + 13 —— 四条基线的多空价差、随机时点、逐日对比、水平表

口径（见 GUIDANCE §9）：
- 5/6/7 + 四状态：池起来算价差（多头组均值 − 空头组均值），**不加任何固定效应**。
  估计样本**只含被比较的两组行**——参照组（OI 安静行、funding 中间档）不进样本，
  否则结果会被参照组的分布拉偏（见 GUIDANCE §0）。
- 标准误：合约 + 月份双向聚类（Cameron-Gelbach-Miller），簇做在**行**上。
- 9：同一批时段上比较四条信号的**逐日**多空价差 r_k(t)。
  − 时段 = 自然日（24 小时，UTC 00:00 对齐）
  − 每边至少 5 个不同合约，否则该日该信号记为缺失
  − 只保留四条信号同时可算的日子（交集）
  − Δ_k = r̄_四状态 − r̄_k；标准误 Newey-West，滞后 = max(1, h/24)
  − 判定看三个 Δ 的 |t|；四条信号的 r̄_k 只报 t 供参考，**不进判定族**
- 8：随机时点重放 1000 轮（合约不变，时刻在该合约的小时里随机换）。
- 13：各组收益水平，只报数（se / t 全空）。

为什么时段是日而不是小时：四状态每小时平均只有 2.2 个 R1、2.6 个 R4，
按「每小时每边 ≥5 个合约」筛完只剩 5 个小时。
1 对 1 的小时价差是特质噪声，Δ 在门槛与期限之间换号；按自然日汇总、
每边 ≥5 是唯一在门槛敏感性上稳定的配置（Δ(价格) 在 ≥5 时 t=2.09、≥3 时 t=1.74）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "phase3_event"))
sys.path.insert(0, str(ROOT / "phase3_event/experiment"))

from config import EVENT  # noqa: E402
import infer as I  # noqa: E402
from infer import nw_se  # noqa: E402

HORIZONS = list(EVENT.horizons)
PANEL = ROOT / "data/06_event_study/panel/freq=1h"
TABLE_DIR = ROOT / "data/06_event_study/tables/freq=1h"
T0 = pd.Timestamp("2021-12-01", tz="UTC")

EXP9_BUCKET = 24          # 一个时段含几小时（= 自然日）
EXP9_MIN_SIDE = 5         # 每边至少几个不同合约，否则该时段该信号缺失

POOLED_NAME = {"纯价格": "5 纯价格", "纯 OI": "6 纯 OI",
               "纯 funding": "7 纯 funding", "四状态": "四状态"}
TESTED = set(POOLED_NAME.values()) | {"9 Δ"}


def load(h: int) -> pd.DataFrame:
    d = pd.read_parquet(PANEL / f"h={h}.parquet")
    d = d[np.isfinite(d["y_raw"])].reset_index(drop=True)
    d["mth"] = pd.factorize((T0 + pd.to_timedelta(d["hour"], unit="h"))
                            .dt.strftime("%Y-%m"), sort=True)[0]
    return d


def masks_of(d: pd.DataFrame) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """四条信号的多头 / 空头掩码。funding 的 extreme ⊂ high，用重叠口径。"""
    dirv, oi3, fund, cell = (d[c].to_numpy() for c in ("dir", "oi3", "fund", "cell"))
    return {"纯价格": (dirv > 0, dirv < 0),
            "纯 OI": (oi3 > 0, oi3 < 0),
            "纯 funding": ((fund == 2) | (fund == 3), fund == 0),
            "四状态": (cell == 1, cell == 4)}


def spread_est(d: pd.DataFrame, long_m: np.ndarray, short_m: np.ndarray, drop=()):
    """池起来的价差 + 双向聚类 SE + 合约层面得分（供 drop5 用）。

    估计样本 = 多头行 ∪ 空头行；drop 里的合约整行剔除。
    返回 (估计, SE, 合约得分, 样本行数)。
    """
    keep = long_m | short_m
    if len(drop):
        keep &= ~np.isin(d["symbol"].to_numpy("int64"), np.asarray(drop, dtype="int64"))
    y = d["y_raw"].to_numpy("float64")[keep]
    isl = long_m[keep]
    cc = d["symbol"].to_numpy("int64")[keep]
    mm = d["mth"].to_numpy("int64")[keep]
    nl, ns = int(isl.sum()), int((~isl).sum())
    ml, ms = float(y[isl].mean()), float(y[~isl].mean())
    psi = np.where(isl, (y - ml) / nl, -(y - ms) / ns)
    n_c, n_m = int(cc.max()) + 1, int(mm.max()) + 1
    se = float(I.cgm_se(psi[:, None], np.eye(1), cc, n_c, mm, n_m)[0])
    score = np.bincount(cc, weights=psi, minlength=n_c)
    return ml - ms, se, score, int(keep.sum())


def _bucket_stats(b: np.ndarray, v: np.ndarray, sym: np.ndarray, T: int):
    """每个时段：行数、均值、**不同合约数**、每行的偏差贡献。"""
    cnt = np.bincount(b, minlength=T).astype("float64")
    tot = np.bincount(b, weights=v, minlength=T)
    mean = np.where(cnt > 0, tot / np.where(cnt > 0, cnt, 1.0), np.nan)
    uniq = np.unique(b * 1_000_000 + sym)
    nun = np.bincount(uniq // 1_000_000, minlength=T).astype("float64")
    dev = (v - mean[b]) / np.where(cnt[b] > 0, cnt[b], 1.0)
    return mean, nun, dev


def bucket_series(d: pd.DataFrame):
    """四条信号的逐时段价差 r_k(t)、有效掩码、每合约贡献。

    每合约贡献 = Σ_t ψ_{k,t}(i)：合约 i 在该信号价差里的影响力（drop5 用）。
    """
    hour = d["hour"].to_numpy("int64")
    b0 = hour // EXP9_BUCKET
    b = b0 - b0.min()
    T = int(b.max()) + 1
    y = d["y_raw"].to_numpy("float64")
    sym = d["symbol"].to_numpy("int64")
    n_c = int(sym.max()) + 1
    out = {}
    for nm, (lo, sh) in masks_of(d).items():
        side, psi_c = {}, np.zeros(n_c)
        for tag, mask, sign in (("L", lo, +1.0), ("S", sh, -1.0)):
            mean, nun, dev = _bucket_stats(b[mask], y[mask], sym[mask], T)
            psi_c += sign * np.bincount(sym[mask], weights=dev, minlength=n_c)
            side[tag] = (mean, nun)
        ok = (side["L"][1] >= EXP9_MIN_SIDE) & (side["S"][1] >= EXP9_MIN_SIDE)
        out[nm] = (side["L"][0] - side["S"][0], ok, psi_c)
    return out, T


def exp9(d: pd.DataFrame, h: int, drop=()):
    """实验 9：逐日价差对比。返回 (四条信号的 r̄_k 行, 三个 Δ 行, 滞后)。"""
    if len(drop):
        d = d[~np.isin(d["symbol"].to_numpy("int64"),
                        np.asarray(drop, dtype="int64"))].reset_index(drop=True)
    ser, _ = bucket_series(d)
    S = np.logical_and.reduce([ser[k][1] for k in ser])
    lag = max(1, int(round(h / EXP9_BUCKET)))
    lvl, dif = [], []
    for nm in ser:
        x = ser[nm][0][S]
        lvl.append(dict(experiment="9 逐日价差", h=h, cell=nm, estimate=float(x.mean()),
                        se=nw_se(x, lag), n_periods=int(S.sum())))
    for nm in ("纯价格", "纯 OI", "纯 funding"):
        x = (ser["四状态"][0] - ser[nm][0])[S]
        dif.append(dict(experiment="9 Δ", h=h, cell=f"四状态−{nm}", estimate=float(x.mean()),
                        se=nw_se(x, lag), n_periods=int(S.sum()),
                        _score=(ser["四状态"][2] - ser[nm][2]) / float(S.sum())))
    return lvl, dif, lag


def self_test() -> list[tuple[bool, str, str]]:
    """坑 ⑦：新估计量先做已知答案验证。"""
    rng = np.random.default_rng(7)
    n, n_c, n_m = 6_000, 40, 12
    sym = rng.integers(0, n_c, n)
    mth = rng.integers(0, n_m, n)
    long_m = rng.random(n) < 0.5
    short_m = ~long_m
    # 噪声在每边内部求和归零：价差的已知答案精确是 +5bp，同时合约簇的得分不全为 0
    # （不要在「合约 × 方向」内部归零——那会让每个合约的 psi 求和恒为 0，SE 变成 0）
    noise = rng.normal(0.0, 1e-3, n)
    noise -= np.where(long_m, noise[long_m].mean(), noise[short_m].mean())
    y = np.where(long_m, 2e-4, -3e-4) + noise         # 均值差正好 +5bp
    d = pd.DataFrame({"y_raw": y, "symbol": sym.astype("int64"),
                      "mth": mth.astype("int64")})
    est, se, score, _ = spread_est(d, long_m, short_m)
    out = [(abs(est - 5e-4) < 1e-12, "自检：已知价差 +5bp 能算出来",
            f"{est*1e4:+.6f}bp（SE {se*1e4:.4f}bp）")]

    # 给 0 号合约加一个离群：drop5 应该先抓它，剔掉后回到 +5bp 且 |t| 回落
    yb = y.copy()
    yb[(sym == 0) & long_m] += 0.2
    db = pd.DataFrame({"y_raw": yb, "symbol": sym.astype("int64"),
                       "mth": mth.astype("int64")})
    e1, s1, sc1, _ = spread_est(db, long_m, short_m)
    worst = np.argsort(-np.abs(sc1))[:5]
    e5, s5, _, _ = spread_est(db, long_m, short_m, drop=worst)
    out.append((int(worst[0]) == 0, "自检：drop5 抓到那个离群合约", f"#{int(worst[0])}"))
    out.append((abs(e1 - 5e-4) > 1e-3 and abs(e5 - 5e-4) < 1e-4,
                "自检：drop5 剔掉离群合约后估回 +5bp",
                f"全样本 {e1*1e4:+.1f}bp → drop5 后 {e5*1e4:+.4f}bp"))
    return out


def main() -> int:
    t0 = time.time()
    gate = self_test()
    rows = []

    def check(name, cond, detail=""):
        gate.append((bool(cond), name, detail))

    for h in HORIZONS:
        d = load(h)
        msk = masks_of(d)
        print(f"  h={h:<3} 面板 {len(d):,} 行 / 合约 {int(d['symbol'].nunique())}", flush=True)
        if h == int(HORIZONS[-1]):
            n_ev = int((d["cell"] >= 1).sum())
            check("h=24 面板行数 = 1,965,030", abs(len(d) / 1_965_030 - 1) < 5e-3, f"{len(d):,}")
            check("h=24 事件行数 = 255,807", abs(n_ev / 255_807 - 1) < 5e-3, f"{n_ev:,}")

        for nm, (lo, sh) in msk.items():
            est, se, score, n_row = spread_est(d, lo, sh)
            worst = np.argsort(-np.abs(score))[:5]
            est5, se5, _, _ = spread_est(d, lo, sh, drop=worst)
            rows.append(dict(experiment=POOLED_NAME[nm], h=h, cell=POOLED_NAME[nm],
                             estimate=est, se=se, n_rows=n_row, t_drop5=est5 / se5))
            if h == int(HORIZONS[-1]):
                print(f"    {POOLED_NAME[nm]:<12} 样本 {n_row:,} 行", flush=True)

        lvl, dif, lag = exp9(d, h)
        worst = np.argsort(-np.abs(np.stack([r["_score"] for r in dif])).sum(axis=0))[:5]
        _, dif5, _ = exp9(d, h, drop=worst)
        for a, b in zip(dif, dif5):
            a["t_drop5"] = b["estimate"] / b["se"]
        for r in lvl:
            r["t_drop5"] = np.nan
        rows.extend(lvl)
        rows.extend(dif)
        n_per = lvl[0]["n_periods"]
        check(f"h={h} 实验 9 的交集日数在 300–1,200 日之间", 300 <= n_per <= 1_200,
              f"{n_per} 日 / 滞后 {lag}")


        y = d["y_raw"].to_numpy("float64")
        for nm, (lo, sh) in msk.items():
            for tag, mask in (("long", lo), ("short", sh)):
                rows.append(dict(experiment="13 水平", h=h, cell=f"{nm}_{tag}",
                                 estimate=float(y[mask].mean()), se=np.nan))

    out = pd.DataFrame(rows)
    out["ci_lo"] = out["estimate"] - 1.96 * out["se"]
    out["ci_hi"] = out["estimate"] + 1.96 * out["se"]
    out["t"] = out["estimate"] / out["se"]
    out["p"] = [I.p_two(x) if np.isfinite(x) else np.nan for x in out["t"]]
    tested = out["experiment"].isin(TESTED)
    out["p_bh"] = np.nan
    out.loc[tested, "p_bh"] = I.bh(out.loc[tested, "p"].to_numpy())

    n_tested = int(tested.sum())
    check("判定行 = 7 × 4 期（4 个价差 + 3 个 Δ）", n_tested == 28, f"{n_tested} 行")
    n_lev = int((out["experiment"] == "13 水平").sum())
    check("实验 13 水平行 = 8 × 4 期（4 条基线 × 多空两侧）", n_lev == 32, f"{n_lev} 行")
    check("判定行的 se 全部 > 0", bool((out.loc[tested, "se"] > 0).all()),
          f"min {out.loc[tested, 'se'].min():.3e}")
    check("判定行的 t 与 t_drop5 全部有限",
          bool(np.isfinite(out.loc[tested, "t"]).all()
               and np.isfinite(out.loc[tested, "t_drop5"]).all()),
          f"NaN {int(out.loc[tested, ['t', 't_drop5']].isna().sum().sum())}")

    cols = ["experiment", "h", "cell", "estimate", "se", "ci_lo", "ci_hi",
            "t", "p", "p_bh", "t_drop5", "n_rows", "n_periods"]
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    out[cols].to_parquet(TABLE_DIR / "exp5_9.parquet", index=False)
    out[cols].to_csv(TABLE_DIR / "exp5_9.csv", index=False, encoding="utf-8-sig")

    n_pass = sum(x for x, _, _ in gate)
    for x, n, dd in gate:
        print(f"  [{'PASS' if x else 'FAIL'}] {n}  {dd}")
    show = out[out["experiment"].isin(TESTED | {"9 逐日价差"})]
    print(show[["experiment", "h", "cell", "estimate", "t", "p", "p_bh", "t_drop5"]]
          .to_string(index=False, float_format=lambda v: f"{v:+.6f}"))
    print(f"闸门 PASS {n_pass}/{len(gate)}；耗时 {time.time()-t0:.0f}s")
    return 0 if n_pass == len(gate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
