# -*- coding: utf-8 -*-
"""Re-insert the merged 2.2.3 contribution paragraph (it was removed when the
stale 2.2.3 numbering heading matched the same prefix)."""
import copy
import sys
from docx import Document
from docx.text.paragraph import Paragraph

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"
LEAD = "The contribution claimed is one of measurement and validity rather than alpha:"
BODY = ("a joint price/OI classification for a liquid perpetual universe, with alignment and "
        "universe-construction decisions documented and data-confidence flags propagated into every "
        "reported statistic; a funding-conditional version of that classification tested under an "
        "explicit multiple-testing correction, which converts a practitioner heuristic into a "
        "measurable quantity; a separation of predictability from profitability on identical samples "
        "and identical costs, so that a regime which predicts returns but not net of costs is a "
        "reportable first-class outcome rather than a caveat; and a reproducible negative-result asset, "
        "in which every input is a free public archive, the pipeline runs from raw files, and the "
        "rejected specifications are recorded alongside the accepted ones.")

doc = Document(REPORT)

# find the 2.2.2 body paragraph to anchor on
anchor = None
for p in doc.paragraphs:
    if p.text.strip().startswith("Open interest is widely used in practice as a crowding indicator"):
        anchor = p
        break
if anchor is None:
    sys.exit("anchor paragraph not found")

# already present?
for p in doc.paragraphs:
    if p.text.strip().startswith(LEAD):
        sys.exit("contribution paragraph already present — nothing to do")

new_el = copy.deepcopy(anchor._p)
anchor._p.addnext(new_el)
new_p = Paragraph(new_el, anchor._parent)
for r in list(new_p.runs):
    r._r.getparent().remove(r._r)
r1 = new_p.add_run(LEAD + " ")
r1.bold = True
r2 = new_p.add_run(BODY)
r2.bold = False

doc.save(REPORT)
print("re-inserted the merged 2.2.3 paragraph")

d2 = Document(REPORT)
print("--- 2.2 block, final ---")
on = False
for p in d2.paragraphs:
    t = p.text.strip()
    if t.startswith("2.2 "): on = True
    elif t.startswith("3. "): on = False
    if on and t:
        print(f"  [{p.style.name:11s}] {t[:118]}")
