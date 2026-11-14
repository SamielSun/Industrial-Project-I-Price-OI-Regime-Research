# Price + Open Interest Regime Signal — FTEC5910 Industrial Programme

Phase 1 builds the data layer (deliverable **D1**): a 1-hour panel of Binance
USDⓈ-M perpetual futures carrying price, open interest, funding and volume, plus
the point-in-time universe the later phases trade on.

## Rebuild the data

```bash
python phase1/run_phase1.py --out-root data --sample-end 2026-08-31
```

Then verify it:

```bash
python phase1/build_deliverables.py --out-root data --sample-end 2026-08-31 --verify
```

Steps 0–3 need a VPN on this machine. Full instructions, prerequisites, the
design-parameter snapshot the current output was produced with, and the
six individual commands: **[`phase1/REPRODUCE.md`](phase1/REPRODUCE.md)**.

## Layout

| Path | What |
|---|---|
| `config.py` | Phase 1 design parameters. Changing these changes the research design, not just the run |
| `lib/schema.py` | Column and type contract for every table |
| `phase1/` | The six pipeline steps, the runner, and `REPRODUCE.md` |
| `data/` | All outputs. **Not in version control** — rebuild it from `phase1/REPRODUCE.md` |
| `research_archive/` | Course materials, literature, submission drafts (not part of the pipeline) |

## Phase 4 — funding × regime

Conditional event study on the Phase 3 events: the 4×4 forward return and
volatility tables, the within-regime contrasts (BH12 + drop5), the path and
stress blocks, and the exploratory Phase 5 gate. See
[`phase4_funding/GUIDANCE.md`](phase4_funding/GUIDANCE.md),
[`phase4_funding/REPRODUCE.md`](phase4_funding/REPRODUCE.md) and
[`phase4_funding/TABLES.md`](phase4_funding/TABLES.md).

## D1 deliverables

Generated into `data/04_qa/` by the last pipeline step:

| File | What |
|---|---|
| `data_dictionary.md` | Every column: name, type, unit, source, meaning |
| `data_quality.md` | Sample scale, coverage, gap attribution, known limitations |
| `figures/*.png` | Coverage distribution and monthly coverage |
| `checksums.sha256` | SHA256 of every file under `data/` |

## Before starting Phase 2 or later

**[`phase3_event/PHASE3_GUIDANCE.md`](phase3_event/PHASE3_GUIDANCE.md)** — read this first. It is
the single authority for Phase 3: the frozen conventions, the null hypothesis of the note mapped
to the individual experiments, the 11-column result format, and the figure specification.

`data/05_regime/data_dictionary.md` documents every Phase 2 output column, and
`phase2_regime/REPRODUCE.md` is the rebuild recipe.

Phase 1's own output is described by [`data/04_qa/data_dictionary.md`](data/04_qa/data_dictionary.md)
and [`phase1/REPRODUCE.md`](phase1/REPRODUCE.md).

## Self-tests

```bash
python config.py        # 8 checks
python -m lib.schema    # 65 checks
```
