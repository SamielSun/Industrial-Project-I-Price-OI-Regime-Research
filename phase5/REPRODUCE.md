# Phase 5 -- reproduction

Phase 5 = D4: the level-gated strategy prototype, its costed backtest and the
report. All commands run from the repo root.

## One command

    python -m phase5.build all

That runs the gate (G0-G5), the evaluation (splits, six baselines, metrics) and
the report renderer, in that order, and rewrites every product below. No manual
step.

## Environment

    python      C:\miniconda\python.exe   (3.12.9)
    packages    pandas 2.3.3, numpy 2.3.4, pyarrow 23.0.1

No scipy: the gate's one-sided normal tail uses math.erfc.

## Data prerequisites (read-only, produced by Phase 1-3)

    data/07_funding/base/p4_base_h={1,8}.parquet    event grid + fwd/y_raw/lrv/state
    data/01_layer2/klines_1h/                       entry/exit prices
    data/01_layer2/funding/                         settlement rates (actual schedule)
    data/03_reference/universe_membership.parquet   monthly universe for buy-and-hold
    data/06_event_study/panel/freq=1h/symbols.parquet  code <-> symbol map

Phase 5 never writes outside data/08_strategy/ and phase5/.

## Commands (the same three steps, individually)

    python -m phase5.gate        # G0-G5 -> p5_gate.csv, p5_gate_arms.csv
    python -m phase5.eval        # splits + baselines -> p5_rules / p5_baselines / p5_by_*
    python -m phase5.figures     # -> data/08_strategy/figures/f0*.png
    python -m phase5.report      # -> phase5/OOS_REPORT.md

    python -m phase5.build smoke # both arms end to end, ledger only (no files)

## Products

    data/08_strategy/tables/p5_gate.csv         96 cells x every gate condition
    data/08_strategy/tables/p5_gate_arms.csv    2 arms that passed
    data/08_strategy/tables/p5_rules.csv        arms x windows x base/V1
    data/08_strategy/tables/p5_baselines.csv    six baselines, main test window
    data/08_strategy/tables/p5_by_regime.csv    funding state / market-vol cells
    data/08_strategy/tables/p5_by_asset.csv     per-contract
    data/08_strategy/tables/p5_daily.csv        daily PnL of the main test window
    data/08_strategy/tables/p5_year.csv         executable PnL per trade by year
    data/08_strategy/figures/f01_equity.png     cumulative PnL and drawdown
    data/08_strategy/figures/f02_cost_hurdle.png  cost* against the 20bp line
    data/08_strategy/figures/f03_year_decay.png   net PnL per trade by year
    phase5/OOS_REPORT.md                        the report

## Runtimes (project machine)

    gate      ~6 s
    eval     ~10 s
    figures   ~2 s
    report    ~1 s
    all       ~20 s

## Caveats that a reader must know

1. **In-sample.** The v2 design was written after the full sample had been
   examined. Every number is in-sample; there is no blind out-of-sample claim.
   See GUIDANCE.md sec.8.

2. **Costs are taker-only.** 5bp fee + 5bp slippage per side = 20bp round trip.
   No maker case: limit-order fills cannot be modelled without order-book and
   queue data. cost* (gross per trade) is reported as a conversion, not as a
   second cost regime.

3. **rv is a volatility, not a variance**, despite the name and despite one
   sentence in phase4_funding/TABLES.md. exp(lrv) == rv row by row, and
   mean(rv^2) ~ mean(fwd^2).  rv is therefore the FORWARD realised vol and is
   never used as an input; V1 uses backtest.trailing_vol instead.

4. **The gate is level-based** (fwd), not contrast-based. The v1 gate used the
   Phase 4 contrasts; a contrast does not identify a level, and a long-only book
   can only earn the level. archive/HANDOFF_v1.md is the superseded design.

5. **No stop-loss, no winsorising** (Phase 3 frozen conventions).

## History

    phase5/archive/HANDOFF_v1.md   the superseded contrast-gated design
    phase5/GUIDANCE.md              the operative design (v2)