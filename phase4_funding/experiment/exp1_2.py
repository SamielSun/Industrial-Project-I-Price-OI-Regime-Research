"""Phase 4 · P4-1/P4-2 — 4x4 conditional surface (note §10 output).

P4-1: forward return (raw fwd and market-neutral y_raw), mean/median + clustered CI.
P4-2: realized volatility (rv level and log lrv), mean/median + clustered CI.
Both: n = n_obs / n_rows_raw / n_cdays / n_cmonths, event and contract-day weighting.

P4-1a/P4-2 contrasts: 12 within-regime funding contrasts (BH 12, drop5),
built in the same script by `contrast_block`.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fe  # noqa: E402
import infer as I  # noqa: E402

T0 = pd.Timestamp("2021-12-01", tz="UTC")
HORIZONS = [1, 4, 8, 24]
BASE = ROOT / "data/07_funding/base"
TBL = ROOT / "data/07_funding/tables/freq=1h"

FUNDS = ["negative", "neutral", "high", "extreme"]
MASKS = {"negative": {0}, "neutral": {1}, "high": {2, 3}, "extreme": {3}}
REGIMES = [1, 2, 3, 4]


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[b["cell"].between(1, 4) & b["state"].between(0, 3)].copy()
    b["day"] = b["hour"].astype("int64") // 24
    return b.reset_index(drop=True)


def obs_event(b: pd.DataFrame) -> pd.DataFrame:
    o = b[["sym", "month", "day", "cell", "state", "fwd", "y_raw", "rv", "lrv"]].copy()
    o["size"] = 1
    return o


def obs_contract_day(b: pd.DataFrame) -> pd.DataFrame:
    o = (b.groupby(["sym", "day", "cell", "state"], as_index=False)
           .agg(fwd=("fwd", "mean"), y_raw=("y_raw", "mean"),
                rv=("rv", "mean"), lrv=("lrv", "mean"),
                size=("fwd", "size"), month=("month", "first")))
    return o


def mean_stats(x, sym, mon, day, size) -> dict:
    x = np.asarray(x, dtype="float64")
    ok = np.isfinite(x)
    x = x[ok]
    sym = np.asarray(sym)[ok]
    mon = np.asarray(mon)[ok]
    day = np.asarray(day)[ok]
    size = np.asarray(size)[ok]
    n = int(x.size)
    if n < 2:
        return dict(mean=np.nan, median=np.nan, ci_lo=np.nan, ci_hi=np.nan,
                    se=np.nan, n_obs=n, n_rows_raw=int(size.sum()),
                    n_cdays=np.nan, n_cmonths=np.nan)
    m = float(x.mean())
    med = float(np.median(x))
    g1 = pd.factorize(sym)[0].astype("int64")
    g2 = pd.factorize(mon)[0].astype("int64")
    psi = ((x - m) / n).reshape(-1, 1)
    V = I.cgm_cov(psi, np.ones((1, 1)), g1, int(g1.max()) + 1,
                  g2, int(g2.max()) + 1)
    se = float(np.sqrt(max(V[0, 0], 0.0)))
    cd = pd.DataFrame({"s": sym, "d": day}).drop_duplicates().shape[0]
    cm = pd.DataFrame({"s": sym, "m": mon}).drop_duplicates().shape[0]
    return dict(mean=m, median=med, ci_lo=m - 1.96 * se, ci_hi=m + 1.96 * se,
                se=se, n_obs=n, n_rows_raw=int(size.sum()),
                n_cdays=int(cd), n_cmonths=int(cm))


def surface(o: pd.DataFrame) -> list[dict]:
    rows = []
    for r in REGIMES:
        for f in FUNDS:
            sub = o[(o.cell == r) & o.state.isin(MASKS[f])]
            if len(sub) == 0:
                continue
            sym = sub["sym"].to_numpy()
            mon = sub["month"].to_numpy()
            day = sub["day"].to_numpy()
            size = sub["size"].to_numpy()
            row = dict(regime=f"R{r}", funding=f)
            for metric in ("fwd", "y_raw", "rv", "lrv"):
                st = mean_stats(sub[metric].to_numpy(), sym, mon, day, size)
                for k, v in st.items():
                    if metric in ("fwd", "y_raw") and k in (
                            "mean", "median", "ci_lo", "ci_hi", "se"):
                        v = v * 1e4
                    row[f"{metric}_{k}"] = v
            rows.append(row)
    return rows


KIND = {"negative - neutral": "neg",
        "high(incl ext) - neutral": "high",
        "extreme - neutral": "ext"}
STATES = {"neg": {0}, "high": {2, 3}, "ext": {3}}
LABELS = {"neg": "negative - neutral",
          "high": "high(incl ext) - neutral",
          "ext": "extreme - neutral"}


def cvec(r: int, kind: str, w2: float) -> np.ndarray:
    """Contrast on the 15 coefficients; cell 15 (R4 x extreme) is the reference."""
    c = np.zeros(16)
    i0 = (r - 1) * 4
    i1, i2, i3 = i0 + 1, i0 + 2, i0 + 3
    if kind == "neg":
        c[i0] += 1.0
        c[i1] -= 1.0
    elif kind == "high":
        c[i2] += w2
        c[i3] += 1.0 - w2
        c[i1] -= 1.0
    elif kind == "ext":
        c[i3] += 1.0
        c[i1] -= 1.0
    return c[:15]


def contrast_block(o: pd.DataFrame, h: int, weighting: str,
                   rows: list, checks: list) -> None:
    o = o.copy()
    o["cellidx"] = ((o["cell"].astype("int64") - 1) * 4
                    + o["state"].astype("int64"))
    sym = pd.factorize(o["sym"])[0].astype("int64")
    mon = pd.factorize(o["month"])[0].astype("int64")

    for dv, in_bh in (("y_raw", True), ("fwd", False), ("lrv", True)):
        y_all = o[dv].to_numpy("float64")
        ok = np.isfinite(y_all)
        y = y_all[ok]
        cell = o["cellidx"].to_numpy("int64")[ok]
        s = sym[ok]
        m = mon[ok]
        beta, V, u, psi = fe.fit(y, cell, s, m)
        n_c = int(s.max()) + 1
        cnt = np.bincount(cell, minlength=16)

        fam = []
        for r in REGIMES:
            i0 = (r - 1) * 4
            n2, n3 = int(cnt[i0 + 2]), int(cnt[i0 + 3])
            w2 = n2 / (n2 + n3) if (n2 + n3) else 0.5
            for kind in ("neg", "high", "ext"):
                c = cvec(r, kind, w2)
                est, se, t = fe.contrast(beta, V, c)
                if dv in ("y_raw", "fwd"):
                    est, se = est * 1e4, se * 1e4
                fam.append(dict(
                    weighting=weighting, h=h, dv=dv, regime=f"R{r}",
                    contrast=LABELS[kind], estimate=est, se=se, t=t,
                    p=I.p_two(t) if in_bh else np.nan, in_bh=in_bh,
                    note_marker=("🟣" if dv == "lrv" else
                                 ("🔵🟡" if r in (1, 3)
                                  else ("🟡" if r == 2 else "—"))),
                ))

        if in_bh:
            pbh = I.bh(np.array([x["p"] for x in fam]))
            for x, pb in zip(fam, pbh):
                x["p_bh"] = float(pb)
        else:
            for x in fam:
                x["p_bh"] = np.nan

        if in_bh:
            for x in fam:
                r = int(x["regime"][1])
                i0 = (r - 1) * 4
                n2, n3 = int(cnt[i0 + 2]), int(cnt[i0 + 3])
                w2 = n2 / (n2 + n3) if (n2 + n3) else 0.5
                x["t_drop5"] = fe.t_drop5(
                    y, cell, s, m, psi, cvec(r, KIND[x["contrast"]], w2), n_c)
        else:
            for x in fam:
                x["t_drop5"] = np.nan

        for x in fam:
            x["flip_drop5"] = (bool(np.sign(x["t"]) != np.sign(x["t_drop5"]))
                               if np.isfinite(x["t_drop5"]) else np.nan)

        for x in fam:
            r = int(x["regime"][1])
            states = STATES[KIND[x["contrast"]]]
            sub = o[(o["cell"] == r) & o["state"].isin(states)]
            sub = sub[np.isfinite(sub[dv])]
            x["n_obs"] = int(len(sub))
            x["n_cmonths"] = int(sub[["sym", "month"]].drop_duplicates().shape[0])
        rows.extend(fam)

        if dv == "y_raw":
            for r in REGIMES:
                i0 = (r - 1) * 4
                n2, n3 = int(cnt[i0 + 2]), int(cnt[i0 + 3])
                w2 = n2 / (n2 + n3) if (n2 + n3) else 0.5
                c_ho = np.zeros(16)
                c_ho[i0 + 2] += 1.0
                c_ho[i0 + 1] -= 1.0
                est_ho = fe.contrast(beta, V, c_ho[:15])[0]
                est2 = fe.contrast(beta, V, cvec(r, "high", w2))[0]
                est3 = fe.contrast(beta, V, cvec(r, "ext", w2))[0]
                exp = w2 * est_ho + (1 - w2) * est3
                checks.append(dict(
                    check=f"y_raw h={h} {weighting} R{r} C2 identity",
                    expected=f"{exp:.12g}", actual=f"{est2:.12g}",
                    pass_=bool(abs(exp - est2) < 1e-10)))


def main() -> int:
    t0 = time.time()
    rows1, rows2, checks, crows = [], [], [], []

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got, pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        for weighting, obs_fn in (("event", obs_event),
                                  ("contract_day", obs_contract_day)):
            o = obs_fn(b)
            for row in surface(o):
                row.update(weighting=weighting, h=h)
                rows1.append(row)
                rows2.append(row)
            if h == 1 and weighting == "event":
                d = pd.DataFrame([r for r in rows1 if r["h"] == 1
                                  and r["weighting"] == "event"])
                for r, s, nrow, ncm in [(1, "neutral", 37_038, 2_384),
                                        (1, "high", 13_184, 1_183),
                                        (1, "extreme", 6_905, 752),
                                        (3, "extreme", 2_416, 584)]:
                    got = d[(d.regime == f"R{r}") & (d.funding == s)].iloc[0]
                    check(f"h=1 R{r} x {s} n_obs", nrow, int(got["y_raw_n_obs"]),
                          int(got["y_raw_n_obs"]) == nrow)
                    check(f"h=1 R{r} x {s} n_cmonths", ncm,
                          int(got["y_raw_n_cmonths"]),
                          int(got["y_raw_n_cmonths"]) == ncm)
                # high-union identity for each metric (weights = finite counts)
                for r in REGIMES:
                    hi = d[(d.regime == f"R{r}") & (d.funding == "high")].iloc[0]
                    ho = o[(o.cell == r) & (o.state == 2)]
                    exo = o[(o.cell == r) & (o.state == 3)]
                    for m in ("fwd", "y_raw", "rv", "lrv"):
                        ho_m = ho[m].dropna().astype("float64")
                        exo_m = exo[m].dropna().astype("float64")
                        w = len(ho_m) / (len(ho_m) + len(exo_m))
                        exp = w * float(ho_m.mean()) + (1 - w) * float(exo_m.mean())
                        if m in ("fwd", "y_raw"):
                            exp *= 1e4
                        got = float(hi[f"{m}_mean"])
                        check(f"h=1 R{r} high-union mean {m}",
                              f"{exp:.12g}", f"{got:.12g}", abs(exp - got) < 1e-8)

    # P4-1a / P4-2 contrasts (12 within-regime per dv, h, weighting)
    for h in HORIZONS:
        b = load(h)
        for weighting, obs_fn in (("event", obs_event),
                                  ("contract_day", obs_contract_day)):
            contrast_block(obs_fn(b), h, weighting, crows, checks)

    cdf = pd.DataFrame(crows)
    for (dv, h, w), g in cdf.groupby(["dv", "h", "weighting"], sort=False):
        check(f"{dv} h={h} {w} n contrasts", 12, len(g), len(g) == 12)
        if dv in ("y_raw", "lrv"):
            check(f"{dv} h={h} {w} p_bh finite", 12,
                  int(g["p_bh"].notna().sum()),
                  int(g["p_bh"].notna().sum()) == 12)
            check(f"{dv} h={h} {w} t_drop5 finite", 12,
                  int(g["t_drop5"].notna().sum()),
                  int(g["t_drop5"].notna().sum()) == 12)
        else:
            check(f"{dv} h={h} {w} no BH", 0,
                  int(g["p_bh"].notna().sum()),
                  int(g["p_bh"].notna().sum()) == 0)

    c1 = pd.DataFrame(checks)
    c1.to_csv(TBL / "exp1_2_validation.csv", index=False)
    print(c1.to_string(index=False))

    s1 = pd.DataFrame(rows1)
    s2 = pd.DataFrame(rows2)
    keep1 = ["weighting", "h", "regime", "funding",
             "fwd_mean", "fwd_median", "fwd_ci_lo", "fwd_ci_hi",
             "y_raw_mean", "y_raw_median", "y_raw_ci_lo", "y_raw_ci_hi",
             "y_raw_n_obs", "y_raw_n_rows_raw", "y_raw_n_cdays", "y_raw_n_cmonths"]
    keep2 = ["weighting", "h", "regime", "funding",
             "rv_mean", "rv_median", "rv_ci_lo", "rv_ci_hi",
             "lrv_mean", "lrv_ci_lo", "lrv_ci_hi",
             "lrv_n_obs", "lrv_n_rows_raw", "lrv_n_cdays", "lrv_n_cmonths"]
    s1[keep1].to_parquet(TBL / "p4_1_surface.parquet", index=False)
    s2[keep2].to_parquet(TBL / "p4_2_vol.parquet", index=False)
    s1[keep1].to_csv(TBL / "p4_1_surface.csv", index=False)
    s2[keep2].to_csv(TBL / "p4_2_vol.csv", index=False)

    d1 = cdf[cdf["dv"].isin(["y_raw", "fwd"])].copy()
    d2 = cdf[cdf["dv"] == "lrv"].copy()
    d2["estimate_pct"] = (np.exp(d2["estimate"]) - 1) * 100
    d1.to_parquet(TBL / "p4_1_contrasts.parquet", index=False)
    d2.to_parquet(TBL / "p4_2_contrasts.parquet", index=False)
    d1.to_csv(TBL / "p4_1_contrasts.csv", index=False)
    d2.to_csv(TBL / "p4_2_contrasts.csv", index=False)

    print(f"\nPASS {int(c1['pass_'].sum())} / {len(c1)}; elapsed {time.time()-t0:.1f}s")
    return 0 if int(c1["pass_"].sum()) == len(c1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
