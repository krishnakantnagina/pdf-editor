from typer.testing import CliRunner

from pdfeditor.cli import app

from conftest import page_labels

runner = CliRunner()


def test_cli_info(pdf5):
    r = runner.invoke(app, ["info", str(pdf5)])
    assert r.exit_code == 0, r.output
    assert "Pages:       5" in r.output
    assert "A4 portrait x5" in r.output


def test_cli_info_folder(pdf5, pdf3):
    r = runner.invoke(app, ["info", str(pdf5.parent)])
    assert r.exit_code == 0
    assert "five.pdf" in r.output and "three.pdf" in r.output


def test_cli_merge_and_verify(pdf5, pdf3, tmp_path):
    out = tmp_path / "m.pdf"
    r = runner.invoke(app, ["merge", str(pdf5), str(pdf3), "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert "[OK] m.pdf: 8 pages" in r.output


def test_cli_extract_delete_reorder_rotate(pdf5):
    for args in (["extract", str(pdf5), "1-2"], ["delete", str(pdf5), "1"],
                 ["reorder", str(pdf5), "reverse"], ["rotate", str(pdf5), "180"]):
        r = runner.invoke(app, args)
        assert r.exit_code == 0, r.output
        assert "[OK]" in r.output
    assert page_labels(pdf5.with_name("five_reorder.pdf"))[0] == "Page 5"


def test_cli_split(pdf5):
    r = runner.invoke(app, ["split", str(pdf5), "--every", "2"])
    assert r.exit_code == 0, r.output
    assert "Split into 3 files" in r.output


def test_cli_bad_pages_gives_clean_error(pdf5):
    r = runner.invoke(app, ["extract", str(pdf5), "9"])
    assert r.exit_code == 1
    assert "out of range" in r.output
