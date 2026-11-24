
import re
from pathlib import Path

base = Path(r"D:\CUHK Fintech\Industrial Programme I\research_archive\report")
lines = (base / "report.md").read_text(encoding="utf-8").split("\n")

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
URL = re.compile(r"(https?://[^\s,;)]+)")

def breakable_code(s):
    def rep(m):
        inner = m.group(1).replace("/", "/\\allowbreak{}").replace(",", ",\\allowbreak{}")
        return r"\texttt{" + inner + "}"
    return re.sub(r"\\texttt\{([^}]*)\}", rep, s)

def inline(s):
    s = URL.sub(lambda m: "\x01" + m.group(1) + "\x02", s)
    s = esc(s)
    s = re.sub(BT + r"([^" + BT + r"]+)" + BT, lambda m: r"\texttt{" + m.group(1) + "}", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\\emph{\1}", s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: r"\href{" + m.group(2) + "}{" + m.group(1) + "}", s)
    s = s.replace("\x01", r"\url{").replace("\x02", "}")
    for a, b in UNI:
        s = s.replace(a, b)
    return breakable_code(s)

NUM = re.compile(r"^[\u2212+\-\u2013]?[\d.,%()\s]*$")

preamble = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.5cm]{geometry}
\usepackage[T1]{fontenc}
\usepackage{amssymb}
\usepackage{newtxtext,newtxmath}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{array}
\usepackage{longtable}
\usepackage{caption}
\usepackage{float}
\usepackage{pdflscape}

\usepackage{enumitem}
\usepackage{amsmath}
\usepackage{xurl}
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
in_numbered = False
in_quote = False
in_refs = False

def flush_lists():
    global in_bullets, in_numbered
    if in_bullets:
        body.append(r"\end{itemize}"); body.append(""); in_bullets = False
    if in_numbered:
        body.append(r"\end{enumerate}"); body.append(""); in_numbered = False

def flush_quote():
    global in_quote
    if in_quote:
        body.append(r"\end{quote}"); body.append(""); in_quote = False

def render_table(rows, caption=None):
    parsed = [r for r in rows if r.strip().startswith("|")]
    if len(parsed) < 2:
        return
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in parsed]
    header, data = cells[0], cells[2:]
    ncol = len(header)
    if len(data) > 8:
        # longtable: fixed p-columns, weighted by content length
        lens = []
        for c in range(ncol):
            col = [row[c] for row in data if c < len(row)] + [header[c]]
            lens.append(max(12, sum(len(x) for x in col) / max(1, len(col))))
        tot = sum(lens)
        widths = [max(0.10, min(0.55, 0.92 * l / tot)) for l in lens]
        scale = 0.90 / sum(widths)
        widths = [w * scale for w in widths]
        spec = "".join("p{%.2f\\linewidth}" % w for w in widths)
        body.append(r"{\footnotesize\setlength{\tabcolsep}{4pt}")
        body.append(r"\begin{longtable}{" + spec + "}")
        if caption:
            body.append(r"\caption{" + inline(caption) + r"}\\")
        body.append(r"\toprule")
        body.append(" & ".join(inline(h) for h in header) + r" \\")
        body.append(r"\midrule")
        body.append(r"\endfirsthead")
        body.append(r"\toprule")
        body.append(" & ".join(inline(h) for h in header) + r" \\")
        body.append(r"\midrule")
        body.append(r"\endhead")
        body.append(r"\bottomrule")
        body.append(r"\endfoot")
        for row in data:
            row = (row + [""] * ncol)[:ncol]
            body.append(" & ".join(inline(c) for c in row) + r" \\")
        body.append(r"\end{longtable}")
        body.append("}")
        body.append("")
        return
    specs = []
    for c in range(ncol):
        col = [row[c] for row in data if c < len(row)]
        numeric = bool(col) and all(NUM.match(x) and x for x in col)
        specs.append(r">{\raggedleft\arraybackslash}X" if numeric else r">{\raggedright\arraybackslash}X")
    body.append(r"\begin{table}[H]\centering")
    if caption:
        body.append(r"\caption{" + inline(caption) + "}")
    body.append(r"\footnotesize")
    body.append(r"\begin{tabularx}{\linewidth}{" + "".join(specs) + "}")
    body.append(r"\toprule")
    body.append(" & ".join(inline(h) for h in header) + r" \\")
    body.append(r"\midrule")
    for row in data:
        row = (row + [""] * ncol)[:ncol]
        body.append(" & ".join(inline(c) for c in row) + r" \\")
    body.append(r"\bottomrule")
    body.append(r"\end{tabularx}")
    body.append(r"\end{table}")
    body.append("")

