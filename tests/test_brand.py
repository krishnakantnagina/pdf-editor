import asyncio
import hashlib
from datetime import date

import pikepdf
import pypdfium2 as pdfium
import pytest
from typer.testing import CliRunner

from pdfeditor.cli import app
from pdfeditor.core import brand, organize
from pdfeditor.core.pages import PageSpecError
from pdfeditor.verify import verify

from conftest import make_pdf, page_labels

runner = CliRunner()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def page_texts(path, password=None):
    doc = pdfium.PdfDocument(str(path), password=password)
    texts = []
    for i in range(len(doc)):
        page = doc[i]
        tp = page.get_textpage()
        texts.append(tp.get_text_range())
        tp.close()
        page.close()
    doc.close()
    return texts


def char_box(path, page_index, needle):
    """Bounding box (left, bottom, right, top) in page user space of `needle` on a page."""
    doc = pdfium.PdfDocument(str(path))
    page = doc[page_index]
    tp = page.get_textpage()
    text = tp.get_text_range()
    i = text.index(needle)
    boxes = [tp.get_charbox(j) for j in range(i, i + len(needle))]
    tp.close()
    page.close()
    doc.close()
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


@pytest.fixture
def png(tmp_path):
    from PIL import Image

    p = tmp_path / "logo.png"
    Image.new("RGBA", (40, 20), (200, 0, 0, 255)).save(p)
    return p


# ---------- watermark ----------

def test_text_watermark_selected_pages(pdf5):
    before = sha(pdf5)
    out = brand.watermark(pdf5, "SECRETMARK", pages="2,4")
    assert out.name == "five_watermarked.pdf"
    assert sha(pdf5) == before
    assert verify(out, expected_pages=5, expect_text=True).ok
    texts = page_texts(out)
    assert ["SECRETMARK" in t for t in texts] == [False, True, False, True, False]
    assert page_labels(out) == [f"Page {i}" for i in range(1, 6)]  # original content kept


def test_tiled_watermark_repeats(pdf3, tmp_path):
    out = brand.watermark(pdf3, "TILE", tile=True, out=tmp_path / "t.pdf")
    assert all(t.count("TILE") > 4 for t in page_texts(out))


@pytest.mark.parametrize("position", brand.WATERMARK_POSITIONS)
def test_watermark_positions_stay_on_page(pdf3, tmp_path, position):
    out = brand.watermark(pdf3, "POS", position=position, angle=0, font_size=30,
                          out=tmp_path / f"{position}.pdf")
    left, bottom, right, top = char_box(out, 0, "POS")
    assert 0 < left < right < 595.3 and 0 < bottom < top < 841.9
    if "left" in position:
        assert left < 100
    if "right" in position:
        assert right > 495
    if position.startswith("top"):
        assert top > 740
    if position.startswith("bottom"):
        assert bottom < 100


def test_image_watermark(pdf3, png):
    before = sha(pdf3)
    out = brand.watermark(pdf3, image=png, opacity=0.5, pages="1")
    assert sha(pdf3) == before
    assert verify(out, expected_pages=3, expect_text=True).ok

    def count_images(resources):
        n = 0
        for _, xobj in resources.get("/XObject", {}).items():
            if xobj.get("/Subtype") == "/Image":
                n += 1
            elif xobj.get("/Subtype") == "/Form":
                n += count_images(xobj.get("/Resources", {}))
        return n

    with pikepdf.open(out) as pdf:
        assert count_images(pdf.pages[0].resources) == 1
        assert count_images(pdf.pages[1].resources) == 0


@pytest.mark.parametrize("opacity", [0, -0.1, 1.5])
def test_opacity_validation(pdf3, opacity):
    with pytest.raises(ValueError, match="opacity"):
        brand.watermark(pdf3, "X", opacity=opacity)


def test_watermark_needs_text_or_image(pdf3, png):
    with pytest.raises(ValueError):
        brand.watermark(pdf3)
    with pytest.raises(ValueError):
        brand.watermark(pdf3, "X", image=png)


def test_watermark_bad_inputs(pdf3, tmp_path):
    with pytest.raises(ValueError, match="color"):
        brand.watermark(pdf3, "X", color="notacolor")
    with pytest.raises(ValueError, match="position"):
        brand.watermark(pdf3, "X", position="middle")
    with pytest.raises(ValueError, match="image"):
        brand.watermark(pdf3, image=tmp_path / "missing.png")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="image"):
        brand.watermark(pdf3, image=bad)
    with pytest.raises(PageSpecError):
        brand.watermark(pdf3, "X", pages="9")


def test_watermark_never_overwrites_input(pdf3):
    with pytest.raises(ValueError):
        brand.watermark(pdf3, "X", out=pdf3)


# ---------- page numbers ----------

