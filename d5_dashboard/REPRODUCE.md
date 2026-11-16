# D5 - Price / Open-Interest Regime Board

A single self-contained HTML page showing, for the **top 50 contracts by
liquidity**, what regime each one is in right now, what it last did, which ones
are crowded on funding, and whose volatility is unusual for it. A date picker
covers every day in the dataset; every event of the selected day can be opened
under its contract.

It is a **state monitor, not a trading signal**. The strategy test in Phase 5
found no first-moment edge after a 20bp taker round trip.

## Build

    python -m d5_dashboard                     # opens on the last day in the dataset
    python -m d5_dashboard --asof 2026-05-12   # opens on a specific day

Runtime: about 30 s. Output: `data/09_dashboard/dashboard.html` - one file,
about 3.8 MB, no assets, no network, no server.

## How the page works

Every day in the dataset (1,645) is pre-computed into one payload: a 9-field row
per contract, plus that day's event list. The payload is gzipped,
base64-encoded and embedded in the HTML; on load the page decompresses it with
`DecompressionStream("gzip")` and renders client-side. Browsers block `fetch()` on
`file://`, but an embedded string is not a fetch, so no server is needed.

Day = the last bar of each UTC day. The dataset ends 2026-09-01 00:00 UTC, so the
last selectable day is 2026-08-31.

## What "state" means here

Two different things, shown as two columns:

- **state @ bar** - the regime label at that daily close itself. A regime is an
  **hourly event flag**, not a persistent state: across the full sample only
  **12.7%** of contract-hours sit in one, so at a single bar most contracts show
  `no regime`. That is the honest answer to "current regime by coin".
- **last event (24h)** - the most recent regime inside the 24h window ending at
  that bar, with its age in hours.

Sections 2-4 list **every contract with that regime in the window**, sorted by
recency (freshest first). The first 10 are visible; the rest open under
"show all". Each row expands to that contract's **full event list for the day**,
which is where the hourly grain is exposed.

Sections 2-4 are derived from the event list, not stored twice: the latest event
of a regime, its age and its size all come from the same records.

## "Current" means the frozen dataset, not live data

To move the page forward you must refresh the data first; the dashboard does not
fetch anything:

    python phase1/run_phase1.py --out-root data --sample-end <month-end>   # needs VPN
    python phase2_regime/regime_generator.py --out-root data --sample-end <month-end>
    python -m d5_dashboard

Regime labels need trailing 90-day windows, so a partial month cannot simply be
appended: the generator recomputes whole month chunks.

## Sections

| # | Section | What it answers |
|---|---|---|
| 1 | Master table | one row per contract: state at the bar, its 1h change, last event |
| 2 | Long buildup (R1) | price up + OI up within 24h, freshest first |
| 3 | Short buildup (R3) | price down + OI up within 24h, freshest first |
| 4 | Deleveraging (R4) | price down + OI down within 24h, strictly R4 |
| 5 | Crowding | funding percentile vs 24h OI change, plus the extreme quadrant |
| 6 | Volatility | 24h realised vol ranked against the contract's own 90 days |

A contract can appear in several sections: they are separate events, and only the
most recent one per regime is listed in each.

## Definitions

- **universe** = `universe_membership.parquet` for the month of the day, ordered by
  its `rank` column (30-day liquidity). "Top" means liquidity, not signal strength.
- **regime** = the label at that bar; thresholds are rolling 90-day quantiles
  computed by Phase 2. `price_change` and `oi_change` are **one-bar (1h)** changes.
- **state @ bar** = 0-3 for R1-R4, -1 for no regime (`undefined` with a valid
  row), -2 when the row is not usable (warmup or missing data).
- **fresh** = inside the 24h window; the age column carries the exact hours.
- **funding percentile** = the current rate mapped inside the band owned by its
  funding state (negative 0-0.25, neutral 0.25-0.75, high 0.75-0.90, extreme
  0.90-1.00), refined by the contract's p25/p75/p90. Binance funding is heavily
  discretised and p75 == p90 for ~70% of contracts, so a pure percentile is
  undefined and the state picks the band.
- **volatility percentile** = the 24h realised volatility of hourly log returns,
  ranked against the same contract's own trailing 90 days (not against peers:
  absolute volatility differs by orders of magnitude across coins).

## Checks

The build asserts and exits non-zero on any failure:

1. every day falls inside the 50-contract universe (49 or 50 rows per day)
2. every row carries 9 fields
3. `bar_state` is in {-2,-1,0,1,2,3}
4. sampled R1 events reproduce from the raw label table
5. funding state agrees with `p4_base_h=1` where the hours overlap
6. event hours are in [0,24] and regime codes in [0,3]

The JSON is serialised with `allow_nan=False` and gzip is written with
`mtime=0`, so a rebuild is byte-identical.

## Not done on purpose

- no historical return, Sharpe or cost figure in the data views; the footer only
  cites the Phase 5 verdict
- no composite score and no ranking by "signal strength" - sections are sorted by
  recency, and "top" refers to the liquidity universe
- no live data, no service, no scheduled refresh
