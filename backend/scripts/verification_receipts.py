"""Immutable verification receipts for Workflow v3.2 (frozen contract).

A receipt is a single, create-only JSON file under
`docs/verification-receipts/<candidate-sha>/<receipt-id>.json`. This module
owns: canonical `receipt_id` generation (a caller can never choose one),
the closed receipt schema (unknown/missing/duplicate keys reject), the
genuinely atomic create-if-absent write (temp file + fsync + `os.link` +
unlink temp -- never `os.replace`, which could silently overwrite), and
`approval_eligible` recomputation (a stored boolean every reader must
independently re-derive, never trust as asserted).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import uuid
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

_RECEIPT_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_UTC_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$")

_GATES = frozenset({"fast", "final", "docs"})
_STEP_STATUSES = frozenset({"PASS", "FAIL", "NOT_RUN"})


class ReceiptError(Exception):
    """A receipt failed schema validation, or could not be created/read
    safely -- never silently downgraded to a warning."""


def generate_receipt_id() -> str:
    """Generated internally, always -- a caller-supplied value is never
    accepted for this field. Canonical lowercase UUID4, hyphenated form
    only; no other separator, no path-traversal component is possible
    since this is the only way a receipt_id is ever produced."""
    return str(uuid.uuid4())


def validate_receipt_id(receipt_id: str) -> None:
    if not _RECEIPT_ID_RE.match(receipt_id):
        raise ReceiptError(
            f"receipt_id must be a canonical lowercase UUID4 (8-4-4-4-12 hyphenated hex), "
            f"got {receipt_id!r}"
        )


def validate_utc_timestamp(value: str, *, field: str) -> None:
    if not _UTC_TIMESTAMP_RE.match(value):
        raise ReceiptError(
            f"{field!r} must be a fully-specified UTC ISO-8601 timestamp "
            f"(explicit Z or +00:00), got {value!r}"
        )


# ---------------------------------------------------------------------------
# Environment descriptor -- secret-free, no local paths, no index URLs.
# ---------------------------------------------------------------------------


def installed_distributions_digest() -> str:
    """sha256 over the sorted (name, version) pairs from
    `importlib.metadata.distributions()` -- package identity/version only,
    never an index URL, file path, or VCS reference (unlike `pip freeze`,
    which can embed exactly those things)."""
    pairs = sorted(
        {(dist.metadata["Name"], dist.version) for dist in importlib_metadata.distributions()}
    )
    payload = json.dumps(pairs, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def environment_descriptor(*, postgresql_version: str | None) -> dict[str, Any]:
    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "postgresql_version": postgresql_version,
        "installed_distributions_digest": installed_distributions_digest(),
    }


# ---------------------------------------------------------------------------
# Dependency/config input hashing -- explicit per-file array, never a
# combined/opaque hash.
# ---------------------------------------------------------------------------


def dependency_and_config_inputs(
    repo_root: Path, relative_paths: list[str]
) -> list[dict[str, str]]:
    entries = []
    for rel in sorted(relative_paths):
        content = (repo_root / rel).read_bytes()
        entries.append({"repo_relative_path": rel, "sha256": hashlib.sha256(content).hexdigest()})
    return entries


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Atomic create-if-absent write.
# ---------------------------------------------------------------------------


def write_receipt_atomic(path: Path, content: dict[str, Any]) -> None:
    """Writes `content` to `path` atomically and create-only: a same-
    filesystem temp file is written and fsynced, then `os.link(temp, path)`
    -- hard-link creation is refused by the filesystem if `path` already
    exists (`FileExistsError`), which is the create-if-absent primitive
    used here, never `os.replace`/`os.rename` (which can silently
    overwrite). The temp link name is removed afterward regardless of
    outcome. Fails closed (re-raises) if hard-linking is unavailable
    (e.g. a cross-filesystem temp/destination) -- no overwrite fallback of
    any kind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(content, indent=2, sort_keys=False) + "\n"

    fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".receipt-", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise ReceiptError(
                f"a receipt already exists at {path} -- create-only, refusing to overwrite"
            ) from exc
        except OSError as exc:
            raise ReceiptError(
                f"atomic create-if-absent write unavailable for {path} ({type(exc).__name__}) -- "
                "failing closed, no overwrite fallback"
            ) from exc
    finally:
        temp_path.unlink(missing_ok=True)


