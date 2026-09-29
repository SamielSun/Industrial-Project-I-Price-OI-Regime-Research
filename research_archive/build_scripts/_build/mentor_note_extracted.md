THEO Industrial Project Idea Note
Price + Open Interest Regime Signal


| Field | Detail |
| Strategy / Project Name | Price + Open Interest Regime Signal |
| Strategy Type | Crypto derivatives / market structure signal / short-horizon regime classification |
| Project Objective | Build a public-data event study that classifies crypto perpetual futures moves into price/OI regimes and tests whether those regimes predict short-term continuation, reversal, volatility, or crowding risk better than price momentum alone. |


# 1. Executive Summary
Crypto perpetual futures markets contain useful information in the joint behavior of price and open interest. Price alone tells us direction. Open interest tells us whether total outstanding derivative positioning is expanding or contracting. When combined, they may help distinguish between different market states:

| Price | Open Interest | Possible Interpretation |
| Up | Up | New long positioning / bullish leverage buildup |
| Up | Down | Short covering / position unwind |
| Down | Up | New short positioning / bearish leverage buildup |
| Down | Down | Long unwind / liquidation-like deleveraging |


The purpose of this project is to test whether these price/OI regimes contain predictive information about future returns, volatility, or reversal/continuation behavior in liquid crypto perpetual futures.
The project is not intended to immediately produce a production trading strategy. The goal is to build a clean, interpretable research framework that helps answer:
Does the joint movement of price and open interest help us understand whether crypto perp moves are likely to continue, reverse, or become unstable?
# 2. Hypothesis
The central hypothesis is:
Price moves accompanied by meaningful open interest changes contain more information than price moves alone. Specifically, price/OI combinations can help distinguish fresh positioning, short covering, long unwind, and new short buildup, and these regimes have different forward-return and volatility characteristics.
The null hypothesis is:
Price/OI regimes do not improve prediction of future returns, volatility, or reversal behavior compared with simple price momentum alone.
# 3. Market Intuition
Open interest is a key variable in perpetual futures markets because it measures how much leveraged positioning is outstanding. A price move can have different meanings depending on whether open interest is rising or falling.
Price Up + OI Up: This may indicate new leveraged longs entering the market. The move may continue if the positioning reflects genuine conviction, but it may also become crowded if funding rises too much.
Price Up + OI Down: This may indicate short covering rather than fresh long demand. The price move may be less durable if it is driven by forced exits rather than new buying.
Price Down + OI Up: This may indicate new shorts entering the market. The move may continue if bearish positioning is building, but it may also create future short-squeeze risk.
Price Down + OI Down: This may indicate long liquidation or deleveraging. The move may overshoot and later mean-revert if forced selling pressure exhausts.
The project should test these interpretations empirically rather than assume them.
# 4. Target Market and Universe
## Initial Universe
- BTC and ETH perpetual futures
- Top 30–50 liquid USDT-margined perpetual futures on Binance
- Exclude stablecoins
- Exclude newly listed tokens with insufficient history
- Exclude contracts with unreliable open interest data
- Exclude illiquid contracts where transaction costs dominate
## Possible Extension
- OKX
- Bybit
- Hyperliquid
- Cross-exchange comparison of price/OI regimes
The first version should remain Binance-only for cleaner data and simpler implementation.
# 5. Data Sources

| Data | Purpose |
| OHLCV | Price returns, volatility, momentum |
| Open interest | Positioning expansion or contraction |
| Funding rates | Crowding and leverage cost filter |
| Volume | Liquidity and participation |
| Mark/index price | Perp pricing consistency |
| Liquidation data, optional | Event confirmation for deleveraging regimes |


Preferred frequency:
- 1-hour bars for initial study
- Optional tests at 4-hour and 8-hour bars
- Daily aggregation for robustness
All timestamps should be standardized to UTC.
# 6. Signal Definition
At each timestamp and for each coin, calculate price change and open interest change over a fixed lookback window N.

| Measure | Example Definition |
| Price Change | price_change = close_t / close_(t-N) - 1 |
| Open Interest Change | oi_change = OI_t / OI_(t-N) - 1 |


## Regime Classification
Each asset-time observation is classified into one of four regimes:

| Regime | Condition | Label |
| Regime 1 | Price up, OI up | Fresh long buildup |
| Regime 2 | Price up, OI down | Short covering |
| Regime 3 | Price down, OI up | Fresh short buildup |
| Regime 4 | Price down, OI down | Long unwind / deleveraging |


