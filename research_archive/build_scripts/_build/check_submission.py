# -*- coding: utf-8 -*-
"""Final acceptance check for the FTEC5910 planning submission.

Verifies, against the course outline requirements, that:
  * the report contains the five required elements as numbered sections;
  * the planning form keeps the official header fields and the three columns;
  * the midterm / final dates agree between the two documents;
  * the five phases of the industrial supervisor's test plan appear in the form;
  * the six deliverables D1-D6 appear in both documents;
  * the AI-use acknowledgement is present in both.
"""
import re
import sys
from docx import Document

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"
FORM = r"D:\Industrial Programme I\FTEC5910-20_Industrial_Project_Planning_Form_SUNYusu_FILLED.docx"

REQUIRED_ELEMENTS = ["Project Goals", "Significance of the Project",
                     "Problem Statement", "Proposed Solutions and Deliverables",
                     "Proposed Timeline"]


def all_text(path):
    d = Document(path)
    chunks = [p.text for p in d.paragraphs]
    for t in d.tables:
        for r in t.rows:
            for c in r.cells:
                chunks.append(c.text)
    return "\n".join(chunks), d


def main():
    fails, warns = [], []

    rep_txt, rep = all_text(REPORT)
    form_txt, form = all_text(FORM)

    # 1. five required elements as headings
    heads = [p.text for p in rep.paragraphs if p.style.name == "Heading 1"]
    for i, el in enumerate(REQUIRED_ELEMENTS, start=1):
        hit = any(h.startswith(f"{i}.") and el.split()[0] in h for h in heads)
        print(f"  [{'OK ' if hit else 'FAIL'}] report required element {i}: {el}")
        if not hit:
            fails.append(f"missing required element: {el}")

    # 2. planning form structure
    hdr = ["Task", "Expected achievements by the midterm",
           "Expected achievements by the final"]
    t = form.tables[-1]
    got = [c.text.strip() for c in t.rows[0].cells]
    ok_hdr = all(h in g for h, g in zip(hdr, got))
    print(f"  [{'OK ' if ok_hdr else 'FAIL'}] form column headers preserved: {got}")
    if not ok_hdr:
        fails.append("planning form column headers changed")
    print(f"  [{'OK ' if len(t.rows) == 7 else 'FAIL'}] form has 6 task rows "
          f"(got {len(t.rows) - 1})")
    if len(t.rows) != 7:
        fails.append("planning form row count")

    for field in ["Student Name & ID", "Project title", "Sponsoring Organisation",
                  "Industrial Supervisor"]:
        hit = field in form_txt
        print(f"  [{'OK ' if hit else 'FAIL'}] form header field: {field}")
        if not hit:
            fails.append(f"form header field missing: {field}")

    # 3. date agreement. The planning-submission date belongs to the report
    #    alone; the form's two achievement columns are keyed to midterm/final.
    for long_form, short_form, needs_form in [
            ("25 September 2026", "25 Sep 2026", False),
            ("23 October 2026", "23 Oct 2026", True),
            ("27 November 2026", "27 Nov 2026", True)]:
        a = long_form in rep_txt
        b = long_form in form_txt or short_form in form_txt
        print(f"  [{'OK ' if a else 'WARN'}] report states {long_form}")
        print(f"  [{'OK ' if b else 'WARN'}] form states {long_form} / {short_form}"
              if needs_form else "  [n/a ] planning-submission date is report-only")
        if not a:
            warns.append(f"report does not state {long_form}")
        if needs_form and not b:
            warns.append(f"form does not state {long_form}")

    # 4. five phases in the form
    for i in range(1, 6):
        hit = f"Phase {i} " in form_txt
        print(f"  [{'OK ' if hit else 'FAIL'}] form covers Phase {i}")
        if not hit:
            fails.append(f"Phase {i} missing from form")

    # 5. deliverables in both
    for i in range(1, 7):
        a, b = re.search(rf"\bD{i}\b", rep_txt), re.search(rf"\bD{i}\b", form_txt)
        print(f"  [{'OK ' if a and b else 'WARN'}] D{i} referenced in both documents")
        if not (a and b):
            warns.append(f"D{i} not referenced in both")

    # 6. AI acknowledgement
    for name, txt in (("report", rep_txt), ("form", form_txt)):
        hit = "Acknowledgement of AI tool use" in txt
        print(f"  [{'OK ' if hit else 'FAIL'}] {name} carries AI-use acknowledgement")
        if not hit:
            fails.append(f"{name}: AI acknowledgement missing")

    # 7. page budget sanity: body word count
    body_words = sum(len(p.text.split()) for p in rep.paragraphs)
    for tb in rep.tables:
        for r in tb.rows:
            for c in r.cells:
                body_words += len(c.text.split())
    print(f"  [{'OK ' if body_words < 9000 else 'WARN'}] body word count {body_words} "
          f"(limit 15 pages; ~700 words/page with tables)")
    if body_words >= 9000:
        warns.append("body may exceed the 15-page limit")

    print()
    print(f"RESULT: {len(fails)} failure(s), {len(warns)} warning(s)")
    for f in fails:
        print("  FAIL:", f)
    for w in warns:
        print("  WARN:", w)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
