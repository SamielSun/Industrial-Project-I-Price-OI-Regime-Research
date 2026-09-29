# -*- coding: utf-8 -*-
"""Build Part 1 of the FTEC5910 planning submission: the project plan report.

Source of the research programme: Theo Quant idea note
"Price + Open Interest Regime Signal".
"""
import sys
sys.path.insert(0, r"D:\Industrial Programme I\_build")
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx_kit import (new_doc, para, rich, bullet, numbered, caption, table,
                      hrule, page_break, add_page_number_footer, INK, GREY,
                      ACCENT)  # noqa: E402

OUT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"
C = WD_ALIGN_PARAGRAPH.CENTER
J = WD_ALIGN_PARAGRAPH.JUSTIFY

doc = new_doc(margin_cm=2.2, body_pt=10.5)
add_page_number_footer(doc, "FTEC5910 Planning Submission — Part 1")

# =============================================================== cover page ===
para(doc, "", space_after=1)
para(doc, "THE CHINESE UNIVERSITY OF HONG KONG", size=13, bold=True, align=C,
     color=ACCENT, space_after=2)
para(doc, "Master of Science in FinTech Programme  |  Faculty of Engineering",
     size=10, align=C, color=GREY, space_after=1)
para(doc, "FTEC5910 Financial Technology Project I", size=10, align=C,
     color=GREY, space_after=18)
para(doc, "PLANNING SUBMISSION — PART 1: PROJECT PLAN REPORT", size=11,
     bold=True, align=C, space_after=22)
para(doc, "Price and Open-Interest Regimes in Crypto Perpetual Futures:",
     size=17, bold=True, align=C, space_after=2)
para(doc, "Do Joint Price–Positioning States Predict Continuation, Reversal and"
          " Crowding Risk?", size=13, align=C, color=ACCENT, space_after=24)

t = table(doc, ["Item", "Detail"], [
    ["Student", "SUN Yusu (孙宇粟)  |  Student ID: 1155267751  |  1155267751@link.cuhk.edu.cn"],
    ["Programme", "MSc in FinTech, Faculty of Engineering, CUHK"],
    ["Course", "FTEC5910 Financial Technology Project I (Term 1, 2026/27)"],
    ["Sponsoring organisation", "Theo Quant Limited"],
    ["Industrial supervisor", "Mr. Jackson Wong, Founding Partner, Theo Quant Limited"],
    ["Academic supervisor", "Prof. WU Xixin, Department of Systems Engineering and Engineering Management"],
    ["Project owner of record", "Submitted jointly with Part 2, the FinTech Industrial Project Planning Form"],
    ["Source of the research programme", "Idea note “Price + Open Interest Regime Signal”, issued by the industrial supervisor (Theo Quant Limited)"],
    ["Submission date", "25 September 2026"],
], widths=[4.2, 12.4], size=9)
caption(doc, "Cover particulars. The research programme documented in this report is the idea note issued "
             "by the industrial supervisor; this report turns it into a specified, bounded and testable plan.")

para(doc, "Acknowledgement of AI tool use: in line with the course policy (Approach 3 — use only with "
          "explicit acknowledgement), generative AI tools were used to help structure this document, to "
          "implement the diagram-generation and document-generation scripts, and to check the consistency "
          "of dates, deliverable identifiers and cross-references. All research design decisions, scope "
          "choices, data-access findings and conclusions are the student's own, and every factual claim "
          "about data availability in this report was verified directly rather than taken from a model "
          "output. No AI tool was used to generate results, and no result is reported in this plan.",
     size=9, italic=True, align=J, color=GREY)

page_break(doc)

# ========================================================== executive summary ===
doc.add_heading("Executive Summary", level=1)
para(doc, "Crypto perpetual futures carry two observable quantities that are cheap to obtain and rich in "
          "interpretation: the direction of price and the direction of open interest (OI). A price move "
          "accompanied by expanding open interest is a different market event from the same price move "
          "accompanied by contracting open interest, because the first requires new positions to be opened "
          "and the second can be produced by existing positions being closed. This project turns that "
          "intuition into a specified, reproducible event study on Binance USDⓈ-M perpetual futures and "
          "asks a deliberately falsifiable question: do price/OI regimes carry information about subsequent "
          "returns, volatility and reversal that price momentum alone does not?", align=J)
para(doc, "The project is a research framework, not a production strategy. Its output is a clean, "
          "documented, interpretable pipeline that classifies every asset-hour into one of four regimes "
          "(price up/down × OI up/down), stratifies those regimes by the prevailing funding state, and "
          "measures forward outcomes over four horizons. The framework is judged only against four "
          "explicit baselines — price momentum alone, OI change alone, funding alone, and random event "
          "timing — and the plan pre-commits to reporting a negative result if the joint regime "
          "classification does not beat them.", align=J)
para(doc, "Scope is bounded in three ways. First, one venue: Binance USDⓈ-M perpetuals, with BTCUSDT and "
          "ETHUSDT as the reference pair and the 30–50 most liquid USDT-margined contracts as a "
          "first-class cross-sectional universe. Second, one primary sampling frequency, one hour, with "
          "four- and eight-hour aggregation as robustness rather than as parallel studies. Third, four "
          "pre-registered horizons (1h, 4h, 8h, 24h) and one pre-registered multiplicity family, so that "
          "the 4 × 4 regime-by-funding grid is tested with an explicit multiple-testing correction instead "
          "of being mined.", align=J)
para(doc, "Three engineering commitments make the study credible rather than decorative, and each responds "
          "to a failure mode the data itself exhibits. The universe is reconstructed point-in-time from "
          "exchange archive file listings, so contracts that stopped trading cannot silently disappear "
          "from the sample. Open-interest snapshots are aligned to price bars with a documented and "
          "reported rule, and every affected asset-day carries a data-confidence flag, because OI and "
          "klines are stamped at different points inside the same hour. Funding is attached to the "
          "settlement that actually charged it, because the archived funding files carry the funding "
          "interval and the rate applied, and because 00/08/16 UTC are round hours whose effects must be "
          "separated from the regime effect.", align=J)
