# Contributing to PDF Editor

Thanks for helping. This project aims to be the best **free, offline, license-clean** PDF toolkit,
for people on the command line and for AI agents through MCP.

## Quick start

```bash
git clone https://github.com/krishnakantnagina/pdf-editor.git
cd pdf-editor
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
python scripts/check_licenses.py
```

## Find something to work on

- Issues labelled **`good first issue`** are small and well-defined.
- Issues labelled **`help wanted`** are bigger features from the roadmap in [PLAN.md](PLAN.md).
- If you have a new idea, open an issue first so we can agree on the approach.
- Comment on an issue to claim it, so nobody else works on it at the same time.

## The rules (CI checks all of them)

1. **Licenses: permissive only.** New dependencies must be MIT, BSD, Apache-2.0, ISC, MPL-2.0 or PSF.
   **No GPL, LGPL or AGPL**, which rules out PyMuPDF, Ghostscript, iText and pdf2docx.
   `scripts/check_licenses.py` fails CI if one slips in. Explain any new dependency in your PR.
2. **Never modify the input.** Every operation writes a new file (see `output_path()` in `pdfeditor/core/pages.py`).
3. **Verify every output.** CLI commands and MCP tools call `verify()` and report the result.
4. **Redaction must delete content.** Drawing a box over it is not redaction.
5. **Tests for every feature.** Use the `make_pdf()` helper in `tests/conftest.py` to build sample PDFs in code.
   Don't commit large binary PDFs.
6. **Offline only.** No network calls at runtime.

## How the code is organized

| Where | What |
|---|---|
| `pdfeditor/core/` | The library: one module per feature group. Pure functions: path in, path out. |
| `pdfeditor/verify.py` | Checks each output: it opens, renders, has the right page count, and kept its text |
| `pdfeditor/cli.py` | `pdfedit` command line (Typer). Thin wrapper around `core`. |
| `pdfeditor/mcp_server.py` | `pdfedit-mcp` MCP server. Thin wrapper around `core`. |
| `tests/` | pytest |

**Adding a feature** usually means: write a function in `core/`, add a test, then wire it into **both**
`cli.py` and `mcp_server.py` so people and AI agents get it at the same time.

## Pull requests

- Keep each PR focused on one feature or fix.
- `pytest -q` and `python scripts/check_licenses.py` must pass. CI runs them on Windows, macOS and Linux.
- Update `README.md` if you add a command or tool.
- By contributing, you agree your work is released under the [MIT License](LICENSE).

## Using Claude Code to contribute

This repo includes a `CLAUDE.md` and a `.mcp.json`, so Claude Code knows the project rules and can
call the PDF tools directly. Review AI-written code as carefully as your own, because you are responsible for what you submit.

## Code of conduct

Be kind and constructive. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
