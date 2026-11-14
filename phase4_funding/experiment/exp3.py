"""Phase 4 · P4-3 — conditional reversal / continuation (LPM).

rev  = 1{fwd_h * dir < 0}   (raw sign, note §8 C)
cont = 1 - rev

LPM with contract+month FE on the 16 disjoint cells; 12 within-regime funding
contrasts (`negative / high(incl ext) / extreme` vs neutral), BH 12, drop5.
`cont` is the complement; both are reported.
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
from exp1_2 import KIND, LABELS, REGIMES, STATES, cvec  # noqa: E402

T0 = pd.Timestamp("2021-12-01", tz="UTC")
HORIZONS = [1, 4, 8, 24]
BASE = ROOT / "phase4_funding/data"
TBL = ROOT / "phase4_funding/tables"


def load(h: int) -> pd.DataFrame:
    b = pd.read_parquet(BASE / f"p4_base_h={h}.parquet")
    b = b[b["cell"].between(1, 4) & b["state"].between(0, 3)].copy()
    b["day"] = b["hour"].astype("int64") // 24
    for c in ("rev", "cont", "flat"):
        b[c] = b[c].astype("float64")
    return b.reset_index(drop=True)


def obs_event(b: pd.DataFrame) -> pd.DataFrame:
    o = b[["sym", "month", "day", "cell", "state", "rev", "cont", "flat", "fwd"]].copy()
    o["size"] = 1
    return o


def obs_contract_day(b: pd.DataFrame) -> pd.DataFrame:
    return (b.groupby(["sym", "day", "cell", "state"], as_index=False)
              .agg(rev=("rev", "mean"), cont=("cont", "mean"),
                   flat=("flat", "mean"), size=("fwd", "size"),
                   month=("month", "first")))


def run(o: pd.DataFrame, h: int, weighting: str,
        rows: list, checks: list) -> None:
    o = o.copy()
    o["cellidx"] = ((o["cell"].astype("int64") - 1) * 4
                    + o["state"].astype("int64"))
    sym = pd.factorize(o["sym"])[0].astype("int64")
    mon = pd.factorize(o["month"])[0].astype("int64")
    y = o["rev"].to_numpy("float64")
    ok = np.isfinite(y)
    y = y[ok]
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
            est, se, t = fe.contrast(beta, V, cvec(r, kind, w2))
            fam.append(dict(
                weighting=weighting, h=h, regime=f"R{r}",
                contrast=LABELS[kind],
                rev_estimate_pp=est * 100.0, rev_se_pp=se * 100.0, rev_t=t,
                cont_estimate_pp=-est * 100.0, cont_se_pp=se * 100.0,
                cont_t=-t, p=I.p_two(t),
                note_marker=("🔵🟡" if r in (1, 3)
                             else ("🟡" if r == 2 else "—")),
            ))

    pbh = I.bh(np.array([x["p"] for x in fam]))
    for x, pb in zip(fam, pbh):
        x["p_bh"] = float(pb)
    for x in fam:
        r = int(x["regime"][1])
        i0 = (r - 1) * 4
        n2, n3 = int(cnt[i0 + 2]), int(cnt[i0 + 3])
        w2 = n2 / (n2 + n3) if (n2 + n3) else 0.5
        t5 = fe.t_drop5(y, cell, s, m, psi,
                        cvec(r, KIND[x["contrast"]], w2), n_c)
        x["rev_t_drop5"] = t5
        x["cont_t_drop5"] = -t5
        x["flip_drop5"] = (bool(np.sign(x["rev_t"]) != np.sign(t5))
                           if np.isfinite(t5) else np.nan)
    for x in fam:
        r = int(x["regime"][1])
        states = STATES[KIND[x["contrast"]]]
        sub = o[(o["cell"] == r) & o["state"].isin(states)]
        x["n_obs"] = int(len(sub))
        x["n_cmonths"] = int(sub[["sym", "month"]].drop_duplicates().shape[0])
    rows.extend(fam)

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
            check=f"rev h={h} {weighting} R{r} C2 identity",
            expected=f"{exp:.12g}", actual=f"{est2:.12g}",
            pass_=bool(abs(exp - est2) < 1e-10)))


def main() -> int:
    t0 = time.time()
    rows, checks = [], []

    def check(name, expected, got, ok):
        checks.append(dict(check=name, expected=expected, actual=got, pass_=bool(ok)))

    for h in HORIZONS:
        b = load(h)
        for weighting, obs_fn in (("event", obs_event),
                                  ("contract_day", obs_contract_day)):
            run(obs_fn(b), h, weighting, rows, checks)

    df = pd.DataFrame(rows)
    for (h, w), g in df.groupby(["h", "weighting"], sort=False):
        check(f"h={h} {w} n contrasts", 12, len(g), len(g) == 12)
        check(f"h={h} {w} p_bh finite", 12, int(g["p_bh"].notna().sum()),
              int(g["p_bh"].notna().sum()) == 12)
        check(f"h={h} {w} t_drop5 finite", 12,
              int(g["rev_t_drop5"].notna().sum()),
              int(g["rev_t_drop5"].notna().sum()) == 12)
        bad = int((np.abs(g["cont_estimate_pp"] + g["rev_estimate_pp"]) > 1e-12).sum())
        check(f"h={h} {w} cont = -rev", 0, bad, bad == 0)

    # n cross-check against P4-1a (same events, same contrast cells)
    c1 = pd.read_parquet(TBL / "p4_1_contrasts.parquet")
    c1 = c1[(c1["dv"] == "y_raw") & (c1["in_bh"])][["weighting", "h", "regime",
                                                    "contrast", "n_obs", "n_cmonths"]]
    mg = df.merge(c1, on=["weighting", "h", "regime", "contrast"],
                  how="left", suffixes=("", "_p41"))
    dn = int((mg["n_obs"] != mg["n_obs_p41"]).sum())
    dm = int((mg["n_cmonths"] != mg["n_cmonths_p41"]).sum())
    check("n_obs matches P4-1a", 0, dn, dn == 0)
    check("n_cmonths matches P4-1a", 0, dm, dm == 0)

    # flat share at h=1 event (diagnostic)
    b1 = load(1)
    flat = float(b1["flat"].mean())
    print(f"flat share (h=1, events): {flat:.4%}")

    cdf = pd.DataFrame(checks)
    cdf.to_csv(TBL / "exp3_validation.csv", index=False)
    print(cdf.to_string(index=False))

    df.to_parquet(TBL / "p4_3_reversal.parquet", index=False)
    df.to_csv(TBL / "p4_3_reversal.csv", index=False)
    print(f"\nPASS {int(cdf['pass_'].sum())} / {len(cdf)}; elapsed {time.time()-t0:.1f}s")
    return 0 if int(cdf["pass_"].sum()) == len(cdf) else 1


if __name__ == "__main__":
    raise SystemExit(main())
