# D5 - Price / Open-Interest Regime Board

A single self-contained HTML page that shows, for the **top 50 contracts by
liquidity**, which ones entered a price/OI regime in the last 24 hours, which
are crowded on funding, and whose volatility is unusual for them. A date picker
covers every day in the dataset.

It is a **state monitor, not a trading signal**. The strategy test in Phase 5
found no first-moment edge after a 20bp taker round trip, and no return, Sharpe
or cost figure appears anywhere on the page.

## Build

    python -m d5_dashboard                     # opens on the last day in the dataset
    python -m d5_dashboard --asof 2026-05-12   # opens on a specific day

Runtime: about 25 s. Output: `data/09_dashboard/dashboard.html` - one file,
2.6 MB, no assets, no network, no server.

## How the page works

Every day in the dataset (1,645 of them) is pre-computed into a compact JSON
payload, gzipped, base64-encoded, and embedded in the HTML. On load the page
decompresses it with `DecompressionStream("gzip")` and renders client-side. That is
why it needs no server: browsers block `fetch()` on `file://`, but an embedded
string is not a fetch.

Day = the last bar of each UTC day. The dataset ends 2026-09-01 00:00 UTC, so
the last selectable day is 2026-08-31.

## "Current" means the frozen dataset, not live data

The page shows what is in `data/`. To move it forward you must refresh the data
first; the dashboard does not fetch anything:

    python phase1/run_phase1.py --out-root data --sample-end <month-end>   # needs VPN
    python phase2_regime/regime_generator.py --out-root data --sample-end <month-end>
    python -m d5_dashboard

Regime labels need trailing 90-day windows, so a partial month cannot simply be
appended: the generator recomputes whole month chunks.

## Sections

| # | Section | What it answers |
|---|---|---|
| 1 | Master table | one row per contract, most recent regime and how long ago |
| 2 | Long buildup (R1) | price up + OI up, within the last 24h |
| 3 | Short buildup (R3) | price down + OI up, within the last 24h |
| 4 | Deleveraging (R4) | price down + OI down, within the last 24h (strictly R4) |
| 5 | Crowding | funding percentile vs 24h OI change, plus the extreme quadrant |
| 6 | Volatility | 24h realised vol ranked against the contract's own 90 days |

Sections 2-4 are **filters of section 1**, not independent computations; a
contract can appear in more than one because it can do more than one thing in a
day. Each row shows that regime's own age and size, which may differ from the
contract's most recent state in section 1.

## Definitions

- **universe** = `universe_membership.parquet` for the month of the day;
  ordered by its `rank` column (30-day liquidity).
- **regime** = the label at that bar; thresholds are rolling 90-day quantiles
  computed by Phase 2.
- **fresh** = within 24h. The `age` column carries the exact number of hours.
- **funding percentile** = the current rate mapped inside the band owned by its
  funding state (negative 0-0.25, neutral 0.25-0.75, high 0.75-0.90, extreme
  0.90-1.00), refined by the contract's p25/p75/p90. Binance funding is heavily
  discretised and p75 == p90 for ~70% of contracts, so a pure percentile is
  undefined and the state picks the band.
- **volatility percentile** = the 24h realised volatility of hourly log returns,
  ranked against the same contract's own trailing 90 days (not against peers:
  absolute volatility differs by orders of magnitude across coins).

## Checks

The build runs four assertions and exits non-zero if any fails:

1. every day falls inside the 50-contract universe (49 or 50 rows per day)
2. sampled R1 rows reproduce from the raw label table
3. funding state agrees with `p4_base_h=1` where the hours overlap
4. every funding percentile sits inside its state's band

The JSON is serialised with `allow_nan=False`: a stray NaN would produce a page
that fails to parse, so the build refuses to write one.

## Not done on purpose

- no historical return, Sharpe or cost figure anywhere (the point of the page
  is the state, not a backtest)
- no composite score, no ranking by "signal strength" - "top" means liquidity
- no live data, no service, no scheduled refresh
