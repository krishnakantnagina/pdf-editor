"""Fail if any installed dependency of pdfeditor uses a copyleft license we don't allow.

Allowed: MIT, BSD, Apache-2.0, ISC, MPL-2.0, PSF, Unlicense, Zlib, CMU (and similar permissive).
Blocked: GPL, LGPL, AGPL, SSPL, EUPL, CC-BY-NC, "Commons Clause".

Run in CI after `pip install -e ".[dev]"`:  python scripts/check_licenses.py
"""

from __future__ import annotations

import re
import sys
from importlib.metadata import PackageNotFoundError, distribution

BLOCKED = re.compile(r"\b(A?GPL|LGPL|GNU (Affero |Lesser )?General Public|SSPL|EUPL|Commons Clause|NonCommercial|CC-BY-NC)", re.I)

# Packages whose metadata is ambiguous but whose license we checked by hand.
# Format: name -> reason. Keep this list short and justified.
REVIEWED: dict[str, str] = {}


def license_text(dist) -> str:
    md = dist.metadata
    parts = [md.get("License-Expression") or "", md.get("License") or ""]
    parts += [c for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
    # Some packages put the full license text in "License"; only look at the first line.
    return " | ".join(p.splitlines()[0] for p in parts if p)


def requirements(name: str, seen: set[str]) -> None:
    key = name.lower().replace("_", "-")
    if key in seen:
        return
    try:
        dist = distribution(name)
    except PackageNotFoundError:
        return
    seen.add(key)
    for req in dist.requires or []:
        if "extra ==" in req and "extra == \"mcp\"" not in req and "extra == \"dev\"" not in req:
            continue
        dep = re.split(r"[ ;<>=!~\[(]", req, maxsplit=1)[0]
        requirements(dep, seen)


def main() -> int:
    seen: set[str] = set()
    requirements("pdfeditor", seen)
    seen.discard("pdfeditor")
    bad = []
    for name in sorted(seen):
        dist = distribution(name)
        lic = license_text(dist)
        flag = bool(BLOCKED.search(lic)) and name not in REVIEWED
        print(f"{'BLOCKED' if flag else 'ok':8} {name:28} {lic or '(no license metadata)'}")
        if flag:
            bad.append(name)
    if bad:
        print(f"\nCopyleft licenses are not allowed: {', '.join(bad)}", file=sys.stderr)
        return 1
    print(f"\nAll {len(seen)} dependencies use allowed licenses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
