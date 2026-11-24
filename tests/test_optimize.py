import asyncio
import hashlib
from pathlib import Path

import pikepdf
import pytest
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from typer.testing import CliRunner

from pdfeditor.cli import app
from pdfeditor.core import optimize, security
from pdfeditor.verify import verify

from conftest import page_labels

runner = CliRunner()
SECRET = "S3cret-user-pw!"
OWNER = "Owner-pw-77#"


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def photo(n: int = 1200) -> Image.Image:
    """Photo-like RGB image: gradients plus noise (compresses badly as Flate)."""
    g = Image.linear_gradient("L").resize((n, n))
    rgb = Image.merge("RGB", (g, g.rotate(90), g.transpose(Image.FLIP_LEFT_RIGHT)))
    return Image.blend(rgb, Image.effect_noise((n, n), 40).convert("RGB"), 0.3)


def make_image_pdf(path: Path, pages: int = 2) -> Path:
    img = ImageReader(photo())
    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(1, pages + 1):
        c.setFont("Helvetica", 24)
        c.drawString(72, 780, f"Photo {i}")
        c.drawImage(img, 72, 250, width=400, height=400)  # 1200 px over 400 pt = 216 dpi
        c.showPage()
    c.save()
    return path


@pytest.fixture(scope="module")
def image_pdf_master(tmp_path_factory) -> Path:
    return make_image_pdf(tmp_path_factory.mktemp("img") / "photos.pdf")


@pytest.fixture
def image_pdf(image_pdf_master, tmp_path) -> Path:
    p = tmp_path / "photos.pdf"
    p.write_bytes(image_pdf_master.read_bytes())
    return p


@pytest.fixture
def locked(pdf5, tmp_path) -> Path:
    return security.protect(pdf5, SECRET, OWNER, allow_copy=False, out=tmp_path / "locked.pdf")


def image_sizes(path: Path, password: str | None = None) -> list[tuple[int, int]]:
    with pikepdf.open(path, password=password or "") as pdf:
        return [(int(i.Width), int(i.Height)) for i in pdf.pages[0].get_images().values()]


# ---------- compress ----------

@pytest.mark.parametrize("level, max_ratio, max_px", [("medium", 0.2, 840), ("high", 0.1, 560)])
def test_compress_images_shrinks(image_pdf, level, max_ratio, max_px):
    before = sha(image_pdf)
    r = optimize.compress(image_pdf, level)
    assert r.output.name == "photos_compressed.pdf"
    assert r.size_before == image_pdf.stat().st_size
    assert r.size_after == r.output.stat().st_size
    assert r.size_after < r.size_before * max_ratio
    assert r.images_recompressed == 1  # the same image is used on both pages
    assert verify(r.output, expected_pages=2, expect_text=True).ok
    assert page_labels(r.output) == ["Photo 1", "Photo 2"]
    w, h = image_sizes(r.output)[0]
    assert w <= max_px and h <= max_px  # downsampled to the dpi cap
    assert sha(image_pdf) == before  # original untouched


def test_compress_high_smaller_than_medium(image_pdf, tmp_path):
    med = optimize.compress(image_pdf, "medium", tmp_path / "m.pdf")
    high = optimize.compress(image_pdf, "high", tmp_path / "h.pdf")
    assert high.size_after < med.size_after


def test_compress_low_is_lossless_and_not_larger(image_pdf):
    r = optimize.compress(image_pdf, "low")
    assert r.size_after <= r.size_before
    assert r.images_recompressed == 0
    assert image_sizes(r.output) == [(1200, 1200)]
    assert verify(r.output, expected_pages=2, expect_text=True).ok


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_text_only_pdf_never_grows(pdf5, level):
    r = optimize.compress(pdf5, level)
    assert r.size_after <= r.size_before
    assert page_labels(r.output) == [f"Page {i}" for i in range(1, 6)]


def test_already_small_pdf_gives_unchanged_copy(tmp_path):
    src = tmp_path / "tiny.pdf"
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        pdf.save(src, object_stream_mode=pikepdf.ObjectStreamMode.generate, compress_streams=True)
    r = optimize.compress(src, "high")
    assert r.size_after <= r.size_before
    assert verify(r.output, expected_pages=1).ok


