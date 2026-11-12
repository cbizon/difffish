"""Command line for difffish.

    difffish models | graph | runs
    difffish document DOC_ID --run NAME [--transcribe-prompt P]
    difffish corpus [DOC_ID ...] --run NAME [--transcribe-prompt P] [--limit N]
    difffish rescore --run NAME
    difffish compare RUN_A RUN_B
    difffish dashboard
"""

from __future__ import annotations

import argparse
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver

from difffish import documents, runs
from difffish.config import PROJECT_ROOT, api_key, get_settings
from difffish.stats import compare, comparison_report, report, summarize

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


def show_runs(args: argparse.Namespace) -> None:
    for name in runs.list_runs():
        manifest = runs.load_manifest(name)
        print(f"{name:<24}{len(runs.saved_doc_ids(name)):>4} documents  prompt={manifest.transcribe_prompt}  "
              f"readers={','.join(manifest.reader_models)}  created={manifest.created}")


def run_document(args: argparse.Namespace) -> None:
    """Run one document. An interrupted run resumes from its last checkpoint,
    so readers that already answered are not called again."""
    from difffish.graph import RunContext, build_document_graph, checkpoint_serializer

    manifest = runs.open_run(args.run, args.transcribe_prompt)
    context = RunContext(transcribe_prompt=manifest.transcribe_prompt)
    CHECKPOINTS.parent.mkdir(exist_ok=True)
    with sqlite3.connect(CHECKPOINTS, check_same_thread=False) as conn:
        saver = SqliteSaver(conn, serde=checkpoint_serializer())
        graph = build_document_graph(saver)
        thread = f"{args.run}:{args.doc_id}"
        config = {"configurable": {"thread_id": thread}}
        if graph.get_state(config).next and not args.fresh:
            result = graph.invoke(None, config, context=context)["result"]  # resume
        else:
            saver.delete_thread(thread)  # or the old run's readings would be added to
            result = graph.invoke({"doc_id": args.doc_id}, config, context=context)["result"]
    out = runs.save_result(args.run, result)
    print(f"{result.contested} of {result.fields} fields contested, {len(result.unsettled)} unsettled")
    for card in result.scorecards:
        name = result.readers.get(card.candidate, card.candidate)
        print(f"  {name:<24}" + "  ".join(f"{s.field}={s.verdict}" for s in card.scores))
    print(f"wrote {out}")


def run_corpus(args: argparse.Namespace) -> None:
    """Run documents into a run. Documents the run already has are skipped, so
    the same command extends a run or picks up after a failure."""
    from difffish.corpus import build_corpus_graph
    from difffish.graph import RunContext

    manifest = runs.open_run(args.run, args.transcribe_prompt)
    wanted = args.doc_ids or documents.document_ids()[: args.limit]
    have = set() if args.redo else runs.saved_doc_ids(args.run)
    doc_ids = [d for d in wanted if d not in have]
    print(f"run {args.run}: prompt {manifest.transcribe_prompt}, {len(doc_ids)} documents to run, "
          f"{len(wanted) - len(doc_ids)} already saved", flush=True)
    if not doc_ids:
        return
    context = RunContext(transcribe_prompt=manifest.transcribe_prompt)
    config = {"max_concurrency": args.concurrency}
    done = 0
    # Stream node by node so each document is saved as soon as it finishes.
    for update in build_corpus_graph().stream({"doc_ids": doc_ids}, config, context=context, stream_mode="updates"):
        for result in update.get("document", {}).get("results", []):
            runs.save_result(args.run, result)
            done += 1
            print(f"[{done}/{len(doc_ids)}] {result.doc_id}: {result.contested} of {result.fields} contested, "
                  f"{len(result.failed_readers)} failed readers", flush=True)
    print(report(summarize(runs.load_results(args.run))))


def rescore(args: argparse.Namespace) -> None:
    """Score a run's saved results again, after a change to the scorer, the human
    records or the vote counting. Readers and adjudicator are not called."""
    from difffish.rescore import build_rescore_graph

    results = [r for r in runs.load_results(args.run) if not args.doc_ids or r.doc_id in args.doc_ids]
    graph = build_rescore_graph()
    inputs = [{"result": r} for r in results]
    for done, (_, output) in enumerate(graph.batch_as_completed(inputs, {"max_concurrency": args.concurrency}), 1):
        runs.save_result(args.run, output["result"])
        print(f"[{done}/{len(results)}] {output['result'].doc_id}", flush=True)
    if not args.doc_ids:
        runs.mark_rescored(args.run)
    print(report(summarize(runs.load_results(args.run))))


def compare_runs(args: argparse.Namespace) -> None:
    first, second = runs.load_manifest(args.first), runs.load_manifest(args.second)
    scoring = first.differences(second, runs.SCORING)
    if scoring:
        raise SystemExit(f"{args.first} and {args.second} were scored differently ({', '.join(scoring)}); "
                         "rescore the older one first, or the comparison would measure the scorer")
    changed = first.differences(second, runs.READING + runs.RECONCILING)
    print(f"{args.first} -> {args.second}: " + (f"differ in {', '.join(changed)}" if changed else "same configuration"))
    print(comparison_report(compare(runs.load_results(args.first), runs.load_results(args.second)),
                            args.first, args.second))


def show_dashboard(args: argparse.Namespace) -> None:
    from difffish.dashboard import serve

    serve(runs.RESULTS_DIR, args.port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="difffish", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(required=True)

    commands.add_parser("graph", help="print both graphs as Mermaid").set_defaults(func=show_graphs)
    commands.add_parser("models", help="list the models deployed on the endpoint").set_defaults(func=list_models)
    commands.add_parser("runs", help="list the saved runs").set_defaults(func=show_runs)

    def run_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--run", required=True, help="name of the run to write to")
        command.add_argument("--transcribe-prompt", help="transcription prompt variant for a new run "
                             "(default: baseline; an existing run keeps its own)")

    document = commands.add_parser("document", help="run one document")
    document.add_argument("doc_id", help="e.g. WCS-0005")
    run_options(document)
    document.add_argument("--fresh", action="store_true", help="start over instead of resuming an interrupted run")
    document.set_defaults(func=run_document)

    corpus = commands.add_parser("corpus", help="run many documents and summarize")
    corpus.add_argument("doc_ids", nargs="*", help="documents to run (default: all)")
    run_options(corpus)
    corpus.add_argument("--limit", type=int, help="only the first N documents")
    corpus.add_argument("--concurrency", type=int, default=4, help="documents in flight at once")
    corpus.add_argument("--redo", action="store_true", help="run documents again even if the run has them")
    corpus.set_defaults(func=run_corpus)

    again = commands.add_parser("rescore", help="score a run's saved results again without re-reading the documents")
    again.add_argument("doc_ids", nargs="*", help="documents to rescore (default: all in the run)")
    again.add_argument("--run", required=True, help="name of the run to rescore")
    again.add_argument("--concurrency", type=int, default=4, help="documents in flight at once")
    again.set_defaults(func=rescore)

    versus = commands.add_parser("compare", help="compare two runs on the documents they share")
    versus.add_argument("first")
    versus.add_argument("second")
    versus.set_defaults(func=compare_runs)

    dashboard = commands.add_parser("dashboard", help="browse results next to the scans")
    dashboard.add_argument("--port", type=int, default=8765)
    dashboard.set_defaults(func=show_dashboard)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
