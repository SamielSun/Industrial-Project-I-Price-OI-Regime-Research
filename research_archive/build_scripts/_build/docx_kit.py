# -*- coding: utf-8 -*-
"""Shared helpers for building the FTEC5910 planning submission docx files."""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

INK = RGBColor(0x1A, 0x1A, 0x1A)
GREY = RGBColor(0x55, 0x55, 0x55)
ACCENT = RGBColor(0x1F, 0x3B, 0x57)
HDR_FILL = "EDF1F5"


# --------------------------------------------------------------- document ---
def new_doc(margin_cm=2.2, body_pt=10.5):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(body_pt)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "SimSun")
    pf = st.paragraph_format
    pf.space_after = Pt(5)
    pf.space_before = Pt(0)
    pf.line_spacing = 1.14
    for s in doc.sections:
        s.top_margin = Cm(margin_cm)
        s.bottom_margin = Cm(margin_cm)
        s.left_margin = Cm(margin_cm)
        s.right_margin = Cm(margin_cm)
    _configure_headings(doc)
    return doc


def _configure_headings(doc):
    sizes = {1: 14, 2: 12, 3: 11, 4: 10.5}
    for lvl, size in sizes.items():
        st = doc.styles[f"Heading {lvl}"]
        st.font.name = "Times New Roman"
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = ACCENT
        st.element.rPr.rFonts.set(qn("w:eastAsia"), "SimHei")
        st.paragraph_format.space_before = Pt(11 if lvl <= 2 else 9)
        st.paragraph_format.space_after = Pt(4)
        st.paragraph_format.keep_with_next = True


# -------------------------------------------------------------- primitives ---
def para(doc, text="", size=None, bold=False, italic=False, align=None,
         color=None, style=None, space_after=None, space_before=None):
    p = doc.add_paragraph(style=style)
    if text:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
        if size:
            r.font.size = Pt(size)
        if color:
            r.font.color.rgb = color
    if align:
        p.alignment = align
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    if space_before is not None:
        p.paragraph_format.space_before = Pt(space_before)
    return p


def rich(doc, parts, size=None, align=None, space_after=None, style=None):
    """parts = list of (text, {bold/italic/mono/sub}) tuples."""
    p = doc.add_paragraph(style=style)
    for text, fmt in parts:
        r = p.add_run(text)
        r.bold = fmt.get("bold", False)
        r.italic = fmt.get("italic", False)
        if fmt.get("mono"):
            r.font.name = "Consolas"
            r.font.size = Pt((size or 10.5) - 1)
        elif size:
            r.font.size = Pt(size)
        if fmt.get("sub"):
            r.font.subscript = True
        if fmt.get("color"):
            r.font.color.rgb = fmt["color"]
    if align:
        p.alignment = align
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return p


def bullet(doc, text, level=0, size=None, bold_lead=None):
    style = "List Bullet" if level == 0 else "List Bullet 2"
    p = doc.add_paragraph(style=style)
    if bold_lead:
        r = p.add_run(bold_lead)
        r.bold = True
        if size:
            r.font.size = Pt(size)
    r = p.add_run(text)
    if size:
        r.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(2)
    return p


def numbered(doc, text, size=None, bold_lead=None):
    p = doc.add_paragraph(style="List Number")
    if bold_lead:
        r = p.add_run(bold_lead)
        r.bold = True
        if size:
            r.font.size = Pt(size)
    r = p.add_run(text)
    if size:
        r.font.size = Pt(size)
    p.paragraph_format.space_after = Pt(2)
    return p


def caption(doc, text):
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.size = Pt(8.5)
    r.italic = True
    r.font.color.rgb = GREY
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(9)
    return p


def shade(cell, fill=HDR_FILL):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def set_cell(cell, text, bold=False, size=9, align=None, italic=False):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.line_spacing = 1.05
    lines = str(text).split("\n")
    for i, line in enumerate(lines):
        if i:
            p = cell.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.line_spacing = 1.05
        r = p.add_run(line)
        r.bold = bold
        r.italic = italic
        r.font.size = Pt(size)
        if align:
            p.alignment = align


def table(doc, headers, rows, widths=None, size=9, header_size=9):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, h in enumerate(headers):
        set_cell(t.rows[0].cells[i], h, bold=True, size=header_size)
        shade(t.rows[0].cells[i])
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            set_cell(cells[i], v, size=size)
    if widths:
        for r in t.rows:
            for i, w in enumerate(widths):
                r.cells[i].width = Cm(w)
    return t


def hrule(doc):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "6")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "999999")
    bdr.append(bottom)
    pPr.append(bdr)
    p.paragraph_format.space_after = Pt(8)
    return p


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def add_page_number_footer(doc, prefix="FTEC5910 Planning Submission"):
    for section in doc.sections:
        p = section.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(prefix + "  |  Page ")
        r.font.size = Pt(8)
        r.font.color.rgb = GREY
        fld = OxmlElement("w:fldSimple")
        fld.set(qn("w:instr"), "PAGE")
        run = OxmlElement("w:r")
        rPr = OxmlElement("w:rPr")
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "16")
        rPr.append(sz)
        run.append(rPr)
        fld.append(run)
        p._p.append(fld)