para(doc, "Two facts about the working environment are stated at the outset because they shape the "
          "timeline. The Binance public archive host was not reachable from the student's current network "
          "during preparation of this plan; this is treated as a Phase 1 deliverable-level risk with a "
          "named mitigation rather than an assumption. And the REST endpoint that serves historical open "
          "interest exposes only a short recent window, so the study is built on the downloadable archive "
          "files; the archive's OI history therefore defines the usable sample, which is shorter than the "
          "price history and must be measured, not assumed.", align=J)
para(doc, "The work is budgeted at approximately 150–180 student-hours across the eight weeks from 25 "
          "September to 27 November 2026, against six deliverables (D1–D6) inherited from the idea note "
          "and re-specified here with acceptance criteria. A single midterm gate governs scope: if the "
          "data layer and the classifier are not demonstrably complete by 23 October, the dashboard and "
          "the costed prototype are reduced before any research question is dropped, and the reduction is "
          "reported at the biweekly meeting rather than absorbed silently.", align=J)

page_break(doc)

# ================================================================== contents ===
doc.add_heading("Table of Contents", level=1)
for line, lvl in [
    ("1.  Project Goals", 0),
    ("1.1  Overall goal      1.2  Research questions      1.3  Success criteria and what “done” means", 1),
    ("1.4  Term 1 scope      1.5  Term 2 outlook      1.6  Learning objectives addressed", 1),
    ("2.  Significance of the Project", 0),
    ("2.1  Significance to the sponsoring organisation      2.2  Significance to the field", 1),
    ("2.3  Significance to the student's development", 1),
    ("3.  Problem Statement", 0),
    ("3.1  The data is not what the signal assumes      3.2  The measurement problem", 1),
    ("3.3  The inference problem      3.4  Why this is worth doing on one venue first", 1),
    ("4.  Proposed Solutions and Deliverables", 0),
    ("4.1  Design principles      4.2  Deliverables D1–D6      4.3  The five-phase execution plan", 1),
    ("4.4  Specification fixed in advance      4.5  Scope tiers and budget", 1),
    ("4.6  Explicitly out of scope in Term 1", 1),
    ("5.  Proposed Timeline", 0),
    ("5.1  Term 1 milestones      5.2  The two-term arc      5.3  Risk register", 1),
    ("Appendix A — Data sources, endpoints and access status", 0),
    ("Appendix B — Cost model applied to the Phase 5 test", 0),
    ("Appendix C — Pre-registered specification sheet", 0),
    ("Appendix D — Alignment with the course outline and the company brief", 0),
]:
    p = para(doc, line, size=10 if lvl == 0 else 9,
             bold=(lvl == 0), color=ACCENT if lvl == 0 else GREY,
             space_after=3 if lvl == 0 else 1)
    if lvl:
        p.paragraph_format.left_indent = 457200

page_break(doc)

# ================================================================== section 1 ===
doc.add_heading("1.  Project Goals", level=1)

doc.add_heading("1.1  Overall goal", level=2)
para(doc, "The goal is to build a public-data event study that classifies crypto perpetual futures moves "
          "into price/open-interest regimes, and to test whether those regimes predict short-horizon "
          "continuation, reversal, volatility or crowding risk better than price momentum alone. The "
          "project is explicitly not intended to produce a production trading strategy in Term 1. Its "
          "intended output is a clean, interpretable and reusable research framework, together with an "
          "honest verdict on whether the joint price/OI state carries incremental information.", align=J)
para(doc, "The framing matters for how the work is judged. The central hypothesis is that a price move "
          "accompanied by a meaningful open-interest change contains more information than the same price "
          "move alone, because the sign of the OI change distinguishes fresh positioning from position "
          "unwinding. The corresponding null hypothesis is equally explicit: price/OI regimes do not "
          "improve the prediction of future returns, volatility or reversal relative to simple price "
          "momentum. Under this framing a well-executed failure to reject the null is a result, not an "
          "accident, and the negative-result ledger is a deliverable rather than an appendix.", align=J)

doc.add_heading("1.2  Research questions", level=2)
para(doc, "The idea note specifies a hypothesis and a test plan; it does not specify research questions. "
          "Three are fixed here, in the order in which they can actually be answered, so that no question "
          "depends on a study that has not yet run.", align=J)
rich(doc, [("RQ1 (classification). ", {"bold": True}),
           ("Do the four price/OI regimes occur often enough, and differ enough in their forward "
            "outcomes, to be worth conditioning on? This is a measurement question answered with regime "
            "frequencies, forward-return distributions by regime, hit rates, post-event realized "
            "volatility, reversal and continuation probabilities, and maximum adverse excursion — before "
            "any trading rule is considered.", {})], align=J)
rich(doc, [("RQ2 (conditioning). ", {"bold": True}),
           ("Does the prevailing funding state change what a regime means? Each regime is split into four "
            "funding states (below the trailing 25th percentile, neutral, above the 75th, above the 90th), "
            "producing the 4 × 4 grid of the idea note, and the question is whether the forward outcomes "
            "differ across funding states within a regime.", {})], align=J)
rich(doc, [("RQ3 (verdict). ", {"bold": True}),
           ("Does the joint regime classification beat the four baselines — price momentum alone, OI "
            "change alone, funding alone, random event timing — and does anything survive a realistic, "
            "time-varying cost assumption? RQ3 carries the headline conclusion, and it is answered last "
            "because it consumes the outputs of RQ1 and RQ2.", {})], align=J)
para(doc, "The dependency structure is deliberate. RQ1 establishes whether the object of study exists in "
          "the data at usable frequency. RQ2 asks whether the conditioning variable from the idea note "
          "earns its place. RQ3 is the only question that speaks to economic value, and it is the only "
          "question that is allowed to depend on cost assumptions.", align=J)

doc.add_heading("1.3  Success criteria and what “done” means", level=2)
para(doc, "The project is complete when six conditions hold, each of which is checkable without "
          "reference to whether the signal works:", align=J)
