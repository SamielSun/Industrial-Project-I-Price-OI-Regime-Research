# Phase 4 — Funding × Regime Interaction · Guidance

**Status.** Design locked. This document specifies what Phase 4 does and how. It supersedes the 16-γ interaction prototype in `HANDOFF.md` §3.5–3.7 where the two conflict; the mentor's idea note is the authority for Phase 4. No implementation code here.

**Audience.** The implementer and the academic supervisor. The sponsor sees the final tables, not this file.

**Superseded artefacts.** `phase4_funding/tables/l1_cellmeans.parquet` and `l2_interactions.parquet` were produced under the old 16-γ design. E1/E2 below replace them; do not cite the old tables.

---

## 0. What the note requires

The only direct Phase 4 definition is §10 of the note:

> **Phase 4: Funding Interaction**
> - Split each regime by funding state: negative, neutral, high, and extreme.
> - Output: 4x4 table of price/OI regimes versus funding states with forward return and volatility by bucket.

The two supporting passages are explicitly illustrative:

> **§7** — "Funding should be used as a conditioning variable, not necessarily as the primary signal."
>
> **§7 Example research questions:**
> - Does Price Up + OI Up perform better when funding is neutral?
> - Does Price Up + OI Up become a reversal signal when funding is extreme?
> - Does Price Down + OI Down mean-revert faster after high liquidation/funding stress?
> - Does Price Down + OI Up predict continuation when funding is still neutral?

> **§11 Example Output Table** — six rows — "These are hypotheses, not conclusions."

Consequences for Phase 4:

- The deliverable is a **stratified 4×4 conditional-performance table**, not a model.
- The examples are slices of the table, not an exhaustive hypothesis list.
- The note does not prescribe a regression, a contrast family, a multiplicity correction, or an economic threshold.
- The note's §9 baselines (price alone, OI alone, funding alone, random timing) belong to Phase 3: experiments 5–9 and 8 already cover them. Phase 4 does not repeat them.
- E2 (the 12 within-regime contrasts) is the **project's** formalization of the note's example questions. It is not a note requirement; it exists because the project needs a pre-declared inferential layer for the Phase 5 gate. Label it as such in any write-up.

---

## 1. Locked design

| Item | Locked choice |
|---|---|
| Primary object | **E1**: 4×4 conditional surface. **E2**: 12 within-regime funding contrasts. |
| Funding states | Nested, exactly as the note: `negative` f ≤ p25; `neutral` p25 < f ≤ p75; `high` f > p75 (**includes extreme**); `extreme` f > p90. `high ⊇ extreme`. |
| Regimes | R1 price up + OI up; R2 up + OI down; R3 down + OI up; R4 down + OI down. |
| Return outcomes | `fwd_h` (raw, note §8 A) and `y_raw` (market-neutral, Phase 3 headline). `y_raw` is the verdict measure; `fwd_h` is the note-literal descriptive measure. |
| Volatility outcome | Realized volatility `rv` over the h hours after the event. E1 reports arithmetic mean and median of `rv` (Phase 3 convention). E2 uses `lrv = log(rv)` and reports `exp(contrast) − 1` in %. |
| Horizons | 1, 4, 8, 24 hours. |
| Weighting | Event-weighted primary; one-vote-per-contract-day robustness. |
| Inference | Contract + month two-way fixed effects, CGM two-way clustered SE, BH within each 12-test family, drop5 per contrast. **No 16-γ ANOVA.** |
| Table statistics | Mean + median, clustered CI for the mean, n in a separate panel. No p-values in E1. |
| Phase 5 gate | Return-only: any `y_raw` contrast passes BH 12 + drop5. Volatility does not gate; it is a risk overlay. |
| Out of scope | Baselines, IC, absolute bp/day scale, β appendix, 16-γ interaction, threshold optimisation, cross-exchange, Phase 5 backtest, R4 stress (Phase 3 experiment 14b). |

---

## 2. Definitions and sample

### 2.1 Sample

Inherit Phase 1–3 frozen conventions; do not rebuild.

