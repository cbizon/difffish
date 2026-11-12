"""Named runs: one folder of results per configuration, so runs can be compared.

    results/<run>/run.json        how the run was made
    results/<run>/WCS-NNNN.json   one result per document

A run is tied to one configuration. Adding documents to a run with a different
prompt or model is refused, because its results would no longer be comparable
with each other.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from difffish import prompts
from difffish.config import PROJECT_ROOT, get_settings
from difffish.schemas import DocResult

RESULTS_DIR = PROJECT_ROOT / "results"
MANIFEST = "run.json"
READING = ("transcribe_prompt", "transcribe_text", "reader_models", "dpi", "structured_output_method")
RECONCILING = ("adjudicator_model", "reconcile_text", "min_readers")
SCORING = ("scorer_model", "score_text")


class Manifest(BaseModel):
    """How a run was made. Everything that can change a result is here."""

    name: str
    created: str
    git_commit: str | None  # informational: the code version when the run started
    # Reading
    transcribe_prompt: str
    transcribe_text: str
    reader_models: list[str]
    dpi: int
    structured_output_method: str
    # Reconciling
    adjudicator_model: str
    reconcile_text: str
    min_readers: int
    # Scoring
    scorer_model: str
    score_text: str

    def differences(self, other: Manifest, fields: tuple[str, ...] = READING + RECONCILING + SCORING) -> list[str]:
        return [f for f in fields if getattr(self, f) != getattr(other, f)]


def run_dir(name: str, root: Path = RESULTS_DIR) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise ValueError(f"run name {name!r} must be letters, digits, '.', '_' or '-'")
    return root / name


def list_runs(root: Path = RESULTS_DIR) -> list[str]:
    return sorted(p.parent.name for p in root.glob(f"*/{MANIFEST}"))


def git_commit() -> str | None:
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def current_manifest(name: str, transcribe_prompt: str) -> Manifest:
    """The manifest a run started now, with this transcription prompt, would have."""
    s = get_settings()
    return Manifest(
        name=name,
        created=datetime.now().isoformat(timespec="seconds"),
        git_commit=git_commit(),
        transcribe_prompt=transcribe_prompt,
        transcribe_text=prompts.transcribe_prompt(transcribe_prompt),
        reader_models=list(s.reader_models),
        dpi=s.dpi,
        structured_output_method=s.structured_output_method,
        adjudicator_model=s.adjudicator_model,
        reconcile_text=prompts.RECONCILE,
        min_readers=s.min_readers,
        scorer_model=s.scorer_model,
        score_text=prompts.SCORE,
    )


def load_manifest(name: str, root: Path = RESULTS_DIR) -> Manifest:
    path = run_dir(name, root) / MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"no run named {name!r}; existing runs: {', '.join(list_runs(root)) or 'none'}")
    return Manifest.model_validate_json(path.read_text())


def save_manifest(manifest: Manifest, root: Path = RESULTS_DIR) -> None:
    folder = run_dir(manifest.name, root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MANIFEST).write_text(manifest.model_dump_json(indent=2))


def open_run(name: str, transcribe_prompt: str | None, root: Path = RESULTS_DIR) -> Manifest:
    """Start a run, or continue one whose configuration still matches the current one.

    ``transcribe_prompt`` may be left out when continuing: the run's own is used.
    """
    if name not in list_runs(root):
        manifest = current_manifest(name, transcribe_prompt or "baseline")
        save_manifest(manifest, root)
        return manifest
    saved = load_manifest(name, root)
    changed = saved.differences(current_manifest(name, transcribe_prompt or saved.transcribe_prompt))
    if changed and set(changed) <= set(SCORING):
        raise RuntimeError(f"run {name!r} was scored with a different scorer ({', '.join(changed)}); "
                           f"run `difffish rescore --run {name}` first")
    if changed:
        raise RuntimeError(f"run {name!r} was made with a different configuration ({', '.join(changed)}); "
                           "use a new run name")
    return saved


def mark_rescored(name: str, root: Path = RESULTS_DIR) -> Manifest:
    """Record that a run's results now carry the current scorer's verdicts."""
    saved = load_manifest(name, root)
    s = get_settings()
    manifest = saved.model_copy(update={"scorer_model": s.scorer_model, "score_text": prompts.SCORE})
    save_manifest(manifest, root)
    return manifest


def save_result(name: str, result: DocResult, root: Path = RESULTS_DIR) -> Path:
    path = run_dir(name, root) / f"{result.doc_id}.json"
    path.write_text(result.model_dump_json(indent=2))
    return path


def load_results(name: str, root: Path = RESULTS_DIR) -> list[DocResult]:
    return [DocResult.model_validate_json(p.read_text()) for p in sorted(run_dir(name, root).glob("WCS-*.json"))]


def saved_doc_ids(name: str, root: Path = RESULTS_DIR) -> set[str]:
    return {p.stem for p in run_dir(name, root).glob("WCS-*.json")}
