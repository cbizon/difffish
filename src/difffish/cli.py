"""Command line: ``difffish graph | models | run DOC_ID | corpus [DOC_ID ...]``."""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from difffish import documents
from difffish.config import PROJECT_ROOT, api_key, get_settings
from difffish.stats import report

RESULTS_DIR = PROJECT_ROOT / "results"
CHECKPOINTS = PROJECT_ROOT / ".difffish" / "checkpoints.sqlite"


def show_graphs(args: argparse.Namespace) -> None:
    from difffish.corpus import build_corpus_graph, document_graph

    print(document_graph.get_graph().draw_mermaid())
    print(build_corpus_graph().get_graph().draw_mermaid())


def list_models(args: argparse.Namespace) -> None:
    from openai import OpenAI

    s = get_settings()
    for model in sorted(OpenAI(base_url=s.base_url, api_key=api_key()).models.list().data, key=lambda m: m.id):
        print(model.id)


def run_document(args: argparse.Namespace) -> None:
    """Run one document. An interrupted run resumes from its last checkpoint,
    so readers that already answered are not called again."""
    from difffish.graph import build_document_graph, checkpoint_serializer

    CHECKPOINTS.parent.mkdir(exist_ok=True)
    with sqlite3.connect(CHECKPOINTS, check_same_thread=False) as conn:
        saver = SqliteSaver(conn, serde=checkpoint_serializer())
        graph = build_document_graph(saver)
        config = {"configurable": {"thread_id": args.doc_id}}
        if graph.get_state(config).next and not args.fresh:
            result = graph.invoke(None, config)["result"]  # resume
        else:
            saver.delete_thread(args.doc_id)  # or the old run's readings would be added to
            result = graph.invoke({"doc_id": args.doc_id}, config)["result"]
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{args.doc_id}.json"
    out.write_text(result.model_dump_json(indent=2))
    print(f"{result.contested} of {result.fields} fields contested, {len(result.unsettled)} unsettled")
    for card in result.scorecards:
        name = result.readers.get(card.candidate, card.candidate)
        print(f"  {name:<24}" + "  ".join(f"{s.field}={s.verdict}" for s in card.scores))
    print(f"wrote {out}")


def run_corpus(args: argparse.Namespace) -> None:
    from difffish.corpus import build_corpus_graph

    doc_ids = args.doc_ids or documents.document_ids()[: args.limit]
    state = build_corpus_graph().invoke({"doc_ids": doc_ids}, {"max_concurrency": args.concurrency})
    RESULTS_DIR.mkdir(exist_ok=True)
    for result in state["results"]:
        (RESULTS_DIR / f"{result.doc_id}.json").write_text(result.model_dump_json(indent=2))
    (RESULTS_DIR / "stats.json").write_text(state["stats"].model_dump_json(indent=2))
    print(report(state["stats"]))


def main() -> None:
    parser = argparse.ArgumentParser(prog="difffish", description=__doc__)
    commands = parser.add_subparsers(required=True)

    commands.add_parser("graph", help="print both graphs as Mermaid").set_defaults(func=show_graphs)
    commands.add_parser("models", help="list the models deployed on the endpoint").set_defaults(func=list_models)

    run = commands.add_parser("run", help="run one document")
    run.add_argument("doc_id", help="e.g. WCS-0005")
    run.add_argument("--fresh", action="store_true", help="start over instead of resuming an interrupted run")
    run.set_defaults(func=run_document)

    corpus = commands.add_parser("corpus", help="run many documents and summarize")
    corpus.add_argument("doc_ids", nargs="*", help="documents to run (default: all)")
    corpus.add_argument("--limit", type=int, help="only the first N documents")
    corpus.add_argument("--concurrency", type=int, default=4, help="documents in flight at once")
    corpus.set_defaults(func=run_corpus)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
