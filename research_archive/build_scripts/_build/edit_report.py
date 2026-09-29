# -*- coding: utf-8 -*-
"""Apply the revised 1.2, the merged 2.2.2/2.2.3, the new problem statement and a
Literature Review section directly into the report docx.

Paragraph text is built from (text, bold) segments so that the bold lead labels
("RQ1 (classification). ", "Central hypothesis: ") survive the rewrite.
"""
import copy
import shutil
import sys
from docx import Document
from docx.shared import Pt

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"
BACKUP = r"D:\Industrial Programme I\_build\backup_before_edits.docx"

# --------------------------------------------------------------- new text ----
CENTRAL_NULL = [
    ("Central hypothesis: ", True),
    ("price moves accompanied by meaningful open-interest changes contain more information than price "
     "moves alone. ", False),
    ("Null hypothesis: ", True),
    ("price/OI regimes do not improve the prediction of future returns, volatility or reversal "
     "behaviour relative to simple price momentum alone. The three questions below are ordered so that "
     "none depends on a study that has not yet run.", False),
]
RQ1 = [
    ("RQ1 (classification). ", True),
    ("Do the four price/open-interest regimes occur often enough, and differ enough in their forward "
     "outcomes, to be worth conditioning on? Measured by regime frequencies at the three labelling "
     "frequencies (1h / 4h / 8h), and by forward-return distributions, hit rates, post-event realized "
     "volatility, and the three-way split of continuation / reversal / no edge at the four horizons "
     "1h / 4h / 8h / 24h, together with path risk (maximum favourable excursion, maximum adverse "
     "excursion, drawdown).", False),
]
RQ2_LEAD = [
    ("RQ2 (conditioning). ", True),
    ("Does the funding state change what a regime means?", False),
]
RQ2A = ("RQ2a — Does the regime's forward outcome differ across funding states? This is the 4 × 4 grid "
        "of the idea note: four price/OI regimes crossed with four funding states.")
RQ2B = ("RQ2b — Crowding, with the predicted signs fixed in advance: after Price Up + OI Up in the "
        "extreme positive funding state, does the forward return turn negative (crowded reversal)? "
        "After Price Down + OI Up in the extreme negative funding state, does it turn positive "
        "(short-squeeze)? And does Price Down + OI Down revert faster after funding stress than "
        "unconditionally (deleveraging mean-reversion)?")
RQ2_NOTE = ("Note on the funding buckets: the four states are defined as non-overlapping "
            "trailing-quantile buckets (0–25 / 25–75 / 75–90 / 90–100) rather than the idea note's "
            "nested thresholds (above the 75th and above the 90th). Nested thresholds cannot produce a "
            "mutually exclusive 4 × 4 grid, and the idea note's own expected-behaviour table requires "
            "an extreme-negative bucket that its definition does not create.")
RQ3 = [
    ("RQ3 (verdict). ", True),
    ("Does the price/OI joint classification beat the four baselines — (i) price momentum alone; "
     "(ii) OI change alone; (iii) funding alone; (iv) random event timing — on identical samples, and "
     "does the incremental information survive realistic, time-varying transaction costs? Statistical "
     "significance and economic significance are reported separately, so that a regime which predicts "
     "returns but not net of costs is recorded as such.", False),
]
RULE = ("Rules fixed in advance: the full four-regime label set, the direction thresholds, the lookback "
        "length and the funding buckets are pre-registered in Appendix C and are not varied between "
        "specifications. Only outcomes are reported below; the baseline itself is never selected after "
        "seeing a result.")
DEPEND = ("The dependency structure is deliberate. RQ1 establishes whether the object of study exists in "
          "the data at usable frequency. RQ2 asks whether the conditioning variable, the funding rate, "
          "earns its place. RQ3 answers the core question: do joint positioning states contain "
          "predictive information beyond price alone?")

