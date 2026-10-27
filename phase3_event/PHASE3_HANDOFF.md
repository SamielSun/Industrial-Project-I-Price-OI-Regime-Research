# PHASE 3 HANDOFF — Event Study

**This document is the complete starting point for Phase 3.** It assumes no memory of
earlier sessions. Read it top to bottom before touching any data.

Project: *Price and Open-Interest Regimes in Crypto Perpetual Futures: Do Joint Positioning
States Contain Predictive Information Beyond Price Alone?*
Sponsor: Theo Quant Limited · Industrial supervisor: Mr. Jackson Wong · Academic supervisor: Prof. WU Xixin
Student: SUN Yusu (1155267751) · FTEC5910

---

## 0. Status

| Phase | Deliverable | State |
|---|---|---|
| 1 | D1 hourly panel + PIT universe | **closed** — `data/02_features/`, `data/03_reference/`, `data/04_qa/` |
| 2 | D2 regime + funding labels | **closed** — `data/05_regime/` (241 files, checksums verified) |
| **3** | **Event study** | **not started — this is you** |
| 4 | Funding interaction (4x4 grid) | blocked on 3 and on a supervisor decision (see section 7.2) |
| 5 | Strategy test + dashboard | blocked on 3 and 4 |

Working rules the user has set, and which still apply: work one step at a time and do not
start step N+1 before step N produces a result; exploratory scratch files are deleted
immediately after use; every number quoted in a document must come from an output file, never
from memory; no defensive code that anticipates failures that have not occurred.

---

## 1. What Phase 3 has to deliver

Straight from the project note (sections 8, 9 and 10-Phase 3):

**Outputs required**
- a forward-return table
- event-study plots
- regime comparison charts

**Measures required, per regime**

| Measure | Reference |
|---|---|
| **Forward return** at 1h, 4h, 8h, 24h — mean *and* median | 8A, 10 |
| **Forward realized volatility** | 8B |
| **Hit rate** | 10 |
| **Continuation / reversal / no-edge** probabilities | 8C, 10 |
| **MFE, MAE, drawdown** over the holding window | 8D |
| **Comparison against four baselines** | 9 |

**The four baselines (section 9)** — the framework only adds value if it beats these:

1. price momentum alone
2. OI change alone
3. funding state alone
4. random event timing (matched count, fixed seed)

**Definition of the three-way split (section 8C)**

> Continuation = future return *follows* the original move; reversal = it moves *against*;
> no edge = no clear relationship.

The natural operationalisation, and the one to implement unless the user says otherwise:
compare the sign of the forward return at horizon h with the sign of the price_change of the
event itself. MFE / MAE / drawdown then quantify the path, not just the endpoint.
---

## 2. Inputs

### 2.1 Labels — `data/05_regime/regime_labels/`

```
freq=1h/  year=<Y>/  chunk=<Y>-<M>.parquet      7,252,717 rows   235.5 MB
freq=4h/                                       1,813,036 rows    66.1 MB
freq=8h/                                         906,426 rows    36.9 MB
freq=1d/                                         302,008 rows    15.8 MB
                                                10,274,187 rows, 228 chunks
```

Partitioned by `freq`, then `year`, then month. Read one frequency at a time; a month is
about 4 MB at 1h. `data/05_regime/data_dictionary.md` documents every table column.

**21 columns**, of which the ones Phase 3 uses:

| Column | Meaning |
|---|---|
| `symbol` | contract, e.g. BTCUSDT |
| `ts` | **bar start** |
| `ts_end` | `ts + 1h` = **the decision instant** |
| `freq` | 1h / 4h / 8h / 1d |
| `close` | close price **at `ts_end`** |
| `oi` | open interest at `ts_end` |
| `price_change` | `close(ts_end) / close(ts_end - fh) - 1` |
| `oi_change` | same shape on OI |
| `price_thr` / `oi_thr` | the trailing-90-day p70 thresholds in force at `ts_end` |
| `regime` | R1 / R2 / R3 / R4 / undefined |
| `excl_reason` | ok / warmup / span_gap / halt / no_oi / no_price |
| `funding_negative` ... `funding_extreme` | four booleans (see section 7) |
| `funding_p25` / `p75` / `p90` | the three quantiles in force |
| `mkt_vol_state` | low / mid / high / unknown |
| `in_universe` | whether the contract was in the PIT universe that month |