def test_page_numbers_default(pdf5):
    before = sha(pdf5)
    out = brand.page_numbers(pdf5, fmt="PN{n}")
    assert sha(pdf5) == before
    assert verify(out, expected_pages=5, expect_text=True).ok
    texts = page_texts(out)
    for i, t in enumerate(texts, 1):
        assert f"PN{i}" in t
    # bottom-center by default
    left, bottom, right, top = char_box(out, 0, "PN1")
    assert bottom < 60 and 250 < (left + right) / 2 < 345


def test_page_numbers_total_start_and_pages(pdf5):
    out = brand.page_numbers(pdf5, fmt="Page {n} of {total}", pages="2-", start=1)
    texts = page_texts(out)
    assert "of 4" not in texts[0]
    for k, t in enumerate(texts[1:], 1):
        assert f"Page {k} of 4" in t
    out = brand.page_numbers(pdf5, fmt="[{n}/{total}]", start=10, out=pdf5.with_name("s.pdf"))
    assert "[10/14]" in page_texts(out)[0] and "[14/14]" in page_texts(out)[4]


@pytest.mark.parametrize("position", brand.NUMBER_POSITIONS)
def test_page_number_positions(pdf3, tmp_path, position):
    out = brand.page_numbers(pdf3, position=position, fmt="NUM{n}", out=tmp_path / f"{position}.pdf")
    left, bottom, right, top = char_box(out, 0, "NUM1")
    assert (bottom < 60) == position.startswith("bottom")
    assert (top > 780) == position.startswith("top")
    if position.endswith("left"):
        assert left < 60
    if position.endswith("right"):
        assert right > 535


@pytest.mark.parametrize("angle", [90, 180, 270])
def test_page_numbers_on_rotated_page(pdf3, tmp_path, angle):
    rotated = organize.rotate(pdf3, angle, "2", out=tmp_path / "rot.pdf")
    out = brand.page_numbers(rotated, fmt="PN{n}", out=tmp_path / "rot_n.pdf")
    texts = page_texts(out)
    assert all(f"PN{i}" in t for i, t in enumerate(texts, 1))
    # The number must sit at the bottom-center *as the reader sees it*.
    # Map the user-space box through the page rotation to reader coordinates.
    w, h = 595.2756, 841.8898
    left, bottom, right, top = char_box(out, 1, "PN2")
    cx, cy = (left + right) / 2, (bottom + top) / 2
    u, v = {90: (cy, w - cx), 180: (w - cx, h - cy), 270: (h - cy, cx)}[angle]
    reader_w = h if angle in (90, 270) else w
    assert v < 60  # near the bottom edge the reader sees
    assert abs(u - reader_w / 2) < 30  # centered horizontally
    # and drawn upright: the text runs along the reader's x axis
    if angle in (90, 270):
        assert (top - bottom) > (right - left)
    else:
        assert (right - left) > (top - bottom)


def test_page_numbers_with_offset_cropbox(tmp_path):
    src = make_pdf(tmp_path / "c.pdf", 2)
    with pikepdf.open(src) as pdf:
        for page in pdf.pages:
            page.obj.MediaBox = [100, 200, 695.2756, 1041.8898]
            page.obj.CropBox = [150, 250, 645.2756, 991.8898]
        pdf.save(tmp_path / "offset.pdf")
    out = brand.page_numbers(tmp_path / "offset.pdf", fmt="PN{n}", margin=20)
    left, bottom, right, top = char_box(out, 0, "PN1")
    # boxes are in user space: the visible area starts at (150, 250)
    assert 250 < bottom < 250 + 40
    assert abs((left + right) / 2 - (150 + 495.2756 / 2)) < 20


def test_page_numbers_validation(pdf3):
    with pytest.raises(ValueError, match="placeholder"):
        brand.page_numbers(pdf3, fmt="{page}")
    with pytest.raises(ValueError, match="position"):
        brand.page_numbers(pdf3, position="center")
    with pytest.raises(ValueError, match="font size"):
        brand.page_numbers(pdf3, font_size=0)


def test_encrypted_input(tmp_path):
    src = make_pdf(tmp_path / "plain.pdf", 2)
    with pikepdf.open(src) as pdf:
        pdf.save(tmp_path / "enc.pdf", encryption=pikepdf.Encryption(owner="o", user="pw"))
    out = brand.page_numbers(tmp_path / "enc.pdf", fmt="PN{n}", password="pw")
    # like the other operations, the output is saved without encryption
    res = verify(out, expected_pages=2, expect_text=True)
    assert res.ok, res.problems
    assert "PN2" in page_texts(out)[1]


# ---------- header / footer ----------

def test_header_footer_placeholders(pdf3):
    before = sha(pdf3)
    out = brand.header_footer(pdf3, header="HDR {filename} {date}", footer="FTR {n}/{total}")
    assert sha(pdf3) == before
    assert verify(out, expected_pages=3, expect_text=True).ok
    today = date.today().isoformat()
    for i, t in enumerate(page_texts(out), 1):
        assert f"HDR three.pdf {today}" in t
        assert f"FTR {i}/3" in t
    _, hb, _, _ = char_box(out, 0, "HDR")
    _, _, _, ft = char_box(out, 0, "FTR")
    assert hb > 780 and ft < 60