PROBLEM_STMT = (
    "The idea note states a research question and a test plan; it does not state the problem those "
    "exist to solve. That problem begins with a mechanical fact about perpetual futures. Open interest "
    "increases only when positions are opened and falls only when they are closed, so a price move on "
    "rising open interest is a different market event from the same price move on falling open "
    "interest, even though the two are identical in every price-based description. Funding rates add a "
    "second dimension, pricing the cost of carrying leveraged positioning and therefore indicating how "
    "crowded that positioning has become. The practical consequence is a costly ambiguity. A desk "
    "observing a strong move cannot tell from price alone whether new positions are being established "
    "or existing ones closed, and therefore cannot judge whether the move is likely to continue, to "
    "reverse, or to overshoot as forced positions are liquidated; nor whether high funding marks "
    "sustainable demand or a crowded trade about to unwind. Signals built on these states are "
    "consequently traded on faith or discarded, and because the states are rarely measured against "
    "explicit baselines under realistic costs, the negative results that would settle the question are "
    "not recorded either. This project addresses that problem: it classifies the joint price and "
    "open-interest state at hourly frequency on a point-in-time universe of liquid contracts, "
    "conditions the classification on the funding state, and measures forward returns, volatility and "
    "reversal against four benchmarks under a pre-declared cost model."
)

MERGED_222 = (
    "Open interest is widely used in practice as a crowding indicator, but the evidence treats it "
    "unsatisfyingly: mostly in isolation rather than jointly with price, mostly on aggregate or "
    "retail-derived positioning rather than on exchange-reported open interest for a point-in-time "
    "universe of contracts, and with its interaction with the funding state asserted rather than "
    "measured. That last omission is the one the idea note puts at the centre, and the ambiguity it "
    "leaves behind is stated as the problem in section 3."
)
MERGED_223 = [
    ("The contribution claimed is one of measurement and validity rather than alpha: ", True),
    ("a joint price/OI classification for a liquid perpetual universe, with alignment and "
     "universe-construction decisions documented and data-confidence flags propagated into every "
     "reported statistic; a funding-conditional version of that classification tested under an explicit "
     "multiple-testing correction, which converts a practitioner heuristic into a measurable quantity; "
     "a separation of predictability from profitability on identical samples and identical costs, so "
     "that a regime which predicts returns but not net of costs is a reportable first-class outcome "
     "rather than a caveat; and a reproducible negative-result asset, in which every input is a free "
     "public archive, the pipeline runs from raw files, and the rejected specifications are recorded "
     "alongside the accepted ones.", False),
]

LR_TITLE = "Literature Review"
LR_INTRO = ("This review covers the four strands the project builds on, states what each establishes, "
            "and ends with the gap the project occupies. It is organised by what is settled and what is "
            "not, rather than by chronology.")
