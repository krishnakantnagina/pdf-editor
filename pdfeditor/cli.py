"""pdfedit command-line interface."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .core import organize, view
from .core.pages import PageSpecError, parse_pages
from .verify import text_chars, verify

app = typer.Typer(
    help="Offline PDF toolkit. Originals are never modified; every output is verified.",
    no_args_is_help=True,
    add_completion=False,
)

PasswordOpt = typer.Option(None, "--password", "-p", help="Password for encrypted input.")
OutOpt = typer.Option(None, "--out", "-o", help="Output file (default: <name>_<operation>.pdf).")


def _fail(msg: str) -> None:
    typer.secho(f"Error: {msg}", fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def _check(out: Path, expected_pages: int | None, src_had_text: bool, password: str | None = None) -> None:
    res = verify(out, expected_pages=expected_pages, expect_text=src_had_text, password=password)
    typer.secho(str(res), fg=typer.colors.GREEN if res.ok else typer.colors.RED)
    if not res.ok:
        raise typer.Exit(2)


def _pdfs_in(paths: list[Path]) -> list[Path]:
    """Expand folders into their PDFs (sorted by name)."""
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files.extend(sorted(p.glob("*.pdf"), key=lambda x: x.name.lower()))
        elif p.exists():
            files.append(p)
        else:
            _fail(f"not found: {p}")
    return files


def _page_count(path: Path, password: str | None) -> int:
    return view.get_info(path, password).pages


@app.command()
def info(
    files: list[Path] = typer.Argument(..., help="PDF files or folders."),
    password: Optional[str] = PasswordOpt,
) -> None:
    """Show pages, sizes, metadata, fonts, images and security."""
    for path in _pdfs_in(files):
        try:
            i = view.get_info(path, password)
        except Exception as e:  # noqa: BLE001
            typer.secho(f"{path.name}: cannot open ({e})", fg=typer.colors.RED)
            continue
        typer.secho(f"\n{path.name}", bold=True)
        typer.echo(f"  Pages:       {i.pages}")
        typer.echo(f"  File size:   {view.human_size(i.file_size)}")
        typer.echo(f"  PDF version: {i.pdf_version}")
        typer.echo(f"  Encrypted:   {'yes' if i.encrypted else 'no'}")
        sizes = ", ".join(f"{name} x{n}" for name, n in i.page_sizes.most_common())
        typer.echo(f"  Page sizes:  {sizes}")
        typer.echo(f"  Images:      {i.images}")
        typer.echo(f"  Fonts:       {', '.join(i.fonts) if i.fonts else 'none (scanned or image-only?)'}")
        typer.echo(f"  Forms:       {'yes' if i.has_forms else 'no'}")
        typer.echo(f"  Bookmarks:   {'yes' if i.has_outline else 'no'}")
        if i.metadata:
            typer.echo("  Metadata:")
            for k, v in i.metadata.items():
                typer.echo(f"    {k}: {v}")


@app.command()
def merge(
    files: list[Path] = typer.Argument(..., help="PDFs (or a folder) in the order to merge."),
    out: Path = typer.Option(..., "--out", "-o", help="Output file."),
    password: Optional[str] = PasswordOpt,
) -> None:
    """Combine several PDFs into one."""
    inputs = _pdfs_in(files)
    try:
        total = sum(_page_count(p, password) for p in inputs)
        had_text = any(text_chars(p, password) for p in inputs)
        result = organize.merge(inputs, out, password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Merged {len(inputs)} files -> {result}")
    _check(result, total, had_text)


@app.command()
def split(
    file: Path,
    ranges: Optional[str] = typer.Option(None, "--ranges", "-r", help='One file per range, e.g. "1-3,4-6,7-".'),
    every: Optional[int] = typer.Option(None, "--every", "-n", help="Chunks of N pages."),
    max_mb: Optional[float] = typer.Option(None, "--max-mb", help="Chunks under this size in MB."),
    out_dir: Optional[Path] = typer.Option(None, "--out-dir", "-d", help="Folder for parts (default: <name>_split/)."),
    password: Optional[str] = PasswordOpt,
) -> None:
    """Split a PDF by ranges, every N pages, or maximum file size."""
    if ranges:
        ranges = ranges.replace(";", ",")
    try:
        parts = organize.split(file, out_dir, ranges=ranges, every=every, max_mb=max_mb, password=password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Split into {len(parts)} files in {parts[0].parent}")
    total = 0
    for p in parts:
        res = verify(p)
        total += res.pages
        typer.secho(str(res), fg=typer.colors.GREEN if res.ok else typer.colors.RED)
        if not res.ok:
            raise typer.Exit(2)
    if not ranges and total != _page_count(file, password):
        _fail(f"parts have {total} pages but source has {_page_count(file, password)}")


@app.command()
def extract(
    file: Path,
    pages: str = typer.Argument(..., help='Pages to keep, e.g. "1-3,7,10-", "odd", "last".'),
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Copy selected pages into a new PDF."""
    try:
        n = len(parse_pages(pages, _page_count(file, password)))
        result = organize.extract(file, pages, out, password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Extracted {n} pages -> {result}")
    _check(result, n, False)


@app.command()
def delete(
    file: Path,
    pages: str = typer.Argument(..., help='Pages to remove, e.g. "2,5-7".'),
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Remove pages."""
    try:
        total = _page_count(file, password)
        n_removed = len(set(parse_pages(pages, total)))
        result = organize.delete(file, pages, out, password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Removed {n_removed} pages -> {result}")
    _check(result, total - n_removed, False)


@app.command()
def reorder(
    file: Path,
    order: str = typer.Argument(..., help='New order, e.g. "3,1,2,4-" or "reverse".'),
    partial: bool = typer.Option(False, "--partial", help="Allow leaving out or repeating pages."),
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Put pages in a new order."""
    try:
        n = len(parse_pages(order, _page_count(file, password)))
        had_text = text_chars(file, password) > 0
        result = organize.reorder(file, order, out, password, allow_partial=partial)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Reordered -> {result}")
    _check(result, n, had_text and not partial)


@app.command()
def rotate(
    file: Path,
    angle: int = typer.Argument(..., help="90, 180, 270 (or -90)."),
    pages: str = typer.Option("all", "--pages", help='Which pages, e.g. "1,3-5" or "even".'),
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Rotate all or selected pages clockwise."""
    try:
        total = _page_count(file, password)
        had_text = text_chars(file, password) > 0
        result = organize.rotate(file, angle, pages, out, password)
    except (ValueError, PageSpecError) as e:
        _fail(str(e))
    typer.echo(f"Rotated -> {result}")
    _check(result, total, had_text, password)


# Feature-group commands register themselves on `app` (one file per group).
from .commands import brand, convert, optimize  # noqa: E402,F401

if __name__ == "__main__":
    from pdfeditor.cli import app as _app  # use the registered instance, not __main__'s copy
    _app()
