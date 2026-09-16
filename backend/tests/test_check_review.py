"""Genuine (non-mocked) tests: a real disposable Git repository with real
C -> A -> R (and M) commits, validated with real `git` plumbing -- never
a synthetic in-memory chain."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Generator
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


def _real_active_guard_refs() -> list[str]:
    from tests.contracts.taxonomy import active_guards

    return sorted(active_guards().keys())


def _minimal_receipt(
    candidate_sha: str, receipt_id: str, *, gate: str = "final", repo_root: Path
) -> dict:
    from scripts import verification_receipts as vr

    static_steps = [
        {"name": "ruff format --check", "status": "PASS", "duration_seconds": 0.1},
        {"name": "ruff check", "status": "PASS", "duration_seconds": 0.1},
        {"name": "mypy", "status": "PASS", "duration_seconds": 0.1},
        {"name": "check_repo.py", "status": "PASS", "duration_seconds": 0.1},
        {"name": "git diff --check", "status": "PASS", "duration_seconds": 0.1},
    ]
    tail_steps = [
        {"name": "handoff metadata validation", "status": "PASS", "duration_seconds": 0.0},
        {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.1},
    ]
    if gate == "final":
        guard_refs = _real_active_guard_refs()
        steps = [
            *static_steps,
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
            {"name": "full pytest suite", "status": "PASS", "duration_seconds": 1.0},
            {"name": "contract mutation witnesses", "status": "PASS", "duration_seconds": 1.0},
            *tail_steps,
        ]
        full_suite = {"status": "ran", "count": 1}
        mutation_witnesses = {
            "status": "ran",
            "guard_refs": guard_refs,
            "passed": len(guard_refs),
            "failed": 0,
        }
    else:  # docs
        steps = [*static_steps, *tail_steps]
        full_suite = {"status": "not_run"}
        mutation_witnesses = {"status": "not_run"}

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
        "verifier_hash": vr.committed_file_hash(
            candidate_sha, "backend/scripts/verify.py", repo_root=repo_root
        ),
        "checker_hash": vr.committed_file_hash(
            candidate_sha, "backend/scripts/check_handoff.py", repo_root=repo_root
        ),
        "dependency_and_config_inputs": vr.dependency_and_config_inputs(
            candidate_sha, ["backend/pyproject.toml"], repo_root=repo_root
        ),
        "environment_descriptor": vr.environment_descriptor(postgresql_version=None),
        "steps": steps,
        "full_suite": full_suite,
        "focused_tests": {"status": "not_run"},
        "mutation_witnesses": mutation_witnesses,
        "affected_surface": {
            "base_sha": "6" * 40,
            # `_build_c_a_r` always adds `src.txt` (real `verification_scope`
            # category: unmapped) and modifies `docs/LLM_HANDOFF.md` (real
            # category: handoff-transition) between base and candidate --
            # these are the *genuinely* recomputable categories for that
            # diff, cross-checked by `check_review._cross_check_affected_
            # surface` against the real, installed `verification_scope`.
            "computed_categories": ["handoff-transition", "unmapped"],
            "required_contract_families": [],
            "required_guard_refs": [],
            "directly_executed_tests": [],
            "not_applicable_reason": None,
        },
        "migration_matrix": {"triggered": False},
        "cleanup": {"attempted": True, "status": "PASS"},
        "approval_eligible": True,
    }


@pytest.fixture()
def car_repo(monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
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
    (root / "docs" / "LLM_HANDOFF.md").write_text(
        "# handoff\n\n## Iteration 1\n\n### Work done\n\nplaceholder text\n", encoding="utf-8"
    )
    (root / "backend" / "scripts").mkdir(parents=True)
    (root / "backend" / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "scripts" / "check_review.py").write_text(
        "import sys\nprint('WORKTREE-OWN-CHECK-REVIEW-MARKER')\nsys.exit(0)\n", encoding="utf-8"
    )
    # Stand-ins for the two hashed files plus the hashed config file --
    # never executed by these tests, only ever read and sha256'd, by both
    # `_build_c_a_r` (to populate a receipt's verifier_hash/checker_hash/
    # dependency_and_config_inputs with the *real* recomputable value) and
    # `check_review.py`'s own `_cross_check_recorded_hashes`.
    (root / "backend" / "scripts" / "verify.py").write_text(
        "# stand-in verify.py\n", encoding="utf-8"
    )
    (root / "backend" / "scripts" / "check_handoff.py").write_text(
        "# stand-in check_handoff.py\n", encoding="utf-8"
    )
    (root / "backend" / "pyproject.toml").write_text("[tool.example]\nx = 1\n", encoding="utf-8")
    _commit(root, "base")
    # `verification_worktree.py`'s `REPO_ROOT` is fixed at module-import
    # time to the real project root; every worktree-creating call this
    # test file exercises (the detached-checkout launcher tests, and now
    # `check_review.py`'s own hash-recomputation cross-check) must instead
    # target this disposable repo.
    monkeypatch.setattr(cr.vw, "REPO_ROOT", root)
    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def _handoff_header() -> str:
    return "# handoff\n\n## Iteration 1\n\n### Work done\n\nplaceholder text\n\n"


def _pending_block(
    *, slice_id: str, risk_class: str, base_sha: str, gate: str, slice_kind: str = "tooling"
) -> str:
    return (
        "```workflow-metadata\n"
        "workflow_version: v3.2\n"
        "state: pending\n"
        f"slice_id: {slice_id}\n"
        f"slice_kind: {slice_kind}\n"
        f"risk_class: {risk_class}\n"
        f"base_sha: {base_sha}\n"
        f"declared_gate: {gate}\n"
        "```\n"
    )


def _published_block(
    *,
    slice_id: str,
    risk_class: str,
    base_sha: str,
    gate: str,
    candidate_sha: str,
    receipt_id: str,
    slice_kind: str = "tooling",
) -> str:
    return (
        "```workflow-metadata\n"
        "workflow_version: v3.2\n"
        "state: published\n"
        f"slice_id: {slice_id}\n"
        f"slice_kind: {slice_kind}\n"
        f"risk_class: {risk_class}\n"
        f"base_sha: {base_sha}\n"
        f"declared_gate: {gate}\n"
        f"executed_gate: {gate}\n"
        f"candidate_sha: {candidate_sha}\n"
        f"receipt_id: {receipt_id}\n"
        f"receipt_path: docs/verification-receipts/{candidate_sha}/{receipt_id}.json\n"
        "```\n"
    )


def _build_c_a_r(
    repo: Path,
    *,
    verdict: str = "approved",
    findings: str = "none",
    reviewer_model: str = "Sol Medium",
    gate: str = "final",
    risk_class: str = "H",
    slice_kind: str = "tooling",
    extra_files: dict[str, str] | None = None,
    migration_matrix_override: dict | None = None,
    receipt_mutator: Callable[[dict], None] | None = None,
) -> tuple[str, str, str, str]:
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    slice_id = f"2026-09-13-example-{base_sha[:7]}"

    (repo / "docs" / "LLM_HANDOFF.md").write_text(
        _handoff_header()
        + _pending_block(
            slice_id=slice_id,
            risk_class=risk_class,
            base_sha=base_sha,
            gate=gate,
            slice_kind=slice_kind,
        ),
        encoding="utf-8",
    )
    for rel_path, content in (extra_files or {}).items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (repo / "src.txt").write_text("v1\n", encoding="utf-8")
    candidate_sha = _commit(repo, "C: candidate")

    receipt_id = str(uuid.uuid4())
    receipt = _minimal_receipt(candidate_sha, receipt_id, gate=gate, repo_root=repo)
    receipt["slice_id"] = slice_id
    receipt["risk_class"] = risk_class
    receipt["base_sha"] = base_sha
    if migration_matrix_override is not None:
        receipt["migration_matrix"] = migration_matrix_override
        if migration_matrix_override.get("triggered"):
            receipt["steps"].append(
                {
                    "name": "migration matrix",
                    "status": (
                        "PASS" if migration_matrix_override.get("status") == "PASS" else "FAIL"
                    ),
                    "duration_seconds": 1.0,
                }
            )
    if receipt_mutator is not None:
        receipt_mutator(receipt)
    receipt_dir = repo / "docs" / "verification-receipts" / candidate_sha
    receipt_dir.mkdir(parents=True)
    receipt_path = receipt_dir / f"{receipt_id}.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    (repo / "docs" / "LLM_HANDOFF.md").write_text(
        _handoff_header()
        + _published_block(
            slice_id=slice_id,
            risk_class=risk_class,
            base_sha=base_sha,
            gate=gate,
            candidate_sha=candidate_sha,
            receipt_id=receipt_id,
            slice_kind=slice_kind,
        ),
        encoding="utf-8",
    )
    publication_sha = _commit(repo, "A: publish receipt")

    review_block = "\n".join(
        [
            "schema_version: 2",
            f"slice_id: {slice_id}",
            f"risk_class: {risk_class}",
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
    with (repo / "docs" / "LLM_HANDOFF.md").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n### Work review\n\n```workflow-review-metadata\n" + review_block + "\n```\n"
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


def test_primary_review_requires_sol_medium_for_executable_slice_kind_even_at_low_risk(
    car_repo: Path,
) -> None:
    """Sol's second-round finding: the Sol Medium requirement must trigger
    for every executable (parser/tooling) primary approval, not only
    risk_class: H -- proven here with risk_class: D."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, risk_class="D", slice_kind="tooling", reviewer_model="Astra"
    )
    with pytest.raises(cr.ReviewValidationError, match="Sol Medium"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_primary_review_permits_non_sol_medium_for_low_risk_docs_slice(car_repo: Path) -> None:
    """Conversely, a low-risk `docs` slice (never executable) must not be
    forced into the Sol Medium requirement."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, gate="docs", risk_class="D", slice_kind="docs", reviewer_model="Astra"
    )
    fields = cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)
    assert fields["verdict"] == "approved"


def test_docs_gate_requires_published_slice_kind_docs_for_merge_eligibility(
    car_repo: Path,
) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, gate="docs", risk_class="D", slice_kind="tooling", reviewer_model="Sol Medium"
    )
    with pytest.raises(cr.ReviewValidationError, match="slice_kind: docs"):
        cr.check_merge_eligibility(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_docs_gate_merge_eligible_when_slice_kind_genuinely_docs(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, gate="docs", risk_class="D", slice_kind="docs", reviewer_model="Astra"
    )
    fields = cr.check_merge_eligibility(
        candidate_sha, publication_sha, review_sha, repo_root=car_repo
    )
    assert fields["verdict"] == "approved"


def test_cross_check_rejects_published_review_slice_id_mismatch() -> None:
    published_fields = {
        "slice_id": "2026-09-13-example-abc1234",
        "risk_class": "H",
        "candidate_sha": "c" * 40,
        "executed_gate": "final",
        "receipt_id": "11111111-1111-4111-8111-111111111111",
        "receipt_path": "docs/verification-receipts/" + "c" * 40 + "/x.json",
    }
    review_fields = {
        "slice_id": "2026-09-13-different-abc1234",
        "risk_class": "H",
        "candidate_sha": "c" * 40,
        "gate": "final",
        "receipt_id": "11111111-1111-4111-8111-111111111111",
        "receipt_path": "docs/verification-receipts/" + "c" * 40 + "/x.json",
    }
    with pytest.raises(cr.ReviewValidationError, match="slice_id"):
        cr._cross_check_published_and_review_metadata(published_fields, review_fields)


def test_cross_check_rejects_published_review_gate_mismatch() -> None:
    published_fields = {
        "slice_id": "2026-09-13-example-abc1234",
        "risk_class": "H",
        "candidate_sha": "c" * 40,
        "executed_gate": "final",
        "receipt_id": "11111111-1111-4111-8111-111111111111",
        "receipt_path": "docs/verification-receipts/" + "c" * 40 + "/x.json",
    }
    review_fields = dict(published_fields)
    review_fields["gate"] = "fast"
    del review_fields["executed_gate"]
    with pytest.raises(cr.ReviewValidationError, match="gate"):
        cr._cross_check_published_and_review_metadata(published_fields, review_fields)


def test_require_base_sha_ancestor_rejects_an_unrelated_commit(car_repo: Path) -> None:
    candidate_sha, _, _, _ = _build_c_a_r(car_repo)
    with pytest.raises(cr.ReviewValidationError, match="not an ancestor"):
        cr._require_base_sha_ancestor("0" * 40, candidate_sha, repo_root=car_repo)


def test_require_base_sha_ancestor_accepts_a_genuine_ancestor(car_repo: Path) -> None:
    candidate_sha, publication_sha, _, _ = _build_c_a_r(car_repo)
    base_sha = _git(["rev-parse", f"{candidate_sha}^"], car_repo)
    cr._require_base_sha_ancestor(base_sha, candidate_sha, repo_root=car_repo)


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


# ---------------------------------------------------------------------------
# Merge eligibility vs. record validity (Sol's correction 1/2)
# ---------------------------------------------------------------------------


def test_check_merge_eligibility_passes_for_approved_final_receipt(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    fields = cr.check_merge_eligibility(
        candidate_sha, publication_sha, review_sha, repo_root=car_repo
    )
    assert fields["verdict"] == "approved"


def test_check_merge_eligibility_rejects_changes_requested(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, verdict="changes_requested", findings="2026-09-13-example/F001"
    )
    # Record validity still passes (proves the two checks are genuinely distinct).
    cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)
    with pytest.raises(cr.ReviewValidationError, match="not merge-eligible"):
        cr.check_merge_eligibility(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


# ---------------------------------------------------------------------------
# Independent affected-surface/migration-trigger/hash recomputation
# (Sol's third correction round, finding 1)
# ---------------------------------------------------------------------------


def test_migration_trigger_mismatch_rejects_merge_eligibility(car_repo: Path) -> None:
    """The exact required regression: a candidate changes a real migration
    path, but the receipt claims `migration_matrix.triggered: false` --
    merge eligibility (and record validity) must reject it."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo,
        extra_files={"backend/migrations/versions/0001_add_table.py": "# migration\n"},
    )
    with pytest.raises(cr.ReviewValidationError, match="migration trigger"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)
    with pytest.raises(cr.ReviewValidationError, match="migration trigger"):
        cr.check_merge_eligibility(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def _valid_triggered_migration_matrix() -> dict:
    # The development database itself is never migrated by the matrix --
    # only its state is read before/after to prove no side effect -- so a
    # genuinely PASSing matrix always has dev_state_before == dev_state_after
    # (see `migration_matrix.run_full_matrix`, which itself raises otherwise).
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


def test_migration_trigger_matching_true_passes(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo,
        extra_files={"backend/migrations/versions/0001_add_table.py": "# migration\n"},
        migration_matrix_override=_valid_triggered_migration_matrix(),
    )
    fields = cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)
    assert fields["verdict"] == "approved"


