from __future__ import annotations

import io

from docx import Document as DocxDocument
from docx.shared import Pt


def create_answer_docx(text: str) -> io.BytesIO:
    doc = DocxDocument()
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Times New Roman"
    font.size = Pt(12)

    for paragraph in text.split("\n"):
        p = doc.add_paragraph(paragraph.strip())

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
