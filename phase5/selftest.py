"""Phase 5 -- engine self-test.  python -m phase5.selftest

Independent recomputation of sampled trades straight from the raw parquet files
(pandas joins on real timestamps, not the array engine) plus the accounting
identities.  This is the "no hand steps / no future data" gate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import backtest as bt
from . import rules as R


def main() -> int:
    code2sym, sym2code, n_sym = bt.load_symbols()
    mkt = bt.load_market(sym2code)
    fund = bt.load_funding(sym2code)
    arm = R.ARM_BY_NAME["A1"]
    ev = R.select(bt.load_base(arm["hold"]), arm)
    tr, sk = bt.run(ev, arm["hold"], mkt, fund)
    k = tr[tr.kept].reset_index(drop=True)

    rng = np.random.default_rng(7)
    samp = k.iloc[rng.choice(len(k), 300, replace=False)].copy()
    syms = set(samp["code"].map(code2sym))
    years = sorted({str((bt.T0 + pd.Timedelta(hours=int(t))).year)
                    for t in list(samp.entry_time) + list(samp.exit_time)})
    print("sampled %d trades over years %s" % (len(samp), years))

    kparts, fparts = [], []
    for p in bt._files(bt.KLINES):
        if p.split("year=")[1][:4] in years:
            kparts.append(pd.read_parquet(p, columns=["symbol", "ts", "ts_end",
                                                      "open", "close"]))
    for p in bt._files(bt.FUNDING):
        if p.split("year=")[1][:4] in years:
            fparts.append(pd.read_parquet(p, columns=["symbol", "ts_funding",
                                                      "funding_rate"]))
    kl = pd.concat(kparts, ignore_index=True)
    fr = pd.concat(fparts, ignore_index=True)
    kl = kl[kl["symbol"].isin(syms)]
    fr = fr[fr["symbol"].isin(syms)]
    op = kl.set_index(["symbol", "ts"])["open"]
    cl = kl.set_index(["symbol", "ts_end"])["close"]
    fr = fr.sort_values(["symbol", "ts_funding"])
    fg = {s: (g.ts_funding.to_numpy("int64"), g.funding_rate.to_numpy())
          for s, g in fr.groupby("symbol", sort=False)}

    bad = []
    for _, row in samp.iterrows():
        sym = code2sym[int(row.code)]
        et = bt.T0 + pd.Timedelta(hours=int(row.entry_time))
        xt = bt.T0 + pd.Timedelta(hours=int(row.exit_time))
        try:
            e_px = float(op.loc[(sym, et)])
            x_px = float(cl.loc[(sym, xt)])
        except KeyError:
            bad.append(("bar", sym, str(et), str(xt)))
            continue
        ts, rate = fg.get(sym, (np.array([], "int64"), np.array([])))
        lo = np.searchsorted(ts, et.value, side="right")
        hi = np.searchsorted(ts, xt.value, side="right")
        f_sum = float(rate[lo:hi].sum())
        if (abs(e_px - row.entry_px) > 1e-12 * max(1.0, e_px)
                or abs(x_px - row.exit_px) > 1e-12 * max(1.0, x_px)
                or abs(f_sum + row.fund_pnl / row.notional) > 1e-12
                or (hi - lo) != int(row.n_settle)):
            bad.append(("mismatch", sym, str(et), str(xt), e_px, row.entry_px,
                        x_px, row.exit_px, int(hi - lo), int(row.n_settle)))

    checks = []
    checks.append(("%d sampled trades reproduce entry px, exit px and funding sum"
                   % len(samp), not bad))
    for b in bad[:5]:
        print("   ", b)
    d1 = float(np.abs(k.price_pnl + k.fund_pnl - k.cost - k.net_pnl).max())
    checks.append(("price + funding - cost == net on every trade (max err %.1e)" % d1,
                   d1 < 1e-6))
    checks.append(("cost is exactly 20bp of notional (taker 5bp + 5bp, both legs)",
                   bool(np.allclose(k.cost / k.notional, 0.002))))
    checks.append(("events = trades + gap + overlap + capacity",
                   sk["n_events"] == sk["n_trades"] + sk["entry_gap"]
                   + sk["overlap"] + sk["capacity"]))
    checks.append(("entry bar never precedes the event bar",
                   bool((k.entry_time >= k.hour).all())))
    checks.append(("exit strictly after entry", bool((k.exit_time > k.entry_time).all())))
    gap = k.sort_values("entry_time").groupby("code")["entry_time"].diff()
    checks.append(("no same-contract overlap (min entry-to-entry gap > 0)",
                   bool(gap.dropna().min() > 0)))
    d0, d1d = int(k.entry_time.min()) // 24, int(k.exit_time.max()) // 24
    dd = bt.daily_frame(tr, mkt, d0, d1d)
    e_daily = abs(float(dd.net.sum()) - float(k.net_pnl.sum()))
    checks.append(("daily MTM sums to the trade ledger (err %.1e)" % e_daily,
                   e_daily < 1e-6))
    trg = tr.assign(cost=0.0, net_pnl=tr.price_pnl + tr.fund_pnl)
    dg = bt.daily_frame(trg, mkt, d0, d1d)
    e_gross = abs(float(dg.price.sum()) - float(k.price_pnl.sum()))
    checks.append(("daily price leg sums to trade price PnL (err %.1e)" % e_gross,
                   e_gross < 1e-6))
    # real capacity check: reconstruct the concurrent size path from the ledger
    ev_t = np.concatenate([k.entry_time.to_numpy("int64"), k.exit_time.to_numpy("int64")])
    dlt = np.concatenate([k["size"].to_numpy("float64"),
                          -k["size"].to_numpy("float64")])
    order = np.lexsort((dlt, ev_t))          # exits (-) before entries (+) at ties
    peak = float(np.max(np.cumsum(dlt[order])))
    checks.append(("peak gross exposure %.2f <= 10 units" % peak, peak <= 10 + 1e-9))

    print("")
    for name, ok in checks:
        print("  [%s] %s" % ("PASS" if ok else "FAIL", name))
    n_bad = sum(1 for _, ok in checks if not ok)
    print("")
    print("%d / %d checks passed" % (len(checks) - n_bad, len(checks)))
    return 1 if n_bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