def test_header_only_on_selected_pages_right_aligned(pdf3):
    out = brand.header_footer(pdf3, header="ONLYHEAD", align="right", pages="odd")
    assert ["ONLYHEAD" in t for t in page_texts(out)] == [True, False, True]
    assert char_box(out, 0, "ONLYHEAD")[2] > 535


def test_header_footer_validation(pdf3):
    with pytest.raises(ValueError):
        brand.header_footer(pdf3)
    with pytest.raises(ValueError, match="align"):
        brand.header_footer(pdf3, header="x", align="justify")
    with pytest.raises(ValueError, match="placeholder"):
        brand.header_footer(pdf3, footer="{author}")


# ---------- CLI ----------

def test_cli_watermark(pdf5, png, tmp_path):
    out = tmp_path / "wm.pdf"
    r = runner.invoke(app, ["watermark", str(pdf5), "--text", "CLIMARK", "--pages", "1", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert "[OK] wm.pdf: 5 pages" in r.output
    assert "CLIMARK" in page_texts(out)[0] and "CLIMARK" not in page_texts(out)[1]
    r = runner.invoke(app, ["watermark", str(pdf5), "--image", str(png), "--tile"])
    assert r.exit_code == 0, r.output
    assert "[OK]" in r.output


def test_cli_watermark_errors(pdf5):
    r = runner.invoke(app, ["watermark", str(pdf5), "--text", "X", "--opacity", "2"])
    assert r.exit_code == 1 and "opacity" in r.output
    r = runner.invoke(app, ["watermark", str(pdf5)])
    assert r.exit_code == 1
    r = runner.invoke(app, ["watermark", str(pdf5), "--text", "X", "--pages", "99"])
    assert r.exit_code == 1 and "out of range" in r.output


def test_cli_page_numbers(pdf5):
    r = runner.invoke(app, ["page-numbers", str(pdf5), "--format", "Page {n} of {total}",
                            "--position", "top-right"])
    assert r.exit_code == 0, r.output
    assert "[OK]" in r.output
    out = pdf5.with_name("five_numbered.pdf")
    assert "Page 5 of 5" in page_texts(out)[4]


def test_cli_header_footer(pdf3):
    r = runner.invoke(app, ["header-footer", str(pdf3), "--header", "{filename}", "--footer", "{n}",
                            "--align", "left"])
    assert r.exit_code == 0, r.output
    assert "[OK]" in r.output
    r = runner.invoke(app, ["header-footer", str(pdf3)])
    assert r.exit_code == 1


# ---------- MCP ----------

@pytest.fixture
def mcp(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path))
    from pdfeditor import mcp_server
    from pdfeditor.mcp_tools import brand as tools
    return mcp_server, tools


def test_mcp_tools_registered(mcp):
    mcp_server, _ = mcp
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names >= {"pdf_add_watermark", "pdf_add_page_numbers", "pdf_add_header_footer"}


def test_mcp_watermark(mcp, pdf3, png, tmp_path):
    _, tools = mcp
    r = tools.pdf_add_watermark(str(pdf3), text="MCPMARK", output=str(tmp_path / "w.pdf"))
    assert r["verified"] and r["pages"] == 3
    assert "MCPMARK" in page_texts(r["output"])[2]
    r = tools.pdf_add_watermark(str(pdf3), image=str(png), pages="2")
    assert r["verified"]


def test_mcp_numbers_and_header_footer(mcp, pdf5):
    _, tools = mcp
    r = tools.pdf_add_page_numbers(str(pdf5), format="{n}/{total}", pages="2-")
    assert r["verified"] and "4/4" in page_texts(r["output"])[4]
    r = tools.pdf_add_header_footer(str(pdf5), footer="F{n}")
    assert r["verified"] and "F3" in page_texts(r["output"])[2]


def test_mcp_through_protocol_layer(mcp, pdf3):
    mcp_server, _ = mcp
    result = asyncio.run(mcp_server.server.call_tool("pdf_add_page_numbers", {"path": str(pdf3)}))
    assert "verified" in str(result)


def test_mcp_paths_outside_allowed_are_refused(mcp, pdf3, png, tmp_path, monkeypatch):
    _, tools = mcp
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path / "only_here"))
    with pytest.raises(PermissionError):
        tools.pdf_add_watermark(str(pdf3), text="X")
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(pdf3.parent / "docs"))
    (pdf3.parent / "docs").mkdir()
    inside = make_pdf(pdf3.parent / "docs" / "d.pdf", 1)
    with pytest.raises(PermissionError):  # image outside allowed folders
        tools.pdf_add_watermark(str(inside), image=str(png))
