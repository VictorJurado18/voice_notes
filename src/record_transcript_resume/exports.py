"""Export saved Voice Notes documents without requiring an external editor."""
from __future__ import annotations

from html import escape
from pathlib import Path


def export_docx(source: Path, destination: Path) -> Path:
    """Export Markdown-like text as an editable Word document."""
    from docx import Document

    document = Document()
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            document.add_heading(line[2:].strip(), level=0)
        elif line.startswith("## "):
            document.add_heading(line[3:].strip(), level=1)
        elif line.strip():
            document.add_paragraph(line)
    destination.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(destination))
    return destination


def export_pdf(source: Path, destination: Path) -> Path:
    """Export text as a readable PDF with Portuguese characters preserved."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    styles = getSampleStyleSheet()
    story = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            story.append(Paragraph(escape(line[2:].strip()), styles["Title"]))
        elif line.startswith("## "):
            story.append(Spacer(1, 0.25 * cm))
            story.append(Paragraph(escape(line[3:].strip()), styles["Heading2"]))
        elif line.strip():
            story.append(Paragraph(escape(line).replace("\n", "<br/>"), styles["BodyText"]))
            story.append(Spacer(1, 0.1 * cm))
    destination.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(destination), pagesize=A4, rightMargin=1.8 * cm, leftMargin=1.8 * cm).build(story)
    return destination