numbered(doc, "the panel is reproducible from raw archive files by a single documented command, with "
              "checksums verified and a point-in-time universe ledger that lists, for every date, exactly "
              "which contracts were eligible;")
numbered(doc, "every asset-hour carries a regime label or an explicit exclusion reason, and the exclusion "
              "rate is reported by symbol and by month;")
numbered(doc, "the four forward-outcome families (return, volatility, reversal/continuation, path risk) "
              "are reported for every regime at every pre-registered horizon, with intervals rather than "
              "point estimates;")
numbered(doc, "the 4 × 4 regime-by-funding grid is reported with a multiple-testing correction applied to "
              "a pre-declared family;")
numbered(doc, "the four baselines are computed on the identical sample, calendar and cost basis as the "
              "regime signal, so the comparison cannot be won by a sample difference;")
numbered(doc, "the verdict, including a negative verdict, is recorded in the results ledger together with "
              "the specification that produced it.")

doc.add_heading("1.4  Term 1 scope", level=2)
para(doc, "Term 1 delivers the following, and only the following:", align=J)
bullet(doc, "on two tracks: hourly klines for the reference pair and the cross-sectional universe, and "
            "the metrics archive that carries open interest and related positioning series, plus the "
            "funding-rate archive. Storage is columnar, the schema is versioned, and the data dictionary "
            "is a deliverable in its own right.", bold_lead="Data platform: ")
bullet(doc, "the regime classifier (price/OI change over a fixed lookback, threshold logic, four-regime "
            "labelling) and the funding-state classifier, both pre-registered and both tested for "
            "threshold sensitivity rather than tuned.", bold_lead="Classifier: ")
bullet(doc, "the regime event study (RQ1), the funding interaction grid (RQ2), and the baseline and "
            "cost-sensitivity verdict (RQ3), with a documented negative-result ledger.",
       bold_lead="Research: ")
bullet(doc, "a current-regime dashboard, the Term 1 report and the end-of-term presentation.",
       bold_lead="Tooling and reporting: ")

doc.add_heading("1.5  Term 2 outlook", level=2)
para(doc, "Term 2 is expected to extend the same platform in three directions, listed here so that Term 1 "
          "design choices do not foreclose them: a second and third venue (OKX, Bybit) to test whether the "
          "regimes are a Binance artefact or a market-wide phenomenon; an intraday microstructure layer "
          "using trade-level signed flow, which the idea note lists only as optional; and a cross-sectional "
          "asset-pricing treatment of the regime signal with point-in-time universe control. None of these "
          "is attempted in Term 1.", align=J)

doc.add_heading("1.6  Learning objectives addressed", level=2)
para(doc, "The work is designed to satisfy the four stated course learning outcomes: analysing and solving "
          "a significant practical problem in financial technology (the information content of positioning "
          "data); carrying out basic project management (a gated eight-week plan with a midterm scope "
          "decision); giving a fluent technical presentation (biweekly 30-minute updates and a 30-minute "
          "final presentation); and writing a report that documents findings and deliverables, including "
          "the ones that failed.", align=J)

page_break(doc)

# ================================================================== section 2 ===
doc.add_heading("2.  Significance of the Project", level=1)

doc.add_heading("2.1  Significance to the sponsoring organisation (Theo Quant Limited)", level=2)
para(doc, "Theo Quant's project brief (#6, “Quantitative Research and Development for Algorithmic Trading "
          "Strategies in Digital Assets”) asks for research tools, analytical frameworks and data-driven "
          "insights, with practical and measurable outputs such as Python-based analysis, backtesting "
          "logic and data dashboards. This project responds with four things the company can use "
          "regardless of the sign of the result.", align=J)
bullet(doc, "a documented ingestion and alignment layer for Binance perpetual market data, including the "
            "open-interest alignment rule and a point-in-time universe ledger, which is the part of any "
            "positioning study that is repeatedly rebuilt and rarely documented.",
       bold_lead="Reusable data layer: ")
bullet(doc, "a four-state classifier that converts raw price and open-interest series into a small, "
            "interpretable set of market states, with an explicit confidence flag when the underlying OI "
            "data is thin.", bold_lead="Positioning framework: ")
bullet(doc, "a costed assessment of whether the states carry tradeable information. The company's interest "
            "is in what survives costs, so the Phase 5 test is costed even though the study is an event "
            "study; a signal that dies after costs is reported as such and is worth more to a trading desk "
            "than an uncosted positive.", bold_lead="Honest verdict: ")
bullet(doc, "a current-regime view across the liquid universe (fresh long buildup, fresh short buildup, "
            "short covering, deleveraging candidates, funding-adjusted crowding), designed to be readable "
            "in a daily workflow.", bold_lead="Operational dashboard: ")
para(doc, "No proprietary company data is required or requested, and every input is a free public archive, "
          "so all results are auditable by the company and by the academic supervisor from the same code "
          "and the same files.", align=J)

doc.add_heading("2.2  Significance to the field", level=2)
doc.add_heading("2.2.1  What is already established", level=3)
bullet(doc, "The no-arbitrage pricing of perpetual futures, the role of the funding mechanism as the "
            "device that tethers the perpetual to spot, and the trading-cost bounds within which the "
            "tether holds are settled (He, Manela, Ross & von Wachter, 2022). The funding rate is "
            "therefore understood as a price anchor by construction, not merely as a sentiment gauge.",
       bold_lead="Perpetual pricing. ")
bullet(doc, "Order-book imbalance has strong contemporaneous explanatory power for short-horizon price "
            "changes (Cont, Kukanov & Stoikov, 2014), and contemporaneous microstructure explanation is "
            "abundant in crypto while forward predictive power is scarce. This asymmetry is the reason any "
            "claimed predictive signal must be tested out-of-sample rather than asserted.",
       bold_lead="Microstructure explains the present. ")
bullet(doc, "Systematic work on funding rates as a return predictor exists in public, survivorship-aware "
            "form (the funding-rate alpha study, 2026, covering millions of settlements across venues) and "
            "can be used as a benchmark rather than duplicated.", bold_lead="Funding as a factor. ")