| Item | Value |
|---|---|
| Universe | Monthly top-50 by trailing 30-day quote volume, four gates; 249 contracts; 54 months (2022-03 … 2026-08). |
| Event | 1h bar where |Δprice| and |ΔOI| both exceed the contract's trailing 90-day p70 (≥30 days history). |
| Headline sample | `in_universe` and `excl_reason == "ok"`; `cell ∈ {1,2,3,4}`; h=1: 256,076 event rows with a valid forward return. |
| No funding state | 219 events (0.09%) have all four funding booleans false (p25 missing). Exclude from E1/E2/E5; report the count. |
| E1/E2 sample at h=1 | 255,857 rows. h=4/8/24 differ only by `ok_{h}h` losses. |
| Contract-months | 2,700 = 50 contracts × 54 months. |
| lrv missing | h=1: 2,244 event rows (0.9%); drop for volatility analyses only. |

### 2.2 Regimes

`cell` 1–4 as defined by Phase 2/3. No change.

### 2.3 Funding states — nested, not a partition

Per contract, trailing 90 calendar days, p25/p75/p90 of the settlement funding series, carried as a step function from the most recent settlement. Strict `>` (the note says "above"); do not switch to `≥`.

```
negative : f ≤ p25
neutral  : p25 < f ≤ p75
high     : f > p75        # includes extreme
extreme  : f > p90        # subset of high
```

The four columns are **not mutually exclusive**. `high` and `extreme` are the same rows when p75 == p90.

For estimation only, define the four disjoint latent states:

```
s0 = negative
s1 = neutral
s2 = high-only   (p75 < f ≤ p90)
s3 = extreme     (f > p90)
```

The reported `high` column is the union `s2 ∪ s3`; its mean is the sample-size-weighted average of the `s2` and `s3` means. The disjoint states are not reported in the main table; they are the appendix split (E5) and the estimation basis (E2).

### 2.4 Return and volatility outcomes

- `fwd_h = close_{t+h} / close_t − 1`. **Not in the panel**; join from `data/06_event_study/forward/freq=1h` (or `events/events_1h.parquet`) on `(symbol, ts_end)`. Map the panel's `symbol` code through `panel/freq=1h/symbols.parquet`; map `hour` to `ts_end = 2021-12-01 UTC + hour hours`.
- `y_raw` is already in the panel: `fwd_h` minus the same-hour equal-weighted mean over the full market pool (7,010,789 rows). Market-neutral, not winsorised, not sign-flipped.
- `rv_h` is the realized variance over the h hours after the event; `lrv = log(rv_h)`. Both are in the forward/panel pipeline; the panel carries `lrv`.

Units: returns in bp (×1e4); volatility levels in % (rv × 100); volatility contrasts in % (`exp(Δlog rv) − 1`).

### 2.5 Weighting

- **Event-weighted**: each event row is one observation. This is the note's event-study unit.
- **Contract-day-weighted**: one observation per `(symbol, UTC day, regime, disjoint funding state)`; average the dependent variable within the group; run the same FE model on the group means. Day = `hour // 24`, as in Phase 3 experiment 15.
- For the nested `high` column: under event weighting, the union mean uses event counts as weights; under contract-day weighting, it uses contract-day-cell counts. Do not mix the two.
- The contract-day weighting is the Phase 4 analogue of the note's §5 "daily aggregation for robustness". A literal daily-aggregated 4×4 (E6) is optional and not part of the locked design; Phase 3 experiment 15 already covers daily aggregation of the regime effect.

---

## 3. Estimands and notation

For regime `r` and disjoint funding state `s`, let `m_{r,s}` be the contract+month FE-adjusted cell mean:

```
y_it = Σ_{r,s} m_{r,s} · 1{regime=r, state=s} + α_contract + λ_month + ε_it
```

The 16 disjoint cell indicators are a partition; one collinearity with the FE constant remains (the cell indicators sum to 1). Drop one reference cell (R4 × s3), estimate 15 coefficients, recover the 16 `m` up to an additive constant. All reported quantities are differences, so the constant cancels.

