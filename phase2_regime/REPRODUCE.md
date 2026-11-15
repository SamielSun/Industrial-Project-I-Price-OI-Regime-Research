# Phase 2 — how to rebuild data/05_regime/

    python phase2_regime/regime_generator.py --out-root data

## Prerequisites

- C:\miniconda\python.exe (3.12) with pandas / numpy / pyarrow / matplotlib
- data/02_features/features_1h/ and data/03_reference/universe_membership.parquet must already exist (built by Phase 1)
- **No network access needed** — Phase 2 only reads what Phase 1 downloaded
- ~2 GB RAM. The panel is processed **contract by contract**; the full 7.25M-row panel is never materialised

## Options

| Flag | Meaning |
|---|---|
| --out-root | **required** — output root (the data/ directory) |
| --in-root | where to read from (defaults to --out-root). Use it for a smoke run so a subset does not overwrite the real output |
| --subset | process only these contracts (smoke test) |
| --freqs | only these frequencies (1h / 4h / 8h) |
| --batch | contracts per flush (default 20) |
| --no-validate | skip the per-chunk schema validation |

Smoke test (writes nothing into data/):

    python phase2_regime/regime_generator.py --out-root %TEMP%\p2smoke --in-root data --subset BTCUSDT LITUSDT MYXUSDT

## Design parameters used for this run

    {
 "freqs": [
  "1h",
  "4h",
  "8h",
  "1d"
 ],
 "n_bars": 1,
 "window_days": 90,
 "min_history_days": 30,
 "quantiles": [
  0.55,
  0.6,
  0.65,
  0.7,
  0.75,
  0.8
 ],
 "quantile_main": 0.7,
 "z_thresholds": [
  0.5,
  0.75,
  1.0,
  1.25,
  1.5
 ],
 "funding_window_days": 90,
 "funding_min_history_days": 30,
 "mkt_vol_window_hours": 8760,
 "mkt_vol_min_history_days": 30,
 "mkt_vol_smooth_hours": 24,
 "mkt_vol_quantiles": [
  0.3333333333333333,
  0.6666666666666666
 ]
}

Every field carries its evidence in the docstrings of config.py; the full reasoning is in phase3_event/GUIDANCE.md.

## Output

    data/05_regime/
      regime_labels/freq={1h,4h,8h,1d}/year=YYYY/chunk=YYYY-MM.parquet
      tables/*.parquet + *.csv
      figures/regime_share_over_time.png
      data_dictionary.md
      checksums.sha256

## Run summary

| | |
|---|---|
| frequencies | 1h, 4h, 8h, 1d |
| label rows written | 10,274,187 |
| parquet chunks | 228 |
| schema validation | 228 chunks checked, 0 failed |
| wall time | 3199 s |

## Related command

    python phase2_regime/build_sensitivity.py --out-root data

Adds table 5 (threshold_sensitivity.parquet/.csv) and threshold_sensitivity.png, then refreshes checksums.sha256. It reads the label tables written above and recomputes nothing else.

checksums.sha256 covers everything under data/05_regime/ except itself. It is **not** merged into Phase 1's data/04_qa/checksums.sha256 — D1's certificate stays frozen.

