"""Conversion: PDF pages to images, images to PDF, PDF to plain text.

Rendering and text extraction use pypdfium2; building a PDF from images uses
Pillow (decoding, EXIF orientation, colour modes) and reportlab (page layout).
Inputs are never modified: every function writes NEW files and returns their path(s).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps, ImageSequence
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .pages import output_path, parse_pages

MIN_DPI = 36
MAX_DPI = 1200
IMAGE_FORMATS = ("png", "jpg")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
PAGE_SIZES = {"fit": None, "a4": A4, "letter": LETTER}


# ---------- PDF -> images ----------

def to_images(path: Path, out_dir: Path | None = None, fmt: str = "png", dpi: int = 150,
              pages: str = "all", password: str | None = None,
              jpg_quality: int = 90) -> list[Path]:
    """Render pages to PNG or JPEG files, one per page.

    Files go to `out_dir` (default: <stem>_images/ next to the input) and are named
    <stem>_p001.png, zero-padded to the page count's width (at least 3 digits).
    Page /Rotate is respected, so a rotated page comes out in its displayed orientation.
    """
    path = Path(path)
    fmt = fmt.lower().lstrip(".")
    if fmt == "jpeg":
        fmt = "jpg"
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"format must be one of: {', '.join(IMAGE_FORMATS)}")
    if not MIN_DPI <= dpi <= MAX_DPI:
        raise ValueError(f"dpi must be between {MIN_DPI} and {MAX_DPI}")
    if not 1 <= jpg_quality <= 100:
        raise ValueError("jpg_quality must be between 1 and 100")

    out_dir = Path(out_dir) if out_dir else path.with_name(f"{path.stem}_images")
    doc = pdfium.PdfDocument(str(path), password=password)
    try:
        total = len(doc)
        indexes = parse_pages(pages, total)
        out_dir.mkdir(parents=True, exist_ok=True)
        width = max(3, len(str(total)))
        outputs: list[Path] = []
        for i in indexes:
            out = out_dir / f"{path.stem}_p{i + 1:0{width}d}.{fmt}"
            if out in outputs:  # same page requested twice: render it once
                continue
            page = doc[i]
            try:
                bitmap = page.render(scale=dpi / 72)
                img = bitmap.to_pil()
                if fmt == "jpg":
                    img.convert("RGB").save(out, "JPEG", quality=jpg_quality, dpi=(dpi, dpi))
                else:
                    img.save(out, "PNG", dpi=(dpi, dpi))
                bitmap.close()
            finally:
                page.close()
            outputs.append(out)
        return outputs
    finally:
        doc.close()


# ---------- images -> PDF ----------

def _natural_key(p: Path) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def collect_images(inputs: list[Path], sort: bool = True) -> list[Path]:
    """Expand folders into their image files.

    Files given explicitly keep their order. A folder's images are added in natural
    name order (img2 before img10) when `sort` is true, else in file-system order.
    """
    files: list[Path] = []
    for p in inputs:
        p = Path(p)
        if p.is_dir():
            found = [f for f in p.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            files.extend(sorted(found, key=_natural_key) if sort else found)
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"not found: {p}")
    if not files:
        raise ValueError("no images found")
    return files


def _frames(path: Path) -> Iterator[Image.Image]:
    """Yield each frame (multi-page TIFF) as an upright RGB or L image."""
    with Image.open(path) as img:
        for frame in ImageSequence.Iterator(img):
            yield _normalize(ImageOps.exif_transpose(frame))


def _normalize(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white and convert to RGB or L."""
    if img.mode == "P":
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "RGB" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, "white")
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    if img.mode in ("1", "L"):
        return img.convert("L")
    if img.mode.startswith("I;16") or img.mode == "I":  # 16-bit greyscale -> 8-bit
        return img.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    if img.mode == "F":
        return img.convert("L")
    return img.convert("RGB")


def count_pages(images: list[Path]) -> int:
    """How many PDF pages from_images() will make (multi-frame TIFFs count each frame)."""
    total = 0
    for p in images:
        with Image.open(p) as img:
            total += getattr(img, "n_frames", 1)
    return total


