# -*- coding: utf-8 -*-
"""Finalise the filled planning form: ensure the Academic Supervisor line is
present (the official template has no such line, but the PLAN cover states one),
then run an integrity check on all five header fields and the task table.
"""
import copy
import shutil
import sys
from docx import Document
from docx.shared import Pt
from docx.text.paragraph import Paragraph

FORM = r"D:\Industrial Programme I\FTEC5910-20_Industrial_Project_Planning_Form_SUNYusu_FILLED.docx"
BACKUP = r"D:\Industrial Programme I\_build\backup_form_before_academic.docx"

LABEL, VALUE = "Academic Supervisor:", "Prof. WU Xixin"

doc = Document(FORM)
present = [p.text.strip() for p in doc.paragraphs]

if any(t.startswith(LABEL) for t in present):
    print("academic line already present")
else:
    shutil.copyfile(FORM, BACKUP)
    anchor = None
    for p in doc.paragraphs:
        if p.text.strip().startswith("Industrial Supervisor:"):
            anchor = p
            break
    if anchor is None:
        sys.exit("anchor 'Industrial Supervisor:' not found")
    new_el = copy.deepcopy(anchor._p)
    anchor._p.addnext(new_el)
    np = Paragraph(new_el, anchor._parent)
    for r in list(np.runs):
        r._r.getparent().remove(r._r)
    np.add_run(LABEL)
    r = np.add_run(" " + VALUE)
    r.font.size = Pt(12)
    doc.save(FORM)
    print("inserted the academic-supervisor line; backup:", BACKUP)

# ------------------------------------------------------------- verification --
d = Document(FORM)
paras = [p.text.strip() for p in d.paragraphs if p.text.strip()]
print("\n--- header ---")
for t in paras:
    print("  ", t[:130])

checks = {
    "Student Name & ID": "SUN Yusu (1155267751)",
    "Project title": "Price and Open-Interest Regimes",
    "Sponsoring Organisation": "Theo Quant Limited",
    "Industrial Supervisor": "Mr. Jackson Wong",
    "Academic Supervisor": "Prof. WU Xixin",
}
print("\n--- field checks ---")
ok = True
for label, frag in checks.items():
    hit = any(t.startswith(label) and frag in t for t in paras)
    ok &= hit
    print(f"  [{'OK ' if hit else 'FAIL'}] {label}")

t = d.tables[0]
print(f"\n--- table: {len(t.rows)} rows x {len(t.columns)} cols, style {t.style.name} ---")
print("  header:", [c.text.strip() for c in t.rows[0].cells])
for ri, row in enumerate(t.rows[1:], 1):
    task = row.cells[0].text.strip().split("\n")[0]
    filled = all(c.text.strip() for c in row.cells)
    print(f"  [{'OK ' if filled else 'FAIL'}] row {ri}: {task[:70]}")
    ok &= filled

print("\nRESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
