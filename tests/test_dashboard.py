import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pymupdf
import pytest

from difffish import runs
from difffish.dashboard import comparison, make_handler, payload, run_list
from difffish.schemas import MAJORITY, RECONCILED, DocResult, FieldScore, Scorecard


def result(doc_id):
    cards = [Scorecard(candidate=c, scores=[FieldScore(field="state", verdict="exact", reason="same")])
             for c in ("Reader A", MAJORITY, RECONCILED)]
    return DocResult(doc_id=doc_id, human={"state": "Tennessee"}, readers={"Reader A": "model-a"}, failed_readers={},
                     transcriptions=[], diffs=[], fields=1, contested=0, unsettled=[], majority={}, reconciled={},
                     decisions=[], scorecards=cards)


@pytest.fixture
def dirs(tmp_path, settings):
    results, notes = tmp_path / "results", tmp_path / "notes"
    notes.mkdir()
    runs.save_manifest(runs.current_manifest("baseline", "baseline"), results)
    for doc_id in ("WCS-0006", "WCS-0005"):
        runs.save_result("baseline", result(doc_id), results)
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


def test_run_list_describes_each_run(dirs):
    listed = run_list(dirs[0])
    assert [(r["name"], r["documents"]) for r in listed] == [("baseline", 2)]
    assert listed[0]["manifest"]["transcribe_prompt"] == "baseline"


def test_payload_has_results_and_statistics(dirs):
    data = payload("baseline", dirs[0])
    assert [r["doc_id"] for r in data["results"]] == ["WCS-0005", "WCS-0006"]
    assert len(data["results"]) == 2
    assert data["stats"]["documents"] == 2
    assert data["stats"]["candidates"]["model-a"]["correct"] == 2


def test_serves_the_page(url):
    content_type, body = get(url + "/")
    assert content_type.startswith("text/html")
    assert b"difffish" in body


def test_serves_results_as_json(url):
    content_type, body = get(url + "/api/results?run=baseline")
    assert content_type == "application/json"
    assert [r["doc_id"] for r in json.loads(body)["results"]] == ["WCS-0005", "WCS-0006"]


def test_serves_the_list_of_runs(url):
    content_type, body = get(url + "/api/runs")
    assert content_type == "application/json"
    assert [r["name"] for r in json.loads(body)] == ["baseline"]


def test_serves_a_comparison_of_two_runs(url, dirs):
    runs.save_manifest(runs.current_manifest("other", "baseline"), dirs[0])
    runs.save_result("other", result("WCS-0005"), dirs[0])
    content_type, body = get(url + "/api/compare?first=baseline&second=other")
    data = json.loads(body)
    assert content_type == "application/json"
    assert data["scoring_differs"] == [] and data["config_differs"] == []
    assert data["comparison"]["documents"] == 1
    assert data["comparison"]["candidates"]["model-a"]["fields"] == 1


def test_runs_scored_differently_are_not_compared(dirs, monkeypatch):
    monkeypatch.setenv("DIFFFISH_SCORER_MODEL", "another-scorer")
    runs.save_manifest(runs.current_manifest("other", "baseline"), dirs[0])
    data = comparison("baseline", "other", dirs[0])
    assert data["scoring_differs"] == ["scorer_model"]
    assert data["comparison"] is None


def test_serves_the_scan(url):
    content_type, body = get(url + "/pdf/WCS-0005")
    assert content_type == "application/pdf"
    assert body.startswith(b"%PDF")


@pytest.mark.parametrize("path", ["/pdf/../../etc/passwd", "/pdf/WCS-9999", "/nothing", "/api/results",
                                  "/api/results?run=other", "/api/results?run=../baseline",
                                  "/api/compare?first=baseline", "/api/compare?first=baseline&second=nope"])
def test_refuses_anything_that_is_not_a_known_document_or_run(url, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        get(url + path)
    assert error.value.code == 404
