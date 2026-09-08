"""Deterministic, offline validator for the Workflow v3.1 pilot's structured
metadata block in `docs/LLM_HANDOFF.md`'s newest `### Work done` entry
(Workflow v3.1 tooling slice — pilot, three-slice trial).

**What this validates**: presence, allowed values, and cross-field
consistency of the metadata block itself, plus (when called from
`verify.py`) a cross-check against the exact counts *that same verifier
invocation* actually observed. **What this never does**: assert or infer
anything about whether the underlying slice's work is semantically
correct. A well-formed, internally-consistent, count-matching block proves
only that the block is honest about its own mechanically-derivable facts
— never that the work it describes is good.

**Never launches a subprocess** — not `pytest`, not `verify.py`, not
anything else. Every check here is a direct, in-process file read or a
comparison against values the caller already has. This is a binding
requirement: a checker that could recursively invoke the canonical
verifier would risk exactly the unbounded, non-deterministic recursion
this tool exists to avoid.

**Which entry is validated**: only the `### Work done` section belonging
to the *last* `## Iteration N` heading in the file (the newest entry, by
document order). Historical, already-rotated-out iterations are never
checked and never fail for predating this format — the two-iteration
rotation rule means older entries may not have a metadata block at all,
and that is not this tool's concern.

**Metadata block schema** (a fenced ```` ```workflow-metadata ```` block,
`key: value` lines):

    workflow_version: v3.1-pilot
    slice_kind: parser | tooling | docs
    verification_level: routine | not_run
    focused_test_selector: <path> | none
    focused_test_count: <int> | not_run
    full_suite_count: <int> | not_run
    lightweight_checks: <comma-separated>   # required only if verification_level: not_run
    fixture_path: <path>                     # required only if slice_kind: parser
    fixture_count: <int>                     # required only if slice_kind: parser

`fixture_path`/`fixture_count` are mandatory when `slice_kind: parser` and
must be *absent* otherwise — a stray, inapplicable field is itself a
structural error, not silently tolerated. `verification_level: not_run`
exists specifically for a genuinely docs-only slice that intentionally did
not run the test suite: `full_suite_count` and `focused_test_count` must
then both be the literal string `not_run` (never a fabricated or
copy-pasted number), and `lightweight_checks` must name what was actually
done instead (e.g. `"ruff format --check, check_repo.py, git diff
--check"`). `slice_kind: parser` additionally requires an actual
(non-`not_run`) `focused_test_count` — a parser slice must be
focus-tested, not merely full-suite-tested.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_PATH = REPO_ROOT / "docs" / "LLM_HANDOFF.md"

_ITERATION_RE = re.compile(r"^## Iteration \d+\s*$", re.MULTILINE)
_WORK_DONE_RE = re.compile(r"^### Work done\s*$", re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^### ", re.MULTILINE)
_METADATA_BLOCK_RE = re.compile(r"```workflow-metadata\n(.*?)\n```", re.DOTALL)

_NOT_RUN = "not_run"
_NONE_SELECTOR = "none"
_VALID_SLICE_KINDS = frozenset({"parser", "tooling", "docs"})
_VALID_VERIFICATION_LEVELS = frozenset({"routine", _NOT_RUN})

_REQUIRED_FIELDS = (
    "workflow_version",
    "slice_kind",
    "verification_level",
    "focused_test_selector",
    "focused_test_count",
    "full_suite_count",
)


class HandoffValidationError(Exception):
    """A structural or consistency problem in the handoff metadata block —
    never raised for a semantic-correctness concern, only for a missing
    field, an unrecognized value, or a mechanically-checkable mismatch."""


def extract_latest_work_done_metadata_text(handoff_text: str) -> str:
    """Returns the raw text inside the `workflow-metadata` fenced block of
    the newest `## Iteration N` heading's `### Work done` section."""
    iteration_matches = list(_ITERATION_RE.finditer(handoff_text))
    if not iteration_matches:
        raise HandoffValidationError("no '## Iteration N' heading found in docs/LLM_HANDOFF.md")
    latest_section = handoff_text[iteration_matches[-1].start() :]

    work_done_matches = list(_WORK_DONE_RE.finditer(latest_section))
    if not work_done_matches:
        raise HandoffValidationError(
            "the newest '## Iteration' heading has no '### Work done' section"
        )
    work_done_start = work_done_matches[-1].end()
    next_heading = _NEXT_HEADING_RE.search(latest_section, work_done_start)
    work_done_end = next_heading.start() if next_heading else len(latest_section)
    work_done_text = latest_section[work_done_start:work_done_end]

    block_match = _METADATA_BLOCK_RE.search(work_done_text)
    if not block_match:
        raise HandoffValidationError(
            "the newest 'Work done' section has no 'workflow-metadata' block"
        )
    return block_match.group(1)


