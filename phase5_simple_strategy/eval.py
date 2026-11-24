"""Phase 5 -- evaluation (GUIDANCE.md sec.8-9).

Splits, the six baselines, the metrics and the breakdown tables.  Everything is
in-sample: the design was written after the full sample had been looked at
(sec.8), so no number here is a blind out-of-sample claim.
"""
from __future__ import annotations

import calendar

import numpy as np
import pandas as pd

from . import backtest as bt
from . import rules as R

TBL = bt.DATA / "08_strategy" / "tables"
MEMBERSHIP = bt.DATA / "03_reference/universe_membership.parquet"

WINDOWS: dict[str, dict] = {
    "main": dict(test=("2022-03", "2026-08")),
}
MAIN = WINDOWS["main"]
ANN = 365


def month_day_bounds(lo: str, hi: str) -> tuple[int, int]:
    y, m = (int(x) for x in lo.split("-"))
    d0 = (pd.Timestamp(f"{y:04d}-{m:02d}-01", tz="UTC") - bt.T0).days
    y, m = (int(x) for x in hi.split("-"))
    d1 = (pd.Timestamp(f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}", tz="UTC")
          - bt.T0).days
    return d0, d1


def _slice(df: pd.DataFrame, lo: str, hi: str) -> pd.DataFrame:
    return df[(df["month"] >= lo) & (df["month"] <= hi)]


def sharpe_ci(r: np.ndarray, reps: int = 2000, block: int = 5,
              seed: int = 20240501) -> tuple[float, float]:
    """Moving-block bootstrap CI for the annualised Sharpe."""
    r = np.asarray(r, dtype="float64")
    n = len(r)
    if n < block + 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(reps, int(np.ceil(n / block))))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)[:, :n]
    s = r[idx]
    mu = s.mean(axis=1)
    sd = s.std(axis=1, ddof=1)
    sh = np.where(sd > 0, mu / sd * np.sqrt(ANN), np.nan)
    lo, hi = np.nanpercentile(sh, [2.5, 97.5])
    return float(lo), float(hi)


def daily_metrics(daily: pd.DataFrame, years: float) -> dict:
    eq, r = bt.equity_path(daily)
    sd = float(np.std(r, ddof=1)) if len(r) > 1 else np.nan
    mu = float(np.mean(r)) if len(r) else np.nan
    total = float(eq[-1] / bt.EQUITY0 - 1.0) if len(eq) else 0.0
    cagr = ((1.0 + total) ** (1.0 / years) - 1.0
            if years > 0 and 1.0 + total > 0 else np.nan)
    return dict(sharpe=mu / sd * np.sqrt(ANN) if sd and sd > 0 else np.nan,
                t_stat=mu / (sd / np.sqrt(len(r))) if sd and sd > 0 else np.nan,
                ann_ret=cagr, ann_vol=sd * np.sqrt(ANN),
                mdd=float(np.min(eq / np.maximum.accumulate(eq) - 1.0)) if len(eq) else 0.0,
                turnover=0.0, total_ret=total)


def stats(tr: pd.DataFrame, sk: dict, daily: pd.DataFrame, dgross: pd.DataFrame,
          d0: int, d1: int, hold: int, label: str) -> dict:
    k = tr[tr.kept]
    years = (d1 - d0 + 1) / 365.0
    m = bt.metrics(daily, tr, years)
    mg = bt.metrics(dgross, tr.assign(cost=0.0,
                                      net_pnl=tr.price_pnl + tr.fund_pnl), years)
    eq_path, r_path = bt.equity_path(daily)
    lo, hi = sharpe_ci(r_path)
    notional = float(k.notional.sum()) if len(k) else np.nan
    return dict(
        arm=label, n_events=sk["n_events"], n_trades=sk["n_trades"],
        skip_gap=sk["entry_gap"], skip_overlap=sk["overlap"], skip_cap=sk["capacity"],
        price_bp=float(k.price_pnl.sum()) / notional * 1e4 if len(k) else np.nan,
        fund_bp=float(k.fund_pnl.sum()) / notional * 1e4 if len(k) else np.nan,
        cost_bp=bt.COST_BP,
        net_bp=float(k.net_pnl.sum()) / notional * 1e4 if len(k) else np.nan,
        cost_star_bp=(float(k.price_pnl.sum()) + float(k.fund_pnl.sum()))
        / notional * 1e4 if len(k) else np.nan,
        net_bp_cap=float(k.net_pnl.sum()) / float(np.mean(eq_path)) * 1e4,
        win_rate=float((k.net_pnl > 0).mean()) if len(k) else np.nan,
        hold_h=hold,
        gross_sharpe=mg["sharpe"], net_sharpe=m["sharpe"],
        ci_lo=lo, ci_hi=hi, t_stat=m["t_stat"], ann_ret=m["ann_ret"],
        ann_vol=m["ann_vol"], mdd=m["mdd"], turnover=m["turnover"],
        exposure=notional * hold / (float(np.mean(eq_path)) * (d1 - d0 + 1) * 24) if len(k) else np.nan,
        n_settle=m["n_settle"], n_settle_missing=m["n_settle_missing"],
        total_ret=m["total_ret"],)