class _StrictDecoder(json.JSONDecoder):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["object_pairs_hook"] = self._reject_duplicates
        super().__init__(*args, **kwargs)

    @staticmethod
    def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise ReceiptError(f"duplicate JSON key {key!r}")
            seen[key] = value
        return seen


def load_receipt_from_text(text: str) -> dict[str, Any]:
    try:
        return json.loads(text, cls=_StrictDecoder)  # type: ignore[no-any-return]
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"not valid JSON: {exc}") from exc


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        return load_receipt_from_text(path.read_text(encoding="utf-8"))
    except ReceiptError as exc:
        raise ReceiptError(f"{path} is {exc}") from exc


# ---------------------------------------------------------------------------
# Closed schema validation.
# ---------------------------------------------------------------------------

_REQUIRED_TOP_LEVEL = frozenset(
    {
        "schema_version",
        "receipt_id",
        "slice_id",
        "risk_class",
        "base_sha",
        "candidate_sha",
        "gate",
        "created_at",
        "coordinator",
        "verifier_hash",
        "checker_hash",
        "dependency_and_config_inputs",
        "environment_descriptor",
        "steps",
        "full_suite",
        "focused_tests",
        "mutation_witnesses",
        "affected_surface",
        "migration_matrix",
        "cleanup",
        "approval_eligible",
    }
)


def validate_receipt_schema(data: dict[str, Any]) -> None:
    unknown = set(data) - _REQUIRED_TOP_LEVEL
    if unknown:
        raise ReceiptError(f"receipt declares unrecognized field(s): {sorted(unknown)}")
    missing = _REQUIRED_TOP_LEVEL - set(data)
    if missing:
        raise ReceiptError(f"receipt is missing required field(s): {sorted(missing)}")

    validate_receipt_id(data["receipt_id"])
    if data["gate"] not in _GATES:
        raise ReceiptError(f"gate must be one of {sorted(_GATES)}, got {data['gate']!r}")
    if data["risk_class"] not in ("D", "R", "H"):
        raise ReceiptError(f"risk_class must be one of D/R/H, got {data['risk_class']!r}")
    validate_utc_timestamp(data["created_at"], field="created_at")

    for sha_field in ("base_sha", "candidate_sha"):
        value = data[sha_field]
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ReceiptError(f"{sha_field!r} must be a full 40-hex commit SHA, got {value!r}")

    for step in data["steps"]:
        if step.get("status") not in _STEP_STATUSES:
            raise ReceiptError(f"invalid step status: {step!r}")

    if not isinstance(data["approval_eligible"], bool):
        raise ReceiptError("approval_eligible must be a boolean")


def compute_approval_eligible(data: dict[str, Any]) -> bool:
    """Recomputed from the receipt's own content -- never trusted as
    asserted. False for `fast`. True only for a successful executable
    `final` (every step PASS/NOT_RUN as applicable, both worktree
    snapshots equal, cleanup PASS). True for a successful `docs` gate run
    on the same terms -- but a `docs`-gate receipt is only ever *merge*-
    eligible when the paired handoff metadata separately declares
    `slice_kind: docs` (checked by `check_review.py`, which has access to
    both records; this receipt alone never knows the handoff's
    `slice_kind`)."""
    if data["cleanup"].get("status") != "PASS":
        return False
    coordinator = data["coordinator"]
    if coordinator["worktree_initial_snapshot"] != coordinator["worktree_final_snapshot"]:
        return False
    if any(step["status"] == "FAIL" for step in data["steps"]):
        return False

    gate: str = data["gate"]
    if gate == "fast":
        return False
    if gate == "final":
        return True
    return bool(gate == "docs")
