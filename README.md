# PDF Editor

**A free, offline, license-clean PDF toolkit for people and AI agents.**

[![CI](https://github.com/krishnakantnagina/pdf-editor/actions/workflows/ci.yml/badge.svg)](https://github.com/krishnakantnagina/pdf-editor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Contributions welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)

- **Offline.** Your PDFs never leave your machine. No accounts, uploads or telemetry.
- **License-clean.** Only MIT, BSD, Apache-2.0 and MPL-2.0 dependencies. CI blocks GPL and AGPL, so you can use it anywhere, including commercially.
- **Fast.** Uses native engines: Google's PDFium for rendering and qpdf for structure.
- **Safe.** Never modifies your original. Every output is checked: it opens, renders, has the right page count, and kept its text.
- **Built for AI agents.** A built-in **MCP server** lets Claude Code (and any MCP client) edit PDFs for you.

## Install

```bash
git clone https://github.com/krishnakantnagina/pdf-editor.git
cd pdf-editor
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[mcp]"
```

Requires Python 3.11+. Tested on Windows, macOS and Linux.

## Command line

| Command | Example |
|---|---|
| `info` | `pdfedit info file.pdf` (a folder works too) |
| `merge` | `pdfedit merge a.pdf b.pdf -o combined.pdf` (or a folder) |
| `split` | `pdfedit split file.pdf --every 10` · `--ranges "1-3,4-"` · `--max-mb 5` |
| `extract` | `pdfedit extract file.pdf "1-3,7"` |
| `delete` | `pdfedit delete file.pdf "2,5-7"` |
| `reorder` | `pdfedit reorder file.pdf "3,1,2,4-"` · `reverse` |
| `rotate` | `pdfedit rotate file.pdf 90 --pages even` |

```text
$ pdfedit merge report.pdf appendix.pdf -o full.pdf
Merged 2 files -> full.pdf
[OK] full.pdf: 8 pages, 6115 text chars
```

**Page specs:** `3`, `1-3`, `5-` (to the end), `-3` (start to page 3), `last`, `odd`, `even`, `reverse`, `all`, or combinations separated by commas.
**Encrypted PDFs:** add `-p PASSWORD`. **Output:** saved as `<name>_<operation>.pdf` by default (never overwrites a file), or choose a path with `-o`.

## Use it from Claude Code (MCP)

```bash
claude mcp add pdf-editor -- /full/path/to/.venv/bin/pdfedit-mcp
# Windows: claude mcp add pdf-editor -- C:\path\to\.venv\Scripts\pdfedit-mcp.exe
```

Then just ask:

> *"Merge every PDF in ~/Downloads/invoices into one file, then delete the blank last page."*
> *"Split thesis.pdf into chapters at pages 1-12, 13-40, 41-."*

| MCP tool | What it does |
|---|---|
| `pdf_info` | Pages, sizes, fonts, images, metadata, encryption |
| `pdf_verify` | Check a PDF opens, renders and has the expected pages |
| `pdf_merge` | Merge files in order |
| `pdf_split` | Split by ranges, every N pages, or max size |
| `pdf_extract_pages` | Copy selected pages to a new file |
| `pdf_delete_pages` | Copy without selected pages |
| `pdf_reorder_pages` | New page order |
| `pdf_rotate_pages` | Rotate selected pages |

**Security:** the MCP server can only touch files inside allowed folders. The default is your home folder and the folder it was started in.
To restrict it further, set `PDFEDIT_ALLOWED_DIRS` (separated by `;` on Windows, `:` elsewhere):

```bash
claude mcp add pdf-editor -e PDFEDIT_ALLOWED_DIRS=/home/me/pdfs -- pdfedit-mcp
```

It works with any MCP client (Claude Desktop, Cursor and others): run `pdfedit-mcp` over stdio.

## Roadmap

✅ **Phase 1a:** info, merge, split, extract, delete, reorder, rotate, output checks, MCP server
⬜ **Phase 1b:** watermark, page numbers, headers and footers, PDF↔images, text extraction, compression, passwords
⬜ **Phase 2:** remove watermarks and ads, true redaction, English OCR
⬜ **Phase 3:** local web UI (drag-and-drop pages, previews)
⬜ **Phase 4:** add text and images, annotations, forms
⬜ **Phase 5:** Office/HTML → PDF, batch recipes
⬜ **Phase 6:** compare PDFs, N-up, watch folders

The full plan, with about 70 features, is in [PLAN.md](PLAN.md).

## Contributing

Contributions are very welcome. Pick a [`good first issue`](https://github.com/krishnakantnagina/pdf-editor/labels/good%20first%20issue)
and read [CONTRIBUTING.md](CONTRIBUTING.md). Every new feature goes into both the CLI and the MCP server.

```bash
pip install -e ".[dev]"
pytest -q
python scripts/check_licenses.py
```

## License

[MIT](LICENSE). All runtime dependencies are permissively licensed (checked in CI).