bullet(doc, "Clock effects are documented in this market: minute-boundary and settlement-boundary trading "
            "clustering has been measured on Binance, in spot more than in perpetuals (Shynkevich, 2026). "
            "Since the regimes in this study are sampled on the hour and funding settles at 00/08/16 UTC, "
            "this literature is a direct threat to naive inference and is treated as a control, not as "
            "background.", bold_lead="Round-hour clustering. ")

doc.add_heading("2.2.2  What remains unsettled, and where this project fits", level=3)
para(doc, "Open interest is widely used in practice as a crowding indicator, but the published evidence "
          "treats it in three unsatisfying ways. It is studied mostly in isolation (OI change as a factor, "
          "funding as a factor) rather than jointly; it is studied mostly on aggregate or retail-derived "
          "positioning data rather than on exchange-reported OI for a point-in-time universe of contracts; "
          "and the interaction with the funding state — the conditioning variable that the idea note puts "
          "at the centre — is usually asserted rather than measured.", align=J)
para(doc, "The joint state is exactly the object the idea note proposes, and it has a specific reason to "
          "be informative. Open interest increases only when positions are opened, whereas price can move "
          "with open interest falling when positions are closed. The four regimes are therefore not four "
          "labels on one variable; they are four distinct order-flow situations, and the idea note's "
          "economic readings (fresh long buildup, short covering, fresh short buildup, long unwind) are "
          "testable claims about which situation is in force.", align=J)

doc.add_heading("2.2.3  The specific contribution claimed", level=3)
para(doc, "The contribution is deliberately modest in kind and precise in scope. It is a measurement and "
          "validity contribution, not a new source of alpha:", align=J)
numbered(doc, "A joint price/OI regime classification for a liquid perpetual universe, with the alignment "
              "and universe-construction decisions documented rather than hidden, and with data-confidence "
              "flags propagated into every reported statistic.")
numbered(doc, "A funding-conditional version of that classification (the 4 × 4 grid), tested with an "
              "explicit multiple-testing correction, which converts a widely used practitioner heuristic "
              "into a measurable quantity.")
numbered(doc, "A separation of predictability from profitability on identical samples and identical "
              "costs, so that a finding of “the regime predicts returns but not net of costs” is "
              "reportable as a first-class outcome rather than as a caveat.")
numbered(doc, "A reproducible negative-result asset. Every input is a free public archive; the pipeline "
              "runs from raw files; and the rejected specifications are recorded alongside the accepted "
              "ones.")

page_break(doc)

# ================================================================== section 3 ===
doc.add_heading("3.  Problem Statement", level=1)
para(doc, "The idea note states the research question and the test plan. It does not state the three "
          "problems that determine whether the test is meaningful: the data does not have the properties "
          "the signal definition assumes; the quantities of interest are measured with different clocks; "
          "and a grid of regimes crossed with funding states across four horizons creates a multiplicity "
          "problem that will manufacture false discoveries unless it is handled before the results are "
          "seen. Each is stated below as a problem to be solved in the design, not as a risk to be "
          "monitored.", align=J)

doc.add_heading("3.1  The data is not what the signal definition assumes", level=2)
bullet(doc, "Open interest and price are stamped at different points inside the same sampling interval, "
            "and the archive's positioning series is published at a finer interval than the study's "
            "primary bars. The idea note defines oi_change as an OI ratio over a lookback window without "
            "saying which observation inside an hour is used, and different defensible choices produce "
            "different labels at the boundary. Left undocumented, this makes results irreproducible.",
       bold_lead="Alignment. ")
bullet(doc, "The set of contracts that trade today is not the set that traded in the past. Contracts are "
            "listed, and some stop trading. If the universe is taken as the current symbol list, the "
            "sample is survivorship-biased in a way that specifically favours the regimes associated with "
            "violent price moves, because those are the episodes after which weak contracts disappear.",
       bold_lead="Universe. ")
bullet(doc, "Historical open interest is served over REST only for a short recent window, so the usable "
            "history is whatever the downloadable archive contains. That boundary must be measured per "
            "symbol rather than assumed from the price history, and the study's effective start date is "
            "the maximum of those boundaries across the universe.", bold_lead="History depth. ")
bullet(doc, "The archive host was not reachable from the student's current network while this plan was "
            "prepared (verified 23 September 2026; see Appendix A). Accessibility is therefore a Phase 1 "
            "task with a named mitigation, not a background assumption.", bold_lead="Access. ")

doc.add_heading("3.2  The measurement problem", level=2)
para(doc, "A regime label is a threshold statement: price moved by more than X and open interest moved by "
          "more than Y. The idea note proposes starting thresholds at rolling 60th–70th percentiles or on "
          "a z-score basis, and then says the thresholds should be tested for robustness rather than "
          "optimized. That sentence contains the whole measurement problem. With two thresholds, a "
          "lookback length, four horizons and a 4 × 4 grid, the number of defensible specifications is "
          "large, and the maximum over specifications is an upward-biased estimate of the effect. The "
          "problem is solved by pre-registering a baseline specification, reporting a sensitivity surface "
          "around it, and treating the surface as the result rather than selecting its best point.", align=J)

doc.add_heading("3.3  The inference problem", level=2)
para(doc, "The headline table of the idea note has sixteen cells, and the study evaluates four horizons "
          "and four outcome families. Even if the null hypothesis is true everywhere, a search over that "
          "grid will produce apparently strong cells. Additionally, the events are clustered: regime "
          "episodes arrive in bursts during volatile periods, so observations are neither independent "
          "across time nor independent across assets in the same hour. Standard errors that ignore this "
          "will be too small. Both problems are addressed in the design by a pre-declared multiplicity "
          "family with an explicit correction, and by inference that respects the clustering structure "
          "(calendar-time and cross-sectional dependence), rather than by reporting uncorrected per-cell "
          "significance.", align=J)

