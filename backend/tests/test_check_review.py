"""Genuine (non-mocked) tests: a real disposable Git repository with real
C -> A -> R (and M) commits, validated with real `git` plumbing -- never
a synthetic in-memory chain."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest

from scripts import check_review as cr

_HANDOFF_PATH = "docs/LLM_HANDOFF.md"


def _git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", message], repo)
    return _git(["rev-parse", "HEAD"], repo)


def _minimal_receipt(candidate_sha: str, receipt_id: str, *, gate: str = "final") -> dict:
    from scripts import verification_receipts as vr

    return {
        "schema_version": "1",
        "receipt_id": receipt_id,
        "slice_id": f"2026-09-13-example-{candidate_sha[:7]}",
        "risk_class": "H",
        "base_sha": "6" * 40,
        "candidate_sha": candidate_sha,
        "gate": gate,
        "created_at": "2026-09-13T12:00:00Z",
        "coordinator": {
            "authoring_checkout_head_at_start": candidate_sha,
            "worktree_initial_snapshot": {"tracked_tree_sha": "x", "untracked_present": False},
            "run_cache_redirect": {
                "pytest_basetemp_redirected": True,
                "ruff_cache_redirected": True,
                "mypy_cache_redirected": True,
                "pycache_redirected": True,
            },
            "worktree_final_snapshot": {"tracked_tree_sha": "x", "untracked_present": False},
            "worktree_removed": True,
            "worktree_leak_check": "ok",
            "authoring_checkout_head_at_receipt": candidate_sha,
            "authoring_checkout_clean_at_receipt": True,
        },
        "verifier_hash": "d" * 64,
        "checker_hash": "e" * 64,
        "dependency_and_config_inputs": [],
        "environment_descriptor": vr.environment_descriptor(postgresql_version=None),
        "steps": [{"name": "x", "status": "PASS", "duration_seconds": 0.1}],
        "full_suite": {"status": "ran", "count": 1},
        "focused_tests": {"status": "not_run"},
        "mutation_witnesses": {"status": "ran", "guard_refs": [], "passed": 0, "failed": 0},
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
        "approval_eligible": gate == "final",
    }


@pytest.fixture()
def car_repo() -> Generator[Path, None, None]:
    # Short-root temp dir, not pytest's own nested `tmp_path`: receipt paths
    # here embed a 40-hex SHA and a 36-char UUID, which combined with
    # `verify.py`'s own basetemp redirection when this suite runs *through*
    # `scripts/verify.py` can otherwise exceed Windows' ~260-char path limit.
    root = Path(tempfile.mkdtemp(prefix="wfv32cr-")) / "repo"
    root.mkdir(parents=True)
    _git(["init", "-q"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / "docs").mkdir()
    (root / "docs" / "LLM_HANDOFF.md").write_text("initial\n", encoding="utf-8")
    _commit(root, "base")
    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def _build_c_a_r(
    repo: Path,
    *,
    verdict: str = "approved",
    findings: str = "none",
    reviewer_model: str = "Sol Medium",
    gate: str = "final",
) -> tuple[str, str, str, str]:
    (repo / "src.txt").write_text("v1\n", encoding="utf-8")
    candidate_sha = _commit(repo, "C: candidate")

    receipt_id = str(uuid.uuid4())
    receipt = _minimal_receipt(candidate_sha, receipt_id, gate=gate)
    receipt_dir = repo / "docs" / "verification-receipts" / candidate_sha
    receipt_dir.mkdir(parents=True)
    receipt_path = receipt_dir / f"{receipt_id}.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    publication_sha = _commit(repo, "A: publish receipt")

    review_block = "\n".join(
        [
            "schema_version: 2",
            f"slice_id: {receipt['slice_id']}",
            f"risk_class: {receipt['risk_class']}",
            "reviewer: Codex",
            "reviewer_role: primary",
            f"reviewer_model: {reviewer_model}",
            "reviewed_at: 2026-09-13T13:00:00Z",
            f"candidate_sha: {candidate_sha}",
            f"publication_commit_sha: {publication_sha}",
            f"receipt_path: docs/verification-receipts/{candidate_sha}/{receipt_id}.json",
            f"receipt_id: {receipt_id}",
            f"gate: {gate}",
            f"verdict: {verdict}",
            f"findings: {findings}",
        ]
    )
    (repo / "docs" / "LLM_HANDOFF.md").write_text(
        "initial\n\n```workflow-review-metadata\n" + review_block + "\n```\n", encoding="utf-8"
    )
    review_sha = _commit(repo, "R: review")
    return candidate_sha, publication_sha, review_sha, receipt_id


def test_valid_chain_passes_and_returns_review_fields(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    fields = cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)
    assert fields["verdict"] == "approved"


def test_a_must_be_direct_child_of_c(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    # Insert an extra commit between C and A conceptually by pointing at a
    # wrong candidate_sha (the real parent chain no longer matches).
    (car_repo / "extra.txt").write_text("x\n", encoding="utf-8")
    wrong_candidate = _commit(car_repo, "not actually C")
    with pytest.raises(cr.ReviewValidationError, match="exactly one parent"):
        cr.require_single_parent_chain(
            wrong_candidate, publication_sha, review_sha, repo_root=car_repo
        )


def test_review_verdict_approved_requires_findings_none(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, verdict="approved", findings="2026-09-13-example/F001"
    )
    with pytest.raises(cr.ReviewValidationError, match="findings: none"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_review_verdict_changes_requested_requires_a_finding(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, verdict="changes_requested", findings="none"
    )
    with pytest.raises(cr.ReviewValidationError, match="at least one"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_class_h_primary_review_requires_sol_medium(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo, reviewer_model="Astra")
    with pytest.raises(cr.ReviewValidationError, match="Sol Medium"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_single_review_can_validate_even_with_changes_requested(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, verdict="changes_requested", findings="2026-09-13-example/F001"
    )
    fields = cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)
    assert fields["verdict"] == "changes_requested"


def test_approved_verdict_rejected_if_receipt_not_approval_eligible(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, verdict="approved", findings="none", gate="fast"
    )
    with pytest.raises(cr.ReviewValidationError, match="approval_eligible is false"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_validate_merge_accepts_clean_ff_merge(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)  # the pre-slice base commit
    _git(["checkout", "-q", "-b", "main-line", base_main_sha], car_repo)
    merge_sha_output = subprocess.run(
        ["git", "merge", "--no-ff", "-m", "M: merge", review_sha],
        cwd=car_repo,
        capture_output=True,
        text=True,
    )
    assert merge_sha_output.returncode == 0, merge_sha_output.stderr
    merge_sha = _git(["rev-parse", "HEAD"], car_repo)
    cr.validate_merge(review_sha, merge_sha, base_main_sha, repo_root=car_repo)


def test_validate_merge_rejects_wrong_first_parent(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    _git(["checkout", "-q", "-b", "main-line-2", base_main_sha], car_repo)
    subprocess.run(
        ["git", "merge", "--no-ff", "-m", "M: merge", review_sha],
        cwd=car_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    merge_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="first parent"):
        cr.validate_merge(review_sha, merge_sha, "0" * 40, repo_root=car_repo)
