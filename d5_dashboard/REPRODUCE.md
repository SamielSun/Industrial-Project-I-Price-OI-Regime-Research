# D5 - Price / Open-Interest Regime Board

A single self-contained HTML page showing, for the **top 50 contracts by
liquidity**, what regime each one is in at a chosen hour, what it last did,
which ones are crowded on funding, and whose volatility is unusual for it.

**Time model.** Every hour for the trailing **180 days**, one snapshot per day
before that, back to 2022-03. One file, no server, no network.

It is a **state monitor, not a trading signal**.

## Build

    python -m d5_dashboard                      # opens on the last bar
    python -m d5_dashboard --asof 2026-08-31T14  # an hour inside the hourly window
    python -m d5_dashboard --asof 2024-05-10     # a day-close snapshot (before the window)

Runtime about 55 s. Output `data/09_dashboard/dashboard.html`, about 4.6 MB.

## How the page works

The payload is gzipped, base64-encoded and embedded; on load the page decompresses
it with `DecompressionStream("gzip")` and renders client-side. Browsers block
`fetch()` on `file://`, but an embedded string is not a fetch, so no server is needed.

A snapshot is labelled by the **bar it shows**: `YYYY-MM-DDTHH` means the bar covering
`[HH:00, HH+1:00)` UTC, whose close is at `HH+1:00`. The last available bar is
`2026-08-31T23`.

## What "state" means

- **state @ bar** - the regime label at that bar. A regime is an **hourly event
  flag**, so most contracts show `no regime`: 12.7% of contract-hours across the
  full sample sit in one.
- **last event** - the most recent regime inside the **24 bars ending at that bar**,
  with its age in hours.

Sections 2-4 list every contract with that regime inside the window, sorted by
recency. The first 10 are visible, the rest open under "show all". Each row expands
to that contract's **events inside the window**.

## Hourly vs daily snapshots

| period | snapshots | fields |
|---|---|---|
| trailing 180 days | every hour (4,320) | all exact |
| before that | one per day, at the day close (1,465) | all exact at that close |

Everything on the page - funding state, volatility percentile, 24h OI change - is
computed on the hourly grid and stored per hour inside the window, so nothing is
interpolated or carried forward there. Outside the window the values are the
day-close values, shown as a daily snapshot.

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
| 2 | Long buildup (R1) | price up + OI up inside the window, freshest first |
| 3 | Short buildup (R3) | price down + OI up inside the window, freshest first |
| 4 | Deleveraging (R4) | price down + OI down inside the window, strictly R4 |
| 5 | Crowding | funding percentile vs 24h OI change, plus the extreme quadrant |
| 6 | Volatility | vol percentile against the contract's own 90d hourly history |

A contract can appear in several sections: they are separate events, and only the
most recent one per regime is listed in each.

## Definitions

- **universe** = `universe_membership.parquet` for the month of the bar, ordered by its
  `rank` column (30-day liquidity). "Top" means liquidity, not signal strength.
- **regime** = the label at that bar; thresholds are rolling 90-day quantiles
  computed by Phase 2. `price_change` and `oi_change` are **one-bar (1h)** changes.
- **window** = the 24 bars ending at the selected bar (inclusive), i.e. the bar's
  own hour plus the 23 before it.
- **state @ bar** = 0-3 for R1-R4, -1 for no regime (a valid row that did not cross
  the thresholds), -2 when the row is not usable.
- **funding percentile** = the current rate mapped inside the band owned by its
  funding state (negative 0-0.25, neutral 0.25-0.75, high 0.75-0.90, extreme
  0.90-1.00), refined by the contract's p25/p75/p90. Binance funding is heavily
  discretised and p75 == p90 for ~70% of contracts, so a pure percentile is
  undefined and the state picks the band.
- **volatility percentile** = rank of the current 24h realised volatility inside a
  rolling 90-day window (2,160 hours) of the same measure, per contract.

## Checks

The build asserts and exits non-zero on any failure:

1. snapshots strictly increasing
2. every snapshot falls inside the 50-contract universe (49 or 50 rows)
3. every row carries 9 fields
4. `bar_state` in {-2,-1,0,1,2,3}
5. sampled R1 events reproduce from the raw label table
6. funding state agrees with `p4_base_h=1` where hours overlap
7. event hours in [0,23], regime codes in [0,3]

JSON is serialised with `allow_nan=False` and gzip with `mtime=0`, so a rebuild is
byte-identical.

## Not done on purpose

- no historical return, Sharpe or cost figure in the data views; the footer only
  cites the Phase 5 verdict
- no composite score and no ranking by "signal strength" - sections are sorted by
  recency, and "top" refers to the liquidity universe
- no live data, no service, no scheduled refresh
