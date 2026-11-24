"""Conversion commands: to-images, from-images, to-text."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pypdfium2 as pdfium
import typer
from PIL import Image

from ..cli import PasswordOpt, _check, _fail, app
from ..core import convert
from ..core.pages import PageSpecError

_ERRORS = (ValueError, PageSpecError, OSError, pdfium.PdfiumError)


@app.command("to-images")
def to_images(
    file: Path,
    fmt: str = typer.Option("png", "--format", "-f", help="png or jpg."),
    dpi: int = typer.Option(150, "--dpi", help=f"Resolution ({convert.MIN_DPI}-{convert.MAX_DPI})."),
    pages: str = typer.Option("all", "--pages", help='Which pages, e.g. "1,3-5" or "odd".'),
    quality: int = typer.Option(90, "--quality", "-q", help="JPEG quality (1-100)."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", "-d", help="Folder for images (default: <name>_images/)."),
    password: Optional[str] = PasswordOpt,
) -> None:
    """Render pages to PNG or JPEG images, one file per page."""
    if not file.exists():
        _fail(f"not found: {file}")
    try:
        images = convert.to_images(file, out_dir, fmt=fmt, dpi=dpi, pages=pages,
                                   password=password, jpg_quality=quality)
    except _ERRORS as e:
        _fail(str(e))
    for img in images:  # verify: every image exists and decodes
        try:
            with Image.open(img) as im:
                im.verify()
        except Exception as e:  # noqa: BLE001
            _fail(f"bad image {img.name}: {e}")
    typer.secho(f"[OK] Wrote {len(images)} images to {images[0].parent}", fg=typer.colors.GREEN)


@app.command("from-images")
def from_images(
    images: list[Path] = typer.Argument(..., help="Image files and/or folders (jpg, png, bmp, tif, webp)."),
    out: Path = typer.Option(..., "--out", "-o", help="Output PDF."),
    page_size: str = typer.Option("fit", "--page-size", "-s", help="fit (page = image size), A4 or Letter."),
    margin: float = typer.Option(0, "--margin", "-m", help="Margin around each image, in mm."),
    sort: bool = typer.Option(True, "--sort/--no-sort", help="Sort images inside folders by name (natural order)."),
) -> None:
    """Combine images into a PDF, one page per image."""
    try:
        files = convert.collect_images(images, sort=sort)
        n = convert.count_pages(files)
        result = convert.from_images(files, out, page_size=page_size, margin_mm=margin, sort=sort)
    except _ERRORS as e:
        _fail(str(e))
    typer.echo(f"Combined {len(files)} images -> {result}")
    _check(result, expected_pages=n, src_had_text=False)


@app.command("to-text")
def to_text(
    file: Path,
    pages: str = typer.Option("all", "--pages", help='Which pages, e.g. "1,3-5" or "odd".'),
    no_markers: bool = typer.Option(False, "--no-markers", help='Leave out the "--- Page N ---" lines.'),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Write to this .txt file instead of the screen."),
    password: Optional[str] = PasswordOpt,
) -> None:
    """Extract plain text (prints it, or writes it to a .txt file with -o)."""
    if not file.exists():
        _fail(f"not found: {file}")
    try:
        text = convert.to_text(file, pages=pages, password=password,
                               page_breaks=not no_markers, out=out)
    except _ERRORS as e:
        _fail(str(e))
    if out is None:
        typer.echo(text, nl=False)
    else:
        chars = sum(1 for c in text if not c.isspace())
        typer.secho(f"[OK] Wrote {chars} text chars -> {out}", fg=typer.colors.GREEN)
