# Numbers audit — report.md

Every bracketed ID in report.md (N01, N02, ...) resolves to one row below. The report is the deliverable; this file is the receipt.

**How to check a claim.** Open the file, find the column named in "Where", compare to "Value". If the value differs, the report is wrong, not this table. Column names are case-sensitive and are the ones inside the parquet/CSV, not the ones the report uses in prose.

**Units.** bp = basis points of notional, 1 bp = 0.01%. "excess" / "y_raw" = forward return minus the same-hour cross-sectional mean of the labelled pool. "raw" / "fwd" = forward return as is. Means are arithmetic means over event rows; no trimming anywhere except where G3 says so.

---

## A. Data and universe

| ID | Claim in report | Value | Where | Definition / caveat |
|---|---|---|---|---|
| N01 | Hourly grid rows, contracts, span | 7,253,002 rows; 285 contracts; 57 months (2021-12 .. 2026-08) | data/04_qa/data_quality.md §1 | Grid size, not observation count: missing hours are still rows, flagged bar_missing / oi_missing |
| N02 | Universe size | 2,700 contract-month cells; 249 distinct contracts; 54 membership months (2022-03 .. 2026-08) | data/04_qa/data_quality.md §1 | 54 < 57 because the 90-day history gate empties the first three months |
| N03 | Universe construction | K = 50 by median quote volume over the trailing 30 days; four gates: (1) base asset not a stablecoin or fiat, 11 bases; (2) 2,160 hourly bars by month start and last active date no earlier than it; (3) OI coverage ≥ 0.90 of all hours and longest publication gap ≤ 48 h; (4) contract type PERPETUAL with underlying COIN, so tokenised equities, ETFs and FX are excluded while PAXG and XAUT stay | config.py L44-100; phase1/build_universe.py L14-36, L412-431 | Liquidity is a ranking, not a gate. Gates 1 and 4 also run in the upstream enumeration, so they reject nothing at this step |
| N04 | Regime thresholds | 90 calendar-day trailing window; p70 on abs(price change) and abs(OI change); ≥ 30 days history | config.py L160, L169; phase4_funding/GUIDANCE.md L64 | Threshold is on absolute change, so "large", not "trending" |
| N05 | Share of contract-hours in a regime | 12.7% | 923,235 event rows ÷ 7,253,002 grid rows = 12.73%; data/06_event_study/events/events_1h.parquet; also printed on the D5 board footer | The denominator is grid rows including missing hours |
| N06 | Market-neutral benchmark | 174 contracts per hour; 7,252,717 labelled rows over 41,639 hours | data/05_regime/regime_labels/freq=1h (row count, distinct ts_end); data/07_funding/base/p4_base_h=1.parquet for the universe pool | The earlier pair (173 per hour over 7,010,789 rows) did not reconcile: 7,010,789 ÷ 41,639 = 168.4, and the audit's own note flagged a third figure of 'about 47'. Recomputed from the label files on 2026-11-23. The universe pool inside the panel averages 14.4 contracts per hour, which is a different denominator |
| N07 | Inference | CGM two-way clustering (contract + month); BH with the family set by stage; q < 0.05 | phase5_simple_strategy/GUIDANCE.md §2; phase3_event/GUIDANCE.md §0 | Phase 3 event-study tests use a one-sided t (cell beats its same-direction benchmark) with a 16-cell family per experiment; Phase 4 contrasts use 12 per (weighting, h); the Phase 5 gate uses a **two-sided** t with 12 per (src, h), which is what N08 and Appendix E report |

## B. Directional results

