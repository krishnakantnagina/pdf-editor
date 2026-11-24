"""MCP server: exposes pdfeditor tools to Claude Code and any other MCP client.

Run:  pdfedit-mcp            (stdio transport)
Add to Claude Code:  claude mcp add pdf-editor -- pdfedit-mcp

Security: tools can only read and write files inside allowed folders.
Set PDFEDIT_ALLOWED_DIRS (separated by ';' on Windows, ':' elsewhere) to choose them.
Default: the user's home folder and the folder the server was started in.
Originals are never modified; every output is verified before it is reported.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import __version__
from .core import organize, view
from .core.pages import parse_pages
from .verify import text_chars, verify

server = MCPServer(
    name="pdf-editor",
    title="PDF Editor",
    version=__version__,
    instructions=(
        "Offline PDF tools. All paths must be absolute or relative to the server's start folder. "
        "Inputs are never modified: each tool writes a new file and returns its path plus a "
        "verification result (opens, renders, page count, text kept). Page specs are 1-based: "
        '"3", "1-3", "5-", "-3", "last", "odd", "even", "reverse", "all", comma-separated.'
    ),
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
WRITES_NEW = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False,
                             openWorldHint=False)


# ---------- path safety ----------

def allowed_roots() -> list[Path]:
    env = os.environ.get("PDFEDIT_ALLOWED_DIRS")
    if env:
        roots = [Path(p).expanduser() for p in env.split(os.pathsep) if p.strip()]
    else:
        roots = [Path.home(), Path.cwd()]
    return [r.resolve() for r in roots]


def safe_path(p: str, must_exist: bool = True) -> Path:
    path = Path(p).expanduser().resolve()
    if not any(path == r or path.is_relative_to(r) for r in allowed_roots()):
        raise PermissionError(
            f"{path} is outside the allowed folders. Set PDFEDIT_ALLOWED_DIRS to allow it."
        )
    if must_exist and not path.exists():
        raise FileNotFoundError(f"not found: {path}")
    return path


def _out(p: str | None) -> Path | None:
    return safe_path(p, must_exist=False) if p else None


def _report(out: Path, expected_pages: int | None, had_text: bool,
            password: str | None = None) -> dict[str, Any]:
    res = verify(out, expected_pages=expected_pages, expect_text=had_text, password=password)
    return {
        "output": str(out),
        "verified": res.ok,
        "pages": res.pages,
        "text_chars": res.text_chars,
        "problems": res.problems,
    }


# ---------- tools ----------

@server.tool(annotations=READ_ONLY)
def pdf_info(path: str, password: str | None = None) -> dict[str, Any]:
    """Describe a PDF: pages, page sizes, file size, version, encryption, fonts, images, forms, bookmarks, metadata."""
    i = view.get_info(safe_path(path), password)
    return {
        "path": str(i.path),
        "pages": i.pages,
        "file_size": view.human_size(i.file_size),
        "pdf_version": i.pdf_version,
        "encrypted": i.encrypted,
        "page_sizes": dict(i.page_sizes),
        "fonts": i.fonts,
        "images": i.images,
        "has_forms": i.has_forms,
        "has_bookmarks": i.has_outline,
        "metadata": i.metadata,
    }


@server.tool(annotations=READ_ONLY)
def pdf_verify(path: str, expected_pages: int | None = None, password: str | None = None) -> dict[str, Any]:
    """Check a PDF opens, renders and (optionally) has the expected page count."""
    p = safe_path(path)
    return _report(p, expected_pages, False, password)


@server.tool(annotations=WRITES_NEW)
def pdf_merge(paths: list[str], output: str, password: str | None = None) -> dict[str, Any]:
    """Merge PDFs, in the given order, into a new file at `output`."""
    inputs = [safe_path(p) for p in paths]
    total = sum(view.get_info(p, password).pages for p in inputs)
    had_text = any(text_chars(p, password) for p in inputs)
    out = organize.merge(inputs, safe_path(output, must_exist=False), password)
    return _report(out, total, had_text, password)


@server.tool(annotations=WRITES_NEW)
def pdf_split(path: str, ranges: str | None = None, every: int | None = None,
              max_mb: float | None = None, output_dir: str | None = None,
              password: str | None = None) -> dict[str, Any]:
    """Split a PDF. Use exactly one of: ranges ("1-3,4-6,7-", one file per range), every (N pages per file), max_mb (size limit per file)."""
    src = safe_path(path)
    parts = organize.split(src, _out(output_dir), ranges=ranges, every=every,
                           max_mb=max_mb, password=password)
    reports = [_report(p, None, False, password) for p in parts]
    return {"parts": reports, "count": len(parts), "all_verified": all(r["verified"] for r in reports)}


@server.tool(annotations=WRITES_NEW)
def pdf_extract_pages(path: str, pages: str, output: str | None = None,
                      password: str | None = None) -> dict[str, Any]:
    """Copy the selected pages (in the given order) into a new PDF."""
    src = safe_path(path)
    n = len(parse_pages(pages, view.get_info(src, password).pages))
    out = organize.extract(src, pages, _out(output), password)
    return _report(out, n, False, password)


@server.tool(annotations=WRITES_NEW)
def pdf_delete_pages(path: str, pages: str, output: str | None = None,
                     password: str | None = None) -> dict[str, Any]:
    """Write a copy of the PDF without the selected pages."""
    src = safe_path(path)
    total = view.get_info(src, password).pages
    removed = len(set(parse_pages(pages, total)))
    out = organize.delete(src, pages, _out(output), password)
    return _report(out, total - removed, False, password)


@server.tool(annotations=WRITES_NEW)
def pdf_reorder_pages(path: str, order: str, allow_partial: bool = False,
                      output: str | None = None, password: str | None = None) -> dict[str, Any]:
    """Write a copy with pages in a new order, e.g. "3,1,2,4-" or "reverse". The order must use every page once unless allow_partial is true."""
    src = safe_path(path)
    n = len(parse_pages(order, view.get_info(src, password).pages))
    had_text = text_chars(src, password) > 0
    out = organize.reorder(src, order, _out(output), password, allow_partial=allow_partial)
    return _report(out, n, had_text and not allow_partial, password)


@server.tool(annotations=WRITES_NEW)
def pdf_rotate_pages(path: str, angle: int, pages: str = "all", output: str | None = None,
                     password: str | None = None) -> dict[str, Any]:
    """Write a copy with the selected pages rotated clockwise by a multiple of 90 degrees (negative = counter-clockwise)."""
    src = safe_path(path)
    total = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    out = organize.rotate(src, angle, pages, _out(output), password)
    return _report(out, total, had_text, password)


def main() -> None:
    server.run("stdio")


# Feature-group tools register themselves on `server` (one file per group).
from .mcp_tools import brand as _brand, convert as _convert, optimize as _optimize  # noqa: E402,F401

if __name__ == "__main__":
    # `python -m pdfeditor.mcp_server` runs this file as __main__; delegate to the
    # imported module so tools registered on its `server` are the ones served.
    from pdfeditor.mcp_server import main as _main
    _main()