def _image_dpi(info: dict) -> tuple[float, float]:
    dpi = info.get("dpi")
    try:
        x, y = float(dpi[0]), float(dpi[1])
    except (TypeError, ValueError, IndexError):
        return 72.0, 72.0
    if not (1 <= x <= 10000 and 1 <= y <= 10000):
        return 72.0, 72.0
    return x, y


def from_images(images: list[Path], out: Path, page_size: str = "fit", margin_mm: float = 0,
                sort: bool = True) -> Path:
    """Build a PDF with one page per image (one per frame for multi-page TIFFs).

    images: image files and/or folders (jpg, jpeg, png, bmp, tif, tiff, webp).
    page_size: "fit" makes each page the image's size (from its DPI, 72 if unknown)
    plus margins; "A4" or "Letter" scales each image to fit inside the margins,
    keeping its aspect ratio, on a portrait or landscape page to match the image.
    EXIF orientation is applied; transparency is flattened onto white.
    """
    size_key = page_size.strip().lower()
    if size_key not in PAGE_SIZES:
        raise ValueError("page_size must be fit, A4 or Letter")
    if margin_mm < 0:
        raise ValueError("margin_mm cannot be negative")
    files = collect_images(images, sort=sort)
    out = Path(out)
    for p in files:
        if p.resolve() == out.resolve():
            raise ValueError("output path is one of the inputs; originals are never overwritten")
    out.parent.mkdir(parents=True, exist_ok=True)

    margin = margin_mm * mm
    base = PAGE_SIZES[size_key]
    c = canvas.Canvas(str(out))
    c.setCreator("pdfeditor")
    pages = 0
    for p in files:
        try:
            with Image.open(p) as probe:
                dpi = _image_dpi(probe.info)
        except Exception as e:  # noqa: BLE001 - give a clear message for any bad image
            raise ValueError(f"cannot read image {p.name}: {e}") from e
        for img in _frames(p):
            w_px, h_px = img.size
            if base is None:
                img_w, img_h = w_px * 72 / dpi[0], h_px * 72 / dpi[1]
                page_w, page_h = img_w + 2 * margin, img_h + 2 * margin
                x, y = margin, margin
            else:
                short, long_ = sorted(base)
                page_w, page_h = (long_, short) if w_px > h_px else (short, long_)
                box_w, box_h = page_w - 2 * margin, page_h - 2 * margin
                if box_w <= 0 or box_h <= 0:
                    raise ValueError("margins are larger than the page")
                scale = min(box_w / w_px, box_h / h_px)
                img_w, img_h = w_px * scale, h_px * scale
                x, y = (page_w - img_w) / 2, (page_h - img_h) / 2
            c.setPageSize((page_w, page_h))
            c.drawImage(ImageReader(img), x, y, width=img_w, height=img_h)
            c.showPage()
            pages += 1
    if not pages:
        raise ValueError("no images found")
    c.save()
    return out


# ---------- PDF -> text ----------

def to_text(path: Path, pages: str = "all", password: str | None = None,
            page_breaks: bool = True, out: Path | None = None) -> str:
    """Extract plain text from the selected pages.

    With page_breaks=True each page's text is preceded by a marker line
    "--- Page N ---" (N is the 1-based page number in the source). Line endings
    are normalized to "\\n". If `out` is given the text is also written there as
    UTF-8 (pass a .txt path; the input is never overwritten).
    Scanned (image-only) pages have no text layer and give empty text.
    """
    path = Path(path)
    doc = pdfium.PdfDocument(str(path), password=password)
    try:
        chunks: list[str] = []
        for i in parse_pages(pages, len(doc)):
            page = doc[i]
            try:
                tp = page.get_textpage()
                text = tp.get_text_range().replace("\r\n", "\n").replace("\r", "\n").strip("\n")
                tp.close()
            finally:
                page.close()
            chunks.append(f"--- Page {i + 1} ---\n{text}" if page_breaks else text)
    finally:
        doc.close()
    result = "\n\n".join(chunks) + "\n"
    if out is not None:
        target = output_path(path, "text", out, suffix=".txt")
        target.write_text(result, encoding="utf-8")
    return result
