# PDF Editor: Plan

A PDF toolkit that runs entirely on your own machine. It needs no internet, sends no files anywhere, and uses only free tools with no license problems.

Created: 2026-11-24 · Updated: 2026-11-24

---

## 1. Decisions

| Decision | Choice |
|---|---|
| Where it runs | **On your machine (hybrid).** Python does all processing natively. The browser on `127.0.0.1` is only the interface. |
| Why not browser-only | WASM in the browser is about 1.5 to 3 times slower, mostly uses one core, and has a 2 to 4 GB memory cap. Native code uses all cores and all RAM. |
| Licenses | **Permissive or weak-copyleft only** (MIT, BSD, Apache-2.0, MPL-2.0). **No AGPL or GPL.** That rules out PyMuPDF, Ghostscript, iText, pdf2docx and MuPDF. |
| OCR language | English only (`eng`) |
| Digital signatures | Not included |

## 2. Tech stack (all free)

| Job | Library | License |
|---|---|---|
| Rendering, text extraction, page thumbnails (Google's PDFium engine) | **pypdfium2** | Apache-2.0 / BSD-3 |
| Structure editing: merge, split, rotate, encrypt, repair, compress, remove objects | **pikepdf** (built on qpdf) | MPL-2.0 (qpdf: Apache-2.0) |
| Simple page operations, form filling, metadata | **pypdf** | BSD-3 |
| Drawing new content (text, watermarks, page numbers, shapes, images) as an overlay layer | **reportlab** | BSD |
| Accurate text and table extraction | **pdfplumber** (pdfminer.six) | MIT |
| OCR engine | **Tesseract** + pytesseract | Apache-2.0 |
| Images | **Pillow** | MIT-CMU (permissive) |
| Office → PDF | **LibreOffice** (headless, run as a separate program) | MPL-2.0 |
| PDF → DOCX | **python-docx**, built from pdfplumber's text and layout | MIT |
| HTML → PDF | **Playwright** (Chromium) | Apache-2.0 |
| CLI | **Typer** | MIT |
| Local server | **FastAPI** + Uvicorn | MIT / BSD |
| MCP server for Claude Code and other AI agents | **mcp** (official Python SDK) | MIT |
| Viewer in the browser | **pdf.js** | Apache-2.0 |
| Watch folder | **watchdog** | Apache-2.0 |

MPL-2.0 is safe here. It only asks you to share changes you make *to that library's own files*, never your app.

### How editing works without PyMuPDF
- **Adding content** (text, watermark, page numbers, stamps, images): reportlab draws an overlay page, and pikepdf/pypdf merges it onto the original page.
- **Removing content** (watermarks, ads, phone numbers): pikepdf parses each page's content stream, deletes the matching text or image operators, and writes the page back. Text stays real text.
- **True redaction:** delete the operators inside the area (as above). For pages where that can't be done cleanly, use **safe fallback** mode: render the page with pypdfium2, paint the box, put the page back as an image, then OCR it with Tesseract so it's searchable again.

## 3. Every feature, by category

Priority: **P1** = build first, **P2** = next, **P3** = nice to have.

### A. Viewing and reading
| Feature | Priority | Library |
|---|---|---|
| Render pages, zoom, page thumbnails | P1 | pypdfium2 / pdf.js |
| Show metadata, page count, fonts, images, PDF version | P1 | pikepdf |
| Full-text search with highlighted results | P2 | pypdfium2 / pdf.js |
| Outline and bookmark navigation | P2 | pypdf |

### B. Page organization
| Feature | Priority | Library |
|---|---|---|
| Merge several PDFs | P1 | pikepdf |
| Split by range, every N pages, bookmark or file size | P1 | pikepdf |
| Extract, delete, reorder and rotate pages | P1 | pikepdf |
| Insert blank pages or pages from another PDF, duplicate pages | P2 | pikepdf |
| Crop and change margins (CropBox/MediaBox), resize to A4 or Letter | P2 | pikepdf |
| N-up (2 or 4 per sheet), booklet imposition | P3 | pypdf |
| Reverse order, interleave odd/even scans | P3 | pikepdf |

### C. Content editing
| Feature | Priority | Library |
|---|---|---|
| Add text boxes | P1 | reportlab overlay |
| Add, replace, delete and extract images | P2 | pikepdf + Pillow |
| Add shapes, lines and freehand ink | P2 | reportlab overlay |
| Find and replace text (simple fonts) | P3 | pikepdf content stream |
| Add links (URL or internal page) | P3 | pypdf |

### D. Cleaning
| Feature | Priority | Library |
|---|---|---|
| Remove text watermarks | P1 | pikepdf content stream |
| Remove phone numbers, URLs and ads with regex plus redaction | P1 | pdfplumber (find) + pikepdf (delete) |
| Remove a repeated logo or image wherever it appears | P1 | pikepdf + Pillow (image hash) |
| Remove headers and footers by area | P2 | pikepdf content stream |
| Remove blank pages | P2 | pypdfium2 (pixel check) |
| Remove annotations, JavaScript, embedded files and metadata | P2 | pikepdf |
| Flatten forms and annotations | P2 | pypdf |

### E. Annotation and review
| Feature | Priority | Library |
|---|---|---|
| Highlight, underline and strike through text | P2 | pypdf annotations |
| Sticky notes and comments | P2 | pypdf |
| Stamps (APPROVED, DRAFT, custom image) | P3 | reportlab overlay |

### F. Branding and marking
| Feature | Priority | Library |
|---|---|---|
| Text or image watermark (opacity, angle, tiling) | P1 | reportlab overlay |
| Page numbers with position and format options | P1 | reportlab overlay |
| Headers and footers (for example a www.paperwala.org footer) | P1 | reportlab overlay |
| Add a cover page | P2 | reportlab + pikepdf |
| Bates numbering | P3 | reportlab overlay |

### G. Conversion
| Feature | Priority | Library |
|---|---|---|
| PDF → PNG/JPG (chosen DPI) | P1 | pypdfium2 |
| Images → PDF | P1 | Pillow / reportlab |
| PDF → plain text or Markdown | P1 | pypdfium2 / pdfplumber |
| PDF tables → CSV or Excel | P2 | pdfplumber + openpyxl (MIT) |
| DOCX, XLSX or PPTX → PDF | P2 | LibreOffice headless |
| HTML or Markdown → PDF | P2 | Playwright |
| PDF → DOCX (text and layout, basic) | P3 | pdfplumber + python-docx |

### H. OCR (English)
| Feature | Priority | Library |
|---|---|---|
| Make scanned PDFs searchable | P1 | Tesseract (`eng`). Render with pypdfium2, OCR to a PDF text layer, merge with pikepdf |
| Detect which pages are scanned and which are text | P2 | pypdfium2 |
| Auto-rotate and straighten (deskew) scans | P2 | Tesseract OSD + Pillow |

### I. Optimization and repair
| Feature | Priority | Library |
|---|---|---|
| Compress (recompress and downsample images, remove duplicate objects, object streams) | P1 | pikepdf + Pillow |
| Repair broken or corrupt PDFs | P2 | pikepdf (qpdf) |
| Linearize for fast loading on the web | P3 | pikepdf |
| Convert to grayscale | P3 | pikepdf + Pillow |

### J. Security
| Feature | Priority | Library |
|---|---|---|
| Add a password (AES-256) | P1 | pikepdf |
| Remove a password (when you know it) | P1 | pikepdf |
| True redaction (content deleted, not covered) | P1 | pikepdf, or the safe fallback in section 2 |
| Set permissions (block printing, copying or editing) | P2 | pikepdf |
| Strip metadata and hidden data | P2 | pikepdf |

### K. Forms
| Feature | Priority | Library |
|---|---|---|
| Read form fields | P2 | pypdf |
| Fill forms from JSON or CSV (mail merge) | P2 | pypdf |
| Flatten filled forms | P2 | pypdf |
| Create form fields | P3 | reportlab |

### L. Comparison and analysis
| Feature | Priority | Library |
|---|---|---|
| Compare the text of two PDFs (diff) | P3 | pdfplumber + difflib |
| Compare two PDFs visually (pixel diff) | P3 | pypdfium2 + Pillow |
| Word count and page statistics | P3 | pdfplumber |

### M. Batch and automation
| Feature | Priority | Library |
|---|---|---|
| Run any operation on a whole folder, using all CPU cores | P1 | Python multiprocessing |
| Saved "recipes" that chain steps (clean → watermark → compress) | P2 | YAML (PyYAML, MIT) |
| Watch folder: process new PDFs automatically | P3 | watchdog |

## 4. Folder structure

```
PDF Editor/
├── PLAN.md
├── README.md
├── pyproject.toml
├── pdfeditor/
│   ├── core/            # one module per category (A–M)
│   │   ├── view.py
│   │   ├── organize.py
│   │   ├── edit.py
│   │   ├── overlay.py   # reportlab drawing + merge (shared by C, E, F)
│   │   ├── contentstream.py  # pikepdf operator parsing (shared by C, D, J)
│   │   ├── clean.py
│   │   ├── annotate.py
│   │   ├── brand.py
│   │   ├── convert.py
│   │   ├── ocr.py
│   │   ├── optimize.py
│   │   ├── security.py
│   │   ├── forms.py
│   │   └── compare.py
│   ├── verify.py        # checks every output
│   ├── cli.py           # Typer commands
│   ├── mcp_server.py    # MCP tools (every feature is exposed to AI agents too)
│   └── web/             # FastAPI app + pdf.js front end
├── recipes/
├── samples/
└── tests/
```

## 5. Build phases

| Phase | What gets built | Done when |
|---|---|---|
| **1. Core + CLI** ✅ done | Set up the project. P1 features from A, B, F, G, I and J, plus `verify.py` | `pdfedit merge/split/rotate/compress/protect/watermark/page-numbers/to-images` all work on the sample files |
| **2. Cleaning + OCR** | Section D, the content-stream engine, redaction, English OCR | A sample paper comes out with ads, watermarks and phone numbers removed and the text searchable |
| **3. Local web UI** | FastAPI + pdf.js: thumbnails, drag-and-drop pages, a toolbar with every P1 tool | Every P1 job can be done in the browser at `127.0.0.1:8000` |
| **4. Editing, annotation, forms** | Sections C, E and K | Can add text, images and highlights and fill a form, then save |
| **5. Conversion + batch** | Office and HTML conversion, recipes, parallel folder processing | One command processes a whole folder with a recipe |
| **6. P3 extras** | Compare, N-up, PDF→DOCX, watch folder | Built as needed |

## 6. Software to install on Windows

```powershell
pip install pypdfium2 pikepdf pypdf reportlab pdfplumber pytesseract pillow openpyxl python-docx typer fastapi uvicorn pyyaml watchdog
winget install UB-Mannheim.TesseractOCR            # English data is included
winget install TheDocumentFoundation.LibreOffice   # only for Office → PDF (phase 5)
pip install playwright; playwright install chromium   # only for HTML → PDF (phase 5)
```

## 7. Rules for every operation

1. Input files are read-only. Outputs go to `<name>_<operation>.pdf`, or to a chosen output folder.
2. Run `verify.py` on every output: it opens, has the expected page count, and its text is still there (or truly gone, for redaction).
3. Redaction must delete the content. Covering it with a black box doesn't count.
4. Each feature has a test that uses a small sample PDF.
5. Before adding any new dependency, check its license. Only MIT, BSD, Apache-2.0, MPL-2.0 or ISC are allowed.