def test_compress_dedupes_identical_images(tmp_path):
    src = tmp_path / "dupes.pdf"
    raw = photo(300).tobytes()
    with pikepdf.new() as pdf:
        for _ in range(3):
            pdf.add_blank_page()
            img = pikepdf.Stream(pdf, raw, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                                 Width=300, Height=300, ColorSpace=pikepdf.Name.DeviceRGB,
                                 BitsPerComponent=8)
            page = pdf.pages[-1]
            page.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img))
            page.Contents = pdf.make_stream(b"q 200 0 0 200 50 50 cm /Im0 Do Q")
        pdf.save(src)
    r = optimize.compress(src, "low")
    with pikepdf.open(r.output) as pdf:
        ids = {p.Resources.XObject.Im0.objgen for p in pdf.pages}
    assert len(ids) == 1
    assert r.size_after < r.size_before / 2


def test_compress_skips_cmyk_and_masks(tmp_path):
    src = tmp_path / "skip.pdf"
    n = 400
    cmyk = photo(n).convert("CMYK").tobytes()
    with pikepdf.new() as pdf:
        pdf.add_blank_page()
        img = pikepdf.Stream(pdf, cmyk, Type=pikepdf.Name.XObject, Subtype=pikepdf.Name.Image,
                             Width=n, Height=n, ColorSpace=pikepdf.Name.DeviceCMYK, BitsPerComponent=8)
        pdf.pages[0].Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=img))
        pdf.pages[0].Contents = pdf.make_stream(b"q 100 0 0 100 0 0 cm /Im0 Do Q")
        pdf.save(src)
    r = optimize.compress(src, "high")
    with pikepdf.open(r.output) as pdf:
        im = pdf.pages[0].Resources.XObject.Im0
        assert im.ColorSpace == pikepdf.Name.DeviceCMYK and int(im.Width) == n
        assert im.get("/Filter") != pikepdf.Name.DCTDecode
    assert r.images_recompressed == 0


def test_compress_encrypted_input_stays_encrypted(locked, tmp_path):
    with pytest.raises(pikepdf.PasswordError):
        optimize.compress(locked, "medium")
    r = optimize.compress(locked, "medium", tmp_path / "c.pdf", password=SECRET)
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(r.output)
    assert verify(r.output, expected_pages=5, expect_text=True, password=SECRET).ok


def test_compress_bad_level(pdf5):
    with pytest.raises(ValueError):
        optimize.compress(pdf5, "extreme")


def test_compress_refuses_overwriting_input(pdf5):
    with pytest.raises(ValueError):
        optimize.compress(pdf5, "low", out=pdf5)


# ---------- protect / unlock ----------

def test_protect(pdf5, tmp_path):
    before = sha(pdf5)
    out = security.protect(pdf5, SECRET, OWNER, allow_print=False, allow_copy=False)
    assert out.name == "five_protected.pdf"
    assert sha(pdf5) == before
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(out)
    with pikepdf.open(out, password=SECRET) as pdf:
        assert pdf.is_encrypted
        assert pdf.encryption.R == 6 and pdf.encryption.bits == 256
        assert "aesv3" in str(pdf.encryption.stream_method)
        assert not pdf.allow.print_highres and not pdf.allow.print_lowres
        assert not pdf.allow.extract
        assert pdf.allow.modify_other and pdf.allow.modify_annotation and pdf.allow.accessibility
        assert len(pdf.pages) == 5
        assert not pdf.owner_password_matched
    with pikepdf.open(out, password=OWNER) as pdf:
        assert pdf.owner_password_matched
    assert verify(out, expected_pages=5, expect_text=True, password=SECRET).ok


def test_protect_no_modify_no_annotate(pdf5):
    out = security.protect(pdf5, SECRET, allow_modify=False, allow_annotate=False)
    with pikepdf.open(out, password=SECRET) as pdf:
        a = pdf.allow
        assert not a.modify_other and not a.modify_assembly
        assert not a.modify_annotation and not a.modify_form
        assert a.print_highres and a.extract


