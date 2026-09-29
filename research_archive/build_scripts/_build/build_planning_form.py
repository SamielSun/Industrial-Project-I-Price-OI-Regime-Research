# -*- coding: utf-8 -*-
"""Build Part 2 of the FTEC5910 planning submission: the planning form,
filled in on the official template layout (task / midterm / final)."""
import sys
sys.path.insert(0, r"D:\Industrial Programme I\_build")
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.enum.section import WD_ORIENT  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402
from docx_kit import (new_doc, para, table, caption, shade, set_cell, INK,
                      GREY, ACCENT, HDR_FILL)  # noqa: E402

OUT = r"D:\Industrial Programme I\FTEC5910-20_Industrial_Project_Planning_Form_SUNYusu_FILLED.docx"

doc = new_doc(margin_cm=1.8, body_pt=10)
sec = doc.sections[0]
sec.orientation = WD_ORIENT.LANDSCAPE
sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
sec.left_margin = sec.right_margin = Cm(1.8)

C = WD_ALIGN_PARAGRAPH.CENTER

t = doc.add_table(rows=1, cols=1)
t.style = "Table Grid"
set_cell(t.rows[0].cells[0],
         "FinTech Industrial Project Planning Form", bold=True, size=13,
         align=C)

for label, value in [
    ("Student Name & ID:", "SUN Yusu (孙宇粟)   —   1155267751"),
    ("Project title:", "Price and Open-Interest Regimes in Crypto Perpetual Futures: Do Joint "
                       "Price–Positioning States Predict Continuation, Reversal and Crowding Risk?"),
    ("Sponsoring Organisation:", "Theo Quant Limited"),
    ("Industrial Supervisor:", "Mr. Jackson Wong, Founding Partner, Theo Quant Limited"),
    ("Academic Supervisor:", "Prof. WU Xixin, Department of Systems Engineering and Engineering "
                             "Management, CUHK"),
]:
    p = doc.add_paragraph()
    r = p.add_run(label + "  ")
    r.bold = True
    r.font.size = Pt(10)
    r2 = p.add_run(value)
    r2.font.size = Pt(10)
    p.paragraph_format.space_after = Pt(2)

para(doc, "Instructions: This form is to specify the tasks the student plans to undertake for the FinTech "
          "Project at the beginning of a semester. Please clearly specify the nature of the task and the "
          "expected achievements up to the midterm and the final.",
     size=8.5, italic=True, color=GREY, space_after=6)

para(doc, "Scope of this form: it covers Term 1 (FTEC5910) only. The tasks below are the five phases of "
          "the industrial supervisor's First Test Plan, plus Phase 6, which is the reporting and demo work "
          "that produces D5 and D6; they are listed in dependency order, and each phase's output is the "
          "next phase's input, so the midterm column is a verifiable state rather than a progress "
          "percentage. Deliverable identifiers D1–D6 are those of the idea note and are used consistently "
          "in Part 1 of the submission.",
     size=8.5, color=GREY, space_after=6)

HEAD = ["Task", "Expected achievements by the midterm (23 Oct 2026)",
        "Expected achievements by the final (27 Nov 2026)"]

