"""Prompts for the three model roles: reader, adjudicator, scorer."""

from __future__ import annotations

import json
from typing import Any

from difffish.schemas import FieldDiff, Transcription

TRANSCRIBE = """\
You are an expert at transcribing handwritten documents into structured data. The attached \
images are the pages of a scanned field data sheet used by a fish biologist to record \
collections. Pages may be pre-printed forms filled in by hand, handwritten cards, typed \
species lists, or free-form notes.

Fill in the structured record for every page.

Transcription rules:
- Transcribe only what is written; do not infer or guess values that are absent.
- Leave a field as an empty string if it was left blank on the form.
- Text for a form field may appear on the line, above it, below it, or to the side — include all of it.
- A caret (^) or connecting line indicates a continuation; treat the continued text as part of the same field.
- Ignore crossed-out or scribbled-out text.
- If a field contains two values (e.g. start/end coordinates or two time intervals), separate them with " / ".

Hints for the NCSM Aquatic/Marine Field Data Sheet:
- DATE: usually DD MMM YYYY
- TIME: usually a 24-hour range e.g. "0830-1100"
- FIELD#: format WCS-NNNN
- LOCALITY: spans two printed lines; include both
- LAT/LONG: usually 5 decimal places
- METHOD CAPTURE: may have text above and below the line; common values include "seine" (with \
length), "electrofishing boat", "backpack electrofisher", "angling"
- STREAM WIDTH / MAX DEPTH: values often written above the line; usually in meters
- CURRENT: common values "fast", "moderate", "sluggish" (often abbreviated)

In transcription_notes, record the fields where you were unsure of the reading and why \
(smearing, overwriting, ambiguous characters), and any handwritten text you could not \
place in a field."""

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
- supporting_readers: the readers whose reading matches your ruling
- rationale: one or two sentences
- settled: false when you have no principled basis for choosing and someone needs to look \
at the document again; otherwise true

Rule on every contested field, and only on those."""

SCORE = """\
You are checking a machine transcription of fish-collection field notes against a record \
that a human curator made from the same document.

The curator's record uses its own field names and is not a literal transcription: one \
curator field may combine several form fields (the locality includes state, county and \
coordinates; remarks merge several notes), and names and abbreviations may be expanded. \
The information for a curator field can be anywhere in the transcription.

For each curator field, give one verdict:
- exact: the transcription has the same text, ignoring case and spacing
- equivalent: the same fact written differently ("TN" / "Tennessee", "W.C. Starnes" / \
"Wayne C. Starnes", "20-30 ft" / "20-30 feet", or the same facts spread over several fields)
- mismatch: the transcription states a different fact, or gets any part of a combined field \
wrong (a different digit in a coordinate, a different collector, a different place)
- missing: the transcription has nothing for this field

Give one score per curator field, using the curator's field names exactly, with a one-line \
reason that names the differing text for a mismatch."""


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