while i < n:
    line = lines[i]
    s = line.strip()
    if i <= 7:
        i += 1
        continue
    if s == "## Abstract":
        flush_lists(); flush_quote()
        body.append(r"\begin{abstract}")
        in_abstract = True
        i += 1
        continue
    if in_abstract and s == "---":
        body.append(r"\end{abstract}")
        body.append(r"\newpage"); body.append(r"\tableofcontents"); body.append(r"\newpage")
        in_abstract = False
        i += 1
        continue
    if s == "## Contents":
        i += 1
        while i < n and not lines[i].strip().startswith("## "):
            i += 1
        continue
    if s.startswith("## "):
        flush_lists(); flush_quote()
        title = s[3:].strip()
        m = re.match(r"^(\d+)\s+(.*)$", title)
        body.append(r"\section{" + inline(m.group(2)) + "}" if m else r"\section*{" + inline(title) + "}")
        body.append("")
        in_refs = False
        i += 1
        continue
    if s.startswith("### "):
        flush_lists(); flush_quote()
        title = s[4:].strip()
        m = re.match(r"^(\d+\.\d+)\s+(.*)$", title)
        body.append(r"\subsection{" + inline(m.group(2)) + "}" if m else r"\subsection*{" + inline(title) + "}")
        body.append("")
        in_refs = "Appendix A" in title
        if in_refs:
            body.append(r"{\small\raggedright\setlength{\parskip}{0.5em}")
        i += 1
        continue
    if line.startswith("    ") and s and not s.startswith("- "):
        flush_lists(); flush_quote()
        block = []
        while i < n and (lines[i].startswith("    ") or not lines[i].strip()):
            if lines[i].startswith("    "):
                block.append(lines[i][4:])
            i += 1
        body.append(r"\begin{verbatim}")
        body.extend(block)
        body.append(r"\end{verbatim}")
        body.append("")
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
    if s.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|$", lines[i+1].strip()):
        flush_lists(); flush_quote()
        rows = []
        while i < n and lines[i].strip().startswith("|"):
            rows.append(lines[i]); i += 1
        render_table(rows, None)
        continue
    mi = re.match(r"^!\[[^\]]*\]\(([^)]+)\)$", s)
    if mi:
        flush_lists(); flush_quote()
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
        if "d5_full" in path:
            for part in (1, 2):
                body.append(r"\begin{figure}[H]")
                body.append(r"\centering")
                body.append(r"\includegraphics[width=\linewidth,height=0.90\textheight,keepaspectratio]{" + path.replace("d5_full.png", "d5_full_p%d.png" % part) + "}")
                if cap:
                    body.append(r"\caption*{Figure 17. " + inline(cap) + " (" + str(part) + " of 2)}")
                body.append(r"\end{figure}")
                body.append("")
            i = k + 1
            continue
        else:
            body.append(r"\begin{figure}[H]")
            body.append(r"\centering")
            body.append(r"\includegraphics[width=0.92\linewidth,height=0.40\textheight,keepaspectratio]{" + path + "}")
            if cap:
                body.append(r"\caption{" + inline(cap) + "}")
            body.append(r"\end{figure}")
        body.append("")
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
        if in_numbered:
            body.append(r"\end{enumerate}"); in_numbered = False
        if not in_bullets:
            body.append(r"\begin{itemize}"); in_bullets = True
        body.append(r"\item " + inline(s[2:].strip()))
        i += 1
        continue
    mo = re.match(r"^\d+\.\s+(.*)$", s)
    if mo:
        if in_bullets:
            body.append(r"\end{itemize}"); in_bullets = False
        if not in_numbered:
            body.append(r"\begin{enumerate}"); in_numbered = True
        body.append(r"\item " + inline(mo.group(1)))
        i += 1
        continue
    flush_lists()
    if s == "---":
        body.append(r"\bigskip"); body.append("")
        i += 1
        continue
    if not s:
        i += 1
        continue
    if in_refs:
        body.append(r"\noindent\hangindent=1.4em\hangafter=1 " + inline(s))
    else:
        body.append(inline(s))
    body.append("")
    i += 1

flush_lists()
if in_refs:
    body.append("}")

tex = preamble + "\n" + "\n".join(body) + "\n\\end{document}\n"
(base / "build_tex.py").write_text(Path(__file__).read_text(encoding="utf-8"), encoding="utf-8")
(base / "report.tex").write_text(tex, encoding="utf-8")
print("written | tables:", tex.count(r"\begin{table}") + tex.count(r"\begin{longtable}"), "| figures:", tex.count(r"\begin{figure}"))
