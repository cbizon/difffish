import base64
import re

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


def test_human_locality_and_coordinates_are_separate_fields():
    record = documents.human_record("WCS-0005")
    assert record["verbatimLocality"].endswith("ca 16 air mi E Madisonville")
    assert record["verbatimLatitude"] == "35.5373°N"
    assert record["verbatimLongitude"] == "84.1046°W"


def test_start_and_end_coordinates_are_joined_with_a_slash():
    record = documents.human_record("WCS-3011")
    assert record["verbatimLatitude"] == "39.37134 N / 38.36654 N"
    assert record["verbatimLongitude"] == "77.33578 W / 77.32188 W"


def test_a_document_without_coordinates_has_no_coordinate_fields():
    record = documents.human_record("WCS-0021")
    assert record["verbatimLocality"] == "MA, Worchester County, Jordan Pond"
    assert "verbatimLatitude" not in record and "verbatimLongitude" not in record


def test_no_locality_still_ends_in_coordinates():
    ends_in_coordinate = re.compile(r"\d\.\d{3,}\s*°?\s*[NSEW]?\s*$|\d\"\s*[NSEW]\s*$")
    for doc_id in documents.document_ids():
        record = documents.human_record(doc_id)
        assert not ends_in_coordinate.search(record["verbatimLocality"]), doc_id
        assert ("verbatimLatitude" in record) == ("verbatimLongitude" in record), doc_id


def test_human_record_drops_fields_the_curator_left_empty():
    record = documents.human_record("WCS-0005")
    assert record["state"] == "Tennessee"
    assert "permits" not in record