To avoid noise, define minimum thresholds:
- abs(price_change) > price_threshold
- abs(oi_change) > oi_threshold
Example starting thresholds: price change or OI change above a rolling 60th/70th percentile, or z-score based thresholds. Thresholds should be tested for robustness, not optimized to fit the backtest.
# 7. Funding Filter
Funding should be used as a conditioning variable, not necessarily as the primary signal.

| Funding State | Definition |
| Negative funding | Funding below trailing 25th percentile |
| Neutral funding | Funding between 25th and 75th percentile |
| High positive funding | Funding above trailing 75th percentile |
| Extreme funding | Funding above trailing 90th percentile |


Example research questions:
- Does Price Up + OI Up perform better when funding is neutral?
- Does Price Up + OI Up become a reversal signal when funding is extreme?
- Does Price Down + OI Down mean-revert faster after high liquidation/funding stress?
- Does Price Down + OI Up predict continuation when funding is still neutral?
# 8. Forward Outcome to Test
## A. Forward Return
Measure future returns over 1 hour, 4 hours, 8 hours, and 24 hours. Example: forward_return_(t,h) = close_(t+h) / close_t - 1
## B. Forward Volatility
Measure whether certain regimes predict higher future realized volatility.
## C. Reversal / Continuation

| Outcome | Meaning |
| Continuation | Future return follows the original move |
| Reversal | Future return moves against the original move |
| No edge | Future return has no clear relationship |


## D. Drawdown / Adverse Move
For each event, measure max favorable excursion, max adverse excursion, and drawdown over the holding window. This is important because a signal may have positive average return but poor path behavior.
# 9. Baseline Comparison
The price/OI regime signal must be compared against simple baselines:
- Price Momentum Alone — Does price direction alone predict forward return?
- OI Change Alone — Does OI increase or decrease alone predict forward return?
- Funding Alone — Does funding state alone predict forward return?
- Random Event Timing — Do randomly selected timestamps produce similar results?
The price/OI framework adds value only if it explains future behavior better than these simple baselines.
# 10. First Test Plan
## Phase 1: Data Collection
- Collect OHLCV, open interest, funding rates, volume, and mark/index price if available.
- Output: clean panel dataset, missing-data report, and data dictionary.
## Phase 2: Regime Labeling
- Create price/OI regime labels at 1h, 4h, and 8h frequencies.
- Output: regime counts, frequency by asset, and frequency by market condition.
## Phase 3: Event Study
- For each regime, calculate average and median forward return, hit rate, volatility after event, reversal probability, and continuation probability.
- Output: forward return table, event-study plots, and regime comparison charts.
## Phase 4: Funding Interaction
- Split each regime by funding state: negative, neutral, high, and extreme.
- Output: 4x4 table of price/OI regimes versus funding states with forward return and volatility by bucket.
## Phase 5: Simple Strategy Test
- Only after the event study shows signal value, test simple rules such as continuation after Price Up + OI Up when funding is neutral or reversal after Price Down + OI Down after deleveraging.
- This should be a simple exploratory backtest, not a full production strategy.
# 11. Example Output Table

| Price/OI Regime | Funding State | Expected Behavior to Test |
| Price Up + OI Up | Neutral | Continuation |
| Price Up + OI Up | Extreme Positive | Crowded reversal risk |
| Price Up + OI Down | Any | Short-covering exhaustion |
| Price Down + OI Up | Neutral | Downside continuation |
| Price Down + OI Up | Extreme Negative | Short-squeeze risk |
| Price Down + OI Down | Stress / High Vol | Mean reversion after deleveraging |


These are hypotheses, not conclusions.
# 12. Evaluation Metrics
- Forward return by regime
- Hit rate
- Reversal probability
- Continuation probability
- Realized volatility after event
- Max adverse excursion
- Turnover
- Transaction cost sensitivity
- IC by horizon, if signal is converted into a ranked score
- Performance by asset
- Performance by market regime
# 13. Expected Deliverables
## D1 — Clean Data Pipeline
- Binance public data pull
- OHLCV, OI, funding, volume
- Parquet storage
- Data dictionary
## D2 — Price/OI Regime Classifier
- Price/OI change calculation
- Threshold logic
- Four-regime label generator
## D3 — Event Study Report
- Forward return by regime
- Reversal/continuation probability
- Funding interaction
- Volatility impact
## D4 — Simple Strategy Prototype
- One or two simple rules
- Costed backtest
- Baseline comparison
## D5 — Dashboard / Visualization
- Current price/OI regime by coin
- Top coins with fresh long buildup
- Top coins with fresh short buildup
- Deleveraging candidates
- Funding-adjusted crowding view
## D6 — Final Report and Presentation
- Answer whether price + open interest improves understanding of short-term crypto perp behavior compared with price alone