"""D5 -- build the payload the interactive board embeds in one HTML.

Time model: every hour for the trailing 180 days, one snapshot per day before that.
A snapshot carries the 50-contract block; the day's event list is stored once and is
the single source of truth for every event fact.
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
HOURS_WINDOW_DAYS = 180


def _files(root: Path) -> list[Path]:
    return sorted(root.glob("year=*/chunk=*.parquet"))


def collect_funding() -> pd.DataFrame:
    return pd.concat([pd.read_parquet(p, columns=["symbol", "ts_funding", "funding_rate"])
                      for p in _files(FUND)], ignore_index=True)


def _hourly_stats(root: Path, col: str, kind: str, want: pd.DataFrame) -> pd.DataFrame:
    """Trailing stats on the hourly grid, kept only for the bars we show.

    The rolling windows span months, so the series must be concatenated BEFORE the
    rolling operations - doing it per monthly chunk makes every window too short.
    """
    parts = [pd.read_parquet(f, columns=["symbol", "ts_end", col]) for f in _files(root)]
    d = pd.concat(parts, ignore_index=True)
    del parts
    d = d.sort_values(["symbol", "ts_end"], kind="mergesort")
    if kind == "vol":
        d["r"] = np.log(d.groupby("symbol")[col].pct_change(fill_method=None).add(1.0))
        d["v24"] = d.groupby("symbol")["r"].transform(
            lambda s: s.rolling(24, min_periods=18).std())
        d["med"] = d.groupby("symbol")["v24"].transform(
            lambda s: s.rolling(2160, min_periods=1000).median())
        d["x"] = d.groupby("symbol")["v24"].transform(
            lambda s: s.rolling(2160, min_periods=1000).rank(pct=True))
        d["v24bp"] = d["v24"] * 1e4
        d["ratio"] = d["v24"] / d["med"]
        return want.merge(d[["symbol", "ts_end", "v24bp", "ratio", "x"]],
                          on=["symbol", "ts_end"], how="left")
    d["x"] = d.groupby("symbol")[col].pct_change(24, fill_method=None)
    return want.merge(d[["symbol", "ts_end", "x"]], on=["symbol", "ts_end"], how="left")


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
    if v is None:
        return None
    v = float(v) * scale
    return round(v, nd) if np.isfinite(v) else None


def build() -> dict:
    last = pd.read_parquet(_files(LAB)[-1], columns=["ts_end"]).ts_end.max()
    cutoff = last - pd.Timedelta(days=HOURS_WINDOW_DAYS)

    cols = ["symbol", "ts_end", "regime", "excl_reason", "price_change", "oi_change",
            "funding_negative", "funding_neutral", "funding_high", "funding_extreme",
            "funding_p25", "funding_p75", "funding_p90", "mkt_vol_state"]
    parts = []
    for p in _files(LAB):
        d = pd.read_parquet(p, columns=cols)
        parts.append(d[(d["ts_end"].dt.hour == 0) | (d["ts_end"] > cutoff)])
    bars = pd.concat(parts, ignore_index=True)
    del parts

    want = bars[["symbol", "ts_end"]].drop_duplicates()
    vol = _hourly_stats(FEAT, "close", "vol", want).rename(columns={"x": "vol_pct"})
    bars = bars.merge(vol, on=["symbol", "ts_end"], how="left")
    del vol
    oi = _hourly_stats(OID, "oi", "oi", want).rename(columns={"x": "oi24"})
    bars = bars.merge(oi, on=["symbol", "ts_end"], how="left")
    del oi

    fund = collect_funding().sort_values("ts_funding")
    bars = bars.sort_values("ts_end")
    bars = pd.merge_asof(bars, fund, left_on="ts_end", right_on="ts_funding",
                         by="symbol", direction="backward")

    st = np.full(len(bars), -1, dtype="int8")
    for key, val in (("funding_negative", 0), ("funding_neutral", 1),
                     ("funding_high", 2), ("funding_extreme", 3)):
        st = np.where(bars[key].to_numpy(dtype=bool), val, st)
    bars["funding"] = st
    bars["fund_pct"] = [funding_position(r, a, b, c, int(s))
                        for r, a, b, c, s in zip(bars["funding_rate"], bars["funding_p25"],
                                                 bars["funding_p75"], bars["funding_p90"],
                                                 bars["funding"])]

    reg = bars["regime"].to_numpy()
    okr = bars["excl_reason"].to_numpy() == "ok"
    bar_state = np.where(okr, -1, -2).astype("int8")
    for i, rg in enumerate(REGIMES):
        bar_state = np.where(reg == rg, i, bar_state)
    bars["bar_state"] = bar_state

    bars["day"] = (bars["ts_end"] - pd.Timedelta(hours=1)).dt.strftime("%Y-%m-%d")
    bars["hour"] = (bars["ts_end"] - pd.Timedelta(hours=1)).dt.hour.astype("int8")
    bars["month"] = bars["day"].str[:7]

    mem = pd.read_parquet(MEM)
    bars = bars.merge(mem[["symbol", "month", "rank"]], on=["symbol", "month"], how="inner")
    bars = bars.sort_values(["ts_end", "rank"])

    syms = sorted(bars["symbol"].unique())
    sidx = {s: i for i, s in enumerate(syms)}

    snap, kind, mkt, rows = [], [], [], []
    for (ts,), g in bars.groupby(["ts_end"], sort=True):
        snap.append("%sT%02d" % (g["day"].iloc[0], int(g["hour"].iloc[0])))
        kind.append(0 if int(g["hour"].iloc[0]) == 23 and ts <= cutoff else 1)
        mkt.append(str(g["mkt_vol_state"].mode().iloc[0]) if len(g) else "unknown")
        rows.append([[int(r.rank), sidx[r.symbol], int(r.funding),
                      _num(r.vol_pct, 1, 2), _num(r.oi24, 1, 2), _num(r.fund_pct, 1, 2),
                      int(r.bar_state), _num(r.price_change, 1e4, 0),
                      _num(r.oi_change, 100, 1), _num(r.v24bp, 1, 1), _num(r.ratio, 1, 2)]
                     for r in g.itertuples(index=False)])

    # ---- per-day event list (unchanged: the drill-down and 24h windows) ----
    ev_parts = []
    for p in _files(LAB):
        d = pd.read_parquet(p, columns=["symbol", "ts_end", "regime", "price_change", "oi_change"])
        ev_parts.append(d[d.regime.isin(REGIMES)])
    ev = pd.concat(ev_parts, ignore_index=True)
    del ev_parts

    # label an event by the bar it belongs to: day/hour of the bar's START, so the
    # convention matches the snapshots exactly (a snapshot at T h = the bar [h, h+1))
    e = ev.copy()
    start = e["ts_end"] - pd.Timedelta(hours=1)
    e["day"] = start.dt.floor("D")
    e["hour"] = start.dt.hour.astype("int8")
    e["day_s"] = e["day"].dt.strftime("%Y-%m-%d")
    days = sorted(bars["day"].unique())
    valid = set(zip(bars["symbol"], bars["day"]))
    e = e[[(s, d) in valid for s, d in zip(e["symbol"], e["day_s"])]]

    syms_all = syms
    sidx_all = sidx
    e = e[e["symbol"].isin(sidx_all)]
    e["ri"] = e["regime"].map({r: i for i, r in enumerate(REGIMES)}).astype("int8")
    e["si"] = e["symbol"].map(sidx_all).astype("int32")

    ev_list = {d: [] for d in days}
    for d, g in e.groupby("day_s", sort=False):
        block = [[int(si), int(h), int(ri), _num(pc, 1e4, 0), _num(oc, 100, 1)]
                 for si, h, ri, pc, oc in zip(g["si"], g["hour"], g["ri"],
                                              g["price_change"], g["oi_change"])]
        block.sort(key=lambda x: (x[0], x[1]))
        ev_list[d] = block

    return {"symbols": syms, "snap": snap, "kind": kind, "mkt": mkt, "rows": rows,
            "days": days, "ev": [ev_list[d] for d in days]}