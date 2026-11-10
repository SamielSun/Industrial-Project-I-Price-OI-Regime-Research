"""Build the Phase 1-3 record document (English) from the repo's own tables.

Run with the bundled python (python-docx 1.2.0):
    <runtime python> build_phase123_record.py
"""
from __future__ import annotations

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

OUT = r"D:\CUHK Fintech\Industrial Programme I\research_archive\submission\Phase1-3_Experiment_Record.docx"

LATIN = "Times New Roman"
EA = "\u5b8b\u4f53"          # SimSun
HEAD_LATIN = "Arial"
GREY = RGBColor(0x59, 0x59, 0x59)
LIGHT = RGBColor(0x80, 0x80, 0x80)

EM = "\u2014"                # em dash
DELTA = "\u0394"             # Delta
TIMES = "\u00d7"             # multiplication sign
MINUS = "\u2212"             # minus sign
APPROX = "\u2248"            # approx

doc = Document()


# --------------------------------------------------------------------------
# styles
# --------------------------------------------------------------------------
def _set_font(style_or_run, latin=LATIN, ea=EA):
    style_or_run.font.name = latin
    rpr = style_or_run.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    fonts.set(qn("w:ascii"), latin)
    fonts.set(qn("w:hAnsi"), latin)
    fonts.set(qn("w:eastAsia"), ea)


normal = doc.styles["Normal"]
_set_font(normal)
normal.font.size = Pt(10.5)
normal.paragraph_format.space_after = Pt(4)
normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
normal.paragraph_format.line_spacing = 1.18

for name, size, before, after in [("Heading 1", 16, 16, 8), ("Heading 2", 13, 12, 6), ("Heading 3", 11.5, 10, 4)]:
    st = doc.styles[name]
    _set_font(st, HEAD_LATIN, "\u9ed1\u4f53")
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0x1F, 0x33, 0x4E)
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = Cm(2.3)
sec.bottom_margin = Cm(2.2)


def _field(paragraph, instr: str):
    run = paragraph.add_run()
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = "1"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    run._r.append(f1); run._r.append(it); run._r.append(f2); run._r.append(t); run._r.append(f3)


footer_p = sec.footer.paragraphs[0]
footer_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
footer_run = footer_p.add_run("Phase 1" + MINUS + "3 Experiment Record  \u00b7  page ")
footer_run.font.size = Pt(8.5)
footer_run.font.color.rgb = LIGHT
_field(footer_p, "PAGE")
for r in footer_p.runs:
    r.font.size = Pt(8.5)
    r.font.color.rgb = LIGHT


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def h1(text, new_page=False):
    p = doc.add_heading(text, level=1)
    p.paragraph_format.space_before = Pt(22)
    p.paragraph_format.space_after = Pt(10)
    if new_page:
        p.paragraph_format.page_break_before = True
    pPr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "4"); bottom.set(qn("w:color"), "1F334E")
    borders.append(bottom)
    pPr.append(borders)
    return p


def h2(text):
    return doc.add_heading(text, level=2)


def h3(text):
    return doc.add_heading(text, level=3)


def body(text, indent=False, space_after=4):
    p = doc.add_paragraph(text)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(space_after)
    if indent:
        p.paragraph_format.first_line_indent = Cm(0.74)
    return p


def labelled(label, text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(label + "  ")
    r.bold = True
    p.add_run(text)
    return p


def numbered(items, space_after=3):
    for i, it in enumerate(items, 1):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.left_indent = Cm(0.75)
        p.paragraph_format.first_line_indent = Cm(-0.55)
        p.paragraph_format.space_after = Pt(space_after)
        if isinstance(it, tuple):
            lead, rest = it
            r = p.add_run(f"({i})  {lead}  ")
            r.bold = True
            p.add_run(rest)
        else:
            p.add_run(f"({i})  {it}")


def bullets(items, space_after=3):
    for it in items:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.paragraph_format.left_indent = Cm(0.75)
        p.paragraph_format.first_line_indent = Cm(-0.4)
        p.paragraph_format.space_after = Pt(space_after)
        if isinstance(it, tuple):
            lead, rest = it
            r = p.add_run("\u2022  " + lead + "  ")
            r.bold = True
            p.add_run(rest)
        else:
            p.add_run("\u2022  " + it)


def quote(text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.8)
    p.paragraph_format.right_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(text)
    r.italic = True
    r.font.color.rgb = GREY
    pPr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single"); left.set(qn("w:sz"), "12")
    left.set(qn("w:space"), "6"); left.set(qn("w:color"), "9DB2C6")
    borders.append(left)
    pPr.append(borders)
    return p


def boxed(text):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.right_indent = Cm(0.4)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(text)
    r.font.size = Pt(10)
    pPr = p._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "6")
        el.set(qn("w:space"), "6"); el.set(qn("w:color"), "C9D6E2")
        borders.append(el)
    pPr.append(borders)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), "F4F7FA")
    pPr.append(shd)
    return p


def table_caption(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(9.5)
    return p


def figure_caption(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(text)
    r.font.size = Pt(9)
    r.italic = True
    r.font.color.rgb = GREY
    return p


def paste_slot(what, size_hint=""):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(10)
    txt = f"[ paste {what} here" + (f" \u00b7 suggested size {size_hint}" if size_hint else "") + " ]"
    r = p.add_run(txt)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = LIGHT
    return p


def make_table(header, rows, widths=None, font=9, header_font=9):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(layout)
    hdr = t.rows[0].cells
    for i, htxt in enumerate(header):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run(htxt)
        r.bold = True
        r.font.size = Pt(header_font)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), "E8EEF4")
        hdr[i]._tc.get_or_add_tcPr().append(shd)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            p.paragraph_format.space_after = Pt(1)
            long_cell = len(str(val)) > 22
            p.alignment = (WD_ALIGN_PARAGRAPH.LEFT if (i == 0 or long_cell)
                           else WD_ALIGN_PARAGRAPH.CENTER)
            r = p.add_run(str(val))
            r.font.size = Pt(font)
    if widths:
        for i, w in enumerate(widths):
            for row in t.rows:
                row.cells[i].width = Cm(w)
    return t


