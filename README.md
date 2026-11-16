# Price + Open-Interest Regime Signal — FTEC5910 Industrial Programme

A five-phase study of Binance USDⓈ-M perpetual futures: does a **price spike combined
with an open-interest spike**, conditioned on the **funding state** and the
**price/OI regime**, carry a tradable edge after costs?

Short answer: the conditional effect exists statistically, but it does not survive
transaction costs in a long-only book. Phase 5 formalises that negative result.

| Phase | What it produces | Design doc | Rebuild |
|---|---|---|---|
| 1 | Data layer (D1): 1h panel, point-in-time universe, QA | — (see `config.py` docstrings) | `phase1/REPRODUCE.md` |
| 2 | Regime labels at 1h/4h/8h/1d (D2) | — | `phase2_regime/REPRODUCE.md` |
| 3 | Event study: 4 regimes x 4 horizons (D3) | `phase3_event/GUIDANCE.md` | `phase3_event/REPRODUCE.md` |
| 4 | Funding x regime conditional event study | `phase4_funding/GUIDANCE.md`, `TABLES.md` | `phase4_funding/REPRODUCE.md` |
| 5 | Level-gated strategy prototype + OOS report (D4) | `phase5_simple_strategy/GUIDANCE.md`, `OOS_REPORT.md` | `phase5_simple_strategy/REPRODUCE.md` |
| D5 | Regime board: self-contained HTML state monitor | — | `d5_dashboard/REPRODUCE.md` |

Design docs are in Chinese; the REPRODUCE files are in English. Every analysis
phase has exactly one `GUIDANCE.md` and one `REPRODUCE.md`.

## Layout

    config.py            Phase 1 design parameters (frozen; changing them changes the design)
    lib/schema.py        Column and type contract for every table
    phase1/              6 pipeline steps + runner            (builds data/)
    phase2_regime/       regime labelling                      (builds data/05_regime/)
    phase3_event/        event study + figures                 (builds data/06_event_study/)
    phase4_funding/      funding x regime study                (builds data/07_funding/)
    phase5_simple_strategy/              strategy backtest + report            (builds data/08_strategy/)
    d5_dashboard/        regime board (HTML snapshot)         (builds data/09_dashboard/)
    data/                all outputs, NOT in version control (~4.8 GB, rebuildable)
    research_archive/    course materials, literature, submissions (not part of the pipeline)

## Rebuild

Each phase is one command from the repo root; its REPRODUCE file has the flags,
runtimes and prerequisites:

    python phase1/run_phase1.py --out-root data --sample-end 2026-08-31
    python phase2_regime/regime_generator.py --out-root data --sample-end 2026-08-31
    python phase3_event/build.py panel && python phase3_event/experiment/exp1_4.py
    python phase4_funding/build.py data && python phase4_funding/experiment/exp1_2.py
    python -m phase5_simple_strategy.build all

Phase 1 steps 0-3 need a VPN. Phases 3-5 read only `data/` and write only under it.

## Conventions

- **Units.** Returns are in **bp** (`fwd`, `y_raw`, `mdd`); `lrv` is `log(rv)`;
  `rev`/`cont` are probabilities in **pp**.
- **`rv` is a volatility, not a variance.** `exp(lrv) == rv` holds row by row and
  `mean(rv^2) ~ mean(fwd^2)`. It is the realised volatility of the **forward**
  window, so it is an outcome, never an input.
- **No winsorising, no trimming** (Phase 3 frozen convention). Means are tail-driven;
  read the medians next to them.
- **Point-in-time universe.** `data/03_reference/universe_membership.parquet` fixes
  50 contracts per month at month start; `in_universe` carries that flag downstream.

## Phase 5 in one paragraph

The Phase 4 gate used **contrast** significance (negative vs neutral funding within a
regime). A long-only book earns the **level**, not the contrast, so Phase 5 re-gates
on the level (G0-G5 in `phase5_simple_strategy/GUIDANCE.md` §2). Two arms survive: A1 (R4 x negative
funding, hold 8h) and B1 (R4 x high market-vol, hold 1h). At a 20bp taker round trip
both lose: net Sharpe **-1.48** and **-0.98** on the main test window. The volatility
overlay (V1) improves every window but does not turn either arm positive.
**Verdict: not passed.** All Phase 5 numbers are in-sample; see `OOS_REPORT.md`.