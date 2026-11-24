"""Read-only document information."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

PT_PER_MM = 72 / 25.4

KNOWN_SIZES = {  # (width_mm, height_mm) portrait
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
}


@dataclass
class DocInfo:
    path: Path
    pdf_version: str
    encrypted: bool
    pages: int
    file_size: int
    metadata: dict[str, str]
    page_sizes: Counter = field(default_factory=Counter)
    fonts: list[str] = field(default_factory=list)
    images: int = 0
    has_forms: bool = False
    has_outline: bool = False


def size_name(w_pt: float, h_pt: float) -> str:
    w, h = w_pt / PT_PER_MM, h_pt / PT_PER_MM
    portrait = (min(w, h), max(w, h))
    for name, (sw, sh) in KNOWN_SIZES.items():
        if abs(portrait[0] - sw) < 3 and abs(portrait[1] - sh) < 3:
            orient = "portrait" if h >= w else "landscape"
            return f"{name} {orient}"
    return f"{w:.0f} x {h:.0f} mm"


def get_info(path: Path, password: str | None = None) -> DocInfo:
    path = Path(path)
    with pikepdf.open(path, password=password or "") as pdf:
        meta = {}
        for key, value in pdf.docinfo.items():
            try:
                meta[str(key).lstrip("/")] = str(value)
            except Exception:  # noqa: BLE001 - odd metadata types
                meta[str(key).lstrip("/")] = repr(value)

        info = DocInfo(
            path=path,
            pdf_version=pdf.pdf_version,
            encrypted=pdf.is_encrypted,
            pages=len(pdf.pages),
            file_size=path.stat().st_size,
            metadata=meta,
            has_forms="/AcroForm" in pdf.Root,
            has_outline="/Outlines" in pdf.Root,
        )

        fonts: set[str] = set()
        image_ids: set[tuple[int, int]] = set()
        for page in pdf.pages:
            box = [float(v) for v in page.mediabox]
            w, h = box[2] - box[0], box[3] - box[1]
            if int(page.obj.get("/Rotate", 0)) % 180 == 90:
                w, h = h, w
            info.page_sizes[size_name(w, h)] += 1

            res = page.obj.get("/Resources")
            if res is not None and "/Font" in res:
                for _, font in res.Font.items():
                    base = font.get("/BaseFont")
                    if base is not None:
                        # drop subset prefix like ABCDEF+Arial
                        name = str(base).lstrip("/")
                        fonts.add(name.split("+", 1)[-1])
            for img in page.get_images().values():
                image_ids.add(img.objgen)

        info.fonts = sorted(fonts)
        info.images = len(image_ids)
    return info


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n} B"
