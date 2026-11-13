"""Phase 4 · P4-4 — conditional path: MFE / MAE / MDD (descriptive).

Per guidance §9: 4x4 cells; mfe_mean, mae_mean, mdd_mean, mdd_p10/p50/p90, n.
MFE/MAE are already direction-flipped by the Phase 3 build; MDD <= 0.
No first-touch, no ATR, no BH/drop5 (descriptive only).
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

HORIZONS = [1, 4, 8, 24]
BASE = ROOT / "phase4_funding/data"
TBL = ROOT / "phase4_funding/tables"

FUNDS = ["negative", "neutral", "high", "extreme"]
MASKS = {"negative": {0}, "neutral": {1}, "high": {2, 3}, "extreme": {3}}
REGIMES = [1, 2, 3, 4]


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[b["cell"].between(1, 4) & b["state"].between(0, 3)].copy()
    for c in ("mfe", "mae", "mdd"):
        b[c] = b[c].astype("float64")
    return b.reset_index(drop=True)


def obs_event(b: pd.DataFrame) -> pd.DataFrame:
    return b[["sym", "month", "cell", "state", "mfe", "mae", "mdd"]].copy()


def obs_contract_day(b: pd.DataFrame) -> pd.DataFrame:
    return (b.groupby(["sym", "day", "cell", "state"], as_index=False)
              .agg(mfe=("mfe", "mean"), mae=("mae", "mean"),
                   mdd=("mdd", "mean"), month=("month", "first")))


def stats(x, sym, mon) -> dict:
    x = np.asarray(x, dtype="float64")
    ok = np.isfinite(x)
    x = x[ok]
    sym = np.asarray(sym)[ok]
    mon = np.asarray(mon)[ok]
    if x.size == 0:
        return dict(mean=np.nan, median=np.nan, p10=np.nan, p50=np.nan,
                    p90=np.nan, n_obs=0, n_cmonths=0)
    return dict(
        mean=float(x.mean()), median=float(np.median(x)),
        p10=float(np.quantile(x, 0.10)), p50=float(np.quantile(x, 0.50)),
        p90=float(np.quantile(x, 0.90)), n_obs=int(x.size),
        n_cmonths=int(pd.DataFrame({"s": sym, "m": mon})
                      .drop_duplicates().shape[0]),
    )


def run(o: pd.DataFrame, h: int, weighting: str, rows: list) -> None:
    for r in REGIMES:
        for f in FUNDS:
            sub = o[(o["cell"] == r) & o["state"].isin(MASKS[f])]
            if len(sub) == 0:
                continue
            sym = sub["sym"].to_numpy()
            mon = sub["month"].to_numpy()
            row = dict(weighting=weighting, h=h, regime=f"R{r}", funding=f)
            for m, keys in (("mfe", ("mean", "median")),
                            ("mae", ("mean", "median")),
                            ("mdd", ("mean", "p10", "p50", "p90"))):
                st = stats(sub[m].to_numpy(), sym, mon)
                for k in keys:
                    row[f"{m}_{k}"] = st[k]
            st = stats(sub["mfe"].to_numpy(), sym, mon)
            row["n_obs"] = st["n_obs"]
            row["n_cmonths"] = st["n_cmonths"]
            rows.append(row)


def main() -> int:
    t0 = time.time()
    rows, checks = [], []

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got, pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        b["day"] = b["hour"].astype("int64") // 24
        for weighting, obs_fn in (("event", obs_event),
                                  ("contract_day", obs_contract_day)):
            run(obs_fn(b), h, weighting, rows)

    df = pd.DataFrame(rows)
    for (h, w), g in df.groupby(["h", "weighting"], sort=False):
        check(f"h={h} {w} n cells", 16, len(g), len(g) == 16)
        check(f"h={h} {w} n_obs positive", 16,
              int((g["n_obs"] > 0).sum()), int((g["n_obs"] > 0).sum()) == 16)
        check(f"h={h} {w} mdd_p10<=p50<=p90", 16,
              int(((g["mdd_p10"] <= g["mdd_p50"])
                   & (g["mdd_p50"] <= g["mdd_p90"])).sum()),
              int(((g["mdd_p10"] <= g["mdd_p50"])
                   & (g["mdd_p50"] <= g["mdd_p90"])).sum()) == 16)
        check(f"h={h} {w} mdd_mean<=0", 16,
              int((g["mdd_mean"] <= 0).sum()),
              int((g["mdd_mean"] <= 0).sum()) == 16)

    # n cross-check against P4-1 surface (same cells)
    s1 = pd.read_parquet(TBL / "p4_1_surface.parquet")
    s1 = s1[["weighting", "h", "regime", "funding", "y_raw_n_obs", "y_raw_n_cmonths"]]
    mg = df.merge(s1, on=["weighting", "h", "regime", "funding"], how="left")
    dn = int((mg["n_obs"] != mg["y_raw_n_obs"]).sum())
    dm = int((mg["n_cmonths"] != mg["y_raw_n_cmonths"]).sum())
    check("n_obs matches P4-1 surface", 0, dn, dn == 0)
    check("n_cmonths matches P4-1 surface", 0, dm, dm == 0)

    # high-union identity for the three means
    for h in HORIZONS:
        b = load(h)
        b["day"] = b["hour"].astype("int64") // 24
        for w, obs_fn in (("event", obs_event), ("contract_day", obs_contract_day)):
            o = obs_fn(b)
            g = df[(df["h"] == h) & (df["weighting"] == w)]
            for r in REGIMES:
                hi = g[(g["regime"] == f"R{r}") & (g["funding"] == "high")].iloc[0]
                ho = o[(o["cell"] == r) & (o["state"] == 2)]
                ex = o[(o["cell"] == r) & (o["state"] == 3)]
                wgt = len(ho) / (len(ho) + len(ex))
                for m in ("mfe", "mae", "mdd"):
                    exp = wgt * float(ho[m].mean()) + (1 - wgt) * float(ex[m].mean())
                    got = float(hi[f"{m}_mean"])
                    check(f"h={h} {w} R{r} high-union {m}",
                          f"{exp:.12g}", f"{got:.12g}", abs(exp - got) < 1e-10)

    # sign diagnostics (events only)
    b1 = load(1)
    exc_mfe = int((b1["mfe"] < 0).sum())
    exc_mae = int((b1["mae"] > 0).sum())
    bad_mdd = int((b1["mdd"] > 0).sum())
    check("mdd <= 0 (raw events)", 0, bad_mdd, bad_mdd == 0)
    print(f"sign exceptions h=1: mfe<0 {exc_mfe}, mae>0 {exc_mae}, mdd>0 {bad_mdd}")

    cdf = pd.DataFrame(checks)
    cdf.to_csv(TBL / "exp4_validation.csv", index=False)
    print(cdf.to_string(index=False))
    df.to_parquet(TBL / "p4_4_path.parquet", index=False)
    df.to_csv(TBL / "p4_4_path.csv", index=False)
    print(f"\nPASS {int(cdf['pass_'].sum())} / {len(cdf)}; elapsed {time.time()-t0:.1f}s")
    return 0 if int(cdf["pass_"].sum()) == len(cdf) else 1


if __name__ == "__main__":
    raise SystemExit(main())
