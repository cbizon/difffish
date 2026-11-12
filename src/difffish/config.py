"""Settings read from environment variables (and a .env file, if present).

| Setting                  | Variable                   | Default          |
|--------------------------|----------------------------|------------------|
| Endpoint URL             | AZURE_OPENAI_URL           | (required)       |
| API key                  | AZURE_OPENAI_API_KEY       | (required)       |
| Field notes directory    | DIFFFISH_NOTES_DIR         | (required)       |
| Reader models            | DIFFFISH_READER_MODELS     | (required)       |
| Adjudicator model        | DIFFFISH_ADJUDICATOR_MODEL | (required)       |
| Scorer model             | DIFFFISH_SCORER_MODEL      | (required)       |
| Minimum readers          | DIFFFISH_MIN_READERS       | 3                |
| Page rendering DPI       | DIFFFISH_DPI               | 200              |
| Structured output method | STRUCTURED_OUTPUT_METHOD   | function_calling |
| Retries per model call   | LLM_MAX_RETRIES            | 3                |
| Model call timeout (s)   | LLM_TIMEOUT                | 300              |
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(Path.cwd() / ".env")
load_dotenv(PROJECT_ROOT / ".env")


class NotConfigured(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    base_url: str
    api_key: str
    notes_dir: Path
    reader_models: tuple[str, ...]
    adjudicator_model: str
    scorer_model: str
    min_readers: int
    dpi: int
    structured_output_method: str
    max_retries: int
    timeout: float


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise NotConfigured(f"{name} is not set (see .env.example)")
    return value


def get_settings() -> Settings:
    """Read settings fresh from the environment on every call."""
    return Settings(
        base_url=_required("AZURE_OPENAI_URL"),
        api_key=_required("AZURE_OPENAI_API_KEY"),
        notes_dir=Path(_required("DIFFFISH_NOTES_DIR")),
        reader_models=tuple(m.strip() for m in _required("DIFFFISH_READER_MODELS").split(",") if m.strip()),
        adjudicator_model=_required("DIFFFISH_ADJUDICATOR_MODEL"),
        scorer_model=_required("DIFFFISH_SCORER_MODEL"),
        min_readers=int(os.getenv("DIFFFISH_MIN_READERS", "3")),
        dpi=int(os.getenv("DIFFFISH_DPI", "200")),
        structured_output_method=os.getenv("STRUCTURED_OUTPUT_METHOD", "function_calling"),
        max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
        timeout=float(os.getenv("LLM_TIMEOUT", "300")),
    )