def test_affected_surface_category_mismatch_rejected(car_repo: Path) -> None:
    def _mutate(receipt: dict) -> None:
        receipt["affected_surface"]["computed_categories"] = []

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo, receipt_mutator=_mutate)
    with pytest.raises(cr.ReviewValidationError, match="computed_categories"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_focused_selector_missing_required_target_rejected(car_repo: Path) -> None:
    from scripts import verification_scope as scope_mod

    extra_files = {"backend/app/normalization/salary.py": "# salary parser change\n"}
    changed_paths = ["docs/LLM_HANDOFF.md", "src.txt", *extra_files]
    classifications = scope_mod.classify_all(changed_paths)
    coverage = scope_mod.compute_required_coverage(changed_paths)

    def _mutate(receipt: dict) -> None:
        receipt["affected_surface"]["computed_categories"] = sorted(
            {c.category for c in classifications}
        )
        receipt["affected_surface"]["required_contract_families"] = sorted(
            coverage.required_contract_families
        )
        receipt["affected_surface"]["required_guard_refs"] = sorted(coverage.required_guard_refs)
        receipt["affected_surface"]["directly_executed_tests"] = sorted(
            coverage.directly_executed_tests
        )
        receipt["mutation_witnesses"]["guard_refs"] = sorted(coverage.required_guard_refs)
        # `focused_tests` is deliberately left at `not_run` -- real coverage
        # for a parser change requires a focus selector, so this must fail.

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, extra_files=extra_files, receipt_mutator=_mutate
    )
    with pytest.raises(cr.ReviewValidationError, match="focused_tests.selector"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_witness_guard_refs_missing_required_ref_rejected(car_repo: Path) -> None:
    from scripts import verification_scope as scope_mod

    extra_files = {"backend/app/normalization/salary.py": "# salary parser change\n"}
    changed_paths = ["docs/LLM_HANDOFF.md", "src.txt", *extra_files]
    classifications = scope_mod.classify_all(changed_paths)
    coverage = scope_mod.compute_required_coverage(changed_paths)
    computed_focus_targets = {
        target.removeprefix("backend/") for target in coverage.required_focus_targets
    }

    def _mutate(receipt: dict) -> None:
        receipt["affected_surface"]["computed_categories"] = sorted(
            {c.category for c in classifications}
        )
        receipt["affected_surface"]["required_contract_families"] = sorted(
            coverage.required_contract_families
        )
        receipt["affected_surface"]["required_guard_refs"] = sorted(coverage.required_guard_refs)
        receipt["affected_surface"]["directly_executed_tests"] = sorted(
            coverage.directly_executed_tests
        )
        receipt["focused_tests"] = {
            "status": "ran",
            "selector": " ".join(sorted(computed_focus_targets)),
            "count": 1,
        }
        receipt["steps"].append(
            {"name": "focused pytest", "status": "PASS", "duration_seconds": 1.0}
        )
        # Explicitly emptied (the `_minimal_receipt` default for gate:
        # final is now the complete active-guard inventory, which would
        # otherwise trivially satisfy this diff's required subset) --
        # required_guard_refs is non-empty for this diff, so this must be
        # rejected.
        receipt["mutation_witnesses"] = {
            "status": "ran",
            "guard_refs": [],
            "passed": 0,
            "failed": 0,
        }

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, extra_files=extra_files, receipt_mutator=_mutate
    )
    with pytest.raises(cr.ReviewValidationError, match="mutation_witnesses.guard_refs"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_final_gate_witness_inventory_rejects_a_single_claimed_guard(car_repo: Path) -> None:
    """The exact required regression: for gate: final, a receipt claiming
    only one of the complete active-guard inventory must be rejected --
    final always runs (and must record) every currently active guard, not
    merely a subset."""

    def _mutate(receipt: dict) -> None:
        only_one = _real_active_guard_refs()[:1]
        receipt["mutation_witnesses"] = {
            "status": "ran",
            "guard_refs": only_one,
            "passed": len(only_one),
            "failed": 0,
        }

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo, receipt_mutator=_mutate)
    with pytest.raises(
        cr.ReviewValidationError, match="does not equal the complete active-guard inventory"
    ):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_final_gate_witness_inventory_rejects_passed_count_mismatch(car_repo: Path) -> None:
    """Even with the complete guard set claimed, `passed` must equal
    `len(guard_refs)` and `failed` must be zero."""

    def _mutate(receipt: dict) -> None:
        all_guards = _real_active_guard_refs()
        receipt["mutation_witnesses"] = {
            "status": "ran",
            "guard_refs": all_guards,
            "passed": len(all_guards) - 1,
            "failed": 1,
        }

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo, receipt_mutator=_mutate)
    with pytest.raises(cr.ReviewValidationError, match="must equal len\\(guard_refs\\)"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_final_gate_witness_inventory_does_not_apply_to_fast_gate() -> None:
    """`_cross_check_final_gate_witness_inventory` is a no-op for any
    gate other than `final` -- proven directly, since a `fast`-gate
    record legitimately claims only a subset of guards."""
    receipt = {"gate": "fast", "mutation_witnesses": {"status": "ran", "guard_refs": ["only-one"]}}
    cr._cross_check_final_gate_witness_inventory(receipt)  # must not raise


def test_verifier_hash_mismatch_rejected(car_repo: Path) -> None:
    def _mutate(receipt: dict) -> None:
        receipt["verifier_hash"] = "f" * 64

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo, receipt_mutator=_mutate)
    with pytest.raises(cr.ReviewValidationError, match="verifier_hash"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


def test_dependency_and_config_inputs_hash_mismatch_rejected(car_repo: Path) -> None:
    def _mutate(receipt: dict) -> None:
        receipt["dependency_and_config_inputs"] = [
            {"repo_relative_path": "backend/pyproject.toml", "sha256": "f" * 64}
        ]

    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo, receipt_mutator=_mutate)
    with pytest.raises(cr.ReviewValidationError, match="dependency_and_config_inputs"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, review_sha, repo_root=car_repo)


