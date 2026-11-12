import base64

import pymupdf
import pytest

from difffish import documents


@pytest.fixture
def pdf(tmp_path):
    path = tmp_path / "WCS-9999.pdf"
    with pymupdf.open() as doc:
        for text in ("page one", "page two"):
            doc.new_page().insert_text((72, 72), text)
        doc.save(path)
    return path


def test_render_pages_returns_one_jpeg_per_page(pdf):
    pages = documents.render_pages(pdf, dpi=50)
    assert len(pages) == 2
    assert all(base64.b64decode(p).startswith(b"\xff\xd8") for p in pages)


def test_page_count(pdf):
    assert documents.page_count(pdf) == 2


def test_pdf_path_finds_the_document(pdf, tmp_path):
    assert documents.pdf_path("WCS-9999", tmp_path) == pdf


def test_pdf_path_finds_a_scan_named_with_a_second_field_number(tmp_path):
    scan = tmp_path / "WCS-1948, REJ-1510.pdf"
    scan.touch()
    (tmp_path / "WCS-19481.pdf").touch()
    assert documents.pdf_path("WCS-1948", tmp_path) == scan


def test_pdf_path_fails_for_a_missing_document(tmp_path):
    with pytest.raises(FileNotFoundError):
        documents.pdf_path("WCS-0000", tmp_path)


def test_every_document_has_page_types_and_a_human_record():
    ids = documents.document_ids()
    assert len(ids) == 239
    for doc_id in ids:
        assert documents.page_types(doc_id)
        assert documents.human_record(doc_id)


def test_human_record_drops_fields_the_curator_left_empty():
    record = documents.human_record("WCS-0005")
    assert record["state"] == "Tennessee"
    assert "permits" not in record
