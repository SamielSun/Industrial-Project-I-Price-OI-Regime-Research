# -*- coding: utf-8 -*-
"""Fill the official FTEC5910 planning form from FTEC5910_PLAN.docx.

Rule enforced here: every word in the filled cells comes from the PLAN text
(the five-phase execution table, the deliverables table and the timeline
table). Nothing is added that the PLAN does not say.

Source mapping
  Task            <- 4.1 The five-phase execution plan (Phase column) + Operations
  by the midterm  <- 4.2 Deliverables acceptance criteria D1/D2 + 5 timeline Meeting 2
  by the final    <- 4.2 acceptance criteria D3/D4/D5/D6 + 5 timeline Meeting 3/4/final
"""
import copy
import shutil
import sys
from docx import Document
from docx.shared import Pt

TEMPLATE = r"D:\Industrial Programme I\_build\FORM_template.docx"
OUT = r"D:\Industrial Programme I\FTEC5910-20_Industrial_Project_Planning_Form_SUNYusu_FILLED.docx"
PLAN = r"D:\Industrial Programme I\_build\PLAN_latest.docx"

# ---------------------------------------------------------------- header -----
# all four values are copied verbatim from the PLAN cover lines
HDR = {
    "Student Name & ID:": "SUN Yusu (1155267751)",
    "Project title:": ("Price and Open-Interest Regimes in Crypto Perpetual Futures: Do Joint "
                       "Positioning States Contain Predictive Information Beyond Price Alone?"),
    "Sponsoring Organisation:": "Theo Quant Limited",
    "Industrial Supervisor:": "Mr. Jackson Wong",
}
# the template has no academic-supervisor line; the PLAN states one, so it is added
ACADEMIC = ("Academic Supervisor:", "Prof. WU Xixin")

# ------------------------------------------------------------------ rows -----
# Task text = phase name (4.1) + Operations (4.1), condensed only by reusing the
# PLAN's own clauses.  Midterm / final text = acceptance criteria (4.2) and the
# gates of the timeline (5), using the PLAN's own wording.
ROWS = [
    [
        "1. Data collection (Phase 1, 26 Sep – 6 Oct)\n"
        "Archive per dataset and symbol; collect hourly OHLCV, open interest, funding rates, volume "
        "and mark/index price if available, for Binance USDT-M perpetual futures. Universe: BTCUSDT "
        "and ETHUSDT plus the 30–50 most liquid USDT-margined perpetual contracts, excluding "
        "stablecoin, newly listed tokens with insufficient history, contracts whose open interest "
        "data is unreliable, and illiquid contracts where transaction costs dominate.",
        "Verified download, a one-command reproducible ingest, and the coverage/gap matrix by symbol "
        "and month; the measured history depth of the positioning archive fixes the study start date "
        "(Meeting 1, 9 Oct).\n"
        "D1 accepted (1-2): clean data pipeline — Binance public data pull (USDⓈ-M perpetual "
        "futures); hourly OHLCV, positioning metrics (open interest), funding archive and mark/index "
        "data; the universe above; Parquet storage; data dictionary; coverage and gap report per "
        "symbol and per month.",
        "Clean panel dataset, missing-data report and data dictionary (4.1, Phase 1 output).\n"
        "The point-in-time universe ledger and the coverage matrix by symbol and month.\n"
        "D1 carried to the final, with the pipeline re-run by one command for the final report.",
    ],
    [
        "2. Regime labelling inputs (Phase 2, 7 – 18 Oct)\n"
        "Compute price and open-interest change over a fixed lookback window N on the 1h, 4h and 8h "
        "series: price_change = close_t / close_(t-N) - 1 and oi_change = OI_t / OI_(t-N) - 1. Keep "
        "only meaningful moves using minimum thresholds, abs(price_change) > price_threshold and "
        "abs(oi_change) > oi_threshold, with the thresholds taken from expanding-window quantiles so "
        "that the label at t uses no information from after t. Classify each surviving observation "
        "into regime 1 (price up, OI up), regime 2 (price up, OI down), regime 3 (price down, OI up) "
        "or regime 4 (price down, OI down), and place observations that fail either threshold in an "
        "explicit undefined class rather than forcing them into a regime. Report a threshold "
        "sensitivity table rather than a single tuned value.",
        "Regime counts and frequency by asset and by market condition, the point-in-time ledger shown "
        "to change over time, and the threshold sensitivity table; D2 accepted (Meeting 2 and "
        "midterm submission, 23 Oct).\n"
        "D2 accepted (2): change calculation over a fixed lookback window N, threshold logic using "
        "expanding-window quantiles, and four-regime labels with an explicit undefined class; "
        "threshold sensitivity table across the 60th to 80th percentile range; four-regime label "
        "generator.\n"
        "D1 accepted (1-2).",
        "The share of observations in the undefined class.\n"
        "The four-regime label generator delivered and re-run for the final report; the threshold "
        "sensitivity table reproduced by one command.",
    ],
    [
        "3. Event study (Phase 3, 19 Oct – 6 Nov)\n"
        "For each regime, calculate average and median forward return, hit rate, volatility after "
        "event, and the probability of continuation / reversal / no edge, together with path risk "
        "(maximum favourable excursion, maximum adverse excursion and drawdown), at the 1h / 4h / 8h "
        "/ 24h horizons.",
        "The event study is underway: Phase 2 closed at the midterm submission (23 Oct) and the "
        "regime labelling that feeds it has been accepted; the event study itself is accepted at "
        "Meeting 3 (6 Nov).",
        "Forward-return tables with observation counts, the continuation / reversal / no edge split "
        "per regime, event-study plots and regime comparison charts, regenerated by one command "
        "(Meeting 3, 6 Nov).\n"
        "D3 accepted (3-4): forward return (mean and median), hit rate, post-event realized "
        "volatility, and the three-way split of continuation / reversal / no edge, for every regime "
        "at 1h / 4h / 8h / 24h; forward volatility; path risk: maximum favourable excursion, maximum "
        "adverse excursion and drawdown; price/OI signal × funding interaction.",
    ],
    [
        "4. Funding interaction (Phase 4, 19 Oct – 6 Nov)\n"
        "Split each regime by four funding states defined as non-overlapping quantile buckets: "
        "negative (0–25), neutral (25–75), high (75–90) and extreme (90–100), computed point-in-time "
        "per contract, and separately for contracts on 4-hour and 8-hour funding schedules.",
        "The funding split is set up — four non-overlapping quantile buckets computed point-in-time — "
        "and accepted together with Phase 3 at Meeting 3 (6 Nov).",
        "4 × 4 table of price/OI regimes against funding states with forward return and volatility "
        "per bucket, each cell reported with its observation count, accepted together with Phase 3 "
        "(Meeting 3, 6 Nov).\n"
        "D3 accepted (3-4), which includes the price/OI signal × funding interaction.",
    ],
    [
        "5. Simple strategy test, dashboard and consolidation (Phase 5, 7 – 27 Nov)\n"
        "Conduct the strategy test only after the event study shows signal value: continuation after "
        "Price Up + OI Up when funding is neutral or reversal after Price Down + OI Down after "
        "deleveraging, costed against the four baselines (price momentum alone, OI change alone, "
        "funding alone, random event timing). Build the dashboard; complete the negative-result "
        "ledger; regenerate every figure and finalise the report.",
        "Strategy rules tested with cost against the four baselines, with the negative-result ledger "
        "started (D4, 5).",
        "Dashboard delivered and every figure regenerated by one command, with the draft report "
        "reviewed (Meeting 4, 20 Nov).\n"
        "At the final submission: all five phases closed and the final report submitted.\n"
        "D4 accepted (5): one or two simple rules tested with cost against four baselines.\n"
        "D5 accepted (5): dashboard / visualization — current price/OI regime by coin; top coins with "
        "fresh long buildup; top coins with fresh short buildup; deleveraging candidates; "
        "funding-adjusted crowding view.\n"
        "D6 final: term report and 30-minute presentation answering whether joint price/open "
        "interest improves the understanding of short-term perpetual behavior compared with price "
        "alone; the end-of-term presentation (30 minutes, including 5 minutes for questions) in the "
        "week of 30 Nov.",
    ],
]


