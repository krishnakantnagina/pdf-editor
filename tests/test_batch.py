import pikepdf
from typer.testing import CliRunner

from pdfeditor.cli import app

from conftest import make_pdf, page_labels

runner = CliRunner()


def folder_of_pdfs(tmp_path, n=3):
    d = tmp_path / "in"
    d.mkdir()
    for i in range(1, n + 1):
        make_pdf(d / f"doc{i}.pdf", 3, label=f"D{i}")
    return d


def test_batch_rotate_next_to_inputs(tmp_path):
    d = folder_of_pdfs(tmp_path)
    r = runner.invoke(app, ["batch", str(d), "rotate", "90", "--pages", "2"])
    assert r.exit_code == 0, r.output
    assert "3/3 succeeded" in r.output
    for i in range(1, 4):
        with pikepdf.open(d / f"doc{i}_rotated.pdf") as pdf:
            assert [int(p.obj.get("/Rotate", 0)) for p in pdf.pages] == [0, 90, 0]


def test_batch_out_dir_and_jobs(tmp_path):
    d = folder_of_pdfs(tmp_path)
    out = tmp_path / "out"
    r = runner.invoke(app, ["batch", "--out-dir", str(out), "-j", "2", str(d), "extract", "1"])
    assert r.exit_code == 0, r.output
    assert sorted(p.name for p in out.iterdir()) == ["doc1.pdf", "doc2.pdf", "doc3.pdf"]
    assert page_labels(out / "doc2.pdf") == ["D2 1"]


def test_batch_dir_output_commands(tmp_path):
    d = folder_of_pdfs(tmp_path, 2)
    out = tmp_path / "imgs"
    r = runner.invoke(app, ["batch", "-O", str(out), str(d), "to-images", "--dpi", "40"])
    assert r.exit_code == 0, r.output
    assert len(list((out / "doc1").glob("*.png"))) == 3


def test_batch_reports_failures_but_continues(tmp_path):
    d = folder_of_pdfs(tmp_path, 2)
    (d / "broken.pdf").write_bytes(b"not a pdf")
    r = runner.invoke(app, ["batch", str(d), "rotate", "90"])
    assert r.exit_code == 2
    assert "FAIL broken.pdf" in r.output and "2/3 succeeded" in r.output


def test_batch_refusals(tmp_path):
    d = folder_of_pdfs(tmp_path, 1)
    assert "can't be run per file" in runner.invoke(app, ["batch", str(d), "merge"]).output
    assert "unknown command" in runner.invoke(app, ["batch", str(d), "nope"]).output
    r = runner.invoke(app, ["batch", str(d), "rotate", "90", "-o", "x.pdf"])
    assert r.exit_code == 1 and "--out-dir" in r.output
