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

## D1 deliverables

Generated into `data/04_qa/` by the last pipeline step:

| File | What |
|---|---|
| `data_dictionary.md` | Every column: name, type, unit, source, meaning |
| `data_quality.md` | Sample scale, coverage, gap attribution, known limitations |
| `figures/*.png` | Coverage distribution and monthly coverage |
| `checksums.sha256` | SHA256 of every file under `data/` |

## Self-tests

```bash
python config.py        # 8 checks
python -m lib.schema    # 65 checks
```
