import pytest

from difffish import prompts


def test_baseline_transcription_prompt_exists():
    assert "baseline" in prompts.transcribe_prompts()
    assert "Transcribe only what is written" in prompts.transcribe_prompt("baseline")


def test_an_unknown_variant_names_the_ones_that_exist():
    with pytest.raises(FileNotFoundError, match="available: .*baseline"):
        prompts.transcribe_prompt("no-such-variant")
