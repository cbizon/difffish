from difffish.schemas import MAJORITY, RECONCILED, DocResult, FieldScore, Scorecard
from difffish.stats import compare, comparison_report, report, summarize


def card(candidate, **verdicts):
    return Scorecard(candidate=candidate, scores=[FieldScore(field=f, verdict=v, reason="") for f, v in verdicts.items()])


def result(doc_id, *cards):
    return DocResult(
        doc_id=doc_id,
        human={},
        transcriptions=[],
        diffs=[],
        majority={},
        readers={"Reader A": "model-a", "Reader B": "model-b"},
        failed_readers={},
        fields=10,
        contested=2,
        unsettled=[],
        reconciled={},
        decisions=[],
        scorecards=list(cards),
    )


def results():
    return [
        result(
            "WCS-0001",
            card("Reader A", state="exact", county="mismatch", gear="mismatch"),
            card("Reader B", state="equivalent", county="exact", gear="mismatch"),
            card(MAJORITY, state="exact", county="mismatch", gear="mismatch"),
            card(RECONCILED, state="exact", county="exact", gear="mismatch"),
        ),
        result(
            "WCS-0002",
            card("Reader A", state="exact", county="exact"),
            card("Reader B", state="missing", county="mismatch"),
            card(MAJORITY, state="exact", county="exact"),
            card(RECONCILED, state="exact", county="mismatch"),
        ),
    ]


def test_candidates_are_reported_by_model_name():
    stats = summarize(results())
    assert set(stats.candidates) == {"model-a", "model-b", MAJORITY, RECONCILED}


def test_tallies_count_exact_and_correct():
    stats = summarize(results())
    a = stats.candidates["model-a"]
    assert (a.fields, a.exact, a.correct) == (5, 3, 3)
    b = stats.candidates["model-b"]
    assert (b.fields, b.exact, b.correct) == (5, 1, 2)  # equivalent counts as correct, not exact


def test_tallies_by_field():
    stats = summarize(results())
    assert stats.by_field["county"][RECONCILED].correct == 1
    assert stats.by_field["county"][RECONCILED].fields == 2
    assert stats.by_field["gear"]["model-a"].fields == 1


def test_adjudicator_measures():
    stats = summarize(results())
    assert stats.documents == 2
    assert stats.scored == 5
    assert stats.ceiling == 4  # gear in WCS-0001: no reader had it
    assert stats.missed == 1  # county in WCS-0002: Reader A was right
    assert stats.beat_majority == 1  # county in WCS-0001
    assert stats.lost_to_majority == 1  # county in WCS-0002


def test_report_lists_every_candidate():
    text = report(summarize(results()))
    for name in ("model-a", "model-b", MAJORITY, RECONCILED):
        assert name in text


def second_run():
    return [
        result(
            "WCS-0001",
            card("Reader A", state="exact", county="exact", gear="mismatch"),  # county: gained
            card("Reader B", state="mismatch", county="exact", gear="mismatch"),  # state: lost
            card(MAJORITY, state="exact", county="exact", gear="mismatch"),
            card(RECONCILED, state="exact", county="exact", gear="exact"),  # gear: gained
        ),
        result("WCS-0003", card("Reader A", state="exact"), card(MAJORITY, state="exact"), card(RECONCILED, state="exact")),
    ]


def test_compare_pairs_runs_on_shared_documents_only():
    comparison = compare(results(), second_run())
    assert comparison.documents == 1
    assert comparison.candidates["model-a"].fields == 3


def test_compare_counts_fields_gained_and_lost():
    comparison = compare(results(), second_run())
    a = comparison.candidates["model-a"]
    assert (a.correct_a, a.correct_b, a.gained, a.lost) == (1, 2, 1, 0)
    b = comparison.candidates["model-b"]
    assert (b.correct_a, b.correct_b, b.gained, b.lost) == (2, 1, 0, 1)
    assert comparison.by_field["gear"][RECONCILED].gained == 1
    assert comparison.by_field["state"]["model-b"].lost == 1


def test_compare_lists_each_field_that_changed():
    changes = compare(results(), second_run()).changes
    assert {(c.candidate, c.field, c.gained) for c in changes} == {
        ("model-a", "county", True), ("model-b", "state", False), (MAJORITY, "county", True),
        (RECONCILED, "gear", True)}
    gained = next(c for c in changes if c.candidate == "model-a")
    assert (gained.doc_id, gained.first.verdict, gained.second.verdict) == ("WCS-0001", "mismatch", "exact")


def test_comparison_report_names_both_runs():
    text = comparison_report(compare(results(), second_run()), "baseline", "hints")
    assert "baseline" in text and "hints" in text and "model-a" in text
