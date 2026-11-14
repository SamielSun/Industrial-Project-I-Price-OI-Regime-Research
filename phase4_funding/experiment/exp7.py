"""Phase 4 · P4-7 — robustness / diagnostics (appendix), A+B.

A. non-degenerate 4x4 (p75 < p90): negative / neutral / high-only / extreme.
B. degenerate bucket (p75 == p90 and state=3): high-only empty, high=extreme.
   full high = high-only + extreme + degenerate; reconciles with the main high.
Diagnostics: thin cells, p75==p90 degeneracy, drop5, raw vs y_raw, old artefacts.
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
# (funding label, state code or -1 for the high union, sample)
LABELS = [
    ("negative", 0, "full"),
    ("neutral", 1, "full"),
    ("high_only", 2, "nondeg"),
    ("extreme", 3, "nondeg"),
    ("degenerate", 3, "deg"),
    ("high", -1, "full"),
]


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[b["cell"].between(1, 4) & b["state"].between(0, 3)].copy()
    b["day"] = b["hour"].astype("int64") // 24
    b["deg"] = (b["funding_p75"] == b["funding_p90"])
    for c in ("y_raw", "rv", "rev", "mdd"):
        b[c] = b[c].astype("float64")
    return b.reset_index(drop=True)


def obs_event(b: pd.DataFrame) -> pd.DataFrame:
    return b[["sym", "month", "cell", "state", "deg",
              "y_raw", "rv", "rev", "mdd"]].copy().assign(size=1)


def obs_contract_day(b: pd.DataFrame) -> pd.DataFrame:
    return (b.groupby(["sym", "day", "cell", "state", "deg"], as_index=False)
              .agg(y_raw=("y_raw", "mean"), rv=("rv", "mean"),
                   rev=("rev", "mean"), mdd=("mdd", "median"),
                   size=("y_raw", "size"), month=("month", "first")))


def mask(o: pd.DataFrame, r: int, st: int, sample: str) -> np.ndarray:
    m = (o["cell"].to_numpy() == r)
    if st >= 0:
        m &= (o["state"].to_numpy() == st)
    else:
        m &= o["state"].isin([2, 3]).to_numpy()
    if sample == "nondeg":
        m &= ~o["deg"].to_numpy()
    elif sample == "deg":
        m &= o["deg"].to_numpy()
    return m


def main() -> int:
    t0 = time.time()
    rows, checks, diag = [], [], []
    full_n: dict[int, int] = {}

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got,
                           pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        full_n[h] = int(len(b))
        for w, fn in (("event", obs_event), ("contract_day", obs_contract_day)):
            o = fn(b)
            for r in (1, 2, 3, 4):
                for lab, st, sample in LABELS:
                    s = o[mask(o, r, st, sample)]
                    rows.append(dict(
                        weighting=w, h=h, regime=f"R{r}", funding=lab,
                        n_obs=int(len(s)),
                        n_cmonths=int(s[["sym", "month"]]
                                      .drop_duplicates().shape[0]),
                        y_raw_mean_bp=float(s["y_raw"].mean() * 1e4)
                        if len(s) else np.nan,
                        rv_mean=float(s["rv"].mean()) if len(s) else np.nan,
                        rev_pct=float(s["rev"].mean() * 100) if len(s) else np.nan,
                        mdd_p50_bp=float(s["mdd"].median() * 1e4)
                        if len(s) else np.nan,
                    ))

    df = pd.DataFrame(rows)
    check("disjoint rows", 192, len(df), len(df) == 192)

    # 5 categories partition the sample; high = high_only + extreme + degenerate
    for h in HORIZONS:
        for w in ("event", "contract_day"):
            g = df[(df["h"] == h) & (df["weighting"] == w)]
            five = g[g["funding"] != "high"]
            exp = (int(g[g["funding"] == "high"]["n_obs"].sum())
                   + int(g[g["funding"] == "negative"]["n_obs"].sum())
                   + int(g[g["funding"] == "neutral"]["n_obs"].sum()))
            got = int(five["n_obs"].sum())
            ok = (exp == got) and (w != "event" or got == full_n[h])
            check(f"{w} h={h} 5 categories sum = full", exp, got, ok)

    # high union = high_only + extreme + degenerate (n and each metric)
    for h in HORIZONS:
        for w in ("event", "contract_day"):
            for r in (1, 2, 3, 4):
                g = df[(df["h"] == h) & (df["weighting"] == w)
                       & (df["regime"] == f"R{r}")]
                hi = g[g["funding"] == "high"].iloc[0]
                parts = g[g["funding"].isin(
                    ["high_only", "extreme", "degenerate"])]
                n = int(parts["n_obs"].sum())
                check(f"{w} h={h} R{r} high n = 3 buckets",
                      int(hi["n_obs"]), n, n == int(hi["n_obs"]))
                for m in ("y_raw_mean_bp", "rv_mean", "rev_pct"):
                    exp = float((parts["n_obs"] * parts[m]).sum() / n)
                    got = float(hi[m])
                    check(f"{w} h={h} R{r} high {m} = 3 buckets",
                          f"{exp:.10g}", f"{got:.10g}",
                          abs(exp - got) < 1e-8)
    diag.append(dict(block="high_union", metric="mdd_p50 not additive",
                     value="median",
                     note="high mdd_p50 is not the weighted avg of bucket medians"))

    # thin cells (A's nondeg 4x4 + B's degenerate; exclude the full high)
    thin = df[(df["n_cmonths"] < 400) & (df["funding"] != "high")]
    for _, row in thin.iterrows():
        diag.append(dict(block="thin", metric="cell",
                         value=f"{row['weighting']} h={row['h']} "
                               f"{row['regime']} x {row['funding']}",
                         note=f"n_cmonths={int(row['n_cmonths'])}"))
    b1 = load(1)
    n_r3e = int(b1[(b1["cell"] == 3) & (b1["state"] == 3)]
                [["sym", "month"]].drop_duplicates().shape[0])
    n_r1e = int(b1[(b1["cell"] == 1) & (b1["state"] == 3)]
                [["sym", "month"]].drop_duplicates().shape[0])
    check("h=1 full R3 x extreme 584", 584, n_r3e, n_r3e == 584)
    check("R1 x extreme 752", 752, n_r1e, n_r1e == 752)

    # degeneracy
    eq = b1["deg"]
    ev_share = float(eq.mean())
    cm_share = float(b1.assign(eq=eq).groupby(["sym", "month"])["eq"].max().mean())
    diag.append(dict(block="degeneracy", metric="p75==p90 event rows",
                     value=f"{ev_share:.4%}", note=f"n={len(b1):,}"))
    diag.append(dict(block="degeneracy",
                     metric="p75==p90 contract-months (event sample)",
                     value=f"{cm_share:.4%}", note=f"n={b1[['sym','month']].drop_duplicates().shape[0]:,}"))
    lab_files = sorted((ROOT / "data/05_regime/regime_labels/freq=1h")
                       .rglob("*.parquet"))
    lab = pd.concat([pd.read_parquet(
        p, columns=["symbol", "ts_end", "funding_p75", "funding_p90"])
        for p in lab_files], ignore_index=True)
    lab["month"] = lab["ts_end"].dt.to_period("M").astype(str)
    lab["deg"] = lab["funding_p75"] == lab["funding_p90"]
    full_cm = lab[["symbol", "month"]].drop_duplicates()
    full_share = float(lab.groupby(["symbol", "month"])["deg"].max().mean())
    diag.append(dict(block="degeneracy",
                     metric="p75==p90 contract-months (full label)",
                     value=f"{full_share:.4%}",
                     note=f"n={len(full_cm):,} contract-months"))
    check("p75==p90 event share", "0.5696", f"{ev_share:.4f}",
          abs(ev_share - 0.5696) < 0.01)
    check("p75==p90 cm share (event sample)", "0.654", f"{cm_share:.4f}",
          abs(cm_share - 0.654) < 0.02)
    raw = pd.read_parquet(BASE / "p4_base_h=1.parquet")
    nofund = int((raw["cell"].between(1, 4) & ~raw["state"].between(0, 3)).sum())
    diag.append(dict(block="degeneracy", metric="no-funding rows excluded",
                     value=str(nofund), note="state = -1, cell 1-4"))
    check("no-funding rows 219", 219, nofund, nofund == 219)

    # drop5 sign flips
    blocks = [
        ("P4-1a", TBL / "p4_1_contrasts.parquet", "dv", "y_raw", "t", "t_drop5"),
        ("P4-2", TBL / "p4_2_contrasts.parquet", None, None, "t", "t_drop5"),
        ("P4-3", TBL / "p4_3_reversal.parquet", None, None, "rev_t",
         "rev_t_drop5"),
        ("P4-5", TBL / "p4_5_beta.parquet", "outcome", "rev", "t", "t_drop5"),
    ]
    for name, path, fc, fv, tc, td in blocks:
        x = pd.read_parquet(path)
        if fc:
            x = x[x[fc] == fv]
        x = x[np.isfinite(x[td])]
        flips = int((np.sign(x[tc]) != np.sign(x[td])).sum())
        mx = float((x[tc] - x[td]).abs().max())
        diag.append(dict(block="drop5", metric=name,
                         value=f"sign flips {flips}/{len(x)}",
                         note=f"max |t-t_drop5|={mx:.2f}"))
        check(f"{name} drop5 finite", "all", len(x), len(x) > 0)

    # raw vs y_raw
    a = pd.read_parquet(TBL / "p4_1_contrasts.parquet")
    piv = a.pivot_table(index=["weighting", "h", "regime", "contrast"],
                        columns="dv", values="estimate").dropna()
    corr = float(np.corrcoef(piv["fwd"], piv["y_raw"])[0, 1])
    flips = int((np.sign(piv["fwd"]) != np.sign(piv["y_raw"])).sum())
    diag.append(dict(block="raw_vs_yraw", metric="P4-1a corr(fwd,y_raw)",
                     value=f"{corr:.3f}", note=f"sign flips {flips}/{len(piv)}"))
    check("P4-1a raw/y_raw corr finite", "finite", corr, np.isfinite(corr))
    p5 = pd.read_parquet(TBL / "p4_5_beta.parquet")
    piv5 = p5.pivot_table(index=["weighting", "h", "regime", "funding"],
                          columns="outcome", values="beta").dropna()
    corr5 = float(np.corrcoef(piv5["fwd"], piv5["y_raw"])[0, 1])
    flips5 = int((np.sign(piv5["fwd"]) != np.sign(piv5["y_raw"])).sum())
    diag.append(dict(block="raw_vs_yraw", metric="P4-5a corr(fwd,y_raw)",
                     value=f"{corr5:.3f}",
                     note=f"sign flips {flips5}/{len(piv5)}"))
    check("P4-5a raw/y_raw corr finite", "finite", corr5, np.isfinite(corr5))

    cdf = pd.DataFrame(checks)
    cdf.to_csv(TBL / "exp7_validation.csv", index=False)
    print(cdf.to_string(index=False))
    df.to_parquet(TBL / "p4_7_disjoint.parquet", index=False)
    df.to_csv(TBL / "p4_7_disjoint.csv", index=False)
    pd.DataFrame(diag).to_csv(TBL / "p4_7_diagnostics.csv", index=False)
    print(f"\nPASS {int(cdf['pass_'].sum())} / {len(cdf)}; "
          f"elapsed {time.time()-t0:.1f}s")
    return 0 if int(cdf["pass_"].sum()) == len(cdf) else 1


if __name__ == "__main__":
    raise SystemExit(main())
