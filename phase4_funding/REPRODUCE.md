# Phase 4 — reproduction

Phase 4 = funding × regime conditional event study. All commands run from the
repo root. Python: the project env (`C:\miniconda\python.exe`); packages:
`pandas`, `numpy`, `pyarrow`, `matplotlib`.

## Prerequisites (already produced by Phase 1–3)

- `data/05_regime/regime_labels/freq=1h/` — labels with `funding_negative/neutral/high/extreme`,
  `funding_p25/p75/p90`, `in_universe`, `excl_reason`.
- `data/06_event_study/panel/freq=1h/` — Phase 3 panel.
- `data/06_event_study/forward/freq=1h/` — forward returns / rv for 1/4/8/24h.
- `data/06_event_study/events/` — the headline event list.
- `lib/schema.py`, `phase3_event/infer.py` — shared schema and inference helpers.

## Commands (in order)

```powershell
python phase4_funding/build.py data                 # P4-0 base + p4_0_validation
python phase4_funding/experiment/exp1_2.py          # P4-1a / P4-2
python phase4_funding/experiment/exp3.py            # P4-3
python phase4_funding/experiment/exp4.py            # P4-4
python phase4_funding/experiment/exp5.py            # P4-5
python phase4_funding/experiment/exp6.py            # P4-6
python phase4_funding/experiment/exp7.py            # P4-7
python data/07_funding/figures.py                    # 5 figures
```

Approximate runtimes on the project machine: build ~1–2 min; exp1_2 ~45 s;
exp3 ~30 s; exp4 ~10 s; exp5 ~63 s; exp6 ~5 s; exp7 ~4 s; figures ~10 s.

## Outputs

- `data/07_funding/base/p4_base_h={1,4,8,24}.parquet` — intermediate; **gitignored**.
- `data/07_funding/tables/freq=1h/p4_1_surface.csv`, `p4_1_contrasts.csv`,
  `p4_2_vol.csv`, `p4_2_contrasts.csv`, `p4_3_reversal.csv`, `p4_4_path.csv`,
  `p4_5_beta.csv`, `p4_6_stress.csv`, `p4_7_disjoint.csv`,
  `p4_7_diagnostics.csv` — the deliverables (CSV tracked; parquet ignored).
- `data/07_funding/tables/freq=1h/p4_0_validation.csv`, `exp1_2_validation.csv`,
  `exp3_validation.csv`, `exp4_validation.csv`, `exp5_validation.csv`,
  `exp6_validation.csv`, `exp7_validation.csv` — 109 + 120 + 66 + 131 + 89 +
  28 + 148 = **691 checks**.
- `data/07_funding/figures/f01_return_level.png`, `f02_vol_level.png`,
  `f03_difference_forest.png`, `f04_beta_forest.png`, `f_p4_4_path.png`.

`figures.py` reads the parquet files, which are gitignored; a fresh clone must
re-run the pipeline (or the CSVs can be loaded instead).

## Scope notes

- `p4_note_map.csv` is **not** part of the deliverable (the note is guidance,
  not a deliverable map).
- P4-1b (within-funding contrasts) is **out of scope** for Phase 4.
- The gate record is in `GUIDANCE.md` §14: 9 qualifying contrasts, 192
  searches, exploratory screening only.

## Known caveats (see `TABLES.md`)

- p75 == p90 in 56.96% of event rows; `high` and `extreme` coincide there.
- Thin cell: degenerate bucket 217–316 contract-months (h=1).
- h=1 `mdd` is `min(0, dir·fwd)` (no path); `mdd_p90` is 0.
- Verdicts use `y_raw`; raw `fwd` is descriptive (corr 0.243 across P4-1a
  contrasts).
- Event vs contract-day can differ; contract-day is the secondary weighting.
- No winsorising (Phase 3 frozen convention); means include extreme moves.