| ID | Claim in report | Value | Where | Definition / caveat |
|---|---|---|---|---|
| N10 | Four-cell means, h = 24 | mean_excess R1 −3.26 / R2 −13.70 / R3 −20.51 / R4 −4.76 bp; medians −60.57 / −44.03 / −37.70 / −44.59; n 74,875 / 50,519 / 44,585 / 85,828 | data/06_event_study/tables/freq=1h/descriptive_core.csv, sample = headline, h = 24 | **Market-neutral**. Event rows are restricted to in_universe = True |
| N11 | Four-cell raw means, h = 24 | +4.11 / +4.33 / +9.80 / +24.96 bp | same file, column mean_raw | The sign of R3 flips against N10; this is the beta trap, not an inconsistency |
| N12 | Tested spreads, h = 24 | R1 − R2 = +8.35 bp (p_BH 0.039); R3 − R4 = −12.31 bp (p_BH 0.023) | data/06_event_study/tables/freq=1h/exp1_4.csv, experiment "1b 因子对比" | Fixed-effects contrasts. These are NOT the arithmetic differences of N10 (+10.44 and +15.75). Do not quote the arithmetic difference as a test |
| N20 | Regime event count | 256,079 at h = 1; 255,807 at h = 24 | phase3_event/GUIDANCE.md L23, L684 | Headline = in_universe and excl_reason == ok and ok_h |
| N21 | Volatility, Phase 3 | 16 of 16 cell-horizon estimates positive, with p_BH ≈ 0 and abs(t_drop5) between 7.0 and 22.8 | data/06_event_study/tables/freq=1h/exp1_4.csv, experiment `3 波动` | 4 cells × 4 horizons. Correction is Benjamini–Hochberg over the sixteen; `drop5` re-estimates after removing the five most influential contracts. **Phase 3, not Phase 4** |
| N22 | Volatility, Phase 4 | 83 of 96 log-realised-volatility contrasts pass BH | data/07_funding/tables/freq=1h/p4_2_contrasts.csv | The lrv family only. This number says nothing about returns |
| N23 | Returns, Phase 4 | 2 of 96 return contrasts pass BH | data/07_funding/tables/freq=1h/p4_1_contrasts.csv, dv = y_raw | Same 96 count as N22 but a different dependent variable. Mixing the two overstates the return result by ~40x |
| N24 | Strongest return contrasts, h = 1 | R4 × negative funding: +2.472 bp, t = 3.09, p_BH = 0.0240. R3 × negative funding: +5.287 bp, t = 2.78, p_BH = 0.0325. Market-neutral levels under the same weighting: +2.04 and +5.56 bp (raw forward means are +6.37 and −0.67, which is a different quantity) | p4_1_contrasts.csv and p4_1_surface.csv (contract_day, h = 1) | R4 × neg is rank 1, not R3 × neg. The +6.37/−0.67 pair in earlier versions were raw means, not market-neutral |

## C. Executability

| ID | Claim in report | Value | Where | Definition / caveat |
|---|---|---|---|---|
| N08 | Gate funnel | 96 → G1 10 (7 long, all R4; 3 short, all R3) → G2 7 (4 long, 3 short) → G3 4 (all long) → G4 2 → G5 2 arms | data/08_strategy/tables/p5_gate.csv (96 rows, column `direction`); phase5_simple_strategy/GUIDANCE.md §2 and §3 | G1: **two-sided** t on mean(fwd) with CGM two-way SE, BH over 12 cells per (src, h), q < 0.05, n ≥ 400; direction = sign(mean). G2-G4 are mirrored by direction: y_raw, median and trimmed mean on the trade's side, and 4 of 5 years plus the trailing 12 months on that side. The three short candidates fail G3 |
| N31 | The ten G1 survivors (Appendix E) | long: 17.86, 10.01, 24.47, 35.14, 77.22, 32.20, 34.40 bp; short: −7.41, −23.68, −14.21 bp. q 0.000 to 0.036. y_raw runs from −10.16 to +2.94 | data/08_strategy/tables/p5_gate.csv, columns direction, level, q, yraw, med, trim, n_pos, last12, G1 to G4, arm; filter G1 == True | Levels are **raw** forward returns in bp per the G0 definition, not market-neutral; y_raw is the separate column that G2 tests. G1 is two-sided since the 2026-11-21 redesign, so the set includes three negative cells that a one-sided test would have excluded |
| N25 | Cost assumption | 20 bp per round trip, charged once per trade | phase5_simple_strategy/GUIDANCE.md; phase5_simple_strategy/RESULTS.md L21 | Taker fees plus half-spread on both sides. Re-price with cost_star if you disagree |
| N26 | Arm A1, compounded sizing | 20,602 trades; price +8.79 bp; funding +1.59 bp; gross +10.38 bp; net −9.62 bp; gross Sharpe 0.73; net Sharpe −0.62 (95% CI −1.34 to 0.17); annual −9.4%; max drawdown −46.6% | data/08_strategy/tables/p5_rules.csv; phase5_simple_strategy/RESULTS.md | Positions are 2% of equity at entry, so the path compounds and the annual figure is a compound growth rate |
| N27 | Arm B1, compounded sizing | 36,047 trades; price +9.32 bp; funding −0.06 bp; gross +9.26 bp; net −10.74 bp; gross Sharpe 1.24; net Sharpe −1.41 (95% CI −2.10 to −0.63); annual −15.7%; max drawdown −54.3% | data/08_strategy/tables/p5_rules.csv; phase5_simple_strategy/RESULTS.md | Same sizing rule as A1 |
| N28 | Beta decomposition | R4 × negative funding, h = 8: raw +17.86 bp; y_raw +2.94 bp; n = 28,486; drift 14.92 bp | data/07_funding/tables/freq=1h/p4_1_surface.csv (regime R4, funding negative, h = 8); RESULTS.md L145 | 14.92 ÷ 17.86 = 84%, the figure quoted in the text |