Regime rule: R1 price up + OI up, R2 price up + OI down, R3 price down + OI up, R4 price
down + OI down. All four conditions are strict, so `price_change == 0` or `oi_change == 0`
is `undefined`. `undefined` is **not a fifth regime** — it is the no-label class.

### 2.2 Panel — `data/02_features/features_1h/`

57 chunks, **7,253,002 rows x 19 columns**, 285 contracts, 2021-12 to 2026-08.

**The label table does not carry future prices.** It has `close` at the decision instant only.
To build forward returns you must join the panel:

```
panel row with ts == X          has close = the close of the hour ending at X + 1h

label row with ts_end == T      has close = the close of the hour ending at T
                                = panel.close[ ts == T - 1h ]

forward close at horizon h      = panel.close[ ts == T + h - 1h ]

so     fwd(h) = panel.close[ ts == T + h - 1h ] / panel.close[ ts == T - 1h ] - 1
             = panel.close[ ts == T + h - 1h ] / label.close[T] - 1
```

**Sanity check before trusting any of this:** take BTCUSDT over a few days and confirm that
`label.close[ts_end == T]` equals the panel's close for `ts == T - 1h`, **not** the panel's close
for `ts == T`. If it does not, the whole forward-return layer is shifted by one hour and every
number downstream is wrong.

Read the panel by month, index it by `(symbol, ts)`, and join. Do not assume rows are dense
in time: the panel is a grid, and missing hours exist as rows carrying `bar_missing`.

---

## 3. Numbers you must reproduce

These are the Phase 2 deliverables. If Phase 3 event counts do not match, stop — something
is being filtered differently.

| freq | valid observations | labelled | labelling rate |
|---|---|---|---|
| 1h | 7,214,627 | **923,235** | 12.80% |
| 4h | 1,801,687 | 227,107 | 12.60% |
| 8h | 899,477 | 112,292 | 12.48% |
| 1d | 298,202 | 37,585 | 12.60% |

**1h regime counts at p70**: R1 267,080 · R2 184,686 · R3 164,126 · R4 307,343.
**Composition of the labelled set** (1h): R1 28.93% · R2 20.00% · R3 17.78% · R4 33.29%.

---

## 4. Design decisions already made — do not re-open without the user

**Regime thresholds.** Per contract, **trailing rolling 90 calendar days**, quantile **p70**,
computed separately on `|price_change|` and `|oi_change|`, with a **30-day minimum history**
measured from the contract's first decision instant. Both axes must exceed their own threshold.

Why: the project note (line 87) says *"rolling 60th/70th percentile, or z-score based
thresholds"* — a rolling percentile is the note's own wording, and p70 is the stricter of the
two levels it offers. An earlier plan draft said "expanding window"; that was tested and
rejected because expanding windows produce a spurious declining labelling rate (10.92% down to
8.90% across 2022-2026, while a rolling window stays at 12.05-13.81%). **Do not reintroduce
expanding windows.**

**Why percentile rather than z-score.** Measured: the 70th percentile of `|change|` sits at
**0.62 standard deviations** at 1h, not the 1.04 a normal distribution would imply, rising to
0.75 at 1d. The data is strongly peaked, so a fixed z threshold does not mean what it looks
like — `|z| > 1.0` labels 5.4% of hours, not the ~32% a reader expects. A z rule matched to
the same labelling count is kept in the sensitivity table as a cross-check only.

**Change window N = 1 bar.** One bar at the label's own frequency: 1h uses 1h, 4h uses 4h.
That is what makes the four frequencies a hierarchy of horizons rather than four arbitrary
cut-offs.

**Span rule.** A labelled observation needs `fh * N + 1` consecutive 1h rows all valid
(2 / 5 / 9 / 25 for the four frequencies). Costs 0.034% of the 1h panel and unifies the halt
treatment across frequencies.

**`excl_reason` priority.** own failure (`no_price` / `halt` / `no_oi`) then `span_gap` then
`warmup` then `ok`. Mutually exclusive.

