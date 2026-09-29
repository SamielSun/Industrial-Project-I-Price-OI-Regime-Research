# -*- coding: utf-8 -*-
"""Repair the styles of the inserted Literature Review block.

The insertion helper cloned the anchor paragraph, so the body paragraphs came in
carrying Heading styles. This resets every paragraph in the block explicitly.
"""
import sys
from docx import Document

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"

LR_SUBHEADS = [
    "Perpetual pricing and the funding anchor",
    "Funding rates as a return predictor",
    "Open interest, positioning and liquidation dynamics",
    "Microstructure and the identification problem",
    "The gap this project occupies",
]

doc = Document(REPORT)

# locate the block: from the "Literature Review" heading to the next Heading 1
start = end = None
paras = doc.paragraphs
for i, p in enumerate(paras):
    if p.text.strip() == "Literature Review":
        start = i
        continue
    if start is not None and i > start and p.style.name == "Heading 1" \
            and p.text.strip().startswith(("4.", "5.")):
        end = i
        break

if start is None or end is None:
    sys.exit("could not locate the Literature Review block")

changed = 0
for p in paras[start:end]:
    t = p.text.strip()
    if not t:
        continue
    if t == "Literature Review":
        want = "Heading 1"
    elif t in LR_SUBHEADS:
        want = "Heading 2"
    else:
        want = "Normal"
    if p.style.name != want:
        p.style = want
        changed += 1
    # body paragraphs should not be bold; headings keep their style boldness
    if want == "Normal":
        for r in p.runs:
            r.bold = False
            r.italic = False

doc.save(REPORT)
print(f"restyled {changed} paragraph(s) in the Literature Review block")
for p in doc.paragraphs[start:end]:
    if p.text.strip():
        print(f"  [{p.style.name:10s}] {p.text.strip()[:90]}")