## D. Recomputed for this report

These three were not in any project table. They were computed on 2026-11-19 from data/06_event_study/events/events_1h.parquet inside %TEMP%, with no writes to the repository. Anyone can reproduce them with the expression in the last column.

| ID | Claim in report | Value | Definition / caveat | Reproduction |
|---|---|---|---|---|
| N29 | Dispersion by cell, h = 24, market-neutral | p10 −492.6 / −427.4 / −434.1 / −412.7; p90 +518.5 / +412.8 / +406.7 / +415.3; skew 3.97 / 3.69 / 5.25 / 3.19; share below zero 0.581 / 0.571 / 0.562 / 0.573 | in_universe and ok_24h, R1..R4, excess_fwd_24h × 10,000 | groupby(regime).quantile / .skew() |
| N30 | Member vs non-member events, h = 24 | R1: members −3.26 bp (n 74,875), non-members +17.94 bp (n 191,779). R2 −13.70 vs +4.71; R3 −20.51 vs −0.64; R4 −4.76 vs +7.29 | Same benchmark for both groups (the ~176-contract pool). Only the event set differs. This isolates the selection, not the benchmark | groupby(regime, in_universe).mean() |

| N32 | CGM two-way clustering is well behaved in the cells checked | variance components at h = 1 and h = 24, four cells: contract term 9.2e-08 to 6.5e-07, month term 1.3e-07 to 4.0e-07, intersection 8.3e-08 to 2.0e-07; two-way estimate positive in all eight | Recomputed 2026-11-19 from events_1h.parquet, in_universe and ok_h only, month = calendar month of the event bar | In R3 the two-way estimate (4.32e-07 at h = 24, 6.68e-09 at h = 1) is **smaller** than the contract-only estimate (6.54e-07, 7.80e-09). That is a property of the estimator, not an error, and it is why the report says the two-way figure is not always the larger of the available estimates | groupby contract / month / contract x month, sum of squared residuals over n squared |

| N33 | Reversal beats continuation in frequency but not in payoff | p_rev 0.4997 to 0.5394; p_cont 0.4523 to 0.4982; p_flat 0.0016 to 0.0093, across four cells at h = 1 and h = 24 | data/06_event_study/tables/freq=1h/descriptive_core.csv, columns p_cont, p_rev, p_flat | cont = 1{sign(fwd_h) = sign(price_change)}, so for the two down-cells a positive forward return is reversal and for the two up-cells it is continuation. The hit rate is not the mean: the mean is negative in all four cells |

| N34 | Price-only baseline spreads | h = 1: −1.43 bp (t = −2.38, p_BH = 0.485); h = 4: −1.33 (t = −1.14); h = 8: −1.83 (t = −1.22); h = 24: −0.77 (t = −0.31) | phase3_event/GUIDANCE.md §5 (line 388 table); data/06_event_study/tables/freq=1h/exp5_9.csv, experiment "5 纯价格" | Long the up-threshold rows, short the down-threshold rows, pooled with CGM two-way SE and no fixed effects. The table is 555,008 rows at h = 1. Only h = 1 clears \|t\| > 1.96, and it fails BH (0.485) |
| N35 | Four states vs three baselines | 12 day-level differences, 1 passes \|t\| > 1.96, none survives BH and none is robust to dropping 5% of observations | phase3_event/GUIDANCE.md line 15 and §9 (Fig 9); exp5_9.csv | The three baselines are price-only, OI-only and funding-only. The comparison is on the same days, daily equal-weight, Newey-West lag 1 |

| N36 | Volatility increment over the price-matched control | h = 4: R1 +18.44%, R2 +8.09%, R3 +10.77%, R4 +7.10%. h = 1 is larger (+24.40% for R1) but **not quoted**: at h = 1, rv_1h = abs(return of one bar), so it is mechanically tied to the return test | phase3_event/GUIDANCE.md §3 (table at lines 840-850); data/06_event_study/tables/freq=1h/exp1_4.csv, experiment "3 波动" | Percentages are exp(beta) − 1 from a regression of log realised volatility on the cell dummy, where the omitted group is rows that crossed the same price threshold in the same direction but not the OI threshold. This is the increment attributable to open interest, not the total effect of a large move |

