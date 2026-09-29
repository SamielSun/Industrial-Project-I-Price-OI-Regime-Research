# -*- coding: utf-8 -*-
"""Final tidy on FTEC5910_PLAN.docx, on the user's instruction:

  * shorten the funding-as-a-factor bullet to one sentence and drop its
    dependence on the uncited replication repository;
  * delete the repository reference;
  * delete the Garcia Seuma reference, which was never cited in the text;
  * rewrite the verification note so it only covers what remains.
"""
import shutil
import sys
from docx import Document

PLAN = r"D:\Industrial Programme I\FTEC5910_PLAN.docx"
BACKUP = r"D:\Industrial Programme I\_build\backup_PLAN_before_ref_tidy.docx"

NEW_BULLET = ("Funding as a factor. Predictability of funding rates has been explored in public, so this "
              "project treats funding-only predictability as a baseline to beat rather than a finding "
              "to reproduce, and focuses instead on the joint price/open-interest state.")

DROP_PREFIXES = (
    "Garcia Seuma, R. M. (2026)",
    "OctopusTakopi (2026)",
)

NEW_NOTE = ("Verification note. Author names, titles and identifiers were checked against the publisher "
            "record. Volume and page numbers for the Shynkevich article are to be confirmed before the "
            "final report.")

doc = Document(PLAN)
shutil.copyfile(PLAN, BACKUP)
print("backup:", BACKUP)

log = []

# ---- 1. shorten the funding bullet ----
hit = 0
for p in doc.paragraphs:
    if p.text.strip().startswith("Funding as a factor"):
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        p.add_run(NEW_BULLET)
        hit += 1
log.append(f"shortened the funding bullet ({hit} paragraph)")

# ---- 2. drop the two references and rewrite the note ----
removed = 0
for p in doc.paragraphs:
    t = p.text.strip()
    if t.startswith(DROP_PREFIXES):
        p._p.getparent().remove(p._p)
        removed += 1
    elif t.startswith("Verification note"):
        for r in list(p.runs):
            r._r.getparent().remove(r._r)
        p.add_run(NEW_NOTE)
        log.append("rewrote the verification note")
log.append(f"removed {removed} reference(s)")

doc.save(PLAN)
print("saved:", PLAN)
for line in log:
    print("  ", line)

# ------------------------------------------------------------------ verify ---
d2 = Document(PLAN)
print("\n--- section 2.1 bullets ---")
on = False
for p in d2.paragraphs:
    t = p.text.strip()
    if t.startswith("2.1"): on = True
    elif t.startswith("2.2"): on = False
    if on and t and not t.startswith("2.1"):
        print("  ·", t[:200])
print("\n--- references ---")
seen = False
for p in d2.paragraphs:
    t = p.text.strip()
    if t.startswith("6. References"): seen = True
    if seen and t:
        print("  ", t[:170])
