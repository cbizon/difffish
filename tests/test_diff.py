import pytest

from difffish.diff import diff_readings, flatten, majority_document, normalize, reconciled_document, unflatten
from difffish.schemas import Decision

DOC = {
    "page_1": {"date": "3 Apr 1969", "locale": {"county": "Monroe", "lat": ""}},
    "page_2": {"species": [{"name": "L. appendix", "count": "2"}, {"name": "N. rubellus", "count": ""}]},
}


def test_flatten_addresses_nested_fields_and_list_items():
    flat = flatten(DOC)
    assert flat["page_1.locale.county"] == "Monroe"
    assert flat["page_2.species.1.name"] == "N. rubellus"
    assert flat["page_1.locale.lat"] == ""


def test_flatten_turns_none_into_blank():
    assert flatten({"a": None}) == {"a": ""}


def test_unflatten_inverts_flatten():
    assert unflatten(flatten(DOC)) == DOC


def test_unflatten_orders_list_items_numerically():
    flat = {f"s.{i}.n": str(i) for i in (10, 2, 0, 1, 3, 4, 5, 6, 7, 8, 9)}
    assert [item["n"] for item in unflatten(flat)["s"]] == [str(i) for i in range(11)]


def test_normalize_ignores_case_and_spacing():
    assert normalize("  Citico   Cr. ") == normalize("citico cr.")


def readings():
    return {
        "Reader A": {"county": "Monroe", "date": "3 Apr 1969", "gear": "seine"},
        "Reader B": {"county": "monroe ", "date": "8 Apr 1969", "gear": "seine"},
        "Reader C": {"county": "Monroe", "date": "3 Apr 1969", "gear": ""},
    }


def test_diff_separates_unanimous_from_contested():
    diffs = {d.path: d for d in diff_readings(readings())}
    assert diffs["county"].unanimous  # case and spacing do not count as disagreement
    assert not diffs["date"].unanimous
    assert diffs["date"].readings == {"Reader A": "3 Apr 1969", "Reader B": "8 Apr 1969", "Reader C": "3 Apr 1969"}
    assert diffs["date"].plurality == "3 Apr 1969"


def test_diff_plurality_keeps_the_value_as_written():
    assert {d.path: d for d in diff_readings(readings())}["county"].plurality == "Monroe"


def test_readers_who_all_differ_have_no_majority():
    diffs = diff_readings({"Reader A": {"f": "x"}, "Reader B": {"f": "y"}, "Reader C": {"f": "z"}})
    assert diffs[0].tied
    assert diffs[0].plurality == ""


def test_a_split_vote_has_no_majority():
    votes = {"Reader A": "x", "Reader B": "y", "Reader C": "x", "Reader D": "y", "Reader E": "z"}
    diffs = diff_readings({reader: {"f": value} for reader, value in votes.items()})
    assert diffs[0].tied
    assert diffs[0].plurality == ""


def test_a_reading_with_the_most_votes_wins_without_half_the_readers():
    votes = {"Reader A": "x", "Reader B": "y", "Reader C": "x", "Reader D": "z", "Reader E": "w"}
    diffs = diff_readings({reader: {"f": value} for reader, value in votes.items()})
    assert not diffs[0].tied
    assert diffs[0].plurality == "x"


def test_a_tied_field_is_blank_in_the_majority_document():
    diffs = diff_readings({"Reader A": {"f": "x", "g": "1"}, "Reader B": {"f": "y", "g": "1"}})
    assert majority_document(diffs) == {"f": "", "g": "1"}


def test_diff_treats_a_field_one_reader_lacks_as_blank():
    diffs = {d.path: d for d in diff_readings({"Reader A": {"s": [{"n": "a"}]}, "Reader B": {"s": []}})}
    assert diffs["s.0.n"].readings == {"Reader A": "a", "Reader B": ""}
    assert not diffs["s.0.n"].unanimous


def test_majority_document_takes_the_plurality_everywhere():
    assert majority_document(diff_readings(readings())) == {"county": "Monroe", "date": "3 Apr 1969", "gear": "seine"}


def decision(path, value):
    return Decision(path=path, value=value, supporting_readers=[], rationale="", settled=True)


def test_reconciled_document_applies_rulings_to_contested_fields():
    diffs = diff_readings(readings())
    doc = reconciled_document(diffs, [decision("date", "8 Apr 1969"), decision("gear", "seine")])
    assert doc == {"county": "Monroe", "date": "8 Apr 1969", "gear": "seine"}


def test_reconciled_document_rejects_a_missing_ruling():
    with pytest.raises(ValueError, match="missing \\['gear'\\]"):
        reconciled_document(diff_readings(readings()), [decision("date", "3 Apr 1969")])


def test_reconciled_document_rejects_a_ruling_on_an_agreed_field():
    rulings = [decision("date", "x"), decision("gear", "x"), decision("county", "Polk")]
    with pytest.raises(ValueError, match="unexpected \\['county'\\]"):
        reconciled_document(diff_readings(readings()), rulings)
