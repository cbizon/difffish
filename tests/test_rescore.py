from difffish import documents
from difffish.rescore import assign_scores, build_rescore_graph, collect, refresh
from difffish.schemas import MAJORITY, RECONCILED, DocResult, FieldScore, Scorecard, Transcription


def saved_result():
    return DocResult(
        doc_id="WCS-0005",
        human={"state": "Tennessee"},
        readers={"Reader A": "model-a"},
        failed_readers={"Reader B": "NotFoundError"},
        transcriptions=[
            Transcription(reader="Reader A", model="model-a", content={"state": "TN"}),
            Transcription(reader="Reader B", model="model-b", error="NotFoundError"),
            Transcription(reader="Reader C", model="model-c", content={"state": "Tenn."}),
        ],
        diffs=[],
        fields=1,
        contested=0,
        unsettled=[],
        majority={"state": "TN"},
        reconciled={"state": "Tenn."},
        decisions=[],
        scorecards=[Scorecard(candidate="Reader A", scores=[FieldScore(field="state", verdict="mismatch", reason="old")])],
    )


def test_graph_shape():
    edges = {(e.source, e.target) for e in build_rescore_graph().get_graph().edges}
    assert edges == {("__start__", "refresh"), ("refresh", "score"), ("score", "collect"), ("collect", "__end__")}


def test_refresh_replaces_the_saved_human_record_with_the_current_one():
    out = refresh({"result": saved_result()})["result"]
    assert out.human == documents.human_record("WCS-0005")
    assert out.majority == {"state": ""}  # recounted: the two readers differ, so there is no majority
    assert out.diffs[0].tied
    assert out.reconciled == {"state": "Tenn."}


def test_saved_candidates_are_sent_to_the_scorer_without_the_failed_reader():
    sends = assign_scores({"result": saved_result()})
    assert [(s.arg["candidate"], s.arg["content"]) for s in sends] == [
        ("Reader A", {"state": "TN"}),
        ("Reader C", {"state": "Tenn."}),
        (MAJORITY, {"state": "TN"}),
        (RECONCILED, {"state": "Tenn."}),
    ]
    assert all(s.arg["human"] == {"state": "Tennessee"} for s in sends)


def test_collect_replaces_the_old_scorecards_and_keeps_the_rest():
    new = [Scorecard(candidate="Reader A", scores=[FieldScore(field="state", found="TN", verdict="equivalent", reason="new")])]
    out = collect({"result": saved_result(), "scorecards": new})["result"]
    assert out.scorecards == new
    assert out.reconciled == {"state": "Tenn."}
