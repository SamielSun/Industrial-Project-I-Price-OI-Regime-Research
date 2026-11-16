"""D5 -- build the per-day payload that the interactive board embeds in one HTML.

One snapshot per UTC day (the last bar of that day), for the 50-contract universe
of that month.  Everything is vectorised; the result is a small JSON object.
"""
from __future__ import annotations

import glob
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
    """Bars that close each UTC day, with the funding/reference fields attached."""
    cols = ["symbol", "ts_end", "regime", "price_change", "oi_change",
            "funding_negative", "funding_neutral", "funding_high", "funding_extreme",
            "funding_p25", "funding_p75", "funding_p90", "mkt_vol_state"]
    parts = []
    for p in _files(LAB):
        d = pd.read_parquet(p, columns=cols)
        parts.append(_dayend(d))
    return pd.concat(parts, ignore_index=True)


def collect_events() -> pd.DataFrame:
    cols = ["symbol", "ts_end", "regime", "price_change", "oi_change"]
    parts = []
    for p in _files(LAB):
        d = pd.read_parquet(p, columns=cols)
        parts.append(d[d.regime.isin(REGIMES)])
    return pd.concat(parts, ignore_index=True)


def collect_hourly(root: Path, col: str) -> pd.DataFrame:
    parts = []
    for p in _files(root):
        parts.append(pd.read_parquet(p, columns=["symbol", "ts_end", col]))
    return pd.concat(parts, ignore_index=True)


def collect_funding() -> pd.DataFrame:
    parts = [pd.read_parquet(p, columns=["symbol", "ts_funding", "funding_rate"])
             for p in _files(FUND)]
    return pd.concat(parts, ignore_index=True)


def _hourly_feature(root: Path, col: str, kind: str) -> pd.DataFrame:
    """Day-end rows carrying a trailing 24h statistic computed on the hourly grid."""
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


def _event_fields(day: pd.DataFrame, ev: pd.DataFrame):
    """Age / price change / OI change of the most recent event, aligned to day."""
    left = day[["symbol", "ts_end"]].copy()
    left["__i"] = np.arange(len(left))
    d = left.sort_values("ts_end")
    l = ev.sort_values("ts_end").rename(
        columns={"ts_end": "ev_ts", "price_change": "ev_pc", "oi_change": "ev_oc"})
    m = pd.merge_asof(d, l[["symbol", "ev_ts", "ev_pc", "ev_oc"]],
                      left_on="ts_end", right_on="ev_ts", by="symbol", direction="backward")
    age = (m["ts_end"] - m["ev_ts"]).dt.total_seconds().to_numpy() / 3600.0
    idx = m["__i"].to_numpy()
    out_age = np.full(len(day), np.nan)
    out_pc = np.full(len(day), np.nan)
    out_oc = np.full(len(day), np.nan)
    out_age[idx] = age
    out_pc[idx] = m["ev_pc"].to_numpy(dtype="float64")
    out_oc[idx] = m["ev_oc"].to_numpy(dtype="float64")
    return out_age, out_pc, out_oc


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


def build() -> dict:
    day = collect_dayend()
    ev = collect_events()
    vol = _hourly_feature(FEAT, "close", "vol")
    oi = _hourly_feature(OID, "oi", "oi")
    fund = collect_funding()
    mem = pd.read_parquet(MEM)

    day = day.merge(vol[["symbol", "ts_end", "v24"]], on=["symbol", "ts_end"], how="left")
    day = day.merge(oi[["symbol", "ts_end", "oi24"]], on=["symbol", "ts_end"], how="left")
    day = _last_rate(day, fund)

    for rg in REGIMES:
        a, p, o = _event_fields(day, ev[ev.regime == rg])
        day["age_" + rg] = a
        day["pc_" + rg] = p
        day["oc_" + rg] = o

    # volatility percentile against the contract's own trailing 90 days (daily grid)
    day = day.sort_values(["symbol", "ts_end"])
    day["vol_pct"] = (day.groupby("symbol")["v24"]
                         .transform(lambda s: s.rolling(90, min_periods=60).rank(pct=True)))

    # funding state and its position on the 0-1 axis
    st = np.full(len(day), -1, dtype="int8")
    for key, val in (("funding_negative", 0), ("funding_neutral", 1),
                     ("funding_high", 2), ("funding_extreme", 3)):
        st = np.where(day[key].to_numpy(dtype=bool), val, st)
    day["funding"] = st
    day["fund_pct"] = [funding_position(r, a, b, c, int(s))
                       for r, a, b, c, s in zip(day["funding_rate"], day["funding_p25"],
                                                day["funding_p75"], day["funding_p90"],
                                                day["funding"])]

    # membership of the month that the bar belongs to
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
        block = []
        for r in g.itertuples(index=False):
            age = {rg: getattr(r, "age_" + rg) for rg in REGIMES}
            ok = [rg for rg in REGIMES if np.isfinite(age[rg]) and age[rg] <= 24]
            last = min(ok, key=lambda k: age[k]) if ok else None

            def fresh(rg, key):
                a = age[rg]
                if not np.isfinite(a) or a > 24:
                    return None
                v = float(getattr(r, key + "_" + rg))
                return None if not np.isfinite(v) else v

            def f(v, scale=1.0, nd=1):
                """Round for JSON; anything non-finite becomes null (JSON has no NaN)."""
                if v is None:
                    return None
                v = float(v) * scale
                return round(v, nd) if np.isfinite(v) else None

            block.append([
                int(r.rank), sidx[r.symbol],
                REGIMES.index(last) if last else -1,
                f(age[last], 1, 1) if last else None,
                f(getattr(r, "pc_" + last), 1e4, 1) if last else None,
                f(getattr(r, "oc_" + last), 100, 2) if last else None,
                int(r.funding),
                f(r.vol_pct, 1, 3),
                f(r.oi24, 1, 4),
                f(age["R1"], 1, 1) if fresh("R1", "age") is not None else None,
                f(age["R3"], 1, 1) if fresh("R3", "age") is not None else None,
                f(age["R4"], 1, 1) if fresh("R4", "age") is not None else None,
                f(r.fund_pct, 1, 3),
                f(r.pc_R1, 1e4, 1) if fresh("R1", "pc") is not None else None,
                f(r.oc_R1, 100, 2) if fresh("R1", "oc") is not None else None,
                f(r.pc_R3, 1e4, 1) if fresh("R3", "pc") is not None else None,
                f(r.oc_R3, 100, 2) if fresh("R3", "oc") is not None else None,
                f(r.pc_R4, 1e4, 1) if fresh("R4", "pc") is not None else None,
                f(r.oc_R4, 100, 2) if fresh("R4", "oc") is not None else None,
            ])
        rows.append(block)

    return {"symbols": syms, "days": days, "mkt": mkt, "rows": rows}


if __name__ == "__main__":
    import json
    import time
    t = time.time()
    payload = build()
    raw = json.dumps(payload, separators=(",", ":"))
    print("days: %d | symbols: %d | json: %.1f MB | %.0fs"
          % (len(payload["days"]), len(payload["symbols"]), len(raw) / 1e6, time.time() - t))