Reported nested cell means:

```
μ(r, neg)     = m_{r,s0}
μ(r, neu)     = m_{r,s1}
μ(r, high)    = w2·m_{r,s2} + w3·m_{r,s3},   w2 = n_{r,s2}/(n_{r,s2}+n_{r,s3}), w3 = 1 − w2
μ(r, extreme) = m_{r,s3}
```

`n` is the number of observations in the cell under the current weighting (event rows or contract-day cells). The weights are realized sample sizes and are treated as fixed.

The contrast vector and its SE are linear combinations of the 15 coefficients, using the CGM covariance:

```
V = V_contract + V_month − V_contract×month
SE(c) = sqrt(c' V c)
```

`c` for the 12 contrasts is defined in §5.2.

---

## 4. E1 — the 4×4 conditional surface

**Purpose.** The note's literal output: forward return and volatility by bucket.

**Sample.** E1/E2 sample (§2.1), one horizon at a time.

**Table layout.** Rows R1–R4; columns `negative / neutral / high (incl. extreme) / extreme`; one table per horizon and weighting.

Each cell reports:

| Field | Definition |
|---|---|
| `fwd_mean`, `fwd_median` | Raw forward return, bp. |
| `y_mean`, `y_median` | Market-neutral `y_raw`, bp. |
| `rv_mean`, `rv_median` | Realized volatility level, % (arithmetic mean/median of `rv`; Phase 3 convention). |
| CI | 95% CI for each mean, CGM two-way clustered by contract and month. Descriptive; no p-values in E1. |

A separate 4×4 n panel reports, per cell:

| Field | Definition |
|---|---|
| `n_obs` | Event rows (event weighting) or contract-day-cell groups (contract-day weighting). |
| `n_cdays` | Unique `(symbol, UTC day)` in the cell. |
| `n_cmonths` | Unique `(symbol, calendar month)` in the cell. |

For the nested columns: `n_obs` of `high` is the sum over `s2` and `s3`; `n_cdays` and `n_cmonths` are the **unique** counts over the union (a contract-day can contain both `s2` and `s3`; do not add the two counts).

**Expected anchors at h=1 (event weighting, y_raw)** — use for validation:

| Cell | n rows | n contract-months |
|---|---:|---:|
| negative (all regimes) | 93,489 | 9,499 |
| neutral (all regimes) | 123,907 | 9,461 |
| high-only (all regimes) | 18,834 | 3,377 |
| extreme (all regimes) | 19,627 | 2,777 |
| high (incl. ext), all regimes | 38,461 | 4,471 (cell-level; unions overlap across regimes) |
| R1 × neutral | 37,038 | 2,384 |
| R1 × high (incl. ext) | 13,184 | 1,183 (unique union, not 902+752) |
| R1 × extreme | 6,905 | 752 |
| R3 × extreme | 2,416 | 584 (thinnest disjoint cell) |

The 400 contract-month gate (§3.7 of the old handoff) is retained as a **flag**, not a filter: mark any cell below 400. The thinnest disjoint cell is 584, so none is flagged at h=1; report the flag anyway.

**Output.** `phase4_funding/tables/e1_surface.parquet` + `.csv`, long format: one row per `(weighting, h, regime, funding)`.

---

## 5. E2 — within-regime funding contrasts

**Purpose.** The formal read of the note's row-wise example questions: within each regime, how does performance change across funding states? This is the project's operationalization, not a note requirement.

**Sample.** Same rows as E1, per horizon and weighting.

**Dependent variables.**

- `y_raw`: primary, enters the BH family.
- `fwd_h`: note-literal descriptive, report estimate + 95% CI, **no BH, no p_bh**.
- `lrv`: volatility, enters a separate BH family, reported as `exp(contrast) − 1` in %.

### 5.1 Contrasts

For each regime `r` (4) and each funding state `f ∈ {negative, high, extreme}` (3), versus `neutral`:

