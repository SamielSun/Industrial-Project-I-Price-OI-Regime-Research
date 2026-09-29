# -*- coding: utf-8 -*-
"""One-shot finisher: move the corrected report onto the canonical filename.

Run AFTER closing the report in Word:

    python "D:\\Industrial Programme I\\_build\\finalise_report.py"
"""
import os
import shutil
import sys
import time

SRC = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"
DST = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL.docx"

if not os.path.exists(SRC):
    print(f"{SRC} not found — nothing to move. The canonical file is already the")
    print("submittable version if it contains 'eight working weeks' in section 5.")
    sys.exit(0)

for attempt in range(1, 13):
    try:
        shutil.copyfile(SRC, DST)
        break
    except PermissionError:
        print(f"attempt {attempt}: {DST} is locked (open in Word?) — retrying")
        time.sleep(5)
else:
    sys.exit(f"still locked. Use this file instead: {SRC}")

from docx import Document  # noqa: E402

doc = Document(DST)
ok = any("eight working weeks" in p.text for p in doc.paragraphs)
print(f"OK: {DST}")
print(f"    paragraphs={len([p for p in doc.paragraphs if p.text.strip()])} "
      f"tables={len(doc.tables)}  corrected_wording={ok}")
os.remove(SRC)
print("    removed the v2 copy; the canonical filename is now the final version")
