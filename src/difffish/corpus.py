"""The corpus graph: run the document graph on many documents, then summarize.

    START → document × D → summarize → END
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from difffish.graph import build_document_graph
from difffish.schemas import DocResult
from difffish.stats import Stats, summarize

document_graph = build_document_graph()


class CorpusState(TypedDict):
    doc_ids: list[str]
    results: Annotated[list[DocResult], operator.add]
    stats: Stats


class DocumentTask(TypedDict):
    doc_id: str


def assign_documents(state: CorpusState) -> list[Send]:
    return [Send("document", {"doc_id": doc_id}) for doc_id in state["doc_ids"]]


def document(task: DocumentTask) -> dict:
    return {"results": [document_graph.invoke({"doc_id": task["doc_id"]})["result"]]}


def summarize_results(state: CorpusState) -> dict:
    return {"stats": summarize(state["results"])}


def build_corpus_graph():
    builder = StateGraph(CorpusState)
    builder.add_node("document", document)
    builder.add_node("summarize", summarize_results)
    builder.add_conditional_edges(START, assign_documents, ["document"])
    builder.add_edge("document", "summarize")
    builder.add_edge("summarize", END)
    return builder.compile()
