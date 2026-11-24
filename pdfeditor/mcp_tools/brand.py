"""Branding MCP tools: watermark, page numbers, header/footer."""

from __future__ import annotations

from typing import Any

from ..core import brand, view
from ..mcp_server import WRITES_NEW, _out, _report, safe_path, server
from ..verify import text_chars


@server.tool(annotations=WRITES_NEW)
def pdf_add_watermark(path: str, text: str | None = None, image: str | None = None,
                      opacity: float = 0.3, angle: float = 45, font_size: float = 60,
                      scale: float = 0.5, color: str = "gray", position: str = "center",
                      tile: bool = False, pages: str = "all", output: str | None = None,
                      password: str | None = None) -> dict[str, Any]:
    """Write a copy of the PDF with a text or image watermark on the selected pages.

    Give exactly one of `text` (e.g. "DRAFT", "CONFIDENTIAL") or `image` (path to a PNG/JPG, e.g. a logo).
    opacity: 0-1 (default 0.3). angle: degrees counter-clockwise (default 45; 0 = horizontal).
    font_size: text size in points. scale: image width as a fraction of the page width.
    color: name ("red") or hex ("#ff0000"). position: center, top-left, top-center, top-right,
    center-left, center-right, bottom-left, bottom-center, bottom-right. tile=true repeats it
    across the whole page. Rotated pages are handled so the watermark appears upright.
    """
    src = safe_path(path)
    img = safe_path(image) if image else None
    total = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    out = brand.watermark(src, text, image=img, opacity=opacity, angle=angle, font_size=font_size,
                          scale=scale, color=color, position=position, tile=tile, pages=pages,
                          out=_out(output), password=password)
    return _report(out, total, had_text, password)


@server.tool(annotations=WRITES_NEW)
def pdf_add_page_numbers(path: str, position: str = "bottom-center", format: str = "{n}",
                         start: int = 1, font_size: float = 10, margin: float = 28,
                         color: str = "black", pages: str = "all", output: str | None = None,
                         password: str | None = None) -> dict[str, Any]:
    """Write a copy of the PDF with page numbers on the selected pages.

    position: bottom-center (default), bottom-left, bottom-right, top-left, top-center, top-right.
    format: label with {n} and {total}, e.g. "{n}" or "Page {n} of {total}".
    Only the selected pages are numbered: the first selected page shows `start`, the next start+1,
    and {total} is the last number shown. To skip a cover page use pages="2-", start=1.
    font_size and margin (distance from the edge) are in points.
    """
    src = safe_path(path)
    total = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    out = brand.page_numbers(src, position=position, fmt=format, start=start, font_size=font_size,
                             margin=margin, color=color, pages=pages, out=_out(output),
                             password=password)
    return _report(out, total, had_text, password)


@server.tool(annotations=WRITES_NEW)
def pdf_add_header_footer(path: str, header: str | None = None, footer: str | None = None,
                          align: str = "center", font_size: float = 10, margin: float = 28,
                          color: str = "black", pages: str = "all", output: str | None = None,
                          password: str | None = None) -> dict[str, Any]:
    """Write a copy of the PDF with a header and/or footer line on the selected pages.

    Placeholders in header/footer text: {n} (page number in the document), {total} (pages in the
    document), {filename} (input file name), {date} (today, YYYY-MM-DD).
    Example: header="{filename}", footer="Page {n} of {total}".
    align: left, center (default) or right. font_size and margin are in points.
    """
    src = safe_path(path)
    total = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    out = brand.header_footer(src, header, footer, align=align, font_size=font_size, margin=margin,
                              color=color, pages=pages, out=_out(output), password=password)
    return _report(out, total, had_text, password)
