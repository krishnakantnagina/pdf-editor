"""Stamp drawings onto existing pages: reportlab draws, pikepdf merges.

`apply_overlay()` builds one overlay page per target page with reportlab, sized
like the page *as the reader sees it* (after /Rotate, inside the CropBox). The
drawing callback works in those reader coordinates: (0, 0) is the bottom-left
corner of the visible page and text drawn upright appears upright on screen.
Each overlay page is then placed on its target page as a Form XObject with a
matrix that undoes the page rotation and box offset.

The input file is never modified; a new file is written to `out`.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pikepdf
from pikepdf import Name
from reportlab.pdfgen import canvas

from .organize import _open, _save
from .pages import parse_pages


@dataclass(frozen=True)
class PageGeom:
    """What a drawing callback knows about the page it is drawing on."""

    index: int       # 0-based page index in the document
    number: int      # 1-based page number in the document
    total: int       # pages in the document
    width: float     # visible width as the reader sees it (points)
    height: float    # visible height as the reader sees it (points)
    rotation: int    # page /Rotate, normalized to 0, 90, 180 or 270


DrawFn = Callable[[canvas.Canvas, PageGeom], None]


def _visible_box(page: pikepdf.Page) -> tuple[float, float, float, float]:
    """CropBox (or MediaBox) as normalized (x0, y0, x1, y1) in user space."""
    box = page.obj.get(Name.CropBox) or page.mediabox
    a, b, c, d = (float(v) for v in box)
    return min(a, c), min(b, d), max(a, c), max(b, d)


def _rotation(page: pikepdf.Page) -> int:
    try:
        rot = int(page.obj.get(Name.Rotate, 0))
    except (TypeError, ValueError):
        rot = 0
    rot %= 360
    return rot if rot in (0, 90, 180, 270) else 0


def _matrix(rot: int, x0: float, y0: float, w: float, h: float) -> tuple[float, ...]:
    """Map reader coordinates (u, v) to page user space (x, y).

    w and h are the unrotated box size. The page is shown rotated `rot` degrees
    clockwise, so we apply the inverse rotation and shift to the box origin.
    """
    if rot == 90:
        return (0, 1, -1, 0, x0 + w, y0)
    if rot == 180:
        return (-1, 0, 0, -1, x0 + w, y0 + h)
    if rot == 270:
        return (0, -1, 1, 0, x0, y0 + h)
    return (1, 0, 0, 1, x0, y0)


def _fmt(n: float) -> str:
    return f"{n:.4f}".rstrip("0").rstrip(".") or "0"


def apply_overlay(path: Path, out: Path, draw: DrawFn, pages: str = "all",
                  password: str | None = None) -> Path:
    """Draw on the selected pages of `path` and save the result to `out`.

    `draw(c, geom)` is called once per selected page (in document order) on a
    reportlab canvas whose page size is (geom.width, geom.height).
    """
    path = Path(path)
    with _open(path, password) as pdf:
        total = len(pdf.pages)
        targets = sorted(set(parse_pages(pages, total)))

        # 1. Draw every overlay page with reportlab, in memory.
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        placements = []
        for i in targets:
            page = pdf.pages[i]
            x0, y0, x1, y1 = _visible_box(page)
            w, h = x1 - x0, y1 - y0
            if w <= 0 or h <= 0:
                raise ValueError(f"page {i + 1} has an empty page box")
            rot = _rotation(page)
            vw, vh = (h, w) if rot in (90, 270) else (w, h)
            c.setPageSize((vw, vh))
            draw(c, PageGeom(index=i, number=i + 1, total=total, width=vw, height=vh, rotation=rot))
            c.showPage()
            placements.append((i, _matrix(rot, x0, y0, w, h)))
        c.save()
        buf.seek(0)

        # 2. Place each overlay page on its target as a Form XObject.
        with pikepdf.open(buf) as ov:
            for k, (i, m) in enumerate(placements):
                page = pdf.pages[i]
                formx = pdf.copy_foreign(ov.pages[k].as_form_xobject())
                name = page.add_resource(formx, Name.XObject, prefix="PdfEdOv")
                cm = " ".join(_fmt(v) for v in m)
                # Isolate the original content so its graphics state can't leak into ours.
                page.contents_add(b"q\n", prepend=True)
                page.contents_add(f"\nQ\nq {cm} cm {name} Do Q\n".encode("ascii"))
            return _save(pdf, Path(out))