**Market condition.** `mkt_vol_state` is a **grouping variable only — it filters nothing**.
Recipe: `bar_range = (high - low) / close`, taken as the cross-sectional median across the
current month's universe members, then a 24h mean (minimum 12 periods), then terciles of that
smoothed series over a trailing 8,760h window, with a 30-day minimum history. `unknown` covers
the first three months (2021-12 to 2022-03, the series does not exist yet) plus one hour on
2024-10-28 where all 50 members had zero quote volume.

**First bucket.** The first decision instant of every (contract, frequency) is dropped
entirely; its right-edge values are still used by later windows. Only 42 of 285 first rows
land on a 4h boundary and 13 on an 8h boundary, so the loss is tiny.

---

## 5. Traps — each one has already cost a debugging session

1. **`ts` is the bar start; `ts_end` is the decision instant.** The label table's change and
   threshold columns are stamped at `ts_end`. Only `funding_rate` in the panel is aligned to
   `ts`. Mixing the two silently produces one-hour-late labels.

2. **Events are extremely concentrated in time.** Within any given hour almost all contracts
   move the same way, so observations are **not independent**. Standard errors must be clustered
   by calendar time, and the 24h forward windows overlap heavily. Treating 923,235 events as
   923,235 independent draws produces t-statistics that are wrong by an order of magnitude.

3. **`undefined` is not a control group.** It is 87% of valid rows and contains three very
   different things: genuinely quiet hours, warm-up, and data gaps. If you need a benchmark,
   use the `ok` subset of `undefined` explicitly, or the random-timing baseline from section 9.

4. **The panel is a grid, not an observation list.** Missing hours are rows with
   `bar_missing = True`. A forward return that silently crosses a halt is wrong; check
   `bar_missing` along the forward path.

5. **`in_universe` is evaluated at `ts_end`**, and the universe starts in 2022-03. Rows before
   that exist but belong to no universe. Decide explicitly whether Phase 3 restricts to
   `in_universe` — the Phase 2 tables do not filter on it, but a tradable-signal study probably should.

6. **Funding is a step function** — see section 7. It is the last *settled* rate, not the
   rate currently being predicted.

---

## 6. What to build (suggested order)

1. **Forward panel builder.** For a given frequency, produce `fwd_1h / fwd_4h / fwd_8h /
   fwd_24h` plus forward realized volatility, and flag any horizon whose path crosses
   `bar_missing`. Verify against a hand-picked single contract over a few days before trusting it.
2. **Event-level table.** One row per labelled observation with its forward measures, the
   event's own sign, and the conditioning columns. This is the object every later table reads.
3. **Per-regime table.** Mean and median forward return, hit rate, volatility, continuation /
   reversal / no-edge share, MFE / MAE / drawdown, each with observation counts.
4. **Baselines.** The same measures for the four alternatives in section 9 of the note.
5. **Figures.** Event-study plots and regime comparison charts.

