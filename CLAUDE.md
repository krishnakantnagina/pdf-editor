# CLAUDE.md

Instructions for Claude Code (and other AI agents) working in this repo.

## Project
Offline PDF toolkit: a Python library (`pdfeditor/core`), a CLI (`pdfedit`) and an MCP server (`pdfedit-mcp`).
The roadmap is in PLAN.md. Contributor rules are in CONTRIBUTING.md.

## Commands
- Install: `pip install -e ".[dev]"` (in a virtual env)
- Test: `pytest -q`
- License check: `python scripts/check_licenses.py`

## Hard rules
- **Never add GPL, LGPL or AGPL dependencies.** That means no PyMuPDF/fitz, Ghostscript, iText or pdf2docx.
  Allowed: MIT, BSD, Apache-2.0, ISC, MPL-2.0, PSF. Run the license check after adding any dependency.
- Core functions never modify their input. Use `output_path()` and return the new path.
- Every CLI command and MCP tool verifies its output with `verify()`.
- New features go in `core/` first. Then add a CLI command in `pdfeditor/commands/<group>.py` and an MCP tool in
  `pdfeditor/mcp_tools/<group>.py` (each registers on the shared `app` / `server`; list new modules in the imports at
  the bottom of `cli.py` / `mcp_server.py`), with tests.
- Encrypted inputs: outputs keep the same encryption (`organize._save` saves with `encryption=pdf.is_encrypted`).
  Edit pages inside the opened source; don't copy them into `pikepdf.new()`, which would drop the protection.
- MCP tools must pass every path through `safe_path()`.
- Build test PDFs in code with `tests/conftest.py::make_pdf`. Don't commit binary fixtures.
- Library choices: pikepdf for structure, pypdfium2 for rendering and text, reportlab for drawing overlays, pypdf for forms and annotations.
