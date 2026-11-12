"""Prompts for the three model roles: reader, adjudicator, scorer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from difffish.schemas import FieldDiff, Transcription

PROMPTS_DIR = Path(__file__).parent / "data" / "prompts"


def transcribe_prompts() -> list[str]:
    """Names of the transcription prompt variants, one text file each."""
    return sorted(p.stem for p in (PROMPTS_DIR / "transcribe").glob("*.txt"))


def transcribe_prompt(name: str) -> str:
    """The transcription prompt a run uses. Add a variant by adding a file."""
    path = PROMPTS_DIR / "transcribe" / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"no transcription prompt {name!r}; available: {', '.join(transcribe_prompts())}")
    return path.read_text().strip()


RECONCILE = """\
Several readers independently transcribed the same scanned, handwritten fish-collection \
field notes into the same structured record. You have not seen the document and cannot. \
Your job is to rule on the fields where the readers disagree, using only what the readers \
wrote.

Evidence you can use:
- How many readers agree, and whether the disagreement is a small variation or a different reading.
- The readers' own notes about what they found hard to read.
- Internal consistency: the same fact is often recorded on more than one page (a field data \
sheet and a summary card), and the agreed fields constrain the contested ones.
- Plausibility: real place names, counties that exist in the stated state, valid dates, real \
fish names, coordinates that fall in the stated region.
- A blank against a filled-in reading can mean one reader missed the text or another invented it.

For every contested field give:
- path: exactly as listed
- value: your ruling. Use one of the readings unless combining them is clearly justified.
- supporting_readers: the readers whose reading matches your ruling, by their full label ("Reader A")
- rationale: one or two sentences
- settled: false when you have no principled basis for choosing and someone needs to look \
at the document again; otherwise true

Rule on every contested field, and only on those."""

SCORE = """\
You are checking a machine transcription of fish-collection field notes against a record \
that a human curator made from the same document.

The curator's record uses its own field names and is not a literal transcription: one \
curator field may combine several form fields (the locality starts with the state and \
county; remarks merge several notes), and names and abbreviations may be expanded. \
The information for a curator field can be anywhere in the transcription.

For each curator field, give one verdict:
- exact: the transcription has the same text, ignoring case and spacing
- equivalent: the same fact written differently ("TN" / "Tennessee", "W.C. Starnes" / \
"Wayne C. Starnes", "20-30 ft" / "20-30 feet", or the same facts spread over several fields)
- mismatch: the transcription states a different fact, or gets any part of a combined field \
wrong (a different digit in a coordinate, a different collector, a different place)
- missing: the transcription has nothing for this field

Apply the rules below the same way every time. Do not weigh small differences case by case: \
if a difference is on the first list it never makes a mismatch, and if it is on the second \
list it always does.

Not a difference (equivalent):
- an abbreviation or expansion of the same word: "Cr." / "C." / "Creek", "R." / "River", \
"mi" / "miles", "ca." / "about", "TN 32" / "Tenn 32", "N. Am." / "North America"
- punctuation, capitals, word order, a leading zero ("03 Apr" / "3 Apr"), "Sep" / "Sept"
- a qualifier, unit or label that is dropped or added without changing the place, person or \
quantity: "16 mi" / "16 air mi", "20-30" / "20-30 feet", "Monroe" / "Monroe County"
- initials for given names and a dropped middle initial ("R. Stiles" / "R.A. Stiles"); \
collectors listed in a different order
- text in the transcription beyond what the curator recorded
- note markers such as an asterisk
- a coordinate in another notation: no degree sign or hemisphere letter, a sign for the \
hemisphere ("-82.7840°" / "82.7840 W"), trailing zeros ("84.848" / "84.8480"), a start and \
end written as a range or as two values

A difference (mismatch):
- any different digit in a number, date or coordinate, including a digit added or dropped \
other than a trailing zero ("35.3222" / "35.32227", "80.0343" / "80.343", "1.3 mi" / "13 mi")
- a different spelling of a proper name, even by one letter ("Klee" / "Klees", \
"Pickett" / "Picket"). Do not correct the curator's spelling.
- a different initial or surname, or a collector the curator lists who is absent
- a different direction, road, waterway or place
- a fact in the curator's field that the transcription lacks: a place, road, distance, \
direction, or a separate note
- an unresolved reading ("197?", "[unclear]") where the curator has a definite value

When pages of the transcription give different readings of the same fact, score the reading \
closest to the curator's. A different reading on another page does not count against it.

Use missing only when the transcription has nothing at all for the field.

Give one score per curator field, using the curator's field names exactly:
- found: the transcription's text for this field, copied as written. When it is spread over \
several transcription fields, join the pieces with "; ". Leave it blank when missing.
- verdict: as above
- reason: one line, naming the differing text for a mismatch"""


def reconcile_prompt(transcriptions: list[Transcription], diffs: list[FieldDiff]) -> str:
    agreed = [f"{d.path}: {d.plurality}" for d in diffs if d.unanimous and d.plurality]
    contested = [
        "\n".join([d.path, *(f"  {reader}: {json.dumps(value)}" for reader, value in d.readings.items())])
        for d in diffs
        if not d.unanimous
    ]
    notes = [f"{t.reader}: {t.notes}" for t in transcriptions if t.content is not None and t.notes]
    return "\n\n".join(
        [
            RECONCILE,
            "AGREED FIELDS (blank ones omitted)\n" + "\n".join(agreed),
            "CONTESTED FIELDS\n" + "\n".join(contested),
            "READER NOTES\n" + "\n".join(notes),
        ]
    )


def score_prompt(content: dict[str, Any], human: dict[str, str]) -> str:
    return "\n\n".join(
        [
            SCORE,
            "CURATOR RECORD\n" + json.dumps(human, indent=2, ensure_ascii=False),
            "TRANSCRIPTION\n" + json.dumps(content, indent=2, ensure_ascii=False),
        ]
    )
