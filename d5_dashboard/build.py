"""D5 -- build the interactive price/OI regime board.

    python -m d5_dashboard                 # opens on the last day in the dataset
    python -m d5_dashboard --asof 2026-05-12

One self-contained HTML file with every day embedded (gzip + base64), a date
picker, and no server.  Reads only data/, writes only data/09_dashboard/.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import payload as P
from .html import CSS, JS, PAGE

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "09_dashboard"
LAB = DATA / "05_regime" / "regime_labels" / "freq=1h"
BASE1 = DATA / "07_funding" / "base" / "p4_base_h=1.parquet"
T0 = pd.Timestamp("2021-12-01", tz="UTC")


def log(msg: str) -> None:
    print(msg, flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    print("  [%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def _labels_for(day: str) -> pd.DataFrame:
    ts = pd.Timestamp(day, tz="UTC")
    path = LAB / ("year=%d" % ts.year) / ("chunk=%s.parquet" % ts.strftime("%Y-%m"))
    cols = ["symbol", "ts_end", "regime"]
    return pd.read_parquet(path, columns=cols)


def main() -> int:
    ap = argparse.ArgumentParser(description="D5 - interactive regime board")
    ap.add_argument("--asof", default=None, help="day the page opens on (YYYY-MM-DD)")
    args = ap.parse_args()

    log("D5 board   building the full-history payload ...")
    pl = P.build()
    days, rows, syms = pl["days"], pl["rows"], pl["symbols"]
    asof = args.asof or days[-1]
    if asof not in set(days):
        raise SystemExit("--asof %s is not a day in the dataset (%s .. %s)"
                         % (asof, days[0], days[-1]))
    log("  days %d | symbols %d | contracts per day %d"
        % (len(days), len(syms), len(rows[0])))

    ok = True
    full = sum(1 for r in rows if len(r) == 50)
    mn, mx = min(len(r) for r in rows), max(len(r) for r in rows)
    ok &= check("every day falls inside the 50-contract universe",
                mx <= 50 and mn >= 45,
                "min %d / max %d rows per day, %d of %d days complete"
                % (mn, mx, full, len(rows)))

    i = days.index(asof)
    day = rows[i]
    bar = pd.Timestamp(asof, tz="UTC") + pd.Timedelta(days=1)
    lab = _labels_for(asof)
    lab = lab[lab.symbol.isin([syms[r[1]] for r in day])]

    r1 = [r for r in day if r[P.REGIMES.index("R1") + 9] is not None]
    sample = r1 if len(r1) <= 3 else [r1[0], r1[len(r1) // 2], r1[-1]]
    hit = True
    for r in sample:
        ev_ts = bar - pd.Timedelta(hours=float(r[9]))
        m = lab[(lab.symbol == syms[r[1]]) & (lab.ts_end == ev_ts) & (lab.regime == "R1")]
        hit &= len(m) == 1
    ok &= check("sampled R1 rows reproduce from the raw label table", hit,
                "%d sampled on %s" % (len(sample), asof))

    hh = int((bar - T0).total_seconds() // 3600)
    if BASE1.exists():
        b = pd.read_parquet(BASE1, columns=["sym", "hour", "state"])
        for probe in (hh, hh - 1):
            bb = b[(b.hour == probe) & (b.state >= 0)]
            if len(bb):
                b = bb
                break
        else:
            b = b.iloc[0:0]
        if len(b):
            idx = {syms[r[1]]: r[6] for r in day}
            j = b[b.sym.isin(idx)]
            same = all(idx[s] == int(st) for s, st in zip(j.sym, j.state))
            ok &= check("funding state agrees with p4_base_h=1", same,
                        "%d overlapping rows" % len(j))
        else:
            check("funding state vs p4_base_h=1", True, "no p4 rows at this hour (skipped)")

    band_ok = True
    for r in day:
        if r[12] is None:
            continue
        lo, hi = P.BAND[int(r[6])]
        band_ok &= (lo - 1e-9) <= r[12] <= (hi + 1e-9)
    ok &= check("funding percentile sits inside its state's band", band_ok,
                "%d rows" % sum(1 for r in day if r[12] is not None))

    raw = json.dumps(pl, separators=(",", ":"), allow_nan=False).encode()
    b64 = base64.b64encode(gzip.compress(raw, 6)).decode("ascii")
    html = (PAGE.replace("__CSS__", CSS).replace("__JS__", JS)
                .replace("__PAYLOAD__", b64).replace("__ASOF__", asof))
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "dashboard.html"
    dst.write_text(html, encoding="utf-8", newline=chr(10))
    log("  payload %.1f MB raw -> %.1f MB embedded" % (len(raw) / 1e6, len(b64) / 1e6))
    log("  written %s (%.1f MB)" % (dst, dst.stat().st_size / 1e6))
    log("  checks %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
