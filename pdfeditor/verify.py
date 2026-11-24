"""Check every output PDF: it opens, renders, has the right page count, and kept its text."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium


@dataclass
class VerifyResult:
    path: Path
    ok: bool
    pages: int = 0
    text_chars: int = 0
    problems: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        status = "OK" if self.ok else "FAILED"
        line = f"[{status}] {self.path.name}: {self.pages} pages, {self.text_chars} text chars"
        if self.problems:
            line += "\n  - " + "\n  - ".join(self.problems)
        return line


def text_chars(path: Path, password: str | None = None) -> int:
    """Count non-whitespace characters of extractable text in the whole document."""
    doc = pdfium.PdfDocument(str(path), password=password)
    try:
        count = 0
        for i in range(len(doc)):
            page = doc[i]
            tp = page.get_textpage()
            count += sum(1 for c in tp.get_text_range() if not c.isspace())
            tp.close()
            page.close()
        return count
    finally:
        doc.close()


def verify(
    path: Path,
    expected_pages: int | None = None,
    expect_text: bool = False,
    password: str | None = None,
) -> VerifyResult:
    path = Path(path)
    res = VerifyResult(path=path, ok=True)

    if not path.exists() or path.stat().st_size == 0:
        res.ok = False
        res.problems.append("file is missing or empty")
        return res

    # 1. Structure opens cleanly (qpdf)
    try:
        with pikepdf.open(path, password=password or "") as pdf:
            res.pages = len(pdf.pages)
    except Exception as e:  # noqa: BLE001 - report any failure
        res.ok = False
        res.problems.append(f"does not open: {e}")
        return res

    # 2. Renders in PDFium (first and last page) and has text
    try:
        doc = pdfium.PdfDocument(str(path), password=password)
        try:
            for i in {0, len(doc) - 1}:
                page = doc[i]
                page.render(scale=0.1).close()
                page.close()
        finally:
            doc.close()
        res.text_chars = text_chars(path, password)
    except Exception as e:  # noqa: BLE001
        res.ok = False
        res.problems.append(f"does not render: {e}")
        return res

    if expected_pages is not None and res.pages != expected_pages:
        res.ok = False
        res.problems.append(f"expected {expected_pages} pages, got {res.pages}")
    if expect_text and res.text_chars == 0:
        res.ok = False
        res.problems.append("source had text but output has none")
    return res
