"""Does the adjudicator help? Aggregate scorecards across documents."""

from __future__ import annotations

from pydantic import BaseModel

from difffish.schemas import CORRECT, MAJORITY, RECONCILED, DocResult


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