ROWS = [
    ["Phase 1 — Data collection\n(archive acquisition, verification, storage, coverage)",
     "A working and verified path to the Binance public archive (direct or via a named proxy/cloud host), "
     "demonstrated at the meeting on 9 October; the reference pair BTCUSDT/ETHUSDT and the full 30–50 "
     "contract USDT-margined universe downloaded, checksum-verified and stored in columnar form; hourly "
     "klines, positioning (open interest) metrics and the funding archive ingested;\n"
     "D1 accepted: data dictionary, coverage and gap matrix by symbol and by month, and the measured "
     "history depth of the positioning archive per symbol, which fixes the study's start date.",
     "The pipeline is reproducible from raw archives by one documented command, with checksums re-verified "
     "and the ingest re-runnable after a data refresh; per-symbol coverage and gap reports regenerated and "
     "frozen for the final report;\n"
     "D1 final: frozen schema and data dictionary, plus a short note recording every data limitation "
     "(short OI history, symbol-level gaps, timestamp-unit changes) and its effect on the sample."],
    ["Phase 2 — Regime labelling inputs\n(point-in-time universe, OI-to-bar alignment, funding "
     "attachment, return panel)",
     "A point-in-time universe ledger built from archive file listings, listing exactly which contracts "
     "were eligible on each date, cross-checked against observed first-trade dates; a documented OI-to-bar "
     "alignment rule with a per-observation data-confidence flag; funding attached to the settlement that "
     "actually charged it, respecting the archived funding interval;\n"
     "the hourly analysis panel with forward returns and realized volatility, and a reported exclusion "
     "rate by symbol and month.",
     "The aligned panel extended to all pre-registered horizons (1h, 4h, 8h, 24h) and to the 4h/8h "
     "aggregations; robustness of the alignment rule quantified as the number of regime labels that flip "
     "under the alternative rule; survivor-only sample retained as a comparison sample so that the size of "
     "any survivorship effect can be stated in the report."],
    ["Phase 3 — Regime labelling and event study\n(four-state classification, threshold sensitivity, "
     "forward outcomes)",
     "D2 accepted: four-regime classifier (price up/down × OI up/down) at hourly frequency with an "
     "explicit undefined class, thresholds taken from trailing expanding-window quantiles so that no label "
     "uses future information;\n"
     "regime frequency tables by asset, by month and by market condition; a threshold sensitivity table "
     "showing that the conclusion does not depend on one threshold choice. No research result is reported "
     "before D1 and D2 are accepted.",
     "D3 complete: for every regime at every pre-registered horizon, forward return (mean and median), hit "
     "rate, post-event realized volatility, reversal probability, continuation probability and maximum "
     "adverse excursion, each reported with intervals and observation counts; event-study plots and regime "
     "comparison charts regenerated by one command from the frozen panel."],
    ["Phase 4 — Funding interaction\n(4 × 4 grid with multiplicity control)",
     "The funding-state classifier (trailing quantile buckets at the 25th, 75th and 90th percentiles, "
     "computed point-in-time and separately for contracts on 4-hour and 8-hour funding schedules), with "
     "the 4-hour cohort reported separately rather than pooled; the first four cells of the 4 × 4 grid "
     "computed as a pipeline check.",
     "D4 (first part) complete: the full 4 × 4 regime-by-funding grid with forward return and forward "
     "volatility per cell, cell counts and intervals, reported with a false-discovery-rate correction "
     "applied to the pre-declared multiplicity family; corrected and uncorrected results shown side by "
     "side, and inference repeated with calendar-time and asset-clustered standard errors so that the "
     "effect of event clustering is visible."],
    ["Phase 5 — Simple strategy test and cost sensitivity\n(conditional on Phase 3 showing signal value)",
     "The cost model specified in Appendix B of Part 1 reviewed and its inputs sourced (published fee "
     "schedule applied by date, perpetual quoted spread from archived depth where available, funding cash "
     "flows from the archive); the four baselines (price momentum alone, OI change alone, funding alone, "
     "random event timing) implemented and verified to run on the identical sample, calendar and cost "
     "basis as the regime signal.",
     "If Phase 3 showed signal value: one or two pre-registered rules tested as a costed exploratory "
     "backtest against all four baselines, with the break-even cost at which the verdict changes sign "
     "reported explicitly, and an explicit statement that this is not a production strategy.\n"
     "If Phase 3 showed no value: a cost-sensitivity study of the null result in its place, so that the "
     "phase still produces a priced statement rather than nothing. Either outcome is entered in the "
     "negative-result ledger with the specification that produced it."],
    ["Phase 6 — Reporting, dashboard and presentation",
     "Dashboard skeleton: the pipeline writes a daily regime snapshot for the universe, and the reference "
     "pair is displayed end-to-end for one date as a pipeline check (the dashboard as a whole sits in the "
     "“if time remains” tier and is the first item dropped if the midterm gate is missed).",
     "D5: a current-regime view across the liquid universe — fresh long buildup, fresh short buildup, "
     "short covering and deleveraging candidates, plus a funding-adjusted crowding view — regenerating "
     "from the pipeline without manual steps.\n"
     "D6: final report and the 30-minute presentation answering whether price plus open interest improves "
     "the understanding of short-term perpetual behaviour relative to price alone, including the negative "
     "findings, the pre-registered specification sheet, and the section that maps the work to the course "
     "learning outcomes."],
]

t = doc.add_table(rows=1, cols=3)
t.style = "Table Grid"
for i, h in enumerate(HEAD):
    set_cell(t.rows[0].cells[i], h, bold=True, size=9.5)
    shade(t.rows[0].cells[i])
for row in ROWS:
    cells = t.add_row().cells
    for i, v in enumerate(row):
        set_cell(cells[i], v, size=8.5)
for r in t.rows:
    r.cells[0].width = Cm(5.4)
    r.cells[1].width = Cm(10.3)
    r.cells[2].width = Cm(10.3)

para(doc, "Scope and resource note. The six phases above are budgeted at approximately 150–180 "
          "student-hours over the nine weeks from 23 September to 27 November 2026, at roughly 20 hours "
          "per week, with a must-close total of about 120 hours and a deliberate buffer for the data-access "
          "and data-quality work described in the risk register of Part 1 (risks R1 and R2). If the "
          "midterm gate on 23 October is not met, the reduction order is fixed in advance and is reported "
          "at the biweekly meeting: the dashboard is dropped first, then the 4h/8h robustness pass is "
          "reduced, and no research question is dropped.",
     size=8.5, color=GREY, space_after=4)

para(doc, "Progress reporting. Biweekly 30-minute progress meetings, jointly attended by the academic and "
          "industrial supervisors, are organised by the student; each meeting is used to demonstrate a "
          "phase output rather than to describe activity, and the midterm and final progress check forms "
          "report completion against the phase-level achievements in this form.",
     size=8.5, color=GREY, space_after=10)

para(doc, "Acknowledgement of AI tool use: generative AI tools were used, with explicit acknowledgement, to "
          "help structure this form and to check consistency of dates, deliverable identifiers and "
          "cross-references with Part 1. The tasks, scope decisions and achievement criteria are the "
          "student's own.",
     size=8, italic=True, color=GREY)

doc.save(OUT)
print("saved:", OUT)
