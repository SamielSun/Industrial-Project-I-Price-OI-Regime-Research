"""Phase 4 · P4-1/P4-2 — 4x4 conditional surface (note §10 output).

P4-1: forward return (raw fwd and market-neutral y_raw), mean/median + clustered CI.
P4-2: realized volatility (rv level and log lrv), mean/median + clustered CI.
Both: n = n_obs / n_rows_raw / n_cdays / n_cmonths, event and contract-day weighting.

No contrasts here (P4-1a/P4-2 contrasts are the next item).
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

import infer as I  # noqa: E402

T0 = pd.Timestamp("2021-12-01", tz="UTC")
HORIZONS = [1, 4, 8, 24]
BASE = ROOT / "phase4_funding/data"
TBL = ROOT / "phase4_funding/tables"

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
                    row[f"{metric}_{k}"] = v
            rows.append(row)
    return rows


def main() -> int:
    t0 = time.time()
    rows1, rows2, checks = [], [], []

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
                        ho_m = ho[m].dropna()
                        exo_m = exo[m].dropna()
                        w = len(ho_m) / (len(ho_m) + len(exo_m))
                        exp = w * float(ho_m.mean()) + (1 - w) * float(exo_m.mean())
                        got = float(hi[f"{m}_mean"])
                        check(f"h=1 R{r} high-union mean {m}",
                              f"{exp:.12g}", f"{got:.12g}", abs(exp - got) < 1e-10)

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

    print(f"\nPASS {int(c1['pass_'].sum())} / {len(c1)}; elapsed {time.time()-t0:.1f}s")
    return 0 if int(c1["pass_"].sum()) == len(c1) else 1


if __name__ == "__main__":
    raise SystemExit(main())
