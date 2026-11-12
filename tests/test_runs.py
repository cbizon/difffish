import pytest

from difffish import prompts, runs
from difffish.schemas import DocResult


def result(doc_id):
    return DocResult(doc_id=doc_id, human={}, readers={}, failed_readers={}, transcriptions=[], diffs=[], fields=0,
                     contested=0, unsettled=[], majority={}, reconciled={}, decisions=[], scorecards=[])


def test_a_new_run_records_how_it_was_made(settings, tmp_path):
    manifest = runs.open_run("first", None, tmp_path)
    assert manifest.transcribe_prompt == "baseline"
    assert manifest.transcribe_text == prompts.transcribe_prompt("baseline")
    assert manifest.reader_models == ["model-a", "model-b", "model-c"]
    assert (manifest.adjudicator_model, manifest.scorer_model) == ("adjudicator", "scorer")
    assert manifest.score_text == prompts.SCORE
    assert runs.load_manifest("first", tmp_path) == manifest
    assert runs.list_runs(tmp_path) == ["first"]


def test_continuing_a_run_keeps_its_manifest(settings, tmp_path):
    first = runs.open_run("first", None, tmp_path)
    assert runs.open_run("first", None, tmp_path) == first
    assert runs.open_run("first", "baseline", tmp_path) == first


def test_a_run_cannot_be_continued_with_other_readers(settings, tmp_path, monkeypatch):
    runs.open_run("first", None, tmp_path)
    monkeypatch.setenv("DIFFFISH_READER_MODELS", "model-a,model-b,model-z")
    with pytest.raises(RuntimeError, match="different configuration \\(reader_models\\)"):
        runs.open_run("first", None, tmp_path)


def test_a_run_cannot_be_continued_with_another_prompt(settings, tmp_path, monkeypatch):
    runs.open_run("first", None, tmp_path)
    variants = tmp_path / "prompts"
    (variants / "transcribe").mkdir(parents=True)
    (variants / "transcribe" / "baseline.txt").write_text("the baseline")
    (variants / "transcribe" / "v2.txt").write_text("a different prompt")
    monkeypatch.setattr(prompts, "PROMPTS_DIR", variants)
    with pytest.raises(RuntimeError, match="transcribe_prompt"):
        runs.open_run("first", "v2", tmp_path)


def test_a_run_scored_by_another_scorer_asks_for_a_rescore(settings, tmp_path, monkeypatch):
    runs.open_run("first", None, tmp_path)
    monkeypatch.setenv("DIFFFISH_SCORER_MODEL", "new-scorer")
    with pytest.raises(RuntimeError, match="rescore --run first"):
        runs.open_run("first", None, tmp_path)
    assert runs.mark_rescored("first", tmp_path).scorer_model == "new-scorer"
    assert runs.open_run("first", None, tmp_path).scorer_model == "new-scorer"


def test_results_are_kept_per_run(settings, tmp_path):
    runs.open_run("first", None, tmp_path)
    runs.open_run("second", None, tmp_path)
    runs.save_result("first", result("WCS-0006"), tmp_path)
    runs.save_result("first", result("WCS-0005"), tmp_path)
    runs.save_result("second", result("WCS-0005"), tmp_path)
    assert [r.doc_id for r in runs.load_results("first", tmp_path)] == ["WCS-0005", "WCS-0006"]
    assert runs.saved_doc_ids("second", tmp_path) == {"WCS-0005"}
    assert runs.list_runs(tmp_path) == ["first", "second"]


def test_an_unknown_run_names_the_ones_that_exist(settings, tmp_path):
    runs.open_run("first", None, tmp_path)
    with pytest.raises(FileNotFoundError, match="existing runs: first"):
        runs.load_manifest("other", tmp_path)


@pytest.mark.parametrize("name", ["../escape", "a/b", "", ".hidden", "with space"])
def test_run_names_cannot_leave_the_results_folder(name, tmp_path):
    with pytest.raises(ValueError):
        runs.run_dir(name, tmp_path)


def test_manifest_differences_can_be_limited_to_one_stage(settings, tmp_path, monkeypatch):
    first = runs.current_manifest("a", "baseline")
    monkeypatch.setenv("DIFFFISH_SCORER_MODEL", "new-scorer")
    monkeypatch.setenv("DIFFFISH_DPI", "300")
    second = runs.current_manifest("b", "baseline")
    assert first.differences(second) == ["dpi", "scorer_model"]
    assert first.differences(second, runs.SCORING) == ["scorer_model"]
    assert first.differences(second, runs.READING) == ["dpi"]
