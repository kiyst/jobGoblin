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
        ],
        "full_suite": {"status": "ran", "count": 2323},
        "focused_tests": {"status": "not_run"},
        "mutation_witnesses": {"status": "ran", "guard_refs": [], "passed": 34, "failed": 0},
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
