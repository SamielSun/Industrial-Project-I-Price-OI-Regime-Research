# Phase 4 — funding × regime interaction · handoff

Status: Phase 3 is closed (deck, record, tables frozen). This file hands Phase 4 over with
the design decisions already made, the evidence behind them, and the options that were
rejected so they are not re-litigated.

Audience: whoever builds Phase 4. Not the sponsor — Gordon sees the deck and the record
(`research_archive/submission/`), not this file.

---

## 1. What Phase 3 established

| Result | Numbers | Status |
|---|---|---|
| Forward volatility premium | 16/16 cells positive, t 7.0–20.8, BH p < 1e-11, drop5 stable | **robust** |
| 2×2 interaction (OI effect ≠ 0 and sign-flips with price direction) | +3.46 / +6.81 / +12.22 / +20.67bp at 1/4/8/24h, t 2.79–4.26, BH 3.2e-4, drop5 4/4 | **robust** |
| Forward return, event level | 6/16 cells; only R3 holds at 4/8/24h (−4.39/−8.26/−11.63bp). R1@1h +2.51, R4@4h +2.05, R2@24h −7.12 | **fragile** |
| Forward return, contract-day weighting | every regime flips sign (R1 +2.51 → −6.36bp @1h; +5.06 → −37.86bp @24h) | **weight-dependent** |
| Reversal | up branch 8/8 (R1 +1.19…+2.51pp, R2 −1.00…−2.17pp); down branch only at 24h | **up-branch only** |
| Long-short spreads, all four | no spread survives BH; label vs baselines: 12 gaps, 1 clears \|t\| before correction (p_bh 0.51) | **null** |
| Levels | all eight single legs negative at 8/24h; raw means positive only because of the market factor | **null after neutralising** |
| Persistence gradient | one appearance in a day: R1 −20.6bp; five or more: +33.5bp (benchmark span 8.2bp) | **mechanism, not yet a rule** |

Caveat that is *not* in the shipped tables: controlling for the size of the triggering move
(deciles of log(|Δp|/threshold), ad-hoc check) takes R1 from +24.4% to +14.1% (t 16.3),
R2 to +2.9%, R3 to +7.8%, and R4 to +1.2% (t 1.5). See §7 risk 4.

---

## 2. Conventions inherited (do not change)

- Universe: monthly top-50 by trailing 30-day quote volume, four gates; 249 contracts, 54 months.
- Event: a 1h bar where |price change| and |OI change| both exceed the contract's own
  trailing 90-day 70th percentile (≥30 days history). Headline = `excl_reason == ok` and
  `in_universe`; 256,079 events.
- `y_raw` = forward return minus the same-hour equal-weighted pool mean (market-neutral).
  No winsorising, no sign flipping.
- `lrv` = log realised volatility over the h hours after the event; not neutralised.
- Inference: contract + month two-way fixed effects, two-way clustered SE (CGM),
  Benjamini–Hochberg within a pre-declared family, `t_drop5` after removing the five most
  influential contracts. Threshold |t| > 1.96.
- Horizons 1, 4, 8, 24 hours.

---

## 3. Decisions taken for Phase 4

### 3.1 Funding scale — keep the rolling percentile

Per contract, trailing 90 calendar days, p25 / p75 / p90 on the settlement series. Four
states: `negative` (≤ p25), `neutral`, `high`, `extreme` (> p90).

**Rejected:** absolute bp scale as the *main* specification, and "deviation from own
median" as the main specification. Reasons below — the absolute scale is kept as an
appendix instead.

### 3.2 Keep four buckets

**Rejected:** collapsing to three or two buckets for power. The four-state structure is
what the note specifies, and the note's hypotheses are phrased per state.

### 3.3 Degenerate rows — keep everything, disclose

64.85% of rows with a funding state have p75 == p90, so `high` and `extreme` select the
same observations there; the fourth column carries independent information only in the
remaining ~35%. 23.92% have p25 == p75 (neutral is empty by construction, and indeed 0.00%
of those rows are neutral); 16.55% have all three equal. 261 of 285 contracts are affected.
The ties also push the modal funding rate into `negative`, which holds 46.0% of stated rows
rather than the nominal 25%.

**Decision:** keep all rows, report the 4×4 as the note asks, and state the degeneracy in
the table note. **Rejected:** dropping degenerate rows (would select on funding variability)
and a separate non-degenerate subsample table (not requested; keep the appendix budget for
the absolute scale).

### 3.4 Both returns and volatility are primary; reversal is descriptive only

Reversal is reported in the 4×4 as a rate (as in Phase 3 Experiment 10), but it is not a
third test family.

