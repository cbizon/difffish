"""Score a saved result again: the scoring half of the document graph on its own.

    START → score × (N + 2) → collect → END

Use after changing the scorer's prompt or model. The saved transcriptions and
reconciliation are reused, so no reader or adjudicator is called.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from difffish.graph import score, score_tasks
from difffish.schemas import DocResult, Scorecard


class RescoreState(TypedDict):
    result: DocResult
    scorecards: Annotated[list[Scorecard], operator.add]


def assign_scores(state: RescoreState) -> list[Send]:
    result = state["result"]
    return score_tasks(result.transcriptions, result.majority, result.reconciled, result.human)


def collect(state: RescoreState) -> dict:
    return {"result": state["result"].model_copy(update={"scorecards": state["scorecards"]})}


def build_rescore_graph():
    builder = StateGraph(RescoreState)
    builder.add_node("score", score)
    builder.add_node("collect", collect)
    builder.add_conditional_edges(START, assign_scores, ["score"])
    builder.add_edge("score", "collect")
    builder.add_edge("collect", END)
    return builder.compile()