LR = [
    ("Perpetual pricing and the funding anchor", [
        "The no-arbitrage pricing of perpetual futures and the funding mechanism that tethers the "
        "perpetual to spot are settled, including the trading-cost bounds within which the tether holds "
        "(He, Manela, Ross and von Wachter, 2022). Two consequences matter here. Funding is a price "
        "anchor by construction rather than a sentiment gauge, which is why this project treats it as a "
        "conditioning variable rather than a directional signal. And the tether is enforced only to the "
        "extent that arbitraging the deviation costs less than the deviation itself, so any statement "
        "about funding has to be made relative to a cost assumption."]),
    ("Funding rates as a return predictor", [
        "Systematic work on funding rates as a return predictor already exists in public, "
        "survivorship-aware form, covering millions of settlements across venues (funding-rate alpha "
        "study, 2026). This strand supplies both a benchmark and a discipline: tests are run without "
        "survivorship filters and at settlement level rather than daily level. Funding-only "
        "predictability is therefore treated here as a baseline to beat rather than a finding to "
        "reproduce."]),
    ("Open interest, positioning and liquidation dynamics", [
        "This is the strand closest to the project, and it cuts both ways. Forced selling during "
        "liquidation cascades has now been measured directly: across seven major crypto-perpetual "
        "cascades between 2022 and 2025, open interest clears by 25–70% during the event, and severity "
        "is governed by the interaction of shock timing, position in the price path and liquidity "
        "withdrawal rather than by a diverging multiplier (Garcia Seuma, 2026). That is direct evidence "
        "that the open-interest-down, price-down state is real and economically large, which supports "
        "the interpretation attached to regime 4.",
        "Against that, the same study reports that none of the scalar pre-cascade state measures it can "
        "construct grades the severity of the event, and that a branching-process account of the "
        "pre-cascade state is rejected on both of its falsifiable predictions. Positioning-based "
        "quantities therefore have a weak record as ex ante crisis predictors. This is precisely why "
        "the present study is specified as an event study of the contemporaneous state — what the joint "
        "price and open-interest configuration implies for the next one to twenty-four hours — rather "
        "than as an attempt to forecast crises."]),
    ("Microstructure and the identification problem", [
        "Two further results constrain how the study must be run. Order-book imbalance explains "
        "contemporaneous short-horizon price changes strongly (Cont, Kukanov and Stoikov, 2014), while "
        "forward predictive power in crypto is scarce; that asymmetry is why any claimed signal must be "
        "tested out-of-sample rather than asserted. And clock effects are documented in this market: "
        "minute-boundary and settlement-boundary trading clustering has been measured on Binance, more "
        "strongly in spot than in perpetuals (Shynkevich, 2026). Because the regimes here are sampled "
        "on the hour and funding settles at 00/08/16 UTC, that literature is a direct threat to naive "
        "inference and is treated as a control rather than as background. Standard event-study and "
        "cost-estimation anchors apply (MacKinlay, 1997; Roll, 1984; Corwin and Schultz, 2012), and the "
        "multiple-testing problem is handled with conventional corrections (Harvey, Liu and Zhu, 2016; "
        "Bailey and López de Prado, 2014)."]),
    ("The gap this project occupies", [
        "Three things are missing from the literature reviewed here, and they are missing together "
        "rather than separately. First, joint treatment: open interest and funding are studied as "
        "separate factors, and the four-way classification of price direction against open-interest "
        "direction is not tested as such. Second, data quality: positioning evidence rests largely on "
        "aggregate or retail-derived series rather than exchange-reported open interest for a "
        "point-in-time universe of contracts, which exposes any backward-looking study to survivorship "
        "bias in exactly the episodes the regimes are meant to capture. Third, the funding interaction: "
        "practitioner material treats funding as a leverage thermometer and asserts that crowded "
        "positioning reverses, but the claim is rarely measured under a pre-declared multiplicity "
        "family with documented data alignment.",
        "This project contributes a joint price/OI regime classification conditioned on funding state, "
        "tested on a point-in-time universe built from archive listings, with alignment and confidence "
        "decisions documented and propagated into every reported statistic. Predictability is separated "
        "from profitability on identical samples and identical costs, and the crowding hypotheses are "
        "pre-registered with their signs fixed in advance. The claim is not that a new source of alpha "
        "has been found, but that a widely used practitioner heuristic is either given a measured basis "
        "or retired."]),
]


# ----------------------------------------------------------------- helpers ---
def find(doc, prefix):
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            return p
    return None


def write(p, segments):
    """Replace a paragraph's content with (text, bold) segments."""
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    for text, bold in segments:
        r = p.add_run(text)
        r.bold = bold


def write_plain(p, text, size=None, italic=False):
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    r = p.add_run(text)
    r.italic = italic
    if size:
        r.font.size = Pt(size)


def insert_after(anchor_p, text, style=None, size=None, italic=False):
    """Splice a new paragraph immediately after anchor_p, matching its style."""
    new_el = copy.deepcopy(anchor_p._p)
    anchor_p._p.addnext(new_el)
    from docx.text.paragraph import Paragraph
    new_p = Paragraph(new_el, anchor_p._parent)
    for r in list(new_p.runs):
        r._r.getparent().remove(r._r)
    r = new_p.add_run(text)
    r.italic = italic
    if size:
        r.font.size = Pt(size)
    if style is not None:
        new_p.style = style
    return new_p