### 3.5 Cell means for the table, interaction coefficients for the verdict, β in an appendix

Three layers, keep them separate:

| Layer | Quantity | Use |
|---|---|---|
| L1 | cell mean of `y_raw` (already market-neutral, **no** fixed effects) | the readable 4×4 table |
| L2 | cell mean of `y_raw` after removing contract and month means | the formal interaction test |
| β | regime minus same-direction benchmark, within funding bucket | appendix |

Market neutralisation is part of the definition of `y_raw`; the fixed effects are an
additional layer on top. For volatility there is no neutralisation, so only "raw cell mean"
and "FE-adjusted cell mean" exist.

### 3.6 Interaction = 16 cells, not a hand-picked contrast

Model: `y = contract FE + month FE + 4 regime main effects + 4 funding main effects +
16 interaction coefficients` (interactions sum to zero along each margin). Each coefficient
answers "does this cell deviate from regime + funding acting additively". Test all 16.

- One BH family of **16 per horizon per dependent variable** (8 families).
- Interpretation weight on **h = 1 for returns** and **h = 24 for volatility**; 4h and 8h
  are reported but labelled reference.
- **Rejected:** three ad-hoc contrasts (P×F / O×F / P×O×F) — it is a reparameterisation of
  the same thing that invites cherry-picking; and a single family of 64/128 — BH would be
  too strict to detect anything.

### 3.7 Sample gate

Report contract-months per cell always. Cells with < 400 contract-months are marked
"underpowered" (t retained, flagged); < 100 report the mean only, no t.

### 3.8 Every weighting, both directions

Returns and volatility are both computed with (i) event weighting and (ii) one vote per
contract-day. Phase 3 showed the return result flips sign between the two; reporting one
only is choosing the answer.

### 3.9 Phase 5 gate

Phase 5 starts only for an interaction that passes **BH within its family and drop5**. The
earlier "both weightings must agree in sign" condition was withdrawn (they are reported, not
gating).

### 3.10 Scope

1h labels only. 4h / 8h label frequencies: parameterised, ~40 min rebuild + estimates,
deferred to the end of Phase 4 as a frequency robustness. **IC is out of scope** — it
requires turning the discrete four-state label into a continuous score, which is a
signal-redefinition decision, not a Phase 4 deliverable.

### 3.11 "Extreme negative" is proxied by `negative`

The note's hypothesis R3 + extreme negative → short-squeeze cannot be tested as written: the
labels only have a one-sided `extreme` (> p90). Use `negative` (≤ p25) and say so in the
table note.

---

## 4. The deliverable: 4×4 table plus a hypothesis map

Main output, per horizon and per dependent variable: 4 regimes × 4 funding states, with
cell mean (L1), n (rows and contract-months), and the interaction coefficient with its t
from L2.

Then one page that walks the note's six hypotheses:

| Note's hypothesis | Operational test | Verdict |
|---|---|---|
| R1 + neutral → continuation | (R1, neutral) cell mean > 0 and above R1's other buckets | testable |
| R1 + extreme positive → crowded reversal | (R1, extreme) below (R1, neutral); reversal rate descriptive | testable, weakened by degeneracy |
| R2 + any funding → short-covering exhaustion | R2 across four buckets flat; interaction row ≈ 0 | weak (absence claim) |
| R3 + neutral → downside continuation | (R3, neutral) negative and below R3's other buckets | testable |
| R3 + extreme negative → short-squeeze | (R3, negative) vs (R3, neutral), with the proxy caveat | testable, weakened |
| R4 + stress / high vol → mean reversion | **not a funding hypothesis** — see below | out of scope |

The sixth row is a market-state hypothesis, not a funding one. Phase 3 Experiment 14b
already describes it (R4 at 1h: +0.99bp high-vol, −0.59 mid, −0.15 low). Declare it out of
scope for Phase 4 and carry it into the Phase 5 rule design, which needs a high-volatility
condition anyway.

---

## 5. Appendix: absolute-scale robustness

Settlement intervals are not uniform — 8h 51.8%, 4h 45.1%, 1h 3.0%, 2h 0.1% of settlements
— so the only comparable absolute unit is **bp per day**: `funding_rate × 24 / interval_hours × 1e4`.

Distribution on event hours: p25 0.45, **p50 = p60 = p70 = p80 = 3.00**, p95 9.53,
p99 22.60 bp/day. 3.00 is the exchange default (0.01% / 8h) and carries ~40% of the mass,
so any cut at 3 splits an atom — the bucket must be atom-aware.

