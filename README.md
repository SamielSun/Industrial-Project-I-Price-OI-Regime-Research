# Price + Open-Interest Regime Signal — FTEC5910 Industrial Programme

A five-phase study of Binance USDⓈ-M perpetual futures: does a **price move combined
with an open-interest move**, conditioned on the **funding state** and the
**market-volatility state**, carry a tradable edge after costs?

Short answer: the four regimes separate forward **volatility** cleanly, but not forward
**direction** in a way that survives transaction costs. Phase 5 formalises that negative
result with a two-sided, level-gated book. Every result is in-sample, one venue, 54
membership months.

## Deliverables

    research_archive/report/report.md          submitted text (English, 11 sections + appendices)
    research_archive/report/figs/              the 17 figures it uses
    research_archive/report/refs.bib           14 research sources + 1 software citation
    research_archive/report/numbers_audit.md   provenance for every number (N01-N49)
    research_archive/report/open_questions.md  open issues and how they were closed

## Phases

| Phase | What it produces | Design doc | Rebuild |
|---|---|---|---|
| 1 | Data layer (D1): 1h panel, point-in-time universe, QA | `config.py` docstrings | `phase1/REPRODUCE.md` |
| 2 | Regime labels at 1h/4h/8h/1d (D2) | — | `phase2_regime/REPRODUCE.md` |
| 3 | Event study: 4 regimes x 4 horizons (D3) | `phase3_event/GUIDANCE.md` | `phase3_event/REPRODUCE.md` |
| 4 | Funding x regime conditional event study | `phase4_funding/GUIDANCE.md`, `TABLES.md` | `phase4_funding/REPRODUCE.md` |
| 5 | Level-gated strategy prototype + results (D4) | `phase5_simple_strategy/GUIDANCE.md`, `RESULTS.md` | `phase5_simple_strategy/REPRODUCE.md` |
| D5 | Regime board: self-contained HTML state monitor | — | `d5_dashboard/REPRODUCE.md` |

Design docs are in Chinese; REPRODUCE files are in English.

## Layout

    config.py            Phase 1 design parameters (frozen; changing them changes the design)
    lib/schema.py        Column and type contract for every table
    phase1/              data pipeline                         (builds data/)
    phase2_regime/       regime labelling                      (builds data/05_regime/)
    phase3_event/        event study + figures                 (builds data/06_event_study/)
    phase4_funding/      funding x regime study                (builds data/07_funding/)
    phase5_simple_strategy/  strategy backtest + results       (builds data/08_strategy/)
    d5_dashboard/        regime board (HTML snapshot)          (builds data/09_dashboard/)
    data/                all outputs, not in version control (~4.8 GB, rebuildable)
    research_archive/    report, course materials, literature, submissions

## Rebuild

One command per phase from the repo root; each REPRODUCE file has the flags and runtimes:

    python phase1/run_phase1.py --out-root data --sample-end 2026-08-31
    python phase2_regime/regime_generator.py --out-root data --sample-end 2026-08-31
    python phase3_event/build.py panel && python phase3_event/experiment/exp1_4.py
    python phase4_funding/build.py data && python phase4_funding/experiment/exp1_2.py
    python -m phase5_simple_strategy.build all

Phase 1 steps 0-3 need a VPN. Phases 3-5 read only `data/` and write only under it.

## Conventions

- **Units.** Returns are in **bp** (`fwd`, `y_raw`, `mdd`); `lrv` is `log(rv)`;
  `rev`/`cont` are probabilities in **pp**.
- **`rv` is a volatility, not a variance.** `exp(lrv) == rv` row by row, and
  `mean(rv^2) ~ mean(fwd^2)`. It is realised volatility of the **forward** window,
  so it is an outcome, never an input.
- **No winsorising, no trimming.** Means are tail-driven; read the medians next to them.
- **Point-in-time universe.** `data/03_reference/universe_membership.parquet` fixes 50
  contracts per month at month start; `in_universe` carries that flag downstream.

## Phase 5 in one paragraph

Phase 4 gated on **contrast** significance (negative vs neutral funding within a regime).
A traded book earns the **level**, so Phase 5 re-gates on the level, two-sided, and trades
its sign (G0-G5 in `phase5_simple_strategy/GUIDANCE.md` §2). Ten cells clear G1, seven
long and three short; the shorts fail G3 and two long arms survive: A1 (R4 x negative
funding, 8h) and B1 (R4 x high market-vol, 1h). Gross edges are **10.38** and **9.26 bp**
against a 20 bp taker round trip, so both lose after costs: net Sharpe **-0.62** and
**-1.41**, annual return **-9.4%** and **-15.7%**. **Verdict: not passed**, in-sample.