```
C1(r) = μ(r, negative) − μ(r, neutral)
C2(r) = μ(r, high)     − μ(r, neutral)    # high includes extreme
C3(r) = μ(r, extreme)  − μ(r, neutral)    # subset of high
```

12 contrasts per `(dv, h, weighting)`. The three are correlated by construction (the high set contains the extreme set); BH is applied to all 12.

Derived, for interpretation only (not a separate test): the tail increment

```
C4(r) = μ(r, extreme) − μ(r, high) = w2 · (m_{r,s3} − m_{r,s2})
```

Report it alongside C2/C3 in the text or appendix. Do not add it to the BH family.

### 5.2 Estimation

1. Build the 16 disjoint cell indicators (`regime × {s0,s1,s2,s3}`).
2. Under event weighting: estimate the FE model on event rows.
   Under contract-day weighting: aggregate to `(symbol, day, regime, state)` means first, then estimate the same FE model on the group means.
3. Recover the 15 coefficients and the CGM covariance; form the nested means `μ(r, high)` with weights `w2`, `w3` from the current weighting's counts.
4. Form the 12 contrast vectors `c`; estimate = `c'β`, SE = `sqrt(c'Vc)`, `t = estimate/SE`, `p` two-sided normal.
5. BH within the 12 contrasts **per `(dv, h, weighting)`**; separate families for `y_raw` and `lrv`; `fwd` is descriptive and has no BH.
6. `t_drop5`: for each contrast, compute the influence function `ψ_c = (X̃ c) · û`; score contracts by `|Σ ψ_c|`; drop the five largest; re-estimate the FE model and the contrast; report `t`.
7. Flag `|t_drop5| ≤ 1.96` for any contrast that passed BH.

### 5.3 Table

One row per `(weighting, dv, h, regime, contrast)`:

| Column | Meaning |
|---|---|
| `estimate` | bp for `y_raw`/`fwd`; log point for `lrv`. |
| `estimate_pct` | `lrv` only: `(exp(estimate) − 1) × 100`. |
| `se` | CGM clustered SE on the estimation scale. |
| `t`, `p` | Two-sided. |
| `p_bh` | BH within the 12; `NA` for `fwd`. |
| `t_drop5` | Drop-five-contracts t; `NA` for `fwd` if not computed. |
| `n_obs`, `n_cmonths` | Cell sizes for the contrast (union for high). |
| `in_bh` | `TRUE` for `y_raw`, `lrv`; `FALSE` for `fwd`. |

**Output.** `phase4_funding/tables/e2_contrasts.parquet` + `.csv`.

---

## 6. E3 — column profile (descriptive)

**Purpose.** The other margin of the 4×4: within each funding state, how do the four regimes compare? This is descriptive context, not a second test family.

**Sample.** Same as E1.

**Table.** One table per `(h, weighting)`: rows = funding states `negative / neutral / high / extreme`; columns = R1–R4. Each cell reports `fwd_mean`, `y_mean`, `rv_mean`, and the clustered 95% CI for each mean; n in a separate panel.

No p-values. If the column profile shows a strong pattern, a follow-up contrast family (regimes vs R4 within funding state) can be added later, but it is not part of the locked design.

**Output.** `phase4_funding/tables/e3_column_profile.parquet` + `.csv`.

---

## 7. E4 — hypothesis map

**Purpose.** Read the note's six example rows against the E1/E2 output. The six are anchors, not the complete hypothesis set; the remaining cells are exploratory.

For each anchor, report:

| Anchor (note §11) | Cell(s) | What is read | Verdict |
|---|---|---|---|
| R1 + neutral → continuation | (R1, neutral) | `fwd` mean/median sign; `y_raw` vs R1's other funding cells | consistent / inconsistent / unclear |
| R1 + extreme positive → crowded reversal | (R1, extreme) | `fwd` sign; C3(R1); C4(R1) | consistent / inconsistent / unclear |
| R2 + any funding → short-covering exhaustion | R2 row | three contrasts C1/C2/C3(R2) ≈ 0 (flat profile) | consistent / inconsistent / unclear |
| R3 + neutral → downside continuation | (R3, neutral) | `fwd` sign; `y_raw` vs R3's other funding cells | consistent / inconsistent / unclear |
| R3 + extreme negative → short-squeeze | (R3, negative) vs (R3, neutral) | C1(R3) > 0 | consistent / inconsistent / unclear |
| R4 + stress / high vol → mean reversion | not a funding cell | out of scope; Phase 3 experiment 14b | out of scope |

