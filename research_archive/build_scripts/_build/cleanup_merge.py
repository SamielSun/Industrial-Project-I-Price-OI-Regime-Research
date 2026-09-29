# -*- coding: utf-8 -*-
"""Clean-up pass after the 2.2 merge and align the funding-state wording."""
import copy
import sys
from docx import Document
from docx.text.paragraph import Paragraph

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"

OLD_LEAD = "The contribution is deliberately modest in kind"
OLD_ITEMS = (
    "A joint price/OI regime classification for a liquid perpetual universe, with the alignment",
    "A funding-conditional version of that classification (the 4 × 4 grid)",
    "A separation of predictability from profitability on identical samples",
    "A reproducible negative-result asset. Every input is a free public archive",
)
BUCKET_NOTE = ("Funding states are four non-overlapping trailing-quantile buckets — low (0–25), neutral "
               "(25–75), high (75–90) and extreme (90–100) — computed point-in-time, separately for "
               "contracts on 8-hour and 4-hour funding schedules.")
FUNDING_44 = [
    ("Funding states. ", True),
    ("four non-overlapping trailing-quantile buckets at the 25th, 75th and 90th percentiles — low "
     "(0–25), neutral (25–75), high (75–90), extreme (90–100) — computed point-in-time and separately "
     "for contracts on 8-hour and 4-hour schedules;", False),
]
REPLACEMENTS = {
    "On two tracks: hourly klines": None,   # placeholder, handled below
}

doc = Document(REPORT)
log, miss = [], []

# ---------------------------------------------------- 2.2.2 list removal ----
victims = []
for p in doc.paragraphs:
    t = p.text.strip()
    if t.startswith(OLD_LEAD) or t.startswith(OLD_ITEMS):
        victims.append(p)
for p in victims:
    p._p.getparent().remove(p._p)
log.append(f"removed {len(victims)} leftover 2.2.3 list paragraph(s)")

# ------------------------------------------------- 4.4 funding-state bullet ---
target = None
for p in doc.paragraphs:
    if p.text.strip().startswith("Funding states.") and "25th" in p.text:
        target = p
        break
if target is None:
    miss.append("4.4 funding-state bullet")
else:
    for r in list(target.runs):
        r._r.getparent().remove(r._r)
    for text, bold in FUNDING_44:
        r = target.add_run(text)
        r.bold = bold
    log.append("aligned 4.4 funding-state bullet")

# --------------------------------------------- appendix C specification row ---
fixed_rows = 0
for t in doc.tables:
    for row in t.rows:
        cells = row.cells
        if len(cells) >= 2 and cells[0].text.strip() == "Funding states":
            body = cells[1]
            for extra in body.paragraphs[1:]:
                extra._p.getparent().remove(extra._p)
            p0 = body.paragraphs[0]
            for r in list(p0.runs):
                r._r.getparent().remove(r._r)
            p0.add_run("Four non-overlapping trailing-quantile buckets: 0–25, 25–75, 75–90, 90–100; "
                       "computed per contract and per funding interval")
            fixed_rows += 1
log.append(f"aligned {fixed_rows} Appendix C row(s)")

# ------------------------------------------------ appendix C / other mentions -
for p in doc.paragraphs:
    if p.text.strip() == "Fixed before any result is computed. Any later deviation is reported as a " \
                         "deviation in the final report.":
        continue

doc.save(REPORT)
print("saved:", REPORT)
for line in log:
    print("  ", line)
if miss:
    print("MISSES:", miss)

# ------------------------------------------------------------- verification --
d2 = Document(REPORT)
print("--- 2.2.2 block after cleanup ---")
on = False
for p in d2.paragraphs:
    t = p.text.strip()
    if t.startswith("2.2.2"): on = True
    elif t.startswith("2.2.3") or t.startswith("3. "): on = False
    if on and t:
        print(f"  [{p.style.name:11s}] {t[:120]}")
print("--- 4.4 funding bullet ---")
for p in d2.paragraphs:
    if p.text.strip().startswith("Funding states."):
        print("  ", p.text.strip()[:200])
print("--- appendix C funding row ---")
for t in d2.tables:
    for row in t.rows:
        if row.cells[0].text.strip() == "Funding states":
            print("  ", row.cells[1].text.strip()[:200])
