"""Phase 5 -- costed event backtest engine.

Protocol is frozen by phase5_simple_strategy/GUIDANCE.md sec.4-5:

  entry   next bar OPEN after the event bar (event time = bar close)
  exit    close of the bar ending at entry_time + h
  gaps    <=2 missing bars -> next available bar; >2 -> skip (counted)
  delist  last tradable bar close
  overlap one position per contract, first one wins, no adds
  sizing  2% of equity per signal (UNIT * s * equity at entry), so the
           equity path compounds; gross <= 10 units (= 1x)
  costs   taker 0.05%/side + 5bp slippage/side, both legs
  funding actual settlement timestamps inside (entry, exit], whole amount,
          long RECEIVES when the rate is negative; missing points = 0 carry

Time convention.  "hour" = hours since 2021-12-01T00:00Z and denotes a POINT IN
TIME.  A kline whose start is h covers [h, h+1): its open is the price at h, its
close the price at h+1.  Phase 3/4 tables store ts_end, so their hour is already
a point in time -- event hour h means the decision instant h, and the entry bar
is the one starting at h.

Lookup key.  Rows are indexed by code * H + hour (H = 1 << 17, > max hour).  The
encoding must be symbol-major: with hour * n_sym + code a range query
[code + lo*n_sym, code + hi*n_sym] would also pull in every other contract that
settled inside the window, which silently inflated funding 30-fold.
"""
from __future__ import annotations

import glob
import heapq
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

# Time origin of the panel/forward grid (same as phase4_funding/build.py).
# Kept here so the engine has no dependency on any rule definition.
T0 = pd.Timestamp("2021-12-01", tz="UTC")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KLINES = DATA / "01_layer2/klines_1h"
FUNDING = DATA / "01_layer2/funding"
BASE = DATA / "07_funding/base"
SYMBOLS = DATA / "06_event_study/panel/freq=1h/symbols.parquet"

H = 1 << 17
EQUITY0 = 100_000.0
UNIT = 0.10                 # 10% of equity per size unit
MAX_UNITS = 10.0            # gross size units <= 10  (1x leverage, sec.5)

# Capacity policy (changed from the frozen 10% x 10 slots -- see REPRODUCE.md).
# Observed instantaneous concurrency peaks at 46-50 across the six arms, so ten
# slots bound on 14-40% of events and dropped exactly the crowded, high-edge
# hours.  One unit is split into 50 slices instead: 2% of equity per signal,
# still capped at 10 units (100%) gross.  Setting SIZE_PER_SIGNAL back to 1.0
# reproduces the original frozen policy with no other change.
SIZE_PER_SIGNAL = 0.2
FEE, SLIP = 0.0005, 0.0005  # per side
COST_PER_SIDE = FEE + SLIP
COST_BP = COST_PER_SIDE * 2 * 1e4        # 20.0 bp round trip


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------
def load_symbols() -> tuple[dict, dict, int]:
    s = pd.read_parquet(SYMBOLS)
    code2sym = dict(zip(s["code"].astype("int64"), s["symbol"]))
    return code2sym, {v: k for k, v in code2sym.items()}, len(code2sym)


def _files(root: Path) -> list[str]:
    return sorted(glob.glob(str(root / "year=*" / "*.parquet")))


@dataclass
class Market:
    keys: np.ndarray        # code * H + hour, sorted; hour = bar START
    open_: np.ndarray
    close: np.ndarray
    code: np.ndarray        # per row, for recovery

    def at(self, hour, code):
        """Index of the bar starting exactly at (hour, code), else -1."""
        k = np.asarray(code, dtype="int64") * H + np.asarray(hour, dtype="int64")
        pos = np.minimum(np.searchsorted(self.keys, k), len(self.keys) - 1)
        return np.where(self.keys[pos] == k, pos, -1)

    def prev(self, hour, code):
        """Index of the last bar at or before (hour, code) of the same symbol."""
        k = np.asarray(code, dtype="int64") * H + np.asarray(hour, dtype="int64")
        pos = np.searchsorted(self.keys, k, side="right") - 1
        return np.where(pos >= 0, pos, -1)

    def hour_of(self, idx):
        return self.keys[np.maximum(idx, 0)] % H