doc.add_heading("3.4  Why this is worth doing on one venue first", level=2)
para(doc, "The obvious objection is that a single-venue study is a partial study. The plan accepts that "
          "boundary and makes it explicit: Binance USDⓈ-M is the venue with the deepest public archives "
          "for both price and positioning data, so it is the only venue on which the joint price/OI "
          "question can be answered end-to-end within one term at the required data quality. The "
          "cross-venue question — whether the regimes are a venue artefact — is stated as a Term 2 "
          "extension with the data layer designed to accommodate it. What is not acceptable is to widen "
          "the venue count in Term 1 at the cost of leaving the alignment, universe and multiplicity "
          "problems unsolved, because a multi-venue answer built on an unsolved alignment problem is not "
          "a stronger result.", align=J)

page_break(doc)

# ================================================================== section 4 ===
doc.add_heading("4.  Proposed Solutions and Deliverables", level=1)

doc.add_heading("4.1  Design principles", level=2)
para(doc, "Four principles govern every design decision below, and each exists because of a specific way "
          "this study can fail:", align=J)
bullet(doc, "One pipeline, one command. The study must be reproducible from raw archives; any figure in "
            "the final report must be regenerable without manual steps.", bold_lead="Reproducibility. ")
bullet(doc, "The baseline specification, the threshold family and the multiplicity family are fixed in "
            "Appendix C before any result is computed, and deviations are recorded as deviations.",
       bold_lead="Pre-registration. ")
bullet(doc, "Every statistic carries the fraction of the sample it rests on, and every OI-derived label "
            "carries a confidence flag. A regime that occurs mostly in low-confidence observations is "
            "reported as such rather than as a finding.", bold_lead="Data honesty. ")
bullet(doc, "The study is designed so that “no incremental information” and “information that does not "
            "survive costs” are reportable outcomes with the same standing as a positive result.",
       bold_lead="Negative results are results. ")

doc.add_heading("4.2  Deliverables D1–D6", level=2)
para(doc, "The idea note names six deliverables. They are adopted, and each is given acceptance criteria "
          "and the phase that produces it, so that progress at the midterm is a matter of record rather "
          "than of impression.", align=J)
table(doc, ["#", "Deliverable", "Acceptance criteria", "Phase"], [
    ["D1", "Clean data pipeline",
     "Hourly klines, positioning metrics (open interest), funding archive and mark/index data ingested "
     "for the reference pair and the cross-sectional universe; checksums verified; Parquet storage; "
     "versioned schema; point-in-time universe ledger; data dictionary; coverage and gap report per "
     "symbol and per month.", "1–2"],
    ["D2", "Price/OI regime classifier",
     "Change calculation over a fixed lookback, threshold logic at pre-registered quantiles, four-regime "
     "labels with an explicit undefined/insufficient-data class; threshold sensitivity table; regime "
     "frequency tables by asset, by month and by market condition.", "3"],
    ["D3", "Event study report",
     "Forward return (mean and median), hit rate, post-event realized volatility, reversal probability, "
     "continuation probability and maximum adverse excursion, for every regime at 1h / 4h / 8h / 24h, "
     "reported with intervals and observation counts.", "4"],
    ["D4", "Funding interaction and costed prototype",
     "4 × 4 regime-by-funding grid with forward return and volatility per cell under a declared "
     "multiplicity correction; one or two simple rules tested with a time-varying cost model against "
     "four baselines; results recorded in the ledger whether positive or negative.", "5"],
    ["D5", "Dashboard / visualisation",
     "Current regime by symbol; fresh long buildup, fresh short buildup and deleveraging candidates; "
     "funding-adjusted crowding view; regenerates from the pipeline without manual intervention.", "5–6"],
    ["D6", "Final report and presentation",
     "Term report and 30-minute presentation answering whether price + open interest improves the "
     "understanding of short-term perpetual behaviour relative to price alone, including the negative "
     "findings and the specification that produced each.", "6"],
], widths=[0.9, 3.5, 9.4, 1.5], size=8.5)
caption(doc, "Table 4.1 — Deliverables, acceptance criteria and producing phase. D1 and D2 are the midterm "
             "gate: no research result is reported before both are accepted.")

doc.add_heading("4.3  The five-phase execution plan", level=2)
para(doc, "The idea note's First Test Plan is adopted as the execution structure, with the following "
          "phase definitions and outputs. Each phase's output is the next phase's input, which is what "
          "makes the midterm gate checkable.", align=J)
table(doc, ["Phase", "Operations", "Output", "Checkpoint"], [
    ["1. Data collection",
     "Archive discovery per dataset and symbol; parallel download with checksums and resume; storage "
     "layout; ingest of hourly klines, positioning metrics, funding and mark/index",
     "Clean panel dataset, missing-data report, data dictionary, coverage matrix by symbol and month",
     "Network path to the archive demonstrated working (or mitigation in force)"],
    ["2. Regime labelling inputs",
     "Point-in-time universe ledger from archive listings; OI-to-bar alignment rule with confidence "
     "flagging; funding attached to the settlement that charged it; return and volatility computation",
     "Aligned analysis panel at hourly frequency; alignment and confidence report; eligible-sample "
     "definition",
     "Exclusion rate documented and accepted; no label depends on future information"],
    ["3. Event study",
     "Four-regime classification at 1h with 4h/8h aggregation; threshold sensitivity; forward outcomes "
     "at 1h/4h/8h/24h; reversal, continuation and path-risk statistics",
     "Forward-return tables, event-study plots, regime comparison charts, sensitivity surface",
     "Every regime has usable frequency and the sensitivity surface is reported rather than optimised"],
    ["4. Funding interaction",
     "Each regime split by four funding states; 4 × 4 grid with return and volatility per cell; "
     "multiplicity correction on the pre-declared family",
     "4 × 4 tables with cell counts, intervals and corrected significance",
     "Corrected results reported alongside uncorrected ones, with the difference visible"],
    ["5. Simple strategy test",
     "One or two pre-registered rules (for example continuation after price-up/OI-up in neutral funding; "
     "reversal after price-down/OI-down following deleveraging); time-varying cost model; four baselines",
     "Costed exploratory backtest, baseline comparison, negative-result ledger entry",
     "Only run after Phase 3 shows signal value; explicitly not a production strategy"],
], widths=[2.5, 5.0, 4.6, 4.5], size=8.5)
caption(doc, "Table 4.2 — The five phases. Phase 5 is conditional: if Phase 3 shows no value, Phase 5 is "
             "replaced by a cost-sensitivity study of the null result, which is why the cost model in "
             "Appendix B is specified before Phase 5 begins.")