def parse_metadata_fields(raw: str) -> dict[str, str]:
    """Parses `key: value` lines into a dict of raw string values. Blank
    lines are ignored; any other non-`key: value` line is a structural
    error, not silently skipped."""
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if ":" not in stripped:
            raise HandoffValidationError(
                f"malformed metadata line (expected 'key: value'): {stripped!r}"
            )
        key, _, value = stripped.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def _require_int(fields: dict[str, str], key: str) -> int:
    value = fields[key]
    if not value.isdigit():
        raise HandoffValidationError(f"{key!r} must be a non-negative integer, got {value!r}")
    return int(value)


def validate_structure(fields: dict[str, str]) -> None:
    """Validates presence, allowed values, and cross-field consistency of
    the metadata block alone."""
    missing = [key for key in _REQUIRED_FIELDS if key not in fields]
    if missing:
        raise HandoffValidationError(f"metadata block is missing required field(s): {missing}")

    slice_kind = fields["slice_kind"]
    if slice_kind not in _VALID_SLICE_KINDS:
        raise HandoffValidationError(
            f"'slice_kind' must be one of {sorted(_VALID_SLICE_KINDS)}, got {slice_kind!r}"
        )

    verification_level = fields["verification_level"]
    if verification_level not in _VALID_VERIFICATION_LEVELS:
        raise HandoffValidationError(
            f"'verification_level' must be one of {sorted(_VALID_VERIFICATION_LEVELS)}, "
            f"got {verification_level!r}"
        )

    has_fixture_path = "fixture_path" in fields
    has_fixture_count = "fixture_count" in fields
    if slice_kind == "parser":
        if not (has_fixture_path and has_fixture_count):
            raise HandoffValidationError(
                "slice_kind: parser requires both 'fixture_path' and 'fixture_count'"
            )
    elif has_fixture_path or has_fixture_count:
        raise HandoffValidationError(
            f"'fixture_path'/'fixture_count' are not applicable when slice_kind: {slice_kind}"
        )

    if verification_level == _NOT_RUN:
        if fields["full_suite_count"] != _NOT_RUN or fields["focused_test_count"] != _NOT_RUN:
            raise HandoffValidationError(
                "verification_level: not_run requires both 'full_suite_count' and "
                "'focused_test_count' to literally be 'not_run', never a fabricated number"
            )
        if not fields.get("lightweight_checks"):
            raise HandoffValidationError(
                "verification_level: not_run requires a non-empty 'lightweight_checks' "
                "field describing what was actually done"
            )
        return

    # verification_level: routine from here on.
    if fields["full_suite_count"] == _NOT_RUN:
        raise HandoffValidationError(
            "verification_level: routine requires an actual 'full_suite_count' integer, "
            "not 'not_run'"
        )
    _require_int(fields, "full_suite_count")
    if fields.get("lightweight_checks"):
        raise HandoffValidationError(
            "'lightweight_checks' is only applicable when verification_level: not_run"
        )

    focused_count = fields["focused_test_count"]
    focused_selector = fields["focused_test_selector"]
    if focused_count == _NOT_RUN:
        if slice_kind == "parser":
            raise HandoffValidationError(
                "slice_kind: parser requires an actual 'focused_test_count', not 'not_run' "
                "— a parser slice must be focus-tested"
            )
        if focused_selector != _NONE_SELECTOR:
            raise HandoffValidationError(
                "focused_test_count: not_run requires focused_test_selector: none"
            )
    else:
        _require_int(fields, "focused_test_count")
        if focused_selector == _NONE_SELECTOR:
            raise HandoffValidationError(
                "a numeric 'focused_test_count' requires a real 'focused_test_selector', "
                "not 'none'"
            )


