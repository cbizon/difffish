import pytest

from difffish import prompts


def test_baseline_transcription_prompt_exists():
    assert "baseline" in prompts.transcribe_prompts()
    assert "Transcribe only what is written" in prompts.transcribe_prompt("baseline")


def test_digits_variant_adds_one_paragraph_to_the_baseline():
    baseline, digits = prompts.transcribe_prompt("baseline"), prompts.transcribe_prompt("digits")
    added = [line for line in digits.splitlines() if line and line not in baseline.splitlines()]
    assert len(added) == 1
    assert added[0].startswith("Before any transcription, examine all the handwritten digits")
    assert [line for line in baseline.splitlines() if line not in digits.splitlines()] == []


def test_an_unknown_variant_names_the_ones_that_exist():
    with pytest.raises(FileNotFoundError, match="available: .*baseline"):
        prompts.transcribe_prompt("no-such-variant")