doc.add_heading("4.4  Specification fixed in advance", level=2)
para(doc, "The following are fixed before any result is computed; the full sheet is Appendix C. They are "
          "listed here because a reader should be able to check the plan's discipline without reading the "
          "appendix.", align=J)
bullet(doc, "primary bars are 1 hour, UTC-stamped; 4h and 8h are aggregations of the same panel, not "
            "separate studies;", bold_lead="Frequency. ")
bullet(doc, "the lookback for price and OI change is the baseline value recorded in Appendix C, with "
            "alternatives reported only as sensitivity;", bold_lead="Lookback. ")
bullet(doc, "thresholds are trailing quantiles computed from expanding windows only, so that a label at "
            "time t uses no information from after t;", bold_lead="Thresholds. ")
bullet(doc, "four regimes, with an explicit fifth “undefined” class for observations failing the "
            "threshold or the data-confidence test;", bold_lead="Regimes. ")
bullet(doc, "funding states are trailing-quantile buckets at the 25th, 75th and 90th percentiles, "
            "computed point-in-time and separately for contracts on 8-hour and 4-hour schedules;",
       bold_lead="Funding states. ")
bullet(doc, "1h, 4h, 8h and 24h forward from the bar close, with the 8h horizon reported separately for "
            "settlement-window overlap;", bold_lead="Horizons. ")
bullet(doc, "the multiplicity family is the 16 cells of the 4 × 4 grid at the primary horizon, corrected "
            "with a false-discovery-rate procedure; the other horizon grids are reported as secondary and "
            "labelled as such;", bold_lead="Multiplicity. ")
bullet(doc, "inference uses calendar-time clustering and is repeated with asset-clustered standard "
            "errors, because events cluster in both dimensions.", bold_lead="Dependence. ")

doc.add_heading("4.5  Scope tiers and budget", level=2)
para(doc, "Scope control is the principal execution risk of a project with this much latitude. The scope "
          "is fixed in three tiers and enforced at every biweekly meeting.", align=J)
table(doc, ["Tier", "Content", "Budget"], [
    ["Must close (midterm gate)",
     "D1 data pipeline; D2 classifier; phase-2 alignment, universe ledger and confidence flagging. No "
     "research result is reported before this tier is accepted.", "≈ 46 h"],
    ["Must close (final)",
     "D3 event study; D4 funding interaction with costed prototype; D6 report and presentation.",
     "≈ 74 h"],
    ["If time remains",
     "D5 dashboard; extended 4h/8h robustness; per-year decomposition; cross-venue feasibility note for "
     "Term 2.", "≈ 36 h"],
    ["Deferred to Term 2",
     "Trade-level signed flow and order-flow imbalance; cross-venue regime comparison; cross-sectional "
     "factor treatment with point-in-time universe control.", "—"],
], widths=[3.6, 10.4, 2.0], size=9)
caption(doc, "Table 4.3 — Scope tiers. The must-close total is ≈ 120 h against an estimated 150–180 h "
             "available in the eight weeks to 27 November 2026, leaving a deliberate buffer for the "
             "network and data-quality work that cannot be scheduled away.")

doc.add_heading("4.6  Explicitly out of scope in Term 1", level=2)
para(doc, "Live or simulated order execution and broker integration; machine-learning directional models "
          "(the point of this study is interpretability, and a model that predicts without explaining "
          "would not answer the question); cross-exchange comparison; order-book reconstruction; "
          "liquidation-data confirmation of deleveraging regimes, which the idea note lists as optional "
          "and which is deferred rather than half-done; and any claim of production readiness for the "
          "Phase 5 rules.", align=J)

page_break(doc)

# ================================================================== section 5 ===
doc.add_heading("5.  Proposed Timeline", level=1)
para(doc, "The working window is the nine weeks from 23 September to 27 November 2026 (eight working "
          "weeks after the planning submission), with the planning submission on 25 September, the "
          "midterm on 23 October, and the final report on 27 November. "
          "The budget assumes roughly 20 hours per week, which is the binding resource; the plan is "
          "sized so that Phases 1–3 complete by the midterm and Phases 4–6 complete by the final "
          "submission, with one week of slack held inside Phase 6.", align=J)