Before step 3, fix two definitions and write them down: the forward horizon grid (recommended:
the note's fixed calendar 1h / 4h / 8h / 24h for every label frequency) and the
continuation-versus-reversal rule (recommended: sign of the forward return against sign of the
event's price change, with MFE / MAE describing the path).

---

## 7. Things Phase 4 will need — do not lose them

### 7.1 Funding label definitions

| Column | Rule |
|---|---|
| `funding_negative` | `f <= p25` |
| `funding_neutral` | `p25 < f <= p75` |
| `funding_high` | `f > p75` |
| `funding_extreme` | `f > p90` |

`p25 / p75 / p90` are trailing 90-day quantiles of that contract's **settlement series** (not
the hourly series), with a 30-day minimum history. Between settlements the state is carried
forward unchanged, because the rate genuinely does not change between settlements. 96.83% of
1h label rows carry a funding state; the remainder are contracts without 30 days of history.

### 7.2 The four funding states are not a partition — open question for the supervisor

`extreme` is a **subset** of `high` by construction. Measured on the full 1h sample:

| | share of labelled rows |
|---|---|
| `funding_negative` | 46.00% |
| `funding_neutral` | 44.29% |
| `funding_high` (all) | 9.71% |
| of which also `extreme` | 4.65% |

The four columns sum to **104.65%**, not 100%. The shares are far from the nominal
25 / 50 / 25 / 10 because funding is concentrated on a few discrete values (58.6% of
settlements sit on two of them), so trailing percentiles frequently coincide:

| condition | share of 1h rows |
|---|---|
| `p25 == p75` (the neutral band vanishes) | 23.92% |
| `p75 == p90` (`high` and `extreme` identical) | 64.86% |
| any collapse | 72.22% |

Consequence: `funding_negative` is True for a **positive** rate in about 96% of its rows — it
means "bottom quartile", not "negative". The supervisor has been asked whether to keep the
overlapping definitions with a footnote or switch to a 4x3 partition with `extreme` as a
nested cut. **The answer is pending; do not build the 4x4 grid before it arrives.** The
quantile columns are stored, so either convention can be produced without recomputing labels.

### 7.3 Threshold sensitivity already exists

`data/05_regime/tables/threshold_sensitivity.parquet` — 68 rows x 20 columns: six percentile
levels (p55 to p80), six z-score rules matched to the same labelling counts, and five fixed-z
rules, at all four frequencies. Headline: moving from p55 to p80 cuts the sample three-fold
but moves the regime mix by at most **3.8 pp at 1h** and **11.8 pp at 1d**, and the drift is
always the same direction (R1 up, R2 and R3 down). Do not rebuild this.

---

## 8. Environment

- Python: `C:\miniconda\python.exe` (3.12.9), pandas 2.3.3, pyarrow 23.0.1, python-docx 1.2.0.
  **No scipy** — use `statistics.NormalDist` for normal-distribution work.
- Matplotlib figures must set `Microsoft YaHei` for CJK glyphs.
- The console is GBK. Any script printing non-GBK characters needs
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` at the top, or it dies on the
  first tick mark.
- `os.replace()` cannot move directories on Windows, even empty ones. Write a temp file and
  replace per file.
- Project root: `D:\CUHK Fintech\Industrial Programme I`.

---

## 9. Where things are

| What | Where |
|---|---|
| Phase 1 panel | `data/02_features/features_1h/` |
| PIT universe ledger | `data/03_reference/` |
| Phase 1 QA and dictionary | `data/04_qa/data_quality.md`, `data/04_qa/data_dictionary.md` |
| **Phase 2 labels** | `data/05_regime/regime_labels/` |
| Phase 2 tables | `data/05_regime/tables/` (5 tables, parquet + csv) |
| Phase 2 figures | `data/05_regime/figures/` (2 PNG) |
| Phase 2 column docs | `data/05_regime/data_dictionary.md` |
| Phase 2 scripts | `phase2_regime/regime_generator.py`, `phase2_regime/build_sensitivity.py` |
| How to rebuild Phase 2 | `phase2_regime/REPRODUCE.md` |
| Config | `config.py` (`Config` = Phase 1, `RegimeConfig` / `REGIME` = Phase 2) |
| Schema registry | `lib/schema.py` (self-test: 69 checks) |
| Project note (original brief) | `research_archive/build_scripts/_build/mentor_note_extracted.md` |
| Course submissions | `research_archive/submission/` |
| **Phase 3 workspace** | `phase3_event/` — currently empty apart from this file |

---

## 10. Deferred, not forgotten

- **Threshold robustness against forward returns.** Phase 2 tested robustness of the label
  *composition*, not of the *signal*. Whether the regime effect survives a threshold change is
  a Phase 3 question and belongs in its robustness section.
- **Liquidity floor.** Deferred to Phase 5, when transaction costs enter.
- **Liquidation data.** Never collected; the archive does not carry it. Any claim about
  liquidations must be phrased as an inference from OI and price, not as measured liquidations.
- **`project_resume_entry.md`** at the project root is a CV artefact, not project
  documentation, and its description of the threshold method is out of date.

---

## 11. First three actions

1. Read `data/05_regime/data_dictionary.md` and `phase2_regime/REPRODUCE.md`.
2. Count the labelled rows per frequency from the label tables and confirm the numbers in
   section 3. If they do not match, stop and investigate before building anything.
3. Build the forward panel for **1h only**, verify it on one contract over five days by hand,
   and only then scale to all frequencies.

