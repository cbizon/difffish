"""Does the adjudicator help? Aggregate scorecards across documents."""

from __future__ import annotations

from pydantic import BaseModel

from difffish.schemas import CORRECT, MAJORITY, RECONCILED, DocResult, FieldScore


class Tally(BaseModel):
    fields: int = 0
    exact: int = 0
    correct: int = 0  # exact or equivalent

    def add(self, verdict: str) -> None:
        self.fields += 1
        self.exact += verdict == "exact"
        self.correct += verdict in CORRECT


class Stats(BaseModel):
    documents: int = 0
    scored: int = 0  # (document, human field) pairs
    # Keyed by model name, plus "majority" and "reconciled".
    candidates: dict[str, Tally] = {}
    by_field: dict[str, dict[str, Tally]] = {}
    # Counts of (document, human field) pairs:
    ceiling: int = 0  # at least one reader was correct
    missed: int = 0  # reconciled wrong although a reader was correct
    beat_majority: int = 0  # reconciled correct, majority vote wrong
    lost_to_majority: int = 0  # reconciled wrong, majority vote correct


def summarize(results: list[DocResult]) -> Stats:
    stats = Stats(documents=len(results))
    for result in results:
        # field -> candidate -> verdict
        verdicts: dict[str, dict[str, str]] = {}
        for card in result.scorecards:
            name = result.readers.get(card.candidate, card.candidate)
            for s in card.scores:
                verdicts.setdefault(s.field, {})[name] = s.verdict
                stats.candidates.setdefault(name, Tally()).add(s.verdict)
                stats.by_field.setdefault(s.field, {}).setdefault(name, Tally()).add(s.verdict)
        for by_candidate in verdicts.values():
            reconciled = by_candidate[RECONCILED] in CORRECT
            majority = by_candidate[MAJORITY] in CORRECT
            any_reader = any(v in CORRECT for name, v in by_candidate.items() if name not in (MAJORITY, RECONCILED))
            stats.scored += 1
            stats.ceiling += any_reader
            stats.missed += any_reader and not reconciled
            stats.beat_majority += reconciled and not majority
            stats.lost_to_majority += majority and not reconciled
    return stats


def report(stats: Stats) -> str:
    """Plain-text table of the headline numbers."""
    lines = [f"{stats.documents} documents, {stats.scored} scored fields", ""]
    lines.append(f"{'candidate':<24}{'exact':>8}{'correct':>9}")
    for name, tally in sorted(stats.candidates.items(), key=lambda kv: -kv[1].correct / kv[1].fields):
        lines.append(f"{name:<24}{tally.exact / tally.fields:>8.1%}{tally.correct / tally.fields:>9.1%}")
    if stats.scored:
        lines += [
            "",
            f"ceiling (some reader correct):      {stats.ceiling / stats.scored:.1%}",
            f"reconciled wrong, a reader correct: {stats.missed}",
            f"reconciled beat majority vote:      {stats.beat_majority}",
            f"reconciled lost to majority vote:   {stats.lost_to_majority}",
        ]
    return "\n".join(lines)


class Shift(BaseModel):
    """One candidate's scores in two runs, over the fields both runs scored."""

    fields: int = 0
    correct_a: int = 0
    correct_b: int = 0
    gained: int = 0  # wrong in the first run, correct in the second
    lost: int = 0  # correct in the first run, wrong in the second

    def add(self, verdict_a: str, verdict_b: str) -> None:
        a, b = verdict_a in CORRECT, verdict_b in CORRECT
        self.fields += 1
        self.correct_a += a
        self.correct_b += b
        self.gained += b and not a
        self.lost += a and not b


class Change(BaseModel):
    """One field of one candidate that is correct in one run and not in the other."""

    doc_id: str
    candidate: str
    field: str
    human: str
    first: FieldScore
    second: FieldScore
    gained: bool  # wrong in the first run, correct in the second


class Comparison(BaseModel):
    documents: int = 0  # documents present in both runs
    candidates: dict[str, Shift] = {}
    by_field: dict[str, dict[str, Shift]] = {}
    changes: list[Change] = []


def _scores(result: DocResult) -> dict[tuple[str, str], FieldScore]:
    """(candidate by model name, human field) -> score."""
    return {
        (result.readers.get(card.candidate, card.candidate), s.field): s
        for card in result.scorecards
        for s in card.scores
    }


def compare(first: list[DocResult], second: list[DocResult]) -> Comparison:
    """Pair two runs document by document, candidate by candidate, field by field.

    Only what both runs have is compared: shared documents, and candidates
    (readers by model name, the majority vote, the reconciled record) in both.
    """
    other = {r.doc_id: r for r in second}
    comparison = Comparison()
    for result in first:
        if result.doc_id not in other:
            continue
        comparison.documents += 1
        a, b = _scores(result), _scores(other[result.doc_id])
        for key in sorted(a.keys() & b.keys()):
            name, field = key
            first_verdict, second_verdict = a[key].verdict, b[key].verdict
            comparison.candidates.setdefault(name, Shift()).add(first_verdict, second_verdict)
            comparison.by_field.setdefault(field, {}).setdefault(name, Shift()).add(first_verdict, second_verdict)
            if (first_verdict in CORRECT) != (second_verdict in CORRECT):
                comparison.changes.append(
                    Change(doc_id=result.doc_id, candidate=name, field=field, human=result.human.get(field, ""),
                           first=a[key], second=b[key], gained=second_verdict in CORRECT)
                )
    return comparison


def comparison_report(comparison: Comparison, first: str, second: str) -> str:
    def row(label: str, shift: Shift) -> str:
        return (f"{label:<24}{shift.correct_a / shift.fields:>9.1%}{shift.correct_b / shift.fields:>9.1%}"
                f"{shift.gained:>8}{shift.lost:>6}{shift.fields:>8}")

    head = f"{'':<24}{first[:8]:>9}{second[:8]:>9}{'gained':>8}{'lost':>6}{'fields':>8}"
    lines = [f"{comparison.documents} documents in both runs. Correct means exact or equivalent.", "", head]
    order = sorted(comparison.candidates, key=lambda n: -comparison.candidates[n].correct_b)
    lines += [row(name, comparison.candidates[name]) for name in order]
    for name in (RECONCILED, *[n for n in order if n not in (RECONCILED, MAJORITY)][:1]):
        if name not in comparison.candidates:
            continue
        lines += ["", f"{name} by field", head]
        lines += [row(field, by[name]) for field, by in comparison.by_field.items() if name in by]
    return "\n".join(lines)
