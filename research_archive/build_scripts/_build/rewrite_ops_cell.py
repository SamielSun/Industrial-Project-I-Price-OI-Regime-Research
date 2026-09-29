# -*- coding: utf-8 -*-
"""Rewrite the Phase 2 operations cell in the report's five-phase table.

The cell is the one text in Table 4.2 that is a stack of noun phrases rather
than an operation, which makes it read differently from every other row.

Writes in place when the file is free; otherwise leaves the edited copy at
TMP and prints where it is.
"""
import os
import shutil
import sys
import time
from docx import Document

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"
TMP = r"D:\Industrial Programme I\_build\_report_ops_edit.docx"

OLD_PREFIX = "Point-in-time universe ledger from archive listings"
NEW = ("Reconstruct the point-in-time universe from archive listings; align open interest to the price "
       "bar and flag low-confidence observations; attach funding to the settlement that charged it; "
       "compute forward returns and realized volatility at the four horizons")

# the same operations column also appears in the timeline table; keep it in step
OLD_TIMELINE = "Point-in-time universe ledger from archive listings; OI-to-bar alignment rule; funding attached to settlements; return and volatility panel"
NEW_TIMELINE = ("Reconstruct the point-in-time universe from archive listings; align open interest to "
                "the price bar and flag low-confidence observations; attach funding to the settlement "
                "that charged it; compute forward returns and realized volatility")


def edit(path):
    doc = Document(path)
    changed = []
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                text = c.text.strip()
                if text.startswith(OLD_PREFIX):
                    new = NEW_TIMELINE if text.startswith("Point-in-time universe ledger from "
                                                          "archive listings; OI-to-bar") else NEW
                    for extra in c.paragraphs[1:]:
                        extra._p.getparent().remove(extra._p)
                    para = c.paragraphs[0]
                    for r in list(para.runs):
                        r._r.getparent().remove(r._r)
                    para.add_run(new)
                    changed.append(new[:60])
    doc.save(path)
    return changed


free = False
for attempt in range(3):
    try:
        handle = open(REPORT, "r+b")
        handle.close()
        free = True
        break
    except PermissionError:
        time.sleep(3)

if free:
    changed = edit(REPORT)
    print(f"edited in place: {REPORT}")
else:
    shutil.copyfile(REPORT, TMP)
    changed = edit(TMP)
    print(f"report is locked by Word; edited copy left at:\n  {TMP}")

print(f"rewrote {len(changed)} cell(s):")
for c in changed:
    print("   ", c)

# ------------------------------------------------------------------ verify ---
target = REPORT if free else TMP
d = Document(target)
print("\n--- Table 4.2, Operations column ---")
for ri, row in enumerate(d.tables[1].rows):
    print(f"  [{ri}] {row.cells[0].text.strip()[:32]:34s} {row.cells[1].text.strip()[:130]}")