def test_protect_default_owner_is_random_and_not_user(pdf5):
    out = security.protect(pdf5, SECRET)
    with pikepdf.open(out, password=SECRET) as pdf:
        assert not pdf.owner_password_matched  # owner is a different, random secret
    with pytest.raises(pikepdf.PasswordError):
        pikepdf.open(out, password="")


def test_protect_permissions_only_lock(pdf5):
    with pytest.raises(ValueError):
        security.protect(pdf5, "")  # empty user password needs an owner password
    out = security.protect(pdf5, "", OWNER, allow_copy=False)
    with pikepdf.open(out) as pdf:  # opens without a password
        assert pdf.is_encrypted and not pdf.allow.extract
    assert security.is_encrypted(out)
    with pytest.raises(security.PermissionDeniedError):
        security.unlock(out, "")
    assert not security.is_encrypted(security.unlock(out, OWNER))


@pytest.mark.parametrize("user, owner", [(SECRET, ""), (SECRET, SECRET)])
def test_protect_rejects_bad_owner(pdf5, user, owner):
    with pytest.raises(ValueError) as e:
        security.protect(pdf5, user, owner)
    assert SECRET not in str(e.value)


def test_unlock(locked, tmp_path):
    before = sha(locked)
    out = security.unlock(locked, OWNER)
    assert out.name == "locked_unlocked.pdf"
    with pikepdf.open(out) as pdf:
        assert not pdf.is_encrypted
    assert page_labels(out) == [f"Page {i}" for i in range(1, 6)]
    assert sha(locked) == before


def test_unlock_with_user_password_when_unrestricted(pdf5):
    out = security.protect(pdf5, SECRET)  # all permissions allowed
    assert not security.is_encrypted(security.unlock(out, SECRET))


def test_unlock_restricted_needs_owner(locked):
    with pytest.raises(security.PermissionDeniedError) as e:
        security.unlock(locked, SECRET)
    assert SECRET not in str(e.value)


def test_unlock_wrong_password(locked):
    with pytest.raises(security.WrongPasswordError) as e:
        security.unlock(locked, "nope-wrong")
    assert "wrong password" in str(e.value) and "nope-wrong" not in str(e.value)


def test_unlock_not_encrypted(pdf5):
    with pytest.raises(ValueError, match="not encrypted"):
        security.unlock(pdf5, "x")


def test_protect_encrypted_input(locked, tmp_path):
    out = security.protect(locked, "new-pw", out=tmp_path / "re.pdf", password=OWNER)
    with pikepdf.open(out, password="new-pw") as pdf:
        assert pdf.encryption.R == 6
    with pytest.raises(security.WrongPasswordError):
        security.protect(locked, "x", password="bad")
    with pytest.raises(security.PermissionDeniedError):  # user pw cannot strip owner's limits
        security.protect(locked, "x", password=SECRET)


# ---------- CLI ----------

