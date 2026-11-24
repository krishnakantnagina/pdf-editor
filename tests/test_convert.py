import asyncio
import hashlib

import pikepdf
import pytest
from PIL import Image
from typer.testing import CliRunner

from pdfeditor.cli import app
from pdfeditor.core import convert, organize, view
from pdfeditor.core.pages import PageSpecError
from pdfeditor.verify import verify

from conftest import make_pdf

runner = CliRunner()


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def page_sizes_pt(path):
    with pikepdf.open(path) as pdf:
        return [(float(p.mediabox[2]) - float(p.mediabox[0]), float(p.mediabox[3]) - float(p.mediabox[1]))
                for p in pdf.pages]


def near(a, b, tol=1.0):
    return abs(a - b) <= tol


# ---------- to_images ----------

def test_to_images_names_and_dpi_math(pdf5):
    before = sha(pdf5)
    imgs = convert.to_images(pdf5, dpi=72)
    assert [p.name for p in imgs] == [f"five_p00{i}.png" for i in range(1, 6)]
    assert imgs[0].parent == pdf5.with_name("five_images")
    with Image.open(imgs[0]) as im:
        assert near(im.width, 595) and near(im.height, 842)
        assert im.format == "PNG"
    assert sha(pdf5) == before


def test_to_images_dpi_scales(pdf5, tmp_path):
    (img,) = convert.to_images(pdf5, tmp_path / "x", dpi=144, pages="1")
    with Image.open(img) as im:
        assert near(im.width, 1190, 2) and near(im.height, 1684, 2)


def test_to_images_jpg_and_page_spec(pdf5, tmp_path):
    imgs = convert.to_images(pdf5, tmp_path / "j", fmt="jpg", dpi=50, pages="2,4-5")
    assert [p.name for p in imgs] == ["five_p002.jpg", "five_p004.jpg", "five_p005.jpg"]
    with Image.open(imgs[0]) as im:
        assert im.format == "JPEG" and im.mode == "RGB"
    assert convert.to_images(pdf5, tmp_path / "j2", fmt="JPEG", dpi=50, pages="1")[0].suffix == ".jpg"


def test_to_images_padding_width(tmp_path):
    src = make_pdf(tmp_path / "many.pdf", 1001)
    imgs = convert.to_images(src, tmp_path / "m", dpi=36, pages="1,last")
    assert [p.name for p in imgs] == ["many_p0001.png", "many_p1001.png"]


def test_to_images_bad_input(pdf5):
    with pytest.raises(ValueError, match="dpi"):
        convert.to_images(pdf5, dpi=10)
    with pytest.raises(ValueError, match="dpi"):
        convert.to_images(pdf5, dpi=5000)
    with pytest.raises(ValueError, match="format"):
        convert.to_images(pdf5, fmt="gif")
    with pytest.raises(PageSpecError):
        convert.to_images(pdf5, pages="9")


def test_rotated_page_renders_landscape(pdf5, tmp_path):
    rotated = organize.rotate(pdf5, 90, pages="1")
    imgs = convert.to_images(rotated, tmp_path / "r", dpi=36, pages="1-2")
    with Image.open(imgs[0]) as a, Image.open(imgs[1]) as b:
        assert a.width > a.height
        assert b.height > b.width


def test_to_images_encrypted(pdf5, tmp_path):
    locked = tmp_path / "locked.pdf"
    with pikepdf.open(pdf5) as pdf:
        pdf.save(locked, encryption=pikepdf.Encryption(owner="o", user="secret"))
    with pytest.raises(Exception):
        convert.to_images(locked, tmp_path / "no", dpi=36)
    assert len(convert.to_images(locked, tmp_path / "yes", dpi=36, password="secret")) == 5
    assert "Page 3" in convert.to_text(locked, pages="3", password="secret")


# ---------- from_images ----------

