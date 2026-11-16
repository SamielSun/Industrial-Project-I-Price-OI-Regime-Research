"""D5 -- build the per-day payload that the interactive board embeds in one HTML.

One snapshot per UTC day (the last bar of that day) for the 50-contract universe of
that month.  The only per-event data carried is the day's event list; everything
else about events (the latest one, its age, the section membership) is derived
from it in the browser.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LAB = DATA / "05_regime" / "regime_labels" / "freq=1h"
FEAT = DATA / "02_features" / "features_1h"
OID = DATA / "01_layer2" / "oi_1h"
FUND = DATA / "01_layer2" / "funding"
MEM = DATA / "03_reference" / "universe_membership.parquet"

BAND = {0: (0.00, 0.25), 1: (0.25, 0.75), 2: (0.75, 0.90), 3: (0.90, 1.00)}
REGIMES = ("R1", "R2", "R3", "R4")


def _files(root: Path) -> list[Path]:
    return sorted(root.glob("year=*/chunk=*.parquet"))


def _dayend(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["ts_end"].dt.hour == 0]


def collect_dayend() -> pd.DataFrame:
    cols = ["symbol", "ts_end", "regime", "excl_reason", "price_change", "oi_change",
            "funding_negative", "funding_neutral", "funding_high", "funding_extreme",
            "funding_p25", "funding_p75", "funding_p90", "mkt_vol_state"]
    return pd.concat([_dayend(pd.read_parquet(p, columns=cols)) for p in _files(LAB)],
                     ignore_index=True)


def collect_events() -> pd.DataFrame:
    cols = ["symbol", "ts_end", "regime", "price_change", "oi_change"]
    parts = []
    for p in _files(LAB):
        d = pd.read_parquet(p, columns=cols)
        parts.append(d[d.regime.isin(REGIMES)])
    return pd.concat(parts, ignore_index=True)


def _hourly_feature(root: Path, col: str, kind: str) -> pd.DataFrame:
    out = []
    for f in _files(root):
        d = pd.read_parquet(f, columns=["symbol", "ts_end", col]).sort_values(["symbol", "ts_end"])
        if kind == "vol":
            r = np.log(d.groupby("symbol")[col].pct_change(fill_method=None).add(1.0))
            d["v24"] = r.groupby(d["symbol"]).transform(
                lambda s: s.rolling(24, min_periods=18).std())
        else:
            d["oi24"] = d.groupby("symbol")[col].pct_change(24, fill_method=None)
        out.append(d[d["ts_end"].dt.hour == 0])
    return pd.concat(out, ignore_index=True)


def _last_rate(day: pd.DataFrame, funding: pd.DataFrame) -> pd.DataFrame:
    f = funding.sort_values("ts_funding")
    d = day.sort_values("ts_end")
    return pd.merge_asof(d, f, left_on="ts_end", right_on="ts_funding",
                         by="symbol", direction="backward")


def collect_funding() -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p, columns=["symbol", "ts_funding", "funding_rate"])
                      for p in _files(FUND)], ignore_index=True)


def funding_position(rate, p25, p75, p90, state):
    if state not in BAND:
        return None
    lo_b, hi_b = BAND[state]
    if not all(np.isfinite(x) for x in (rate, p25, p75, p90)):
        return 0.5 * (lo_b + hi_b)
    if state == 0:
        a, b = (2.0 * p25 if p25 < 0 else 0.0), p25
    elif state == 1:
        a, b = p25, p75
    elif state == 2:
        a, b = p75, p90
    else:
        a, b = p90, p90 + max(abs(p90), 1e-9)
    if b - a <= 1e-12:
        return 0.5 * (lo_b + hi_b)
    t = float(np.clip((rate - a) / (b - a), 0.0, 1.0))
    return lo_b + (hi_b - lo_b) * t


def _num(v, scale=1.0, nd=1):
    """Round for JSON; anything non-finite becomes None (JSON has no NaN)."""
    if v is None:
        return None
    v = float(v) * scale
    return round(v, nd) if np.isfinite(v) else None


def build() -> dict:
    day = collect_dayend()
    ev = collect_events()
    fund = collect_funding()
    mem = pd.read_parquet(MEM)

    day = day.merge(_hourly_feature(FEAT, "close", "vol")[["symbol", "ts_end", "v24"]],
                    on=["symbol", "ts_end"], how="left")
    day = day.merge(_hourly_feature(OID, "oi", "oi")[["symbol", "ts_end", "oi24"]],
                    on=["symbol", "ts_end"], how="left")
    day = _last_rate(day, fund)

    day = day.sort_values(["symbol", "ts_end"])
    day["vol_pct"] = (day.groupby("symbol")["v24"]
                         .transform(lambda s: s.rolling(90, min_periods=60).rank(pct=True)))

    st = np.full(len(day), -1, dtype="int8")
    for key, val in (("funding_negative", 0), ("funding_neutral", 1),
                     ("funding_high", 2), ("funding_extreme", 3)):
        st = np.where(day[key].to_numpy(dtype=bool), val, st)
    day["funding"] = st
    day["fund_pct"] = [funding_position(r, a, b, c, int(s))
                       for r, a, b, c, s in zip(day["funding_rate"], day["funding_p25"],
                                                day["funding_p75"], day["funding_p90"],
                                                day["funding"])]

    # state of each contract at the bar itself: 0-3 = R1-R4, -1 = no regime, -2 = n/a
    reg = day["regime"].to_numpy()
    okr = day["excl_reason"].to_numpy() == "ok"
    bar_state = np.where(okr, -1, -2).astype("int8")
    for i, rg in enumerate(REGIMES):
        bar_state = np.where(reg == rg, i, bar_state)
    day["bar_state"] = bar_state

    day["month"] = (day["ts_end"] - pd.Timedelta(hours=1)).dt.strftime("%Y-%m")
    day = day.merge(mem[["symbol", "month", "rank"]], on=["symbol", "month"], how="inner")
    day["date"] = (day["ts_end"] - pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d")
    day = day.sort_values(["date", "rank"])

    syms = sorted(day["symbol"].unique())
    sidx = {s: i for i, s in enumerate(syms)}
    days = sorted(day["date"].unique())

    rows, mkt = [], []
    for d, g in day.groupby("date", sort=True):
        mkt.append(str(g["mkt_vol_state"].mode().iloc[0]) if len(g) else "unknown")
        rows.append([[int(r.rank), sidx[r.symbol], int(r.funding),
                      _num(r.vol_pct, 1, 3), _num(r.oi24, 1, 4), _num(r.fund_pct, 1, 3),
                      int(r.bar_state), _num(r.price_change, 1e4, 1),
                      _num(r.oi_change, 100, 2)]
                     for r in g.itertuples(index=False)])

    # ---- per-day event list: the single source of truth for every event fact ----
    # a day's window is [D 00:00, D+1 00:00]; an event exactly at midnight belongs to
    # that day (hour 0) and also to the previous day (hour 24)
    e = ev.copy()
    e["day"] = e["ts_end"].dt.floor("D")
    e["hour"] = ((e["ts_end"] - e["day"]).dt.total_seconds() / 3600).round().astype("int8")
    mid = e[e["hour"] == 0]
    if len(mid):
        e = pd.concat([e, mid.assign(day=mid["day"] - pd.Timedelta(days=1), hour=24)],
                      ignore_index=True)
    e["day_s"] = e["day"].dt.strftime("%Y-%m-%d")
    # only events on days when the contract is actually in that month's universe
    valid = set(zip(day["symbol"], day["date"]))
    e = e[[(s, d) in valid for s, d in zip(e["symbol"], e["day_s"])]]
    e["ri"] = e["regime"].map({r: i for i, r in enumerate(REGIMES)}).astype("int8")
    e["si"] = e["symbol"].map(sidx).astype("int32")

    ev_list = {d: [] for d in days}
    for d, g in e.groupby("day_s", sort=False):
        block = [[int(si), int(h), int(ri), _num(pc, 1e4, 1), _num(oc, 100, 2)]
                 for si, h, ri, pc, oc in zip(g["si"], g["hour"], g["ri"],
                                              g["price_change"], g["oi_change"])]
        block.sort(key=lambda x: (x[0], x[1]))
        ev_list[d] = block

    return {"symbols": syms, "days": days, "mkt": mkt, "rows": rows,
            "ev": [ev_list[d] for d in days]}


if __name__ == "__main__":
    import base64
    import gzip
    import json
    import time

    t = time.time()
    pl = build()
    raw = json.dumps(pl, separators=(",", ":"), allow_nan=False).encode()
    gz = gzip.compress(raw, 6, mtime=0)
    print("days %d | symbols %d | fields/row %d | events %d"
          % (len(pl["days"]), len(pl["symbols"]), len(pl["rows"][0][0]),
             sum(len(x) for x in pl["ev"])))
    print("json %.2f MB | gzip %.2f MB | b64 %.2f MB | %.0fs"
          % (len(raw) / 1e6, len(gz) / 1e6, len(base64.b64encode(gz)) / 1e6, time.time() - t))
