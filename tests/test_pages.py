import pytest

from pdfeditor.core.pages import PageSpecError, output_path, parse_pages


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("3", [2]),
        ("1-3", [0, 1, 2]),
        ("4-", [3, 4]),
        ("-2", [0, 1]),
        ("last", [4]),
        ("odd", [0, 2, 4]),
        ("even", [1, 3]),
        ("reverse", [4, 3, 2, 1, 0]),
        ("all", [0, 1, 2, 3, 4]),
        ("1-2, 5", [0, 1, 4]),
        ("3-1", [2, 1, 0]),
    ],
)
def test_parse_pages(spec, expected):
    assert parse_pages(spec, 5) == expected


@pytest.mark.parametrize("spec", ["0", "6", "abc", "", "1-9"])
def test_parse_pages_errors(spec):
    with pytest.raises(PageSpecError):
        parse_pages(spec, 5)


def test_output_path_never_overwrites(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(b"x")
    first = output_path(src, "rotated")
    assert first.name == "a_rotated.pdf"
    first.write_bytes(b"x")
    assert output_path(src, "rotated").name == "a_rotated_2.pdf"
    with pytest.raises(ValueError):
        output_path(src, "rotated", out=src)
