"""Phase 4 · P4-6 (minimal, B) — R4 x market-vol state, descriptive only.

Q3 asks whether R4 mean-reverts *faster* after high liquidation / funding
stress.  There is no liquidation data and no first-touch / survival outcome, so
this block is a single descriptive table:

  R4 (price down + OI down) x market-vol state (low / mid / high)
  x horizon (1 / 4 / 8 / 24h)
  y_raw mean (bp), rev share (%), mdd p50 (bp), n

No family, no test, no figure; the label is "descriptive — not a test of faster".
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
BASE = ROOT / "data/07_funding/base"
TBL = ROOT / "data/07_funding/tables/freq=1h"
VSTATES = ["low", "mid", "high"]


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[(b["cell"] == 4) & b["state"].between(0, 3)].copy()
    for c in ("y_raw", "rev", "mdd"):
        b[c] = b[c].astype("float64")
    return b.reset_index(drop=True)


def main() -> int:
    t0 = time.time()
    rows, checks = [], []

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got,
                           pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        for v in VSTATES + ["unknown"]:
            s = b[b["mkt_vol_lab"] == v] if v != "unknown" \
                else b[~b["mkt_vol_lab"].isin(VSTATES)]
            rows.append(dict(
                h=h, vol_state=v, n_obs=int(len(s)),
                n_cmonths=int(s[["sym", "month"]].drop_duplicates().shape[0]),
                y_raw_mean_bp=float(s["y_raw"].mean() * 1e4) if len(s) else np.nan,
                rev_pct=float(s["rev"].mean() * 100) if len(s) else np.nan,
                mdd_p50_bp=float(s["mdd"].median() * 1e4) if len(s) else np.nan,
            ))
        tot = sum(r["n_obs"] for r in rows if r["h"] == h)
        check(f"h={h} R4 total n", int(len(b)), tot, tot == len(b))
        unknown = int((b["mkt_vol_lab"] == "unknown").sum())
        checks.append(dict(check=f"h={h} R4 unknown rows (info)",
                           expected=unknown, actual=unknown, pass_=True))

    df = pd.DataFrame(rows)
    for h, g in df.groupby("h", sort=False):
        check(f"h={h} 4 vol rows", 4, len(g), len(g) == 4)
        check(f"h={h} rev in [0,100]", 4,
              int(g["rev_pct"].between(0, 100).sum()),
              int(g["rev_pct"].between(0, 100).sum()) == 4)
        check(f"h={h} mdd_p50 <= 0", 4,
              int((g["mdd_p50_bp"] <= 0).sum()),
              int((g["mdd_p50_bp"] <= 0).sum()) == 4)
        check(f"h={h} y_raw finite", 4,
              int(np.isfinite(g["y_raw_mean_bp"]).sum()),
              int(np.isfinite(g["y_raw_mean_bp"]).sum()) == 4)

    # cross-check against P4-4 R4 cell counts (negative + neutral + high = distinct)
    p4 = pd.read_parquet(TBL / "p4_4_path.parquet")
    p4 = p4[(p4["weighting"] == "event") & (p4["regime"] == "R4")]
    p4_tot = {int(r): int(p4[(p4["funding"] == "negative") & (p4["h"] == r)]["n_obs"].iloc[0]
                  + p4[(p4["funding"] == "neutral") & (p4["h"] == r)]["n_obs"].iloc[0]
                  + p4[(p4["funding"] == "high") & (p4["h"] == r)]["n_obs"].iloc[0])
              for r in HORIZONS}
    for h in HORIZONS:
        got = int(df[(df["h"] == h)]["n_obs"].sum())
        check(f"h={h} n matches P4-4 R4 distinct", p4_tot[h], got,
              got == p4_tot[h])

    cdf = pd.DataFrame(checks)
    cdf.to_csv(TBL / "exp6_validation.csv", index=False)
    print(cdf.to_string(index=False))
    df.to_parquet(TBL / "p4_6_stress.parquet", index=False)
    df.to_csv(TBL / "p4_6_stress.csv", index=False)

    print("\nP4-6 (descriptive — not a test of 'faster')")
    for h in HORIZONS:
        g = df[df["h"] == h].set_index("vol_state").reindex(VSTATES + ["unknown"])
        print(f"\nh={h}: y_raw bp / rev % / mdd p50 bp / n")
        for v in VSTATES + ["unknown"]:
            r = g.loc[v]
            print(f"  {v:7s} {r['y_raw_mean_bp']:8.2f}  {r['rev_pct']:6.2f}  "
                  f"{r['mdd_p50_bp']:10.2f}  {int(r['n_obs']):6d}")

    print(f"\nPASS {int(cdf['pass_'].sum())} / {len(cdf)}; "
          f"elapsed {time.time()-t0:.1f}s")
    return 0 if int(cdf["pass_"].sum()) == len(cdf) else 1


if __name__ == "__main__":
    raise SystemExit(main())