Buckets: `≤0` / `(0,3)` / `=3` / `>3`. Contract-months for R1: 2,103 / 2,144 / 2,484 / 730.
Shares of event hours: ≤0 28.1%, >3 10.3%, >6 7.6%, >10 4.7%.

Note what this does and does not fix: it removes the interval mismatch and gives "at default"
a real meaning, but **it does not enlarge the high-funding tail** — genuinely high funding is
rare in event hours (10.3% above 3bp/day). Thin tail cells are a property of the data, not of
the percentile label.

This appendix exists to answer "what if you use bp instead of percentiles". It does not enter
the verdict.

---

## 6. Data and code map

```
phase3_event/
  build.py            forward / events / panel construction, gates, market neutralisation
  infer.py            fe_ols, demean2, cgm_cov/se, bh, p_two, nw_se
  experiment/         exp1_4.py, exp5_9.py, exp8_placebo.py, descriptive.py, event_path.py, robust_daily.py
  figures.py          15 figures
  PHASE3_GUIDANCE.md  the authoritative record of Phase 3 (16 experiments)
  REPRODUCE.md        rebuild order and timings (~6.6 min end to end)
data/05_regime/regime_labels/freq=1h/   labels (regime, funding booleans + p25/p75/p90, mkt_vol_state)
data/06_event_study/panel/freq=1h/      analysis panel, 8 columns
data/06_event_study/tables/freq=1h/     Phase 3 result tables
data/02_features/features_1h/           raw funding_rate and funding_interval_hours (needed for §5)
config.py                               RegimeConfig / EventConfig, frozen
```

Phase 4 should read the panel and the labels, not the event table: the panel is the only
object that carries the same-direction benchmark rows needed for β.

---

## 7. Risks and known limitations

1. **Degeneracy** — 64.85% of rows cannot separate `high` from `extreme`; the interaction for
   the extreme column is effectively identified from the non-degenerate third.
2. **Thin cells** — R1 × extreme holds 752 contract-months (against 2,384 for R1 × neutral).
   Scaling from Phase 3's standard errors, only effects of roughly 13bp at h=1 and 60bp at
   h=24 are detectable in such cells. Single-digit interaction effects will not be resolvable.
3. **The `negative` bucket is contaminated** — it absorbs the modal funding rate, so it mixes
   "cheap" with "unchanged". Anything said about the low-funding side inherits this.
4. **Volatility and trigger size** — the Phase 3 volatility premium falls about in half once
   the size of the triggering move is held fixed (R1 +24.4% → +14.1%, R4 → 0). If Phase 4
   reports volatility by funding bucket, add the same trigger-size control as a robustness
   row; funding may correlate with move size.
5. **Reversal is not a test family** — the note's "crowded reversal risk" is only half-tested
   (returns), with reversal rates descriptive.
6. **Sample size in the tail is real** — do not respond by widening the buckets; report the
   gate instead.

---

## 8. Open items waiting on the sponsor

Sent to Gordon, not blocking:

1. Monthly top-50 liquidity universe acceptable as the point-in-time sample?
2. 90-day lookback and the threshold scheme acceptable across the three label families?
3. Difference estimator acceptable for regime-vs-benchmark?
4. Long-short constructions are diagnostic, not implementable, and carry no cost; costed
   version is Phase 4–5 work.
5. Funding buckets: the percentile degeneration described in §3.3 — switch to an absolute
   scale, or keep percentiles and reduce buckets?

No answer has been received. Phase 4 proceeds on the decisions in §3 and will show the
degeneracy diagnostic alongside the main table, so either answer is accommodated.

---

## 9. Checklist for Phase 4

- [ ] Rebuild the funding state columns with an explicit `funding_degenerate` flag (p75 == p90) for the table note and for the §5 appendix.
- [ ] Build the hourly bp/day series from `features_1h.funding_rate` and `funding_interval_hours`, forward-filled, for the appendix only.
- [ ] Cross-tabulate regime × funding (rows, contract-days, contract-months) before estimating anything; confirm the §7 cell sizes.
- [ ] Estimate the 16-coefficient interaction model (L2) per horizon, per dependent variable; clustered SE; BH within each 16; drop5.
- [ ] Produce the L1 cell-mean table (market-neutral for returns, raw for volatility) with n, and the β appendix.
- [ ] Repeat everything under contract-day weighting.
- [ ] Write the hypothesis map (§4) with verdicts and evidence strength.
- [ ] Run the absolute-scale appendix (§5) at 4 buckets, atom-aware.
- [ ] Write the Phase 5 gate sentence: which interaction, if any, unlocks a rule.
