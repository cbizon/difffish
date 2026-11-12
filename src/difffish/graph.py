"""The document graph: several models read one document, an adjudicator
reconciles them, and a scorer compares every candidate with the human record.

    prepare → transcribe × N → diff → reconcile → score × (N + 2) → compare

Two rules are enforced by what each node is allowed to see, not by prompts:

* The adjudicator never sees the document. Page images are rendered inside
  ``transcribe`` and never enter graph state, and ``reconcile`` declares an
  input schema without the PDF path.
* The adjudicator never sees the human record. Only ``score`` receives it.

The scorer is blind: readers, the majority vote, and the reconciled record all
go through the same node with the same prompt, and it is not told which is which.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

import openai
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic import ValidationError

from difffish import documents, prompts
from difffish.config import get_settings
from difffish.diff import diff_readings, majority_document, reconciled_document
from difffish.forms import build_document_model
from difffish.models import get_structured_model
from difffish.schemas import (
    MAJORITY,
    RECONCILED,
    DocResult,
    FieldDiff,
    Reconciliation,
    Scorecard,
    ScoreSheet,
    Decision,
    FieldScore,
    Transcription,
)

class DocInput(TypedDict):
    doc_id: str


class DocState(TypedDict):
    doc_id: str
    pdf_path: str
    page_types: dict[str, str]
    human: dict[str, str]
    reader_models: list[str]
    transcriptions: Annotated[list[Transcription], operator.add]  # one per reader, added as they finish
    diffs: list[FieldDiff]
    reconciliation: Reconciliation
    reconciled: dict[str, Any]
    scorecards: Annotated[list[Scorecard], operator.add]
    result: DocResult


class ReaderTask(TypedDict):
    reader: str
    model: str
    pdf_path: str
    page_types: dict[str, str]


class ReadingsOnly(TypedDict):
    """All that ``diff`` and ``reconcile`` may see: no document, no human record."""

    transcriptions: list[Transcription]
    diffs: list[FieldDiff]


class ScoreTask(TypedDict):
    candidate: str
    content: dict[str, Any]
    human: dict[str, str]


def prepare(state: DocInput) -> dict:
    s = get_settings()
    doc_id = state["doc_id"]
    path = documents.pdf_path(doc_id, s.notes_dir)
    page_types = documents.page_types(doc_id)
    if documents.page_count(path) != len(page_types):
        raise ValueError(f"{doc_id}: PDF has {documents.page_count(path)} pages, classified {len(page_types)}")
    return {
        "pdf_path": str(path),
        "page_types": page_types,
        "human": documents.human_record(doc_id),
        "reader_models": list(s.reader_models),
    }


def assign_readers(state: DocState) -> list[Send]:
    return [
        Send("transcribe", {"reader": f"Reader {chr(65 + i)}", "model": model,
                            "pdf_path": state["pdf_path"], "page_types": state["page_types"]})
        for i, model in enumerate(state["reader_models"])
    ]


def transcribe(task: ReaderTask) -> dict:
    """One model reads the document. A failed call is recorded, not hidden: ``diff`` enforces the quorum."""
    schema = build_document_model(task["page_types"])
    pages = documents.render_pages(task["pdf_path"], get_settings().dpi)
    message = HumanMessage(
        content=[
            *(
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{page}", "detail": "high"}}
                for page in pages
            ),
            {"type": "text", "text": prompts.TRANSCRIBE},
        ]
    )
    reading = Transcription(reader=task["reader"], model=task["model"])
    try:
        record = get_structured_model(task["model"], schema).invoke([message])
    except (openai.APIError, OutputParserException, ValidationError) as e:
        reading.error = f"{type(e).__name__}: {e}"
    else:
        if record is None:
            reading.error = "model returned no structured record"
        else:
            reading.content = record.model_dump()
            reading.notes = reading.content.pop("transcription_notes")
    return {"transcriptions": [reading]}


def diff(state: ReadingsOnly) -> dict:
    readings = {t.reader: t.content for t in state["transcriptions"] if t.content is not None}
    quorum = get_settings().min_readers
    if len(readings) < quorum:
        failures = "; ".join(f"{t.model}: {t.error}" for t in state["transcriptions"] if t.error)
        raise RuntimeError(f"only {len(readings)} of {len(state['transcriptions'])} readers succeeded "
                           f"(need {quorum}): {failures}")
    return {"diffs": diff_readings(readings)}


def reconcile(state: ReadingsOnly) -> dict:
    diffs = state["diffs"]
    if all(d.unanimous for d in diffs):
        reconciliation = Reconciliation(decisions=[])
    else:
        adjudicator = get_structured_model(get_settings().adjudicator_model, Reconciliation)
        reconciliation = adjudicator.invoke(prompts.reconcile_prompt(state["transcriptions"], diffs))
    return {
        "reconciliation": reconciliation,
        "reconciled": reconciled_document(diffs, reconciliation.decisions),
    }


def assign_scores(state: DocState) -> list[Send]:
    candidates = {t.reader: t.content for t in state["transcriptions"] if t.content is not None}
    candidates[MAJORITY] = majority_document(state["diffs"])
    candidates[RECONCILED] = state["reconciled"]
    return [
        Send("score", {"candidate": name, "content": content, "human": state["human"]})
        for name, content in candidates.items()
    ]


def score(task: ScoreTask) -> dict:
    scorer = get_structured_model(get_settings().scorer_model, ScoreSheet)
    sheet = scorer.invoke(prompts.score_prompt(task["content"], task["human"]))
    scored = [s.field for s in sheet.scores]
    if sorted(scored) != sorted(task["human"]):
        raise ValueError(f"scorer returned fields {sorted(scored)}, expected {sorted(task['human'])}")
    return {"scorecards": [Scorecard(candidate=task["candidate"], scores=sheet.scores)]}


def compare(state: DocState) -> dict:
    decisions = state["reconciliation"].decisions
    return {
        "result": DocResult(
            doc_id=state["doc_id"],
            readers={t.reader: t.model for t in state["transcriptions"] if t.content is not None},
            failed_readers={t.reader: t.error for t in state["transcriptions"] if t.error},
            fields=len(state["diffs"]),
            contested=sum(not d.unanimous for d in state["diffs"]),
            unsettled=[d.path for d in decisions if not d.settled],
            reconciled=state["reconciled"],
            decisions=decisions,
            scorecards=state["scorecards"],
        )
    }


def checkpoint_serializer() -> JsonPlusSerializer:
    """A serializer that is allowed to restore the classes held in graph state."""
    types = [Transcription, FieldDiff, Decision, Reconciliation, FieldScore, Scorecard, DocResult]
    return JsonPlusSerializer(allowed_msgpack_modules=[(t.__module__, t.__name__) for t in types])


def build_document_graph(checkpointer=None):
    builder = StateGraph(DocState, input_schema=DocInput)
    builder.add_node("prepare", prepare)
    builder.add_node("transcribe", transcribe)
    builder.add_node("diff", diff)
    builder.add_node("reconcile", reconcile)
    builder.add_node("score", score)
    builder.add_node("compare", compare)
    builder.add_edge(START, "prepare")
    builder.add_conditional_edges("prepare", assign_readers, ["transcribe"])  # fan out, one per reader
    builder.add_edge("transcribe", "diff")  # runs once, after every reader
    builder.add_edge("diff", "reconcile")
    builder.add_conditional_edges("reconcile", assign_scores, ["score"])  # fan out, one per candidate
    builder.add_edge("score", "compare")
    builder.add_edge("compare", END)
    return builder.compile(checkpointer=checkpointer)
