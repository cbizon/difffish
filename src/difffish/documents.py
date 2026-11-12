"""Field note PDFs, their page classifications, and the human transcriptions."""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from pathlib import Path

import pymupdf

DATA_DIR = Path(__file__).parent / "data"


@lru_cache
def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text())


def document_ids() -> list[str]:
    return sorted(_load("human_transcriptions.json"))


def page_types(doc_id: str) -> dict[str, str]:
    """Form type of each page, e.g. ``{"page_1": "ncsm_sheet", "page_2": "starnes_card"}``."""
    return _load("form_classifications.json")[doc_id]


def human_record(doc_id: str) -> dict[str, str]:
    """The human transcription, keeping only the fields the curator filled in."""
    return {k: v for k, v in _load("human_transcriptions.json")[doc_id].items() if v is not None}


def pdf_path(doc_id: str, notes_dir: Path) -> Path:
    """The scan for a document. Two files carry a second field number
    ("WCS-1948, REJ-1510.pdf"), so match on the WCS ID prefix."""
    matches = [p for p in notes_dir.glob(f"{doc_id}*.pdf") if p.stem.split(",")[0] == doc_id]
    if len(matches) != 1:
        raise FileNotFoundError(f"expected one PDF for {doc_id} in {notes_dir}, found {len(matches)}")
    return matches[0]


def page_count(path: str | Path) -> int:
    with pymupdf.open(path) as doc:
        return doc.page_count


def render_pages(path: str | Path, dpi: int) -> list[str]:
    """Render each page to a JPEG and return them base64-encoded."""
    with pymupdf.open(path) as doc:
        return [base64.b64encode(page.get_pixmap(dpi=dpi).tobytes("jpeg")).decode() for page in doc]
