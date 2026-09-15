from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import verification_receipts as vr


def test_generate_receipt_id_is_canonical_uuid4() -> None:
    rid = vr.generate_receipt_id()
    vr.validate_receipt_id(rid)  # must not raise


@pytest.mark.parametrize(
    "bad",
    [
        "not-a-uuid",
        "12345678-1234-1234-1234-123456789012-extra",
        "../../../etc/passwd",
        "12345678_1234_1234_1234_123456789012",
        "12345678-1234-1234-1234-123456789ABC",  # uppercase rejected
    ],
)
def test_invalid_receipt_id_rejected(bad: str) -> None:
    with pytest.raises(vr.ReceiptError):
        vr.validate_receipt_id(bad)


@pytest.mark.parametrize(
    "value",
    ["2026-09-13T12:00:00Z", "2026-09-13T12:00:00.123Z", "2026-09-13T12:00:00+00:00"],
)
def test_valid_utc_timestamp_accepted(value: str) -> None:
    vr.validate_utc_timestamp(value, field="created_at")


@pytest.mark.parametrize("value", ["2026-09-13", "2026-09-13T12:00:00", "not a timestamp"])
def test_invalid_utc_timestamp_rejected(value: str) -> None:
    with pytest.raises(vr.ReceiptError):
        vr.validate_utc_timestamp(value, field="created_at")


def test_installed_distributions_digest_is_deterministic_and_stable() -> None:
    first = vr.installed_distributions_digest()
    second = vr.installed_distributions_digest()
    assert first == second
    assert len(first) == 64  # sha256 hex


def test_environment_descriptor_never_contains_a_url_or_local_path() -> None:
    descriptor = vr.environment_descriptor(postgresql_version=None)
    serialized = json.dumps(descriptor)
    assert "://" not in serialized
    assert str(Path.home()) not in serialized


def test_dependency_and_config_inputs_sorted_and_hashed(tmp_path: Path) -> None:
    (tmp_path / "a.toml").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.toml").write_text("b = 2\n", encoding="utf-8")
    entries = vr.dependency_and_config_inputs(tmp_path, ["b.toml", "a.toml"])
    assert [e["repo_relative_path"] for e in entries] == ["a.toml", "b.toml"]
    assert all(len(e["sha256"]) == 64 for e in entries)


def _minimal_valid_receipt(**overrides: object) -> dict:
    base = {
        "schema_version": "1",
        "receipt_id": vr.generate_receipt_id(),
        "slice_id": "2026-09-13-workflow-v3-2-activation-66202c2",
        "risk_class": "R",
        "base_sha": "6" * 40,
        "candidate_sha": "c" * 40,
        "gate": "final",
        "created_at": "2026-09-13T12:00:00Z",
        "coordinator": {
            "authoring_checkout_head_at_start": "6" * 40,
            "worktree_initial_snapshot": {"tracked_tree_sha": "x", "untracked_present": False},
            "run_cache_redirect": {
                "pytest_basetemp_redirected": True,
                "ruff_cache_redirected": True,
                "mypy_cache_redirected": True,
                "pycache_redirected": True,
            },
            "worktree_final_snapshot": {"tracked_tree_sha": "x", "untracked_present": False},
            "worktree_removed": True,
            "worktree_leak_check": "no residual .git/worktrees entry, no residual directory",
            "authoring_checkout_head_at_receipt": "6" * 40,
            "authoring_checkout_clean_at_receipt": True,
        },
        "verifier_hash": "d" * 64,
        "checker_hash": "e" * 64,
        "dependency_and_config_inputs": [],
        "environment_descriptor": vr.environment_descriptor(postgresql_version="16.0"),
        "steps": [
            {"name": "ruff format --check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "ruff check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "mypy", "status": "PASS", "duration_seconds": 0.1},
            {"name": "check_repo.py", "status": "PASS", "duration_seconds": 0.1},
            {"name": "git diff --check", "status": "PASS", "duration_seconds": 0.1},
            {
                "name": "disposable test-database URL validation",
                "status": "PASS",
                "duration_seconds": 0.0,
            },
            {
                "name": "test-database reachability preflight",
                "status": "PASS",
                "duration_seconds": 0.1,
            },
            {"name": "full pytest suite", "status": "PASS", "duration_seconds": 100.0},
            {"name": "contract mutation witnesses", "status": "PASS", "duration_seconds": 1.0},
            {"name": "handoff metadata validation", "status": "PASS", "duration_seconds": 0.0},
            {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.1},
        ],
        "full_suite": {"status": "ran", "count": 2323},
        "focused_tests": {"status": "not_run"},
        "mutation_witnesses": {
            "status": "ran",
            "guard_refs": sorted(vr.compute_active_guard_refs()),
            "passed": len(vr.compute_active_guard_refs()),
            "failed": 0,
        },
        "affected_surface": {
            "base_sha": "6" * 40,
            "computed_categories": [],
            "required_contract_families": [],
            "required_guard_refs": [],
            "directly_executed_tests": [],
            "not_applicable_reason": None,
        },
        "migration_matrix": {"triggered": False},
        "cleanup": {"attempted": True, "status": "PASS"},
        "approval_eligible": True,
    }
    base.update(overrides)
    return base


