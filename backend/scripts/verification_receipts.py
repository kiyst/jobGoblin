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
# Duplicated from `check_handoff.py`'s own `_SLICE_ID_RE` -- intentionally,
# not imported, since `check_handoff.py` already imports from this module
# and importing back the other way would be circular. Kept in sync by hand;
# both anchor the same frozen `<date>-<slug>-<base-short-sha>` format.
_SLICE_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*-[0-9a-f]{7,40}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")

_SUPPORTED_SCHEMA_VERSION = "1"
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


def validate_receipt_id(receipt_id: Any) -> None:
    if not isinstance(receipt_id, str) or not _RECEIPT_ID_RE.match(receipt_id):
        raise ReceiptError(
            f"receipt_id must be a canonical lowercase UUID4 (8-4-4-4-12 hyphenated hex), "
            f"got {receipt_id!r}"
        )


def validate_slice_id(slice_id: Any) -> None:
    if not isinstance(slice_id, str) or not _SLICE_ID_RE.match(slice_id):
        raise ReceiptError(f"slice_id must match <date>-<slug>-<base-short-sha>, got {slice_id!r}")


def validate_sha256_hex(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256_HEX_RE.match(value):
        raise ReceiptError(f"{field!r} must be a 64-character lowercase hex sha256, got {value!r}")


def validate_utc_timestamp(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.match(value):
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


def _require_exact_keys(obj: Any, required: frozenset[str], *, context: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ReceiptError(f"{context} must be an object, got {type(obj).__name__}")
    unknown = set(obj) - required
    if unknown:
        raise ReceiptError(f"{context} declares unrecognized field(s): {sorted(unknown)}")
    missing = required - set(obj)
    if missing:
        raise ReceiptError(f"{context} is missing required field(s): {sorted(missing)}")
    return obj


def _require_bool(obj: dict[str, Any], key: str, *, context: str) -> bool:
    value = obj[key]
    if not isinstance(value, bool):
        raise ReceiptError(f"{context}.{key} must be a bool, got {type(value).__name__}")
    return value


def _require_str(obj: dict[str, Any], key: str, *, context: str) -> str:
    value = obj[key]
    if not isinstance(value, str):
        raise ReceiptError(f"{context}.{key} must be a str, got {type(value).__name__}")
    return value


def _require_positive_int(obj: dict[str, Any], key: str, *, context: str) -> int:
    value = obj[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ReceiptError(f"{context}.{key} must be an int, got {type(value).__name__}")
    return value


def _require_str_list(obj: dict[str, Any], key: str, *, context: str) -> list[str]:
    value = obj[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ReceiptError(f"{context}.{key} must be a list of strings")
    return value


_SNAPSHOT_KEYS = frozenset({"tracked_tree_sha", "untracked_present"})
_RUN_CACHE_REDIRECT_KEYS = frozenset(
    {
        "pytest_basetemp_redirected",
        "ruff_cache_redirected",
        "mypy_cache_redirected",
        "pycache_redirected",
    }
)
_COORDINATOR_KEYS = frozenset(
    {
        "authoring_checkout_head_at_start",
        "worktree_initial_snapshot",
        "run_cache_redirect",
        "worktree_final_snapshot",
        "worktree_removed",
        "worktree_leak_check",
        "authoring_checkout_head_at_receipt",
        "authoring_checkout_clean_at_receipt",
    }
)
_STEP_KEYS = frozenset({"name", "status", "duration_seconds"})
_DEPENDENCY_INPUT_KEYS = frozenset({"repo_relative_path", "sha256"})
_ENV_DESCRIPTOR_KEYS = frozenset(
    {"python_version", "platform", "postgresql_version", "installed_distributions_digest"}
)
_AFFECTED_SURFACE_KEYS = frozenset(
    {
        "base_sha",
        "computed_categories",
        "required_contract_families",
        "required_guard_refs",
        "directly_executed_tests",
        "not_applicable_reason",
    }
)
_CLEANUP_KEYS = frozenset({"attempted", "status"})
_DEV_STATE_KEYS = frozenset({"alembic_revision", "schema_fingerprint"})
_MIGRATION_NOT_TRIGGERED_KEYS = frozenset({"triggered"})
_MIGRATION_TRIGGERED_KEYS = frozenset(
    {
        "triggered",
        "status",
        "dev_state_before",
        "dev_state_after",
        "postgresql_server_version",
        "fresh_database_created",
        "fresh_database_cleaned_up",
        "steps",
    }
)

# name -> the exact step this summary field's "ran" status must be backed
# by, with status PASS -- a forged summary can never exist without a real,
# passing step record behind it.
_SUMMARY_TO_REQUIRED_STEP = {
    "full_suite": "full pytest suite",
    "focused_tests": "focused pytest",
    "mutation_witnesses": "contract mutation witnesses",
}


def _validate_snapshot(obj: Any, *, context: str) -> None:
    snap = _require_exact_keys(obj, _SNAPSHOT_KEYS, context=context)
    _require_str(snap, "tracked_tree_sha", context=context)
    _require_bool(snap, "untracked_present", context=context)


def _validate_coordinator(obj: Any) -> dict[str, Any]:
    coordinator = _require_exact_keys(obj, _COORDINATOR_KEYS, context="coordinator")
    _require_str(coordinator, "authoring_checkout_head_at_start", context="coordinator")
    _validate_snapshot(
        coordinator["worktree_initial_snapshot"], context="coordinator.worktree_initial_snapshot"
    )
    _validate_snapshot(
        coordinator["worktree_final_snapshot"], context="coordinator.worktree_final_snapshot"
    )
    run_cache = _require_exact_keys(
        coordinator["run_cache_redirect"],
        _RUN_CACHE_REDIRECT_KEYS,
        context="coordinator.run_cache_redirect",
    )
    for key in _RUN_CACHE_REDIRECT_KEYS:
        _require_bool(run_cache, key, context="coordinator.run_cache_redirect")
    _require_bool(coordinator, "worktree_removed", context="coordinator")
    _require_str(coordinator, "worktree_leak_check", context="coordinator")
    _require_str(coordinator, "authoring_checkout_head_at_receipt", context="coordinator")
    _require_bool(coordinator, "authoring_checkout_clean_at_receipt", context="coordinator")
    return coordinator


def _validate_steps(data: dict[str, Any]) -> list[dict[str, Any]]:
    steps = data["steps"]
    if not isinstance(steps, list):
        raise ReceiptError("steps must be a list")
    names_seen: list[str] = []
    for step in steps:
        _require_exact_keys(step, _STEP_KEYS, context="steps[]")
        _require_str(step, "name", context="steps[]")
        if step["status"] not in _STEP_STATUSES:
            raise ReceiptError(f"invalid step status: {step!r}")
        duration = step["duration_seconds"]
        if isinstance(duration, bool) or not isinstance(duration, int | float):
            raise ReceiptError(f"steps[].duration_seconds must be numeric, got {step!r}")
        names_seen.append(step["name"])
    duplicates = {name for name in names_seen if names_seen.count(name) > 1}
    if duplicates:
        raise ReceiptError(f"receipt declares duplicate step name(s): {sorted(duplicates)}")
    return steps


def _validate_ran_or_not_run_summary(
    data: dict[str, Any],
    field: str,
    *,
    ran_keys: frozenset[str],
) -> None:
    summary = data[field]
    if not isinstance(summary, dict) or "status" not in summary:
        raise ReceiptError(f"{field} must be an object with a 'status' field")
    status = summary["status"]
    if status == "not_run":
        _require_exact_keys(summary, frozenset({"status"}), context=field)
        return
    if status != "ran":
        raise ReceiptError(f"{field}.status must be 'not_run' or 'ran', got {status!r}")
    _require_exact_keys(summary, ran_keys, context=field)

    # Bind this "ran" summary to its corresponding step, PASS, exactly
    # once -- a summary claiming a run happened can never exist without a
    # real, passing step record behind it.
    required_step_name = _SUMMARY_TO_REQUIRED_STEP[field]
    matching = [s for s in data["steps"] if s["name"] == required_step_name]
    if len(matching) != 1:
        raise ReceiptError(
            f"{field}.status is 'ran' but step {required_step_name!r} does not appear "
            f"exactly once in steps (found {len(matching)})"
        )
    if matching[0]["status"] != "PASS":
        raise ReceiptError(f"{field}.status is 'ran' but step {required_step_name!r} is not PASS")


def _validate_migration_matrix(data: dict[str, Any]) -> None:
    migration = data["migration_matrix"]
    if not isinstance(migration, dict) or "triggered" not in migration:
        raise ReceiptError("migration_matrix must be an object with a 'triggered' field")
    triggered = migration["triggered"]
    if not isinstance(triggered, bool):
        raise ReceiptError("migration_matrix.triggered must be a bool")
    if not triggered:
        _require_exact_keys(migration, _MIGRATION_NOT_TRIGGERED_KEYS, context="migration_matrix")
        return
    _require_exact_keys(migration, _MIGRATION_TRIGGERED_KEYS, context="migration_matrix")
    if migration["status"] not in ("PASS", "FAIL"):
        raise ReceiptError("migration_matrix.status must be 'PASS' or 'FAIL'")
    if migration["status"] == "PASS":
        for dev_state_key in ("dev_state_before", "dev_state_after"):
            dev_state = _require_exact_keys(
                migration[dev_state_key],
                _DEV_STATE_KEYS,
                context=f"migration_matrix.{dev_state_key}",
            )
            if dev_state["alembic_revision"] is not None and not isinstance(
                dev_state["alembic_revision"], str
            ):
                raise ReceiptError(
                    f"migration_matrix.{dev_state_key}.alembic_revision must be a str or null"
                )
            _require_str(
                dev_state, "schema_fingerprint", context=f"migration_matrix.{dev_state_key}"
            )
        _require_str(migration, "postgresql_server_version", context="migration_matrix")
        _require_bool(migration, "fresh_database_created", context="migration_matrix")
        _require_bool(migration, "fresh_database_cleaned_up", context="migration_matrix")
        _require_str_list(migration, "steps", context="migration_matrix")


def validate_receipt_schema(data: dict[str, Any]) -> None:
    unknown = set(data) - _REQUIRED_TOP_LEVEL
    if unknown:
        raise ReceiptError(f"receipt declares unrecognized field(s): {sorted(unknown)}")
    missing = _REQUIRED_TOP_LEVEL - set(data)
    if missing:
        raise ReceiptError(f"receipt is missing required field(s): {sorted(missing)}")

    if data["schema_version"] != _SUPPORTED_SCHEMA_VERSION:
        raise ReceiptError(
            f"schema_version must be {_SUPPORTED_SCHEMA_VERSION!r}, got {data['schema_version']!r}"
        )
    validate_slice_id(data["slice_id"])
    validate_receipt_id(data["receipt_id"])
    if data["gate"] not in _GATES:
        raise ReceiptError(f"gate must be one of {sorted(_GATES)}, got {data['gate']!r}")
    if data["risk_class"] not in ("D", "R", "H"):
        raise ReceiptError(f"risk_class must be one of D/R/H, got {data['risk_class']!r}")
    validate_utc_timestamp(data["created_at"], field="created_at")

    for sha_field in ("base_sha", "candidate_sha"):
        value = data[sha_field]
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ReceiptError(f"{sha_field!r} must be a full 40-hex commit SHA, got {value!r}")

    validate_sha256_hex(data["verifier_hash"], field="verifier_hash")
    validate_sha256_hex(data["checker_hash"], field="checker_hash")

    dependency_inputs = data["dependency_and_config_inputs"]
    if not isinstance(dependency_inputs, list):
        raise ReceiptError("dependency_and_config_inputs must be a list")
    for entry in dependency_inputs:
        item = _require_exact_keys(
            entry, _DEPENDENCY_INPUT_KEYS, context="dependency_and_config_inputs[]"
        )
        _require_str(item, "repo_relative_path", context="dependency_and_config_inputs[]")
        validate_sha256_hex(item["sha256"], field="dependency_and_config_inputs[].sha256")

    env_descriptor = _require_exact_keys(
        data["environment_descriptor"], _ENV_DESCRIPTOR_KEYS, context="environment_descriptor"
    )
    _require_str(env_descriptor, "python_version", context="environment_descriptor")
    _require_str(env_descriptor, "platform", context="environment_descriptor")
    if env_descriptor["postgresql_version"] is not None and not isinstance(
        env_descriptor["postgresql_version"], str
    ):
        raise ReceiptError("environment_descriptor.postgresql_version must be a str or null")
    _require_str(env_descriptor, "installed_distributions_digest", context="environment_descriptor")

    _validate_coordinator(data["coordinator"])
    _validate_steps(data)
    _validate_ran_or_not_run_summary(data, "full_suite", ran_keys=frozenset({"status", "count"}))
    _validate_ran_or_not_run_summary(
        data, "focused_tests", ran_keys=frozenset({"status", "selector", "count"})
    )
    _validate_ran_or_not_run_summary(
        data,
        "mutation_witnesses",
        ran_keys=frozenset({"status", "guard_refs", "passed", "failed"}),
    )
    if data["full_suite"].get("status") == "ran":
        _require_positive_int_allow_zero(data["full_suite"], "count", context="full_suite")
    if data["focused_tests"].get("status") == "ran":
        _require_str(data["focused_tests"], "selector", context="focused_tests")
        _require_positive_int_allow_zero(data["focused_tests"], "count", context="focused_tests")
    if data["mutation_witnesses"].get("status") == "ran":
        _require_str_list(data["mutation_witnesses"], "guard_refs", context="mutation_witnesses")
        _require_positive_int_allow_zero(
            data["mutation_witnesses"], "passed", context="mutation_witnesses"
        )
        _require_positive_int_allow_zero(
            data["mutation_witnesses"], "failed", context="mutation_witnesses"
        )

    affected_surface = _require_exact_keys(
        data["affected_surface"], _AFFECTED_SURFACE_KEYS, context="affected_surface"
    )
    _require_str(affected_surface, "base_sha", context="affected_surface")
    for list_key in (
        "computed_categories",
        "required_contract_families",
        "required_guard_refs",
        "directly_executed_tests",
    ):
        _require_str_list(affected_surface, list_key, context="affected_surface")
    if affected_surface["not_applicable_reason"] is not None and not isinstance(
        affected_surface["not_applicable_reason"], str
    ):
        raise ReceiptError("affected_surface.not_applicable_reason must be a str or null")

    _validate_migration_matrix(data)

    cleanup = _require_exact_keys(data["cleanup"], _CLEANUP_KEYS, context="cleanup")
    _require_bool(cleanup, "attempted", context="cleanup")
    if cleanup["status"] not in ("PASS", "FAIL"):
        raise ReceiptError("cleanup.status must be 'PASS' or 'FAIL'")

    if not isinstance(data["approval_eligible"], bool):
        raise ReceiptError("approval_eligible must be a boolean")


def _require_positive_int_allow_zero(obj: dict[str, Any], key: str, *, context: str) -> int:
    value = obj[key]
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReceiptError(f"{context}.{key} must be a non-negative int, got {value!r}")
    return value


def _required_step_names_present(data: dict[str, Any]) -> bool:
    """Every gate requires at least the static/repository checks to have
    genuinely run -- a receipt with an empty step list, one missing these
    names, one declaring a required name more than once, or one where a
    required step's own status is not PASS, can never be eligible,
    regardless of what its other fields claim."""
    required = {"ruff format --check", "ruff check", "mypy", "check_repo.py", "git diff --check"}
    for name in required:
        matching = [s for s in data["steps"] if s["name"] == name]
        if len(matching) != 1 or matching[0]["status"] != "PASS":
            return False
    return True


def _full_suite_genuinely_ran(data: dict[str, Any]) -> bool:
    full_suite = data["full_suite"]
    if full_suite.get("status") != "ran":
        return False
    count = full_suite.get("count")
    return isinstance(count, int) and not isinstance(count, bool) and count > 0


def _witnesses_genuinely_ran_and_passed(data: dict[str, Any]) -> bool:
    witnesses = data["mutation_witnesses"]
    if witnesses.get("status") != "ran":
        return False
    passed = witnesses.get("passed")
    failed = witnesses.get("failed")
    if not (isinstance(passed, int) and isinstance(failed, int)):
        return False
    if isinstance(passed, bool) or isinstance(failed, bool):
        return False
    return failed == 0 and passed > 0


def compute_approval_eligible(data: dict[str, Any]) -> bool:
    """Recomputed from the receipt's own content -- never trusted as
    asserted. False for `fast`. True only for a successful executable
    `final` where: every named static-check step is present; cleanup
    passed; both worktree snapshots are identical and non-trivial; no
    step reports FAIL; the full suite genuinely ran with a positive
    numeric count (never `not_run`, never a non-numeric/boolean value);
    and every dynamically active mutation guard ran and passed (a
    positive numeric `passed` count, zero `failed`). A receipt with an
    empty step list and every execution group left `not_run` is the
    degenerate case this function must reject outright -- it satisfies no
    positive requirement below. True for a successful `docs` gate run on
    the analogous terms -- but a `docs`-gate receipt is only ever *merge*-
    eligible when the paired handoff metadata separately declares
    `slice_kind: docs` (checked by `check_review.py`, which has access to
    both records; this receipt alone never knows the handoff's
    `slice_kind`)."""
    if not data["steps"]:
        return False
    if not _required_step_names_present(data):
        return False
    if data["cleanup"].get("status") != "PASS":
        return False
    coordinator = data["coordinator"]
    initial = coordinator["worktree_initial_snapshot"]
    final = coordinator["worktree_final_snapshot"]
    if initial != final:
        return False
    if not initial.get("tracked_tree_sha"):
        return False
    if any(step["status"] == "FAIL" for step in data["steps"]):
        return False

    gate: str = data["gate"]
    if gate == "fast":
        return False
    if gate == "final":
        return _full_suite_genuinely_ran(data) and _witnesses_genuinely_ran_and_passed(data)
    return bool(gate == "docs")