def fill_header(doc):
    mapping = dict(HDR)
    for p in doc.paragraphs:
        t = p.text.strip()
        if t in mapping:
            r = p.add_run(" " + mapping[t])
            r.font.size = Pt(12)
            mapping.pop(t)
    # academic supervisor: the template has no such line, but the PLAN cover
    # states one, so it is added right after the industrial-supervisor line
    labels = [p.text.strip() for p in doc.paragraphs]
    if not any(t.startswith(ACADEMIC[0]) for t in labels):
        for p in doc.paragraphs:
            if p.text.strip() == "Industrial Supervisor:":
                new_el = copy.deepcopy(p._p)
                p._p.addnext(new_el)
                from docx.text.paragraph import Paragraph
                np = Paragraph(new_el, p._parent)
                for r in list(np.runs):
                    r._r.getparent().remove(r._r)
                np.add_run(ACADEMIC[0])
                r = np.add_run(" " + ACADEMIC[1])
                r.font.size = Pt(12)
                break
    return mapping


def fill_table(doc):
    t = doc.tables[0]
    template = copy.deepcopy(t.rows[1]._tr)
    while len(t.rows) > 1:
        t._tbl.remove(t.rows[-1]._tr)
    for values in ROWS:
        t._tbl.append(copy.deepcopy(template))
        row = t.rows[-1]
        for cell, value in zip(row.cells, values):
            for extra in cell.paragraphs[1:]:
                extra._p.getparent().remove(extra._p)
            p = cell.paragraphs[0]
            for r in list(p.runs):
                r._r.getparent().remove(r._r)
            lines = value.split("\n")
            p.add_run(lines[0]).font.size = Pt(9)
            for line in lines[1:]:
                np = cell.add_paragraph()
                np.paragraph_format.space_after = Pt(1)
                np.add_run(line).font.size = Pt(9)


def main():
    shutil.copyfile(TEMPLATE, OUT)
    doc = Document(OUT)
    missing = fill_header(doc)
    fill_table(doc)
    doc.save(OUT)
    print("saved:", OUT)
    if missing:
        print("header labels not found:", list(missing))

    d = Document(OUT)
    print("\n--- header ---")
    for p in d.paragraphs:
        if p.text.strip():
            print("  ", p.text.strip()[:150])
    print("\n--- table ---")
    t = d.tables[0]
    print("rows:", len(t.rows), "cols:", len(t.columns))
    for ri, row in enumerate(t.rows):
        print(f"  [{ri}] {row.cells[0].text.strip()[:70]!r} | "
              f"{row.cells[1].text.strip()[:60]!r} | {row.cells[2].text.strip()[:60]!r}")


if __name__ == "__main__":
    main()
