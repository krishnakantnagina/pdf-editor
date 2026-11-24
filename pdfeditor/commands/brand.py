"""Branding commands: watermark, page-numbers, header-footer."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..cli import OutOpt, PasswordOpt, _check, _fail, _page_count, app
from ..core import brand
from ..core.pages import PageSpecError
from ..verify import text_chars

PagesOpt = typer.Option("all", "--pages", help='Which pages, e.g. "1,3-5", "2-" or "odd".')


def _source_facts(file: Path, password: str | None) -> tuple[int, bool]:
    if not file.is_file():
        raise ValueError(f"not found: {file}")
    return _page_count(file, password), text_chars(file, password) > 0


@app.command()
def watermark(
    file: Path,
    text: Optional[str] = typer.Option(None, "--text", "-t", help='Watermark text, e.g. "DRAFT".'),
    image: Optional[Path] = typer.Option(None, "--image", "-i", help="PNG or JPG image to use instead of text."),
    opacity: float = typer.Option(0.3, "--opacity", help="0 (invisible) to 1 (solid)."),
    angle: float = typer.Option(45, "--angle", help="Rotation in degrees, counter-clockwise."),
    font_size: float = typer.Option(60, "--font-size", help="Text size in points."),
    scale: float = typer.Option(0.5, "--scale", help="Image width as a fraction of the page width."),
    color: str = typer.Option("gray", "--color", help='Text color: a name ("red") or hex ("#ff0000").'),
    position: str = typer.Option("center", "--position", help="center, top-left, top-center, top-right, "
                                 "center-left, center-right, bottom-left, bottom-center, bottom-right."),
    tile: bool = typer.Option(False, "--tile", help="Repeat the watermark across the whole page."),
    pages: str = PagesOpt,
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Stamp a text or image watermark on all or selected pages."""
    try:
        total, had_text = _source_facts(file, password)
        result = brand.watermark(file, text, image=image, opacity=opacity, angle=angle,
                                 font_size=font_size, scale=scale, color=color, position=position,
                                 tile=tile, pages=pages, out=out, password=password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Watermarked -> {result}")
    _check(result, total, had_text, password)


@app.command("page-numbers")
def page_numbers(
    file: Path,
    position: str = typer.Option("bottom-center", "--position", help="bottom-center, bottom-left, "
                                 "bottom-right, top-left, top-center or top-right."),
    fmt: str = typer.Option("{n}", "--format", "-f", help='Label format with {n} and {total}, e.g. "Page {n} of {total}".'),
    start: int = typer.Option(1, "--start", help="Number shown on the first selected page."),
    font_size: float = typer.Option(10, "--font-size", help="Text size in points."),
    margin: float = typer.Option(28, "--margin", help="Distance from the page edge in points."),
    color: str = typer.Option("black", "--color", help='Text color: a name or hex like "#333333".'),
    pages: str = PagesOpt,
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Add page numbers. Only the selected pages are numbered, counting from --start."""
    try:
        total, had_text = _source_facts(file, password)
        result = brand.page_numbers(file, position=position, fmt=fmt, start=start, font_size=font_size,
                                    margin=margin, color=color, pages=pages, out=out, password=password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Numbered -> {result}")
    _check(result, total, had_text, password)


@app.command("header-footer")
def header_footer(
    file: Path,
    header: Optional[str] = typer.Option(None, "--header", help="Header text. Placeholders: {n} {total} {filename} {date}."),
    footer: Optional[str] = typer.Option(None, "--footer", help="Footer text. Same placeholders as --header."),
    align: str = typer.Option("center", "--align", help="left, center or right."),
    font_size: float = typer.Option(10, "--font-size", help="Text size in points."),
    margin: float = typer.Option(28, "--margin", help="Distance from the page edge in points."),
    color: str = typer.Option("black", "--color", help='Text color: a name or hex like "#333333".'),
    pages: str = PagesOpt,
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Add a header and/or footer line to all or selected pages."""
    try:
        total, had_text = _source_facts(file, password)
        result = brand.header_footer(file, header, footer, align=align, font_size=font_size,
                                     margin=margin, color=color, pages=pages, out=out, password=password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Added header/footer -> {result}")
    _check(result, total, had_text, password)
