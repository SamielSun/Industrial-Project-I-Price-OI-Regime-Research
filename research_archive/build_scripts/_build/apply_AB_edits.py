# -*- coding: utf-8 -*-
"""Apply the agreed A- and B-level corrections to FTEC5910_PLAN.docx.

Applied : A1 signal definition, A2 funding-state buckets, A3 universe,
          A5 citation check + References, B1 logic chain, B2 remove
          pre-registration wording, B3 drop multiplicity correction,
          B5 add "no edge", B6 align phase descriptions, B7 typo.
Skipped : A4 (user: no change), A6 (user: ignore), B4 (user: ignore),
          all C-level items.
"""
import copy
import shutil
import sys
from docx import Document

PLAN = r"D:\Industrial Programme I\FTEC5910_PLAN.docx"
BACKUP = r"D:\Industrial Programme I\_build\backup_PLAN_before_AB_edits.docx"

# ------------------------------------------------------------------- A1 ------
PHASE2_OPS = (
    "Compute price and open-interest change over a fixed lookback window N on the 1h, 4h and 8h "
    "series: price_change = close_t / close_(t-N) - 1 and oi_change = OI_t / OI_(t-N) - 1. Keep only "
    "meaningful moves using minimum thresholds, abs(price_change) > price_threshold and "
    "abs(oi_change) > oi_threshold, with the thresholds taken from expanding-window quantiles so that "
    "the label at t uses no information from after t. Classify each surviving observation into "
    "regime 1 (price up, OI up), regime 2 (price up, OI down), regime 3 (price down, OI up) or "
    "regime 4 (price down, OI down), and place observations that fail either threshold in an explicit "
    "undefined class rather than forcing them into a regime. Report a threshold sensitivity table "
    "across the 60th to 80th percentile range rather than a single tuned value."
)
PHASE2_OUT = (
    "Regime counts and frequencies by asset, by month and by market condition; the share of "
    "observations in the undefined class; and a threshold sensitivity table showing how regime "
    "frequencies move with the threshold choice."
)

# ------------------------------------------------------------------- A2 ------
FUNDING_STATES = (
    "Split each regime by four funding states defined as non-overlapping trailing-quantile buckets: "
    "negative (0–25), neutral (25–75), high (75–90) and extreme (90–100)."
)
PHASE4_OPS = (
    "Split each regime by four funding states defined as non-overlapping trailing-quantile buckets: "
    "negative (0–25), neutral (25–75), high (75–90) and extreme (90–100), computed point-in-time per "
    "contract, and separately for contracts on 4-hour and 8-hour funding schedules."
)
PHASE4_OUT = (
    "4 × 4 table of price/OI regimes against funding states with forward return and volatility per "
    "bucket, each cell reported with its observation count and with cells below a minimum sample size "
    "flagged as indicative only. Because the grid contains sixteen cells, per-cell results are "
    "reported as descriptive evidence and not as confirmatory tests."
)

# ------------------------------------------------------------------- A3 ------
PHASE1_OPS = (
    "Archive per dataset and symbol, collect hourly OHLCV, open interest, funding rates, volume and "
    "mark/index price if available, for Binance USDⓈ-M perpetual futures. The universe is BTCUSDT and "
    "ETHUSDT plus the 30–50 most liquid USDT-margined perpetual contracts, excluding stablecoin pairs, "
    "newly listed tokens with insufficient history, contracts whose open interest data is unreliable, "
    "and illiquid contracts where transaction costs dominate."
)
PHASE1_OUT = (
    "Clean panel dataset, missing-data report, data dictionary, coverage matrix by symbol and month, "
    "and the applied universe rule with the list of excluded contracts and the reason for each "
    "exclusion."
)
D1_CRITERIA = [
    "Binance public data pull (USDⓈ-M perpetual futures).",
    "Hourly OHLCV, positioning metrics (open interest), funding archive and mark/index data.",
    "Universe: BTCUSDT and ETHUSDT plus the 30–50 most liquid USDT-margined perpetuals; stablecoins, "
    "newly listed tokens with insufficient history, contracts with unreliable open interest data and "
    "illiquid contracts excluded.",
    "Parquet storage.",
    "Data dictionary.",
    "Coverage and gap report per symbol and per month.",
]

