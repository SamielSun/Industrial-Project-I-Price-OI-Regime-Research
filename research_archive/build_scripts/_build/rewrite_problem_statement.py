# -*- coding: utf-8 -*-
"""Replace the section 3 opening with a self-contained problem statement that
does not refer to, or evaluate, the source idea note."""
import copy
import sys
from docx import Document
from docx.text.paragraph import Paragraph

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"

OLD_PREFIX = "The idea note states a research question and a test plan"

PARAS = [
    "Perpetual futures markets publish, for every liquid contract, three quantities that are cheap to "
    "obtain and central to how positioning is read: the direction of price, the direction of open "
    "interest, and the funding rate that prices the cost of holding a leveraged position. These "
    "quantities are informative because of a mechanical asymmetry. Open interest rises only when "
    "positions are opened and falls only when they are closed, so a price move accompanied by rising "
    "open interest and the same move accompanied by falling open interest are different market events, "
    "even though they are indistinguishable in any description based on price alone.",

    "The problem is that this distinction is used far more often than it is measured. Practitioners "
    "read a price move on rising open interest as fresh positioning and the same move on falling open "
    "interest as unwinding, and read a high funding rate as either durable demand or a crowded trade "
    "about to reverse, but the evidence behind those readings is fragmentary: open interest and funding "
    "are studied largely as separate factors, frequently on aggregate or retail-derived positioning "
    "series, and rarely conditioned on one another.",

    "The consequence is operational. A trader observing a strong move cannot tell whether new positions "
    "are being established or existing ones closed, and therefore cannot judge whether the move is "
    "likely to continue, to reverse, or to overshoot as leveraged positions are liquidated; nor whether "
    "high funding marks sustainable demand or an imminent unwind. Without measured benchmarks, such "
    "signals are either traded on conviction alone or discarded, and the results that would settle the "
    "question, including negative ones, are not produced.",

    "This project addresses that problem. It makes the joint state of price, open interest and funding "
    "measurable at hourly frequency across a liquid universe of perpetual contracts, and asks which "
    "combinations, if any, carry information about subsequent returns, volatility and reversal.",
]

doc = Document(REPORT)

anchor = None
for p in doc.paragraphs:
    if p.text.strip().startswith(OLD_PREFIX):
        anchor = p
        break
if anchor is None:
    sys.exit("section 3 opening paragraph not found")

# rewrite the opening paragraph in place
for r in list(anchor.runs):
    r._r.getparent().remove(r._r)
anchor.add_run(PARAS[0])

# splice the remaining paragraphs directly after it
cursor = anchor
for text in PARAS[1:]:
    new_el = copy.deepcopy(anchor._p)
    cursor._p.addnext(new_el)
    new_p = Paragraph(new_el, cursor._parent)
    for r in list(new_p.runs):
        r._r.getparent().remove(r._r)
    new_p.add_run(text)
    cursor = new_p

doc.save(REPORT)
print("section 3 opening replaced with", len(PARAS), "paragraphs")
print("word count:", sum(len(t.split()) for t in PARAS))

# ------------------------------------------------------------------ verify ---
d2 = Document(REPORT)
print("--- section 3 as it now reads (headings + first 90 chars) ---")
on = False
for p in d2.paragraphs:
    t = p.text.strip()
    if t.startswith("3.  Problem Statement"):
        on = True
    elif t.startswith("Literature Review"):
        on = False
    if on and t:
        tag = p.style.name
        print(f"  [{tag:12s}] {t[:96]}")
