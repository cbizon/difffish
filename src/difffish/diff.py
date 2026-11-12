"""Field-by-field comparison of transcriptions. No model calls."""

from __future__ import annotations

from collections import Counter
from typing import Any

from difffish.schemas import Decision, FieldDiff


def flatten(value: Any, prefix: str = "") -> dict[str, str]:
    """Nested dicts and lists to ``{"page_1.locale.county": "Monroe"}``.

    List items are addressed by position: ``page_2.species.0.name``.
    """
    if isinstance(value, dict):
        items = value.items()
    elif isinstance(value, list):
        items = ((str(i), v) for i, v in enumerate(value))
    else:
        return {prefix: "" if value is None else str(value)}
    flat: dict[str, str] = {}
    for key, child in items:
        flat.update(flatten(child, f"{prefix}.{key}" if prefix else str(key)))
    return flat


def unflatten(flat: dict[str, str]) -> dict[str, Any]:
    """Inverse of ``flatten`` (empty lists and dicts are not recoverable)."""
    root: dict[str, Any] = {}
    for path, value in flat.items():
        node = root
        *parents, leaf = path.split(".")
        for key in parents:
            node = node.setdefault(key, {})
        node[leaf] = value
    return _lists(root)


def _lists(node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    children = {k: _lists(v) for k, v in node.items()}
    if children and all(k.isdigit() for k in children):
        return [children[k] for k in sorted(children, key=int)]
    return children


def normalize(value: str) -> str:
    """Readings that differ only in case or spacing count as agreeing."""
    return " ".join(value.split()).casefold()


def diff_readings(readings: dict[str, dict[str, Any]]) -> list[FieldDiff]:
    """Compare each field across readers.

    ``readings`` maps reader label to transcription content. A field one
    reader lacks (a shorter species list, say) counts as blank for that reader.
    """
    flat = {reader: flatten(content) for reader, content in readings.items()}
    paths = list(dict.fromkeys(path for fields in flat.values() for path in fields))
    diffs = []
    for path in paths:
        values = {reader: fields.get(path, "") for reader, fields in flat.items()}
        ranked = Counter(normalize(v) for v in values.values()).most_common(2)
        top = ranked[0][0]
        # A vote only has a winner when one reading has more votes than any other.
        # Five readers who all differ have no majority; neither does a 2-2-1 split.
        tied = len(ranked) > 1 and ranked[0][1] == ranked[1][1]
        diffs.append(
            FieldDiff(
                path=path,
                readings=values,
                plurality="" if tied else next(v for v in values.values() if normalize(v) == top),
                unanimous=len(ranked) == 1,
                tied=tied,
            )
        )
    return diffs


def majority_document(diffs: list[FieldDiff]) -> dict[str, Any]:
    """The transcription a plain vote produces: the baseline for the adjudicator.

    A field with no winning reading is blank, so it scores as missing."""
    return unflatten({d.path: d.plurality for d in diffs})


def reconciled_document(diffs: list[FieldDiff], decisions: list[Decision]) -> dict[str, Any]:
    """Unanimous fields as read, contested fields as the adjudicator ruled."""
    contested = {d.path for d in diffs if not d.unanimous}
    ruled = {d.path: d.value for d in decisions}
    if set(ruled) != contested:
        raise ValueError(
            f"adjudicator rulings do not match the contested fields: "
            f"missing {sorted(contested - set(ruled))}, unexpected {sorted(set(ruled) - contested)}"
        )
    return unflatten({d.path: ruled.get(d.path, d.plurality) for d in diffs})