doc.add_heading("5.1  Term 1 milestones", level=2)
table(doc, ["Dates", "Phase", "Work", "Gate / demonstration at the biweekly meeting"], [
    ["25 Sep (Fri)", "—", "Planning submission: this report and the planning form",
     "Plan frozen; specification sheet pre-registered with both supervisors"],
    ["26 Sep – 2 Oct", "Phase 1",
     "Establish a working path to the archive; download and checksum the reference pair; build the "
     "storage layout and ingest skeleton",
     "Demonstrate a verified download and a reproducible ingest command on BTCUSDT/ETHUSDT"],
    ["3 – 9 Oct", "Phase 1", "Scale ingestion to the full universe; coverage and gap report by symbol "
     "and month; begin the regression sample build",
     "Show the coverage matrix and the measured history depth of the positioning archive per symbol"],
    ["10 – 16 Oct", "Phase 2",
     "Point-in-time universe ledger from archive listings; OI-to-bar alignment rule; funding attached to "
     "settlements; return and volatility panel",
     "Show that the universe ledger changes over time and that no label uses future information; report "
     "the exclusion rate"],
    ["17 – 23 Oct", "Phase 3 (start)", "Regime labelling with threshold sensitivity",
     "Midterm submission: D1 and D2 accepted; regime frequency tables shown; scope decision recorded "
     "(Table 4.3)"],
    ["24 – 30 Oct", "Phase 3", "Event study at four horizons; volatility, reversal, continuation and "
     "path-risk statistics",
     "Forward-return tables with intervals and observation counts for every regime"],
    ["31 Oct – 6 Nov", "Phase 4", "4 × 4 funding interaction with multiplicity correction",
     "Corrected and uncorrected grids shown side by side; dependence-robust standard errors"],
    ["7 – 13 Nov", "Phase 5",
     "Costed prototype of one or two pre-registered rules against four baselines; negative-result ledger "
     "updated",
     "Baseline comparison on identical samples and cost basis; verdict stated explicitly"],
    ["14 – 20 Nov", "Phase 6", "Dashboard; report drafting; figure regeneration from the pipeline",
     "Draft report reviewed; every figure regenerated by one command"],
    ["21 – 27 Nov", "Phase 6", "Final report; rehearsal of the presentation",
     "Final submission on 27 November 2026; presentation deck complete"],
    ["Week of 30 Nov", "—", "Presentation to academic and industrial supervisors (30 minutes, 5 minutes "
     "Q&A)", "—"],
], widths=[2.3, 1.9, 6.0, 6.2], size=8.5)
caption(doc, "Table 5.1 — Term 1 timeline aligned to the course outline dates. The midterm gate is a scope "
             "decision point, not a progress report: if D1 and D2 are not accepted on 23 October, the "
             "dashboard is dropped first, then the 4h/8h robustness pass is reduced, and the meeting "
             "record states the reduction.")

doc.add_heading("5.2  The two-term arc", level=2)
para(doc, "Term 2 (FTEC5920) is expected to take the same platform across venues and into "
          "microstructure, under a new planning form due 22 January 2027. The Term 1 design keeps that "
          "option open by storing data at hourly frequency with a schema that accommodates trade-level "
          "extension, and by not baking venue-specific assumptions into the classifier.", align=J)

doc.add_heading("5.3  Risk register", level=2)
table(doc, ["#", "Risk", "L", "I", "Mitigation and trigger"], [
    ["R1", "The public archive host is unreachable from the student's network (observed on 23 September "
     "2026)", "High", "High",
     "Test direct and proxied access in the first week; if direct access fails, route through an "
     "institutional or cloud host; if neither works within three days, substitute the keyless REST "
     "endpoints for a shorter but complete recent window and record the shortened sample explicitly"],
    ["R2", "Positioning (open interest) history is materially shorter, or has larger gaps, than price "
     "history", "High", "High",
     "Measure the boundary per symbol in Phase 1 and set the study start to the maximum across the "
     "universe; report every result with the eligible sample stated; treat a short sample as a finding "
     "about data availability"],
    ["R3", "OI-to-bar alignment changes regime labels at the threshold boundary", "Medium", "Medium",
     "Fix one alignment rule in Appendix C, quantify label flips under the alternative rule as a "
     "robustness result, and carry a per-observation confidence flag into every table"],
    ["R4", "Survivorship or listing-date bias from using today's symbol list", "Medium", "High",
     "Build the universe ledger from archive file listings (point-in-time), verify against observed "
     "first-trade dates, and re-run the headline tables on the survivor-only sample to show the size of "
     "the difference"],
    ["R5", "Specification search across thresholds, lookbacks, horizons and the 4 × 4 grid", "High",
     "High", "Pre-register the baseline in Appendix C; report sensitivity surfaces rather than best "
     "cells; apply a false-discovery-rate correction to the pre-declared family"],
    ["R6", "Round-hour and settlement-window effects contaminate the hourly comparison", "Medium",
     "Medium", "Include hour-of-day controls, report the 8h horizon separately, and re-run headline "
     "results excluding bars adjacent to 00/08/16 UTC settlements"],
    ["R7", "Cost assumptions drive the Phase 5 verdict more than the signal does", "Medium", "High",
     "Use a time-varying cost model with a measured-spread input and a published-fee input, report both, "
     "and state the break-even cost at which the verdict flips"],
    ["R8", "Scope expansion (dashboard, extra venues, ML) consumes the research time", "Medium",
     "Medium", "Three-tier scope rule enforced at every biweekly meeting; dashboard is in the “if time "
     "remains” tier and is the first item dropped"],
], widths=[0.8, 5.2, 1.3, 1.0, 7.9], size=8.5)
caption(doc, "Table 5.2 — Risk register. L = likelihood, I = impact. R1 and R2 are the two risks that can "
             "change the timeline rather than the quality of the result; both are resolved in the first "
             "two weeks by measurement rather than by assumption.")

page_break(doc)

# ================================================================ appendices ===
doc.add_heading("Appendix A — Data sources, endpoints and access status", level=1)
para(doc, "All inputs are free public Binance data; no proprietary company data is used. The table records "
          "what the study needs, where it comes from, and the status of the access test performed while "
          "preparing this plan.", align=J)
table(doc, ["Data", "Source", "Use in the study", "Status at 23 September 2026"], [
    ["Klines (1h, 1d)", "Binance public archive (daily and monthly files, per symbol and interval)",
     "Price change, forward returns, realized volatility, momentum baseline",
     "Archive host not reachable from the current network; REST/WebSocket endpoints also unverified from "
     "this network. Phase 1 task R1"],
    ["Positioning metrics (open interest, and related published ratio series)",
     "Binance public archive, futures metrics files",
     "The OI leg of the regime classification; the primary object of study",
     "Same access constraint. The archive is the only source with usable history: the REST history "
     "endpoint returns a short recent window (community-reported limitation), so the archive defines the "
     "sample start"],
    ["Funding rate history", "Binance public archive, futures funding files",
     "Funding-state buckets; the conditioning variable of RQ2; funding baseline",
     "Same access constraint. Files carry the funding interval, which is required because not every "
     "contract settles every eight hours"],
    ["Mark / index price", "Binance public archive",
     "Consistency check on the perpetual price series used for returns",
     "Same access constraint"],
    ["Optional: liquidation data", "Public aggregator or exchange endpoint",
     "Event confirmation for deleveraging regimes", "Deferred; not required by any pre-registered test"],
], widths=[3.1, 4.4, 4.6, 4.6], size=8.5)
caption(doc, "Table A.1 — Data inventory and access status. The access test on 23 September 2026 exercised "
             "the archive host directly and through the local proxy ports commonly used on this machine; "
             "all attempts failed, so access is treated as a Phase 1 deliverable-level risk (R1) rather "
             "than as a settled precondition.")

