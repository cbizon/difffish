import pytest


@pytest.fixture
def settings(monkeypatch, tmp_path):
    """A complete configuration that never reaches a real endpoint."""
    for name, value in {
        "AZURE_OPENAI_URL": "http://localhost/openai/v1",
        "DIFFFISH_NOTES_DIR": str(tmp_path),
        "DIFFFISH_READER_MODELS": "model-a, model-b,model-c",
        "DIFFFISH_ADJUDICATOR_MODEL": "adjudicator",
        "DIFFFISH_SCORER_MODEL": "scorer",
        "DIFFFISH_MIN_READERS": "3",
        "DIFFFISH_DPI": "200",
    }.items():
        monkeypatch.setenv(name, value)
