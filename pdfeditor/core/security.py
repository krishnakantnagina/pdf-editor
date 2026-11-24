"""Password protection: add AES-256 encryption or remove it.

Rules:
- `protect` always uses AES-256 (PDF 2.0 security handler, R=6).
- The user password is needed to open the file. It may be "" (anyone can open
  the file, but the permissions still apply) only if you also give an owner
  password, so an empty user password is always a deliberate choice.
- The owner password lifts the permissions. If you don't give one, a random
  32-byte secret is used and thrown away: nobody can lift the restrictions
  later, so pass an owner password if you may need to.
- `unlock` removes encryption. If the file restricts printing, copying or
  editing, it needs the owner password: the user password alone only opens it.
- Passwords are never printed, logged, returned, or put into error messages.
"""

from __future__ import annotations

import secrets
import warnings
from pathlib import Path

import pikepdf

from .pages import output_path


class WrongPasswordError(ValueError):
    """The password is missing or wrong. The message never contains the password."""


class PermissionDeniedError(ValueError):
    """The file opened, but only the owner password may change its security."""


def _open(path: Path, password: str | None) -> pikepdf.Pdf:
    try:
        with warnings.catch_warnings():  # "password given but not needed" is harmless here
            warnings.simplefilter("ignore", UserWarning)
            return pikepdf.open(path, password=password or "")
    except pikepdf.PasswordError:
        what = "wrong password" if password else "this PDF needs a password"
        raise WrongPasswordError(f"{Path(path).name}: {what}") from None


def _restricted(pdf: pikepdf.Pdf) -> bool:
    allow = pdf.allow
    return not all((allow.print_highres, allow.print_lowres, allow.extract, allow.modify_other,
                    allow.modify_annotation, allow.modify_form, allow.modify_assembly))


def _require_owner(pdf: pikepdf.Pdf, path: Path) -> None:
    """Don't let a user-password holder strip restrictions set by the owner."""
    if pdf.is_encrypted and not pdf.owner_password_matched and _restricted(pdf):
        raise PermissionDeniedError(
            f"{Path(path).name} has restricted permissions; the owner password is needed "
            "to change or remove its security"
        )


def permissions(allow_print: bool = True, allow_copy: bool = True, allow_modify: bool = True,
                allow_annotate: bool = True) -> pikepdf.Permissions:
    return pikepdf.Permissions(
        accessibility=True,  # screen readers may always read the text
        extract=allow_copy,
        modify_annotation=allow_annotate,
        modify_form=allow_annotate,
        modify_assembly=allow_modify,
        modify_other=allow_modify,
        print_lowres=allow_print,
        print_highres=allow_print,
    )


def protect(path: Path, user_password: str, owner_password: str | None = None,
            allow_print: bool = True, allow_copy: bool = True, allow_modify: bool = True,
            allow_annotate: bool = True, out: Path | None = None,
            password: str | None = None) -> Path:
    """Write an AES-256 encrypted copy. `password` opens an already-encrypted input."""
    if user_password is None:
        raise ValueError("a user password is required (use \"\" with an owner password for a permissions-only lock)")
    if owner_password == "":
        raise ValueError("the owner password cannot be empty")
    if user_password == "" and owner_password is None:
        raise ValueError("an empty user password needs an owner password (permissions-only lock)")
    if owner_password is not None and owner_password == user_password:
        raise ValueError("the owner password must be different from the user password")
    owner = owner_password if owner_password is not None else secrets.token_urlsafe(32)

    path = Path(path)
    with _open(path, password) as pdf:
        _require_owner(pdf, path)
        out = output_path(path, "protected", out)
        enc = pikepdf.Encryption(
            owner=owner, user=user_password, R=6, aes=True, metadata=True,
            allow=permissions(allow_print, allow_copy, allow_modify, allow_annotate),
        )
        pdf.save(out, encryption=enc, object_stream_mode=pikepdf.ObjectStreamMode.generate)

    with pikepdf.open(out, password=user_password) as check:  # make sure it really is encrypted
        if not check.is_encrypted or check.encryption.R != 6:
            raise RuntimeError("encryption was not applied")
    return out


def unlock(path: Path, password: str, out: Path | None = None) -> Path:
    """Write a copy with encryption removed."""
    path = Path(path)
    with _open(path, password) as pdf:
        if not pdf.is_encrypted:
            raise ValueError(f"{path.name} is not encrypted; nothing to unlock")
        _require_owner(pdf, path)
        out = output_path(path, "unlocked", out)
        pdf.save(out, encryption=False, object_stream_mode=pikepdf.ObjectStreamMode.generate)
    return out


def is_encrypted(path: Path) -> bool:
    """True if the file has any encryption (even with an empty user password)."""
    try:
        with pikepdf.open(path) as pdf:
            return pdf.is_encrypted
    except pikepdf.PasswordError:
        return True