Proxy caveat: the labels have no one-sided extreme-negative bucket. `negative` (f ≤ p25) proxies the note's "extreme negative" for the R3 short-squeeze anchor; say so in the table note.

Verdict rules (qualitative, no new tests):

- **consistent**: the observed sign matches the note's expected direction, and the relevant `y_raw` contrast passes BH 12 + drop5 (where a contrast applies).
- **inconsistent**: the sign is opposite, or the contrast is significant in the opposite direction.
- **unclear**: sign matches but the contrast does not pass BH/drop5, or the cell is underpowered; report the n.

The `fwd` sign is the note-literal continuation/reversal read. `y_raw` is the verdict measure. The six anchors are not a confirmatory family; do not BH across them.

**Output.** `phase4_funding/tables/e4_hypothesis_map.csv`.

---

## 8. E5 — degeneracy diagnostic

**Purpose.** Disclose that `high` and `extreme` are the same rows on degenerate funding days, and provide the high-only vs extreme split.

### 8.1 Table note (all E1/E2 tables)

State:

- The four funding columns are overlapping conditions, not a partition: `high = f > p75` includes `extreme = f > p90`.
- In the estimation sample, `p75 == p90` on **56.96%** of event rows (h=1) and **48.9%** of contract-months; on those rows `high` and `extreme` select the same observations, and `high` contains no high-only rows.
- Label-wide (all 7,022,757 stated rows, 285 contracts): 64.85% p75==p90, 23.92% p25==p75, 16.55% all three equal; 46.0% of stated rows are `negative`. The estimation-sample figures above are the ones that describe the table.
- 219 events with no funding state are excluded.
- 206 of 249 estimation-sample contracts have at least one event row on a p75==p90 row.

### 8.2 Appendix split

A 4×4 table (rows R1–R4; columns `negative / neutral / high-only / extreme`) with `fwd_mean`, `y_mean`, `rv_mean`, and n. This is the disjoint-state view; the main table keeps the note's nested columns.

Validation identity: the E1 `high` cell mean must equal `w2 × high-only + w3 × extreme` (max abs difference < 1e-12).

**Output.** `phase4_funding/tables/e5_disjoint.parquet` + `.csv`; `e5_overlap.csv`.

---

## 9. Phase 5 gate

**Locked rule.** Phase 5 starts if **at least one of the 12 `y_raw` within-regime funding contrasts passes BH within its 12-test family (`p_bh < 0.05`) and survives drop5 (`|t_drop5| > 1.96`)**, at any horizon and in either weighting. No bp threshold; no requirement that both weightings agree.

The gate does not apply to volatility. Volatility contrasts are reported and used as a risk overlay (position sizing / stop width) once a return rule is selected.

The gate sentence for the report:

> Phase 5 is unlocked by `<regime> × <funding>` at h = `<h>`, weighting = `<event|contract-day>`: `y_raw` contrast = `<bp>` (t = `<t>`, p_bh = `<p>`, t_drop5 = `<t5>`).

If no contrast passes, Phase 5 does not start; that is a valid Phase 4 conclusion.

Multiplicity note: the gate is per-family. There are 8 `y_raw` families (4 horizons × 2 weightings), each with its own BH 12; there is no correction across the 8 families. This is a deliberate, liberal choice (locked with the project lead) and must be disclosed with the gate sentence: the family, the number of tests, and the fact that the gate is not family-wise across horizons/weightings.

---

## 10. Out of scope