# ------------------------------------------------------------------- B1 ------
B1_BULLET = (
    "Microstructure explains the present, not the future. Order-book imbalance has strong "
    "contemporaneous explanatory power for short-horizon price changes (Cont, Kukanov and Stoikov, "
    "2014), while forward predictive power in crypto is scarce. This asymmetry is the reason any "
    "claimed predictive signal must be tested out-of-sample rather than asserted, and it is why this "
    "project separates contemporaneous description from forward prediction."
)

# ------------------------------------------------------------- B2 / B3 -------
D2_CRITERIA = [
    "Change calculation over a fixed lookback window N, threshold logic using expanding-window "
    "quantiles, and four-regime labels with an explicit undefined class.",
    "Threshold sensitivity table across the 60th to 80th percentile range.",
    "Four-regime label generator.",
]
D3_CRITERIA = [
    "Forward return (mean and median), hit rate, post-event realized volatility, and the three-way "
    "split of continuation / reversal / no edge, for every regime at 1h / 4h / 8h / 24h.",
    "Forward volatility.",
    "Path risk: maximum favourable excursion, maximum adverse excursion and drawdown.",
    "Price/OI signal × Funding interaction.",
]

# ------------------------------------------------------------- B5 ------------
PHASE3_OPS = (
    "For each regime, calculate average and median forward return, hit rate, volatility after event, "
    "and the three-way split of continuation / reversal / no edge, together with path risk (maximum "
    "favourable excursion, maximum adverse excursion and drawdown), at the 1h / 4h / 8h / 24h horizons."
)
PHASE3_OUT = (
    "Forward-return tables with observation counts, the continuation / reversal / no edge split per "
    "regime, event-study plots and regime comparison charts."
)

# ------------------------------------------------------------- A5 ------------
FUNDING_BULLET = (
    "Funding as a factor. Predictability of funding rates has been explored in public, including "
    "open-source replication work that tests whether funding rates predict returns without "
    "survivorship filters. Rather than duplicating that work, this project treats funding-only "
    "predictability as a baseline to beat and focuses on the joint price/open-interest state."
)
REFERENCES = [
    "Cont, R., Kukanov, A., & Stoikov, S. (2014). The Price Impact of Order Book Events. Journal of "
    "Financial Econometrics, 12(1), 47–88.",
    "Garcia Seuma, R. M. (2026). Measuring the engine of a liquidation cascade: subcritical branching "
    "inside a first-order transition. arXiv:2608.03616.",
    "He, S., Manela, A., Ross, O., & von Wachter, V. (2022). Fundamentals of Perpetual Futures. "
    "arXiv:2212.06888.",
    "OctopusTakopi (2026). funding-rate-alpha: Do funding rates predict returns? A survivorship-free "
    "test on 6.1M settlements across three venues [Open-source replication repository]. GitHub. "
    "https://github.com/OctopusTakopi/funding-rate-alpha (accessed 24 September 2026).",
    "Shynkevich, A. (2026). When the clock strikes: algorithmic trading in cryptocurrency markets. "
    "Applied Economics Letters. DOI: 10.1080/13504851.2026.2617499.",
]
REF_NOTE = (
    "Verification note. Author names, titles and identifiers above were checked against the publisher "
    "or repository record. The funding-rate alpha work is cited as an open-source replication rather "
    "than as a peer-reviewed paper, because no author attribution or formal publication record could "
    "be identified for it. Volume and page numbers for the Shynkevich article are to be confirmed "
    "from the publisher record before the final report."
)


# ----------------------------------------------------------------- helpers ---
def replace_para(p, text):
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    p.add_run(text)


