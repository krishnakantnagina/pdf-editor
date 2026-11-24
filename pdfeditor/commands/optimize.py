"""CLI: compress, protect, unlock."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

import pikepdf
import typer

from ..cli import OutOpt, PasswordOpt, _check, _fail, app
from ..core import optimize as core_optimize
from ..core import security, view
from ..verify import text_chars


class Level(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


def _pages_and_text(file: Path, password: str | None) -> tuple[int, bool]:
    try:
        return view.get_info(file, password).pages, text_chars(file, password) > 0
    except pikepdf.PasswordError:
        _fail(f"{file.name}: {'wrong password' if password else 'this PDF needs a password (use --password)'}")
    except FileNotFoundError:
        _fail(f"not found: {file}")
    raise AssertionError  # unreachable: _fail exits


@app.command()
def compress(
    file: Path,
    level: Level = typer.Option(Level.medium, "--level", "-l",
                                help="low = lossless; medium = JPEG q75, max 150 dpi; high = JPEG q50, max 100 dpi."),
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Make a PDF smaller. Text and vector graphics are never touched."""
    pages, had_text = _pages_and_text(file, password)
    try:
        r = core_optimize.compress(file, level.value, out, password)
    except (ValueError, pikepdf.PdfError) as e:
        _fail(str(e))
    before, after = view.human_size(r.size_before), view.human_size(r.size_after)
    if r.saved_bytes > 0:
        typer.echo(f"Compressed ({level.value}): {before} -> {after} ({r.saved_percent:.1f}% smaller, "
                   f"{r.images_recompressed} images re-encoded) -> {r.output}")
    else:
        typer.echo(f"No size gain at level {level.value} ({before}); wrote an unchanged copy -> {r.output}")
    _check(r.output, pages, had_text, password)


@app.command()
def protect(
    file: Path,
    user_password: str = typer.Option(
        ..., "--user-password", "-u", prompt="User password (needed to open the file)",
        hide_input=True, confirmation_prompt=True,
        help='Password to open the file. Asked for if not given (keeps it out of shell history). '
             '"" = anyone can open, permissions still apply (needs --owner-password).'),
    owner_password: Optional[str] = typer.Option(
        None, "--owner-password",
        help="Password that lifts the restrictions. Default: a random secret nobody knows."),
    no_print: bool = typer.Option(False, "--no-print", help="Do not allow printing."),
    no_copy: bool = typer.Option(False, "--no-copy", help="Do not allow copying text and images."),
    no_modify: bool = typer.Option(False, "--no-modify", help="Do not allow editing or page assembly."),
    no_annotate: bool = typer.Option(False, "--no-annotate", help="Do not allow comments or form filling."),
    out: Optional[Path] = OutOpt,
    password: Optional[str] = PasswordOpt,
) -> None:
    """Encrypt a PDF with AES-256 and optional permission limits."""
    pages, had_text = _pages_and_text(file, password)
    try:
        result = security.protect(file, user_password, owner_password,
                                  allow_print=not no_print, allow_copy=not no_copy,
                                  allow_modify=not no_modify, allow_annotate=not no_annotate,
                                  out=out, password=password)
    except ValueError as e:
        _fail(str(e))
    limits = [n for n, off in (("print", no_print), ("copy", no_copy), ("modify", no_modify),
                               ("annotate", no_annotate)) if off]
    typer.echo(f"Protected with AES-256 -> {result}")
    typer.echo(f"  Blocked: {', '.join(limits) if limits else 'nothing (all permissions allowed)'}")
    if owner_password is None and limits:
        typer.echo("  Note: no owner password given, so these limits can never be lifted.")
    _check(result, pages, had_text, user_password or None)


@app.command()
def unlock(
    file: Path,
    password: str = typer.Option(..., "--password", "-p", prompt="Password", hide_input=True,
                                 help="Current password (owner password if the file has restrictions)."),
    out: Optional[Path] = OutOpt,
) -> None:
    """Remove the password and restrictions from a PDF."""
    pages, had_text = _pages_and_text(file, password)
    try:
        result = security.unlock(file, password, out)
    except ValueError as e:
        _fail(str(e))
    typer.echo(f"Unlocked -> {result}")
    _check(result, pages, had_text)