def validate_fixture_count(fields: dict[str, str], *, repo_root: Path = REPO_ROOT) -> None:
    """Cross-checks the declared `fixture_count` against the actual length
    of the JSON array at `fixture_path` — a direct, in-process file read,
    never a subprocess. A no-op unless `fixture_path` is present (i.e.
    unless `slice_kind: parser`, per `validate_structure`)."""
    if "fixture_path" not in fields:
        return
    declared_count = _require_int(fields, "fixture_count")
    fixture_path = repo_root / fields["fixture_path"]
    try:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise HandoffValidationError(
            f"fixture_path {fields['fixture_path']!r} could not be read: {type(exc).__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise HandoffValidationError(
            f"fixture_path {fields['fixture_path']!r} is not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, list):
        raise HandoffValidationError(
            f"fixture_path {fields['fixture_path']!r} must contain a JSON array"
        )
    actual_count = len(data)
    if actual_count != declared_count:
        raise HandoffValidationError(
            f"declared fixture_count {declared_count} does not match the actual "
            f"{actual_count} entries in {fields['fixture_path']!r}"
        )


def validate_against_run(
    fields: dict[str, str],
    *,
    docs_only: bool,
    actual_full_suite_count: int | None,
    actual_focused_count: int | None,
    actual_focus_selector: str | None,
) -> None:
    """Cross-checks the metadata block against what *this exact verify.py
    invocation* actually observed. Never launches anything — every
    `actual_*` value is supplied by the caller from its own already-
    completed pytest step(s)."""
    verification_level = fields["verification_level"]

    if docs_only:
        if verification_level != _NOT_RUN:
            raise HandoffValidationError(
                "verify.py was invoked with --docs-only (the full suite did not run), "
                "but the handoff metadata does not declare verification_level: not_run"
            )
        return

    if verification_level == _NOT_RUN:
        raise HandoffValidationError(
            "the handoff metadata declares verification_level: not_run, but this "
            "verify.py invocation actually ran the full suite — record the real counts, "
            "or rerun with --docs-only if that was intended"
        )

    declared_full = _require_int(fields, "full_suite_count")
    if actual_full_suite_count is None:
        raise HandoffValidationError(
            "this run's full-suite pytest summary could not be parsed, so the declared "
            "full_suite_count cannot be cross-checked"
        )
    if declared_full != actual_full_suite_count:
        raise HandoffValidationError(
            f"declared full_suite_count {declared_full} does not match this run's actual "
            f"{actual_full_suite_count}"
        )

    focused_count_field = fields["focused_test_count"]
    if actual_focused_count is None:
        if focused_count_field != _NOT_RUN:
            raise HandoffValidationError(
                "this invocation was not given --focus, but the handoff metadata declares "
                f"a numeric focused_test_count ({focused_count_field!r})"
            )
        if fields["slice_kind"] == "parser":
            raise HandoffValidationError(
                "slice_kind: parser requires this verify.py invocation to be run with "
                "--focus matching the declared focused_test_selector"
            )
        return

    declared_focused = _require_int(fields, "focused_test_count")
    if declared_focused != actual_focused_count:
        raise HandoffValidationError(
            f"declared focused_test_count {declared_focused} does not match this run's "
            f"actual {actual_focused_count}"
        )
    declared_selector = fields["focused_test_selector"]
    if fields["slice_kind"] == "parser" and declared_selector != actual_focus_selector:
        raise HandoffValidationError(
            f"declared focused_test_selector {declared_selector!r} does not match the "
            f"--focus value actually used ({actual_focus_selector!r})"
        )


def validate_handoff(
    *,
    docs_only: bool,
    actual_full_suite_count: int | None,
    actual_focused_count: int | None,
    actual_focus_selector: str | None,
    handoff_path: Path = HANDOFF_PATH,
    repo_root: Path = REPO_ROOT,
) -> None:
    """The single entry point `verify.py` calls. Raises
    `HandoffValidationError` with a precise, actionable message on any
    failure; returns `None` on success. Never launches a subprocess, never
    re-runs pytest or `verify.py` itself."""
    handoff_text = handoff_path.read_text(encoding="utf-8")
    metadata_text = extract_latest_work_done_metadata_text(handoff_text)
    fields = parse_metadata_fields(metadata_text)
    validate_structure(fields)
    validate_fixture_count(fields, repo_root=repo_root)
    validate_against_run(
        fields,
        docs_only=docs_only,
        actual_full_suite_count=actual_full_suite_count,
        actual_focused_count=actual_focused_count,
        actual_focus_selector=actual_focus_selector,
    )


def main() -> int:
    """Standalone structural check only (no "this run's" counts to cross-
    check against) — a quick sanity check of the handoff file's metadata
    block on its own, independent of the full verifier."""
    try:
        handoff_text = HANDOFF_PATH.read_text(encoding="utf-8")
        metadata_text = extract_latest_work_done_metadata_text(handoff_text)
        fields = parse_metadata_fields(metadata_text)
        validate_structure(fields)
        validate_fixture_count(fields)
    except HandoffValidationError as exc:
        print(f"handoff metadata validation failed: {exc}")
        return 1
    print("handoff metadata structure ok")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
