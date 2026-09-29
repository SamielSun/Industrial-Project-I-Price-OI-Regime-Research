# -*- coding: utf-8 -*-
"""Small consistency touches: capitalise the pre-registered bullet leads in 4.4
and note the Literature Review in the Appendix D compliance map."""
import sys
from docx import Document

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"

LEAD_FIXES = {
    "Frequency. primary bars": "Frequency. Primary bars",
    "Lookback. the lookback": "Lookback. The lookback",
    "Thresholds. thresholds are": "Thresholds. Thresholds are",
    "Regimes. four regimes": "Regimes. Four regimes",
    "Horizons. 1h, 4h": "Horizons. 1h, 4h",
    "Multiplicity. the multiplicity": "Multiplicity. The multiplicity",
    "Dependence. inference uses": "Dependence. Inference uses",
}

doc = Document(REPORT)
fixed = 0
for p in doc.paragraphs:
    t = p.text
    for old, new in LEAD_FIXES.items():
        if t.startswith(old):
            # only the first run carries the bold lead
            if p.runs and p.runs[0].text.startswith(old.split(".")[0] + "."):
                head, _, tail = p.runs[0].text.partition(". ")
                p.runs[0].text = head + ". " + tail[:1].upper() + tail[1:]
                fixed += 1
            break
print(f"capitalised {fixed} bullet lead(s)")

# Appendix D: add the literature-review row
target = None
for t in doc.tables:
    for row in t.rows:
        if row.cells[0].text.strip().startswith("Proposed timeline"):
            target = t
            break
    if target is not None:
        break
if target is None:
    print("Appendix D table not found")
else:
    row = target.add_row()
    row.cells[0].text = "Literature review (prepared ahead of the Term 2 draft)"
    row.cells[1].text = ("A Literature Review section is already included in this plan, covering "
                         "perpetual pricing, funding as a predictor, open-interest and liquidation "
                         "dynamics, the identification problem, and the gap the project occupies")
    print("added Appendix D row for the literature review")

doc.save(REPORT)
print("saved")
