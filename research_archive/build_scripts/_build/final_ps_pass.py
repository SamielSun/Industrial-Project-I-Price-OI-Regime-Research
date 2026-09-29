# -*- coding: utf-8 -*-
"""Final pass on section 3: replace the problem statement with a version that
never refers to the source note, and de-reference the note in 3.2 and 3.3."""
import copy
import sys
from docx import Document
from docx.text.paragraph import Paragraph

REPORT = r"D:\Industrial Programme I\FTEC5910_Planning_Report_SUNYusu_FINAL_v2.docx"

P1 = ("Perpetual futures markets publish, for every liquid contract, three quantities that are cheap to "
      "obtain and central to how positioning is read: the direction of price, the direction of open "
      "interest, and the funding rate that prices the cost of holding a leveraged position. Open "
      "interest is informative because of a mechanical asymmetry: it rises only when positions are "
      "opened and falls only when they are closed, so a price move on rising open interest is a "
      "different market event from the same move on falling open interest, even though price alone "
      "cannot distinguish them.")
P2 = ("What is missing is not the observation but its basis. In practice a move on rising open interest "
      "is read as fresh positioning and the same move on falling open interest as unwinding, while a "
      "high funding rate is read as either durable demand or a crowded trade about to reverse. The "
      "evidence behind those readings is fragmentary: open interest and funding are studied largely as "
      "separate factors rather than jointly; positioning evidence rests frequently on aggregate or "
      "retail-derived series rather than exchange-reported open interest for a point-in-time universe of "
      "contracts; and the interaction between a price/open-interest state and the funding state is "
      "assumed rather than measured.")
P3 = ("The consequence is operational. A trader observing a strong move cannot tell whether new positions "
      "are being established or existing ones closed, and so cannot judge whether the move is likely to "
      "continue, to reverse, or to overshoot as leveraged positions are liquidated; nor whether high "
      "funding marks sustainable demand or an imminent unwind. Without measured benchmarks such signals "
      "are traded on conviction alone or discarded, and the negative results that would settle the "
      "question are not produced either.")
P4 = ("This project addresses that gap. It makes the joint state of price, open interest and funding "
      "measurable at hourly frequency across a liquid universe of perpetual contracts, and asks which "
      "combinations, if any, carry information about subsequent returns, volatility and reversal.")

S32 = ("A regime label is a threshold statement: price moved by more than X and open interest moved by "
       "more than Y. The design choice of where those thresholds sit, and over what lookback the two "
       "changes are measured, is therefore not a detail: it decides how many observations qualify as "
       "events and which ones they are. With two thresholds, a lookback length, four horizons and a "
       "4 × 4 funding grid, the number of defensible specifications is large, and the maximum over "
       "specifications is an upward-biased estimate of the effect. The problem is solved by fixing a "
       "baseline specification in advance, reporting a sensitivity surface around it, and treating the "
       "surface as the result rather than selecting its best point.")

S33 = ("The regime-by-funding grid has sixteen cells, and the study evaluates four horizons and four "
       "outcome families. Even if the null hypothesis is true everywhere, a search over that grid will "
       "produce apparently strong cells. The events are also clustered: regime episodes arrive in bursts "
       "during volatile periods, so observations are neither independent across time nor independent "
       "across assets in the same hour, and standard errors that ignore this will be too small. Both "
       "problems are addressed in the design by a pre-declared multiplicity family with an explicit "
       "correction, and by inference that respects the clustering structure rather than by reporting "
       "uncorrected per-cell significance.")


def replace(p, text):
    for r in list(p.runs):
        r._r.getparent().remove(r._r)
    p.add_run(text)


doc = Document(REPORT)
log, miss = [], []

# ---- the four problem-statement paragraphs ----
anchor = None
for p in doc.paragraphs:
    if p.text.strip().startswith("Perpetual futures markets publish"):
        anchor = p
        break
if anchor is None:
    miss.append("problem statement opening")
else:
    replace(anchor, P1)
    cursor = anchor
    for text in (P2, P3, P4):
        new_el = copy.deepcopy(anchor._p)
        cursor._p.addnext(new_el)
        new_p = Paragraph(new_el, cursor._parent)
        for r in list(new_p.runs):
            r._r.getparent().remove(r._r)
        new_p.add_run(text)
        cursor = new_p
    log.append(f"rewrote problem statement ({sum(len(t.split()) for t in (P1,P2,P3,P4))} words)")

# drop any duplicate opening left over from the previous wording
victims = [p for p in doc.paragraphs
           if p.text.strip().startswith("The idea note states a research question")]
for p in victims:
    p._p.getparent().remove(p._p)
if victims:
    log.append(f"removed {len(victims)} superseded opening paragraph(s)")

# ---- 3.2 and 3.3 de-referenced ----
for prefix, text, tag in [
        ("A regime label is a threshold statement", S32, "3.2 measurement problem"),
        ("The headline table of the idea note", S33, "3.3 inference problem"),
        ("The regime-by-funding grid has sixteen cells", S33, "3.3 inference problem")]:
    for p in doc.paragraphs:
        if p.text.strip().startswith(prefix):
            replace(p, text)
            log.append(f"rewrote {tag}")
            break

doc.save(REPORT)
print("saved:", REPORT)
for line in log:
    print("  ", line)
if miss:
    print("MISSES:", miss)

# ---------------------------------------------------------------- verify -----
import re
d2 = Document(REPORT)
leftover = [(i, p.text.strip()[:110]) for i, p in enumerate(d2.paragraphs)
            if re.search(r"idea note", p.text, re.I)]
print("\n--- remaining 'idea note' mentions ---")
for i, t in leftover:
    print(f"  P{i}: {t}")
print("\n--- section 3 opening ---")
on = False
for p in d2.paragraphs:
    t = p.text.strip()
    if t.startswith("3.  Problem Statement"):
        on = True
    elif t.startswith("3.2"):
        on = False
    if on and t:
        print(f"  [{p.style.name[:11]:11s}] {t[:110]}")
