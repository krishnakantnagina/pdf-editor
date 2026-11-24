"""Conversion MCP tools: pdf_to_images, pdf_from_images, pdf_extract_text."""

from __future__ import annotations

from typing import Any

from PIL import Image

from ..core import convert
from ..mcp_server import READ_ONLY, WRITES_NEW, _out, _report, safe_path, server


@server.tool(annotations=WRITES_NEW)
def pdf_to_images(path: str, output_dir: str | None = None, fmt: str = "png", dpi: int = 150,
                  pages: str = "all", jpg_quality: int = 90,
                  password: str | None = None) -> dict[str, Any]:
    """Render PDF pages to image files, one per page.

    fmt: "png" (lossless) or "jpg" (smaller; jpg_quality 1-100). dpi: 36-1200 (150 is good
    for screens, 300 for print/OCR). pages: page spec such as "1-3,7" or "all".
    Images go to output_dir (default: <name>_images/ next to the PDF), named <name>_p001.png.
    Returns the image paths, how many were written, and whether every image decodes.
    """
    src = safe_path(path)
    images = convert.to_images(src, _out(output_dir), fmt=fmt, dpi=dpi, pages=pages,
                               password=password, jpg_quality=jpg_quality)
    problems = []
    for img in images:
        try:
            with Image.open(img) as im:
                im.verify()
        except Exception as e:  # noqa: BLE001
            problems.append(f"{img.name}: {e}")
    return {
        "images": [str(p) for p in images],
        "count": len(images),
        "output_dir": str(images[0].parent) if images else None,
        "verified": not problems,
        "problems": problems,
    }


@server.tool(annotations=WRITES_NEW)
def pdf_from_images(images: list[str], output: str, page_size: str = "fit",
                    margin_mm: float = 0, sort: bool = True) -> dict[str, Any]:
    """Combine images into a new PDF at `output`, one page per image (one per frame for multi-page TIFF).

    images: image files and/or folders (jpg, jpeg, png, bmp, tif, tiff, webp). Files keep the
    given order; images inside a folder are sorted by name (natural order) when sort is true.
    page_size: "fit" (each page matches its image), "A4" or "Letter" (image scaled to fit inside
    the margins, page turned landscape for wide images). EXIF rotation is applied and
    transparency is flattened onto white.
    """
    inputs = [safe_path(p) for p in images]
    files = convert.collect_images(inputs, sort=sort)
    n = convert.count_pages(files)
    out = convert.from_images(files, safe_path(output, must_exist=False), page_size=page_size,
                              margin_mm=margin_mm, sort=sort)
    return _report(out, n, False)


@server.tool(annotations=READ_ONLY)
def pdf_extract_text(path: str, pages: str = "all", page_breaks: bool = True,
                     max_chars: int = 50_000, password: str | None = None) -> dict[str, Any]:
    """Return the plain text of a PDF (or selected pages) directly, without writing a file.

    With page_breaks each page starts with a "--- Page N ---" line. The text is cut at
    max_chars and `truncated` is set when that happens: then ask for fewer pages at a time.
    Scanned (image-only) pages have no text layer and return empty text.
    """
    if max_chars < 1:
        raise ValueError("max_chars must be at least 1")
    text = convert.to_text(safe_path(path), pages=pages, password=password, page_breaks=page_breaks)
    truncated = len(text) > max_chars
    return {
        "text": text[:max_chars],
        "chars": len(text),
        "truncated": truncated,
    }