def run_arm(ev: pd.DataFrame, hold: int, mkt, fund, d0: int, d1: int, size=None,
            direction: int = 1):
    tr, sk = bt.run(ev, hold, mkt, fund, size=size, direction=direction)
    daily = bt.daily_frame(tr, mkt, d0, d1)
    trg = tr.assign(cost=0.0, net_pnl=tr.price_pnl + tr.fund_pnl)
    dgross = bt.daily_frame(trg, mkt, d0, d1)
    return tr, sk, daily, dgross


# --------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------
def baseline_events(base: pd.DataFrame, kind: str, direction: int) -> pd.DataFrame:
    b = base[base["state"].between(0, 3)]
    if kind == "price_alone":
        m = b["dir"] == direction
    elif kind == "price_oi":
        m = b["cell"].isin([1, 2, 3, 4]) & (b["dir"] == direction)
    elif kind == "oi_alone":
        m = b["cell"].isin([1, 2, 3, 4])
    elif kind == "funding_alone":
        m = b["state"] == 0
    else:
        raise ValueError(kind)
    out = b.loc[m].copy()
    out["code"] = out["symbol"].astype("int64")
    return out.sort_values(["hour", "code"]).reset_index(drop=True)


def random_events(ev: pd.DataFrame, members: pd.DataFrame, rng) -> pd.DataFrame:
    cnt = ev.groupby("month").size()
    bounds = ev.groupby("month")["hour"].agg(["min", "max"])
    out = []
    for mth, k in cnt.items():
        syms = members.loc[members["month"] == mth, "code"].to_numpy()
        if len(syms) == 0:
            continue
        h0, h1 = int(bounds.loc[mth, "min"]), int(bounds.loc[mth, "max"])
        out.append(pd.DataFrame(dict(
            code=rng.choice(syms, size=int(k), replace=True),
            hour=rng.integers(h0, h1 + 1, size=int(k)),
            lrv=np.nan, month=mth)))
    return pd.concat(out, ignore_index=True) if out else ev.iloc[0:0]


