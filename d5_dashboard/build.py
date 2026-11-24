"""D5 -- build the interactive price/OI regime board.

    python -m d5_dashboard                     # opens on the last bar
    python -m d5_dashboard --asof 2026-08-31T14 # any hour in the hourly window
    python -m d5_dashboard --asof 2024-05-10    # a day-close snapshot

Hourly snapshots for the trailing 180 days, one snapshot per day before that.
One self-contained HTML file with the payload embedded gzip+base64; no server.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
from collections import Counter
from pathlib import Path

import pandas as pd

from . import payload as P
from .html import CSS, JS, PAGE

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "09_dashboard"
LAB = DATA / "05_regime" / "regime_labels" / "freq=1h"
BASE1 = DATA / "07_funding" / "base" / "p4_base_h=1.parquet"
T0 = pd.Timestamp("2021-12-01", tz="UTC")
NFIELDS = 11


def log(msg: str) -> None:
    print(msg, flush=True)


def check(name: str, ok: bool, detail: str = "") -> bool:
    print("  [%s] %s  %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)
    return bool(ok)


def main() -> int:
    ap = argparse.ArgumentParser(description="D5 - interactive regime board")
    ap.add_argument("--asof", default=None,
                    help="snapshot to open on: YYYY-MM-DD (day close) or YYYY-MM-DDTHH")
    args = ap.parse_args()

    log("D5 board   building the payload (hourly window %dd) ..." % P.HOURS_WINDOW_DAYS)
    pl = P.build()
    snap, kind, rows, syms, days, evs = (pl["snap"], pl["kind"], pl["rows"],
                                         pl["symbols"], pl["days"], pl["ev"])
    want = args.asof or snap[-1]
    if want.isdigit() is False and "T" not in want:
        want = want + "T23"
    idx_of = {s: i for i, s in enumerate(snap)}
    if want not in idx_of:
        raise SystemExit("--asof %s is not a snapshot (use YYYY-MM-DD or YYYY-MM-DDTHH, "
                         "range %s .. %s)" % (want, snap[0], snap[-1]))
    i = idx_of[want]
    log("  snapshots %d (daily %d / hourly %d) | days %d | events %d"
        % (len(snap), kind.count(0), kind.count(1), len(days), sum(len(x) for x in evs)))

    ok = True
    ok &= check("snapshots are strictly increasing", all(snap[k] < snap[k + 1] for k in range(len(snap) - 1)),
                "%s .. %s" % (snap[0], snap[-1]))
    mn, mx = min(len(r) for r in rows), max(len(r) for r in rows)
    ok &= check("every snapshot falls inside the 50-contract universe",
                mx <= 50 and mn >= 49, "min %d / max %d rows, %d snapshots" % (mn, mx, len(rows)))
    ok &= check("every row carries %d fields" % NFIELDS,
                all(len(x) == NFIELDS for r in rows for x in r),
                "checked %d rows" % sum(len(r) for r in rows))
    n_all = sum(len(r) for r in rows)
    n_vol = sum(1 for r in rows for x in r if x[3] is not None)
    ok &= check("volatility percentile is populated", n_vol >= 0.9 * n_all,
                "%d / %d rows (%.1f%%)" % (n_vol, n_all, 100.0 * n_vol / n_all))
    n_lvl = sum(1 for r in rows for x in r if x[9] is not None)
    n_rat = sum(1 for r in rows for x in r if x[10] is not None)
    ok &= check("24h volatility level and ratio are populated",
                n_lvl >= 0.9 * n_all and n_rat >= 0.9 * n_all,
                "level %d / ratio %d of %d" % (n_lvl, n_rat, n_all))

    states = Counter(x[6] for r in rows for x in r)
    ok &= check("bar_state is in {-2,-1,0,1,2,3}", set(states) <= {-2, -1, 0, 1, 2, 3},
                "counts %s" % dict(sorted(states.items())))

    # sampled events reproduce from the raw label table
    dd, hh = snap[i].split("T")
    lab = pd.read_parquet(LAB / ("year=%d" % int(dd[:4])) / ("chunk=%s.parquet" % dd[:7]),
                          columns=["symbol", "ts_end", "regime"])
    dayIdx = days.index(dd)
    win = []
    for k in (dayIdx - 1, dayIdx):
        if 0 <= k < len(days):
            for e in evs[k]:
                a = k * 24 + e[1]
                if (dayIdx * 24 + int(hh)) - 23 <= a <= dayIdx * 24 + int(hh):
                    win.append((e, k))
    sample = [w for w in win if w[0][2] == 0][:3]
    hit = True
    for e, k in sample:
        # events are labelled by the bar's start; the label row sits at ts_end = start + 1h
        ts = pd.Timestamp(days[k], tz="UTC") + pd.Timedelta(hours=int(e[1]) + 1)
        m = lab[(lab.symbol == syms[e[0]]) & (lab.ts_end == ts) & (lab.regime == "R1")]
        hit &= len(m) == 1
    ok &= check("sampled R1 events reproduce from the raw label table", hit,
                "%d sampled at %s" % (len(sample), snap[i]))

    # funding state agrees with p4_base at the snapshot hour
    if BASE1.exists():
        hh_abs = int((pd.Timestamp(dd, tz="UTC") + pd.Timedelta(hours=int(hh)) - T0).total_seconds() // 3600)
        b = pd.read_parquet(BASE1, columns=["sym", "hour", "state"])
        for probe in (hh_abs, hh_abs - 1):
            bb = b[(b.hour == probe) & (b.state >= 0)]
            if len(bb):
                b = bb
                break
        else:
            b = b.iloc[0:0]
        if len(b):
            cur = {syms[r[1]]: r[2] for r in rows[i]}
            j = b[b.sym.isin(cur)]
            same = all(cur[s] == int(st) for s, st in zip(j.sym, j.state))
            ok &= check("funding state agrees with p4_base_h=1", same,
                        "%d overlapping rows" % len(j))

    hours_ok = all(0 <= e[1] <= 23 for x in evs for e in x)
    regs_ok = all(0 <= e[2] <= 3 for x in evs for e in x)
    ok &= check("event hours in [0,23] and regime codes in [0,3]", hours_ok and regs_ok,
                "%d events" % sum(len(x) for x in evs))

    # what the page will show at the selected snapshot
    log("  at %s: %s" % (snap[i], dict(sorted(Counter(r[6] for r in rows[i]).items()))))
    by = {}
    for e, k in win:
        by.setdefault(e[0], {})[e[2]] = max(by.get(e[0], {}).get(e[2], -1), k * 24 + e[1])
    for name, reg in (("R1", 0), ("R2", 1), ("R3", 2), ("R4", 3)):
        got = sorted([(v[reg], syms[k2]) for k2, v in by.items() if reg in v], reverse=True)
        log("  %s: %d contracts, top1 %s (age %dh)"
            % (name, len(got), got[0][1] if got else "-", (dayIdx * 24 + int(hh)) - got[0][0] if got else -1))

    raw = json.dumps(pl, separators=(",", ":"), allow_nan=False).encode()
    b64 = base64.b64encode(gzip.compress(raw, 6, mtime=0)).decode("ascii")
    html = (PAGE.replace("__CSS__", CSS).replace("__JS__", JS)
                .replace("__PAYLOAD__", b64).replace("__ASOF__", snap[i]))
    OUT.mkdir(parents=True, exist_ok=True)
    dst = OUT / "dashboard.html"
    dst.write_text(html, encoding="utf-8", newline=chr(10))
    log("  payload %.1f MB raw -> %.1f MB embedded" % (len(raw) / 1e6, len(b64) / 1e6))
    log("  written %s (%.1f MB)" % (dst, dst.stat().st_size / 1e6))
    log("  checks %s" % ("PASSED" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())