def test_round_trip(pdf5, tmp_path):
    imgs = convert.to_images(pdf5, tmp_path / "imgs", dpi=72)
    out = convert.from_images([tmp_path / "imgs"], tmp_path / "back.pdf")
    assert verify(out, expected_pages=5).ok
    for w, h in page_sizes_pt(out):  # PNG dpi is stored, so pages come back A4-sized
        assert near(w, 595.3) and near(h, 841.9)
    assert len(imgs) == 5


def test_fit_uses_image_dpi(tmp_path):
    Image.new("RGB", (300, 150), "red").save(tmp_path / "a.png", dpi=(150, 150))
    Image.new("RGB", (100, 50), "blue").save(tmp_path / "b.webp")  # no dpi stored -> 72
    out = convert.from_images([tmp_path / "a.png", tmp_path / "b.webp"], tmp_path / "o.pdf", margin_mm=10)
    (w1, h1), (w2, h2) = page_sizes_pt(out)
    m = 10 * 72 / 25.4
    assert near(w1, 144 + 2 * m) and near(h1, 72 + 2 * m)
    assert near(w2, 100 + 2 * m) and near(h2, 50 + 2 * m)


def test_a4_fitting_orientation_and_margins(tmp_path):
    Image.new("RGB", (2000, 1000), "red").save(tmp_path / "wide.png")
    Image.new("RGB", (100, 400), "blue").save(tmp_path / "tall.png")
    out = convert.from_images([tmp_path / "wide.png", tmp_path / "tall.png"], tmp_path / "a4.pdf",
                              page_size="A4", margin_mm=20)
    (w1, h1), (w2, h2) = page_sizes_pt(out)
    assert near(w1, 841.9) and near(h1, 595.3)  # landscape for the wide image
    assert near(w2, 595.3) and near(h2, 841.9)  # portrait for the tall one
    # The wide image is limited by width: it fills the box between the 20 mm margins.
    img = convert.to_images(out, tmp_path / "chk", dpi=72, pages="1")[0]
    with Image.open(img) as im:
        rgb = im.convert("RGB")
        m = round(20 * 72 / 25.4)
        assert rgb.getpixel((m + 3, im.height // 2))[0] > 200  # red just inside margin
        assert rgb.getpixel((m - 5, im.height // 2)) == (255, 255, 255)  # white margin
        assert rgb.getpixel((im.width // 2, 10)) == (255, 255, 255)  # centred vertically


def test_letter_size(tmp_path):
    Image.new("RGB", (50, 60), "green").save(tmp_path / "s.png")
    out = convert.from_images([tmp_path / "s.png"], tmp_path / "l.pdf", page_size="Letter")
    (w, h), = page_sizes_pt(out)
    assert near(w, 612) and near(h, 792)


def test_exif_rotated_jpeg(tmp_path):
    img = Image.new("RGB", (200, 100), "red")
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90 CW to display": stored 200x100, shown 100x200
    img.save(tmp_path / "cam.jpg", exif=exif.tobytes())
    out = convert.from_images([tmp_path / "cam.jpg"], tmp_path / "e.pdf")
    (w, h), = page_sizes_pt(out)
    assert near(w, 100) and near(h, 200)


def test_rgba_palette_cmyk_and_greyscale(tmp_path):
    rgba = Image.new("RGBA", (40, 40), (255, 0, 0, 0))
    rgba.save(tmp_path / "1.png")
    Image.new("P", (40, 40)).save(tmp_path / "2.png", transparency=0)
    Image.new("CMYK", (40, 40), (0, 255, 255, 0)).save(tmp_path / "3.jpg")
    Image.new("L", (40, 40), 128).save(tmp_path / "4.tif")
    Image.new("I;16", (40, 40)).save(tmp_path / "5.png")
    Image.new("RGB", (40, 40), "blue").save(tmp_path / "6.webp")
    out = convert.from_images([tmp_path], tmp_path / "modes.pdf")
    assert verify(out, expected_pages=6).ok
    img = convert.to_images(out, tmp_path / "chk", dpi=72, pages="1")[0]
    with Image.open(img) as im:  # fully transparent pixels flattened onto white
        assert im.convert("RGB").getpixel((20, 20)) == (255, 255, 255)


def test_multi_frame_tiff(tmp_path):
    frames = [Image.new("RGB", (30, 30), c) for c in ("red", "green", "blue")]
    frames[0].save(tmp_path / "multi.tiff", save_all=True, append_images=frames[1:])
    assert convert.count_pages([tmp_path / "multi.tiff"]) == 3
    out = convert.from_images([tmp_path / "multi.tiff"], tmp_path / "t.pdf")
    assert verify(out, expected_pages=3).ok


def test_folder_natural_sort_and_skips_other_files(tmp_path):
    folder = tmp_path / "pics"
    folder.mkdir()
    for n, size in ((10, 30), (2, 20), (1, 10)):
        Image.new("RGB", (size, size), "red").save(folder / f"img{n}.png")
    (folder / "notes.txt").write_text("x")
    assert [p.name for p in convert.collect_images([folder])] == ["img1.png", "img2.png", "img10.png"]
    out = convert.from_images([folder], tmp_path / "f.pdf")
    assert [round(w) for w, _ in page_sizes_pt(out)] == [10, 20, 30]


def test_explicit_files_keep_order(tmp_path):
    for n, size in ((1, 10), (2, 20)):
        Image.new("RGB", (size, size)).save(tmp_path / f"{n}.png")
    out = convert.from_images([tmp_path / "2.png", tmp_path / "1.png"], tmp_path / "o.pdf")
    assert [round(w) for w, _ in page_sizes_pt(out)] == [20, 10]


def test_from_images_errors(tmp_path):
    src = tmp_path / "a.png"
    Image.new("RGB", (10, 10)).save(src)
    with pytest.raises(ValueError, match="never overwritten"):
        convert.from_images([src], src)
    with pytest.raises(ValueError, match="page_size"):
        convert.from_images([src], tmp_path / "o.pdf", page_size="A3")
    with pytest.raises(ValueError, match="margins"):
        convert.from_images([src], tmp_path / "o.pdf", page_size="A4", margin_mm=200)
    with pytest.raises(FileNotFoundError):
        convert.from_images([tmp_path / "missing.png"], tmp_path / "o.pdf")
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no images"):
        convert.from_images([empty], tmp_path / "o.pdf")
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    with pytest.raises(ValueError, match="cannot read image"):
        convert.from_images([bad], tmp_path / "o.pdf")


# ---------- to_text ----------

def test_to_text_markers(pdf5):
    text = convert.to_text(pdf5)
    assert text.count("--- Page ") == 5
    assert "--- Page 3 ---\nPage 3\n" in text
    assert "Line 30 of sample text on page 5." in text
    assert "\r" not in text


def test_to_text_pages_and_no_markers(pdf5):
    text = convert.to_text(pdf5, pages="4,2", page_breaks=False)
    assert "--- Page" not in text
    assert text.index("Page 4") < text.index("Page 2")
    assert "Page 1" not in text


def test_to_text_writes_file(pdf5, tmp_path):
    out = tmp_path / "t.txt"
    text = convert.to_text(pdf5, pages="3", out=out)
    assert out.read_text(encoding="utf-8") == text
    with pytest.raises(ValueError):
        convert.to_text(pdf5, out=pdf5)


# ---------- CLI ----------

def test_cli_to_images(pdf5, tmp_path):
    r = runner.invoke(app, ["to-images", str(pdf5), "--dpi", "40", "-f", "jpg", "--pages", "1-2",
                            "-d", str(tmp_path / "c")])
    assert r.exit_code == 0, r.output
    assert "2 images" in r.output
    assert sorted(p.name for p in (tmp_path / "c").iterdir()) == ["five_p001.jpg", "five_p002.jpg"]


def test_cli_to_images_errors(pdf5, tmp_path):
    assert runner.invoke(app, ["to-images", str(pdf5), "--dpi", "5"]).exit_code == 1
    assert runner.invoke(app, ["to-images", str(tmp_path / "nope.pdf")]).exit_code == 1


def test_cli_from_images(pdf3, tmp_path):
    convert.to_images(pdf3, tmp_path / "i", dpi=40)
    out = tmp_path / "joined.pdf"
    r = runner.invoke(app, ["from-images", str(tmp_path / "i"), "-o", str(out), "-s", "A4", "-m", "5"])
    assert r.exit_code == 0, r.output
    assert "[OK]" in r.output
    assert view.get_info(out).pages == 3


def test_cli_to_text(pdf5, tmp_path):
    r = runner.invoke(app, ["to-text", str(pdf5), "--pages", "2"])
    assert r.exit_code == 0
    assert "--- Page 2 ---" in r.output and "Page 2" in r.output
    out = tmp_path / "x.txt"
    r = runner.invoke(app, ["to-text", str(pdf5), "--no-markers", "-o", str(out)])
    assert r.exit_code == 0 and str(out) in r.output
    assert "--- Page" not in out.read_text(encoding="utf-8")


# ---------- MCP ----------

@pytest.fixture
def mcp(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path))
    from pdfeditor import mcp_server
    from pdfeditor.mcp_tools import convert as tools
    return mcp_server, tools


def test_mcp_tools_registered(mcp):
    mcp_server, _ = mcp
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names >= {"pdf_to_images", "pdf_from_images", "pdf_extract_text"}


def test_mcp_round_trip(mcp, pdf5, tmp_path):
    _, tools = mcp
    r = tools.pdf_to_images(str(pdf5), str(tmp_path / "m"), dpi=40, pages="1-3")
    assert r["count"] == 3 and r["verified"] and len(r["images"]) == 3
    rep = tools.pdf_from_images([str(tmp_path / "m")], str(tmp_path / "m.pdf"), page_size="Letter")
    assert rep["verified"] and rep["pages"] == 3


def test_mcp_extract_text_truncates(mcp, pdf5):
    _, tools = mcp
    full = tools.pdf_extract_text(str(pdf5))
    assert not full["truncated"] and "--- Page 5 ---" in full["text"]
    short = tools.pdf_extract_text(str(pdf5), pages="1", max_chars=20)
    assert short["truncated"] and len(short["text"]) == 20 and short["chars"] > 20


def test_mcp_paths_outside_refused(mcp, pdf5, tmp_path, monkeypatch):
    _, tools = mcp
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path / "only_here"))
    with pytest.raises(PermissionError):
        tools.pdf_extract_text(str(pdf5))
    with pytest.raises(PermissionError):
        tools.pdf_from_images([str(tmp_path)], str(tmp_path / "x.pdf"))


def test_mcp_through_protocol_layer(mcp, pdf5):
    mcp_server, _ = mcp
    result = asyncio.run(mcp_server.server.call_tool("pdf_extract_text", {"path": str(pdf5), "pages": "3"}))
    assert "Page 3" in str(result)


def test_from_images_embeds_jpeg_without_reencoding(tmp_path):
    import random

    import pikepdf
    from PIL import Image

    from pdfeditor.core import convert

    rng = random.Random(1)
    img = Image.new("RGB", (800, 600))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(800 * 600)])
    jpg = tmp_path / "photo.jpg"
    img.save(jpg, quality=80)

    out = convert.from_images([jpg], tmp_path / "photo.pdf")
    with pikepdf.open(out) as pdf:
        (xobj,) = pdf.pages[0].get_images().values()
        assert xobj.Filter == "/DCTDecode" or list(xobj.Filter) == ["/DCTDecode"]
        assert xobj.read_raw_bytes() == jpg.read_bytes()
    # PDF overhead only: not a lossless re-encode that is several times bigger
    assert out.stat().st_size < jpg.stat().st_size * 1.05 + 4096
