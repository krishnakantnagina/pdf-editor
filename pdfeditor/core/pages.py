"""Page-range parsing and output-path helpers shared by all commands."""

from __future__ import annotations

from pathlib import Path


class PageSpecError(ValueError):
    pass


def parse_pages(spec: str, total: int) -> list[int]:
    """Turn a 1-based page spec into a list of 0-based indexes, in the given order.

    Accepts: "3", "1-3", "5-" (to end), "-3" (start to 3), "last", "odd", "even",
    "reverse", "all", and comma-separated combinations like "1-3,7,10-".
    Duplicates are kept so the same spec can express duplication/reordering.
    """
    if total < 1:
        raise PageSpecError("document has no pages")
    spec = spec.strip().lower()
    if not spec:
        raise PageSpecError("empty page spec")

    result: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if part == "all":
            result.extend(range(total))
        elif part == "odd":
            result.extend(range(0, total, 2))
        elif part == "even":
            result.extend(range(1, total, 2))
        elif part == "reverse":
            result.extend(range(total - 1, -1, -1))
        elif "-" in part:
            a, b = part.split("-", 1)
            start = _num(a, total) if a else 1
            end = _num(b, total) if b else total
            step = 1 if end >= start else -1
            result.extend(i - 1 for i in range(start, end + step, step))
        else:
            result.append(_num(part, total) - 1)
    return result


def _num(token: str, total: int) -> int:
    token = token.strip()
    if token == "last":
        return total
    if not token.isdigit():
        raise PageSpecError(f"not a page number: {token!r}")
    n = int(token)
    if not 1 <= n <= total:
        raise PageSpecError(f"page {n} is out of range (document has {total} pages)")
    return n


def output_path(src: Path, op: str, out: Path | None = None, suffix: str = ".pdf") -> Path:
    """Pick an output path that never overwrites the input or an existing file.

    If `out` is given it is used as-is (but must not be the input file).
    Otherwise: <src_dir>/<stem>_<op>.pdf, adding _2, _3 ... if it exists.
    """
    src = Path(src)
    if out is not None:
        out = Path(out)
        if out.resolve() == src.resolve():
            raise ValueError("output path is the same as the input; originals are never overwritten")
        out.parent.mkdir(parents=True, exist_ok=True)
        return out
    candidate = src.with_name(f"{src.stem}_{op}{suffix}")
    n = 2
    while candidate.exists():
        candidate = src.with_name(f"{src.stem}_{op}_{n}{suffix}")
        n += 1
    return candidate
