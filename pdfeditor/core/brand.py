"""Branding: watermarks, page numbers, headers and footers.

All functions read the input, write a NEW file, and return the output path.
Inputs are never modified. Text is drawn with the built-in Helvetica font.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .overlay import PageGeom, apply_overlay
from .pages import output_path, parse_pages

FONT = "Helvetica"

WATERMARK_POSITIONS = (
    "center", "top-left", "top-center", "top-right", "center-left", "center-right",
    "bottom-left", "bottom-center", "bottom-right",
)
NUMBER_POSITIONS = ("bottom-center", "bottom-left", "bottom-right", "top-left", "top-center", "top-right")
ALIGNMENTS = ("left", "center", "right")


# ---------- validation helpers ----------

def _color(value: str) -> colors.Color:
    try:
        return colors.toColor(value)
    except Exception as e:  # noqa: BLE001 - reportlab raises ValueError or others
        raise ValueError(f"unknown color: {value!r} (use a name like 'gray' or hex like '#ff0000')") from e


def _positive(name: str, value: float) -> float:
    if value is None or value <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return float(value)


def _non_negative(name: str, value: float) -> float:
    if value is None or value < 0:
        raise ValueError(f"{name} must be 0 or more")
    return float(value)


def _choice(name: str, value: str, allowed: tuple[str, ...]) -> str:
    value = (value or "").strip().lower()
    if value not in allowed:
        raise ValueError(f"{name} must be one of: {', '.join(allowed)}")
    return value


def _render(template: str, **values: object) -> str:
    try:
        return template.format(**values)
    except KeyError as e:
        names = ", ".join("{" + k + "}" for k in values)
        raise ValueError(f"unknown placeholder {{{e.args[0]}}}; available: {names}") from None
    except (IndexError, ValueError) as e:
        raise ValueError(f"bad format string {template!r}: {e}") from None


def _check_text(text: str) -> None:
    """Helvetica only covers Latin-1; fail early with a clear message."""
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        raise ValueError("text has characters the built-in font cannot show (only Latin characters are supported)") from None


# ---------- watermark ----------

def watermark(
    path: Path,
    text: str | None = None,
    *,
    image: Path | None = None,
    opacity: float = 0.3,
    angle: float = 45,
    font_size: float = 60,
    scale: float = 0.5,
    color: str = "gray",
    position: str = "center",
    tile: bool = False,
    pages: str = "all",
    out: Path | None = None,
    password: str | None = None,
) -> Path:
    """Stamp a text or image watermark on the selected pages.

    text/image: give exactly one. opacity: 0 (invisible) to 1 (solid).
    angle: counter-clockwise degrees. font_size: for text. scale: for images,
    the image width as a fraction of the page width (0.5 = half the page).
    position: one of WATERMARK_POSITIONS; tile=True repeats it in a grid instead.
    """
    if bool(text) == bool(image):
        raise ValueError("give either text or an image for the watermark (not both)")
    if opacity is None or not 0 < opacity <= 1:
        raise ValueError("opacity must be greater than 0 and at most 1")
    position = _choice("position", position, WATERMARK_POSITIONS)
    fill = _color(color)
    path = Path(path)

    if text:
        _check_text(text)
        size = _positive("font size", font_size)
        tw = stringWidth(text, FONT, size)
        th = size * 0.72  # cap height is roughly 0.72 em for Helvetica

        def item_size(geom: PageGeom) -> tuple[float, float]:
            return tw, th

        def draw_item(c: canvas.Canvas, geom: PageGeom) -> None:
            c.setFont(FONT, size)
            c.drawCentredString(0, -th / 2, text)
    else:
        img_path = Path(image)
        if not img_path.is_file():
            raise ValueError(f"image not found: {img_path}")
        try:
            reader = ImageReader(str(img_path))
            iw, ih = reader.getSize()
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"cannot read image {img_path.name}: {e}") from None
        frac = _positive("scale", scale)

        def item_size(geom: PageGeom) -> tuple[float, float]:
            w = geom.width * frac
            return w, w * ih / iw

        def draw_item(c: canvas.Canvas, geom: PageGeom) -> None:
            w, h = item_size(geom)
            c.drawImage(reader, -w / 2, -h / 2, width=w, height=h, mask="auto")

    rad = math.radians(angle)
    cos, sin = abs(math.cos(rad)), abs(math.sin(rad))
    margin = 36.0

    def draw(c: canvas.Canvas, geom: PageGeom) -> None:
        w, h = item_size(geom)
        bw, bh = w * cos + h * sin, w * sin + h * cos  # rotated bounding box
        c.setFillAlpha(opacity)
        c.setStrokeAlpha(opacity)
        c.setFillColor(fill)
        if tile:
            step_x, step_y = bw + max(h, 24) * 2, bh + max(h, 24) * 2
            row = 0
            y = -step_y / 2
            while y < geom.height + step_y:
                x = -step_x / 2 + (step_x / 2 if row % 2 else 0)
                while x < geom.width + step_x:
                    _stamp(c, x, y, angle, draw_item, geom)
                    x += step_x
                y += step_y
                row += 1
            return
        vert, _, horiz = position.partition("-") if position != "center" else ("center", "", "center")
        x = {"left": margin + bw / 2, "center": geom.width / 2,
             "right": geom.width - margin - bw / 2}[horiz or "center"]
        y = {"bottom": margin + bh / 2, "center": geom.height / 2,
             "top": geom.height - margin - bh / 2}[vert]
        _stamp(c, x, y, angle, draw_item, geom)

    return apply_overlay(path, output_path(path, "watermarked", out), draw, pages, password)


def _stamp(c: canvas.Canvas, x: float, y: float, angle: float, draw_item, geom: PageGeom) -> None:
    c.saveState()
    c.translate(x, y)
    c.rotate(angle)
    draw_item(c, geom)
    c.restoreState()


# ---------- text placed along an edge ----------

def _draw_edge_text(c: canvas.Canvas, geom: PageGeom, text: str, edge: str, align: str,
                    size: float, margin: float, fill: colors.Color) -> None:
    c.setFont(FONT, size)
    c.setFillColor(fill)
    y = margin if edge == "bottom" else geom.height - margin - size * 0.72
    if align == "left":
        c.drawString(margin, y, text)
    elif align == "right":
        c.drawRightString(geom.width - margin, y, text)
    else:
        c.drawCentredString(geom.width / 2, y, text)


# ---------- page numbers ----------

def page_numbers(
    path: Path,
    *,
    position: str = "bottom-center",
    fmt: str = "{n}",
    start: int = 1,
    font_size: float = 10,
    margin: float = 28,
    color: str = "black",
    pages: str = "all",
    out: Path | None = None,
    password: str | None = None,
) -> Path:
    """Add page numbers to the selected pages.

    Numbering counts only the selected pages: the first selected page gets
    `start`, the next start+1, and so on (so pages="2-", start=1 skips a cover).
    fmt may use {n} (this page's number) and {total} (the last number shown),
    e.g. "Page {n} of {total}".
    """
    position = _choice("position", position, NUMBER_POSITIONS)
    size = _positive("font size", font_size)
    margin = _non_negative("margin", margin)
    fill = _color(color)
    _check_text(_render(fmt, n=0, total=0))
    path = Path(path)
    edge, align = position.split("-")
    numbers: dict[int, int] = {}
    total_shown = 0

    def draw(c: canvas.Canvas, geom: PageGeom) -> None:
        nonlocal total_shown
        if not numbers:  # first call: we now know the page count
            selected = sorted(set(parse_pages(pages, geom.total)))
            numbers.update({i: start + k for k, i in enumerate(selected)})
            total_shown = start + len(selected) - 1
        text = _render(fmt, n=numbers[geom.index], total=total_shown)
        _draw_edge_text(c, geom, text, edge, align, size, margin, fill)

    return apply_overlay(path, output_path(path, "numbered", out), draw, pages, password)


# ---------- header / footer ----------

def header_footer(
    path: Path,
    header: str | None = None,
    footer: str | None = None,
    *,
    align: str = "center",
    font_size: float = 10,
    margin: float = 28,
    color: str = "black",
    pages: str = "all",
    out: Path | None = None,
    password: str | None = None,
) -> Path:
    """Add a header and/or footer line to the selected pages.

    Placeholders: {n} page number in the document, {total} pages in the
    document, {filename} the input file name, {date} today as YYYY-MM-DD.
    """
    if not header and not footer:
        raise ValueError("give header text, footer text, or both")
    align = _choice("align", align, ALIGNMENTS)
    size = _positive("font size", font_size)
    margin = _non_negative("margin", margin)
    fill = _color(color)
    path = Path(path)
    today = date.today().isoformat()

    def values(geom: PageGeom) -> dict[str, object]:
        return {"n": geom.number, "total": geom.total, "filename": path.name, "date": today}

    sample = PageGeom(index=0, number=1, total=1, width=1, height=1, rotation=0)
    for t in (header, footer):
        if t:
            _check_text(_render(t, **values(sample)))

    def draw(c: canvas.Canvas, geom: PageGeom) -> None:
        if header:
            _draw_edge_text(c, geom, _render(header, **values(geom)), "top", align, size, margin, fill)
        if footer:
            _draw_edge_text(c, geom, _render(footer, **values(geom)), "bottom", align, size, margin, fill)

    return apply_overlay(path, output_path(path, "header_footer", out), draw, pages, password)