def main():
    shutil.copyfile(REPORT, BACKUP)
    print("backup:", BACKUP)
    doc = Document(REPORT)
    log, miss = [], []

    # ---- 1.2 rewrites ----
    for prefix, segs, tag in [
            ("The idea note specifies a hypothesis", CENTRAL_NULL, "central+null hypothesis"),
            ("RQ1 (classification)", RQ1, "RQ1"),
            ("RQ2 (conditioning)", RQ2_LEAD, "RQ2 lead"),
            ("RQ3 (verdict)", RQ3, "RQ3"),
            ("The dependency structure is deliberate", [(DEPEND, False)], "dependency paragraph")]:
        p = find(doc, prefix)
        if p is None:
            miss.append(tag)
            continue
        write(p, segs)
        log.append(f"rewrote {tag}")

    # ---- RQ2a / RQ2b / bucket note ----
    rq2 = find(doc, "RQ2 (conditioning)")
    if rq2 is not None:
        b = insert_after(rq2, RQ2B, style="List Bullet")
        a = insert_after(rq2, RQ2A, style="List Bullet")
        insert_after(b, RQ2_NOTE, size=9, italic=True)
        log.append("inserted RQ2a, RQ2b, funding-bucket note")
    else:
        miss.append("RQ2 anchor for bullets")

    dep = find(doc, "The dependency structure is deliberate")
    if dep is not None:
        insert_after(dep, RULE, size=9.5, italic=True)
        log.append("inserted pre-registration rule paragraph")

    # ---- problem statement ----
    ps = find(doc, "The idea note states")
    if ps is None:
        miss.append("problem statement opening")
    else:
        write_plain(ps, PROBLEM_STMT)
        log.append("rewrote problem statement opening (§3)")

    # ---- 2.2.2 / 2.2.3 merge ----
    p222 = find(doc, "Open interest is widely used in practice")
    if p222 is None:
        miss.append("2.2.2 paragraph")
    else:
        write_plain(p222, MERGED_222)
        log.append("rewrote 2.2.2")

    # drop the stale blocks, remembering the anchor slot for the merged text
    stale_prefixes = (
        "The joint state is exactly the object",
        "The joint state is worth studying",
        "2.2.3",
        "The contribution is deliberately modest",
        "The contribution claimed is one of measurement and validity",
    )
    slot = None
    victims = []
    for p in doc.paragraphs:
        t = p.text.strip()
        if t.startswith("The joint state is exactly the object") and slot is None:
            slot = p._p            # the merged contribution goes here
        if t.startswith(stale_prefixes):
            victims.append(p)
    for p in victims:
        p._p.getparent().remove(p._p)
    log.append(f"removed {len(victims)} stale 2.2.2/2.2.3 block(s)")

    if slot is not None:
        new_el = copy.deepcopy(p222._p) if p222 is not None else copy.deepcopy(slot)
        slot.addprevious(new_el)
        from docx.text.paragraph import Paragraph
        new_p = Paragraph(new_el, doc)
        for r in list(new_p.runs):
            r._r.getparent().remove(r._r)
        for text, bold in MERGED_223:
            r = new_p.add_run(text)
            r.bold = bold
        log.append("inserted merged 2.2.3 contribution paragraph")
    else:
        miss.append("slot for merged contribution")

    # ---- literature review, spliced after section 3.4 ----
    body = None
    for p in doc.paragraphs:
        if p.text.strip().startswith("The obvious objection is that a single-venue study"):
            body = p
            break
    if body is None:
        miss.append("PR anchor for Literature Review (section 3.4 body)")
    else:
        cur = body
        cur = insert_after(cur, LR_TITLE, style="Heading 1")
        cur = insert_after(cur, LR_INTRO)
        for head, paras in LR:
            cur = insert_after(cur, head, style="Heading 2")
            for pt in paras:
                cur = insert_after(cur, pt)
        log.append("inserted Literature Review after section 3.4")

    doc.save(REPORT)
    print("saved:", REPORT)
    for line in log:
        print("  ", line)
    if miss:
        print("MISSES:", miss)
    return 1 if miss else 0


if __name__ == "__main__":
    sys.exit(main())