def test_valid_receipt_schema_passes() -> None:
    vr.validate_receipt_schema(_minimal_valid_receipt())


def test_unknown_field_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["typo_field"] = "oops"
    with pytest.raises(vr.ReceiptError, match="unrecognized"):
        vr.validate_receipt_schema(receipt)


def test_missing_field_rejected() -> None:
    receipt = _minimal_valid_receipt()
    del receipt["migration_matrix"]
    with pytest.raises(vr.ReceiptError, match="missing"):
        vr.validate_receipt_schema(receipt)


def test_invalid_gate_rejected() -> None:
    receipt = _minimal_valid_receipt(gate="ultra")
    with pytest.raises(vr.ReceiptError, match="gate must be"):
        vr.validate_receipt_schema(receipt)


def test_invalid_risk_class_rejected() -> None:
    receipt = _minimal_valid_receipt(risk_class="X")
    with pytest.raises(vr.ReceiptError, match="risk_class"):
        vr.validate_receipt_schema(receipt)


def test_malformed_sha_rejected() -> None:
    receipt = _minimal_valid_receipt(base_sha="not-a-sha")
    with pytest.raises(vr.ReceiptError, match="40-hex"):
        vr.validate_receipt_schema(receipt)


def test_non_string_sha_rejected_without_crashing() -> None:
    receipt = _minimal_valid_receipt(candidate_sha=1234567890)
    with pytest.raises(vr.ReceiptError, match="40-hex"):
        vr.validate_receipt_schema(receipt)


def test_numeric_schema_version_rejected() -> None:
    receipt = _minimal_valid_receipt(schema_version=1)
    with pytest.raises(vr.ReceiptError, match="schema_version"):
        vr.validate_receipt_schema(receipt)


def test_unsupported_schema_version_string_rejected() -> None:
    receipt = _minimal_valid_receipt(schema_version="999")
    with pytest.raises(vr.ReceiptError, match="schema_version"):
        vr.validate_receipt_schema(receipt)


def test_numeric_slice_id_rejected() -> None:
    receipt = _minimal_valid_receipt(slice_id=20260913)
    with pytest.raises(vr.ReceiptError, match="slice_id"):
        vr.validate_receipt_schema(receipt)


def test_malformed_slice_id_string_rejected() -> None:
    receipt = _minimal_valid_receipt(slice_id="not-a-valid-slice-id")
    with pytest.raises(vr.ReceiptError, match="slice_id"):
        vr.validate_receipt_schema(receipt)


def test_validate_slice_id_accepts_a_wellformed_value() -> None:
    vr.validate_slice_id("2026-09-13-workflow-v3-2-activation-66202c2")  # must not raise


@pytest.mark.parametrize("bad", [20260913, None, "not-a-valid-slice-id", ""])
def test_validate_slice_id_rejects_bad_values(bad: object) -> None:
    with pytest.raises(vr.ReceiptError):
        vr.validate_slice_id(bad)


