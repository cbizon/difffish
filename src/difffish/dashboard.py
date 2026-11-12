"""A local page for reading results next to the scan: ``difffish dashboard``.

Serves on 127.0.0.1 only. Results are re-read on every request, so the page
can be refreshed while a corpus run is still writing them.
"""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from difffish import documents
from difffish.config import get_settings
from difffish.schemas import DocResult
from difffish.stats import summarize

PAGE = Path(__file__).parent / "dashboard.html"


def load_results(results_dir: Path) -> list[DocResult]:
    return [DocResult.model_validate_json(p.read_text()) for p in sorted(results_dir.glob("WCS-*.json"))]


def payload(results_dir: Path) -> dict:
    results = load_results(results_dir)
    return {
        "results": [r.model_dump() for r in results],
        "stats": summarize(results).model_dump(),
    }


def make_handler(results_dir: Path, notes_dir: Path) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = unquote(urlparse(self.path).path)
            if path == "/":
                self._send(PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/results":
                self._send(json.dumps(payload(results_dir)).encode(), "application/json")
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


def serve(results_dir: Path, port: int) -> None:
    handler = make_handler(results_dir, get_settings().notes_dir)
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"dashboard at http://127.0.0.1:{port}", flush=True)
        server.serve_forever()
