"""MCP tools: pdf_compress, pdf_protect, pdf_unlock.

Results never contain passwords.
"""

from __future__ import annotations

from typing import Any, Literal

from ..core import optimize as core_optimize
from ..core import security, view
from ..mcp_server import WRITES_NEW, _out, _report, safe_path, server
from ..verify import text_chars


@server.tool(annotations=WRITES_NEW)
def pdf_compress(path: str, level: Literal["low", "medium", "high"] = "medium",
                 output: str | None = None, password: str | None = None) -> dict[str, Any]:
    """Write a smaller copy of a PDF. Text and vector graphics are never changed.

    level: "low" = lossless (object streams, recompressed streams, unused resources
    and duplicate images removed); "medium" = also re-encode large photos as JPEG
    quality 75 at most 150 dpi; "high" = JPEG quality 50 at most 100 dpi.
    The output is never larger than the input (if nothing helps, it is an unchanged
    copy). Encrypted inputs need `password` and stay encrypted.
    Returns sizes in bytes, percent saved, and the verification result.
    """
    src = safe_path(path)
    pages = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    r = core_optimize.compress(src, level, _out(output), password)
    report = _report(r.output, pages, had_text, password)
    report.update({
        "level": level,
        "size_before": r.size_before,
        "size_after": r.size_after,
        "saved_percent": round(r.saved_percent, 1),
        "images_recompressed": r.images_recompressed,
    })
    return report


@server.tool(annotations=WRITES_NEW)
def pdf_protect(path: str, user_password: str, owner_password: str | None = None,
                allow_print: bool = True, allow_copy: bool = True, allow_modify: bool = True,
                allow_annotate: bool = True, output: str | None = None,
                password: str | None = None) -> dict[str, Any]:
    """Write an AES-256 encrypted copy of a PDF.

    user_password opens the file. It may be "" (anyone can open it, but the
    permissions still apply) only together with an owner_password.
    owner_password lifts the permissions; if omitted, a random secret is used and
    the limits can never be lifted. allow_* switch printing, copying text/images,
    editing/page assembly, and comments/form filling on or off.
    `password` opens an already-encrypted input. Passwords are not echoed back.
    """
    src = safe_path(path)
    pages = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    out = security.protect(src, user_password, owner_password, allow_print=allow_print,
                           allow_copy=allow_copy, allow_modify=allow_modify,
                           allow_annotate=allow_annotate, out=_out(output), password=password)
    report = _report(out, pages, had_text, user_password or None)
    report.update({
        "encryption": "AES-256 (R6)",
        "permissions": {"print": allow_print, "copy": allow_copy,
                        "modify": allow_modify, "annotate": allow_annotate},
        "owner_password_set": owner_password is not None,
    })
    return report


@server.tool(annotations=WRITES_NEW)
def pdf_unlock(path: str, password: str, output: str | None = None) -> dict[str, Any]:
    """Write a copy of an encrypted PDF with the password and restrictions removed.

    If the file restricts printing, copying or editing, `password` must be the owner
    password; the user password alone only opens such a file.
    """
    src = safe_path(path)
    pages = view.get_info(src, password).pages
    had_text = text_chars(src, password) > 0
    out = security.unlock(src, password, _out(output))
    return _report(out, pages, had_text)