def test_malformed_verifier_hash_wrong_length_rejected() -> None:
    receipt = _minimal_valid_receipt(verifier_hash="d" * 63)
    with pytest.raises(vr.ReceiptError, match="verifier_hash"):
        vr.validate_receipt_schema(receipt)


def test_malformed_verifier_hash_uppercase_rejected() -> None:
    receipt = _minimal_valid_receipt(verifier_hash="D" * 64)
    with pytest.raises(vr.ReceiptError, match="verifier_hash"):
        vr.validate_receipt_schema(receipt)


def test_non_string_checker_hash_rejected_without_crashing() -> None:
    receipt = _minimal_valid_receipt(checker_hash=12345)
    with pytest.raises(vr.ReceiptError, match="checker_hash"):
        vr.validate_receipt_schema(receipt)


def test_malformed_dependency_input_hash_rejected() -> None:
    receipt = _minimal_valid_receipt(
        dependency_and_config_inputs=[
            {"repo_relative_path": "backend/pyproject.toml", "sha256": "not-a-hash"}
        ]
    )
    with pytest.raises(vr.ReceiptError, match="sha256"):
        vr.validate_receipt_schema(receipt)


@pytest.mark.parametrize("bad", ["d" * 63, "D" * 64, "not-a-hash", 12345, None])
def test_validate_sha256_hex_rejects_bad_values(bad: object) -> None:
    with pytest.raises(vr.ReceiptError):
        vr.validate_sha256_hex(bad, field="x")


def test_validate_sha256_hex_accepts_a_wellformed_value() -> None:
    vr.validate_sha256_hex("d" * 64, field="x")  # must not raise


def test_write_receipt_atomic_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "sub" / "receipt.json"
    vr.write_receipt_atomic(target, _minimal_valid_receipt())
    assert target.is_file()
    loaded = vr.load_receipt(target)
    assert loaded["gate"] == "final"


def test_write_receipt_atomic_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    vr.write_receipt_atomic(target, _minimal_valid_receipt())
    original_mtime = target.stat().st_mtime_ns
    with pytest.raises(vr.ReceiptError, match="already exists"):
        vr.write_receipt_atomic(target, _minimal_valid_receipt(gate="fast"))
    assert target.stat().st_mtime_ns == original_mtime
    assert vr.load_receipt(target)["gate"] == "final"  # unchanged


def test_write_receipt_atomic_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    vr.write_receipt_atomic(tmp_path / "receipt.json", _minimal_valid_receipt())
    leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".receipt-")]
    assert leftovers == []


def test_load_receipt_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "dup.json"
    path.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(vr.ReceiptError, match="duplicate JSON key"):
        vr.load_receipt(path)


def test_compute_approval_eligible_false_for_fast() -> None:
    receipt = _minimal_valid_receipt(gate="fast")
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_true_for_successful_final() -> None:
    receipt = _minimal_valid_receipt(gate="final")
    assert vr.compute_approval_eligible(receipt) is True


