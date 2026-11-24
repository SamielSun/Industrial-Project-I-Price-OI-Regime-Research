
import re
from pathlib import Path

base = Path(r"D:\CUHK Fintech\Industrial Programme I\research_archive\report")
src = base / "report.md"
out = base / "report.tex"
lines = src.read_text(encoding="utf-8").split("\n")

def esc(s):
    s = s.replace("\\", r"\textbackslash{}")
    for a, b in [("&", r"\&"), ("%", r"\%"), ("$", r"\$"), ("#", r"\#"),
                 ("_", r"\_"), ("{", r"\{"), ("}", r"\}"),
                 ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")]:
        s = s.replace(a, b)
    return s

UNI = [("\u2212", r"$-$"), ("\u2013", "--"), ("\u2014", "---"), ("\u00d7", r"$\times$"),
       ("\u0394", r"$\Delta$"), ("\u24c8", r"$\circledS$"), ("\u2248", r"$\approx$"),
       ("\u2264", r"$\le$"), ("\u2265", r"$\ge$"), ("\u00b1", r"$\pm$"), ("\u03b2", r"$\beta$"),
       ("\u2192", r"$\to$"), ("\u00f7", r"$\div$"), ("\u00b7", r"$\cdot$")]

BT = "\x60"

def inline(s):
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: r"\href{" + m.group(2) + "}{" + esc(m.group(1)) + "}", s)
    s = re.sub(BT + r"([^" + BT + r"]+)" + BT, lambda m: r"\texttt{" + esc(m.group(1)) + "}", s)
    s = esc(s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\emph{\1}", s)
    for a, b in UNI:
        s = s.replace(a, b)
    return s

preamble = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.5cm]{geometry}
\usepackage[T1]{fontenc}
\usepackage{amssymb}
\usepackage{newtxtext,newtxmath}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{caption}
\usepackage{float}
\usepackage{enumitem}
\usepackage{amsmath}
\usepackage[hidelinks]{hyperref}
\usepackage{microtype}
\captionsetup{font=small,labelfont=bf,skip=4pt}
\setlist{nosep,leftmargin=1.2em}
\setlength{\parskip}{0.35em}
\setlength{\parindent}{0pt}
\renewcommand{\arraystretch}{1.15}
\title{\textbf{Price $\times$ Open-Interest Regimes in Binance Perpetual Futures}\\[4pt]
\large What Positioning Data Does and Does Not Predict}
\author{Sun Yusu\\[2pt]\small Student ID 1155267751\\[6pt]
\small Academic Supervisor: Professor Wu Xixin\\
\small Industrial Supervisor: Mr. Jackson Wong}
\date{27 November 2026}
\begin{document}
\maketitle
"""

body = []
i = 0
n = len(lines)
in_abstract = False
in_bullets = False
in_quote = False

def flush_bullets():
    global in_bullets
    if in_bullets:
        body.append(r"\end{itemize}")
        in_bullets = False

def flush_quote():
    global in_quote
    if in_quote:
        body.append(r"\end{quote}")
        in_quote = False

def render_table(rows, caption=None):
    parsed = [r for r in rows if r.strip().startswith("|")]
    if len(parsed) < 2:
        return False
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in parsed]
    header, data = cells[0], cells[2:]
    ncol = len(header)
    spec = "X" + "r" * (ncol - 1)
    body.append(r"\begin{table}[htbp]\centering")
    if caption:
        body.append(r"\caption{" + inline(caption) + "}")
    body.append(r"\small")
    body.append(r"\begin{tabularx}{\linewidth}{" + spec + "}")
    body.append(r"\toprule")
    body.append(" & ".join(inline(h) for h in header) + r" \\")
    body.append(r"\midrule")
    for row in data:
        row = (row + [""] * ncol)[:ncol]
        body.append(" & ".join(inline(c) for c in row) + r" \\")
    body.append(r"\bottomrule")
    body.append(r"\end{tabularx}")
    body.append(r"\end{table}")
    return True

while i < n:
    line = lines[i]
    s = line.strip()
    if i <= 7:
        i += 1
        continue
    if s == "## Abstract":
        flush_bullets(); flush_quote()
        body.append(r"\begin{abstract}")
        in_abstract = True
        i += 1
        continue
    if in_abstract and s == "---":
        body.append(r"\end{abstract}")
        body.append(r"\newpage")
        body.append(r"\tableofcontents")
        body.append(r"\newpage")
        in_abstract = False
        i += 1
        continue
    if s == "## Contents":
        i += 1
        while i < n and not lines[i].strip().startswith("## "):
            i += 1
        continue
    if s.startswith("## "):
        flush_bullets(); flush_quote()
        title = s[3:].strip()
        m = re.match(r"^(\d+)\s+(.*)$", title)
        body.append(r"\section{" + inline(m.group(2)) + "}" if m else r"\section*{" + inline(title) + "}")
        i += 1
        continue
    if s.startswith("### "):
        flush_bullets(); flush_quote()
        title = s[4:].strip()
        m = re.match(r"^(\d+\.\d+)\s+(.*)$", title)
        body.append(r"\subsection{" + inline(m.group(2)) + "}" if m else r"\subsection*{" + inline(title) + "}")
        i += 1
        continue
    mt = re.match(r"^\*\*Table (\d+)\.\s*(.*?)\*\*$", s)
    if mt:
        caption = "Table " + mt.group(1) + ". " + mt.group(2)
        i += 1
        while i < n and not lines[i].strip():
            i += 1
        rows = []
        while i < n and lines[i].strip().startswith("|"):
            rows.append(lines[i]); i += 1
        render_table(rows, caption)
        continue
    # any pipe table without a caption
    if s.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|$", lines[i+1].strip()):
        flush_bullets(); flush_quote()
        rows = []
        while i < n and lines[i].strip().startswith("|"):
            rows.append(lines[i]); i += 1
        render_table(rows, None)
        continue
    mi = re.match(r"^!\[[^\]]*\]\(([^)]+)\)$", s)
    if mi:
        flush_bullets(); flush_quote()
        path = mi.group(1)
        j = i + 1
        while j < n and not lines[j].strip():
            j += 1
        cap = ""
        k = i
        if j < n and lines[j].strip().startswith("*Figure"):
            cap = lines[j].strip().strip("*")
            k = j
        cap = re.sub(r"^Figure (\d+)\.\s*", "", cap)
        body.append(r"\begin{figure}[htbp]")
        body.append(r"\centering")
        body.append(r"\includegraphics[width=0.92\linewidth]{" + path + "}")
        if cap:
            body.append(r"\caption{" + inline(cap) + "}")
        body.append(r"\end{figure}")
        i = k + 1
        continue
    if s.startswith(">"):
        txt = s.lstrip(">").strip()
        if txt.startswith("**[TIKZ"):
            body.append("% [TIKZ placeholder removed from the compiled report]")
            i += 1
            while i < n and lines[i].strip().startswith(">"):
                i += 1
            continue
        if not in_quote:
            body.append(r"\begin{quote}"); in_quote = True
        body.append(inline(txt))
        i += 1
        continue
    flush_quote()
    if s.startswith("- "):
        if not in_bullets:
            body.append(r"\begin{itemize}"); in_bullets = True
        body.append(r"\item " + inline(s[2:].strip()))
        i += 1
        continue
    flush_bullets()
    if s == "---":
        body.append(r"\bigskip")
        i += 1
        continue
    if not s:
        i += 1
        continue
    body.append(inline(s))
    i += 1

if in_bullets:
    body.append(r"\end{itemize}")

tex = preamble + "\n" + "\n".join(body) + "\n\\end{document}\n"
(base / "build_tex.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
out.write_text(tex, encoding="utf-8")
print("written", out, "| tables:", tex.count(r"\begin{table}"), "| figures:", tex.count(r"\begin{figure}"))
