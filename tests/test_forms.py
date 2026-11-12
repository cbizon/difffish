import pytest
from pydantic import ValidationError

from difffish import documents
from difffish.forms import FORM_TYPE_MAP, NcsmSheet, StarnesCard, build_document_model


def test_document_model_has_one_field_per_page():
    model = build_document_model({"page_1": "ncsm_sheet", "page_2": "starnes_card"})
    record = model()
    assert isinstance(record.page_1, NcsmSheet)
    assert isinstance(record.page_2, StarnesCard)
    assert record.transcription_notes == ""


def test_unknown_form_type_fails():
    with pytest.raises(KeyError):
        build_document_model({"page_1": "no_such_form"})


def test_form_type_cannot_be_rewritten_by_a_reader():
    with pytest.raises(ValidationError):
        NcsmSheet(form_type="North Carolina State Museum sheet")


def test_every_classified_form_type_has_a_model():
    used = {t for doc_id in documents.document_ids() for t in documents.page_types(doc_id).values()}
    assert used <= set(FORM_TYPE_MAP)