def test_compute_approval_eligible_false_if_snapshots_differ() -> None:
    receipt = _minimal_valid_receipt(gate="final")
    receipt["coordinator"]["worktree_final_snapshot"] = {"tracked_tree_sha": "different"}
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_any_step_failed() -> None:
    receipt = _minimal_valid_receipt(gate="final")
    receipt["steps"].append({"name": "mypy", "status": "FAIL", "duration_seconds": 1.0})
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_cleanup_failed() -> None:
    receipt = _minimal_valid_receipt(gate="final")
    receipt["cleanup"] = {"attempted": True, "status": "FAIL"}
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_for_empty_steps_and_all_groups_not_run() -> None:
    """The reproduced degenerate case: an empty step list with every
    execution group left `not_run` must be rejected outright -- it
    satisfies no positive requirement, regardless of gate or cleanup
    status."""
    receipt = _minimal_valid_receipt(
        gate="final",
        steps=[],
        full_suite={"status": "not_run"},
        focused_tests={"status": "not_run"},
        mutation_witnesses={"status": "not_run"},
    )
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_required_step_name_missing() -> None:
    receipt = _minimal_valid_receipt(gate="final")
    receipt["steps"] = [s for s in receipt["steps"] if s["name"] != "mypy"]
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_full_suite_count_not_positive_int() -> None:
    receipt = _minimal_valid_receipt(gate="final", full_suite={"status": "ran", "count": 0})
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_full_suite_count_is_bool() -> None:
    receipt = _minimal_valid_receipt(gate="final", full_suite={"status": "ran", "count": True})
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_no_witnesses_passed() -> None:
    receipt = _minimal_valid_receipt(
        gate="final",
        mutation_witnesses={"status": "ran", "guard_refs": [], "passed": 0, "failed": 0},
    )
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_any_witness_failed() -> None:
    receipt = _minimal_valid_receipt(
        gate="final",
        mutation_witnesses={"status": "ran", "guard_refs": [], "passed": 33, "failed": 1},
    )
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_only_one_of_the_active_guards_claimed() -> None:
    """The exact required regression (Sol's fifth correction round): a
    schema-valid final receipt claiming only one of the complete active-
    guard inventory must recompute `approval_eligible: false` -- a
    positive count alone (here, 1 passed, 0 failed) is never sufficient."""
    only_one = sorted(vr.compute_active_guard_refs())[:1]
    receipt = _minimal_valid_receipt(
        gate="final",
        mutation_witnesses={
            "status": "ran",
            "guard_refs": only_one,
            "passed": len(only_one),
            "failed": 0,
        },
    )
    vr.validate_receipt_schema(receipt)  # schema-valid despite the incomplete inventory
    assert vr.compute_approval_eligible(receipt) is False


def test_witnesses_match_complete_active_inventory_true_for_the_real_full_set() -> None:
    all_guards = sorted(vr.compute_active_guard_refs())
    data = {
        "mutation_witnesses": {
            "status": "ran",
            "guard_refs": all_guards,
            "passed": len(all_guards),
            "failed": 0,
        }
    }
    assert vr.witnesses_match_complete_active_inventory(data) is True


@pytest.mark.parametrize(
    "witnesses",
    [
        {"status": "not_run"},
        {"status": "ran", "guard_refs": [], "passed": 0, "failed": 0},
        {"status": "ran", "guard_refs": "not-a-list", "passed": 0, "failed": 0},
    ],
)
def test_witnesses_match_complete_active_inventory_false_for_bad_shapes(witnesses: dict) -> None:
    assert vr.witnesses_match_complete_active_inventory({"mutation_witnesses": witnesses}) is False


# ---------------------------------------------------------------------------
# Sol's fourth correction round: gate-aware applicable step matrix
# (findings 2/3) -- omission and NOT_RUN regressions for every
# non-static-check applicable step, and migration-matrix-triggered
# evidence requirements.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "step_name",
    [
        "disposable test-database URL validation",
        "test-database reachability preflight",
        "full pytest suite",
        "contract mutation witnesses",
        "handoff metadata validation",
        "temporary-directory cleanup",
    ],
)
def test_compute_approval_eligible_false_if_non_static_step_omitted(step_name: str) -> None:
    receipt = _minimal_valid_receipt(gate="final")
    receipt["steps"] = [s for s in receipt["steps"] if s["name"] != step_name]
    assert vr.compute_approval_eligible(receipt) is False


@pytest.mark.parametrize(
    "step_name",
    [
        "disposable test-database URL validation",
        "test-database reachability preflight",
        "full pytest suite",
        "contract mutation witnesses",
        "handoff metadata validation",
        "temporary-directory cleanup",
    ],
)
def test_compute_approval_eligible_false_if_non_static_step_not_run(step_name: str) -> None:
    receipt = _minimal_valid_receipt(gate="final")
    for step in receipt["steps"]:
        if step["name"] == step_name:
            step["status"] = "NOT_RUN"
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_applicable_final_step_names_includes_focused_pytest_when_computed() -> None:
    names = vr.compute_applicable_final_step_names(
        focused_tests_computed=True, migration_triggered=False
    )
    assert "focused pytest" in names
    names_without = vr.compute_applicable_final_step_names(
        focused_tests_computed=False, migration_triggered=False
    )
    assert "focused pytest" not in names_without


