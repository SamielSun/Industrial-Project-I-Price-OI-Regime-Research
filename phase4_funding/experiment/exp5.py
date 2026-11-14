"""Phase 4 · P4-5 — conditional beta vs matched benchmark.

For each (regime r, funding column f):
  treat = regime r rows (same price direction, same funding)
  bench = cell 0 (same direction, same funding, OI quiet)
          + the other OI state (same direction, same funding)
  y = beta * treat + contract FE + month FE + e

16 betas per (weighting, h, outcome): 4 regimes x 4 funding columns.
P4-5a: y_raw (main) and fwd (descriptive), beta in bp.
P4-5b: rev (LPM), beta in pp.  BH 16 + drop5 for y_raw / rev.
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

HORIZONS = [1, 4, 8, 24]
BASE = ROOT / "data/07_funding/base"
TBL = ROOT / "data/07_funding/tables/freq=1h"

FUNDS = ["negative", "neutral", "high", "extreme"]
MASKS = {"negative": {0}, "neutral": {1}, "high": {2, 3}, "extreme": {3}}
REGIMES = [1, 2, 3, 4]
DIRS = {1: 1, 2: 1, 3: -1, 4: -1}
OTHER = {1: 2, 2: 1, 3: 4, 4: 3}


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[b["cell"].between(0, 4) & b["state"].between(0, 3)].copy()
    b["day"] = b["hour"].astype("int64") // 24
    return b.reset_index(drop=True)


def obs_event(b: pd.DataFrame) -> pd.DataFrame:
    o = b[["sym", "month", "day", "cell", "state", "dir",
           "y_raw", "fwd", "rev"]].copy()
    o["size"] = 1
    return o


def obs_contract_day(b: pd.DataFrame) -> pd.DataFrame:
    return (b.groupby(["sym", "day", "cell", "state", "dir"], as_index=False)
              .agg(y_raw=("y_raw", "mean"), fwd=("fwd", "mean"),
                   rev=("rev", "mean"), size=("y_raw", "size"),
                   month=("month", "first")))


def _drop5(y, treat, sym, mon, psi, n1):
    score = np.bincount(sym, weights=psi[:, 0], minlength=n1)
    drop = np.argsort(-np.abs(score))[:5]
    keep = ~np.isin(sym, drop)
    if keep.sum() < 100:
        return np.nan
    us, s2 = np.unique(sym[keep], return_inverse=True)
    um, m2 = np.unique(mon[keep], return_inverse=True)
    if len(us) < 20 or len(um) < 10:
        return np.nan
    try:
        b2, _, se2 = I.fe_ols(y[keep], treat[keep, None], s2, len(us), m2, len(um))
        return float(b2[0] / se2[0])
    except np.linalg.LinAlgError:
        return np.nan


def beta_one(o: pd.DataFrame, r: int, f: str, dv: str, do_drop5: bool):
    dr = DIRS[r]
    other = OTHER[r]
    states = MASKS[f]
    sub = o[(o["dir"] == dr) & o["state"].isin(states)
            & o["cell"].isin([r, 0, other])].copy()
    y_all = sub[dv].to_numpy("float64")
    ok = np.isfinite(y_all)
    sub = sub[ok]
    y = y_all[ok]
    treat = (sub["cell"] == r).to_numpy("float64")
    n_tr = int(treat.sum())
    n_b = int(len(treat) - n_tr)
    if n_tr < 10 or n_b < 10:
        return None
    sym = pd.factorize(sub["sym"])[0].astype("int64")
    mon = pd.factorize(sub["month"])[0].astype("int64")
    n1 = int(sym.max()) + 1
    n2 = int(mon.max()) + 1
    beta, psi, se = I.fe_ols(y, treat[:, None], sym, n1, mon, n2)
    t = float(beta[0] / se[0])
    p = float(I.p_two(t))
    t5 = _drop5(y, treat, sym, mon, psi, n1) if do_drop5 else np.nan
    n_cm = int(sub[["sym", "month"]].drop_duplicates().shape[0])
    return dict(beta=float(beta[0]), se=float(se[0]), t=t, p=p,
                t_drop5=t5, n_treat=n_tr, n_bench=n_b, n_cmonths=n_cm)


def main() -> int:
    t0 = time.time()
    rows, checks = [], []

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got, pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        for weighting, obs_fn in (("event", obs_event),
                                  ("contract_day", obs_contract_day)):
            o = obs_fn(b)
            for dv, in_bh in (("y_raw", True), ("fwd", False), ("rev", True)):
                fam = []
                for r in REGIMES:
                    for f in FUNDS:
                        st = beta_one(o, r, f, dv, in_bh)
                        if st is None:
                            continue
                        if dv == "rev":
                            beta_d, se_d, unit = st["beta"] * 100.0, st["se"] * 100.0, "pp"
                        else:
                            beta_d, se_d, unit = st["beta"] * 1e4, st["se"] * 1e4, "bp"
                        fam.append(dict(
                            weighting=weighting, h=h, outcome=dv, regime=f"R{r}",
                            funding=f, beta=beta_d, se=se_d, t=st["t"],
                            p=st["p"], in_bh=in_bh, t_drop5=st["t_drop5"],
                            flip_drop5=(bool(np.sign(st["t"]) != np.sign(st["t_drop5"]))
                                        if np.isfinite(st["t_drop5"]) else np.nan),
                            n_treat=st["n_treat"], n_bench=st["n_bench"],
                            n_cmonths=st["n_cmonths"], unit=unit,
                            note_marker=("🔵🟡" if r in (1, 3)
                                         else ("🟡" if r == 2 else "—")),
                        ))
                if in_bh and fam:
                    pbh = I.bh(np.array([x["p"] for x in fam]))
                    for x, pb in zip(fam, pbh):
                        x["p_bh"] = float(pb)
                else:
                    for x in fam:
                        x["p_bh"] = np.nan
                rows.extend(fam)

    df = pd.DataFrame(rows)
    for (h, w, dv), g in df.groupby(["h", "weighting", "outcome"], sort=False):
        check(f"{dv} h={h} {w} n betas", 16, len(g), len(g) == 16)
        if dv in ("y_raw", "rev"):
            check(f"{dv} h={h} {w} p_bh finite", 16,
                  int(g["p_bh"].notna().sum()),
                  int(g["p_bh"].notna().sum()) == 16)
            check(f"{dv} h={h} {w} t_drop5 finite", 16,
                  int(g["t_drop5"].notna().sum()),
                  int(g["t_drop5"].notna().sum()) == 16)
        else:
            check(f"{dv} h={h} {w} no BH", 0,
                  int(g["p_bh"].notna().sum()),
                  int(g["p_bh"].notna().sum()) == 0)
        check(f"{dv} h={h} {w} n_bench positive", 16,
              int((g["n_bench"] > 0).sum()), int((g["n_bench"] > 0).sum()) == 16)

    # n_treat cross-check against P4-1 surface (same cells, y_raw sample)
    s1 = pd.read_parquet(TBL / "p4_1_surface.parquet")
    s1 = s1[["weighting", "h", "regime", "funding", "y_raw_n_obs"]]
    y = df[df["outcome"] == "y_raw"].merge(
        s1, on=["weighting", "h", "regime", "funding"], how="left")
    dn = int((y["n_treat"] != y["y_raw_n_obs"]).sum())
    check("n_treat matches P4-1 surface (y_raw)", 0, dn, dn == 0)

    cdf = pd.DataFrame(checks)
    cdf.to_csv(TBL / "exp5_validation.csv", index=False)
    print(cdf.to_string(index=False))
    df.to_parquet(TBL / "p4_5_beta.parquet", index=False)
    df.to_csv(TBL / "p4_5_beta.csv", index=False)
    print(f"\nPASS {int(cdf['pass_'].sum())} / {len(cdf)}; elapsed {time.time()-t0:.1f}s")
    return 0 if int(cdf["pass_"].sum()) == len(cdf) else 1


if __name__ == "__main__":
    raise SystemExit(main())
