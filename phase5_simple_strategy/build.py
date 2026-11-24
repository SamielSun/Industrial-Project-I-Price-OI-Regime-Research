"""One-command entry point.

    python -m phase5_simple_strategy.build all     # gate -> eval -> report
    python -m phase5_simple_strategy.build smoke   # both arms end to end, ledger only
"""
from __future__ import annotations

import argparse
import time

from . import backtest as bt
from . import rules as R


def smoke() -> int:
    t0 = time.time()
    code2sym, sym2code, n_sym = bt.load_symbols()
    mkt = bt.load_market(sym2code)
    fund = bt.load_funding(sym2code)
    print("market bars %s | funding rows %s | %.1fs"
          % (f"{len(mkt.keys):,}", f"{len(fund.keys):,}", time.time() - t0))
    for arm in R.ARMS:
        hold = arm["hold"]
        ev = R.select(bt.load_base(hold), arm)
        tr, sk = bt.run(ev, hold, mkt, fund, direction=arm.get("direction", 1))
        k = tr[tr.kept]
        d0, d1 = int(tr.entry_time.min()) // 24, int(tr.exit_time.max()) // 24
        m = bt.metrics(bt.daily_frame(tr, mkt, d0, d1), tr, (d1 - d0 + 1) / 365.0)
        gross = k.price_ret + k.fund_pnl / k.notional
        print("")
        print("%s (hold %dh, %s): events %d -> trades %d | gap %d overlap %d capacity %d"
              % (arm["name"], hold, arm["role"], sk["n_events"], sk["n_trades"],
                 sk["entry_gap"], sk["overlap"], sk["capacity"]))
        print("   price %6.2fbp  funding %6.2fbp  cost 20.00bp  NET %7.2fbp"
              % (k.price_ret.mean() * 1e4,
                 k.fund_pnl.sum() / k.notional.sum() * 1e4,
                 k.net_pnl.sum() / k.notional.sum() * 1e4))
        print("   cost* %6.2fbp (gross per trade), %.2fbp short of the 20bp round trip"
              % (gross.mean() * 1e4, gross.mean() * 1e4 - 20.0))
        print("   in-sample: Sharpe %6.2f  ann %7.2f  vol %6.2f  MDD %7.2f"
              % (m["sharpe"], m["ann_ret"], m["ann_vol"], m["mdd"]))
    print("")
    print("elapsed %.1fs" % (time.time() - t0))
    return 0


def run_all() -> int:
    from . import eval as ev
    from . import figures, gate, report
    t0 = time.time()
    print("[1/4] gate")
    if gate.main([]) != 0:
        return 1
    print("")
    print("[2/4] eval")
    if ev.main() != 0:
        return 1
    print("")
    print("[3/4] figures")
    if figures.main() != 0:
        return 1
    print("")
    print("[4/4] results")
    if report.main() != 0:
        return 1
    print("")
    print("all done in %.1fs" % (time.time() - t0))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["smoke", "all"])
    a = ap.parse_args()
    return smoke() if a.step == "smoke" else run_all()


if __name__ == "__main__":
    raise SystemExit(main())