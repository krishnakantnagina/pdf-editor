import hashlib

import pikepdf
import pytest

from pdfeditor.core import organize, view
from pdfeditor.core.pages import PageSpecError
from pdfeditor.verify import verify

from conftest import make_pdf, page_labels


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_info(pdf5):
    i = view.get_info(pdf5)
    assert i.pages == 5
    assert i.page_sizes == {"A4 portrait": 5}
    assert "Helvetica" in i.fonts
    assert i.metadata["Title"] == "Sample Page"
    assert not i.encrypted


def test_merge(pdf5, pdf3, tmp_path):
    out = organize.merge([pdf5, pdf3], tmp_path / "merged.pdf")
    assert verify(out, expected_pages=8, expect_text=True).ok
    assert page_labels(out) == [f"Page {i}" for i in range(1, 6)] + [f"Doc {i}" for i in range(1, 4)]
    assert view.get_info(out).metadata["Title"] == "Sample Page"


def test_merge_refuses_overwriting_input(pdf5, pdf3):
    with pytest.raises(ValueError):
        organize.merge([pdf5, pdf3], pdf5)


def test_extract(pdf5):
    before = sha(pdf5)
    out = organize.extract(pdf5, "4,1")
    assert out.name == "five_extract.pdf"
    assert page_labels(out) == ["Page 4", "Page 1"]
    assert sha(pdf5) == before  # original untouched


def test_delete(pdf5):
    out = organize.delete(pdf5, "2,4-5")
    assert page_labels(out) == ["Page 1", "Page 3"]


def test_delete_all_refused(pdf5):
    with pytest.raises(PageSpecError):
        organize.delete(pdf5, "all")


def test_reorder(pdf5):
    out = organize.reorder(pdf5, "3,1,2,4-")
    assert page_labels(out) == ["Page 3", "Page 1", "Page 2", "Page 4", "Page 5"]


def test_reorder_reverse(pdf5):
    out = organize.reorder(pdf5, "reverse")
    assert page_labels(out) == [f"Page {i}" for i in range(5, 0, -1)]


def test_reorder_must_be_complete(pdf5):
    with pytest.raises(PageSpecError, match="missing pages 4,5"):
        organize.reorder(pdf5, "3,1,2")
    out = organize.reorder(pdf5, "1,1,2", allow_partial=True)
    assert page_labels(out) == ["Page 1", "Page 1", "Page 2"]


def test_rotate(pdf5):
    out = organize.rotate(pdf5, 90, pages="even")
    with pikepdf.open(out) as pdf:
        rot = [int(p.obj.get("/Rotate", 0)) for p in pdf.pages]
    assert rot == [0, 90, 0, 90, 0]
    out2 = organize.rotate(out, -90, pages="2")
    with pikepdf.open(out2) as pdf:
        assert int(pdf.pages[1].obj.get("/Rotate", 0)) % 360 == 0
    assert view.get_info(out).page_sizes == {"A4 portrait": 3, "A4 landscape": 2}


def test_rotate_bad_angle(pdf5):
    with pytest.raises(ValueError):
        organize.rotate(pdf5, 45)


def test_split_every(pdf5):
    parts = organize.split(pdf5, every=2)
    assert [len(page_labels(p)) for p in parts] == [2, 2, 1]
    assert parts[0].name == "five_part1.pdf"


def test_split_ranges(pdf5, tmp_path):
    parts = organize.split(pdf5, tmp_path / "out", ranges="1-2,5,3-")
    assert [page_labels(p) for p in parts] == [
        ["Page 1", "Page 2"], ["Page 5"], ["Page 3", "Page 4", "Page 5"]
    ]


def test_split_max_size(tmp_path):
    src = make_pdf(tmp_path / "big.pdf", 20)
    limit_mb = src.stat().st_size / 3 / (1024 * 1024)
    parts = organize.split(src, max_mb=limit_mb)
    assert len(parts) >= 2  # parts are saved compressed, so fewer than size/limit
    assert sum(len(page_labels(p)) for p in parts) == 20
    for p in parts:
        assert p.stat().st_size <= limit_mb * 1024 * 1024


def test_split_needs_one_mode(pdf5):
    with pytest.raises(ValueError):
        organize.split(pdf5)
    with pytest.raises(ValueError):
        organize.split(pdf5, every=2, ranges="1")


def test_encrypted_input(pdf5, tmp_path):
    locked = tmp_path / "locked.pdf"
    with pikepdf.open(pdf5) as pdf:
        pdf.save(locked, encryption=pikepdf.Encryption(owner="o", user="secret"))
    with pytest.raises(pikepdf.PasswordError):
        view.get_info(locked)
    assert view.get_info(locked, password="secret").encrypted
    out = organize.extract(locked, "1-2", password="secret")
    assert page_labels(out) == ["Page 1", "Page 2"]


def test_verify_catches_problems(pdf5, tmp_path):
    assert not verify(pdf5, expected_pages=4).ok
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert not verify(bad).ok