def test_compute_applicable_final_step_names_includes_migration_matrix_when_triggered() -> None:
    names = vr.compute_applicable_final_step_names(
        focused_tests_computed=False, migration_triggered=True
    )
    assert "migration matrix" in names
    names_without = vr.compute_applicable_final_step_names(
        focused_tests_computed=False, migration_triggered=False
    )
    assert "migration matrix" not in names_without


def test_compute_applicable_docs_step_names_excludes_db_and_suite_steps() -> None:
    names = vr.compute_applicable_docs_step_names()
    assert "disposable test-database URL validation" not in names
    assert "full pytest suite" not in names
    assert "contract mutation witnesses" not in names
    assert "handoff metadata validation" in names
    assert "temporary-directory cleanup" in names


def test_compute_approval_eligible_true_for_successful_docs() -> None:
    receipt = _minimal_valid_receipt(
        gate="docs",
        steps=[
            {"name": "ruff format --check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "ruff check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "mypy", "status": "PASS", "duration_seconds": 0.1},
            {"name": "check_repo.py", "status": "PASS", "duration_seconds": 0.1},
            {"name": "git diff --check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "handoff metadata validation", "status": "PASS", "duration_seconds": 0.0},
            {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.1},
        ],
        full_suite={"status": "not_run"},
        mutation_witnesses={"status": "not_run"},
    )
    assert vr.compute_approval_eligible(receipt) is True


def test_compute_approval_eligible_false_for_docs_missing_handoff_step() -> None:
    receipt = _minimal_valid_receipt(
        gate="docs",
        steps=[
            {"name": "ruff format --check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "ruff check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "mypy", "status": "PASS", "duration_seconds": 0.1},
            {"name": "check_repo.py", "status": "PASS", "duration_seconds": 0.1},
            {"name": "git diff --check", "status": "PASS", "duration_seconds": 0.1},
            {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.1},
        ],
        full_suite={"status": "not_run"},
        mutation_witnesses={"status": "not_run"},
    )
    assert vr.compute_approval_eligible(receipt) is False


def _valid_triggered_migration_matrix() -> dict:
    dev_state = {"alembic_revision": "0011", "schema_fingerprint": "a" * 64}
    return {
        "triggered": True,
        "status": "PASS",
        "dev_state_before": dict(dev_state),
        "dev_state_after": dict(dev_state),
        "postgresql_server_version": "PostgreSQL 16.0",
        "fresh_database_created": True,
        "fresh_database_cleaned_up": True,
        "steps": ["existing-head upgrade"],
    }


def _receipt_with_triggered_migration(**migration_overrides: object) -> dict:
    matrix = _valid_triggered_migration_matrix()
    matrix.update(migration_overrides)
    receipt = _minimal_valid_receipt(gate="final", migration_matrix=matrix)
    receipt["steps"].append({"name": "migration matrix", "status": "PASS", "duration_seconds": 1.0})
    return receipt


def test_compute_approval_eligible_true_for_genuinely_passed_migration_matrix() -> None:
    receipt = _receipt_with_triggered_migration()
    assert vr.compute_approval_eligible(receipt) is True


def test_compute_approval_eligible_false_for_migration_matrix_status_fail() -> None:
    """The exact required regression: a schema-valid `status: FAIL`
    reproduction (triggered, otherwise well-formed) must be rejected."""
    receipt = _receipt_with_triggered_migration(status="FAIL")
    vr.validate_receipt_schema(receipt)  # schema-valid despite status: FAIL
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_migration_dev_state_before_after_differ() -> None:
    receipt = _receipt_with_triggered_migration(
        dev_state_after={"alembic_revision": "0012", "schema_fingerprint": "b" * 64}
    )
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_migration_fresh_database_not_created() -> None:
    receipt = _receipt_with_triggered_migration(fresh_database_created=False)
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_migration_fresh_database_not_cleaned_up() -> None:
    receipt = _receipt_with_triggered_migration(fresh_database_cleaned_up=False)
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_migration_step_missing() -> None:
    matrix = _valid_triggered_migration_matrix()
    receipt = _minimal_valid_receipt(gate="final", migration_matrix=matrix)
    # No "migration matrix" step appended -- omitted entirely.
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_false_if_migration_step_not_run() -> None:
    receipt = _receipt_with_triggered_migration()
    for step in receipt["steps"]:
        if step["name"] == "migration matrix":
            step["status"] = "NOT_RUN"
    assert vr.compute_approval_eligible(receipt) is False


def test_compute_approval_eligible_true_when_migration_not_triggered_is_vacuous() -> None:
    receipt = _minimal_valid_receipt(gate="final", migration_matrix={"triggered": False})
    assert vr.compute_approval_eligible(receipt) is True


# ---------------------------------------------------------------------------
# Recursively closed/typed schema -- unknown-nested-field regressions
# ---------------------------------------------------------------------------


def test_unknown_nested_field_in_coordinator_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["coordinator"]["unexpected_field"] = "surprise"
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_worktree_snapshot_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["coordinator"]["worktree_initial_snapshot"]["extra"] = 1
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_run_cache_redirect_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["coordinator"]["run_cache_redirect"]["extra"] = True
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_step_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["steps"][0]["raw_output"] = "should not be here"
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_full_suite_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["full_suite"]["extra"] = 1
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_mutation_witnesses_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["mutation_witnesses"]["extra"] = 1
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_affected_surface_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["affected_surface"]["extra"] = 1
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_cleanup_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["cleanup"]["extra"] = 1
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_dependency_input_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["dependency_and_config_inputs"] = [
        {"repo_relative_path": "x.toml", "sha256": "a" * 64, "extra": 1}
    ]
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_environment_descriptor_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["environment_descriptor"]["extra"] = 1
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_unknown_nested_field_in_triggered_migration_matrix_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["migration_matrix"] = {"triggered": True, "extra": 1}
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)


