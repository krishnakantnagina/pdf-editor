"""Page organization: merge, split, extract, delete, reorder, rotate.

All functions read the input, write a NEW file, and return the output path(s).
Inputs are never modified.

Encryption: pages are rearranged *inside* the opened source document and saved with
`encryption=True`, so an encrypted input gives an output with the SAME passwords and
permissions. Opening a restricted file with only the user password therefore can't be
used to strip its restrictions.
"""

from __future__ import annotations

import io
from contextlib import ExitStack
from pathlib import Path

import pikepdf

from .pages import PageSpecError, output_path, parse_pages


def _open(path: Path, password: str | None) -> pikepdf.Pdf:
    return pikepdf.open(path, password=password or "")


def _save(pdf: pikepdf.Pdf, out) -> Path:
    """Save, keeping the source's encryption (same passwords + permissions) if it had any."""
    pdf.save(out, object_stream_mode=pikepdf.ObjectStreamMode.generate,
             encryption=pdf.is_encrypted)
    return out


def _keep_pages(pdf: pikepdf.Pdf, indexes: list[int]) -> None:
    """Rearrange pdf in place so it contains exactly pages[indexes], in that order.

    Works within the same document (duplicates allowed), so document-level data
    (metadata, encryption) is preserved.
    """
    n = len(pdf.pages)
    for i in indexes:
        pdf.pages.append(pdf.pages[i])
    for _ in range(n):
        del pdf.pages[0]


def merge(inputs: list[Path], out: Path, password: str | None = None) -> Path:
    if len(inputs) < 2:
        raise ValueError("merge needs at least 2 files")
    for p in inputs:
        if Path(p).resolve() == Path(out).resolve():
            raise ValueError("output path is one of the inputs; originals are never overwritten")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        # The first file is the base: its metadata and encryption carry over.
        result = stack.enter_context(_open(inputs[0], password))
        for p in inputs[1:]:
            src = stack.enter_context(_open(p, password))
            if src.is_encrypted:
                raise ValueError(
                    f"{Path(p).name} is password-protected; merging would remove its protection. "
                    "Put it first, or unlock it first with `pdfedit unlock`."
                )
            result.pages.extend(src.pages)
        return _save(result, Path(out))


def _write_subset(path: Path, password: str | None, indexes: list[int], out) -> Path:
    with _open(path, password) as pdf:
        _keep_pages(pdf, indexes)
        return _save(pdf, out)


def extract(path: Path, pages: str, out: Path | None = None, password: str | None = None) -> Path:
    path = Path(path)
    with _open(path, password) as src:
        idx = parse_pages(pages, len(src.pages))
    return _write_subset(path, password, idx, output_path(path, "extract", out))


def delete(path: Path, pages: str, out: Path | None = None, password: str | None = None) -> Path:
    path = Path(path)
    with _open(path, password) as src:
        total = len(src.pages)
        remove = set(parse_pages(pages, total))
        keep = [i for i in range(total) if i not in remove]
        if not keep:
            raise PageSpecError("that would delete every page")
    return _write_subset(path, password, keep, output_path(path, "delete", out))


def reorder(path: Path, order: str, out: Path | None = None, password: str | None = None,
            allow_partial: bool = False) -> Path:
    """New page order, e.g. "3,1,2,4-" or "reverse".

    By default the order must use every page exactly once (so nothing is lost or
    duplicated by mistake). Use allow_partial=True to drop/duplicate pages.
    """
    path = Path(path)
    with _open(path, password) as src:
        total = len(src.pages)
        idx = parse_pages(order, total)
        if not allow_partial and sorted(idx) != list(range(total)):
            missing = sorted(set(range(total)) - set(idx))
            dupes = sorted({i for i in idx if idx.count(i) > 1})
            msg = []
            if missing:
                msg.append("missing pages " + ",".join(str(i + 1) for i in missing))
            if dupes:
                msg.append("repeated pages " + ",".join(str(i + 1) for i in dupes))
            raise PageSpecError("order must list every page once: " + "; ".join(msg))
    return _write_subset(path, password, idx, output_path(path, "reorder", out))


def rotate(path: Path, angle: int, pages: str = "all", out: Path | None = None,
           password: str | None = None) -> Path:
    if angle % 90 != 0:
        raise ValueError("angle must be a multiple of 90")
    path = Path(path)
    with _open(path, password) as pdf:
        for i in set(parse_pages(pages, len(pdf.pages))):
            pdf.pages[i].rotate(angle, relative=True)
        return _save(pdf, output_path(path, "rotated", out))


def split(path: Path, out_dir: Path | None = None, *, ranges: str | None = None,
          every: int | None = None, max_mb: float | None = None,
          password: str | None = None) -> list[Path]:
    """Split into several files. Pick exactly one mode:

    ranges="1-3,4-6,7-"  -> one file per range
    every=N              -> chunks of N pages
    max_mb=X             -> chunks as large as possible but under X MB
    """
    modes = [m for m in (ranges, every, max_mb) if m]
    if len(modes) != 1:
        raise ValueError("choose exactly one of: ranges, every, max_mb")
    path = Path(path)
    out_dir = Path(out_dir) if out_dir else path.with_name(f"{path.stem}_split")
    out_dir.mkdir(parents=True, exist_ok=True)

    with _open(path, password) as src:
        total = len(src.pages)
        if ranges:
            groups = [parse_pages(r, total) for r in ranges.split(",")]
        elif every:
            if every < 1:
                raise ValueError("every must be at least 1")
            groups = [list(range(s, min(s + every, total))) for s in range(0, total, every)]
    if not ranges and not every:
        groups = _groups_by_size(path, password, total, int(max_mb * 1024 * 1024))

    width = len(str(len(groups)))
    outputs = []
    for n, idx in enumerate(groups, 1):
        out = out_dir / f"{path.stem}_part{n:0{width}d}.pdf"
        outputs.append(_write_subset(path, password, idx, out))
    return outputs


def _subset_size(path: Path, password: str | None, idx: list[int]) -> int:
    buf = io.BytesIO()
    _write_subset(path, password, idx, buf)
    return buf.tell()


def _groups_by_size(path: Path, password: str | None, total: int, limit: int) -> list[list[int]]:
    """Greedy: keep adding pages while the chunk stays under the limit.

    A single page bigger than the limit becomes its own chunk.
    """
    groups: list[list[int]] = []
    current: list[int] = []
    for i in range(total):
        trial = current + [i]
        if current and _subset_size(path, password, trial) > limit:
            groups.append(current)
            current = [i]
        else:
            current = trial
    if current:
        groups.append(current)
    return groups