def test_cli_compress(image_pdf, tmp_path):
    out = tmp_path / "c.pdf"
    r = runner.invoke(app, ["compress", str(image_pdf), "--level", "high", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert "smaller" in r.output and "->" in r.output
    assert "[OK] c.pdf: 2 pages" in r.output


def test_cli_compress_no_gain(pdf5, tmp_path):
    r = runner.invoke(app, ["compress", str(pdf5), "-l", "low", "-o", str(tmp_path / "c.pdf")])
    assert r.exit_code == 0, r.output
    assert "[OK] c.pdf: 5 pages" in r.output


def test_cli_compress_bad_level(pdf5):
    assert runner.invoke(app, ["compress", str(pdf5), "-l", "max"]).exit_code != 0


def test_cli_compress_encrypted(locked, tmp_path):
    r = runner.invoke(app, ["compress", str(locked), "-o", str(tmp_path / "c.pdf")])
    assert r.exit_code == 1 and "needs a password" in r.output
    r = runner.invoke(app, ["compress", str(locked), "-p", SECRET, "-o", str(tmp_path / "c.pdf")])
    assert r.exit_code == 0, r.output
    assert SECRET not in r.output


def test_cli_protect_and_unlock_with_options(pdf5, tmp_path):
    out = tmp_path / "p.pdf"
    r = runner.invoke(app, ["protect", str(pdf5), "-u", SECRET, "--owner-password", OWNER,
                            "--no-print", "--no-copy", "--no-modify", "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert "[OK] p.pdf: 5 pages" in r.output
    assert SECRET not in r.output and OWNER not in r.output
    with pikepdf.open(out, password=SECRET) as pdf:
        assert not pdf.allow.print_highres and not pdf.allow.extract and not pdf.allow.modify_other
        assert pdf.allow.modify_annotation

    r = runner.invoke(app, ["unlock", str(out), "-p", OWNER, "-o", str(tmp_path / "u.pdf")])
    assert r.exit_code == 0, r.output
    assert "[OK] u.pdf: 5 pages" in r.output and OWNER not in r.output
    assert not security.is_encrypted(tmp_path / "u.pdf")


def test_cli_protect_prompts_for_password(pdf5, tmp_path):
    out = tmp_path / "p.pdf"
    r = runner.invoke(app, ["protect", str(pdf5), "-o", str(out)], input=f"{SECRET}\n{SECRET}\n")
    assert r.exit_code == 0, r.output
    assert SECRET not in r.output  # hidden input is not echoed
    with pikepdf.open(out, password=SECRET) as pdf:
        assert pdf.is_encrypted


def test_cli_unlock_prompt_and_wrong_password(locked, tmp_path):
    r = runner.invoke(app, ["unlock", str(locked), "-o", str(tmp_path / "u.pdf")], input="bad-guess\n")
    assert r.exit_code == 1
    assert "wrong password" in r.output and "bad-guess" not in r.output
    r = runner.invoke(app, ["unlock", str(locked), "-o", str(tmp_path / "u.pdf")], input=f"{OWNER}\n")
    assert r.exit_code == 0, r.output
    assert OWNER not in r.output


def test_cli_unlock_restricted_with_user_password(locked):
    r = runner.invoke(app, ["unlock", str(locked), "-p", SECRET])
    assert r.exit_code == 1 and "owner password" in r.output
    assert SECRET not in r.output


# ---------- MCP ----------

mcp = pytest.importorskip("mcp")


@pytest.fixture
def mcp_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path))
    from pdfeditor import mcp_server
    from pdfeditor.mcp_tools import optimize as tools
    return mcp_server, tools


def test_mcp_tools_registered(mcp_tools):
    mcp_server, _ = mcp_tools
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert {"pdf_compress", "pdf_protect", "pdf_unlock"} <= names


def test_mcp_compress(mcp_tools, image_pdf):
    _, tools = mcp_tools
    r = tools.pdf_compress(str(image_pdf), level="medium")
    assert r["verified"] and r["pages"] == 2
    assert r["size_after"] < r["size_before"] and r["saved_percent"] > 50


def test_mcp_protect_unlock_hides_passwords(mcp_tools, pdf5, tmp_path):
    mcp_server, tools = mcp_tools
    r = tools.pdf_protect(str(pdf5), SECRET, OWNER, allow_copy=False, output=str(tmp_path / "p.pdf"))
    assert r["verified"] and r["pages"] == 5 and r["permissions"]["copy"] is False
    assert SECRET not in str(r) and OWNER not in str(r)
    r2 = tools.pdf_unlock(r["output"], OWNER)
    assert r2["verified"] and OWNER not in str(r2)
    assert not security.is_encrypted(Path(r2["output"]))
    # through the protocol layer too
    res = asyncio.run(mcp_server.server.call_tool(
        "pdf_protect", {"path": str(pdf5), "user_password": SECRET, "output": str(tmp_path / "q.pdf")}))
    assert "AES-256" in str(res) and SECRET not in str(res)


def test_mcp_paths_outside_allowed_refused(mcp_tools, pdf5, tmp_path, monkeypatch):
    _, tools = mcp_tools
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path / "only_here"))
    with pytest.raises(PermissionError):
        tools.pdf_compress(str(pdf5))
    with pytest.raises(PermissionError):
        tools.pdf_protect(str(pdf5), SECRET)


def test_mcp_wrong_password(mcp_tools, locked):
    _, tools = mcp_tools
    with pytest.raises(Exception) as e:
        tools.pdf_unlock(str(locked), "bad-guess")
    assert "bad-guess" not in str(e.value)
