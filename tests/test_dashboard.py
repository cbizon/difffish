import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pymupdf
import pytest

from difffish.dashboard import load_results, make_handler, payload
from difffish.schemas import MAJORITY, RECONCILED, DocResult, FieldScore, Scorecard


def result(doc_id):
    cards = [Scorecard(candidate=c, scores=[FieldScore(field="state", verdict="exact", reason="same")])
             for c in ("Reader A", MAJORITY, RECONCILED)]
    return DocResult(doc_id=doc_id, human={"state": "Tennessee"}, readers={"Reader A": "model-a"}, failed_readers={},
                     transcriptions=[], diffs=[], fields=1, contested=0, unsettled=[], majority={}, reconciled={},
                     decisions=[], scorecards=cards)


@pytest.fixture
def dirs(tmp_path):
    results, notes = tmp_path / "results", tmp_path / "notes"
    results.mkdir()
    notes.mkdir()
    for doc_id in ("WCS-0006", "WCS-0005"):
        (results / f"{doc_id}.json").write_text(result(doc_id).model_dump_json())
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(notes / "WCS-0005.pdf")
    return results, notes


@pytest.fixture
def url(dirs):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(*dirs))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url) as response:
        return response.headers["Content-Type"], response.read()


def test_load_results_returns_documents_in_order(dirs):
    assert [r.doc_id for r in load_results(dirs[0])] == ["WCS-0005", "WCS-0006"]


def test_payload_has_results_and_statistics(dirs):
    data = payload(dirs[0])
    assert len(data["results"]) == 2
    assert data["stats"]["documents"] == 2
    assert data["stats"]["candidates"]["model-a"]["correct"] == 2


def test_serves_the_page(url):
    content_type, body = get(url + "/")
    assert content_type.startswith("text/html")
    assert b"difffish" in body


def test_serves_results_as_json(url):
    content_type, body = get(url + "/api/results")
    assert content_type == "application/json"
    assert [r["doc_id"] for r in json.loads(body)["results"]] == ["WCS-0005", "WCS-0006"]


def test_serves_the_scan(url):
    content_type, body = get(url + "/pdf/WCS-0005")
    assert content_type == "application/pdf"
    assert body.startswith(b"%PDF")


@pytest.mark.parametrize("path", ["/pdf/../../etc/passwd", "/pdf/WCS-9999", "/nothing"])
def test_refuses_anything_that_is_not_a_known_document(url, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        get(url + path)
    assert error.value.code == 404
