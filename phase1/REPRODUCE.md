# Reproduce

sample_end = `2026-08-31`　sample_start = `2021-12-01`

One command rebuilds every D1 output from scratch; the six steps it runs are
listed further down for when one of them needs debugging.

## Design parameters of this output

These come from `config.py`. **If `config.py` has since been edited, the values
below are the ones the output was produced with** — different parameters give a
different output, so this snapshot is what identifies which design a given
output corresponds to.

```
sample_start = 2021-12-01
K = 50
liq_window_days = 30
min_history_bars = 2160
require_live_at_month_start = True
min_oi_coverage = 0.9
max_oi_gap_hours = 48
stablecoin_bases = ['USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDP', 'SUSD', 'USDD', 'PYUSD', 'FRAX', 'USTC']
```

Note it records **parameter values only, not the code version**. If only the
computation logic changed while parameters stayed the same, this snapshot cannot
show it — use the git history for that.

## One command

```bash
python phase1/run_phase1.py --out-root data --sample-end 2026-08-31
```

This runs the six steps below in order, passing `--out-root` and `--sample-end`
to each. It stops at the first non-zero exit and names the step that failed;
re-run the whole command afterwards, or run the remaining steps individually.

It does **not** run the verification below, and it takes no other flags —
step-specific flags (`--subset`, `--keep-cache`, `--skip-download`, …) are used
directly against that step's script.

## Prerequisites

- Python 3.12 with `pandas` / `pyarrow` (2.3.3 / 23.0.1 here)
- Downloads use **Python `urllib` only** — `curl` and `Invoke-WebRequest` fail
  on this machine (Windows schannel fault)
- **`s3-ap-northeast-1.amazonaws.com` is DNS-poisoned here; Steps 0–3 need a VPN.**
  `data.binance.vision` (CloudFront) is unaffected
- **Step 6a reads the committed snapshot `phase1/exchange_info_snapshot.json`, so it
  needs no network.** Add `--refresh-exchange-info` only to update the gate-4
  criterion (needs VPN)

## The same thing, step by step

What `run_phase1.py` executes, in order — this is also the fallback route when
one step needs debugging or has to be re-run on its own.

```bash
# Step 0-2  enumerate archive -> hard filter -> monthly liquidity rank -> pool
python phase1/build_candidate_pool.py --out-root data --sample-end 2026-08-31

# Step 3  download the candidate pool's raw data
python phase1/fetch_market_data.py --out-root data --sample-end 2026-08-31

# Step 4  build the four normalized layer-2 tables
python phase1/build_layer2.py --out-root data --sample-end 2026-08-31

# Step 5  build the 19-column dense panel
python phase1/build_features.py --out-root data --sample-end 2026-08-31

# Step 6a four eligibility gates -> PIT membership
python phase1/build_universe.py --out-root data --sample-end 2026-08-31

# Step 6b quality report + dictionary + checksums + this file
python phase1/build_deliverables.py --out-root data --sample-end 2026-08-31
```

## Self-tests

```bash
python config.py            # 8 checks
python -m lib.schema        # 65 checks
```

## Verify

```bash
# re-hash every output file; exit 0 when all digests match
python phase1/build_deliverables.py --out-root data --sample-end 2026-08-31 --verify
```

## Notes

- **Only Steps 0–3 need a VPN** (S3 enumeration and CDN download). Steps 4–6b are
  pure local computation; Step 6a reads a committed snapshot.
- Every script takes its output directory from `--out-root`, and every one
  **requires** it (`run_phase1.py` included). Environment variables are not used
  — they do not survive across shells, which once wrote smoke-test results into
  the production directory.
- **Step 6b must run last**: the checksums are its final write, and every file
  written before it is hashed. Re-running Steps 3–6a invalidates the checksums;
  re-run Step 6b to regenerate them.
- **This file is in `phase1/` and tracked by git**, not in `data/` — it is
  instructions rather than output. Step 6b rewrites it on every run; commit the
  change, so the log of which window and parameters each output used survives
  the next `data/` wipe.
