"""A local page for reading results next to the scan: ``difffish dashboard``.

Serves on 127.0.0.1 only. Results are re-read on every request, so the page
can be refreshed while a corpus run is still writing them.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from difffish import documents, runs
from difffish.config import get_settings
from difffish.stats import compare, summarize

PAGE = Path(__file__).parent / "dashboard.html"


def run_list(root: Path) -> list[dict]:
    """Every saved run with its manifest and how many documents it holds."""
    return [
        {"name": name, "documents": len(runs.saved_doc_ids(name, root)), "manifest": runs.load_manifest(name, root).model_dump()}
        for name in runs.list_runs(root)
    ]


def payload(run: str, root: Path) -> dict:
    results = runs.load_results(run, root)
    return {
        "run": run,
        "results": [r.model_dump() for r in results],
        "stats": summarize(results).model_dump(),
    }


def comparison(first: str, second: str, root: Path) -> dict:
    """Two runs paired on the documents they share.

    Runs scored by different scorers are not compared: the numbers would
    measure the scorer and not the change between the runs.
    """
    a, b = runs.load_manifest(first, root), runs.load_manifest(second, root)
    scoring = a.differences(b, runs.SCORING)
    return {
        "first": first,
        "second": second,
        "scoring_differs": scoring,
        "config_differs": a.differences(b, runs.READING + runs.RECONCILING),
        "comparison": None if scoring else compare(runs.load_results(first, root), runs.load_results(second, root)).model_dump(),
    }


def make_handler(root: Path, notes_dir: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            path = unquote(url.path)
            query = parse_qs(url.query)
            run = query.get("run", [""])[0]
            pair = [query.get(key, [""])[0] for key in ("first", "second")]
            if path == "/":
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/runs":
                self._send(json.dumps(run_list(root)).encode(), "application/json")
            elif path == "/api/results" and run in runs.list_runs(root):
                self._send(json.dumps(payload(run, root)).encode(), "application/json")
            elif path == "/api/compare" and all(name in runs.list_runs(root) for name in pair):
                self._send(json.dumps(comparison(*pair, root)).encode(), "application/json")
            elif path.startswith("/pdf/") and path.removeprefix("/pdf/") in documents.document_ids():
                self._send(documents.pdf_path(path.removeprefix("/pdf/"), notes_dir).read_bytes(), "application/pdf")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def _send(self, body: bytes, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args) -> None:
            pass

    return Handler


def serve(root: Path, port: int) -> None:
    handler = make_handler(root, get_settings().notes_dir)
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"dashboard at http://127.0.0.1:{port}", flush=True)
        server.serve_forever()