def test_duplicate_step_name_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["steps"].append({"name": "mypy", "status": "PASS", "duration_seconds": 0.2})
    with pytest.raises(vr.ReceiptError, match="duplicate step name"):
        vr.validate_receipt_schema(receipt)


def test_full_suite_ran_without_matching_pass_step_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["steps"] = [s for s in receipt["steps"] if s["name"] != "full pytest suite"]
    with pytest.raises(vr.ReceiptError, match="does not appear exactly once"):
        vr.validate_receipt_schema(receipt)


def test_full_suite_ran_with_failed_matching_step_rejected() -> None:
    receipt = _minimal_valid_receipt()
    for step in receipt["steps"]:
        if step["name"] == "full pytest suite":
            step["status"] = "FAIL"
    with pytest.raises(vr.ReceiptError, match="is not PASS"):
        vr.validate_receipt_schema(receipt)


def test_valid_triggered_migration_matrix_passes_schema() -> None:
    receipt = _minimal_valid_receipt()
    receipt["migration_matrix"] = {
        "triggered": True,
        "status": "PASS",
        "dev_state_before": {"alembic_revision": "0017", "schema_fingerprint": "a" * 64},
        "dev_state_after": {"alembic_revision": "0017", "schema_fingerprint": "a" * 64},
        "postgresql_server_version": "PostgreSQL 16.0",
        "fresh_database_created": True,
        "fresh_database_cleaned_up": True,
        "steps": ["existing-head upgrade"],
    }
    vr.validate_receipt_schema(receipt)


def test_triggered_migration_matrix_with_unknown_dev_state_field_rejected() -> None:
    receipt = _minimal_valid_receipt()
    receipt["migration_matrix"] = {
        "triggered": True,
        "status": "PASS",
        "dev_state_before": {
            "alembic_revision": "0017",
            "schema_fingerprint": "a" * 64,
            "extra": 1,
        },
        "dev_state_after": {"alembic_revision": "0017", "schema_fingerprint": "a" * 64},
        "postgresql_server_version": "PostgreSQL 16.0",
        "fresh_database_created": True,
        "fresh_database_cleaned_up": True,
        "steps": ["existing-head upgrade"],
    }
    with pytest.raises(vr.ReceiptError, match="unrecognized field"):
        vr.validate_receipt_schema(receipt)