def load_market(sym2code: dict) -> Market:
    parts = []
    for p in _files(KLINES):
        d = pd.read_parquet(p, columns=["symbol", "ts", "open", "close"])
        d["code"] = d["symbol"].map(sym2code).astype("int64")
        d["hour"] = ((d["ts"] - T0).dt.total_seconds() // 3600).astype("int64")
        parts.append(d[["code", "hour", "open", "close"]])
    d = pd.concat(parts, ignore_index=True)
    d["key"] = d["code"] * H + d["hour"]
    d = d.sort_values("key", kind="stable")
    return Market(d["key"].to_numpy("int64"), d["open"].to_numpy("float64"),
                  d["close"].to_numpy("float64"), d["code"].to_numpy("int64"))


@dataclass
class Funding:
    keys: np.ndarray        # code * H + settlement hour, sorted
    rate: np.ndarray
    cum: np.ndarray         # cumulative sum -> O(1) window sums
    interval: np.ndarray

    def window(self, lo_hour, hi_hour, code):
        """Sum of rates with lo_hour < t <= hi_hour, and how many were found."""
        c = np.asarray(code, dtype="int64")
        i0 = np.searchsorted(self.keys, c * H + np.asarray(lo_hour), side="right")
        i1 = np.searchsorted(self.keys, c * H + np.asarray(hi_hour), side="right")
        return self.cum[i1] - self.cum[i0], i1 - i0

    def interval_at(self, hour, code, default=8.0):
        """Funding interval in force at that hour (last record at or before it)."""
        c = np.asarray(code, dtype="int64")
        pos = np.searchsorted(self.keys, c * H + np.asarray(hour), side="right") - 1
        ok = pos >= 0
        return np.where(ok, self.interval[np.maximum(pos, 0)], default)


def load_funding(sym2code: dict) -> Funding:
    parts = []
    for p in _files(FUNDING):
        d = pd.read_parquet(p, columns=["symbol", "ts_funding", "funding_rate",
                                        "funding_interval_hours"])
        d["code"] = d["symbol"].map(sym2code).astype("int64")
        d["hour"] = ((d["ts_funding"] - T0).dt.total_seconds() // 3600).astype("int64")
        parts.append(d[["code", "hour", "funding_rate", "funding_interval_hours"]])
    d = pd.concat(parts, ignore_index=True)
    d["key"] = d["code"] * H + d["hour"]
    d = d.sort_values("key", kind="stable").drop_duplicates("key", keep="first")
    rate = d["funding_rate"].to_numpy("float64")
    return Funding(d["key"].to_numpy("int64"), rate,
                   np.concatenate([[0.0], np.cumsum(rate)]),
                   d["funding_interval_hours"].to_numpy("float64"))


BASE_COLS = ["symbol", "sym", "hour", "month", "cell", "state", "dir",
             "mkt_vol_lab", "fwd", "y_raw"]


def load_base(h: int = 1) -> pd.DataFrame:
    return pd.read_parquet(BASE / f"p4_base_h={h}.parquet", columns=BASE_COLS)


# --------------------------------------------------------------------------
# engine
# --------------------------------------------------------------------------
def run(events: pd.DataFrame, hold: int, mkt: Market, fund: Funding,
        size: np.ndarray | None = None, max_units: float = MAX_UNITS,
        seed: int = 20240501, direction: int = 1) -> tuple[pd.DataFrame, dict]:
    """Execute one rule x horizon.  events needs columns code and hour.

    direction +1 is long, -1 is short.  The gate is two-sided, so an arm can in
    principle be short; sizing, cost and the sequential pass are symmetric, and
    price PnL, funding PnL and the marked return all flip sign with direction.
    """
    n = len(events)
    code = events["code"].to_numpy("int64")
    hour = events["hour"].to_numpy("int64")
    s = np.full(n, SIZE_PER_SIGNAL) if size is None else np.asarray(size, dtype="float64")

    # ---- entry: bar starting at the event time, else next available <=2h ----
    gap = np.full(n, -1, dtype="int64")
    entry_idx = np.full(n, -1, dtype="int64")
    for g in (0, 1, 2):
        todo = gap < 0
        if not todo.any():
            break
        idx = mkt.at(hour + g, code)
        hit = todo & (idx >= 0)
        gap[hit] = g
        entry_idx[hit] = idx[hit]
    skip = dict(entry_gap=int((gap < 0).sum()), overlap=0, capacity=0)
    entry_time = hour + np.maximum(gap, 0)
    entry_px = np.where(entry_idx >= 0, mkt.open_[np.maximum(entry_idx, 0)], np.nan)

    # ---- exit: close of the bar ending at entry_time + hold ----
    tgt = entry_time + hold
    exit_idx = mkt.at(tgt - 1, code)
    exit_time = tgt.copy()
    exit_kind = np.where(exit_idx >= 0, 0, -1)      # 0 = scheduled
    for g in (1, 2):                                 # <=2h late, entry rule reused
        todo = exit_kind < 0
        if not todo.any():
            break
        idx = mkt.at(tgt - 1 + g, code)
        hit = todo & (idx >= 0)
        exit_kind[hit] = 1
        exit_idx[hit] = idx[hit]
        exit_time[hit] = tgt[hit] + g
    todo = exit_kind < 0
    if todo.any():                                   # 2 = early / delisting
        idx = mkt.prev(tgt[todo] - 1, code[todo])
        exit_idx[todo] = idx
        exit_time[todo] = np.where(idx >= 0, mkt.hour_of(idx) + 1, tgt[todo])
        exit_kind[todo] = 2
    bad = exit_idx < 0
    exit_px = np.where(bad, np.nan, mkt.close[np.maximum(exit_idx, 0)])

    # ---- funding inside (entry, exit] ----
    r_sum, r_n = fund.window(entry_time, exit_time, code)
    iv = fund.interval_at(entry_time, code)
    iv = np.where(np.isfinite(iv) & (iv > 0), iv, 8.0)
    expected = np.floor(exit_time / iv) - np.floor(entry_time / iv)
    missing = np.maximum(0.0, expected - r_n)

    d = float(1 if direction >= 0 else -1)
    # PnL per unit of notional: scale-free, so it can be applied to any size.
    net_ret = d * (exit_px / entry_px - 1.0) - d * r_sum - 2.0 * COST_PER_SIDE

    # ---- sequential pass: one position per contract, gross budget, equity ----
    # Tie-break among simultaneous candidates is RANDOM (fixed seed), not by
    # contract code: a code-ordered queue would systematically prefer the
    # earliest-listed contracts, which is a listing-order bias, not an economic
    # one.  Events cluster in market-wide hours, so this choice matters.
    #
    # Sizing compounds: the notional of a trade is UNIT * s * E, where E is the
    # equity already realised when the trade opens (initial capital plus the PnL
    # of positions closed before that hour).  Unrealised PnL is not marked into
    # E, which is the conservative reading of "equity at entry".
    rng = np.random.default_rng(seed)
    order = np.lexsort((rng.random(n), entry_time))
    keep = np.zeros(n, dtype=bool)
    notional = np.zeros(n)
    units = 0.0
    realized = 0.0
    open_until: dict[int, int] = {}
    heap: list[tuple[int, float]] = []
    closed: list[tuple[int, float]] = []
    for i in order:
        if (gap[i] < 0) or bad[i]:
            continue
        t = int(entry_time[i])
        while closed and closed[0][0] <= t:
            realized += heapq.heappop(closed)[1]
        while heap and heap[0][0] <= t:
            units -= heapq.heappop(heap)[1]
        c = int(code[i])
        if open_until.get(c, -1) > t:
            skip["overlap"] += 1
            continue
        if units + s[i] > max_units + 1e-9:
            skip["capacity"] += 1
            continue
        notional[i] = UNIT * s[i] * (EQUITY0 + realized)
        keep[i] = True
        units += s[i]
        open_until[c] = int(exit_time[i])
        heapq.heappush(heap, (int(exit_time[i]), s[i]))
        heapq.heappush(closed, (int(exit_time[i]), notional[i] * net_ret[i]))

    qty = np.where(keep, notional / np.where(np.isfinite(entry_px), entry_px, 1.0), 0.0)
    trades = pd.DataFrame(dict(
        i=np.arange(n), code=code, hour=hour, entry_time=entry_time,
        exit_time=exit_time, entry_px=entry_px, exit_px=exit_px,
        gap=gap, exit_kind=exit_kind, size=s, notional=notional, qty=qty,
        direction=np.full(n, d),
        price_pnl=d * qty * (exit_px - entry_px),
        fund_pnl=-d * r_sum * notional,
        cost=notional * COST_PER_SIDE * 2.0,
        n_settle=r_n, n_settle_missing=missing, kept=keep,
    ))
    trades["price_ret"] = d * (trades.exit_px / trades.entry_px - 1.0)
    trades["net_pnl"] = trades.price_pnl + trades.fund_pnl - trades.cost
    skip["n_events"] = n
    skip["n_trades"] = int(keep.sum())
    return trades, skip


# --------------------------------------------------------------------------
# daily mark-to-market
# --------------------------------------------------------------------------
def daily_frame(trades: pd.DataFrame, mkt: Market, day0: int, day1: int) -> pd.DataFrame:
    """Daily PnL (dollar) split into price / funding / cost.

    Price PnL is marked to the close of every UTC midnight inside the holding
    window, so no day ever books a price the strategy could not have seen.
    Funding is booked on the exit day: the hold is <= 24h, so at most one
    midnight of timing drift and the total is exact.  Costs are split evenly
    between the entry and the exit day.
    """
    t = trades[trades.kept]
    nd = day1 - day0 + 1
    price = np.zeros(nd)
    fund = np.zeros(nd)
    cost = np.zeros(nd)
    if len(t):
        et = t.entry_time.to_numpy("int64")
        xt = t.exit_time.to_numpy("int64")
        px = t.entry_px.to_numpy("float64")
        xp = t.exit_px.to_numpy("float64")
        q = (t.qty * t.direction).to_numpy("float64")
        cl = t.code.to_numpy("int64")
        # Walk every UTC midnight strictly inside (entry, exit): book each
        # segment on the day it ends.  The final leg to the exit price is booked
        # separately, otherwise a trade that never crosses midnight (most of the
        # 1h arm) would contribute no price PnL at all.
        prev_px = px.copy()
        for k in range(1, 40):
            b = (et // 24 + k) * 24
            live = b < xt
            if not live.any():
                break
            bi = mkt.prev(b[live] - 1, cl[live])
            p = np.where(bi >= 0, mkt.close[np.maximum(bi, 0)], xp[live])
            np.add.at(price, np.clip(b[live] // 24 - day0, 0, nd - 1),
                      (p - prev_px[live]) * q[live])
            prev_px[live] = p
        np.add.at(price, np.clip(xt // 24 - day0, 0, nd - 1), (xp - prev_px) * q)
        np.add.at(fund, np.clip(xt // 24 - day0, 0, nd - 1), t.fund_pnl.to_numpy("float64"))
        np.add.at(cost, np.clip(et // 24 - day0, 0, nd - 1), t.cost.to_numpy("float64") / 2)
        np.add.at(cost, np.clip(xt // 24 - day0, 0, nd - 1), t.cost.to_numpy("float64") / 2)
    out = pd.DataFrame(dict(day=np.arange(day0, day1 + 1), price=price,
                            funding=fund, cost=cost))
    out["net"] = out.price + out.funding - out.cost
    out["date"] = T0 + pd.to_timedelta(out.day, unit="D")
    return out


def equity_path(daily: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Compounded equity path and the daily returns that produce it.

    Sizing is a fraction of the equity realised at entry, so the path grows
    multiplicatively: E_t = E_{t-1} + net_t, with r_t = net_t / E_{t-1}.
    """
    net = daily.net.to_numpy("float64")
    eq = np.empty(len(net) + 1)
    eq[0] = EQUITY0
    for i, x in enumerate(net):
        eq[i + 1] = eq[i] + x
    r = net / eq[:-1] if len(net) else net
    return eq[1:], r


def metrics(daily: pd.DataFrame, trades: pd.DataFrame, years: float,
            ann: int = 365) -> dict:
    """Headline numbers for one arm x one window.

    Sharpe is annualised on 365 days because the venue trades every calendar
    day (see REPRODUCE.md).  Sizing compounds, so the equity path is the
    product of the daily returns, annual return is its compound growth rate,
    and turnover and the bp aggregates are quoted against average equity.
    """
    eq, r = equity_path(daily)
    mdd = float(np.min(eq / np.maximum.accumulate(eq) - 1.0)) if len(eq) else 0.0
    sd = float(np.std(r, ddof=1)) if len(r) > 1 else np.nan
    mu = float(np.mean(r)) if len(r) else np.nan
    t = trades[trades.kept]
    avg_eq = float(np.mean(eq)) if len(eq) else EQUITY0
    total = float(eq[-1] / EQUITY0 - 1.0) if len(eq) else 0.0
    cagr = ((1.0 + total) ** (1.0 / years) - 1.0
            if years > 0 and 1.0 + total > 0 else np.nan)
    return dict(
        n_days=int(len(r)), n_trades=int(len(t)),
        total_ret=total,
        ann_ret=cagr, ann_vol=sd * np.sqrt(ann),
        sharpe=mu / sd * np.sqrt(ann) if sd and sd > 0 else np.nan,
        t_stat=mu / (sd / np.sqrt(len(r))) if sd and sd > 0 else np.nan,
        mdd=mdd,
        turnover=float(t.notional.sum()) / (avg_eq * years) if years > 0 else 0.0,
        price_bp=float(t.price_pnl.sum()) / avg_eq * 1e4,
        fund_bp=float(t.fund_pnl.sum()) / avg_eq * 1e4,
        cost_bp=float(t.cost.sum()) / avg_eq * 1e4,
        net_bp=float(t.net_pnl.sum()) / avg_eq * 1e4,
        n_settle=int(t.n_settle.sum()),
        n_settle_missing=int(t.n_settle_missing.sum()),
    )