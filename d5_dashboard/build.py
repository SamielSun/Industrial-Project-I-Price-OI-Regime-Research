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
from collections import Counter
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
NFIELDS = 9


def log(msg: str) -> None:
    print(msg, flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    print("  [%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def _month_file(day: str) -> Path:
    ts = pd.Timestamp(day, tz="UTC")
    return LAB / ("year=%d" % ts.year) / ("chunk=%s.parquet" % ts.strftime("%Y-%m"))


def main() -> int:
    ap = argparse.ArgumentParser(description="D5 - interactive regime board")
    ap.add_argument("--asof", default=None, help="day the page opens on (YYYY-MM-DD)")
    args = ap.parse_args()

    log("D5 board   building the full-history payload ...")
    pl = P.build()
    days, rows, syms, evs = pl["days"], pl["rows"], pl["symbols"], pl["ev"]
    asof = args.asof or days[-1]
    if asof not in set(days):
        raise SystemExit("--asof %s is not a day in the dataset (%s .. %s)"
                         % (asof, days[0], days[-1]))
    log("  days %d | symbols %d | rows/day %d | events %d"
        % (len(days), len(syms), len(rows[0]), sum(len(x) for x in evs)))

    ok = True
    mn, mx = min(len(r) for r in rows), max(len(r) for r in rows)
    full = sum(1 for r in rows if len(r) == 50)
    ok &= check("every day falls inside the 50-contract universe",
                mx <= 50 and mn >= 49 and len(rows) == len(days),
                "min %d / max %d rows per day, %d of %d days complete"
                % (mn, mx, full, len(rows)))
    ok &= check("every row carries %d fields" % NFIELDS,
                all(len(x) == NFIELDS for r in rows for x in r),
                "checked %d rows" % sum(len(r) for r in rows))

    states = Counter(x[6] for r in rows for x in r)
    ok &= check("bar_state is in {-2,-1,0,1,2,3}",
                set(states) <= {-2, -1, 0, 1, 2, 3},
                "counts %s" % dict(sorted(states.items())))

    # sampled events must reproduce from the raw label table
    i = days.index(asof)
    bar = pd.Timestamp(asof, tz="UTC") + pd.Timedelta(days=1)
    lab = pd.read_parquet(_month_file(asof), columns=["symbol", "ts_end", "regime"])
    pool = [e for e in evs[i] if e[2] == 0]
    sample = pool[:1] + pool[len(pool) // 2:len(pool) // 2 + 1] + pool[-1:]
    hit = True
    for e in sample:
        ts = pd.Timestamp(asof, tz="UTC") + pd.Timedelta(hours=int(e[1]))
        m = lab[(lab.symbol == syms[e[0]]) & (lab.ts_end == ts) & (lab.regime == "R1")]
        hit &= len(m) == 1
    ok &= check("sampled R1 events reproduce from the raw label table", hit,
                "%d sampled on %s" % (len(sample), asof))

    # funding state recomputed independently from rate vs the contract's own percentiles
    if BASE1.exists() and len(evs[i]) >= 0:
        hh = int((bar - T0).total_seconds() // 3600)
        b = pd.read_parquet(BASE1, columns=["sym", "hour", "state"])
        for probe in (hh, hh - 1):
            bb = b[(b.hour == probe) & (b.state >= 0)]
            if len(bb):
                b = bb
                break
        else:
            b = b.iloc[0:0]
        if len(b):
            idx = {syms[r[1]]: r[2] for r in rows[i]}
            j = b[b.sym.isin(idx)]
            same = all(idx[s] == int(st) for s, st in zip(j.sym, j.state))
            ok &= check("funding state agrees with p4_base_h=1", same,
                        "%d overlapping rows" % len(j))

    hours_ok = all(0 <= e[1] <= 24 for x in evs for e in x)
    regs_ok = all(0 <= e[2] <= 3 for x in evs for e in x)
    ok &= check("event hours in [0,24] and regime codes in [0,3]", hours_ok and regs_ok,
                "%d events" % sum(len(x) for x in evs))

    # the day on screen: what each section will show
    by = {}
    for e in evs[i]:
        by.setdefault(e[0], {})[e[2]] = max(by.get(e[0], {}).get(e[2], -1), e[1])
    for name, reg in (("R1", 0), ("R3", 2), ("R4", 3)):
        got = sorted([(v[reg], syms[k]) for k, v in by.items() if reg in v], reverse=True)
        log("  %s: %d contracts, top1 %s (age %dh)"
            % (name, len(got), got[0][1] if got else "-", 24 - got[0][0] if got else -1))
    log("  at the bar: %s" % dict(sorted(Counter(r[6] for r in rows[i]).items())))

    raw = json.dumps(pl, separators=(",", ":"), allow_nan=False).encode()
    b64 = base64.b64encode(gzip.compress(raw, 6, mtime=0)).decode("ascii")
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
