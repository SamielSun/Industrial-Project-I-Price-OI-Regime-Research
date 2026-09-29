# -*- coding: utf-8 -*-
"""Add the missing significance subsection (2.3) to FTEC5910_PLAN.docx.

This is the only required element of the planning submission that had no
content: the heading "Significance" existed, but section 2 carried only the
literature review.
"""
import copy
import shutil
import sys
from docx import Document
from docx.text.paragraph import Paragraph

PLAN = r"D:\Industrial Programme I\FTEC5910_PLAN.docx"
BACKUP = r"D:\Industrial Programme I\_build\backup_PLAN_before_significance.docx"

HEADING = "2.3 Significance to the project and to the sponsoring organisation"

PARAS = [
    "The significance of the project is practical. Practitioners already read price moves through the "
    "sign of the open-interest change and treat the funding rate as a gauge of crowding, but they do so "
    "without a measured basis: no public study states how these joint states behave in forward returns, "
    "volatility or reversal on a liquid perpetual universe, under explicit benchmarks. This project "
    "supplies that basis for Theo Quant. It converts three free public series — price, open interest and "
    "the funding rate — into a state classification that a trading desk can inspect daily, and it "
    "answers a question the desk currently settles by conviction: whether a move accompanied by rising "
    "open interest is fresh positioning or the closing of existing positions.",

    "The second contribution is reusable infrastructure rather than a single result. The pipeline, the "
    "point-in-time universe ledger and the regime classifier are documented and reproducible from raw "
    "archives, so company researchers can apply them to other signals without rebuilding the data "
    "layer. Because every input is public and every step is scripted, the results are auditable by both "
    "the company and the academic supervisor from the same code and the same files.",

    "The expected outcome is deliberately not conditional on the signal working. The project produces a "
    "verdict stated against four explicit benchmarks and a time-varying cost model, so the result is "
    "either a measured basis for a widely used heuristic or a documented reason to retire it. Both are "
    "useful to a desk, and the negative branch is recorded rather than discarded.",
]


def main():
    shutil.copyfile(PLAN, BACKUP)
    print("backup:", BACKUP)

    doc = Document(PLAN)

    # anchor: the last paragraph of section 2.2
    anchor = None
    for p in doc.paragraphs:
        if p.text.strip().startswith("What makes the joint state worth measuring"):
            anchor = p
    if anchor is None:
        sys.exit("anchor paragraph (2.2 body) not found")

    # already present?
    if any(p.text.strip().startswith("2.3 Significance") for p in doc.paragraphs):
        sys.exit("section 2.3 already present — nothing to do")

    blocks = [HEADING] + PARAS
    cursor = anchor
    for i, text in enumerate(blocks):
        new_el = copy.deepcopy(anchor._p)
        cursor._p.addnext(new_el)
        new_p = Paragraph(new_el, cursor._parent)
        for r in list(new_p.runs):
            r._r.getparent().remove(r._r)
        new_p.add_run(text)
        cursor = new_p
    print(f"inserted {len(blocks)} paragraph(s) after section 2.2")

    doc.save(PLAN)
    print("saved:", PLAN)

    # ------------------------------------------------------------ verify -----
    d2 = Document(PLAN)
    print("\n--- section 2 and 3 as they now read ---")
    on = False
    for p in d2.paragraphs:
        t = p.text.strip()
        if t.startswith("2.1"): on = True
        elif t.startswith("4."): on = False
        if on and t:
            print(f"  [{p.style.name[:12]:12s}] {t[:105]}")

    txt = "\n".join(p.text for p in d2.paragraphs)
    for tb in d2.tables:
        for r in tb.rows:
            for c in r.cells:
                txt += "\n" + c.text
    print("\nword count:", len(txt.split()))
    print("has significance content:",
          "significance of the project is practical" in txt)


if __name__ == "__main__":
    main()
