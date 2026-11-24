from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def make_pdf(path: Path, pages: int, label: str = "Page") -> Path:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setTitle(f"Sample {label}")
    c.setAuthor("pdfeditor tests")
    for i in range(1, pages + 1):
        c.setFont("Helvetica", 24)
        c.drawString(72, 750, f"{label} {i}")
        c.setFont("Helvetica", 11)
        for line in range(30):
            c.drawString(72, 700 - line * 18, f"Line {line + 1} of sample text on {label.lower()} {i}.")
        c.showPage()
    c.save()
    return path


def page_labels(path: Path) -> list[str]:
    """First line of text on each page, e.g. ['Page 1', 'Page 2']."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    labels = []
    for i in range(len(doc)):
        page = doc[i]
        tp = page.get_textpage()
        labels.append(tp.get_text_range().strip().splitlines()[0].strip())
        tp.close()
        page.close()
    doc.close()
    return labels


@pytest.fixture
def pdf5(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "five.pdf", 5)


@pytest.fixture
def pdf3(tmp_path: Path) -> Path:
    return make_pdf(tmp_path / "three.pdf", 3, label="Doc")