| N37 | Increment over the same-direction benchmark, two weightings | Event-weighted: R1 h=1 +2.51 (t 3.41), R3 h=4 −4.39 (−3.02), R4 h=4 +2.05 (2.43), R3 h=8 −8.26 (−3.23), R2 h=24 −7.12 (−2.50), R3 h=24 −11.63 (−2.61); six of 16 pass BH. Daily-weighted, same rows: R1 h=1 −6.36 (−7.60), R2 h=1 +1.35 (1.92), R3 h=1 +2.49 (2.80), R4 h=1 −0.96 (−1.74), R1 h=24 −37.86 (−13.37), R2 h=24 +16.57 (6.20) | data/06_event_study/tables/freq=1h/exp1_4.csv (experiment "1 收益·均值") and robust_daily.csv (experiment 15); phase3_event/GUIDANCE.md §§1 and 15 | Both are contract + month fixed-effects regressions of y_raw on a cell dummy, benchmark = rows that crossed the **same** price threshold in the same direction (cell 0). They differ only in the unit of observation: event-hour vs contract-day. **This is a difference against a benchmark, not the regime's absolute return level** |

| N38 | Persistence gradient | R1 days by hours in state: 1 hour −20.6 bp (n 20,746), 2 −9.0, 3 +4.3, 4 +15.2, 5+ +33.5 (2,129); control span 8.2 bp against 54 bp for R1 | phase3_event/GUIDANCE.md §15 ③; robust_daily_bycount.csv | Daily equal-weight means at h=1. The control is the price-matched OI-quiet rows. This is why the event-weighted and daily-weighted signs differ |
| N39 | The labels' own long-short portfolio | R1 long / R4 short: +0.93, −3.22, −4.50, −3.28 bp at h = 1/4/8/24; \|t\| 0.46 to 1.07 | phase3_event/GUIDANCE.md §9 and the one-line summary at line 14 | Pooled group means, CGM two-way SE. This is the regime portfolio with no funding conditioning and no gate |
| N41 | Coverage outages | Seven months contain a day on which at least 20% of live contracts lack a source; the worst open-interest gap is 16 February 2024, at 42% covered (58% missing) | data/04_qa/figures/monthly_coverage.png; data/04_qa/data_quality.md | The figure annotates each dashed month with its cause: five klines holes, three exchange-wide outages, one index shortfall over a month |
| N42 | Threshold sensitivity of the labels | Labelling rate falls from 23.0% (p55) to 7.5% (p80); within the labelled set the largest move is 3.8 pp at 1h and 11.8 pp at 1d | data/05_regime/figures/threshold_sensitivity.png; data/05_regime/tables/threshold_sensitivity.csv | The mix, not the rate, is the object: the four labels keep their relative shares across the six thresholds |
| N43 | R4 by market-volatility state, h = 1 | low: y_raw −0.12 bp, reversal 51.2%, median drawdown −3.1 bp; mid: −0.61, 52.4%, −6.4; high: +0.99, 55.9%, −18.4 | data/07_funding/tables/freq=1h/p4_6_stress.csv | Descriptive by design; no test of recovery speed is possible without liquidation or survival data |
| N44 | Placebo against random timing | 10 of 16 cells fall outside the 5–95% band of 1,000 random-time draws per contract; 7 fall below it, 3 above, 6 inside | data/06_event_study/tables/freq=1h/placebo.csv, experiment `8 安慰剂` | Draws use the same contracts and the same number of events per contract, hours sampled uniformly from each contract's history |
| N45 | Single-signal baseline spreads | Price only: −1.43, −1.33, −1.83, −0.77 bp at h = 1/4/8/24. OI only: +0.63, −0.71, −1.26, −0.87. Funding only: −0.53, −1.52, −2.59, −6.42 | data/06_event_study/tables/freq=1h/exp5_9.csv; data/06_event_study/figures/f05_07_singles.png | Pooled long-short spreads, no fixed effects, two-way clustered intervals. None is significant at any horizon |
| N46 | Reversal, Phase 4 | 7 of 96 contrasts pass BH12 + drop5, all negative-versus-neutral: R4 +1.46 pp at h=1 (event, p 0.015; contract-day, p 0.042); R1 −1.84 at h=1 and −1.86 at h=4 (contract-day); R2 −2.46 at h=8 (event); R3 +2.86 at h=8 and +2.64 at h=24 (contract-day) | data/07_funding/tables/freq=1h/p4_3_reversal.csv | LPM with contract and month effects. Negative estimate = less reversal, so R1/R2 continue and R3/R4 reverse under negative funding |
| N47 | Beta against matched benchmarks, P4-5 | 72 of 384 estimates pass BH16 + drop5 (22 return, 50 reversal); event and contract-day versions differ in sign in several cells (R1 × neutral +2.35 bp event, −6.23 bp contract-day) | data/07_funding/tables/freq=1h/p4_5_beta.csv; data/07_funding/TABLES.md | Not used as a result; the weight-dependence is the finding |
| N48 | Extreme-only cells are thin | Degenerate bucket at h=1: 217–316 contract-months (R1 292, R2 236, R3 217, R4 316); the full extreme cells hold 584 (R3) and 752 (R1) | data/07_funding/tables/freq=1h/p4_7_diagnostics.csv | Why the Phase 5 gate merges high and extreme: a separate extreme arm would have no power |
| N49 | Compounded sizing | Positions are 2% of equity at entry, so notional falls as the account loses; the equity path is E_t = E_{t-1} + net_t, and annual return is its CAGR | phase5_simple_strategy/backtest.py (`run`, `equity_path`); eval.py | Replaces the earlier fixed-notional run: A1 ends at 64.1 (−35.9%) and B1 at 46.2 (−53.8%) of an initial 100 |

