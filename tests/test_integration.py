"""Runs the real graph against the model endpoint. Costs money; off by default."""

import os

import pytest

from difffish.graph import RunContext, build_document_graph
from difffish.schemas import MAJORITY, RECONCILED

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("DIFFFISH_INTEGRATION") != "1", reason="set DIFFFISH_INTEGRATION=1 to call the endpoint"),
]


def test_one_document_end_to_end():
    result = build_document_graph().invoke({"doc_id": "WCS-0005"}, context=RunContext())["result"]
    assert len(result.readers) >= 3
    candidates = [card.candidate for card in result.scorecards]
    assert candidates[-2:] == [MAJORITY, RECONCILED]
    assert all({s.field for s in card.scores} >= {"state", "county"} for card in result.scorecards)
