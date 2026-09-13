"""Deterministic, offline validator for Workflow v3.2's structured
metadata block in `docs/LLM_HANDOFF.md`'s newest `### Work done` entry.

**Schema v2** (Workflow v3.2, superseding the v3.1-pilot schema this
module previously validated -- see `docs/DECISIONS/0009-workflow-v3.2-
activation.md`). A slice's metadata block moves through exactly two
states, defined precisely to avoid a self-referential commit SHA (a
candidate `C` cannot name its own SHA; the commit `A` that publishes a
receipt cannot name its own SHA either):

- **`state: pending`** -- written as part of the candidate commit `C`
  itself. Declares the slice's identity and intent only: `slice_id`,
  `slice_kind`, `risk_class`, `base_sha` (the slice's authoritative
  starting point), and `declared_gate` (the gate this candidate intends
  to be verified under). No receipt exists yet, so none of
  `executed_gate`/`candidate_sha`/`receipt_id`/`receipt_path` may appear.
- **`state: published`** -- the *same* block, transitioned by the direct
  child commit `A` once a receipt has been created: `declared_gate` is
  retained unchanged, and `executed_gate`/`candidate_sha`/`receipt_id`/
  `receipt_path` are added. `executed_gate` must equal `declared_gate`.

**What this validates**: presence, allowed values, and internal
consistency of the metadata block alone -- never anything that requires
Git plumbing or reading the receipt/review chain (that cross-referencing
is `check_review.py`'s job, not this module's). A well-formed,
internally-consistent block proves only that the block is honest about
its own structure -- never that the work it describes is good.

**Never launches a subprocess.** Every check here is a direct, in-process
file read or string/regex validation.

**Which entry is validated**: only the `### Work done` section belonging
to the *last* `## Iteration N` heading in the file (the newest entry).
Historical, already-rotated-out iterations are never checked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.verification_receipts import ReceiptError, validate_receipt_id

REPO_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_PATH = REPO_ROOT / "docs" / "LLM_HANDOFF.md"

_ITERATION_RE = re.compile(r"^## Iteration \d+\s*$", re.MULTILINE)
_WORK_DONE_RE = re.compile(r"^### Work done\s*$", re.MULTILINE)
_NEXT_HEADING_RE = re.compile(r"^### ", re.MULTILINE)
_METADATA_BLOCK_RE = re.compile(r"```workflow-metadata\n(.*?)\n```", re.DOTALL)

_SUPPORTED_WORKFLOW_VERSION = "v3.2"
_VALID_STATES = frozenset({"pending", "published"})
_VALID_SLICE_KINDS = frozenset({"parser", "tooling", "docs"})
_VALID_RISK_CLASSES = frozenset({"D", "R", "H"})
_VALID_GATES = frozenset({"fast", "final", "docs"})
_ASCII_INT_RE = re.compile(r"^[0-9]+$")
_SLICE_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{7,40}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_ALWAYS_REQUIRED_FIELDS = (
    "workflow_version",
    "state",
    "slice_id",
    "slice_kind",
    "risk_class",
    "base_sha",
    "declared_gate",
)
_PUBLISHED_ONLY_REQUIRED_FIELDS = ("executed_gate", "candidate_sha", "receipt_id", "receipt_path")
_OPTIONAL_COUNT_FIELDS = frozenset(
    {"full_suite_count", "focused_test_count", "mutation_witness_count"}
)
_FIXTURE_FIELDS = frozenset({"fixture_path", "fixture_count"})

_ALLOWED_FIELDS = (
    frozenset(_ALWAYS_REQUIRED_FIELDS)
    | frozenset(_PUBLISHED_ONLY_REQUIRED_FIELDS)
    | _OPTIONAL_COUNT_FIELDS
    | _FIXTURE_FIELDS
)


class HandoffValidationError(Exception):
    """A structural or consistency problem in the handoff metadata block --
    never raised for a semantic-correctness concern, only for a missing
    field, an unrecognized value, or a mechanically-checkable mismatch."""


def extract_latest_work_done_metadata_text(handoff_text: str) -> str:
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
    """Parses `key: value` lines into a dict of raw string values. A
    repeated key is a structural error, never a silently-last-wins
    overwrite -- this is the same strict line-based parser every fenced
    metadata block in this project uses (never JSON/YAML nesting)."""
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
    value = fields[key]
    if not _ASCII_INT_RE.match(value):
        raise HandoffValidationError(f"{key!r} must be a non-negative integer, got {value!r}")
    return int(value)


def validate_structure(fields: dict[str, str]) -> None:
    unknown = sorted(key for key in fields if key not in _ALLOWED_FIELDS)
    if unknown:
        raise HandoffValidationError(
            f"metadata block declares unrecognized field(s) outside the closed schema: "
            f"{unknown} — allowed fields are {sorted(_ALLOWED_FIELDS)}"
        )

    missing = [key for key in _ALWAYS_REQUIRED_FIELDS if key not in fields]
    if missing:
        raise HandoffValidationError(f"metadata block is missing required field(s): {missing}")
    empty = [key for key in _ALWAYS_REQUIRED_FIELDS if not fields[key]]
    if empty:
        raise HandoffValidationError(f"metadata block has empty required field(s): {empty}")

    workflow_version = fields["workflow_version"]
    if workflow_version != _SUPPORTED_WORKFLOW_VERSION:
        raise HandoffValidationError(
            f"'workflow_version' must be {_SUPPORTED_WORKFLOW_VERSION!r}, got {workflow_version!r}"
        )

    state = fields["state"]
    if state not in _VALID_STATES:
        raise HandoffValidationError(
            f"'state' must be one of {sorted(_VALID_STATES)}, got {state!r}"
        )

    slice_kind = fields["slice_kind"]
    if slice_kind not in _VALID_SLICE_KINDS:
        raise HandoffValidationError(
            f"'slice_kind' must be one of {sorted(_VALID_SLICE_KINDS)}, got {slice_kind!r}"
        )

    risk_class = fields["risk_class"]
    if risk_class not in _VALID_RISK_CLASSES:
        raise HandoffValidationError(
            f"'risk_class' must be one of {sorted(_VALID_RISK_CLASSES)}, got {risk_class!r}"
        )

    slice_id = fields["slice_id"]
    if not _SLICE_ID_RE.match(slice_id):
        raise HandoffValidationError(
            f"'slice_id' must match <date>-<slug>-<base-short-sha>, got {slice_id!r}"
        )
    base_sha = fields["base_sha"]
    if not _SHA_RE.match(base_sha):
        raise HandoffValidationError(
            f"'base_sha' must be a full 40-hex commit SHA, got {base_sha!r}"
        )
    slice_id_suffix = slice_id.rsplit("-", 1)[-1]
    if not base_sha.startswith(slice_id_suffix):
        raise HandoffValidationError(
            f"'slice_id' base suffix {slice_id_suffix!r} does not match 'base_sha' {base_sha!r}"
        )

    declared_gate = fields["declared_gate"]
    if declared_gate not in _VALID_GATES:
        raise HandoffValidationError(
            f"'declared_gate' must be one of {sorted(_VALID_GATES)}, got {declared_gate!r}"
        )

    published_fields_present = [key for key in _PUBLISHED_ONLY_REQUIRED_FIELDS if key in fields]
    if state == "pending":
        if published_fields_present:
            raise HandoffValidationError(
                f"state: pending must not declare {published_fields_present} -- "
                "no receipt exists yet"
            )
    else:  # published
        missing_published = [key for key in _PUBLISHED_ONLY_REQUIRED_FIELDS if key not in fields]
        if missing_published:
            raise HandoffValidationError(
                f"state: published is missing required field(s): {missing_published}"
            )
        executed_gate = fields["executed_gate"]
        if executed_gate not in _VALID_GATES:
            raise HandoffValidationError(
                f"'executed_gate' must be one of {sorted(_VALID_GATES)}, got {executed_gate!r}"
            )
        if executed_gate != declared_gate:
            raise HandoffValidationError(
                f"'executed_gate' ({executed_gate!r}) must equal "
                f"'declared_gate' ({declared_gate!r})"
            )
        candidate_sha = fields["candidate_sha"]
        if not _SHA_RE.match(candidate_sha):
            raise HandoffValidationError(
                f"'candidate_sha' must be a full 40-hex commit SHA, got {candidate_sha!r}"
            )
        try:
            validate_receipt_id(fields["receipt_id"])
        except ReceiptError as exc:
            raise HandoffValidationError(str(exc)) from exc
        expected_receipt_path = (
            f"docs/verification-receipts/{candidate_sha}/{fields['receipt_id']}.json"
        )
        if fields["receipt_path"] != expected_receipt_path:
            raise HandoffValidationError(
                f"'receipt_path' must be {expected_receipt_path!r}, got {fields['receipt_path']!r}"
            )
        for count_field in _OPTIONAL_COUNT_FIELDS:
            if count_field in fields:
                _require_int(fields, count_field)

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


def _read_handoff_text(handoff_path: Path) -> str:
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


def validate_handoff(*, handoff_path: Path = HANDOFF_PATH, repo_root: Path = REPO_ROOT) -> None:
    """The single entry point `verify.py` calls. Raises
    `HandoffValidationError` on any failure; returns `None` on success.
    Purely structural -- see module docstring for what this does and does
    not validate."""
    handoff_text = _read_handoff_text(handoff_path)
    metadata_text = extract_latest_work_done_metadata_text(handoff_text)
    fields = parse_metadata_fields(metadata_text)
    validate_structure(fields)
    validate_fixture_count(fields, repo_root=repo_root)


def main() -> int:
    try:
        validate_handoff(handoff_path=HANDOFF_PATH, repo_root=REPO_ROOT)
    except HandoffValidationError as exc:
        print(f"handoff metadata validation failed: {exc}")
        return 1
    print("handoff metadata structure ok")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
