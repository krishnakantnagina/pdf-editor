"""Generate sample PDFs into samples/ for trying the CLI:  python scripts/make_samples.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from conftest import make_pdf  # noqa: E402

out = Path(__file__).resolve().parent.parent / "samples"
out.mkdir(exist_ok=True)
make_pdf(out / "sample5.pdf", 5)
make_pdf(out / "sample3.pdf", 3, "Doc")
print(f"Wrote sample PDFs to {out}")