def buy_and_hold(mkt, members: pd.DataFrame, d0: int, d1: int,
                 cost_side: float = bt.COST_PER_SIDE) -> pd.DataFrame:
    day = (mkt.keys % bt.H) // 24
    s = pd.DataFrame(dict(code=mkt.code, day=day, close=mkt.close))
    s = s[(s["day"] >= d0 - 1) & (s["day"] <= d1)]
    px = s.groupby(["code", "day"])["close"].last().unstack(0).sort_index()
    ret = px.pct_change(fill_method=None)
    days = list(range(d0, d1 + 1))
    port = pd.Series(0.0, index=days)
    cost = pd.Series(0.0, index=days)
    prev_w: dict[int, float] = {}
    for mth, blk in members.groupby("month"):
        start = (pd.Timestamp(f"{mth}-01", tz="UTC") - bt.T0).days
        nb = (pd.Timestamp(f"{mth}-01", tz="UTC") + pd.offsets.MonthBegin(1) - bt.T0).days
        blk_days = [d for d in days if start <= d < nb]
        if not blk_days:
            continue
        codes = [int(c) for c in blk["code"].unique() if int(c) in px.columns]
        if not codes:
            continue
        w = {c: 1.0 / len(codes) for c in codes}
        turn = sum(abs(w.get(c, 0.0) - prev_w.get(c, 0.0)) for c in set(w) | set(prev_w))
        cost[blk_days[0]] = turn * cost_side * bt.EQUITY0
        for d in blk_days:
            r = 0.0
            for c, wc in w.items():
                x = ret.at[d, c] if c in ret.columns else np.nan
                if np.isfinite(x):
                    r += wc * x
            port[d] = r * bt.EQUITY0
        prev_w = dict(w)
    out = pd.DataFrame(dict(day=days, price=port.reindex(days).to_numpy(),
                            funding=0.0, cost=cost.reindex(days).to_numpy()))
    out["net"] = out.price - out.cost
    out["date"] = bt.T0 + pd.to_timedelta(out.day, unit="D")
    return out


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------
def main() -> int:
    TBL.mkdir(parents=True, exist_ok=True)
    code2sym, sym2code, n_sym = bt.load_symbols()
    mkt = bt.load_market(sym2code)
    fund = bt.load_funding(sym2code)
    bases = {h: bt.load_base(h) for h in (1, 8)}
    mem = pd.read_parquet(MEMBERSHIP)
    mem["code"] = mem["symbol"].map(sym2code).astype("int64")

    rows = []
    for wname, w in WINDOWS.items():
        d0, d1 = month_day_bounds(*w["test"])
        for arm in R.ARMS:
            hold = arm["hold"]
            ev = R.select(bases[hold], arm)
            tst = _slice(ev, *w["test"]).reset_index(drop=True)
            if len(tst) == 0:
                continue
            tr, sk, daily, dg = run_arm(tst, hold, mkt, fund, d0, d1)
            row = stats(tr, sk, daily, dg, d0, d1, hold, label=arm["name"])
            row.update(window=wname, variant="base", role=arm["role"],
                       target_vol=np.nan)
            rows.append(row)
    rules_df = pd.DataFrame(rows)
    rules_df.to_csv(TBL / "p5_rules.csv", index=False)


    # baselines on the main test window
    d0, d1 = month_day_bounds(*MAIN["test"])
    brows = []
    cache = {}
    rng = np.random.default_rng(20240501)
    for arm in R.ARMS:
        hold = arm["hold"]
        base = bases[hold]
        tst = _slice(base, *MAIN["test"])
        for kind in ("price_alone", "price_oi", "oi_alone", "funding_alone"):
            key = (kind, hold)
            if key not in cache:
                ev = baseline_events(tst, kind, -1)
                tr, sk, daily, dg = run_arm(ev, hold, mkt, fund, d0, d1)
                cache[key] = stats(tr, sk, daily, dg, d0, d1, hold, label=kind)
            row = dict(cache[key])
            row.update(arm=f"{arm['name']}:{kind}", window="main", variant="baseline")
            brows.append(row)
        ev = R.select(base, arm)
        rv = random_events(_slice(ev, *MAIN["test"]), mem, rng)
        tr, sk, daily, dg = run_arm(rv.sort_values(["hour", "code"]).reset_index(drop=True),
                                    hold, mkt, fund, d0, d1)
        row = stats(tr, sk, daily, dg, d0, d1, hold, label="random")
        row.update(arm=f"{arm['name']}:random", window="main", variant="baseline")
        brows.append(row)

    bh = buy_and_hold(mkt, mem, d0, d1)
    m = daily_metrics(bh, (d1 - d0 + 1) / 365.0)
    bh_gross = bh.assign(net=bh.price)
    mg = daily_metrics(bh_gross, (d1 - d0 + 1) / 365.0)
    lo, hi = sharpe_ci(bh.net.to_numpy("float64") / bt.EQUITY0)
    brows.append(dict(arm="buy_and_hold", window="main", variant="baseline",
                      n_events=np.nan, n_trades=np.nan, skip_gap=np.nan,
                      skip_overlap=np.nan, skip_cap=np.nan, price_bp=np.nan,
                      fund_bp=np.nan, cost_bp=np.nan, net_bp=np.nan,
                      cost_star_bp=np.nan,
                      net_bp_cap=float(bh.net.sum()) / bt.EQUITY0 * 1e4,
                      gross_sharpe=mg["sharpe"], net_sharpe=m["sharpe"],
                      ci_lo=lo, ci_hi=hi, t_stat=m["t_stat"], ann_ret=m["ann_ret"],
                      ann_vol=m["ann_vol"], mdd=m["mdd"], turnover=m["turnover"],
                      exposure=1.0, n_settle=0, n_settle_missing=0,
                      total_ret=m["total_ret"], role="benchmark", target_vol=np.nan))
    base_df = pd.DataFrame(brows)
    base_df.to_csv(TBL / "p5_baselines.csv", index=False)

    # table 3: by funding state / market-vol / contract, main test window
    reg_rows, ast_rows = [], []
    for arm in R.ARMS:
        hold = arm["hold"]
        ev = _slice(R.select(bases[hold], arm), *MAIN["test"]).reset_index(drop=True)
        tr, sk, _, _ = run_arm(ev, hold, mkt, fund, d0, d1)
        k = tr[tr.kept].copy()
        idx = k["i"].to_numpy()
        k["net_ret"] = k.net_pnl / k.notional
        for dim, col, fmt in (("cell", "cell", int), ("state", "state", int),
                              ("mkt_vol", "mkt_vol_lab", str)):
            k["_g"] = ev[col].to_numpy()[idx]
            for key, gg in k.groupby("_g"):
                reg_rows.append(dict(arm=arm["name"], dim=dim, key=fmt(key),
                                     n=len(gg), net_bp=float(gg["net_ret"].mean() * 1e4),
                                     price_bp=float(gg["price_pnl"].sum()
                                                    / gg["notional"].sum() * 1e4),
                                     fund_bp=float(gg["fund_pnl"].sum()
                                                   / gg["notional"].sum() * 1e4)))
        k["_g"] = ev["sym"].to_numpy()[idx]
        for sym, gg in k.groupby("_g"):
            ast_rows.append(dict(arm=arm["name"], sym=sym, n=len(gg),
                                 net_bp=float(gg["net_ret"].mean() * 1e4)))
        reg_rows.append(dict(arm=arm["name"], dim="all", key="all", n=len(k),
                             net_bp=float(k["net_ret"].mean() * 1e4),
                             price_bp=float(k["price_pnl"].sum()
                                            / k["notional"].sum() * 1e4),
                             fund_bp=float(k["fund_pnl"].sum()
                                           / k["notional"].sum() * 1e4)))
    pd.DataFrame(reg_rows).to_csv(TBL / "p5_by_regime.csv", index=False)
    pd.DataFrame(ast_rows).to_csv(TBL / "p5_by_asset.csv", index=False)

    # daily series for the figures (main window only) and by-year ledger
    drows = []
    for arm in R.ARMS:
        hold = arm["hold"]
        ev = _slice(R.select(bases[hold], arm), *MAIN["test"]).reset_index(drop=True)
        tr, sk, daily, dg = run_arm(ev, hold, mkt, fund, d0, d1)
        for _, r in daily.iterrows():
            drows.append(dict(arm=arm["name"], variant="base", date=r["date"],
                              price=r["price"], funding=r["funding"],
                              cost=r["cost"], net=r["net"]))
    pd.DataFrame(drows).to_csv(TBL / "p5_daily.csv", index=False)

    yrows = []
    for arm in R.ARMS:
        hold = arm["hold"]
        ev = R.select(bases[hold], arm)
        tr, sk, _, _ = run_arm(ev, hold, mkt, fund, 0, 1)
        k = tr[tr.kept].copy()
        k["yr"] = (bt.T0 + pd.to_timedelta(k["entry_time"], unit="h")).dt.year.to_numpy()
        for yr, gg in k.groupby("yr"):
            n = float(gg["notional"].sum())
            yrows.append(dict(arm=arm["name"], year=int(yr), n=len(gg),
                              price_bp=float(gg["price_pnl"].sum()) / n * 1e4,
                              fund_bp=float(gg["fund_pnl"].sum()) / n * 1e4,
                              net_bp=float(gg["net_pnl"].sum()) / n * 1e4,
                              cost_star_bp=(float(gg["price_pnl"].sum())
                                            + float(gg["fund_pnl"].sum())) / n * 1e4))
    pd.DataFrame(yrows).to_csv(TBL / "p5_year.csv", index=False)

    pd.set_option("display.width", 250)
    cols = ["window", "variant", "arm", "n_trades", "skip_overlap", "skip_cap",
            "price_bp", "fund_bp", "net_bp", "cost_star_bp", "gross_sharpe",
            "net_sharpe", "ci_lo", "ci_hi", "ann_ret", "ann_vol"]
    print(rules_df[cols].round(2).to_string(index=False))
    print("")
    print(base_df[["arm", "n_trades", "gross_sharpe", "net_sharpe", "ci_lo",
                   "ci_hi", "ann_ret"]].round(2).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())