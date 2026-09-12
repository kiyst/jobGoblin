"""Experience adapter (Workflow v3.2 Slice 2). Imports only the public
`classify_experience` entry point -- see `adapters/location.py`'s
docstring for the shared rationale. Unlike location/salary, this
parser takes two optional string arguments (`title`, `description`);
a case record's `target.input_field` states which one it exercises,
and the other is passed as `None`, matching the parser's own
`str | None` signature."""

from __future__ import annotations

from app.normalization.experience import classify_experience


def invoke(inputs: dict[str, str | None]) -> dict[str, tuple[object, str]]:
    result = classify_experience(inputs.get("title"), inputs.get("description"))
    return {
        "minimum": (result.minimum.value, result.minimum.provenance.value),
        "maximum": (result.maximum.value, result.maximum.provenance.value),
    }
