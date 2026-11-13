"""Phase 4 · build — P4-0 analysis base.

Mirrors the Phase 3 layout: one build entry point, per-block experiment scripts
under experiment/, and infer.py reused from phase3_event.

Step `data`:
  panel (cell 0..4) + forward (fwd_h, rv_h, ok_h) + events (rev/cont/hit/flat,
  mfe/mae/mdd, mkt_vol_state) + labels (funding booleans, p25/p75/p90,
  mkt_vol_state) -> phase4_funding/data/p4_base_h={h}.parquet

The base keeps:
  * event rows (cell 1..4),
  * benchmark rows (cell 0, same-direction price-over-threshold with quiet OI),
  and drops cell -1 (price not over threshold).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "phase3_event"))

from config import EVENT  # noqa: E402
import infer as I  # noqa: E402,F401  (kept for the block scripts)

T0 = pd.Timestamp("2021-12-01", tz="UTC")
HORIZONS = list(EVENT.horizons)
PANEL = ROOT / "data/06_event_study/panel/freq=1h"
FWD = ROOT / "data/06_event_study/forward/freq=1h"
EVENTS = ROOT / "data/06_event_study/events/events_1h.parquet"
LABELS = ROOT / "data/05_regime/regime_labels/freq=1h"
OUT = ROOT / "phase4_funding/data"
TBL = ROOT / "phase4_funding/tables"

PANEL_COLS = ["symbol", "hour", "dir", "oi3", "cell", "fund", "y_raw", "lrv"]
EV_COLS = (["symbol", "ts_end", "regime", "mkt_vol_state"]
           + [f"{x}_{h}h" for h in HORIZONS
              for x in ("fwd", "excess_fwd", "rev", "cont", "hit", "flat",
                        "mfe", "mae", "mdd")])
LAB_COLS = ["symbol", "ts_end", "funding_negative", "funding_neutral",
            "funding_high", "funding_extreme", "funding_p25", "funding_p75",
            "funding_p90", "mkt_vol_state"]


def _hour(ts: pd.Series) -> np.ndarray:
    return ((ts - T0).dt.total_seconds() // 3600).to_numpy("int64")


def load_symbols() -> tuple[dict, dict, int]:
    s = pd.read_parquet(PANEL / "symbols.parquet")
    code2sym = dict(zip(s["code"].astype("int64"), s["symbol"]))
    sym2code = {v: k for k, v in code2sym.items()}
    return code2sym, sym2code, len(code2sym)


def load_panel(h: int, n_sym: int, code2sym: dict) -> pd.DataFrame:
    d = pd.read_parquet(PANEL / f"h={h}.parquet", columns=PANEL_COLS)
    d = d[d["cell"].between(0, 4)].copy()
    d["symbol"] = d["symbol"].astype("int64")
    d["hour"] = d["hour"].astype("int64")
    d["key"] = d["hour"] * n_sym + d["symbol"]
    d["sym"] = d["symbol"].map(code2sym)
    d["ts_end"] = T0 + pd.to_timedelta(d["hour"], unit="h")
    d["month"] = d["ts_end"].dt.tz_localize(None).dt.to_period("M").astype(str)
    if d["key"].duplicated().any():
        raise SystemExit(f"panel h={h}: duplicate (hour, symbol)")
    return d.reset_index(drop=True)


def _keep(d: pd.DataFrame, keys: np.ndarray) -> pd.DataFrame:
    """Filter a chunk to the panel keys (keys sorted, unique)."""
    k = d["key"].to_numpy("int64")
    pos = np.searchsorted(keys, k)
    pos_c = np.minimum(pos, len(keys) - 1)
    hit = (pos < len(keys)) & (keys[pos_c] == k)
    return d.loc[hit].reset_index(drop=True)


def load_forward(h: int, keys: np.ndarray, n_sym: int, sym2code: dict) -> pd.DataFrame:
    parts = []
    for p in sorted(FWD.rglob("*.parquet")):
        d = pd.read_parquet(p, columns=["symbol", "ts_end", f"fwd_{h}h",
                                        f"rv_{h}h", f"ok_{h}h"])
        d["symbol"] = d["symbol"].map(sym2code)
        d = d[d["symbol"].notna()]
        d["hour"] = _hour(d["ts_end"])
        d["key"] = d["hour"] * n_sym + d["symbol"].astype("int64")
        d = _keep(d, keys)
        if len(d):
            parts.append(d[["key", f"fwd_{h}h", f"rv_{h}h", f"ok_{h}h"]])
    out = pd.concat(parts, ignore_index=True).rename(
        columns={f"fwd_{h}h": "fwd", f"rv_{h}h": "rv", f"ok_{h}h": "ok"})
    if out["key"].duplicated().any():
        raise SystemExit(f"forward h={h}: duplicate key")
    return out


def load_events(h: int, keys: np.ndarray, n_sym: int, sym2code: dict) -> pd.DataFrame:
    d = pd.read_parquet(EVENTS, columns=EV_COLS)
    d["symbol"] = d["symbol"].map(sym2code)
    d = d[d["symbol"].notna()].copy()
    d["hour"] = _hour(d["ts_end"])
    d["key"] = d["hour"] * n_sym + d["symbol"].astype("int64")
    d = _keep(d, keys)
    cols = {"key": "key", "regime": "regime_ev", "mkt_vol_state": "mkt_vol_ev",
            f"fwd_{h}h": "fwd_ev", f"excess_fwd_{h}h": "y_ev",
            f"rev_{h}h": "rev_ev", f"cont_{h}h": "cont_ev",
            f"hit_{h}h": "hit_ev", f"flat_{h}h": "flat_ev",
            f"mfe_{h}h": "mfe", f"mae_{h}h": "mae", f"mdd_{h}h": "mdd"}
    return d[list(cols)].rename(columns=cols)


def load_labels(keys: np.ndarray, n_sym: int, sym2code: dict) -> pd.DataFrame:
    parts = []
    for p in sorted(LABELS.rglob("*.parquet")):
        d = pd.read_parquet(p, columns=LAB_COLS)
        d["symbol"] = d["symbol"].map(sym2code)
        d = d[d["symbol"].notna()]
        d["hour"] = _hour(d["ts_end"])
        d["key"] = d["hour"] * n_sym + d["symbol"].astype("int64")
        d = _keep(d, keys)
        if len(d):
            parts.append(d[["key", "funding_negative", "funding_neutral",
                            "funding_high", "funding_extreme", "funding_p25",
                            "funding_p75", "funding_p90", "mkt_vol_state"]])
    out = pd.concat(parts, ignore_index=True).rename(
        columns={"mkt_vol_state": "mkt_vol_lab"})
    if out["key"].duplicated().any():
        raise SystemExit("labels: duplicate key")
    return out


def derive(base: pd.DataFrame) -> pd.DataFrame:
    b = base
    b["state"] = b["fund"].astype("int64")
    b["fund_neg"] = b["state"] == 0
    b["fund_neu"] = b["state"] == 1
    b["fund_high"] = b["state"].isin([2, 3])
    b["fund_ext"] = b["state"] == 3
    b["benchmark"] = b["cell"] == 0
    b["regime"] = np.where(b["cell"] == 0, "R0", "R" + b["cell"].astype(str))

    s = np.sign(b["fwd"].to_numpy("float64"))
    d = b["dir"].to_numpy("int64")
    ok = np.isfinite(s)
    b["rev"] = np.where(ok, (s == -d).astype("int8"), np.nan)
    b["cont_exact"] = np.where(ok, (s == d).astype("int8"), np.nan)
    b["flat"] = np.where(ok, (s == 0).astype("int8"), np.nan)
    b["hit"] = b["cont_exact"]
    b["cont"] = 1.0 - b["rev"]          # guidance's definition: flat counts as cont
    return b


def build_h(h: int, code2sym: dict, sym2code: dict, n_sym: int) -> tuple[pd.DataFrame, list]:
    panel = load_panel(h, n_sym, code2sym)
    keys = np.sort(panel["key"].to_numpy("int64"))
    fwd = load_forward(h, keys, n_sym, sym2code)
    ev = load_events(h, keys, n_sym, sym2code)
    lab = load_labels(keys, n_sym, sym2code)

    b = panel.merge(fwd, on="key", how="left", validate="one_to_one")
    b = b.merge(ev, on="key", how="left", validate="one_to_one")
    b = b.merge(lab, on="key", how="left", validate="one_to_one")
    b = derive(b)

    print(f"  h={h:<3} panel cell0-4 {len(panel):,} | fwd matched {fwd['key'].size:,} "
          f"| events {ev['key'].size:,} | labels {lab['key'].size:,} "
          f"| base {len(b):,}", flush=True)
    return b, [panel, fwd, ev, lab]


def fmt(x) -> str:
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def main_data() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    TBL.mkdir(parents=True, exist_ok=True)
    code2sym, sym2code, n_sym = load_symbols()
    print(f"symbols {n_sym}; horizons {HORIZONS}", flush=True)

    checks = []

    def check(name, expected, actual, ok, note=""):
        checks.append(dict(check=name, expected=fmt(expected), actual=fmt(actual),
                           pass_=bool(ok), note=note))

    bases = {}
    for h in HORIZONS:
        b, _ = build_h(h, code2sym, sym2code, n_sym)
        b.to_parquet(OUT / f"p4_base_h={h}.parquet", index=False)
        bases[h] = b

    b1 = bases[HORIZONS[0]]
    ev1 = b1[(b1.cell > 0) & (b1.state.between(0, 3))]

    # 1. n reconciliation
    check("n rows cell1-4 & fund0-3 (h=1)", 255_857, len(ev1),
          len(ev1) == 255_857)
    for s, exp in [(0, 93_489), (1, 123_907), (2, 18_834), (3, 19_627)]:
        got = int((ev1.state == s).sum())
        check(f"n state={s} (h=1)", exp, got, got == exp)
    for s, exp in [(0, 9_499), (1, 9_461), (2, 3_377), (3, 2_777)]:
        # expected counts are cell-level sums over the four regimes, not a
        # cross-regime unique count (a contract-month can be in several regimes)
        got = sum(
            ev1[(ev1.cell == c) & (ev1.state == s)][["sym", "month"]]
            .drop_duplicates().shape[0]
            for c in (1, 2, 3, 4)
        )
        check(f"contract-months state={s} (h=1, cell-level sum)", exp, got, got == exp)
    for cell, s, exp_rows, exp_cm in [(1, 1, 37_038, 2_384), (1, 3, 6_905, 752),
                                      (3, 3, 2_416, 584)]:
        sub = ev1[(ev1.cell == cell) & (ev1.state == s)]
        check(f"R{cell} x state{s} rows (h=1)", exp_rows, len(sub),
              len(sub) == exp_rows)
        check(f"R{cell} x state{s} cmonths (h=1)", exp_cm,
              sub[["sym", "month"]].drop_duplicates().shape[0],
              sub[["sym", "month"]].drop_duplicates().shape[0] == exp_cm)
    r1h = ev1[(ev1.cell == 1) & ev1.fund_high]
    check("R1 x high(incl ext) rows (h=1)", 13_184, len(r1h), len(r1h) == 13_184)
    check("R1 x high(incl ext) cmonths (h=1)", 1_183,
          r1h[["sym", "month"]].drop_duplicates().shape[0],
          r1h[["sym", "month"]].drop_duplicates().shape[0] == 1_183)

    # 2. join coverage
    for h, b in bases.items():
        n_ev = int((b.cell > 0).sum())
        check(f"h={h} panel events", n_ev, n_ev, True)
        check(f"h={h} fwd non-null on events",
              n_ev, int((b.loc[b.cell > 0, "fwd"].notna()).sum()),
              int((b.loc[b.cell > 0, "fwd"].notna()).sum()) == n_ev)
        check(f"h={h} events table matched",
              n_ev, int((b.loc[b.cell > 0, "rev_ev"].notna()).sum()),
              int((b.loc[b.cell > 0, "rev_ev"].notna()).sum()) == n_ev)
        check(f"h={h} labels matched",
              len(b), int(b["funding_negative"].notna().sum()),
              int(b["funding_negative"].notna().sum()) == len(b))

    # 3. fwd - y_raw constant within hour (market mean)
    for h, b in bases.items():
        d = b[b["fwd"].notna()].copy()
        d["diff"] = d["fwd"] - d["y_raw"]
        sd = d.groupby("hour")["diff"].std().max()
        check(f"h={h} max within-hour sd(fwd-y_raw)", 0.0, float(sd),
              float(sd) < 1e-12)

    # 4. high-union identity
    for h, b in bases.items():
        e = b[(b.cell > 0) & b.state.between(0, 3)]
        for cell in (1, 2, 3, 4):
            s = e[e.cell == cell]
            hi = s[s.fund_high]
            h2 = s[s.state == 2]
            h3 = s[s.state == 3]
            if len(h2) and len(h3):
                w = len(h2) / (len(h2) + len(h3))
                exp = w * h2["y_raw"].mean() + (1 - w) * h3["y_raw"].mean()
                got = hi["y_raw"].mean()
                check(f"h={h} R{cell} high-union identity", float(exp), float(got),
                      abs(exp - got) < 1e-12)

    # 5. rev / cont / flat vs events table
    for h, b in bases.items():
        e = b[(b.cell > 0) & b["rev_ev"].notna()]
        for col, ev_col in [("rev", "rev_ev"), ("cont_exact", "cont_ev"),
                            ("flat", "flat_ev"), ("hit", "hit_ev")]:
            m = int((e[col].to_numpy() != e[ev_col].to_numpy()).sum())
            check(f"h={h} {col} vs events {ev_col}", 0, m, m == 0)
        bad = int((e["rev"] + e["cont_exact"] + e["flat"] != 1).sum())
        check(f"h={h} rev+cont_exact+flat=1", 0, bad, bad == 0)

    # 6. benchmark coverage: every regime x funding has same-direction cell-0 rows
    bm = b1[b1.cell == 0]
    for cell, d in [(1, 1), (2, 1), (3, -1), (4, -1)]:
        for s in range(4):
            got = int(((bm.state == s) & (bm.dir == d)).sum())
            check(f"R{cell} x state{s} benchmark rows", ">0", got, got > 0)

    # additional: state vs label booleans; mkt_vol; fwd_ev/excess_ev
    for h, b in bases.items():
        st = b["state"]
        bad = int(((st == 0) != b["funding_negative"]).sum()
                  + ((st == 1) != b["funding_neutral"]).sum()
                  + ((st.isin([2, 3])) != b["funding_high"]).sum()
                  + ((st == 3) != b["funding_extreme"]).sum())
        check(f"h={h} state vs label booleans", 0, bad, bad == 0)
        e = b[(b.cell > 0) & b["fwd_ev"].notna()]
        d1 = float(np.nanmax(np.abs(e["fwd"].to_numpy() - e["fwd_ev"].to_numpy())))
        d2 = float(np.nanmax(np.abs(e["y_raw"].to_numpy() - e["y_ev"].to_numpy())))
        check(f"h={h} fwd vs events fwd", 0.0, d1, d1 < 1e-12)
        check(f"h={h} y_raw vs events excess", 0.0, d2, d2 < 1e-12)
        d3 = float(np.nanmax(np.abs(np.exp(e["lrv"].to_numpy()) - e["rv"].to_numpy())))
        check(f"h={h} exp(lrv) vs rv", 0.0, d3, d3 < 1e-10)
        m = int((e["mkt_vol_lab"].astype(str).to_numpy()
                 != e["mkt_vol_ev"].astype(str).to_numpy()).sum())
        check(f"h={h} mkt_vol labels vs events", 0, m, m == 0)

    df = pd.DataFrame(checks)
    df.to_csv(TBL / "p4_0_validation.csv", index=False)
    n_pass = int(df["pass_"].sum())
    print("\nP4-0 validation")
    print(df.to_string(index=False))
    print(f"\nPASS {n_pass} / {len(df)}; elapsed {time.time() - t0:.1f}s")
    return 0 if n_pass == len(df) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase 4 · build")
    ap.add_argument("step", choices=["data"])
    a = ap.parse_args()
    return {"data": main_data}[a.step]()


if __name__ == "__main__":
    raise SystemExit(main())