The divergence in N30 is large enough that it belongs in the report rather than in a drawer. It is reported in Section 6.5 as an observation, with no causal claim, because the project did not test for small-cap premia or for pool-construction artefacts.

## E. Numbers that are deliberately NOT in the report

| Number | Why it is excluded |
|---|---|
| "83 of 96 contrasts pass" stated as a return result | 83/96 is the volatility family (N22). Returns are 2/96 (N23) |
| "16 of 16 cells significant" attached to Phase 4 | 16/16 is Phase 3 (N21). Phase 4's volatility block is 17/24 at h = 1 |
| A continuous shift of about +9 bp from moving to a tradable benchmark | No artifact computes a second benchmark. The invariance argument is analytic (a per-hour demeaning is linear within the hour), and it is approximately true, not exactly true. The report states the analytic version and quotes no magnitude |
| A one-week horizon | The pipeline stops at 24 hours. No weekly result exists |
| Any out-of-sample claim | The whole chain is in-sample. See the declaration at phase5_simple_strategy/RESULTS.md L5-6 |

## F. Numbers quoted from other papers

Kept separate from the rows above because the provenance is a PDF, not this project's tables.

| ID | Number | Source | Where in that source |
|---|---|---|---|
| X01 | Interaction coefficient 0.661 (t = 2.70) at the weekly horizon | Kim (2026), Journal of Empirical Finance 89:101779 | Section on the funding × open-interest interaction, eq. (15) discussion |
| X02 | Interaction coefficient 0.393 (t = 2.41) at the monthly horizon | same | same |
| X03 | "Open-interest change alone is not significant" | same | same paragraph: "dLogOI_t itself is not significant" |
| X04 | 65% of 452 anomalies fail \|t\| > 1.96; 82% fail 2.78 | Hou, Xue and Zhang (2020) | abstract |
| X05 | ROC-AUC 0.874 / 0.896; 6.72% loss over 19 cycles at 31 bp | Jadouli (2026), arXiv:2607.19453 | abstract |
| X06 | Reversal in small coins, momentum in the largest | Zaremba et al. (2021) | abstract |
| X07 | Open interest misreported at some venues | Giagkiozis and Said (2024) | abstract |

If any of these is challenged, the check is the PDF in research_archive/literature/ where one exists, otherwise the DOI, not this repository's data. All 14 now have a local PDF. Seven are working-paper or repository copies with pagination that differs from the published articles (cameron2011, christensen2023, cong2023, harvey2020, hou2020, jensen2023, petersen2009), so a page number is only safe to quote from brauneis2021, giagkiozis2024, kim2026, seo2020 or zaremba2021.

## G. Known inconsistencies inside the project's own documentation

Recorded here so that a reader who finds them knows they were seen.

1. Market-neutral pool size: "about 173 contracts per hour" (phase3_event/REPRODUCE.md L109, and in build.py L244) against "about 47 contracts" (phase3_event/GUIDANCE.md L654). The code computes 7,010,789 ÷ 39,459 = 177.7, so 173 is the operative figure.
2. Contract count: 249 in the universe table against 285 contracts in the panel. Both are correct under their own definitions (249 ever qualified; 285 appear in the grid), but the report uses 249 only for the universe and 285 only for the panel.
3. Span: 57 calendar months against 54 membership months. The report states both and says why.
