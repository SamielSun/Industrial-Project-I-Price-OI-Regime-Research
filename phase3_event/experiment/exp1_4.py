"""Phase 3 · 实验 1–3 + 1b —— 平均收益 / 中位收益 / 波动 + 2×2 因子对比

样本 = 同方向价格超阈的**全部行**（含该状态自己，估固定效应需要）；基准/比较组 = 其中 dummy=0 的行（另一个状态 + OI 安静行）。
例外：实验 2（中位数）的基准是「同向全部行的中位数」，那一节确实含自己。
估计：合约 + 月份双向固定效应（实验 2 例外——只报数，不检验）。
标准误：合约 + 月份双向聚类（Cameron-Gelbach-Miller）。
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

from config import EVENT  # noqa: E402
import infer as I  # noqa: E402

HORIZONS = list(EVENT.horizons)
PANEL = ROOT / "data/06_event_study/panel/freq=1h"
TABLE_DIR = ROOT / "data/06_event_study/tables/freq=1h"
CELLS = ((1, 1), (2, 1), (3, -1), (4, -1))
T0 = pd.Timestamp("2021-12-01", tz="UTC")


def load(h: int) -> pd.DataFrame:
    d = pd.read_parquet(PANEL / f"h={h}.parquet")
    d = d[d["dir"] != 0].reset_index(drop=True)
    d["mth"] = pd.factorize((T0 + pd.to_timedelta(d["hour"], unit="h"))
                            .dt.to_period("M").astype(str), sort=True)[0]
    return d


def _dummy(s: pd.DataFrame, cell: int) -> np.ndarray:
    return (s["cell"].to_numpy() == cell).astype("float64")


def _groups(s: pd.DataFrame):
    c = s["symbol"].to_numpy("int64"); m = s["mth"].to_numpy("int64")
    return c, int(c.max()) + 1, m, int(m.max()) + 1


def fit(s: pd.DataFrame, ycol: str, X: np.ndarray):
    """去掉 y 非有限的行（rv=0 时 lrv 是 NaN），再跑双向 FE。"""
    keep = np.isfinite(s[ycol].to_numpy("float64"))
    s = s[keep]
    X = X[keep]
    c, n1, m, n2 = _groups(s)
    return I.fe_ols(s[ycol].to_numpy("float64"), X, c, n1, m, n2)


def est_median(s: pd.DataFrame, cell: int):
    diffs = []
    for _, g in s.groupby("symbol", sort=True):
        v = g["y_raw"].to_numpy("float64")
        sel = g["cell"].to_numpy() == cell
        if sel.sum() == 0 or (~sel).sum() == 0:
            continue
        # 基准剔自己：与实验 1/3 的 dummy=0 组是同一个比较对象
        diffs.append(np.median(v[sel]) - np.median(v[~sel]))
    arr = np.asarray(diffs)
    return float(arr.mean()), int(arr.size), float((arr < 0).mean())


def factor_contrasts(s: pd.DataFrame, drop=()):
    """1b：2×2 因子（价格 × OI）。一套回归同时给出四个简单效应与交互。

    只在 cell 1–4 的行上拟合（不含 OI 安静的 cell 0）：
        ỹ = a·P + b·O + c·(P·O) + 合约FE + 月份FE
    P = 1{涨}（R1/R2）、O = 1{OI 增}（R1/R3）。于是
        OI | 价格上 = b + c   (R1−R2)      OI | 价格下 = b   (R3−R4)
        价格 | OI 增 = a + c   (R1−R3)     价格 | OI 减 = a   (R2−R4)
        交互         = c      (R1−R2) − (R3−R4)
    五个量都写成 e'β，SE 用 e'·bread·V·bread·e（V 是双向聚类），拿的是同一套回归，
    所以 SE 之间自动协调。
    """
    if len(drop):
        s = s[~np.isin(s["symbol"].to_numpy("int64"), np.asarray(drop, dtype="int64"))]
    s = s[s["cell"].isin([1, 2, 3, 4])].reset_index(drop=True)
    y = s["y_raw"].to_numpy("float64")
    ok = np.isfinite(y)
    s, y = s[ok].reset_index(drop=True), y[ok]
    cellv = s["cell"].to_numpy()
    P = np.isin(cellv, [1, 2]).astype("float64")
    O = np.isin(cellv, [1, 3]).astype("float64")
    X = np.column_stack([P, O, P * O])
    c, n1, m, n2 = _groups(s)
    beta, psi, _ = I.fe_ols(y, X, c, n1, m, n2)
    Z = I.demean2_cols(np.column_stack([y, X]), c, n1, m, n2)
    Xd = Z[:, 1:]
    bread = np.linalg.inv(Xd.T @ Xd)
    V = I.cgm_cov(psi, bread, c, n1, m, n2)
    combos = {
        "OI|价格上 (R1-R2)": np.array([0.0, 1.0, 1.0]),
        "OI|价格下 (R3-R4)": np.array([0.0, 1.0, 0.0]),
        "价格|OI增 (R1-R3)": np.array([1.0, 0.0, 1.0]),
        "价格|OI减 (R2-R4)": np.array([1.0, 0.0, 0.0]),
        "交互 (R1-R2)-(R3-R4)": np.array([0.0, 0.0, 1.0]),
    }
    out = {}
    for nm, e in combos.items():
        est = float(e @ beta)
        se = float(np.sqrt(max(float(e @ V @ e), 0.0)))
        out[nm] = (est, se, psi @ (bread @ e), c, n1)
    return out


def main() -> int:
    t0 = time.time()
    rows = []
    for h in HORIZONS:
        d = load(h)
        print(f"  h={h:<3} 行 {len(d):,} / 合约 {d['symbol'].nunique()}", flush=True)
        for cell, dirv in CELLS:
            s = d[d["dir"] == dirv].reset_index(drop=True)
            X = _dummy(s, cell)[:, None]

            beta, _, se = fit(s, "y_raw", X)
            rows.append(dict(experiment="1 收益·均值", h=h, cell=f"R{cell}",
                             estimate=float(beta[0]), se=float(se[0])))

            m_, n_c, sh = est_median(s, cell)
            rows.append(dict(experiment="2 收益·中位数", h=h, cell=f"R{cell}",
                             estimate=m_, se=np.nan, n_contracts=n_c, share_negative=sh))

            beta, _, se = fit(s, "lrv", X)
            rows.append(dict(experiment="3 波动", h=h, cell=f"R{cell}",
                             estimate=float(beta[0]), se=float(se[0])))


        # 1b：2×2 因子，一套回归出五个对比
        fc = factor_contrasts(d)
        for nm, (est, se, infl, cc, n_c) in fc.items():
            score = np.bincount(cc, weights=infl, minlength=n_c)
            worst = np.argsort(-np.abs(score))[:5]
            fc5 = factor_contrasts(d, drop=worst)
            e5_, se5_ = fc5[nm][0], fc5[nm][1]
            rows.append(dict(experiment="1b 因子对比", h=h, cell=nm,
                             estimate=est, se=se, t_drop5=e5_ / se5_,
                             n_rows=len(cc)))

    out = pd.DataFrame(rows)
    out["ci_lo"] = out["estimate"] - 1.96 * out["se"]
    out["ci_hi"] = out["estimate"] + 1.96 * out["se"]
    out["t"] = out["estimate"] / out["se"]
    out["p"] = [I.p_two(x) if np.isfinite(x) else np.nan for x in out["t"]]

    if "t_drop5" not in out:
        out["t_drop5"] = np.nan          # 1b 的行在构造时就带了值，别覆盖
    out["t_drop5"] = out["t_drop5"].astype("float64")
    for h in HORIZONS:
        d = load(h)
        for cell, dirv in CELLS:
            s = d[d["dir"] == dirv].reset_index(drop=True)
            for nm, col in (("1 收益·均值", "y_raw"), ("3 波动", "lrv")):
                if out.loc[(out["experiment"] == nm) & (out["h"] == h)
                           & (out["cell"] == f"R{cell}"), "t"].isna().any():
                    continue      # 中位数不检验，本来就没有 t
                X = _dummy(s, cell)[:, None]
                # 必须先按被解释变量的有限性过滤（lrv 有 NaN），否则 yd 全 NaN → b 与 score 全 NaN，
                # argsort 会挑到不存在的合约码，等于一个合约都没剔（曾经的真实 bug）。
                v = s[col].to_numpy("float64")
                ok = np.isfinite(v)
                sf = s[ok].reset_index(drop=True)
                c, n1, m, n2 = _groups(sf)
                Xd = I.demean2(_dummy(sf, cell), c, n1, m, n2)
                yd = I.demean2(v[ok], c, n1, m, n2)
                b = float(Xd @ yd / (Xd @ Xd))
                score = np.bincount(c, weights=Xd * (yd - b * Xd), minlength=n1)
                worst = np.argsort(-np.abs(score))[:5]
                keep = ~np.isin(c, worst)
                s2 = sf[keep].reset_index(drop=True)
                b5, _, se5 = fit(s2, col, _dummy(s2, cell)[:, None])
                msk = ((out["experiment"] == nm) & (out["h"] == h)
                       & (out["cell"] == f"R{cell}"))
                out.loc[msk, "t_drop5"] = float(b5[0]) / float(se5[0])


    out["p_bh"] = np.nan
    for nm in ("1 收益·均值", "3 波动", "1b 因子对比"):
        msk = out["experiment"] == nm
        out.loc[msk, "p_bh"] = I.bh(out.loc[msk, "p"].to_numpy())

    cols = ["experiment", "h", "cell", "estimate", "se", "ci_lo", "ci_hi",
            "t", "p", "p_bh", "t_drop5"]
    extra = [c for c in ("n_contracts", "share_negative") if c in out]
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    out[cols + extra].to_parquet(TABLE_DIR / "exp1_4.parquet", index=False)
    out[cols + extra].to_csv(TABLE_DIR / "exp1_4.csv", index=False, encoding="utf-8-sig")
    show = out[out["experiment"].isin(["1 收益·均值", "3 波动"])]
    print(show[["experiment", "h", "cell", "estimate", "t", "p", "p_bh", "t_drop5"]]
          .to_string(index=False, float_format=lambda v: f"{v:+.4f}"))
    print(f"耗时 {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