def note(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(text)
    r.font.size = Pt(8.5)
    r.italic = True
    r.font.color.rgb = GREY
    return p


def experiment(code, title, sample, est, tstat, conclusion, figs=(), tabs=()):
    h3(f"{code}  {title}")
    labelled("Sample.", sample)
    labelled("Estimator and test.", est)
    labelled("t-statistic construction.", tstat)
    labelled("Conclusion.", conclusion)
    for cap, fname in figs:
        paste_slot("figure", "width 15 cm")
        figure_caption(f"{cap}   {EM}   source: data/06_event_study/figures/{fname}")
    for cap in tabs:
        table_caption(cap)
        paste_slot("table", "width 15 cm")
        note("")


# --------------------------------------------------------------------------
# cover
# --------------------------------------------------------------------------
title = doc.add_paragraph()
title.paragraph_format.space_before = Pt(90)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = title.add_run("Price + Open Interest Regime Signal")
r.font.size = Pt(26)
r.bold = True
r.font.color.rgb = RGBColor(0x1F, 0x33, 0x4E)

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("Phase 1" + MINUS + "3: data, labelling, experiments, conclusions and open questions")
r.font.size = Pt(13)
r.font.color.rgb = GREY

doc.add_paragraph()

info_rows = [
    ("Project", "Price + Open Interest Regime Signal (crypto USD-M perpetual futures)"),
    ("Sponsoring organisation", "Theo Quant"),
    ("Student", "SUN, Yusu"),
    ("Academic supervisor", "Prof. WU Xixin"),
    ("Industrial mentor", "Gordon"),
    ("Purpose", "Pre-reading for the consultation on experiment design and for the mid-term review"),
    ("Version / date", "v1.0  \u00b7  4 November 2026"),
    ("Code and data", "D:\\CUHK Fintech\\Industrial Programme I"),
]
t = doc.add_table(rows=0, cols=2)
t.alignment = WD_TABLE_ALIGNMENT.CENTER
try:
    t.style = doc.styles["Normal Table"]
except KeyError:
    pass
for k, v in info_rows:
    cells = t.add_row().cells
    cells[0].width, cells[1].width = Cm(4.6), Cm(11.4)
    p0 = cells[0].paragraphs[0]; p0.paragraph_format.space_after = Pt(2)
    r0 = p0.add_run(k); r0.bold = True; r0.font.size = Pt(9.5)
    p1 = cells[1].paragraphs[0]; p1.paragraph_format.space_after = Pt(2)
    r1 = p1.add_run(v); r1.font.size = Pt(9.5)

doc.add_paragraph()
abstract = doc.add_paragraph()
abstract.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
abstract.paragraph_format.left_indent = Cm(1.2)
abstract.paragraph_format.right_indent = Cm(1.2)
r = abstract.add_run(
    "This document records what was built and what was found in Phases 1 to 3, in enough detail "
    "that the experiments can be reviewed without reading the code. It follows the order of the "
    "Phase 3 deck: data, labels, experimental design, the sixteen experiments one by one, the "
    "conclusions, and four design questions that I would like a view on before the mid-term."
)
r.font.size = Pt(10)

doc.add_page_break()

# --------------------------------------------------------------------------
# how to read
# --------------------------------------------------------------------------
h1("How to read this document")
body(
    "Sections 1 and 2 describe the input side: where the data comes from, how the point-in-time "
    "panel is built, what is wrong with it, and how the three label families are generated. "
    "Section 3 states the common design of the Phase 3 experiments once, so that Section 4 does not "
    "have to repeat it. Section 4 walks through the experiments individually, each under four "
    "headings: sample, estimator and test, t-statistic construction, conclusion. Section 5 collects "
    "the conclusions and the multiplicity-adjusted counts. Section 6 lists the four open questions, "
    "with what we currently do, why I think it is defensible, what it does not cover, and a "
    "suggested one-sentence answer.",
    indent=False,
)
body(
    "Grey bracketed lines mark where a figure or a table should be pasted. Every figure already "
    "exists as a PNG in data/06_event_study/figures/ under the file name given in its caption; the "
    "tables that are shown as real Word tables here are the ones that do not have a slide equivalent "
    "yet. The numbers in the text come from data/06_event_study/tables/freq=1h/ and from "
    "data/05_regime/tables/, and all of them can be regenerated in about seven minutes (Appendix A).",
    indent=False,
)
body(
    "One convention throughout: the word benchmark means the same-direction rows that also crossed "
    "the price threshold but are not the regime being tested. It does not mean the market, and it "
    "does not mean a random hour. The random-hour comparison exists separately as the placebo "
    "(Experiment 8).",
    indent=False,
)

# --------------------------------------------------------------------------
# part 1 data
# --------------------------------------------------------------------------
h1("1  Data")

h2("1.1  Sources and sample window")
body(
    "Everything comes from the public Binance USD-M perpetual futures archive: 1-hour klines "
    "(OHLCV plus taker-buy volume and trade count), mark price klines, index price klines, the open "
    "interest metrics series, and funding rate history. No proprietary or vendor data is used, and no "
    "exchange other than Binance is in scope for Phase 1" + MINUS + "3.",
    indent=True,
)
body(
    "The sample window is 2021-12-01 to 2026-08-31 UTC, 57 months. The start date is not a choice: "
    "the open-interest archive becomes materially thinner before December 2021, so any earlier start "
    "would have a coverage cliff in the middle of the sample rather than at its edge.",
    indent=True,
)

h2("1.2  Six steps from the archive to the analysis panel")
body(
    "The pipeline is deterministic and re-runnable end to end. Each step writes parquet, and each "
    "step's output is checksummed, so a reviewer can tell whether a number came from the data that "
    "was actually used.",
    indent=True,
)
numbered([
    ("Enumerate", "every contract that has ever been listed on USD-M futures, from the archive index and the exchange-info snapshot. 683 contracts survive the first hard filter (USDT-quoted, base asset is not a stablecoin or fiat proxy)."),
    ("Liquidity screen", "keep contracts whose monthly hourly quote volume has ever ranked in the top 50. This leaves 285 contracts and fixes the download set."),
    ("Download", "the five archives per contract: klines, mark, index, open interest, funding."),
    ("Normalise", "four 1-hour tables on one grid defined by klines (klines_1h, mark_index_1h, oi_1h, funding), plus a contract master table."),
    ("Dense panel", "a 19-column hourly panel with exactly one row per contract-hour from the first bar to the last active day, 7,253,002 rows over 57 months. Missing hours are rows with bar_missing or oi_missing set, not gaps."),
    ("Point-in-time universe", "four eligibility gates applied at every month start produce 2,700 contract-months across 249 distinct contracts and 54 usable months."),
])

h2("1.3  How the point-in-time data is constructed")
body(
    "The requirement is that every quantity used at decision time t is observable at t, and that no "
    "quantity used to compute a forward outcome leaks back into the signal. Five conventions "
    "implement that:",
    indent=True,
)
bullets([
    ("Open interest is aligned to the end of the bar.", "The bar [20:00, 21:00) is paired with the OI snapshot taken at 21:00. Price and OI therefore become observable at the same instant, and the decision row is self-contained: it needs no forward-looking information."),
    ("The universe is decided at the month start, from the previous 30 days.", "Membership for month m uses the window [m" + MINUS + "30d, m). A contract that de-lists later is still in the sample for every month in which it qualified; a contract that becomes liquid mid-month enters at the next month start, never inside the month."),
    ("Thresholds are trailing.", "The p70 for price and for OI is computed on the contract's own last 90 calendar days, ending at the decision instant, so the threshold never uses a future observation."),
    ("The market-neutral adjustment is a same-hour cross-section.", "Each hour, the equal-weighted mean return of the whole labelled-ok pool (7,010,789 rows, about 173 contracts per hour) is subtracted from every row of that hour. It uses only that hour's information."),
    ("Forward outcomes start at the decision price.", "fwd_h = P(t+h) / P(t) " + MINUS + " 1 and rv_h = square root of the sum of squared hourly log returns over the h hours after t, where t is the close of the event bar. Neither window includes the event bar."),
])
body(
    "The dense grid deserves one sentence more. Because missing hours are kept as flagged rows, a "
    "rolling 90-day percentile always has a well-defined window length and a visible count of usable "
    "observations; if the grid were sparse, the same percentile would silently mean different things "
    "for different contracts.",
    indent=True,
)

h2("1.4  Data quality")
body(
    "Coverage is measured per contract and per source on the panel grid. The important column is not "
    "\"share at 100%\" but \"share at or above 0.999\", because four exchange-wide outage days "
    "(2022-07-31, 2022-10-02, 2023-02-24, 2026-06-29) each remove 24 hours from most listed contracts "
    "and therefore cap any full-sample 100% count.",
    indent=True,
)
table_caption("Table 1.1  Scale of the Phase 1 dataset and coverage by source")
make_table(
    ["Item", "Value"],
    [
        ["Panel rows (dense hourly grid)", "7,253,002"],
        ["Contracts / months", "285 / 57"],
        ["Universe cells (contract " + TIMES + " month)", "2,700  (249 contracts, 54 months)"],
        ["Median history per contract", "24,684 hours (34.3 months); range 1,605" + EM + "41,640"],
        ["klines coverage", "median 1.0000;  239 of 285 contracts at or above 0.999"],
        ["Open interest coverage", "median 0.9997;  208 of 285 at or above 0.999"],
        ["Mark price coverage", "median 0.9981;  39 of 285 at or above 0.999"],
        ["Index price coverage", "median 0.9977;  37 of 285 at or above 0.999"],
    ],
    widths=[7.0, 9.0],
)
note("Source: data/04_qa/data_quality.md and data/04_qa/data_dictionary.md.")

body(
    "Four properties of the data change how it has to be used, and all four are handled in code "
    "rather than left to the reader:",
    indent=True,
)
numbered([
    ("Grid rule drops data the archive holds.", "Because the grid is defined by klines, 6,863 mark hours, 6,766 index hours and 5,212 OI hours read as missing even though the value exists in the raw archive. They are concentrated on five days where the klines archive itself has holes. This understates mark and index coverage; it does not bias any price series that is used."),
    ("Open interest has genuine holes.", "19,313 hours (806 contract-days) have no file in the archive at all, and in 28% of those hours the contract was actively trading; a further 7,989 hours have a file but no snapshot. The universe gate caps this at 10% trailing coverage and 48 consecutive hours, and the panel carries the per-hour flag."),
    ("Halted bars look like observations.", "18,524 hours carry a kline with quote_volume = 0 and zero trades: the exchange kept publishing a frozen price. close.pct_change() returns exactly zero on every one of them, so a naive volatility estimate would read them as the quietest hours in the sample. Every downstream filter requires quote_volume > 0; LITUSDT alone accounts for 7,816 of these hours."),
    ("Funding sparsity is semantic, not a defect.", "Only 16.65% of rows carry a funding rate, because funding settles on an interval; the rest are NaN by design. The interval itself is forward-filled (a known quantity at decision time), and it is not constant: 1h, 2h, 4h and 8h all occur, and 91 contracts changed interval mid-sample. Nothing in the pipeline hard-codes 8h."),
])
body(
    "Two further conventions are worth recording because they are easy to get wrong. First, open "
    "interest, volume and taker-buy volume are in base-asset units, not contracts, and contracts whose "
    "base asset starts with 1000 count a thousand tokens per unit; the ratio quote_volume / volume "
    "falls inside [low, high] on 99.9996% of bars, which is the check that confirms the unit system. "
    "Second, oi = 0 is a market-wide publishing event on 2,523 rows, not a gap, and downstream code "
    "filters oi > 0 rather than treating it as missing.",
    indent=True,
)

h2("1.5  Reproduction and verification")
body(
    "Phase 1 rebuilds with one command (python phase1/run_phase1.py --out-root data --sample-end "
    "2026-08-31); steps 4 to 6b are local computation, while steps 0 to 3 need network access to the "
    "archive. Phase 2 rebuilds with one command as well, and Phase 3 in six, with a total wall time of "
    "about 6.6 minutes when the inputs are on disk (Appendix A). Verification is by checksum: "
    "build_deliverables.py --verify re-hashes every file under data/ and exits non-zero on any "
    "mismatch. This proves internal consistency, not provenance: it shows the outputs match the inputs "
    "that produced them, not that the inputs match Binance's own archive.",
    indent=True,
)

# --------------------------------------------------------------------------
# part 2 labels
# --------------------------------------------------------------------------
h1("2  How the three label families are generated")

body(
    "Every label is computed per contract, from that contract's own trailing history, at four "
    "frequencies (1h, 4h, 8h, 1d). Phase 3 uses the 1h labels only; 1d exists as a robustness "
    "aggregation, and 4h/8h are parameterised but not yet run. Three families are produced in the same "
    "pass, so a single row carries the regime, the funding state and the market state together.",
    indent=True,
)
table_caption("Table 2.1  Label parameters")
make_table(
    ["Parameter", "Regime (price/OI)", "Funding state", "Market volatility state"],
    [
        ["Signal", "1-bar change: |P(t)/P(t-h) " + MINUS + " 1|, |OI(t)/OI(t-h) " + MINUS + " 1|", "Funding rate at settlement", "Cross-sectional median of (high" + MINUS + "low)/close"],
        ["Lookback window", "90 calendar days, trailing", "90 calendar days, trailing", "1 year of hours (8,760h), trailing"],
        ["Quantile / cut", "p70 on each axis (scan p55" + EM + "p80)", "p25 / p75 / p90", "1/3 and 2/3 of the smoothed series"],
        ["Minimum history", "30 days", "30 days", "30 days"],
        ["Smoothing", "none", "none (settlement series, one vote per settlement)", "24-hour moving average"],
        ["Change window N", "1 bar (n_bars = 1)", "not applicable", "not applicable"],
        ["Output", "R1 / R2 / R3 / R4 / undefined", "negative / neutral / high / extreme", "low / mid / high / unknown"],
    ],
    widths=[3.4, 4.6, 4.2, 4.4],
    font=8.5,
    header_font=8.5,
)
note(
    "Frequencies: 1h, 4h, 8h, 1d. Phase 3 uses 1h. The 1d labels are an aggregation robustness check, "
    "not a parallel main frequency, and 4h/8h are optional tests in the note that have not been run yet."
)

h2("2.1  Price/OI regime labels (R1 to R4)")
body(
    "The classification is a 2x2 of the signs, applied only to bars where both magnitudes are "
    "unusual for that contract:",
    indent=True,
)
make_table(
    ["Condition", "Label", "Reading in the note"],
    [
        ["|" + DELTA + "p| > p70 and |" + DELTA + "OI| > p70, " + DELTA + "p > 0, " + DELTA + "OI > 0", "R1", "fresh long buildup"],
        ["|" + DELTA + "p| > p70 and |" + DELTA + "OI| > p70, " + DELTA + "p > 0, " + DELTA + "OI < 0", "R2", "short covering"],
        ["|" + DELTA + "p| > p70 and |" + DELTA + "OI| > p70, " + DELTA + "p < 0, " + DELTA + "OI > 0", "R3", "fresh short buildup"],
        ["|" + DELTA + "p| > p70 and |" + DELTA + "OI| > p70, " + DELTA + "p < 0, " + DELTA + "OI < 0", "R4", "long unwind / deleveraging"],
    ],
    widths=[8.4, 1.6, 6.6],
)
note(
    "Rows that fail any requirement are kept and tagged with a mutually exclusive excl_reason: "
    "no_price, halt (quote_volume = 0), no_oi, span_gap (a bar inside the change window is invalid), "
    "warmup (less than 30 days of history). About 87% of valid rows are undefined at p70 by "
    "construction: this is an event definition, not a state definition."
)
table_caption("Table 2.2  Regime counts at 1h, p70, full sample")
make_table(
    ["Regime", "Rows", "Share of labelled", "Share of valid rows"],
    [
        ["R1", "267,080", "28.9%", "3.70%"],
        ["R2", "184,686", "20.0%", "2.56%"],
        ["R3", "164,126", "17.8%", "2.27%"],
        ["R4", "307,343", "33.3%", "4.26%"],
        ["Labelled total", "923,235", "100%", "12.80%"],
        ["Undefined", "6,291,392", EM, "87.20%"],
    ],
    widths=[3.8, 3.8, 4.4, 4.6],
)
note(
    "Source: data/05_regime/tables/regime_counts.parquet, freq = 1h. Phase 3's headline sample further "
    "requires in_universe and a valid forward window, which is why it is 256,079 events rather than 923,235."
)

h2("2.2  Funding state labels")
body(
    "Funding is treated as a conditioning variable, not a signal, exactly as the note specifies. The "
    "percentiles are computed on the settlement series (one vote per settlement, not forward-filled "
    "onto the hourly grid), over the contract's trailing 90 days, with p25/p75/p90. The three "
    "thresholds produce four boolean columns, and they overlap by design: funding_high is f > p75 and "
    "funding_extreme is f > p90, so the extreme rows are a subset of the high rows. When a spread "
    "needs \"above p75 including extreme\", the code takes the union explicitly (fund == 2 or fund == "
    "3) rather than relying on the mutually exclusive bucket.",
    indent=True,
)
body(
    "Computing on the settlement series rather than on an hourly forward-filled grid is a deliberate "
    "choice: it avoids inventing observations. The cost is small: the three alternative "
    "representations (settlement, hourly forward-fill, hourly annualised) disagree on 1.91% to 2.82% "
    "of rows.",
    indent=True,
)

h2("2.3  Market volatility state labels")
body(
    "The market state groups hours into low, mid and high volatility. The construction is: take "
    "(high " + MINUS + " low) / close for every contract-hour, take the cross-sectional median across "
    "the universe members of that hour, smooth it with a 24-hour moving average, and cut it at the "
    "series' own trailing one-year 1/3 and 2/3 quantiles. Thirty days of history are required before a "
    "state is assigned, and rows without a state are marked unknown rather than dropped.",
    indent=True,
)
body(
    "The range (high " + MINUS + " low) / close is used instead of |return| on purpose: |return| only "
    "sees the net path, so a bar that spikes 3% and returns to its open reads as the quietest hour of "
    "the day, which is exactly wrong. The cross-sectional median absorbs single-contract bad prints. "
    "Because the cuts are trailing quantiles of a smoothed series, the three buckets are not "
    "equal-sized: the measured split is 37.4% low, 31.1% mid and 31.5% high, and the report must state "
    "that rather than implying thirds.",
    indent=True,
)
body(
    "This variable filters nothing. It exists so that results can be split by environment (Experiment "
    "14b) and so that a reviewer can check whether an effect is just a volatility proxy.",
    indent=True,
)

h2("2.4  Threshold robustness")
body(
    "The threshold was fixed before any result was computed, at the 70th percentile, and it was not "
    "subsequently moved. Three checks show that this choice is not doing hidden work:",
    indent=True,
)
numbered([
    ("Six-percentile scan (p55 to p80).", "The labelling rate falls from 23.0% to 7.5% of valid rows, but the composition of the labelled set barely moves: R1 goes from 27.2% to 31.0%, R4 from 32.1% to 34.1%, R2 from 21.8% to 18.2%, R3 from 18.9% to 16.7%. In other words the percentile is a sample-size dial, not a conclusion dial."),
    ("A matched z-score alternative.", "The note suggests z-scores as a second method. Comparing the two requires matching the labelling rate first: |z| > 0.416 corresponds to p55, |z| > 0.623 to p70, |z| > 0.843 to p80. At matched rates the two methods produce the same composition to within about one percentage point, so the percentile rule is not an artefact of the method."),
    ("Cross-frequency consistency.", "The 4h and 8h labels exist and the generator is frequency-agnostic; re-running the event study on them is parameterisation work (about 40 minutes) plus estimation (about 10 minutes), and it is the most direct test of whether the 1h threshold is doing something special."),
])
table_caption("Table 2.3  Threshold scan at 1h (percentile method)")
make_table(
    ["Threshold", "Labelled share of valid", "R1 share", "R2 share", "R3 share", "R4 share"],
    [
        ["p55", "23.01%", "27.2%", "21.8%", "18.9%", "32.1%"],
        ["p60", "19.27%", "27.7%", "21.3%", "18.6%", "32.5%"],
        ["p65", "15.87%", "28.2%", "20.7%", "18.2%", "32.9%"],
        ["p70 (main)", "12.80%", "28.9%", "20.0%", "17.8%", "33.3%"],
        ["p75", "10.00%", "29.8%", "19.2%", "17.3%", "33.7%"],
        ["p80", "7.49%", "31.0%", "18.2%", "16.7%", "34.1%"],
    ],
    widths=[2.6, 4.0, 2.5, 2.5, 2.5, 2.5],
)
note("Source: data/05_regime/tables/threshold_sensitivity.parquet, freq = 1h. Shares are within the labelled set and sum to 100%.")
paste_slot("figure", "width 15 cm")
figure_caption("Figure 2.1  Threshold sensitivity: labelling rate and regime composition, 1h.   " + EM + "   source: data/05_regime/figures/threshold_sensitivity.png")
paste_slot("figure", "width 15 cm")
figure_caption("Figure 2.2  Regime composition over time.   " + EM + "   source: data/05_regime/figures/regime_share_over_time.png")

# --------------------------------------------------------------------------
# part 3 design
# --------------------------------------------------------------------------
h1("3  Phase 3 experimental design (common to all experiments)")

body(
    "Phase 3 asks one question in four ways: once the fact that something moved is held fixed, does "
    "the joint behaviour of price and open interest add information about what happens next? The "
    "design below is shared by every experiment; Section 4 only states what changes.",
    indent=True,
)
table_caption("Table 3.1  The design in one table")
make_table(
    ["Item", "Setting"],
    [
        ["Main sample", "Headline events: 256,079 at 1h (255,807 with a complete 24h forward window), restricted to in_universe and excl_reason = ok"],
        ["Analysis panel", "1,966,709 rows at h = 1, 1,965,030 at h = 24: the events plus every same-direction price-threshold row"],
        ["Event definition", "A 1-hour bar in which |price change| and |OI change| both exceed the contract's own trailing 90-day 70th percentile (at least 30 days of history)"],
        ["Cells", "-1 = price did not cross (not an event); 0 = price crossed but OI did not (the comparison base); 1-4 = R1 to R4"],
        ["Dependent variable (returns)", "y_raw = market-neutral return, no winsorising, no sign flipping. The equal-weighted mean of the labelled-ok pool is subtracted hour by hour"],
        ["Dependent variable (volatility)", "lrv = log(rv_h), not neutralised, not winsorised"],
        ["Dependent variable (reversal)", "0/1 indicator: did the forward return have the opposite sign to the event bar"],
        ["Forward horizons", "1, 4, 8 and 24 hours, all four reported for every structure"],
        ["Estimation, Exps 1-4", "Two-way (contract and month) fixed effects, fitted by iterative de-meaning to 1e-7, then OLS on the residuals"],
        ["Estimation, Exps 5-9", "No fixed effects and no regression: pooled group means, i.e. the portfolio view"],
        ["Standard errors", "Two-way clustered (CGM): V = V_contract + V_month " + MINUS + " V_contract x month"],
        ["Multiplicity", "Benjamini-Hochberg within each experiment's family; families of 16, 20 or 28 cells depending on the experiment"],
        ["Influence", "t_drop5: re-estimate after removing the five contracts with the largest influence"],
        ["Decision rule", "|t| > 1.96 for significance; a result is reported as robust only if it also survives BH and drop5"],
        ["Units", "Decimals internally (x100 = percent, x1e4 = basis points)"],
    ],
    widths=[4.4, 12.2],
    font=8.5,
    header_font=8.5,
)

h2("3.1  What the benchmark is, and what it is not")
body(
    "For R1 the comparison group is the other rows that also moved up more than the price threshold: "
    "R2 plus the up-bars where OI stayed quiet. For R3 it is R4 plus the quiet down-bars, and so on. "
    "The regression is estimated on the whole same-direction sample at once, with a single dummy for "
    "the regime, so beta is the difference between that regime and the rest of the same-direction "
    "rows, not a difference between the regime and itself.",
    indent=True,
)
table_caption("Table 3.2  Benchmarks by regime")
make_table(
    ["Price direction", "Regime", "Comparison group"],
    [
        ["up", "R1 (OI up)", "R2 + up-bars where OI did not move"],
        ["up", "R2 (OI down)", "R1 + up-bars where OI did not move"],
        ["down", "R3 (OI up)", "R4 + down-bars where OI did not move"],
        ["down", "R4 (OI down)", "R3 + down-bars where OI did not move"],
    ],
    widths=[3.4, 4.0, 9.2],
)
body(
    "The benchmark is deliberately not \"all hours\" and deliberately not \"the market\". It holds the "
    "fact of a large move and the direction fixed, and varies only the open-interest condition, which "
    "is the comparison the note's hypothesis requires. The other natural comparison, against random "
    "hours of the same contracts, is Experiment 8; having both means a null cannot be explained by the "
    "choice of benchmark alone.",
    indent=True,
)

h2("3.2  Why the return variable is market-neutral")
body(
    "The raw forward return of a crypto perpetual is dominated by the market factor: in the headline "
    "sample R4's 24-hour raw mean is +0.250%, while its market-neutral counterpart is " + MINUS +
    "0.048%. Said plainly, the entire positive raw number is the common factor, not the signal. "
    "Subtracting the same-hour equal-weighted mean of the labelled-ok pool (about 173 contracts per "
    "hour) removes it.",
    indent=True,
)
body(
    "Winsorising was tried and removed, because it is not a neutral transformation here. At h = 1 the "
    "truncation compresses R1's events by 3.36% but its comparison pool by only 1.34%, so a single cut "
    "removes more from the event side and shrinks or even flips the difference. The main specification "
    "is therefore untruncated, and the influence of extreme values is handled by reporting medians "
    "(Experiment 2) and by t_drop5.",
    indent=True,
)

h2("3.3  How the t-statistics are built")
body(
    "Three estimators are used, and each has its own standard-error expression. In all of them the "
    "clustering is two-way on contract and on month, which is the correction that matters: returns are "
    "correlated within a contract over time and across contracts in the same month.",
    indent=True,
)
body(
    "Fixed-effects regression (Experiments 1, 3, 4, 15). After de-meaning y and the dummy D to the "
    "contract and month means,",
    indent=True,
)
quote(
    "u = y~ - beta * D~;   psi = D~ * u;   "
    "V = sum_contracts (sum psi)^2 + sum_months (sum psi)^2 - sum_contract-month (sum psi)^2;   "
    "SE = sqrt(V) / sum(D~^2);   t = beta / SE"
)
body(
    "Linear combination of coefficients (Experiment 1b). The five 2x2 contrasts are e'beta, so the "
    "standard error is a quadratic form in the clustered covariance:",
    indent=True,
)
quote(
    "SE = sqrt( e' * bread * V * bread * e ),   bread = (X~'X~)^-1,   t = e'beta / SE"
)
body(
    "Pooled spread with no regression (Experiments 5 to 7). Each row contributes a deviation from its "
    "own group mean, signed positive for the long leg and negative for the short leg:",
    indent=True,
)
quote(
    "psi_i = +/- (y_i - ybar_group) / n;   V = sum_contracts (sum psi)^2 + sum_months (sum psi)^2 - "
    "sum_contract-month (sum psi)^2;   SE = sqrt(V);   t = spread / SE"
)
body(
    "Daily difference series (Experiment 9) uses Newey-West with one lag. The placebo (Experiment 8) "
    "does not use a t-statistic at all: it reports a two-sided empirical p from 1,000 random draws, "
    "whose resolution floor is 0.002, and it is not entered into any BH family.",
    indent=True,
)

h2("3.4  Multiplicity and influence")
body(
    "Each experiment tests 16 or 20 or 28 cells at once, so a raw |t| > 1.96 threshold would produce "
    "about one false positive per 16 cells. Benjamini-Hochberg is applied within each family, and the "
    "families are kept separate rather than pooled, because pooling experiments that ask different "
    "questions would make the correction depend on how many experiments happened to be run. In "
    "addition, every headline result is re-estimated after removing the five most influential "
    "contracts (t_drop5); a result that survives |t| > 1.96 but not drop5 is reported as dependent on "
    "a few contracts rather than as a finding.",
    indent=True,
)

# --------------------------------------------------------------------------
# part 4 experiments
# --------------------------------------------------------------------------
h1("4  The experiments")

body(
    "The order follows the deck. Experiments 1 to 9 form the decision layer; 10 to 14 are descriptive "
    "and carry no test; 15 is a robustness check that belongs to the decision layer even though it is "
    "numbered with the descriptive block.",
    indent=True,
)

h2("4.1  Decision layer (Experiments 1 to 9)")

experiment(
    "Experiment 1", "Forward return: does the regime differ from its price-only benchmark?",
    "Headline sample, excl_reason = ok, forward window complete. The estimation sample is all rows "
    "that crossed the price threshold in that direction, which is 554,489 rows at h = 24 (255,807 "
    "events plus 298,682 OI-quiet rows). Each of the four regimes is estimated once against the rest "
    "of its own direction.",
    "y = beta * D + contract fixed effects + month fixed effects, with y the market-neutral return. "
    "beta is the difference, within the same contract and the same month, between the regime and the "
    "other same-direction rows that also crossed the price threshold. Fitted by two-way de-meaning to "
    "1e-7 and then OLS on the residuals, which is numerically identical to including 303 dummies.",
    "u = y~ " + MINUS + " beta * D~, psi = D~ * u, V = V_contract + V_month " + MINUS +
    " V_contract" + TIMES + "month, SE = sqrt(V) / sum(D~^2), t = beta / SE. Benjamini-Hochberg over "
    "the 16 cells of this family; t_drop5 re-estimates after removing the five contracts with the "
    "largest psi.",
    "Six of sixteen cells clear |t| > 1.96: R1 at 1h (+2.51bp, t 3.41), R4 at 4h (+2.05bp, t 2.43), "
    "R3 at 4h (" + MINUS + "4.39bp, t " + MINUS + "3.02), R3 at 8h (" + MINUS + "8.26bp, t " + MINUS +
    "3.23), R3 at 24h (" + MINUS + "11.63bp, t " + MINUS + "2.61) and R2 at 24h (" + MINUS +
    "7.12bp, t " + MINUS + "2.50). All six survive BH and all six survive drop5. The other ten cells "
    "are individually indistinguishable from zero, including every R1 horizon except 1h. Read as a "
    "row, only R3 holds across 4, 8 and 24 hours, and only under event weighting (Experiment 15).",
    figs=[("Figure 4.1  Mean forward return: each regime against its price-only benchmark", "f01_mean_return.png")],
    tabs=["Table 4.1  Experiment 1: beta in basis points, with t in parentheses"],
)

experiment(
    "Experiment 1b", "The 2x2 factor view: what does OI add to a price move?",
    "Headline sample restricted to cells 1 to 4, i.e. the OI-quiet rows are excluded so that the two "
    "axes are both \"active\": 256,076 rows at h = 1 and 255,807 at h = 24.",
    "The four regimes are literally a 2x2 of price direction and OI direction. With P = 1{price up} "
    "and O = 1{OI up}, estimate y = aP + bO + c(P x O) + fixed effects, and report five linear "
    "combinations: R1 " + MINUS + " R2 = b + c (OI effect when price is up), R3 " + MINUS +
    " R4 = b (OI effect when price is down), R1 " + MINUS + " R3 = a + c (price effect when OI is up), "
    "R2 " + MINUS + " R4 = a (price effect when OI is down), and the interaction (R1 " + MINUS +
    " R2) " + MINUS + " (R3 " + MINUS + " R4) = c.",
    "For each contrast, SE = sqrt(e' bread V bread e) with bread = (X~'X~)^-1 and V the same two-way "
    "clustered covariance; t = e'beta / SE. BH over the 20 cells of this family. For drop5 the "
    "influence of each contract is scored by psi * (bread e).",
    "Fourteen of twenty cells clear |t| > 1.96, and all fourteen survive BH; thirteen survive drop5. "
    "The interaction is the strongest result in the whole phase: +3.46, +6.81, +12.22 and +20.67bp at "
    "1, 4, 8 and 24 hours (t = 3.35, 2.79, 4.26, 4.16; smallest BH p = 3.2e-4), and it survives drop5 "
    "at every horizon. That is a statement that the price effect and the OI effect are not additive: "
    "the OI effect has opposite signs on up-moves and down-moves, and the price effect has opposite "
    "signs when OI rises and when it falls. The second robust row is R2 " + MINUS + " R4, the price "
    "contrast conditional on OI falling (4/4, " + MINUS + "2.53 to " + MINUS + "9.49bp). The weakest "
    "is R1 " + MINUS + " R2 at 24h, where +8.35bp falls to t = 0.90 after removing five contracts.",
    figs=[("Figure 4.2  The 2x2 factor view: four simple effects and the interaction", "f01b_factor_2x2.png")],
    tabs=["Table 4.2  Experiment 1b: the five contrasts in basis points, with t in parentheses"],
)

experiment(
    "Experiment 2", "The mean is not the typical event",
    "Same rows as Experiment 1. For each contract, the median of the regime is differenced against "
    "the median of its same-direction comparison rows; the reported number is the average of those "
    "per-contract differences, and the last column is the share of contracts where the difference is "
    "negative (249 contracts, 248 for R3 because BSBUSDT has no R3 event).",
    "A two-stage descriptive statistic, not a regression. The table's two columns are deliberately "
    "different objects and the slide labels them as such: the mean column is the FE-adjusted "
    "coefficient from Experiment 1, and the median column is the per-contract median difference "
    "averaged across contracts. Both are measured against the same-direction benchmark at 24 hours, "
    "so the column titles carry an explicit \"Δ vs same-direction benchmark\" header. No fixed "
    "effects are removed and nothing is tested, for three reasons: the median is non-linear and has "
    "no row-level influence function, so an analytic clustered standard error does not exist; the "
    "second stage averages over contracts with very few events each; and median(A) " + MINUS +
    " median(B) mixes a location shift with a difference in dispersion.",
    "None. The standard-error, t, p and BH columns are empty for this experiment by construction.",
    "At 24 hours all four regimes are negative on this measure: " + MINUS + "66.27, " + MINUS +
    "24.54, " + MINUS + "11.34 and " + MINUS + "13.30bp, with 76%, 49%, 50% and 67% of contracts on "
    "the same side. Set against the mean column this is the \"mean is not the typical event\" point: "
    "the row-level distribution of the market-neutral return is strongly right-skewed in all four "
    "regimes (skewness +3.97, +3.69, +5.25, +3.19; medians " + MINUS + "60.57, " + MINUS + "44.03, "
    + MINUS + "37.70, " + MINUS + "44.59bp), so the mean sits well above the median and a handful of "
    "large positive observations carries the average.",
    tabs=["Table 4.3  Experiment 2: mean versus median, 24 hours"],
)

experiment(
    "Experiment 3", "Forward volatility is the strongest result",
    "Identical to Experiment 1, including the OI-quiet rows; without them the comparison group would "
    "collapse to \"the other OI state\" and the benchmark would change meaning.",
    "The same regression with the dependent variable replaced by lrv = log(rv_h), where "
    "rv_h = sqrt(sum over the h hours after the decision of r_s^2) and r_s = ln(P_s / P_{s-1}). The "
    "window therefore starts with the first bar after the event bar, which is the definition the deck "
    "prints on the slide. The reported number is exp(beta) " + MINUS + " 1, i.e. how much higher the "
    "volatility is than the benchmark, in percent.",
    "Same as Experiment 1: psi = D~ * u, two-way clustered V, SE = sqrt(V) / sum(D~^2). BH over 16 "
    "cells; drop5 as before.",
    "Sixteen of sixteen cells are positive and significant, with |t| between 7.0 and 20.8 and BH p "
    "below 1e-11 everywhere: R1 goes from +24.40% at 1h to +10.87% at 24h, R3 from +12.34% to +7.35%, "
    "R4 from +9.92% to +4.33%. drop5 makes the estimates slightly stronger rather than weaker, which "
    "is the signature of an effect that is not carried by a few names. Two caveats belong with the "
    "number. First, rv_1h is the absolute log return of the first bar after the event, not of the "
    "event bar itself, so the 1h column is a single-bar quantity and should not be compared in "
    "magnitude with 4, 8 and 24 hours. Second, event rows sit further above their own threshold than "
    "the comparison rows (mean log(|" + DELTA + "p|/threshold) of 0.70 against 0.49), and volatility "
    "is increasing in the size of that move; controlling for the trigger-move decile, R1 falls from "
    "+24.4% to +14.1% (t 16.3), R2 from +9.1% to +2.9% (t 3.4), R3 from +12.3% to +7.8% (t 8.1) and "
    "R4 from +9.9% to +1.2% (t 1.5). The qualitative conclusion survives for three regimes and not "
    "for R4.",
    figs=[("Figure 4.3  Realised volatility: how much higher than the benchmark", "f03_volatility.png")],
    tabs=["Table 4.4  Experiment 3: volatility premium in percent, with t in parentheses"],
)

experiment(
    "Experiment 4", "Reversal probability moves only on the up branch",
    "All rows that crossed the price threshold, including the OI-quiet rows: 555,008 rows at h = 1 "
    "(277,431 up and 277,577 down, of which 298,932 are OI-quiet). The reversal indicator needs the "
    "raw forward return, so the panel is merged with the forward file on (contract, hour).",
    "A linear probability model, since the dependent variable is 0/1: rev = beta * D + contract and "
    "month fixed effects, where rev = 1 if the forward return has the opposite sign to the event bar. "
    "The only difference from Experiments 1 and 3 is that the return is not made market-neutral: "
    "subtracting the cross-sectional mean would change the sign of the forward return itself and the "
    "left-hand side would stop being a reversal indicator.",
    "Same clustered construction as Experiment 1, with psi = D~ * u. BH over 16 cells; drop5 as "
    "before.",
    "Ten of sixteen cells are significant, and the pattern is asymmetric. The up branch is significant "
    "at every horizon: R1 is 1.19 to 2.51pp more likely to reverse than its benchmark, R2 is 1.00 to "
    "2.17pp less likely, with |t| between 2.56 and 7.29 and both BH and drop5 clean. The down branch "
    "is silent until 24 hours, where it appears with the opposite sign (R3 +1.48pp, t 3.08; R4 "
    + MINUS + "1.25pp, t " + MINUS + "3.14). Read economically, new long positioning tends to give "
    "part of the move back and short covering tends not to. The descriptive continuation rates are "
    "46.0% to 49.8% at 24 hours, but the continuation rate is identical to the hit rate by "
    "construction, so it cannot be used as independent evidence: what is tested here is the difference "
    "between the regime and the other rows, not a probability against 50%.",
    figs=[("Figure 4.4  Reversal behaviour: raw rates and the tested gap versus the benchmark", "f04_cont_rev.png")],
    tabs=["Table 4.5  Experiment 4: difference in reversal probability in percentage points, with t in parentheses"],
)

experiment(
    "Experiment 5", "Baseline 1: price alone",
    "Rows that crossed the price threshold, irrespective of OI: 277,431 up and 277,577 down at h = 1. "
    "Only the two compared groups enter the estimate; the reference rows are excluded.",
    "Pooled long-short spread: the mean of the up group minus the mean of the down group, with no "
    "fixed effects and no regression, which is the portfolio view rather than the controlled view.",
    "Each row contributes its deviation from its own group mean, positive for the long leg and "
    "negative for the short leg: psi = +/- (y " + MINUS + " ybar) / n. Then the same two-way clustered "
    "variance, SE = sqrt(V), t = spread / SE. BH over the 28 cells shared by Experiments 5 to 9.",
    "The spread is negative at all four horizons and only reaches |t| > 1.96 at 1h: " + MINUS +
    "1.43bp, t " + MINUS + "2.38. Its BH p-value is 0.485, so it does not survive the family "
    "correction. Price direction alone does not produce a profitable long-short spread at these "
    "horizons.",
    figs=[("Figure 4.5  Four pooled long-short spreads: price, OI, funding and the regime label", "f05_07_singles.png")],
    tabs=["Table 4.6  Experiments 5 to 7: pooled spreads in basis points, with t in parentheses"],
)

experiment(
    "Experiment 6", "Baseline 2: open interest alone",
    "Rows that exceeded the OI threshold, ignoring the price condition: 266,219 with OI up and 280,214 "
    "with OI down at h = 1.",
    "Same pooled spread as Experiment 5, with the long leg defined as OI increasing and the short leg "
    "as OI decreasing. No fixed effects.",
    "Identical to Experiment 5; the BH family is again the shared 28-cell family of Experiments 5 to 9.",
    "Zero of four cells are significant; the closest is +0.63bp at 1h (t 1.52). This is not in "
    "conflict with Experiment 3: OI predicts volatility, and this experiment asks whether it predicts "
    "the direction of return. It does not.",
)

experiment(
    "Experiment 7", "Baseline 3: funding alone",
    "Rows in the top funding bucket (above p75, including the extreme rows above p90): 139,803 + "
    "102,018 = 241,821 rows, against 705,117 rows below p25, 946,938 in total at h = 1. The middle "
    "bucket is the reference and is not in the sample.",
    "Same pooled spread, long the high-funding group and short the low-funding group. The bucket "
    "definitions overlap (extreme is a subset of high), so the code takes the union explicitly rather "
    "than relying on the mutually exclusive bucket column.",
    "Identical to Experiment 5.",
    "Zero of four cells are significant. The sign is consistently negative at all four horizons "
    "(" + MINUS + "0.53, " + MINUS + "1.52, " + MINUS + "2.59, " + MINUS + "6.42bp): high funding is "
    "followed by slightly worse performance, but never by enough to separate from zero. Funding as a "
    "standalone signal does not earn a spread in this sample.",
)

experiment(
    "Experiment 8", "Placebo: the regime against random hours",
    "The true value uses each regime's headline event rows (74,959 / 50,564 / 44,622 / 85,931 at "
    "h = 1). The random pool is every hour of the same contracts, including the hours where nothing "
    "moved: 1,966,709 rows at h = 1.",
    "For each regime, keep its contract composition and redraw the same number of timestamps "
    "uniformly from each contract's own history, 1,000 times, and compute the same mean each time. "
    "The true value is then compared with the simulated distribution rather than with a regression "
    "coefficient.",
    "No t-statistic. The two-sided empirical p is p = 2 * min(P(random <= true), P(random >= true)), "
    "capped at 1; 1,000 draws give a resolution of 0.002. The seed is fixed in config.py, so the "
    "distribution is reproducible to the digit.",
    "Ten of sixteen cells fall outside the random band. R2 is below the 5th percentile at all four "
    "horizons, and R3 at 4, 8 and 24 hours: both regimes do worse than random hours of the same "
    "contracts, which rules out \"these coins were simply weak over the sample\". R1 is above the "
    "95th percentile only at 1h (+0.70bp) and R4 only at 4h and 8h. By 24 hours R1 and R4 have fallen "
    "back inside the band. The point of the experiment is that \"is this moment special\" and \"is "
    "this difference significant\" are different questions: R4's beta is significant only at 4h, yet "
    "its placebo value is outside the band at both 4h and 8h.",
    figs=[("Figure 4.6  Placebo: true value against 1,000 random-timestamp draws", "f08_placebo.png")],
    tabs=["Table 4.7  Experiment 8: true means and the random band, in basis points"],
)

experiment(
    "Experiment 9", "The four-state spread against its three baselines",
    "Four signals measured on the same calendar days: price only, OI only, funding only, and the "
    "regime label itself (long R1, short R4). The intersection is 710 to 711 days. Each side of each "
    "signal requires at least five distinct contracts that day, otherwise the day is dropped.",
    "For each day, r_k = mean(long leg) " + MINUS + " mean(short leg). The comparison is the average "
    "of r_four_state " + MINUS + " r_k over the common days, so the question is whether the label's "
    "portfolio beats another portfolio on exactly the same days.",
    "Newey-West standard error with one lag on the daily difference series, t = mean(Delta) / NW SE. "
    "BH over the 28 cells of the 5-to-9 family; drop5 as before.",
    "The label's own long-short spread is not distinguishable from zero at any horizon (|t| between "
    "0.46 and 1.07), and none of the twelve differences against the three baselines is significant "
    "after correction. The single cell that clears |t| (the label minus price at 1h, +2.15bp, t 2.09) "
    "has BH p = 0.51 and t_drop5 = 1.57, so it fails both robustness checks. This is a clean null: the "
    "four-state label does not beat simple price, simple OI or simple funding as a daily-rebalanced "
    "long-short. It does not contradict Experiments 1 to 4, which ask a different question (is there "
    "information once composition is controlled), and it does not show that the label is useless; it "
    "shows that the tradeable spread built from it is flat.",
    figs=[("Figure 4.7  The four-state spread against its three baselines, same days", "f09_four_state_vs_baselines.png")],
    tabs=["Table 4.8  Experiment 9: daily spreads and differences, in basis points"],
)

h2("4.2  Descriptive layer (Experiments 10 to 14)")

experiment(
    "Experiment 10", "Descriptive: each cell's own levels, not versus the benchmark",
    "Headline sample with a valid forward window; every cell, including the OI-quiet one, is reported "
    "at every horizon.",
    "Pure description: count, mean, median, hit rate and mean realised volatility for each cell and "
    "horizon, on the untruncated market-neutral return. The raw (not neutralised) return is reported "
    "alongside as a reference.",
    "None. \"The cell mean is not zero\" is not a null hypothesis, so no test is run and no standard "
    "error is reported on this slide.",
    "At 24 hours every cell has a negative mean and a negative median (" + MINUS + "3.26 / " + MINUS +
    "13.70 / " + MINUS + "20.51 / " + MINUS + "4.76bp and " + MINUS + "60.57 / " + MINUS + "44.03 / "
    + MINUS + "37.70 / " + MINUS + "44.59bp), with hit rates between 46.0% and 49.8%. The same cells "
    "have positive raw returns (+4.11 to +24.96bp), which is the clearest single demonstration of why "
    "the market-neutral adjustment is needed: the raw number measures the market, not the signal.",
    figs=[("Figure 4.8  Descriptive levels: market-neutral return, raw return and realised volatility", "f10_levels.png")],
)

experiment(
    "Experiment 11", "Descriptive: path risk (reference only, no test)",
    "Same rows as Experiment 10.",
    "For each event, the maximum favourable excursion, maximum adverse excursion and maximum drawdown "
    "over the holding window. The first two are sign-flipped for short events so that \"favourable\" "
    "always means favourable; drawdown is non-positive by construction. Means and the 10th, 50th and "
    "90th percentiles are reported untruncated.",
    "None; descriptive only.",
    "At 24 hours the four paths are almost identical in shape: maximum favourable excursion around "
    "+5.4% to +5.6%, maximum adverse around " + MINUS + "4.9% to " + MINUS + "5.4%, maximum drawdown "
    "around " + MINUS + "4.8% to " + MINUS + "5.2%, with R3 the worst on all three. The means of these "
    "columns are dominated by a very small number of extreme paths (the single worst drawdown is "
    + MINUS + "382%), which is why the figure plots medians only. The economically relevant statement "
    "is that the path asymmetry is small: the average favourable and adverse excursions nearly offset, "
    "so the label does not describe a trade with a favourable risk profile.",
    figs=[("Figure 4.9  Path risk: median favourable against adverse excursion", "f11_path_risk.png")],
)

experiment(
    "Experiment 12", "Descriptive: the event path (reference only, no test)",
    "All events with a complete +/" + MINUS + "24 hour window (about 240,000 events), with a constant "
    "sample size at each offset.",
    "The average cumulative excess return from 24 hours before the event to 24 hours after, where the "
    "excess return each hour is the log return minus the same-hour equal-weighted mean of the labelled "
    "pool.",
    "Contract-clustered standard errors are drawn as a 95% band, but nothing is tested, and the band "
    "is described as descriptive.",
    "The left side is large (about 3% either way) because events are selected on large moves; the "
    "right side is close to half a percentage point. At k = +24 the four regimes sit at " + MINUS +
    "4.8, " + MINUS + "12.3, " + MINUS + "36.4 and +1.2bp, the same ordering as Experiments 1 and 10 "
    "with a 1 to 16bp gap caused by summing hourly log excess returns rather than compounding. Two "
    "cautionary notes belong with the figure: the vertical axes of the two panels are identical and "
    "should not be read as comparable steepness, and the benchmark is the pool-internal mean (about 47 "
    "contracts per hour), not the market index.",
    figs=[("Figure 4.10  Event path, 24 hours either side", "f12_event_path.png")],
)

experiment(
    "Experiment 13", "Descriptive: the eight single legs (reference only, no test)",
    "Headline sample with a valid window; each baseline contributes its long and short leg, and the "
    "regime label contributes R1 and R4. Eight series per horizon, 32 rows in total.",
    "The levels, not the spreads: the market-neutral mean return of each leg, reported separately.",
    "None; descriptive only. This is the one bar chart in the deck, and it is labelled as descriptive "
    "with no test.",
    "At 8 and 24 hours all eight legs are negative (at 24h: price " + MINUS + "8.59 and " + MINUS +
    "7.82bp, OI " + MINUS + "9.35 and " + MINUS + "8.48bp, funding " + MINUS + "13.15 and " + MINUS +
    "6.73bp, regimes " + MINUS + "3.26 and " + MINUS + "4.76bp). This is the table that explains why "
    "the spreads in Figures 4.5 and 4.7 are close to zero: they are the difference of two negative "
    "numbers, not of two zeros. Presenting a spread without its legs invites the reader to conclude "
    "that there is no effect at all, when the correct conclusion is that both sides underperform the "
    "pool by a similar amount.",
    figs=[("Figure 4.11  Eight single-leg levels by horizon", "f13_levels.png")],
)

experiment(
    "Experiment 14", "Descriptive: by contract and by market state",
    "Event rows only (cells 1 to 4, no OI-quiet rows): 256,076 at h = 1. The by-contract table has "
    "3,980 rows (249 contracts x 4 regimes x 4 horizons, minus missing combinations); the by-state "
    "table has 48 rows (3 states x 4 regimes x 4 horizons).",
    "Two separate re-cuts of the Experiment 1 cells: one by contract, one by the market volatility "
    "state. Only counts, means, medians, hit rates and volatility are reported.",
    "None; descriptive. The figures show the cross-contract interquartile band and the median "
    "contract, with contracts that have fewer than 30 events suppressed.",
    "Contract choice dominates regime choice by an order of magnitude: at 24 hours the cross-contract "
    "interquartile range is about 125bp, while the spread between the four regime means is about 17bp. "
    "The median contract loses in all four regimes (" + MINUS + "13 to " + MINUS + "27bp with the "
    "30-event filter). Splitting by market state tells a similar story in the other direction: from 4 "
    "hours on, R3 is the only regime that stays negative in all three volatility states, R1 changes "
    "sign in high volatility, and no regime shows a monotone gradient across states, so the regime "
    "effect is not simply a volatility proxy.",
    figs=[
        ("Figure 4.12  By contract: cross-contract distribution by regime and horizon", "f14a_by_symbol.png"),
        ("Figure 4.13  By market volatility state", "f14b_by_state.png"),
    ],
)

h2("4.3  Robustness of the decision layer (Experiment 15)")

experiment(
    "Experiment 15", "Daily aggregation: the return result depends on how observations are weighted",
    "Exactly the same rows as Experiments 1 and 3, re-grouped into (contract, calendar day, "
    "direction, cell). At h = 1 that is 555,008 rows collapsing to 276,389 groups, with a median of "
    "one hour per group.",
    "The same regression as Experiment 1, re-run on the grouped data with the group means as the "
    "dependent variable, so that each contract-day counts once instead of each event-hour counting "
    "once. This changes the weights, not the model: the fixed effects and the clustered standard "
    "errors are unchanged.",
    "Identical to Experiment 1. The purpose is to see whether a result is an artefact of the "
    "observation unit, so the two versions are reported side by side rather than replacing each other.",
    "The volatility result is stable: 16 of 16 cells keep the sign and the significance, with R1 "
    "falling from +24.40% to +16.94% at 1h and from +10.87% to +5.29% at 24h. The return result is "
    "not: 13 of 16 cells remain significant, but every regime flips sign. R1 goes from +2.51 to "
    + MINUS + "6.36bp at 1h and from +5.06 to " + MINUS + "37.86bp at 24h (t " + MINUS + "13.37); R2 "
    "goes from negative to positive at every horizon. The mechanism is within-day persistence: "
    "conditioning on how many hours of that day the state was present, a single appearance reverses "
    "(R1 " + MINUS + "20.6bp at h = 1) and five or more appearances continue (+33.5bp), a span of "
    "54bp, against 8.2bp for the benchmark across the same buckets. The correct statement is therefore "
    "not that one weighting is wrong: the event-weighted number answers \"what happens after a "
    "signal\", and the contract-day-weighted number answers \"what happens on a signal day\", and the "
    "two differ because repeated signals are not independent.",
    figs=[("Figure 4.14  Daily aggregation: the persistence gradient and the two weighting schemes", "f15_bycount.png")],
    tabs=["Table 4.9  Experiment 15: the same regression under two observation units, in basis points"],
)

# --------------------------------------------------------------------------
# part 5 conclusions
# --------------------------------------------------------------------------
h1("5  Conclusions")

h2("5.1  Three answers")
body(
    "Volatility: yes. Every regime is followed by a higher realised volatility than its price-only "
    "benchmark, at all four horizons, in 16 of 16 cells, with BH p below 1e-11 and drop5 unchanged or "
    "stronger. The result survives daily aggregation. It does not survive a control for the size of "
    "the triggering move unchanged: that control takes R1 from +24.4% to +14.1%, R3 from +12.3% to "
    "+7.8% and R4 from +9.9% to +1.2%. The defensible claim is that the OI condition adds to forward "
    "volatility beyond the price condition for three regimes, with R4 explained by trigger size.",
    indent=True,
)
body(
    "Direction: no, with one qualification. Six of sixteen cells are significant at the event level "
    "and only R3 holds across 4, 8 and 24 hours. Under daily weighting every regime flips sign, "
    "including R3. The one directional fact that is robust under the alternative weighting is the "
    "contract-day result: R1 underperforms its benchmark by 6 to 38bp with t between " + MINUS +
    "7.6 and " + MINUS + "13.4, and the persistence gradient explains why.",
    indent=True,
)
body(
    "Trading: no. The label's own long-short spread, the price spread, the OI spread and the funding "
    "spread are all indistinguishable from zero at every horizon, no spread survives BH, and the label "
    "beats none of its three baselines on the same days. Before any transaction cost is applied, none "
    "of these objects is a strategy.",
    indent=True,
)
body(
    "Interaction: yes. The one result that is significant at every horizon and survives both "
    "corrections is the 2x2 interaction in Experiment 1b: the effect of OI depends on the sign of the "
    "price move, and the effect of price depends on the sign of the OI move. That is the strongest "
    "evidence that the four cells should be treated as a joint state rather than as two independent "
    "factors, and it is the result I would build the next phase around.",
    indent=True,
)

h2("5.2  Decision summary")
table_caption("Table 5.1  Significance counts by experiment, after BH and after drop5")
make_table(
    ["Experiment", "h", "Cells tested", "|t| > 1.96", "BH < 0.05", "drop5 > 1.96"],
    [
        ["1  Return, mean", "1 / 4 / 8 / 24", "4 each", "1 / 2 / 1 / 2", "1 / 2 / 1 / 2", "1 / 2 / 1 / 2"],
        ["1b Factor contrasts", "1 / 4 / 8 / 24", "5 each", "3 / 3 / 3 / 5", "3 / 3 / 3 / 5", "3 / 3 / 3 / 4"],
        ["3  Volatility", "1 / 4 / 8 / 24", "4 each", "4 / 4 / 4 / 4", "4 / 4 / 4 / 4", "4 / 4 / 4 / 4"],
        ["4  Reversal", "1 / 4 / 8 / 24", "4 each", "2 / 2 / 2 / 4", "2 / 2 / 2 / 4", "2 / 2 / 2 / 4"],
        ["5-9 Spreads and deltas", "1 / 4 / 8 / 24", "7 each", "2 / 0 / 0 / 0", "0 / 0 / 0 / 0", "1 / 0 / 0 / 0"],
        ["15 Daily, returns", "1 / 4 / 8 / 24", "4 each", "2 / 4 / 4 / 3", "2 / 4 / 4 / 3", "2 / 3 / 3 / 3"],
        ["15 Daily, volatility", "1 / 4 / 8 / 24", "4 each", "4 / 4 / 4 / 4", "4 / 4 / 4 / 4", "4 / 4 / 4 / 4"],
    ],
    widths=[4.4, 3.0, 2.3, 2.2, 2.2, 2.5],
    font=8.5,
    header_font=8.5,
)
note(
    "77 cells clear |t| > 1.96 across all experiments; 75 survive BH and 73 survive drop5. The drop5 "
    "column is conditional on the cell having cleared |t| in the first place."
)

h2("5.3  How this maps to the note's hypothesis")
body(
    "The note's central hypothesis is that price moves accompanied by meaningful open-interest changes "
    "contain more information than price moves alone. The evidence is mixed by outcome, and it is "
    "worth stating that clearly rather than claiming a general win:",
    indent=True,
)
bullets([
    ("On volatility, supported.", "The OI condition adds information, with the trigger-size caveat above."),
    ("On direction, not supported at the event level.", "Only R3 holds across horizons, and it does not survive reweighting; the interaction in 1b is the part that survives."),
    ("On reversal, supported on the up branch.", "R1 reverses more and R2 reverses less, at all four horizons."),
    ("On the tradeable spread, not supported.", "No spread is distinguishable from zero before costs."),
])
body(
    "The note's null hypothesis, that price/OI regimes do not improve on simple price momentum, can "
    "therefore be rejected for volatility and for reversal, and cannot be rejected for returns. For "
    "an industrial project the second half matters as much as the first: the deliverable is a clean "
    "statement of where the signal does and does not work, not a strategy.",
    indent=True,
)

h2("5.4  Known limitations, stated up front")
numbered([
    ("No cost and no capacity.", "Phase 3 measures spreads, not portfolios (Section 6.4). The costed version is Phase 5."),
    ("No 4h or 8h labels yet.", "These are optional in the note and the generator supports them; running them is parameterisation plus estimation work (Section 6.2)."),
    ("Funding is a baseline, not a conditioning variable.", "The 4x4 regime-by-funding table in the note is Phase 4 work and has not been run."),
    ("The universe is defined by liquidity.", "Conclusions are about liquid USD-M perpetuals, not about crypto in general (Section 6.1)."),
    ("The difference estimator is an association.", "Fixed effects absorb contract and month levels, not the size of the triggering move (Section 6.3)."),
    ("Single sub-period.", "No year-by-year split: the sample is 54 months and the results are full-sample only."),
])

# --------------------------------------------------------------------------
# part 6 questions
# --------------------------------------------------------------------------
h1("6  Four design questions for discussion")

body(
    "These are the points where I would like a view before the mid-term. For each one I state what we "
    "currently do, why I think it is defensible, what it does not cover, and a one-sentence answer "
    "that I would give if asked.",
    indent=True,
)

h2("6.1  Is a monthly top-50 liquidity universe acceptable as the point-in-time sample?")
labelled("What we do.",
         "At the start of every month, contracts are ranked by their median hourly quote volume over "
         "the preceding 30 days, and the top 50 are kept subject to four gates: USDT-quoted and not a "
         "stablecoin or fiat pair; at least 90 days of 1h history at the month start; still trading at "
         "the month start; trailing 30-day OI coverage of at least 0.90 with no OI publication gap "
         "longer than 48 hours. This gives 2,700 contract-months, 249 distinct contracts, 54 months.")
labelled("Why I think it is acceptable.",
         "Five reasons, in order of importance.")
numbered([
    ("It is genuinely point-in-time.", "The rank uses only the window ending at the month start, so a contract that de-lists or collapses later is still in the sample for the months in which it qualified. There is no survivorship filter."),
    ("The gate that makes monthly cuts safe is the liveness gate.", "Without it, a dead contract's bar count freezes above the 90-day threshold and it passes every subsequent month: LUNAUSDT, which stopped trading in May 2022, would be eligible from July 2022 onward. Requiring \"last active day no earlier than the month start\" is what prevents the sample from accumulating corpses."),
    ("Top-50 is a capacity constraint, not a statistical convenience.", "It makes the estimand \"the effect for liquid USD-M perpetuals\", which is the only universe in which the result could ever be traded, and it is exactly the universe the note specifies."),
    ("The results do not rest on a handful of names.", "Every significant cell reported here also survives drop5, and the by-contract view (Experiment 14) shows that the median contract behaves like the mean."),
    ("Monthly rebalancing is slow enough to be stable.", "Membership turns over gradually, so there are no large month-to-month composition jumps that would show up as spurious time-series breaks."),
])
labelled("What it does not cover.",
         "Four things, none of which I think invalidates the design but all of which should be stated.")
numbered([
    ("Liquidity is correlated with volatility and with the size of a 1h move.", "The conclusions describe liquid alt perps. An all-market universe would be dominated by contracts nobody can trade and would answer a different question."),
    ("Ranking by volume is not ranking by cost.", "Some top-50 members have wide spreads; Phase 5 should assign per-contract costs instead of a single band."),
    ("Mid-month liquidity is ignored.", "A contract that becomes liquid during a month enters at the next month start, so entry can lag by up to a month."),
    ("The \"market\" in the market-neutral adjustment is the equal-weighted member basket.", "It is not a cap-weighted index, and it should be labelled as such."),
])
labelled("Cheap things we could add.",
         "A balanced subsample restricted to contracts present in at least 90% of the months, re-run "
         "through Experiments 1 and 3; and a K = 30 / K = 75 comparison, since the sample-size "
         "parameter is a single number in the pipeline.")
boxed("Suggested answer: \"The universe is point-in-time, rebalanced monthly on trailing 30-day "
      "traded volume, with an explicit 'still trading at month start' gate. It defines the estimand "
      "as liquid USD-M perpetuals, which is the note's own initial universe, and every headline cell "
      "survives dropping the five most influential contracts.\"")

h2("6.2  Are the lookback windows and threshold schemes in the three labels acceptable?")
labelled("What we do.",
         "Regimes: each contract's own trailing 90 calendar days, 70th percentile on |price change| "
         "and |OI change|, 30 days of minimum history; a six-point percentile scan and a matched "
         "z-score alternative. Funding: the same 90 and 30 days, computed on the settlement series at "
         "p25, p75 and p90. Market state: cross-sectional median of (high " + MINUS + " low) / close, "
         "24-hour smoothing, cut at the trailing one-year 1/3 and 2/3 quantiles.")
labelled("Why I think it is acceptable.",
         "The thresholds are contract-specific and time-varying, so they are already scale-free: a 1% "
         "hourly move is an outlier in BTC and ordinary in a small cap, and a fixed threshold would "
         "turn the label into a market-cap proxy. Ninety days is about 2,160 hourly observations, "
         "enough for a stable 70th percentile; shorter windows are noisy and longer ones straddle "
         "regime changes. Most importantly the threshold was fixed before any result was computed and "
         "the scan shows it is not doing hidden work: from p55 to p80 the labelling rate falls from "
         "23.0% to 7.5% while the composition of the labelled set moves by only 2 to 4 percentage "
         "points. The z-score method, matched on labelling rate, reproduces the same composition, so "
         "the result is not an artefact of the percentile rule.")
labelled("What it does not cover.", "Four points.")
numbered([
    ("The joint condition is not an independent 2x2.", "The two thresholds are separate marginal percentiles and price and OI changes are correlated, so \"both exceed\" is not 9% of rows and the four cells are far from equal in size (R4 307k against R3 164k at 1h). This matters for comparing precision across cells, not for the validity of the labels."),
    ("The rule is a magnitude threshold, not a relative one.", "A +3% move with +0.3% OI qualifies if both clear their own p70, even though the OI move is small relative to the price move."),
    ("Trailing windows are self-referential.", "A recently volatile period raises the threshold afterwards, so event frequency falls after a volatile month. This is inherent to trailing thresholds and should be stated once in the report."),
    ("4h and 8h labels have not been run.", "They exist and the generator is frequency-agnostic; rebuilding is roughly 40 minutes plus 10 minutes of estimation, and it is the most direct test of whether the 1h threshold is doing something special."),
])
boxed("Suggested answer: \"Thresholds are each contract's own trailing 90-day 70th percentile, fixed "
      "before the results. The p55-to-p80 scan and a rate-matched z-score alternative show that only "
      "the sample size moves (23.0% to 7.5% of valid rows), not the composition (2 to 4 percentage "
      "points), so the threshold is not selecting the conclusion.\"")

h2("6.3  Is it acceptable to test regimes against their benchmark using a difference as the estimator?")
labelled("What we do.",
         "Experiments 1, 3 and 4 estimate beta in y = beta * D + contract and month fixed effects, "
         "where D marks the regime and the omitted group is the same-direction rows that also crossed "
         "the price threshold. Experiment 1b estimates a 2x2 and reports five linear combinations. "
         "Experiments 5 to 9 use pooled group-mean differences with no fixed effects. All standard "
         "errors are two-way clustered, and every family is BH-corrected and influence-checked.")
labelled("Why I think it is acceptable.",
         "The difference is the comparison the question requires. The note asks whether OI adds "
         "information over price alone, and the only way to isolate that is to hold the price "
         "condition fixed (same direction, same threshold crossing) and vary the OI condition; a level "
         "comparison would confound the two. The contrast is defined on the data rather than on a "
         "model: the comparison rows are real events, in the same contracts, in the same months. "
         "Differences are linear, so the clustered standard error and the t-statistic are exact and no "
         "bootstrap is required. And there are two benchmarks, not one: Experiment 8 compares the same "
         "regimes against random hours of the same contracts, so a null cannot be blamed on the choice "
         "of comparison group.")
labelled("What it does not cover, and should be disclosed.",
         "Four points, the second of which is the one I would raise myself.")
numbered([
    ("A difference is not a causal effect.", "The regime is not randomly assigned. The fixed effects absorb contract and month levels, not the size of the triggering move and not the level of past volatility."),
    ("The composition difference is measurable.", "Event rows sit further above their own threshold than the comparison rows (mean log(|" + DELTA + "p|/threshold) 0.70 against 0.49, i.e. trigger moves about 22% larger). Controlling for the trigger-move decile, R1's volatility premium falls from +24.4% to +14.1% (t 16.3), R3 from +12.3% to +7.8% and R4 from +9.9% to +1.2% (t 1.5). For volatility this is a material magnitude correction and it removes R4. The same control on the return side moves the betas by less than 1.6bp and keeps every sign (at 4 and 24 hours; the only inference that changes is R1 at 24h, t 1.48 to 2.37), so the composition issue is specific to the volatility result rather than to the study as a whole. I would add the control as a row in Experiment 3 rather than leave it in a footnote."),
    ("A zero difference means \"not distinguishable from zero\".", "It does not mean \"no effect\", and no equivalence test was run."),
    ("Sixteen cells at a time need correction.", "BH and drop5 are part of the design, not optional extras."),
])
boxed("Suggested answer: \"The estimator is the regime minus its same-direction above-threshold "
      "benchmark, with contract and month fixed effects. It is a difference for identification and an "
      "association rather than a causal effect, and the composition in trigger size is controlled in a "
      "robustness row rather than ignored.\"")

h2("6.4  The long-short constructions are not implementable and carry no transaction cost")
labelled("What we do.",
         "The note asks for four baselines, and Phase 3 compares them as long-short spreads: long R1 "
         "against short R4; long up against short down; long OI-up against short OI-down; and long high "
         "funding against short low funding. No transaction cost, no funding P&L, no capacity and no "
         "borrow constraint is applied.")
labelled("Why these are diagnostics rather than portfolios.", "Three reasons.")
numbered([
    ("Several legs are not tradeable as written.", "\"Long high funding / short low funding\" is not a pair of assets. Funding is a payment on a perpetual position, not a security, and the pair is a ranking device: its sign says whether the funding state sorts returns, not whether the pair could be run. The same applies to \"long R1 / short R4\", which is a statement about a joint state rather than two instruments."),
    ("The spreads ignore execution.", "They equal-weight overlapping events, with no limit on the number of simultaneous positions and no impact model."),
    ("The levels explain the near-zero spreads.", "At 8 and 24 hours all eight single legs have negative market-neutral means, so a spread of " + MINUS + "1.5bp is the difference of two negative numbers. A spread presented without its legs invites the conclusion that nothing happens, when the correct reading is that both sides underperform the pool similarly."),
])
labelled("Why cost-free is still the right test for Phase 3.",
         "The Phase 3 question is whether the difference is non-zero, not whether it is profitable. A "
         "spread whose zero-cost value is 1.5bp cannot survive a 4bp fee, so the conclusion does not "
         "depend on the cost estimate: it is robust to any non-negative cost. Adding costs at this "
         "stage would only make every number more negative and would not change a single decision. The "
         "note itself sequences the costed test into D4 and Phase 5.")
labelled("What must be said out loud.",
         "The cost band has to be stated rather than implied. Binance USD-M standard tier is 0.02% "
         "maker and 0.05% taker per side, so a round trip is 4bp maker-to-maker and 10bp if both legs "
         "take liquidity; the deck's \"4 to 5bp\" should appear with that assumption attached. Phase 4 "
         "and Phase 5 should then add per-contract costs, the funding payment over the holding window "
         "and a position cap, and the tables should carry the words \"diagnostic spread\" in their "
         "titles.")
boxed("Suggested answer: \"The long-short spreads are diagnostic: they ask whether the difference is "
      "non-zero before any execution constraint. Several legs, in particular high versus low funding, "
      "are not implementable as stated. The costed, capacity-constrained version is D4 and Phase 5, and "
      "the tables are labelled accordingly so that no reader mistakes them for a strategy.\"")

h2("6.5  Where I would spend the next two weeks")
body(
    "If the four answers above are accepted, the highest-value additions, in order, are: the "
    "trigger-move control as a row in Experiment 3; the 4h and 8h label runs; the by-year split; and "
    "the balanced-universe subsample. The first is a robustness row that closes the most likely "
    "challenge to the headline result. The next two are the robustness checks the note explicitly asks "
    "for and that the current phase defers. After that, Phase 4's regime-by-funding table is a design "
    "question rather than a computation question, and I would rather agree the design before running "
    "it.",
    indent=True,
)

# --------------------------------------------------------------------------
# appendix
# --------------------------------------------------------------------------
h1("Appendix A  Reproduction")
body("With the inputs on disk, the whole of Phase 3 rebuilds in about 6.6 minutes:", indent=True)
make_table(
    ["Command", "Time", "Output"],
    [
        ["python phase3_event/build.py forward --freq 1h", "57 s", "forward panel, 7,252,717 rows"],
        ["python phase3_event/build.py events --freq 1h", "48 s", "event table, 923,235 x 65"],
        ["python phase3_event/build.py panel", "29 s", "analysis panel, 8 columns, 18 gates"],
        ["python phase3_event/experiment/exp1_4.py", "86 s", "Experiments 1, 2, 3, 1b"],
        ["python phase3_event/experiment/exp5_9.py", "39 s", "Experiments 5, 6, 7, 9, 13"],
        ["python phase3_event/experiment/exp8_placebo.py", "23 s", "Experiment 8"],
        ["python phase3_event/experiment/descriptive.py", "45 s", "Experiments 4, 10, 11, 14"],
        ["python phase3_event/experiment/event_path.py", "2 s", "Experiment 12"],
        ["python phase3_event/experiment/robust_daily.py", "36 s", "Experiment 15"],
        ["python phase3_event/figures.py", "4 s", "15 figures"],
    ],
    widths=[8.6, 3.0, 5.0],
    font=8.5,
    header_font=8.5,
)
note(
    "Phase 1 rebuilds with phase1/run_phase1.py (steps 0-3 need network access). Phase 2 rebuilds with "
    "phase2_regime/regime_generator.py in about 53 minutes. All randomness is fixed in config.py: "
    "random_draws = 1000 and random_seed = 20240501."
)

h1("Appendix B  Where each number comes from")
make_table(
    ["Table", "File", "Used in"],
    [
        ["Experiments 1, 1b, 2, 3", "tables/freq=1h/exp1_4.parquet", "Section 4"],
        ["Experiments 5, 6, 7, 9, 13", "tables/freq=1h/exp5_9.parquet", "Section 4"],
        ["Experiment 8", "tables/freq=1h/placebo.parquet", "Section 4"],
        ["Experiment 4", "tables/freq=1h/rev_prob.parquet", "Section 4"],
        ["Experiments 10, 11", "tables/freq=1h/descriptive_core.parquet, descriptive_path.parquet", "Section 4"],
        ["Experiments 12 and 13", "tables/freq=1h/event_path.parquet, exp5_9.parquet", "Section 4"],
        ["Experiment 14", "tables/freq=1h/descriptive_by_symbol.parquet, descriptive_by_state.parquet", "Section 4"],
        ["Experiment 15", "tables/freq=1h/robust_daily.parquet, robust_daily_bycount.parquet", "Section 4"],
        ["Label counts and scan", "data/05_regime/tables/regime_counts.parquet, threshold_sensitivity.parquet", "Section 2"],
        ["Data quality", "data/04_qa/data_quality.md", "Section 1"],
    ],
    widths=[5.0, 8.6, 3.0],
    font=8.5,
    header_font=8.5,
)

h1("Appendix C  Units and conventions", new_page=True)
make_table(
    ["Term", "Convention"],
    [
        ["bp", "basis points; 1bp = 0.01%. Internally every estimate is a decimal, multiplied by 1e4 to print."],
        ["pp", "percentage points, used only for the reversal probability (Experiment 4)."],
        ["t / p / p_bh / t_drop5", "the clustered t; the two-sided p; the Benjamini-Hochberg adjusted p within the experiment's family; the t after removing the five most influential contracts."],
        ["cell", MINUS + "1 price did not cross; 0 price crossed but OI did not; 1-4 the four regimes."],
        ["h", "forward horizon in calendar hours (1, 4, 8, 24), not the label frequency."],
        ["Benchmark", "the same-direction rows that crossed the price threshold and are not the regime being tested. Never the market, never a random hour."],
        ["y_raw vs lrv", "y_raw is the market-neutral return used for all return tests; lrv is log realised volatility, neither neutralised nor winsorised, used for all volatility tests."],
    ],
    widths=[4.2, 12.4],
    font=8.5,
    header_font=8.5,
)

doc.save(OUT)
print("saved", OUT)
