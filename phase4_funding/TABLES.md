# Phase 4 — table notes

All tables live in `data/07_funding/tables/freq=1h/`. Returns are in **bp** (`y_raw`,
`fwd`, `mdd`, `mfe`, `mae`, β); `lrv` is log(rv); `rev`/`cont` are in **pp**
(LPM coefficients); `rv` is a variance.

## Common definitions

- **Event**: 1h bar where |Δprice| and |ΔOI| both exceed the contract's trailing
  90-day p70; headline = `in_universe & excl_reason=="ok"`; 256,079 rows;
  255,857 with a funding state (219 excluded).
- **Regime**: R1 up+OI up, R2 up+OI down, R3 down+OI up, R4 down+OI down.
- **Funding**: `negative` f ≤ p25; `neutral` p25 < f ≤ p75; `high` f > p75
  (includes extreme); `extreme` f > p90. `high`/`extreme` are nested, not
  disjoint; on p75 == p90 they coincide and `high-only` is empty.
- **Weighting**: `event` = one row per event; `contract_day` = one row per
  (contract, UTC day, regime, funding state, dir) group mean.

## Per table

### `p4_1_surface.csv`
4×4 levels (R1–R4 × negative/neutral/high/extreme) of `fwd` and `y_raw`
(mean, median, CI), event/contract-day × 1/4/8/24h. Descriptive, no test.
`high` includes `extreme` (nested, overlapping).

### `p4_1_contrasts.csv`
12 within-regime contrasts per (h, weighting): negative/high/extreme vs neutral.
FE: 16 cell dummies + contract + month FE; CGM two-way clustered SE; BH 12 per
family; `t_drop5` = re-estimate after dropping the 5 most influential contracts.
`y_raw` is the inferential outcome; `fwd` is descriptive (no BH).
**Drop5 is not always stable**: 19/96 `y_raw` contrasts flip sign between `t`
and `t_drop5` (all with |t| < 1 in the current sample).

### `p4_2_vol.csv`
4×4 levels of `rv`/`lrv`; same layout. `lrv = log(rv)`; rows with rv = 0
(= flat forward) are excluded (2,244 rows, 0.88%), so `lrv_n_obs` can be below
`rv_n_obs`. `rv` level means include the zeros.

### `p4_2_contrasts.csv`
12 within-regime `lrv` contrasts, BH 12 + drop5; `estimate_pct` =
`exp(estimate) − 1` (%). The P4-2 family is the robust block: 17/24 h=1
contrasts pass BH12 + drop5, all same sign (higher funding → higher forward
volatility).

### `p4_3_reversal.csv`
12 within-regime `rev` LPM contrasts (pp), BH 12 + drop5. `rev = 1{fwd·dir < 0}`;
`cont = 1 − rev` includes flat (fwd = 0); `cont_*` columns are the exact
negative of `rev_*`. `rev > 0` = more reversal; `rev < 0` = more continuation.

### `p4_4_path.csv`
MFE / MAE / MDD 4×4 (mean, median, p10/p50/p90), event/contract-day × 4h.
Descriptive. **h=1 caveat**: `mdd = min(0, dir·fwd)` (no intrabar path);
`mdd_p90` is 0 at h=1; `mdd_p50` equals `fwd_median` there. Use h ≥ 4 for MDD.

### `p4_5_beta.csv`
16 β per (h, weighting, outcome): treatment cell minus a matched benchmark
(same direction, same funding, price-threshold hit but OI quiet; cell 0 + the
other OI state). FE: contract + month; CGM; BH 16 + drop5. `fwd` and `rev` are
secondary; the **event** and **contract-day** β can have opposite signs
(e.g. R1 neutral +2.35 bp event vs −6.23 bp contract-day), so the β is
weight-dependent, not a single estimate.

### `p4_6_stress.csv`
Descriptive R4 × market-vol (low/mid/high/unknown) × h: n, mean `y_raw`,
`rev` %, `mdd_p50`. **Not** a test of "faster": no first-touch/survival, and
MDD at h=1 is degenerate. High-vol rows mechanically have higher vol and
deeper MDD; differences are not causal.

### `p4_7_disjoint.csv`
5 mutually exclusive categories (negative / neutral / high_only / extreme /
degenerate) + the `high` union, per (h, weighting, regime). `negative`/`neutral`
are full-sample; `high_only`/`extreme` are non-degenerate (p75 < p90);
`degenerate` is the p75 == p90 `high = extreme` bucket. `high` = sum of the
three high buckets; means/rv/rev are additive, **`mdd_p50` is a median and is
not additive**. Thin: degenerate bucket 217–316 contract-months (h=1);
`full R3×extreme` 584, `R1×extreme` 752.

### `p4_7_diagnostics.csv`
Degeneracy shares (56.96% event rows, 65.41% event-sample contract-months,
48.9% full label), the degenerate thin cells, drop5 sign flips (P4-1a 19/96,
P4-2 0/96, P4-3 7/96, P4-5 6/128), and raw vs y_raw correlations (P4-1a 0.243,
P4-5a 0.849).

### `*_validation.csv`
Automated checks for each block (109/120/66/131/89/28/148). `pass_` is a real
boolean; failures exit non-zero.
