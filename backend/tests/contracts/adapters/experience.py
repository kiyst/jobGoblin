"""Experience adapter (Workflow v3.2 Slice 2). Imports only the public
`classify_experience` entry point -- see `adapters/location.py`'s
docstring for the shared rationale. Unlike location/salary, this
parser takes two optional string arguments (`title`, `description`).
For most records only one is populated and `target.input_field` names
that one, with the other passed as `None`. This is not universal: a
record may deliberately populate *both* `title` and `description`
together -- for example a cross-source reconciliation/conflict
witness (see `experience/g05-internal-conflict-precedence`), where the
guard under test is specifically about how the two sources interact.
In that case `target.input_field` names the field the guard's own
mechanism most centrally concerns, not "the only non-null one"."""

from __future__ import annotations

from app.normalization.experience import classify_experience


def invoke(inputs: dict[str, str | None]) -> dict[str, tuple[object, str]]:
    result = classify_experience(inputs.get("title"), inputs.get("description"))
    return {
        "minimum": (result.minimum.value, result.minimum.provenance.value),
        "maximum": (result.maximum.value, result.maximum.provenance.value),
    }
