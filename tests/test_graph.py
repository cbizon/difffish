import pytest
from langgraph.types import Send

from difffish import graph, prompts
from difffish.diff import diff_readings
from pydantic import ValidationError

from difffish.schemas import MAJORITY, RECONCILED, Reconciliation, Transcription, reconciliation_schema


def reading(reader, model, **content):
    return Transcription(reader=reader, model=model, content=content, notes=f"{reader} found the date smudged")


def transcriptions():
    return [
        reading("Reader A", "model-a", county="Monroe", date="3 Apr 1969"),
        reading("Reader B", "model-b", county="Monroe", date="8 Apr 1969"),
        reading("Reader C", "model-c", county="Monroe", date="3 Apr 1969"),
        Transcription(reader="Reader D", model="model-d", error="NotFoundError: decommissioned"),
    ]


def test_graph_shape():
    edges = {(e.source, e.target) for e in graph.build_document_graph().get_graph().edges}
    assert edges == {
        ("__start__", "prepare"),
        ("prepare", "transcribe"),
        ("transcribe", "diff"),
        ("diff", "reconcile"),
        ("reconcile", "score"),
        ("score", "compare"),
        ("compare", "__end__"),
    }


@pytest.mark.parametrize("node", ["diff", "reconcile"])
def test_adjudication_cannot_see_the_document_or_the_human_record(node):
    visible = set(graph.build_document_graph().builder.nodes[node].input_schema.__annotations__)
    assert visible == {"transcriptions", "diffs"}


def test_page_images_are_not_part_of_graph_state():
    assert not {"pages", "images"} & set(graph.DocState.__annotations__)


def test_assign_readers_sends_one_anonymous_task_per_model():
    state = {"pdf_path": "x.pdf", "page_types": {"page_1": "freeform"}, "reader_models": ["model-a", "model-b"]}
    sends = graph.assign_readers(state)
    assert all(isinstance(s, Send) and s.node == "transcribe" for s in sends)
    assert [(s.arg["reader"], s.arg["model"]) for s in sends] == [("Reader A", "model-a"), ("Reader B", "model-b")]


def test_diff_ignores_failed_readers(settings):
    diffs = {d.path: d for d in graph.diff({"transcriptions": transcriptions()})["diffs"]}
    assert set(diffs["date"].readings) == {"Reader A", "Reader B", "Reader C"}


def test_diff_fails_below_the_quorum(settings):
    with pytest.raises(RuntimeError, match="only 2 of 3 readers succeeded.*decommissioned"):
        graph.diff({"transcriptions": transcriptions()[1:]})


def test_reconcile_makes_no_model_call_when_readers_agree():
    agreed = [reading(r, "m", county="Monroe") for r in ("Reader A", "Reader B", "Reader C")]
    diffs = diff_readings({t.reader: t.content for t in agreed})
    out = graph.reconcile({"transcriptions": agreed, "diffs": diffs})
    assert out["reconciliation"] == Reconciliation(decisions=[])
    assert out["reconciled"] == {"county": "Monroe"}


def ruling(readers):
    return {"decisions": [{"path": "date", "value": "3 Apr 1969", "supporting_readers": readers,
                           "rationale": "two of three", "settled": True}]}


def test_adjudicator_must_name_readers_by_their_full_label():
    schema = reconciliation_schema(["Reader A", "Reader B"])
    accepted = schema.model_validate(ruling(["Reader A", "Reader B"]))
    assert Reconciliation.model_validate(accepted.model_dump()).decisions[0].supporting_readers == ["Reader A", "Reader B"]
    with pytest.raises(ValidationError):
        schema.model_validate(ruling(["A"]))
    with pytest.raises(ValidationError):
        schema.model_validate(ruling(["Reader C"]))


def test_reconcile_prompt_names_readers_but_not_models():
    readings = [t for t in transcriptions() if t.content is not None]
    prompt = prompts.reconcile_prompt(transcriptions(), diff_readings({t.reader: t.content for t in readings}))
    assert "Reader B: \"8 Apr 1969\"" in prompt
    assert "Reader A found the date smudged" in prompt
    assert "county: Monroe" in prompt
    assert "model-" not in prompt


def test_assign_scores_sends_every_candidate_through_the_same_scorer():
    readings = [t for t in transcriptions() if t.content is not None]
    state = {
        "transcriptions": transcriptions(),
        "diffs": diff_readings({t.reader: t.content for t in readings}),
        "reconciled": {"county": "Monroe", "date": "3 Apr 1969"},
        "human": {"county": "Monroe"},
    }
    sends = graph.assign_scores(state)
    assert {s.node for s in sends} == {"score"}
    assert [s.arg["candidate"] for s in sends] == ["Reader A", "Reader B", "Reader C", MAJORITY, RECONCILED]
    assert all(set(s.arg) == {"candidate", "content", "human"} for s in sends)
    assert sends[3].arg["content"] == {"county": "Monroe", "date": "3 Apr 1969"}


def test_score_prompt_does_not_say_which_candidate_it_is():
    prompt = prompts.score_prompt({"county": "Monroe"}, {"county": "Monroe"})
    for word in ("Reader", MAJORITY, RECONCILED, "adjudicat"):
        assert word not in prompt


def test_readers_are_reported_by_model_name():
    assert graph.reader_names(transcriptions()) == {
        "Reader A": "model-a", "Reader B": "model-b", "Reader C": "model-c", "Reader D": "model-d"}


def test_a_model_that_reads_more_than_once_is_numbered():
    readings = [reading("Reader C", "luna"), reading("Reader A", "luna"), reading("Reader B", "sol"),
                Transcription(reader="Reader D", model="luna", error="failed")]
    assert graph.reader_names(readings) == {
        "Reader A": "luna #1", "Reader B": "sol", "Reader C": "luna #2", "Reader D": "luna #3"}


def test_state_survives_a_checkpoint_round_trip():
    serde = graph.checkpoint_serializer()
    original = transcriptions()[0]
    assert serde.loads_typed(serde.dumps_typed(original)) == original
