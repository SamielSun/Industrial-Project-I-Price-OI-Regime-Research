# -*- coding: utf-8 -*-
"""Extract mentor note docx -> markdown, keeping heading levels and tables."""
import sys
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

SRC = r"D:\Industrial Programme I\price_oi_regime_signal_idea_note_mentor.docx"
OUT = r"D:\Industrial Programme I\_build\mentor_note_extracted.md"


def iter_block_items(parent):
    from docx.oxml.ns import qn
    body = parent.element.body
    for child in body.iterchildren():
        if child.tag == qn('w:p'):
            yield Paragraph(child, parent)
        elif child.tag == qn('w:tbl'):
            yield Table(child, parent)


doc = Document(SRC)
lines = []
for block in iter_block_items(doc):
    if isinstance(block, Paragraph):
        txt = block.text.strip()
        style = (block.style.name or '')
        if not txt:
            lines.append('')
            continue
        if style.startswith('Heading'):
            try:
                lvl = int(style.split()[-1])
            except ValueError:
                lvl = 1
            lines.append('#' * max(1, min(6, lvl)) + ' ' + txt)
        elif style.startswith('Title'):
            lines.append('# ' + txt)
        elif 'List' in style:
            lines.append('- ' + txt)
        else:
            lines.append(txt)
    else:
        lines.append('')
        for row in block.rows:
            cells = [c.text.strip().replace('\n', ' ') for c in row.cells]
            lines.append('| ' + ' | '.join(cells) + ' |')
        lines.append('')

with open(OUT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print('wrote', OUT)
print('paragraph blocks:', len(lines))
