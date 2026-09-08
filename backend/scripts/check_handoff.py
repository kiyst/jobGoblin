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

These nine names are the **complete, closed schema** — any other key (a typo
such as `typo_full_sute_count`, or an invented field) is rejected outright by
`validate_structure`, never silently ignored.

`fixture_path`/`fixture_count` are mandatory when `slice_kind: parser` and
must be *absent* otherwise — a stray, inapplicable field is itself a
structural error, not silently tolerated. `verification_level: not_run`
exists specifically for a genuinely docs-only slice that intentionally did
not run the test suite, and is **only permitted when `slice_kind: docs`** —
a `parser`/`tooling` slice may never declare `not_run`, even structurally,
independent of how `verify.py` was invoked. When `not_run` applies,
`full_suite_count` and `focused_test_count` must both be the literal
string `not_run` (never a fabricated or copy-pasted number),
`focused_test_selector` must be `none`, and `lightweight_checks` must name
what was actually done instead (e.g. `"ruff format --check,
check_repo.py, git diff --check"`). A `docs` slice that *did* actually run
the test suite instead truthfully records `verification_level: routine`
with real counts, exactly like any other slice kind — `not_run` is
permitted for docs, never mandatory. `slice_kind: parser` additionally
requires an actual (non-`not_run`) `focused_test_count` — a parser slice
must be focus-tested, not merely full-suite-tested. Cross-checking against
an actual invocation (`validate_against_run`) distinguishes a genuinely
*omitted* `--focus` (no cross-check possible) from one that ran but whose
summary line could not be parsed (a hard failure, never silently treated
as omitted) — and requires the declared `focused_test_selector` to match
the `--focus` value actually used whenever focus ran, for every
`slice_kind`, not only `parser`.
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
_SUPPORTED_WORKFLOW_VERSION = "v3.1-pilot"
_VALID_SLICE_KINDS = frozenset({"parser", "tooling", "docs"})
_VALID_VERIFICATION_LEVELS = frozenset({"routine", _NOT_RUN})
_ASCII_INT_RE = re.compile(r"^[0-9]+$")

_REQUIRED_FIELDS = (
    "workflow_version",
    "slice_kind",
    "verification_level",
    "focused_test_selector",
    "focused_test_count",
    "full_suite_count",
)

_OPTIONAL_FIELDS = frozenset({"lightweight_checks", "fixture_path", "fixture_count"})

# The complete, closed set of keys a metadata block may ever declare — the six
# always-required fields plus the three conditionally-required optional ones.
# Any other key (a typo, an invented field) is rejected outright rather than
# silently ignored, per Codex review finding (commit d5fec38).
_ALLOWED_FIELDS = frozenset(_REQUIRED_FIELDS) | _OPTIONAL_FIELDS


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

    block_matches = list(_METADATA_BLOCK_RE.finditer(work_done_text))
    if not block_matches:
        raise HandoffValidationError(
            "the newest 'Work done' section has no 'workflow-metadata' block"
        )
    if len(block_matches) > 1:
        raise HandoffValidationError(
            "the newest 'Work done' section has more than one 'workflow-metadata' block"
        )
    return block_matches[0].group(1)


def parse_metadata_fields(raw: str) -> dict[str, str]:
    """Parses `key: value` lines into a dict of raw string values. Blank
    lines are ignored; any other non-`key: value` line, an empty key, or a
    key repeated more than once (a silently-last-wins overwrite would
    otherwise hide a conflicting declaration) is a structural error, never
    silently skipped or resolved by picking one."""
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
        key = key.strip()
        value = value.strip()
        if not key:
            raise HandoffValidationError(f"malformed metadata line (empty key): {stripped!r}")
        if key in fields:
            raise HandoffValidationError(f"duplicate metadata key {key!r}")
        fields[key] = value
    return fields


def _require_int(fields: dict[str, str], key: str) -> int:
    """Requires an ASCII-digit-only string before calling `int()` — plain
    `str.isdigit()` also accepts non-ASCII "digit" characters (e.g. the
    superscript `²`) that `int()` itself then rejects with an
    unhandled `ValueError`, a real defect found by probing this function
    directly."""
    value = fields[key]
    if not _ASCII_INT_RE.match(value):
        raise HandoffValidationError(f"{key!r} must be a non-negative integer, got {value!r}")
    return int(value)