# ---------------------------------------------------------------------------
# C..A / A..R transition-diff fault injection
# ---------------------------------------------------------------------------


def test_c_to_a_rejects_an_unrelated_smuggled_edit(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    _git(["checkout", "-q", publication_sha], car_repo)
    (car_repo / "sneaky.txt").write_text("surprise\n", encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_publication_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="must not change any other path"):
        cr.validate_c_to_a_transition(
            candidate_sha,
            new_publication_sha,
            cr.read_file_at_commit(candidate_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            cr.read_file_at_commit(new_publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


def test_c_to_a_rejects_a_second_smuggled_receipt_file(car_repo: Path) -> None:
    """Two receipt additions in the same C..A transition -- not merely a
    plain single-file addition -- must be rejected, never silently
    accepted as "one of them counts"."""
    candidate_sha, publication_sha, review_sha, receipt_id = _build_c_a_r(car_repo)
    _git(["checkout", "-q", publication_sha], car_repo)
    extra_receipt_dir = car_repo / "docs" / "verification-receipts" / candidate_sha
    (extra_receipt_dir / "extra-receipt.json").write_text('{"a": 1}', encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_publication_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="exactly one receipt file"):
        cr.validate_c_to_a_transition(
            candidate_sha,
            new_publication_sha,
            cr.read_file_at_commit(candidate_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            cr.read_file_at_commit(new_publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


def test_c_to_a_rejects_a_change_outside_the_metadata_block() -> None:
    handoff_at_c = "prose\n\n```workflow-metadata\nstate: pending\n```\n"
    handoff_at_a = "REWRITTEN PROSE\n\n```workflow-metadata\nstate: published\n```\n"
    normalized_c = cr._replace_last_metadata_block(handoff_at_c, "<B>")
    normalized_a = cr._replace_last_metadata_block(handoff_at_a, "<B>")
    assert normalized_c != normalized_a


def test_a_to_r_rejects_a_historical_iteration_rewrite(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_path = car_repo / "docs" / "LLM_HANDOFF.md"
    text = handoff_path.read_text(encoding="utf-8")
    rewritten = text.replace("placeholder text", "REWRITTEN HISTORICAL TEXT")
    handoff_path.write_text(rewritten, encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_review_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="pure append"):
        cr.validate_a_to_r_transition(
            publication_sha,
            new_review_sha,
            cr.read_file_at_commit(publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            cr.read_file_at_commit(new_review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


def test_a_to_r_rejects_an_unrelated_path_change(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    (car_repo / "sneaky2.txt").write_text("surprise\n", encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_review_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="must change only docs/LLM_HANDOFF.md"):
        cr.validate_a_to_r_transition(
            publication_sha,
            new_review_sha,
            cr.read_file_at_commit(publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            cr.read_file_at_commit(new_review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


# ---------------------------------------------------------------------------
# Suffix-scoped review/escalation-block extraction (Sol's seventh
# correction round): review/escalation metadata is extracted and validated
# exclusively from the exact `A..R` appended suffix
# (`handoff_at_r[len(handoff_at_a):]`, as computed and returned by
# `validate_a_to_r_transition`) -- never by searching the whole handoff
# file, and never by searching "the latest '## Iteration N' section
# onward" (that weaker scope was this project's own prior, insufficiently
# precise fix, and is itself replaced here).
# ---------------------------------------------------------------------------


def test_extract_review_metadata_text_rejects_two_blocks_in_the_given_text() -> None:
    handoff_text = (
        "```workflow-review-metadata\nschema_version: 2\n```\n\n"
        "```workflow-review-metadata\nschema_version: 2\n```\n"
    )
    with pytest.raises(cr.ReviewValidationError, match="more than one"):
        cr.extract_review_metadata_text(handoff_text)


def test_extract_review_metadata_text_rejects_no_blocks_in_the_given_text() -> None:
    with pytest.raises(cr.ReviewValidationError, match="no 'workflow-review-metadata'"):
        cr.extract_review_metadata_text("no blocks here\n")


def test_validate_a_to_r_transition_returns_the_exact_appended_suffix(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_at_a = cr.read_file_at_commit(
        publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )
    handoff_at_r = cr.read_file_at_commit(review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo)

    suffix = cr.validate_a_to_r_transition(
        publication_sha, review_sha, handoff_at_a, handoff_at_r, repo_root=car_repo
    )
    assert suffix == handoff_at_r[len(handoff_at_a) :]
    assert handoff_at_a + suffix == handoff_at_r
    # The suffix alone (never the whole file) is enough to extract R's
    # own review metadata.
    review_fields = cr.ch.parse_metadata_fields(cr.extract_review_metadata_text(suffix))
    assert review_fields["candidate_sha"] == candidate_sha


def test_a_to_r_transition_rejects_two_review_blocks_separated_by_a_fake_iteration_heading(
    car_repo: Path,
) -> None:
    """The exact required full-transition regression: a fabricated
    `## Iteration N` heading appended between two review blocks must be
    rejected outright -- proving the appended suffix can never smuggle a
    second, fake iteration (and, with it, an extra review block) past
    this check."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_at_a = cr.read_file_at_commit(
        publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )
    handoff_at_legit_r = cr.read_file_at_commit(
        review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )

    fake_addition = (
        "\n## Iteration 99\n\n"
        "### Work review\n\n"
        "```workflow-review-metadata\n"
        "schema_version: 2\n"
        "slice_id: 2026-09-13-example-abc9999\n"
        "risk_class: H\n"
        "reviewer: Sol\n"
        "reviewer_role: primary\n"
        "reviewer_model: Sol Medium\n"
        "reviewed_at: 2026-09-15T03:00:00Z\n"
        f"candidate_sha: {'9' * 40}\n"
        f"publication_commit_sha: {'8' * 40}\n"
        "receipt_path: docs/verification-receipts/fake/fake.json\n"
        "receipt_id: 44444444-4444-4444-8444-444444444444\n"
        "gate: final\n"
        "verdict: approved\n"
        "findings: none\n"
        "```\n"
    )
    _git(["checkout", "-q", review_sha], car_repo)
    (car_repo / "docs" / "LLM_HANDOFF.md").write_text(
        handoff_at_legit_r + fake_addition, encoding="utf-8"
    )
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "-m", "malicious review extension"], car_repo)
    malicious_review_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="new '## Iteration N' heading"):
        cr.validate_a_to_r_transition(
            publication_sha,
            malicious_review_sha,
            handoff_at_a,
            cr.read_file_at_commit(malicious_review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


def test_a_to_r_transition_rejects_a_hidden_escalation_block_behind_a_fake_iteration_heading(
    car_repo: Path,
) -> None:
    """The analogous proof for escalation content: an escalation block
    hidden behind a fabricated `## Iteration N` heading in the appended
    suffix must be rejected identically -- the same "no new Iteration
    heading" guard protects escalation content exactly as it protects a
    second review block."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_at_a = cr.read_file_at_commit(
        publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )
    handoff_at_legit_r = cr.read_file_at_commit(
        review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )

    fake_addition = (
        "\n## Iteration 99\n\n"
        "### Work review\n\n"
        "```workflow-escalation-metadata\n"
        "schema_version: 2\n"
        "slice_id: 2026-09-13-example-abc9999\n"
        "reviewer: Astra\n"
        "reviewer_model: Astra\n"
        "reviewed_at: 2026-09-15T03:00:00Z\n"
        f"candidate_sha: {'9' * 40}\n"
        "verdict: approved\n"
        "findings: none\n"
        "trigger: disputed_finding\n"
        "```\n"
    )
    _git(["checkout", "-q", review_sha], car_repo)
    (car_repo / "docs" / "LLM_HANDOFF.md").write_text(
        handoff_at_legit_r + fake_addition, encoding="utf-8"
    )
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "-m", "malicious escalation extension"], car_repo)
    malicious_review_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="new '## Iteration N' heading"):
        cr.validate_a_to_r_transition(
            publication_sha,
            malicious_review_sha,
            handoff_at_a,
            cr.read_file_at_commit(malicious_review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


def test_a_to_r_transition_rejects_a_suffix_with_two_work_review_sections(
    car_repo: Path,
) -> None:
    """Even without a fake `## Iteration N` heading, a suffix containing
    two `### Work review` sections must be rejected -- exactly one is
    ever permitted."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_at_a = cr.read_file_at_commit(
        publication_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )
    handoff_at_legit_r = cr.read_file_at_commit(
        review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo
    )
    fake_addition = (
        "\n### Work review\n\n"
        "```workflow-review-metadata\n"
        "schema_version: 2\n"
        "slice_id: 2026-09-13-example-abc9999\n"
        "risk_class: H\n"
        "reviewer: Sol\n"
        "reviewer_role: primary\n"
        "reviewer_model: Sol Medium\n"
        "reviewed_at: 2026-09-15T03:00:00Z\n"
        f"candidate_sha: {'9' * 40}\n"
        f"publication_commit_sha: {'8' * 40}\n"
        "receipt_path: docs/verification-receipts/fake/fake.json\n"
        "receipt_id: 55555555-5555-4555-8555-555555555555\n"
        "gate: final\n"
        "verdict: approved\n"
        "findings: none\n"
        "```\n"
    )
    _git(["checkout", "-q", review_sha], car_repo)
    (car_repo / "docs" / "LLM_HANDOFF.md").write_text(
        handoff_at_legit_r + fake_addition, encoding="utf-8"
    )
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "-m", "malicious second work-review section"], car_repo)
    malicious_review_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="exactly one '### Work review'"):
        cr.validate_a_to_r_transition(
            publication_sha,
            malicious_review_sha,
            handoff_at_a,
            cr.read_file_at_commit(malicious_review_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


# ---------------------------------------------------------------------------
# Escalation blocks
# ---------------------------------------------------------------------------


def test_valid_escalation_block_passes() -> None:
    fields = {
        "schema_version": "2",
        "slice_id": "2026-09-13-example-abc1234",
        "reviewer": "Astra",
        "reviewer_model": "Astra",
        "reviewed_at": "2026-09-13T14:00:00Z",
        "candidate_sha": "c" * 40,
        "verdict": "approved",
        "findings": "none",
        "trigger": "disputed_finding",
    }
    cr.validate_escalation_metadata_structure(fields)


def test_escalation_block_rejects_invalid_trigger() -> None:
    fields = {
        "schema_version": "2",
        "slice_id": "2026-09-13-example-abc1234",
        "reviewer": "Astra",
        "reviewer_model": "Astra",
        "reviewed_at": "2026-09-13T14:00:00Z",
        "candidate_sha": "c" * 40,
        "verdict": "approved",
        "findings": "none",
        "trigger": "just_felt_like_it",
    }
    with pytest.raises(cr.ReviewValidationError, match="'trigger'"):
        cr.validate_escalation_metadata_structure(fields)


def test_escalation_block_rejects_unknown_field() -> None:
    fields = {
        "schema_version": "2",
        "slice_id": "2026-09-13-example-abc1234",
        "reviewer": "Astra",
        "reviewer_model": "Astra",
        "reviewed_at": "2026-09-13T14:00:00Z",
        "candidate_sha": "c" * 40,
        "verdict": "approved",
        "findings": "none",
        "trigger": "disputed_finding",
        "unexpected_field": "surprise",
    }
    with pytest.raises(cr.ReviewValidationError, match="unrecognized"):
        cr.validate_escalation_metadata_structure(fields)


def test_escalation_block_rejects_wrong_schema_version() -> None:
    fields = {
        "schema_version": "1",
        "slice_id": "2026-09-13-example-abc1234",
        "reviewer": "Astra",
        "reviewer_model": "Astra",
        "reviewed_at": "2026-09-13T14:00:00Z",
        "candidate_sha": "c" * 40,
        "verdict": "approved",
        "findings": "none",
        "trigger": "disputed_finding",
    }
    with pytest.raises(cr.ReviewValidationError, match="schema_version"):
        cr.validate_escalation_metadata_structure(fields)


def test_review_metadata_rejects_unknown_field(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_path = car_repo / "docs" / "LLM_HANDOFF.md"
    text = handoff_path.read_text(encoding="utf-8")
    tampered = text.replace(
        "findings: none\n```", "findings: none\nunexpected_field: surprise\n```"
    )
    assert tampered != text
    handoff_path.write_text(tampered, encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_review_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="unrecognized"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, new_review_sha, repo_root=car_repo)


def test_review_metadata_rejects_wrong_schema_version(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    handoff_path = car_repo / "docs" / "LLM_HANDOFF.md"
    text = handoff_path.read_text(encoding="utf-8")
    tampered = text.replace("schema_version: 2\n", "schema_version: 999\n")
    assert tampered != text
    handoff_path.write_text(tampered, encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_review_sha = _git(["rev-parse", "HEAD"], car_repo)
    with pytest.raises(cr.ReviewValidationError, match="schema_version"):
        cr.validate_c_a_r_chain(candidate_sha, publication_sha, new_review_sha, repo_root=car_repo)


def test_escalation_block_never_satisfies_approval_alone(car_repo: Path) -> None:
    """An escalation-only 'approved' block must never make merge eligible
    on its own -- only the primary review block is read for eligibility."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo, verdict="changes_requested", findings="2026-09-13-example/F001"
    )
    handoff_path = car_repo / "docs" / "LLM_HANDOFF.md"
    escalation_block = (
        "\n```workflow-escalation-metadata\n"
        "schema_version: 2\n"
        f"slice_id: 2026-09-13-example-{candidate_sha[:7]}\n"
        "reviewer: Astra\n"
        "reviewer_model: Astra\n"
        "reviewed_at: 2026-09-13T15:00:00Z\n"
        f"candidate_sha: {candidate_sha}\n"
        "verdict: approved\n"
        "findings: none\n"
        "trigger: disputed_finding\n"
        "```\n"
    )
    with handoff_path.open("a", encoding="utf-8") as handle:
        handle.write(escalation_block)
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    new_review_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="not merge-eligible"):
        cr.check_merge_eligibility(
            candidate_sha, publication_sha, new_review_sha, repo_root=car_repo
        )


# ---------------------------------------------------------------------------
# Q validation and full published (post-merge) validation
# ---------------------------------------------------------------------------


def _valid_post_merge_coordinator() -> dict:
    return {
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
        "worktree_leak_check": "ok",
        "authoring_checkout_head_at_receipt": "6" * 40,
        "authoring_checkout_clean_at_receipt": True,
    }


def _build_m_q(
    car_repo: Path,
    review_sha: str,
    base_main_sha: str,
    *,
    slice_id: str = "2026-09-13-example-0000000",
    base_sha: str = "6" * 40,
    candidate_sha: str = "1" * 40,
    publication_commit_sha: str = "2" * 40,
    review_commit_sha: str = "3" * 40,
    original_receipt_id: str = "00000000-0000-0000-0000-000000000000",
    original_receipt_path: str = "docs/verification-receipts/placeholder/placeholder.json",
) -> tuple[str, str]:
    from scripts import verification_receipts as vr

    _git(["checkout", "-q", "-b", "main-line-mq", base_main_sha], car_repo)
    subprocess.run(
        ["git", "merge", "--no-ff", "-m", "M: merge", review_sha],
        cwd=car_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    merge_sha = _git(["rev-parse", "HEAD"], car_repo)

    artifact = {
        "schema_version": "1",
        "kind": "post_merge_verification",
        "slice_id": slice_id,
        "base_sha": base_sha,
        "candidate_sha": candidate_sha,
        "publication_commit_sha": publication_commit_sha,
        "review_commit_sha": review_commit_sha,
        "original_receipt_id": original_receipt_id,
        "original_receipt_path": original_receipt_path,
        "merged_commit": merge_sha,
        "environment_descriptor": vr.environment_descriptor(postgresql_version=None),
        "coordinator": _valid_post_merge_coordinator(),
        "full_suite": {"status": "ran", "count": 1},
        "mutation_witnesses": {
            "status": "ran",
            "guard_refs": sorted(vr.compute_active_guard_refs()),
            "passed": len(vr.compute_active_guard_refs()),
            "failed": 0,
        },
        "migration_matrix": {"triggered": False},
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
            {"name": "full pytest suite", "status": "PASS", "duration_seconds": 1.0},
            {"name": "contract mutation witnesses", "status": "PASS", "duration_seconds": 1.0},
            {"name": "handoff metadata validation", "status": "PASS", "duration_seconds": 0.01},
            {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.1},
        ],
        "cleanup": {"attempted": True, "status": "PASS"},
    }
    artifact_dir = car_repo / "docs" / "post-merge"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "artifact.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "-m", "Q: publish post-merge evidence"], car_repo)
    q_sha = _git(["rev-parse", "HEAD"], car_repo)
    return merge_sha, q_sha


def test_validate_q_passes_for_a_well_formed_artifact(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, receipt_id = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact = cr.validate_q(merge_sha, q_sha, repo_root=car_repo)
    assert artifact["merged_commit"] == merge_sha


def test_validate_q_rejects_wrong_parent(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)
    with pytest.raises(cr.ReviewValidationError, match="exactly one parent"):
        cr.validate_q("0" * 40, q_sha, repo_root=car_repo)


def test_validate_published_end_to_end(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, receipt_id = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    slice_id = f"2026-09-13-example-{base_main_sha[:7]}"
    receipt_path = f"docs/verification-receipts/{candidate_sha}/{receipt_id}.json"

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["slice_id"] = slice_id
    artifact["base_sha"] = base_main_sha
    artifact["candidate_sha"] = candidate_sha
    artifact["publication_commit_sha"] = publication_sha
    artifact["review_commit_sha"] = review_sha
    artifact["original_receipt_id"] = receipt_id
    artifact["original_receipt_path"] = receipt_path
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    result = cr.validate_published(
        candidate_sha,
        publication_sha,
        review_sha,
        merge_sha,
        fixed_q_sha,
        base_main_sha,
        repo_root=car_repo,
    )
    assert result["merged_commit"] == merge_sha


@pytest.mark.parametrize(
    "omitted_step_name",
    [
        "ruff format --check",
        "mypy",
        "check_repo.py",
        "git diff --check",
        "disposable test-database URL validation",
        "test-database reachability preflight",
        "full pytest suite",
        "contract mutation witnesses",
        "handoff metadata validation",
        "temporary-directory cleanup",
    ],
)
def test_validate_q_rejects_artifact_omitting_a_required_static_check_step(
    car_repo: Path, omitted_step_name: str
) -> None:
    """The exact required regression: a Q artifact omitting Ruff format,
    mypy, check_repo, or git diff --check must be rejected -- and, per
    Sol's fourth correction round, the same holds for every other
    applicable non-static step (DB URL safety, DB reachability, full
    suite, all witnesses, handoff validation, temporary-directory
    cleanup)."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["steps"] = [s for s in artifact["steps"] if s["name"] != omitted_step_name]
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match=re.escape(omitted_step_name)):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


@pytest.mark.parametrize(
    "not_run_step_name",
    [
        "ruff format --check",
        "ruff check",
        "mypy",
        "check_repo.py",
        "git diff --check",
        "disposable test-database URL validation",
        "test-database reachability preflight",
        "full pytest suite",
        "contract mutation witnesses",
        "handoff metadata validation",
        "temporary-directory cleanup",
    ],
)
def test_validate_q_rejects_artifact_marking_a_required_step_not_run(
    car_repo: Path, not_run_step_name: str
) -> None:
    """The exact required regression: a Q artifact marking one of the
    required static checks NOT_RUN must be rejected, identically to an
    omission -- and, per Sol's fourth correction round, the same holds
    for every other applicable non-static step."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    for step in artifact["steps"]:
        if step["name"] == not_run_step_name:
            step["status"] = "NOT_RUN"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="is not PASS"):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_validate_q_rejects_artifact_with_a_duplicate_required_step(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["steps"].append({"name": "mypy", "status": "PASS", "duration_seconds": 0.2})
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="duplicate step name"):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_validate_published_rejects_migration_trigger_mismatch(car_repo: Path) -> None:
    """`validate_published` independently re-derives whether migration
    evidence is required for the original slice diff -- a post-merge
    artifact claiming `migration_matrix.triggered: false` when the slice
    genuinely changed a migration path must be rejected."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(
        car_repo,
        extra_files={"backend/migrations/versions/0001_add_table.py": "# migration\n"},
        # The receipt's own migration evidence must be correct (matching
        # the real diff), so `validate_c_a_r_chain`'s own recomputation
        # passes cleanly -- isolating this test to the *artifact's*
        # migration_matrix, which is deliberately left wrong below.
        migration_matrix_override=_valid_triggered_migration_matrix(),
    )
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    slice_id = f"2026-09-13-example-{base_main_sha[:7]}"
    receipt_path = next((car_repo / "docs" / "verification-receipts").glob("*/*.json"))
    receipt_id = receipt_path.stem

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["slice_id"] = slice_id
    artifact["base_sha"] = base_main_sha
    artifact["candidate_sha"] = candidate_sha
    artifact["publication_commit_sha"] = publication_sha
    artifact["review_commit_sha"] = review_sha
    artifact["original_receipt_id"] = receipt_id
    artifact["original_receipt_path"] = (
        f"docs/verification-receipts/{candidate_sha}/{receipt_id}.json"
    )
    # migration_matrix stays at the fixture default {"triggered": False},
    # which is wrong for this diff -- must be rejected.
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="migration trigger"):
        cr.validate_published(
            candidate_sha,
            publication_sha,
            review_sha,
            merge_sha,
            fixed_q_sha,
            base_main_sha,
            repo_root=car_repo,
        )


def test_validate_q_rejects_artifact_with_a_failed_step(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    # Every step name in the default fixture is now part of the required
    # applicable-step set -- add an extra, non-required step and fail
    # *that* one, so this exercises the generic FAIL-anywhere check
    # specifically, not the more specific required-step-must-be-PASS or
    # summary-binding checks (each covered by their own tests).
    artifact["steps"].append(
        {"name": "extra diagnostic step", "status": "FAIL", "duration_seconds": 0.1}
    )
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="FAILed step"):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_validate_q_rejects_artifact_whose_full_suite_did_not_genuinely_run(
    car_repo: Path,
) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["full_suite"] = {"status": "not_run"}
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="full suite did not genuinely run"):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_validate_q_rejects_artifact_claiming_only_one_of_the_active_guards(
    car_repo: Path,
) -> None:
    """The exact required regression (Sol's fifth correction round): a
    schema-valid post-merge artifact claiming only one of the complete
    active-guard inventory must be rejected -- post-merge is inherently
    full/final-equivalent, so a positive count alone is never enough."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    only_one = _real_active_guard_refs()[:1]
    artifact["mutation_witnesses"] = {
        "status": "ran",
        "guard_refs": only_one,
        "passed": len(only_one),
        "failed": 0,
    }
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(
        cr.ReviewValidationError, match="does not equal the complete active-guard inventory"
    ):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_validate_q_rejects_artifact_with_unknown_coordinator_field(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["coordinator"]["extra"] = 1
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="unrecognized field"):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_validate_q_rejects_a_triggered_migration_matrix_that_did_not_pass(
    car_repo: Path,
) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    artifact_path = car_repo / "docs" / "post-merge" / "artifact.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["migration_matrix"] = {
        "triggered": True,
        "status": "FAIL",
        "dev_state_before": {"alembic_revision": "0017", "schema_fingerprint": "a" * 64},
        "dev_state_after": {"alembic_revision": "0017", "schema_fingerprint": "a" * 64},
        "postgresql_server_version": "PostgreSQL 16.0",
        "fresh_database_created": True,
        "fresh_database_cleaned_up": True,
        "steps": ["existing-head upgrade"],
    }
    # The "migration matrix" step itself is present and PASS (so the
    # required-step-presence check does not fire first) -- this isolates
    # the test to `_migration_matrix_genuinely_passed`'s own status check,
    # which must never trust a mismatched, more-detailed status: FAIL.
    artifact["steps"].append(
        {"name": "migration matrix", "status": "PASS", "duration_seconds": 1.0}
    )
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="migration matrix was triggered"):
        cr.validate_q(merge_sha, fixed_q_sha, repo_root=car_repo)


def test_m_to_q_transition_rejects_a_historical_rewrite(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)

    handoff_path = car_repo / "docs" / "LLM_HANDOFF.md"
    text = handoff_path.read_text(encoding="utf-8")
    handoff_path.write_text(text.replace("placeholder text", "REWRITTEN"), encoding="utf-8")
    _git(["add", "-A"], car_repo)
    _git(["commit", "-q", "--amend", "--no-edit"], car_repo)
    fixed_q_sha = _git(["rev-parse", "HEAD"], car_repo)

    with pytest.raises(cr.ReviewValidationError, match="pure append"):
        cr.validate_m_to_q_transition(
            merge_sha,
            fixed_q_sha,
            cr.read_file_at_commit(merge_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            cr.read_file_at_commit(fixed_q_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo),
            repo_root=car_repo,
        )


def test_m_to_q_transition_permits_no_handoff_change_at_all(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)
    handoff_text = cr.read_file_at_commit(merge_sha, "docs/LLM_HANDOFF.md", repo_root=car_repo)
    cr.validate_m_to_q_transition(merge_sha, q_sha, handoff_text, handoff_text, repo_root=car_repo)


def test_validate_published_rejects_artifact_with_wrong_chain_references(car_repo: Path) -> None:
    candidate_sha, publication_sha, review_sha, receipt_id = _build_c_a_r(car_repo)
    base_main_sha = _git(["rev-parse", "HEAD~3"], car_repo)
    merge_sha, q_sha = _build_m_q(car_repo, review_sha, base_main_sha)
    with pytest.raises(
        cr.ReviewValidationError, match="do not match the independently recomputed chain"
    ):
        cr.validate_published(
            candidate_sha,
            publication_sha,
            review_sha,
            merge_sha,
            q_sha,
            base_main_sha,
            repo_root=car_repo,
        )


# ---------------------------------------------------------------------------
# Outer detached-checkout launcher (genuine subprocess re-execution)
# ---------------------------------------------------------------------------


def test_run_via_detached_checkout_executes_the_target_commits_own_code(
    car_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves the *real* precedence at stake: this project ships as an
    editable install (`backend/scripts/` importable from anywhere via a
    `.pth` file), so `cwd`-based resolution alone is not self-evidently
    enough -- confirmed here by giving the disposable repo its own
    colliding `backend/scripts/check_review.py` stand-in (a distinct
    marker string) and proving the *worktree's* copy actually ran, not
    the real project's installed copy."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    monkeypatch.setattr(cr.vw, "REPO_ROOT", car_repo)
    proc = cr.run_via_detached_checkout(
        review_sha,
        "single",
        ["--candidate", candidate_sha, "--publication", publication_sha, "--review", review_sha],
        repo_root=car_repo,
    )
    assert "WORKTREE-OWN-CHECK-REVIEW-MARKER" in proc.stdout
    worktree_list = subprocess.run(
        ["git", "worktree", "list"], cwd=car_repo, check=True, capture_output=True, text=True
    ).stdout
    assert len(worktree_list.strip().splitlines()) == 1


def test_run_via_detached_checkout_fails_closed_when_worktree_teardown_fails(
    car_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree-removal failure must be raised, never silently
    swallowed -- and the caller must be able to trust that a raised
    exception means cleanup was surfaced, not silently partial."""
    candidate_sha, publication_sha, review_sha, _ = _build_c_a_r(car_repo)
    monkeypatch.setattr(cr.vw, "REPO_ROOT", car_repo)

    def _fail_remove(worktree_path: Path) -> None:
        raise cr.vw.WorktreeError("simulated worktree teardown failure")

    monkeypatch.setattr(cr.vw, "remove_worktree", _fail_remove)

    with pytest.raises(cr.ReviewValidationError, match="cleanup failed"):
        cr.run_via_detached_checkout(
            review_sha,
            "single",
            [
                "--candidate",
                candidate_sha,
                "--publication",
                publication_sha,
                "--review",
                review_sha,
            ],
            repo_root=car_repo,
        )