doc.add_heading("Appendix B — Cost model applied to the Phase 5 test", level=1)
para(doc, "Phase 5 is the only part of the study that speaks to economic value, so its cost model is "
          "specified before the test rather than after the result. The model has four components and one "
          "explicit time-variation rule.", align=J)
table(doc, ["Component", "Measurement", "Treatment in the test"], [
    ["Fees", "Published Binance USDⓈ-M fee schedule, taker and maker, with any historical changes applied "
     "by date rather than using today's schedule",
     "Charged per side on notional; the test reports both a taker-only and a mixed assumption, because "
     "the answer depends on execution style"],
    ["Spread", "Quoted spread from archived depth where available for the perpetual leg; estimated from "
     "trade prices where it is not",
     "Charged on entry and exit; stored as a time series, not a single number per symbol"],
    ["Slippage / impact", "Not separately modelled in Term 1 (no order-book reconstruction)",
     "Disclosed as an omission; the costed result is therefore an upper bound on net performance and is "
     "labelled as such"],
    ["Funding cash flow", "Attached from the archive to the settlement that charged it",
     "Credited or debited settlement by settlement for any position held across 00/08/16 UTC"],
], widths=[3.0, 6.6, 7.1], size=8.5)
para(doc, "The time-variation rule is the substantive commitment. Cost conditions in this market are not "
          "stationary: the same signal evaluated with one cost assumption across a multi-year sample "
          "produces a verdict that is an artefact of the assumption. The test therefore uses a cost "
          "series that varies by date, reports the break-even cost at which the verdict changes sign, "
          "and states the period over which the cost input is considered reliable. If the cost input is "
          "only defensible for part of the sample, the costed result is reported for that part and "
          "labelled accordingly, rather than extrapolated across the whole history.", align=J)

doc.add_heading("Appendix C — Pre-registered specification sheet", level=1)
para(doc, "Fixed before any result is computed. Any later deviation is reported as a deviation in the "
          "final report.", align=J)
table(doc, ["Element", "Specification", "Why this form"], [
    ["Primary frequency", "1 hour bars, UTC", "Matches the idea note's preference and keeps the "
     "cross-sectional universe tractable"],
    ["Aggregation robustness", "4h and 8h built from the same hourly panel", "Avoids three parallel "
     "studies with three different data treatments"],
    ["Lookback for change", "Baseline recorded here and applied identically to price and OI; alternatives "
     "reported as sensitivity only", "A lookback that differs between the two legs would make the "
     "classification incoherent"],
    ["Thresholds", "Trailing expanding-window quantiles; baseline quantile pre-registered; the 60th–70th "
     "range of the idea note reported as a surface", "Expanding windows are the only form that keeps a "
     "label free of future information"],
    ["Regime set", "R1 price up / OI up; R2 price up / OI down; R3 price down / OI up; R4 price down / OI "
     "down; plus an explicit undefined class", "The fifth class prevents “no event” from being silently "
     "labelled as an event"],
    ["Funding states", "Trailing quantile buckets at 25 / 75 / 90; computed per contract and per funding "
     "interval", "Contracts on a 4-hour funding schedule must not be pooled with 8-hour contracts"],
    ["Horizons", "1h, 4h, 8h, 24h from bar close", "Covers the idea note's set; 8h is reported separately "
     "for settlement overlap"],
    ["Multiplicity family", "The 16 cells of the 4 × 4 grid at the primary horizon", "One declared family, "
     "one declared correction; secondary grids are labelled secondary"],
    ["Dependence", "Calendar-time clustering primary, asset clustering as robustness", "Events cluster in "
     "time and across assets in the same hour"],
    ["Confidence flag", "Each asset-hour is flagged when the OI observation is missing, stale or "
     "interpolated", "Allows every table to be re-reported on high-confidence observations only"],
], widths=[3.0, 6.4, 7.3], size=8.5)

doc.add_heading("Appendix D — Alignment with the course outline and the company brief", level=1)
table(doc, ["Requirement", "Where addressed"], [
    ["Project goal", "§1.1–§1.3: overall goal, three research questions, six completion conditions"],
    ["Significance of the project", "§2.1 company, §2.2 field with the claimed contribution, §2.3 student "
     "development"],
    ["Problem statement", "§3: data properties, measurement problem, inference problem, and the "
     "single-venue boundary"],
    ["Proposed solutions and deliverables", "§4: four design principles, D1–D6 with acceptance criteria, "
     "the five phases, the pre-registered specification, scope tiers, exclusions"],
    ["Proposed timeline", "§5: eleven dated milestones against the course dates, plus the risk register"],
    ["Part 2 planning form", "Submitted separately: five phase-level tasks with expected achievements at "
     "the midterm (23 October 2026) and at the final (27 November 2026)"],
    ["Company brief #6 mapping", "Research tools and analytical framework → D1, D2; data-driven insights "
     "→ D3, D4; practical measurable outputs (Python analysis, backtesting logic, dashboard) → D4, D5; "
     "strategy performance review under different market conditions → D3, D4"],
], widths=[4.6, 12.0], size=9)
caption(doc, "Table D.1 — Compliance map. The planning submission comprises this report (Part 1) and the "
             "FinTech Industrial Project Planning Form (Part 2).")

para(doc, "End of Part 1 planning report. Part 2 (FinTech Industrial Project Planning Form) is submitted "
          "as a separate file. Prepared by SUN Yusu, 23 September 2026, on the research programme issued "
          "by the industrial supervisor (Theo Quant Limited).", size=9, italic=True, color=GREY)

doc.save(OUT)
print("saved:", OUT)
