"""Data passed between graph nodes."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

# How a candidate's value for one human field compares with the human value.
#   exact      — the same text, ignoring case and spacing
#   equivalent — the same fact written differently ("TN" / "Tennessee",
#                "W.C. Starnes" / "Wayne C. Starnes")
#   mismatch   — a different fact
#   missing    — the candidate has nothing for this field
Verdict = Literal["exact", "equivalent", "mismatch", "missing"]
CORRECT: frozenset[str] = frozenset({"exact", "equivalent"})

# Candidates scored alongside the individual readers.
MAJORITY = "majority"  # plain vote across readers
RECONCILED = "reconciled"  # the adjudicator's record


class Transcription(BaseModel):
    """One reader's reading of a document, or the reason it has none."""

    reader: str  # anonymous label shown to the adjudicator, e.g. "Reader A"
    model: str  # deployment name; never shown to the adjudicator
    content: dict[str, Any] | None = None
    notes: str = ""
    error: str | None = None


class FieldDiff(BaseModel):
    """What each reader wrote for one field."""

    path: str  # e.g. "page_1.locale.county"
    readings: dict[str, str]  # reader label -> value as written
    plurality: str  # most common reading; ties go to the earliest reader
    unanimous: bool


class Decision(BaseModel):
    """The adjudicator's ruling on one contested field."""

    path: str
    value: str
    supporting_readers: list[str]
    rationale: str
    settled: bool  # False when the readings cannot be resolved without another look


class Reconciliation(BaseModel):
    decisions: list[Decision]


class FieldScore(BaseModel):
    field: str
    verdict: Verdict
    reason: str


class ScoreSheet(BaseModel):
    """The scorer's output for one candidate."""

    scores: list[FieldScore]


class Scorecard(BaseModel):
    candidate: str  # a reader label, "majority", or "reconciled"
    scores: list[FieldScore]


class DocResult(BaseModel):
    doc_id: str
    readers: dict[str, str]  # reader label -> model
    failed_readers: dict[str, str]  # reader label -> error
    fields: int
    contested: int
    unsettled: list[str]
    reconciled: dict[str, Any]
    decisions: list[Decision]
    scorecards: list[Scorecard]