def replace_cell(cell, lines):
    for extra in cell.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    first = cell.paragraphs[0]
    for r in list(first.runs):
        r._r.getparent().remove(r._r)
    first.add_run(lines[0])
    for line in lines[1:]:
        new_p = copy.deepcopy(first._p)
        first._p.addnext(new_p)
        from docx.text.paragraph import Paragraph
        para = Paragraph(new_p, cell)
        for r in list(para.runs):
            r._r.getparent().remove(r._r)
        para.add_run(line)
        first = para


def find_table(doc, header_prefix):
    for t in doc.tables:
        cells = [c.text.strip() for c in t.rows[0].cells]
        if cells[:len(header_prefix)] == header_prefix:
            return t
    return None


def main():
    shutil.copyfile(PLAN, BACKUP)
    print("backup:", BACKUP)
    doc = Document(PLAN)
    log = []

    # ---- A3: universe, on the phase table and D1 ----
    pt = find_table(doc, ["Phase", "Operations", "Output"])
    if pt is None:
        sys.exit("phase table not found")
    rows = {r.cells[0].text.strip(): r for r in pt.rows[1:]}
    for key, ops, out in [
            ("1. Data collection", PHASE1_OPS, PHASE1_OUT),
            ("2. Regime labelling inputs", PHASE2_OPS, PHASE2_OUT),
            ("3. Event study", PHASE3_OPS, PHASE3_OUT),
            ("4. Funding interaction", PHASE4_OPS, PHASE4_OUT)]:
        row = next((r for k, r in rows.items() if k.startswith(key.split(".")[0] + ".")), None)
        if row is None:
            log.append(f"MISS phase row {key}")
            continue
        replace_cell(row.cells[1], [ops])
        replace_cell(row.cells[2], [out])
    log.append("A1/A2/A3/B3/B5/B6: rewrote phases 1-4 (operations and outputs)")

    # ---- A3/B2/B5/B7: deliverables ----
    dt = find_table(doc, ["", "Deliverable", "Acceptance criteria"])
    if dt is None:
        sys.exit("deliverables table not found")
    mapping = {"D1": D1_CRITERIA, "D2": D2_CRITERIA, "D3": D3_CRITERIA}
    for r in dt.rows[1:]:
        code = r.cells[0].text.strip()
        if code in mapping:
            replace_cell(r.cells[2], mapping[code])
    log.append("A3/B2/B5/B7: rewrote D1, D2 and D3 acceptance criteria")

    # ---- B1: add the microstructure bullet after the perpetual-pricing one ----
    anchor = None
    for p in doc.paragraphs:
        if p.text.strip().startswith("Perpetual pricing. The no-arbitrage pricing"):
            anchor = p
            break
    if anchor is None:
        log.append("MISS perpetual-pricing bullet")
    else:
        new_el = copy.deepcopy(anchor._p)
        anchor._p.addnext(new_el)
        from docx.text.paragraph import Paragraph
        para = Paragraph(new_el, anchor._parent)
        replace_para(para, B1_BULLET)
        log.append("B1: inserted the microstructure logic-chain bullet")

    # ---- A5: replace the unverifiable citation ----
    hit = 0
    for p in doc.paragraphs:
        if p.text.strip().startswith("Funding as a factor is already covered in public"):
            replace_para(p, FUNDING_BULLET)
            hit += 1
    log.append(f"A5: replaced the unverifiable funding citation in {hit} paragraph(s)")

    # ---- A5: References section ----
    tail = [p for p in doc.paragraphs if p.text.strip()]
    if tail and tail[-1].text.strip().startswith("5. Proposed Timeline"):
        style = tail[-1].style
    else:
        style = None
    last_el = tail[-1]._p
    blocks = ["6. References"] + REFERENCES + [REF_NOTE]
    cur = last_el
    for i, text in enumerate(blocks):
        new_el = copy.deepcopy(last_el)
        cur.addnext(new_el)
        from docx.text.paragraph import Paragraph
        para = Paragraph(new_el, doc)
        replace_para(para, text)
        if style is not None and i == 0:
            para.style = style
        cur = new_el
    log.append("A5: appended section 6 References with verification note")

    doc.save(PLAN)
    print("saved:", PLAN)
    for line in log:
        print("  ", line)


if __name__ == "__main__":
    main()
