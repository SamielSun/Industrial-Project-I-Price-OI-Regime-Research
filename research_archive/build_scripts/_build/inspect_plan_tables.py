# -*- coding: utf-8 -*-
"""Inspect the deliverables phase column and look for stray Phase 6 references."""
import re
import sys
from docx import Document

d = Document(r"D:\Industrial Programme I\FTEC5910_PLAN.docx")
t = next(x for x in d.tables
         if [c.text.strip() for c in x.rows[0].cells][1:3] == ["Deliverable", "Acceptance criteria"])

print("--- deliverables table: Phase column ---")
for r in t.rows:
    print(f"  {r.cells[0].text.strip():4s} {r.cells[1].text.strip()[:34]:36s} "
          f"-> Phase {r.cells[3].text.strip()}")

hits = []
for p in d.paragraphs:
    if re.search(r"Phase 6", p.text):
        hits.append(("para", p.text.strip()[:110]))
for x in d.tables:
    for r in x.rows:
        for c in r.cells:
            if re.search(r"Phase 6", c.text):
                hits.append(("cell", c.text.strip()[:110]))

print(f"\nremaining 'Phase 6' mentions: {len(hits)}")
for k, h in hits:
    print("  ", k, h)

# also: how many phases does each source table claim?
print("\n--- phase counts ---")
for i, x in enumerate(d.tables):
    head = " | ".join(c.text.strip()[:20] for c in x.rows[0].cells)
    print(f"  table {i}: {len(x.rows) - 1} data rows  [{head}]")