- Baselines: price alone, OI alone, funding alone, random timing — Phase 3 experiments 5–9 and 8.
- IC: the note's IC is conditional on a ranked score; the signal is a threshold label.
- Absolute bp/day funding scale: not in the note.
- β appendix (regime vs same-direction benchmark within funding): not in the note.
- 16-γ interaction ANOVA: requires a disjoint high/extreme partition and removes the main effects from the reported object; rejected.
- Threshold optimisation (p60/p70 grid): Phase 2 already did the threshold grid; p70 is frozen.
- Cross-exchange, Phase 5 backtest, R4 stress (Phase 3 experiment 14b), 4h/8h labels (deferred; 1h first).

---

## 11. Outputs

```
phase4_funding/
  GUIDANCE.md                     this file
  tables/
    e1_surface.parquet/.csv
    e2_contrasts.parquet/.csv
    e3_column_profile.parquet/.csv
    e4_hypothesis_map.csv
    e5_disjoint.parquet/.csv
    e5_overlap.csv
  figures/
    f01_return_heatmap.png        raw fwd and y_raw, 4 horizons × 4 regimes × 4 funding
    f02_vol_heatmap.png           rv mean, same layout
    f03_contrast_forest.png       12 contrasts per DV/horizon/weighting, with 95% CI
```

Figure rules: heatmaps show the estimate and mark cells whose `y_raw` contrast passes BH 12 + drop5; the forest plot shows the 12 contrasts with 95% CI, points filled when BH passes. No bar charts of levels.

---

## 12. Validation gates

Run these before anything is written up:

1. **n reconciliation.** E1 n at h=1 matches the sample-size audit: 255,857 rows; disjoint totals 93,489 / 123,907 / 18,834 / 19,627; contract-month totals 9,499 / 9,461 / 3,377 / 2,777; R1 × neutral 2,384; R1 × extreme 752; thinnest disjoint cell 584 (R3 × extreme).
2. **Raw return join.** For each hour, `fwd_h − y_raw` is constant across events (the market mean); max within-hour standard deviation < 1e-12. Also check the join covers all E1/E2 rows (no missing `fwd_h`).
3. **High-union identity.** E1 `high` mean = `w2 × high-only + w3 × extreme`, max abs difference < 1e-12, at every `(h, weighting, regime)`.
4. **Disjoint sums.** The 16 disjoint cells sum to the E1/E2 sample (n) at every `(h, weighting)`.
5. **Contrast identity.** C2(r) = `w2 × (high-only − neutral) + w3 × (extreme − neutral)`; max abs difference < 1e-12.
6. **BH families.** Exactly 12 tests per `(dv, h, weighting)` for `y_raw` and `lrv`; `p_bh` monotone; `fwd` has no `p_bh`.
7. **Weighting.** Event and contract-day tables have the same cells and the same definitions; the contract-day high-union weights use contract-day-cell counts, not event counts.
8. **Degeneracy flags.** The p75==p90 share recomputed on the E1/E2 sample matches 56.96% (rows) and 48.9% (contract-months); the high-union n uses unique counts, not sums.
9. **Sample gates.** No cell below 400 contract-months at h=1; flag if any horizon/weighting produces one.
10. **No stale 16-γ artefacts.** The old `l1_cellmeans` / `l2_interactions` are not used anywhere in E1–E5.

---

## 13. Checklist

- [ ] Join `fwd_h` from `forward/freq=1h`; validate the within-hour identity.
- [ ] Build E1 surface: 4 horizons × 2 weightings × {raw fwd, y_raw, rv} with mean/median/CI/n.
- [ ] Build E5 disjoint cells and overlap stats; verify the high-union identity.
- [ ] Build E2 contrasts: 12 per (dv, h, weighting); `y_raw` and `lrv` BH 12; `fwd` descriptive; drop5.
- [ ] Build E3 column profile.
- [ ] Build E4 hypothesis map (six anchors + exploratory cells).
- [ ] Produce the three figures.
- [ ] Run the validation gates.
- [ ] Write the Phase 5 gate sentence (or the explicit "gate not met").
- [ ] Update the table notes with the degeneracy disclosure.
