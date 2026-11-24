import asyncio

import pytest

pytest.importorskip("mcp")

from pdfeditor import mcp_server  # noqa: E402

from conftest import page_labels  # noqa: E402


@pytest.fixture(autouse=True)
def allow_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path))


def call(name, **args):
    return asyncio.run(mcp_server.server.call_tool(name, args))


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(mcp_server.server.list_tools())}
    assert names == {
        "pdf_info", "pdf_verify", "pdf_merge", "pdf_split", "pdf_extract_pages",
        "pdf_delete_pages", "pdf_reorder_pages", "pdf_rotate_pages",
    }


def test_info_tool(pdf5):
    assert mcp_server.pdf_info(str(pdf5))["pages"] == 5


def test_merge_tool(pdf5, pdf3, tmp_path):
    r = mcp_server.pdf_merge([str(pdf5), str(pdf3)], str(tmp_path / "m.pdf"))
    assert r["verified"] and r["pages"] == 8


def test_extract_and_reorder_tools(pdf5):
    r = mcp_server.pdf_extract_pages(str(pdf5), "5,1")
    assert page_labels(r["output"]) == ["Page 5", "Page 1"]
    r = mcp_server.pdf_reorder_pages(str(pdf5), "reverse")
    assert r["verified"]


def test_split_tool(pdf5):
    r = mcp_server.pdf_split(str(pdf5), every=2)
    assert r["count"] == 3 and r["all_verified"]


def test_path_outside_allowed_is_refused(pdf5, tmp_path, monkeypatch):
    monkeypatch.setenv("PDFEDIT_ALLOWED_DIRS", str(tmp_path / "only_here"))
    with pytest.raises(PermissionError):
        mcp_server.pdf_info(str(pdf5))


def test_call_through_protocol_layer(pdf5):
    result = call("pdf_info", path=str(pdf5))
    assert "5" in str(result)