def validate_structure(fields: dict[str, str]) -> None:
    """Validates presence, allowed values, and cross-field consistency of
    the metadata block alone."""
    unknown = sorted(key for key in fields if key not in _ALLOWED_FIELDS)
    if unknown:
        raise HandoffValidationError(
            f"metadata block declares unrecognized field(s) outside the closed schema: "
            f"{unknown} — allowed fields are {sorted(_ALLOWED_FIELDS)}"
        )

    missing = [key for key in _REQUIRED_FIELDS if key not in fields]
    if missing:
        raise HandoffValidationError(f"metadata block is missing required field(s): {missing}")

    empty = [key for key in _REQUIRED_FIELDS if not fields[key]]
    if empty:
        raise HandoffValidationError(f"metadata block has empty required field(s): {empty}")

    workflow_version = fields["workflow_version"]
    if workflow_version != _SUPPORTED_WORKFLOW_VERSION:
        raise HandoffValidationError(
            f"'workflow_version' must be {_SUPPORTED_WORKFLOW_VERSION!r}, "
            f"got {workflow_version!r}"
        )

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
        if not fields["fixture_path"]:
            raise HandoffValidationError("'fixture_path' must not be empty")
    elif has_fixture_path or has_fixture_count:
        raise HandoffValidationError(
            f"'fixture_path'/'fixture_count' are not applicable when slice_kind: {slice_kind}"
        )

    if verification_level == _NOT_RUN:
        if slice_kind != "docs":
            raise HandoffValidationError(
                "verification_level: not_run is only permitted when slice_kind: docs — "
                f"got slice_kind: {slice_kind!r}"
            )
        if fields["full_suite_count"] != _NOT_RUN or fields["focused_test_count"] != _NOT_RUN:
            raise HandoffValidationError(
                "verification_level: not_run requires both 'full_suite_count' and "
                "'focused_test_count' to literally be 'not_run', never a fabricated number"
            )
        if fields["focused_test_selector"] != _NONE_SELECTOR:
            raise HandoffValidationError(
                "verification_level: not_run requires 'focused_test_selector: none'"
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


def _read_handoff_text(handoff_path: Path) -> str:
    """Reads `handoff_path`, converting every expected failure mode into
    `HandoffValidationError` at this input boundary — a missing file
    (`FileNotFoundError`), a permissions/IO failure (other `OSError`
    subclasses), or invalid UTF-8 (`UnicodeDecodeError`, a `ValueError`
    subclass) would otherwise propagate uncaught through both
    `verify.py`'s `handoff_metadata_step` (which only catches
    `HandoffValidationError`) and this module's own `main()` — a real
    defect found by probing a missing handoff path directly. Never echoes
    the exception's own message, only its type name."""
    try:
        return handoff_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HandoffValidationError(
            f"{handoff_path} could not be read: {type(exc).__name__}"
        ) from exc
    except ValueError as exc:  # covers UnicodeDecodeError
        raise HandoffValidationError(
            f"{handoff_path} could not be decoded as UTF-8: {type(exc).__name__}"
        ) from exc


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
        if fields["slice_kind"] != "docs":
            raise HandoffValidationError(
                "verify.py was invoked with --docs-only, but the handoff metadata declares "
                f"slice_kind: {fields['slice_kind']!r}, not 'docs' — --docs-only is never "
                "valid for a parser or tooling slice"
            )
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
    # `actual_focus_selector` is `None` exactly when `--focus` was never given to this
    # invocation (see `verify.handoff_metadata_step`) — this is the only reliable signal
    # that focus was genuinely *omitted*, as distinct from focus having *run* but its
    # pytest summary being unparseable (`actual_focused_count is None` for a different
    # reason). Conflating the two previously let a declared `not_run` pass silently even
    # when this invocation actually executed a focused run whose output just couldn't be
    # parsed — a real defect found by probing this function directly.
    focus_was_used = actual_focus_selector is not None

    if not focus_was_used:
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

    # This invocation was actually given --focus, regardless of slice_kind.
    if focused_count_field == _NOT_RUN:
        raise HandoffValidationError(
            "this invocation was run with --focus, but the handoff metadata declares "
            "focused_test_count: not_run"
        )
    if actual_focused_count is None:
        raise HandoffValidationError(
            "this run's focused pytest summary could not be parsed, so the declared "
            "focused_test_count cannot be cross-checked"
        )
    declared_focused = _require_int(fields, "focused_test_count")
    if declared_focused != actual_focused_count:
        raise HandoffValidationError(
            f"declared focused_test_count {declared_focused} does not match this run's "
            f"actual {actual_focused_count}"
        )
    declared_selector = fields["focused_test_selector"]
    if declared_selector != actual_focus_selector:
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
    handoff_text = _read_handoff_text(handoff_path)
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
        handoff_text = _read_handoff_text(HANDOFF_PATH)
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
