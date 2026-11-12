"""Score a saved result again: the scoring half of the document graph on its own.

    START → refresh → score × (N + 2) → collect → END

Use after changing the scorer's prompt or model, or the human records. The
saved transcriptions and reconciliation are reused, so no reader or adjudicator
is called.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from difffish import documents
from difffish.graph import score, score_tasks
from difffish.schemas import DocResult, Scorecard


class RescoreState(TypedDict):
    result: DocResult
    scorecards: Annotated[list[Scorecard], operator.add]


def refresh(state: RescoreState) -> dict:
    """Pick up the current human record, which may have changed since the result was saved."""
    result = state["result"]
    return {"result": result.model_copy(update={"human": documents.human_record(result.doc_id)})}


def assign_scores(state: RescoreState) -> list[Send]:
    result = state["result"]
    return score_tasks(result.transcriptions, result.majority, result.reconciled, result.human)


def collect(state: RescoreState) -> dict:
    return {"result": state["result"].model_copy(update={"scorecards": state["scorecards"]})}


def build_rescore_graph():
    builder = StateGraph(RescoreState)
    builder.add_node("refresh", refresh)
    builder.add_node("score", score)
    builder.add_node("collect", collect)
    builder.add_edge(START, "refresh")
    builder.add_conditional_edges("refresh", assign_scores, ["score"])
    builder.add_edge("score", "collect")
    builder.add_edge("collect", END)
    return builder.compile()
