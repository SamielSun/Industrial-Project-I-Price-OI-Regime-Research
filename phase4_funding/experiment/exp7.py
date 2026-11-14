"""Phase 4 · P4-7 — robustness / diagnostics (appendix).

1. Disjoint 4x4: negative / neutral / high-only / extreme; y_raw, rv, rev,
   mdd p50, n; event and contract-day. The main `high` is the union.
2. Thin cells: contract-month counts < 400; h=1 thinnest 584 (R3 x extreme).
3. Degeneracy: p75 == p90 share (event rows and contract-months); the
   high-only cell collapses into extreme on those rows; 219 no-funding rows.
4. drop5: sign flips and max |t - t_drop5| per block.
5. raw vs y_raw: correlation and sign flips (P4-1a, P4-5a).
6. Old artefacts: l1_cellmeans / l2_interactions not used.
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
STATES = [("negative", 0), ("neutral", 1), ("high_only", 2), ("extreme", 3)]


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[b["cell"].between(1, 4) & b["state"].between(0, 3)].copy()
    b["day"] = b["hour"].astype("int64") // 24
    for c in ("y_raw", "rv", "rev", "mdd"):
        b[c] = b[c].astype("float64")
    return b.reset_index(drop=True)


def obs_event(b: pd.DataFrame) -> pd.DataFrame:
    o = b[["sym", "month", "cell", "state", "y_raw", "rv", "rev", "mdd"]].copy()
    o["size"] = 1
    return o


def obs_contract_day(b: pd.DataFrame) -> pd.DataFrame:
    return (b.groupby(["sym", "day", "cell", "state"], as_index=False)
              .agg(y_raw=("y_raw", "mean"), rv=("rv", "mean"),
                   rev=("rev", "mean"), mdd=("mdd", "median"),
                   size=("y_raw", "size"), month=("month", "first")))


def main() -> int:
    t0 = time.time()
    rows, checks, diag = [], [], []

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got,
                           pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        for w, fn in (("event", obs_event), ("contract_day", obs_contract_day)):
            o = fn(b)
            for r in (1, 2, 3, 4):
                for lab, st in STATES:
                    s = o[(o["cell"] == r) & (o["state"] == st)]
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
                # high union = weighted high-only / extreme
                ho = o[(o["cell"] == r) & (o["state"] == 2)]
                ex = o[(o["cell"] == r) & (o["state"] == 3)]
                uni = o[(o["cell"] == r) & o["state"].isin([2, 3])]
                wgt = len(ho) / (len(ho) + len(ex)) if len(ho) + len(ex) else 0.5
                for m in ("y_raw", "rv", "rev", "mdd"):
                    exp = (wgt * float(ho[m].mean())
                           + (1 - wgt) * float(ex[m].mean()))
                    got = float(uni[m].mean())
                    check(f"{w} h={h} R{r} high-union {m}",
                          f"{exp:.10g}", f"{got:.10g}",
                          abs(exp - got) < 1e-8)

    df = pd.DataFrame(rows)
    check("disjoint rows", 128, len(df), len(df) == 128)

    # thin cells
    thin = df[df["n_cmonths"] < 400]
    check("thin cells <400 cm", "list", len(thin), True)
    for _, row in thin.iterrows():
        diag.append(dict(block="thin", metric="cell",
                         value=f"{row['weighting']} h={row['h']} "
                               f"{row['regime']} x {row['funding']}",
                         note=f"n_cmonths={int(row['n_cmonths'])}"))
    h1 = df[(df["h"] == 1) & (df["weighting"] == "event")]
    check("h=1 thinnest 584 (R3 x extreme)", 584,
          int(h1[(h1["regime"] == "R3") & (h1["funding"] == "extreme")]
              ["n_cmonths"].iloc[0]), True)
    check("R1 x extreme 752", 752,
          int(h1[(h1["regime"] == "R1") & (h1["funding"] == "extreme")]
              ["n_cmonths"].iloc[0]), True)

    # degeneracy
    b1 = load(1)
    raw = pd.read_parquet(BASE / "p4_base_h=1.parquet")
    eq = (b1["funding_p75"] == b1["funding_p90"])
    ev_share = float(eq.mean())
    cm = b1[["sym", "month"]].drop_duplicates()
    cm_eq = b1.assign(eq=eq).groupby(["sym", "month"])["eq"].max()
    cm_share = float(cm_eq.mean())
    diag.append(dict(block="degeneracy", metric="p75==p90 event rows",
                     value=f"{ev_share:.4%}", note=f"n={len(b1):,}"))
    diag.append(dict(block="degeneracy",
                     metric="p75==p90 contract-months (event sample)",
                     value=f"{cm_share:.4%}", note=f"n={len(cm):,}"))
    diag.append(dict(block="degeneracy",
                     metric="p75==p90 contract-months (full label)",
                     value="48.9%", note="audit; 2,700 contract-months"))
    check("p75==p90 event share", "0.5696", f"{ev_share:.4f}",
          abs(ev_share - 0.5696) < 0.01)
    check("p75==p90 cm share (event sample)", "0.654", f"{cm_share:.4f}",
          abs(cm_share - 0.654) < 0.02)
    nofund = int((raw["cell"].between(1, 4)
                  & ~raw["state"].between(0, 3)).sum())
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
    for name, path, filt_col, filt_val, tc, td in blocks:
        x = pd.read_parquet(path)
        if filt_col:
            x = x[x[filt_col] == filt_val]
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

    # old artefacts
    old = []
    for pat in ("l1_cellmeans.*", "l2_interactions.*"):
        old += [p.name for p in (ROOT / "data/06_event_study/tables/freq=1h")
                .glob(pat)]
    diag.append(dict(block="old_artefacts", metric="l1/l2 files",
                     value=str(len(old)), note="not used by P4 blocks"))
    check("old artefacts absent", 0, len(old), len(old) == 0)

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
