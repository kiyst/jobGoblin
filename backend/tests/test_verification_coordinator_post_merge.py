"""Genuine end-to-end tests for `verification_coordinator.run_post_merge_
verification` (Workflow v3.2's post-merge `Q` evidence producer) and its
cleanup-prefix scoping: a real disposable Git repository, a real `git
worktree`, a real executable stand-in `scripts/verify.py`, and a real
atomic artifact write to disk -- never a mocked git/subprocess layer, and
never a hand-typed chain standing in for one that was never actually
built. Complements `test_verification_coordinator.py` (the receipt-
eligible `A` producer) and `test_check_review.py` (the pure chain-
validation logic) with the post-merge `M -> Q` side specifically."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Generator
from pathlib import Path

import pytest

from scripts import check_review as cr
from scripts import verification_coordinator as coord
from scripts import verification_receipts as vr
from scripts import verification_scope as vs

_STAND_IN_VERIFY_PY = """
import argparse
import json
import os
import sys

def _discover_active_guards():
    # See test_verification_coordinator.py's own stand-in for why this
    # falls back to an empty inventory on ImportError -- a disposable
    # test repo's own package layout can shadow the real project's
    # .pth-installed `tests` package for this subprocess.
    try:
        from tests.contracts.taxonomy import active_guards
        return sorted(active_guards().keys())
    except ImportError:
        return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", required=True)
    parser.add_argument("--gate", default=None)
    parser.add_argument("--focus", nargs="+", default=None)
    parser.add_argument("--witness", nargs="+", default=None)
    parser.add_argument("--docs-only", action="store_true")
    parser.add_argument("--migration-required", action="store_true")
    parser.add_argument("--emit-step-json", default=None)
    args = parser.parse_args()

    fail = os.environ.get("STAND_IN_VERIFY_FAIL") == "1"
    drop_step = os.environ.get("STAND_IN_VERIFY_DROP_STEP")
    guard_refs = _discover_active_guards()

    steps = [
        {"name": "ruff format --check", "status": "PASS", "duration_seconds": 0.01},
        {"name": "ruff check", "status": "PASS", "duration_seconds": 0.01},
        {"name": "mypy", "status": "PASS", "duration_seconds": 0.01},
        {"name": "check_repo.py", "status": "PASS", "duration_seconds": 0.01},
        {"name": "git diff --check", "status": "PASS", "duration_seconds": 0.01},
        {
            "name": "disposable test-database URL validation",
            "status": "PASS",
            "duration_seconds": 0.0,
        },
        {
            "name": "test-database reachability preflight",
            "status": "PASS",
            "duration_seconds": 0.01,
        },
        {
            "name": "full pytest suite",
            "status": "FAIL" if fail else "PASS",
            "duration_seconds": 0.02,
        },
        {"name": "contract mutation witnesses", "status": "PASS", "duration_seconds": 0.02},
        {"name": "handoff metadata validation", "status": "PASS", "duration_seconds": 0.0},
        {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.01},
    ]
    if drop_step:
        # Simulates a verify.py that mis-reports `all_passed: True` while
        # silently omitting a required step -- proves the coordinator's
        # own self-validation (schema/evidence check), not just its
        # returncode/all_passed gate, blocks artifact emission.
        steps = [s for s in steps if s["name"] != drop_step]
    migration_matrix = {"triggered": False}
    if args.migration_required:
        steps.append({"name": "migration matrix", "status": "PASS", "duration_seconds": 0.5})
        migration_matrix = {
            "triggered": True,
            "status": "PASS",
            "dev_state_before": {"alembic_revision": None, "schema_fingerprint": "x"},
            "dev_state_after": {"alembic_revision": None, "schema_fingerprint": "x"},
            "postgresql_server_version": "16.0",
            "fresh_database_created": True,
            "fresh_database_cleaned_up": True,
            "steps": ["alembic upgrade head"],
        }

    payload = {
        "steps": steps,
        "full_suite": {"status": "ran", "count": 7},
        "mutation_witnesses": {
            "status": "ran",
            "guard_refs": guard_refs,
            "passed": len(guard_refs),
            "failed": 0,
        },
        "migration_matrix": migration_matrix,
        "all_passed": not fail,
    }
    if args.emit_step_json:
        with open(args.emit_step_json, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _rev_parse(cwd: Path, rev: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", rev], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _verify_tmp_is_clean(repo: Path) -> bool:
    """`COORDINATOR_RUN_ROOT` (`.verify-tmp`) is created once and never
    removed itself -- only each run's own subdirectory is. A rejection
    before that directory is ever created (e.g. a stage-1 chain-
    validation failure) leaves it absent entirely; a rejection after
    (e.g. a failed verification run) leaves it present but empty. Both
    are "clean"; only a leftover run subdirectory is not."""
    verify_tmp = repo / "backend" / ".verify-tmp"
    return not verify_tmp.exists() or not any(verify_tmp.iterdir())


def _commit(cwd: Path, message: str) -> str:
    _git(["add", "-A"], cwd)
    _git(["commit", "-q", "-m", message], cwd)
    return _rev_parse(cwd, "HEAD")


def _real_active_guard_refs() -> list[str]:
    from tests.contracts.taxonomy import active_guards

    return sorted(active_guards().keys())


def _handoff_header() -> str:
    return "# handoff\n\n## Iteration 1\n\n### Work done\n\nplaceholder text\n\n"


def _pending_block(*, slice_id: str, base_sha: str) -> str:
    return (
        "```workflow-metadata\n"
        "workflow_version: v3.2\n"
        "state: pending\n"
        f"slice_id: {slice_id}\n"
        "slice_kind: tooling\n"
        "risk_class: H\n"
        f"base_sha: {base_sha}\n"
        "declared_gate: final\n"
        "```\n"
    )


def _published_block(*, slice_id: str, base_sha: str, candidate_sha: str, receipt_id: str) -> str:
    return (
        "```workflow-metadata\n"
        "workflow_version: v3.2\n"
        "state: published\n"
        f"slice_id: {slice_id}\n"
        "slice_kind: tooling\n"
        "risk_class: H\n"
        f"base_sha: {base_sha}\n"
        "declared_gate: final\n"
        "executed_gate: final\n"
        f"candidate_sha: {candidate_sha}\n"
        f"receipt_id: {receipt_id}\n"
        f"receipt_path: docs/verification-receipts/{candidate_sha}/{receipt_id}.json\n"
        "```\n"
    )


def _minimal_receipt(candidate_sha: str, receipt_id: str, *, repo_root: Path) -> dict:
    guard_refs = _real_active_guard_refs()
    return {
        "schema_version": "1",
        "receipt_id": receipt_id,
        "slice_id": "placeholder",
        "risk_class": "H",
        "base_sha": "placeholder",
        "candidate_sha": candidate_sha,
        "gate": "final",
        "created_at": "2026-09-18T00:00:00Z",
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
        "steps": [
            {"name": "ruff format --check", "status": "PASS", "duration_seconds": 0.01},
            {"name": "ruff check", "status": "PASS", "duration_seconds": 0.01},
            {"name": "mypy", "status": "PASS", "duration_seconds": 0.01},
            {"name": "check_repo.py", "status": "PASS", "duration_seconds": 0.01},
            {"name": "git diff --check", "status": "PASS", "duration_seconds": 0.01},
            {
                "name": "disposable test-database URL validation",
                "status": "PASS",
                "duration_seconds": 0.0,
            },
            {
                "name": "test-database reachability preflight",
                "status": "PASS",
                "duration_seconds": 0.01,
            },
            {"name": "full pytest suite", "status": "PASS", "duration_seconds": 0.02},
            {"name": "contract mutation witnesses", "status": "PASS", "duration_seconds": 0.02},
            {"name": "handoff metadata validation", "status": "PASS", "duration_seconds": 0.0},
            {"name": "temporary-directory cleanup", "status": "PASS", "duration_seconds": 0.01},
        ],
        "full_suite": {"status": "ran", "count": 7},
        "focused_tests": {"status": "not_run"},
        "mutation_witnesses": {
            "status": "ran",
            "guard_refs": guard_refs,
            "passed": len(guard_refs),
            "failed": 0,
        },
        "affected_surface": {
            "base_sha": "placeholder",
            "computed_categories": ["unmapped"],
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
def post_merge_repo(monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    # Short-root temp dir -- see the sibling fixtures' own comments: nested
    # worktree/receipt/artifact paths embedding 40-hex SHAs and UUIDs can
    # otherwise exceed Windows' ~260-character path limit.
    root = Path(tempfile.mkdtemp(prefix="wfv32pm-")) / "repo"
    root.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "Test"], root)
    (root / ".gitignore").write_text("backend/.verify-tmp/\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "LLM_HANDOFF.md").write_text(
        "# handoff\n\n## Iteration 1\n\n### Work done\n\nplaceholder text\n", encoding="utf-8"
    )
    (root / "backend" / "scripts").mkdir(parents=True)
    (root / "backend" / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "scripts" / "verify.py").write_text(_STAND_IN_VERIFY_PY, encoding="utf-8")
    (root / "backend" / "scripts" / "check_handoff.py").write_text(
        "# stand-in check_handoff.py\n", encoding="utf-8"
    )
    (root / "backend" / "pyproject.toml").write_text("[tool.example]\nx = 1\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "base"], root)

    # A real `origin` remote at exactly the base commit -- required for the
    # release-sequence guard (`confirm_main_unchanged`) tests; harmless for
    # every other test, which never touches it.
    origin_bare = root.parent / "origin.git"
    _git(["init", "-q", "--bare", "-b", "main", str(origin_bare)], root)
    _git(["remote", "add", "origin", str(origin_bare)], root)
    _git(["push", "-q", "origin", "main"], root)

    monkeypatch.setattr(coord, "REPO_ROOT", root)
    monkeypatch.setattr(coord, "BACKEND_DIR", root / "backend")
    monkeypatch.setattr(coord, "COORDINATOR_RUN_ROOT", root / "backend" / ".verify-tmp")
    monkeypatch.setattr(coord.vw, "REPO_ROOT", root)

    try:
        yield root
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def _build_chain(
    repo: Path,
    *,
    extra_files: dict[str, str] | None = None,
    receipt_mutator: Callable[[dict], None] | None = None,
) -> dict[str, str]:
    """Builds a genuine `C -> A -> R` sequence on a `feature` branch cut
    from `main`'s current tip (`base_sha`), then merges `feature` back
    into `main` via a real `git merge --no-ff` -- so `M`'s first parent is
    genuinely `base_sha` and its second parent is genuinely `R`, exactly
    the shape `check_review.validate_merge` requires. Returns every SHA a
    caller could need, keyed by name."""
    base_sha = _rev_parse(repo, "HEAD")
    slice_id = f"2026-09-18-example-{base_sha[:7]}"

    _git(["checkout", "-q", "-b", "feature"], repo)

    (repo / "docs" / "LLM_HANDOFF.md").write_text(
        _handoff_header() + _pending_block(slice_id=slice_id, base_sha=base_sha),
        encoding="utf-8",
    )
    for rel_path, content in (extra_files or {}).items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    candidate_sha = _commit(repo, "C: candidate")

    # `check_review._cross_check_affected_surface` independently
    # recomputes `base_sha..candidate_sha` categories via the real,
    # installed `verification_scope` module and rejects any receipt that
    # merely asserts a convenient scope -- so the receipt must carry the
    # genuinely recomputed categories, never a hardcoded placeholder.
    changed_paths = subprocess.run(
        ["git", "diff", "--name-only", base_sha, candidate_sha],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    changed_paths = [p for p in changed_paths if p.strip()]
    computed_categories = sorted({c.category for c in vs.classify_all(changed_paths)})
    migration_required = any(vs.is_migration_trigger(p) for p in changed_paths)

    receipt_id = str(uuid.uuid4())
    receipt = _minimal_receipt(candidate_sha, receipt_id, repo_root=repo)
    receipt["slice_id"] = slice_id
    receipt["base_sha"] = base_sha
    receipt["affected_surface"]["base_sha"] = base_sha
    receipt["affected_surface"]["computed_categories"] = computed_categories
    if migration_required:
        # A's own original receipt must genuinely reflect the true
        # base_sha..candidate_sha migration trigger too --
        # `_cross_check_affected_surface` independently recomputes and
        # cross-checks it, just like every other affected-surface field.
        receipt["steps"].append(
            {"name": "migration matrix", "status": "PASS", "duration_seconds": 0.5}
        )
        receipt["migration_matrix"] = {
            "triggered": True,
            "status": "PASS",
            "dev_state_before": {"alembic_revision": None, "schema_fingerprint": "x"},
            "dev_state_after": {"alembic_revision": None, "schema_fingerprint": "x"},
            "postgresql_server_version": "16.0",
            "fresh_database_created": True,
            "fresh_database_cleaned_up": True,
            "steps": ["alembic upgrade head"],
        }
    if receipt_mutator is not None:
        receipt_mutator(receipt)
    receipt_dir = repo / "docs" / "verification-receipts" / candidate_sha
    receipt_dir.mkdir(parents=True)
    (receipt_dir / f"{receipt_id}.json").write_text(json.dumps(receipt), encoding="utf-8")

    (repo / "docs" / "LLM_HANDOFF.md").write_text(
        _handoff_header()
        + _published_block(
            slice_id=slice_id, base_sha=base_sha, candidate_sha=candidate_sha, receipt_id=receipt_id
        ),
        encoding="utf-8",
    )
    publication_sha = _commit(repo, "A: publish receipt")

    review_block = "\n".join(
        [
            "schema_version: 2",
            f"slice_id: {slice_id}",
            "risk_class: H",
            "reviewer: Sol",
            "reviewer_role: primary",
            "reviewer_model: Sol Medium",
            "reviewed_at: 2026-09-18T00:00:00Z",
            f"candidate_sha: {candidate_sha}",
            f"publication_commit_sha: {publication_sha}",
            f"receipt_path: docs/verification-receipts/{candidate_sha}/{receipt_id}.json",
            f"receipt_id: {receipt_id}",
            "gate: final",
            "verdict: approved",
            "findings: none",
        ]
    )
    with (repo / "docs" / "LLM_HANDOFF.md").open("a", encoding="utf-8") as handle:
        handle.write(
            "\n### Work review\n\n```workflow-review-metadata\n" + review_block + "\n```\n"
        )
    review_sha = _commit(repo, "R: review")

    _git(["checkout", "-q", "main"], repo)
    _git(["merge", "--no-ff", "feature", "-m", "Merge feature into main"], repo)
    merge_sha = _rev_parse(repo, "HEAD")

    return {
        "base_sha": base_sha,
        "slice_id": slice_id,
        "candidate_sha": candidate_sha,
        "publication_sha": publication_sha,
        "review_sha": review_sha,
        "merge_sha": merge_sha,
        "receipt_id": receipt_id,
    }


def _commit_q(repo: Path, artifact_path: Path) -> str:
    """Bundles the artifact addition with the append-only merge-record
    edit to the handoff, in one commit -- exactly the future-merge policy
    this slice's own `LLM_WORKFLOW.md` addendum specifies for `Q`."""
    with (repo / "docs" / "LLM_HANDOFF.md").open("a", encoding="utf-8") as handle:
        handle.write("\n### Merge record\n\nplaceholder merge-record prose.\n")
    _git(["add", "-A"], repo)
    assert artifact_path.is_relative_to(repo)
    _git(["commit", "-q", "-m", "Q: publish post-merge evidence"], repo)
    return _rev_parse(repo, "HEAD")


# ---------------------------------------------------------------------------
# Success: a genuine local M -> Q chain passes validate_published.
# ---------------------------------------------------------------------------


def test_post_merge_verification_produces_a_valid_artifact_and_full_chain_passes_validate_published(
    post_merge_repo: Path,
) -> None:
    chain = _build_chain(post_merge_repo)
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )

    artifact_path = coord.run_post_merge_verification(request)

    assert artifact_path.is_file()
    assert artifact_path.is_relative_to(post_merge_repo / "docs" / "post-merge")
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["kind"] == "post_merge_verification"
    assert artifact["merged_commit"] == chain["merge_sha"]
    assert artifact["candidate_sha"] == chain["candidate_sha"]
    assert artifact["original_receipt_id"] == chain["receipt_id"]
    assert artifact["cleanup"] == {"attempted": True, "status": "PASS"}

    # The authoring checkout must be back to clean at M (aside from the
    # one new, not-yet-committed artifact file the producer just wrote --
    # committing it, bundled with the merge-record append, is what turns
    # it into Q), and the worktree must be fully gone.
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=post_merge_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status.strip() == "?? docs/post-merge/"
    worktree_list = subprocess.run(
        ["git", "worktree", "list"],
        cwd=post_merge_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert len(worktree_list.strip().splitlines()) == 1
    # `.verify-tmp` is gitignored, so `git status` alone can't prove the
    # physical scratch tree is gone -- assert its absence directly too.
    assert _verify_tmp_is_clean(post_merge_repo)

    q_sha = _commit_q(post_merge_repo, artifact_path)

    # `validate_published` returns the independently re-validated post-
    # merge artifact itself (not the review's verdict fields) -- its mere
    # successful return, with the cross-checked identity below, is the
    # proof that the complete C -> A -> R -> M -> Q chain validates.
    published_artifact = cr.validate_published(
        chain["candidate_sha"],
        chain["publication_sha"],
        chain["review_sha"],
        chain["merge_sha"],
        q_sha,
        chain["base_sha"],
        repo_root=post_merge_repo,
    )
    assert published_artifact["candidate_sha"] == chain["candidate_sha"]
    assert published_artifact["merged_commit"] == chain["merge_sha"]


# ---------------------------------------------------------------------------
# Fail-closed: no artifact on verification failure or cleanup failure.
# ---------------------------------------------------------------------------


def test_post_merge_verification_writes_no_artifact_when_verify_invocation_fails(
    post_merge_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STAND_IN_VERIFY_FAIL", "1")
    chain = _build_chain(post_merge_repo)
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )

    with pytest.raises(coord.CoordinatorError, match="did not pass"):
        coord.run_post_merge_verification(request)

    assert not (post_merge_repo / "docs" / "post-merge").exists()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=post_merge_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status.strip() == ""
    # `.verify-tmp` is gitignored, so `git status` alone can't prove the
    # physical scratch tree is gone -- assert its absence directly too.
    assert _verify_tmp_is_clean(post_merge_repo)


def test_post_merge_verification_writes_no_artifact_when_worktree_removal_fails(
    post_merge_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verification itself succeeds, but cleanup fails -- must still
    produce no artifact, mirroring the receipt producer's own
    `test_no_receipt_when_worktree_removal_fails`."""
    chain = _build_chain(post_merge_repo)

    def _fail_remove(worktree_path: Path) -> None:
        raise coord.vw.WorktreeError("simulated worktree removal failure")

    monkeypatch.setattr(coord.vw, "remove_worktree", _fail_remove)

    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )

    with pytest.raises(coord.CoordinatorError, match="cleanup"):
        coord.run_post_merge_verification(request)

    assert not (post_merge_repo / "docs" / "post-merge").exists()


def test_post_merge_verification_writes_no_artifact_when_self_validation_fails(
    post_merge_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The coordinator's own explicit `proc.returncode`/`all_passed` gate
    is not the only thing standing between a bad run and a written
    artifact: a worktree-isolated `verify.py` that mis-reports
    `all_passed: True` while silently omitting a required step (here,
    `contract mutation witnesses`) passes that first gate cleanly, but
    must still be caught by the artifact's own self-validation
    (`check_review._validate_post_merge_artifact_evidence`, via
    `_require_post_merge_steps_present`) before anything is written."""
    monkeypatch.setenv("STAND_IN_VERIFY_DROP_STEP", "contract mutation witnesses")
    chain = _build_chain(post_merge_repo)
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )

    with pytest.raises(cr.ReviewValidationError, match="contract mutation witnesses"):
        coord.run_post_merge_verification(request)

    assert not (post_merge_repo / "docs" / "post-merge").exists()
    assert _verify_tmp_is_clean(post_merge_repo)


# ---------------------------------------------------------------------------
# Bound request fields: incorrect parentage and a malformed committed `A`
# receipt are both rejected in stage 1/2, before any worktree is created.
# ---------------------------------------------------------------------------


def test_post_merge_verification_rejects_incorrect_parentage_before_any_worktree(
    post_merge_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chain = _build_chain(post_merge_repo)

    def _fail_if_called(candidate_sha: str, run_dir: Path) -> Path:
        raise AssertionError("a worktree must never be created for a malformed M")

    monkeypatch.setattr(coord.vw, "create_detached_worktree", _fail_if_called)

    # A merge commit whose second parent is *not* R (built by merging the
    # feature branch into a throwaway branch cut from a different point).
    _git(["checkout", "-q", "-b", "not-main", chain["base_sha"]], post_merge_repo)
    (post_merge_repo / "unrelated.txt").write_text("x\n", encoding="utf-8")
    _commit(post_merge_repo, "unrelated change")
    _git(["merge", "--no-ff", chain["candidate_sha"], "-m", "wrong merge"], post_merge_repo)
    wrong_merge_sha = _rev_parse(post_merge_repo, "HEAD")

    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=wrong_merge_sha,
        expected_first_parent=chain["base_sha"],
    )
    with pytest.raises(cr.ReviewValidationError, match="second parent"):
        coord.run_post_merge_verification(request)


def test_post_merge_verification_rejects_schema_invalid_committed_a_receipt(
    post_merge_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A receipt missing a required schema field is rejected by
    `vr.validate_receipt_schema`, called (uncaught) inside `check_review.
    validate_c_a_r_chain` -- the producer's own stage-1 pre-flight, before
    any worktree is created. The `create_detached_worktree` guard proves
    *when* this is rejected, not merely *that* it is -- `.verify-tmp`
    absence alone would also be true of a worktree that was created and
    then successfully cleaned up."""

    def _fail_if_called(candidate_sha: str, run_dir: Path) -> Path:
        raise AssertionError("a worktree must never be created for a malformed A receipt")

    monkeypatch.setattr(coord.vw, "create_detached_worktree", _fail_if_called)

    def _break_schema(receipt: dict) -> None:
        del receipt["environment_descriptor"]

    chain = _build_chain(post_merge_repo, receipt_mutator=_break_schema)
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )
    with pytest.raises(vr.ReceiptError, match="missing required field"):
        coord.run_post_merge_verification(request)
    assert _verify_tmp_is_clean(post_merge_repo)


def test_post_merge_verification_rejects_committed_a_receipt_with_mismatched_receipt_id(
    post_merge_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A schema-*valid* receipt whose own `receipt_id` does not match what
    the review metadata claims is rejected by `check_review.
    ReviewValidationError`'s explicit cross-check -- a different guard
    than the schema-invalid case above, still inside stage 1, still
    before any worktree is created (proven the same way, not merely by
    `.verify-tmp` absence)."""

    def _fail_if_called(candidate_sha: str, run_dir: Path) -> Path:
        raise AssertionError("a worktree must never be created for a mismatched receipt_id")

    monkeypatch.setattr(coord.vw, "create_detached_worktree", _fail_if_called)

    def _mismatch_id(receipt: dict) -> None:
        receipt["receipt_id"] = str(uuid.uuid4())

    chain = _build_chain(post_merge_repo, receipt_mutator=_mismatch_id)
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )
    with pytest.raises(cr.ReviewValidationError, match="does not match the receipt itself"):
        coord.run_post_merge_verification(request)
    assert _verify_tmp_is_clean(post_merge_repo)


# ---------------------------------------------------------------------------
# Caller-controlled values cannot skip the migration matrix.
# ---------------------------------------------------------------------------


def test_post_merge_eligible_request_has_no_forgeable_base_sha_field() -> None:
    """There is nothing left to forge: `PostMergeEligibleRequest` carries
    only the five chain SHAs, never `base_sha`/`slice_id`/receipt fields."""
    field_names = {f.name for f in __import__("dataclasses").fields(coord.PostMergeEligibleRequest)}
    assert field_names == {
        "candidate_sha",
        "publication_sha",
        "review_sha",
        "merge_sha",
        "expected_first_parent",
    }


def test_post_merge_verification_derives_migration_requirement_from_the_true_base(
    post_merge_repo: Path,
) -> None:
    """A candidate that genuinely touches a migration-trigger path
    relative to its *true* base must drive `--migration-required` --
    proving the decision is derived from the chain-validated `base_sha`
    (`review_fields["published_base_sha"]`), never from any external
    input, since no such input exists on the request at all."""
    chain = _build_chain(
        post_merge_repo,
        extra_files={"backend/migrations/0001_example.py": "# migration placeholder\n"},
    )
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )

    artifact_path = coord.run_post_merge_verification(request)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    assert artifact["migration_matrix"]["triggered"] is True
    assert artifact["migration_matrix"]["status"] == "PASS"
    matching = [s for s in artifact["steps"] if s["name"] == "migration matrix"]
    assert len(matching) == 1
    assert matching[0]["status"] == "PASS"


def test_post_merge_verification_does_not_trigger_migration_for_an_unrelated_candidate(
    post_merge_repo: Path,
) -> None:
    """Negative control for the above: a candidate that touches nothing
    migration-related must not spuriously trigger the migration matrix."""
    chain = _build_chain(post_merge_repo)
    request = coord.PostMergeEligibleRequest(
        candidate_sha=chain["candidate_sha"],
        publication_sha=chain["publication_sha"],
        review_sha=chain["review_sha"],
        merge_sha=chain["merge_sha"],
        expected_first_parent=chain["base_sha"],
    )
    artifact_path = coord.run_post_merge_verification(request)
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert artifact["migration_matrix"] == {"triggered": False}


# ---------------------------------------------------------------------------
# Cleanup-prefix scoping: only the two known prefixes are ever accepted,
# and the two scopes never cross.
# ---------------------------------------------------------------------------


def test_cleanup_stale_coordinator_dirs_rejects_unknown_prefix(tmp_path: Path) -> None:
    """Rejected before any directory is ever scanned -- proven here by
    pointing `COORDINATOR_RUN_ROOT` at a directory that does not even
    exist; a prefix check that ran *after* the existence check would
    return `[]` silently instead of raising."""
    original_root = coord.COORDINATOR_RUN_ROOT
    coord.COORDINATOR_RUN_ROOT = tmp_path / "does-not-exist"
    try:
        with pytest.raises(
            coord.CoordinatorError, match="unrecognized coordinator directory prefix"
        ):
            coord.cleanup_stale_coordinator_dirs(prefix="")
        with pytest.raises(
            coord.CoordinatorError, match="unrecognized coordinator directory prefix"
        ):
            coord.cleanup_stale_coordinator_dirs(prefix="arbitrary-")
    finally:
        coord.COORDINATOR_RUN_ROOT = original_root


def _make_stale_dir(run_root: Path, name: str) -> Path:
    stale_dir = run_root / name
    stale_dir.mkdir()
    handle = coord.vl.try_acquire_exclusive_lock(stale_dir / coord._LOCK_FILE_NAME)
    assert handle is not None
    handle.release()
    return stale_dir


def test_cleanup_stale_coordinator_dirs_prefix_scoping_never_crosses(tmp_path: Path) -> None:
    run_root = tmp_path / ".verify-tmp"
    run_root.mkdir()
    stale_receipt_dir = _make_stale_dir(run_root, "coordinator-stale")
    stale_post_merge_dir = _make_stale_dir(run_root, "post-merge-coordinator-stale")
    unrelated_dir = run_root / "run-xyz789"
    unrelated_dir.mkdir()

    original_root = coord.COORDINATOR_RUN_ROOT
    coord.COORDINATOR_RUN_ROOT = run_root
    try:
        removed_post_merge = coord.cleanup_stale_coordinator_dirs(
            prefix=coord._POST_MERGE_DIR_PREFIX
        )
        assert removed_post_merge == ["post-merge-coordinator-stale"]
        assert not stale_post_merge_dir.exists()
        assert stale_receipt_dir.exists()  # untouched by the post-merge-scoped call
        assert unrelated_dir.exists()

        removed_receipt = coord.cleanup_stale_coordinator_dirs()
        assert removed_receipt == ["coordinator-stale"]
        assert not stale_receipt_dir.exists()
        assert unrelated_dir.exists()
    finally:
        coord.COORDINATOR_RUN_ROOT = original_root


def test_cleanup_stale_coordinator_dirs_leaves_actively_locked_dirs_of_either_prefix(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / ".verify-tmp"
    run_root.mkdir()
    active_receipt_dir = run_root / "coordinator-active"
    active_receipt_dir.mkdir()
    active_post_merge_dir = run_root / "post-merge-coordinator-active"
    active_post_merge_dir.mkdir()
    receipt_handle = coord.vl.try_acquire_exclusive_lock(active_receipt_dir / coord._LOCK_FILE_NAME)
    post_merge_handle = coord.vl.try_acquire_exclusive_lock(
        active_post_merge_dir / coord._LOCK_FILE_NAME
    )
    assert receipt_handle is not None
    assert post_merge_handle is not None
    try:
        original_root = coord.COORDINATOR_RUN_ROOT
        coord.COORDINATOR_RUN_ROOT = run_root
        try:
            assert coord.cleanup_stale_coordinator_dirs() == []
            assert coord.cleanup_stale_coordinator_dirs(prefix=coord._POST_MERGE_DIR_PREFIX) == []
        finally:
            coord.COORDINATOR_RUN_ROOT = original_root
        assert active_receipt_dir.exists()
        assert active_post_merge_dir.exists()
    finally:
        receipt_handle.release()
        post_merge_handle.release()


def test_cleanup_stale_coordinator_dirs_leaves_unrelated_directories(tmp_path: Path) -> None:
    run_root = tmp_path / ".verify-tmp"
    run_root.mkdir()
    unrelated_verify_run_dir = run_root / "run-xyz789"
    unrelated_verify_run_dir.mkdir()
    unrelated_named_dir = run_root / "review-contracts"
    unrelated_named_dir.mkdir()

    original_root = coord.COORDINATOR_RUN_ROOT
    coord.COORDINATOR_RUN_ROOT = run_root
    try:
        assert coord.cleanup_stale_coordinator_dirs() == []
        assert coord.cleanup_stale_coordinator_dirs(prefix=coord._POST_MERGE_DIR_PREFIX) == []
    finally:
        coord.COORDINATOR_RUN_ROOT = original_root
    assert unrelated_verify_run_dir.exists()
    assert unrelated_named_dir.exists()


# ---------------------------------------------------------------------------
# Release-sequence guard: confirm_main_unchanged.
# ---------------------------------------------------------------------------


def test_confirm_main_unchanged_passes_when_remote_matches(post_merge_repo: Path) -> None:
    base_sha = _rev_parse(post_merge_repo, "HEAD")
    coord.confirm_main_unchanged(base_sha)  # must not raise


def test_confirm_main_unchanged_rejects_when_remote_advanced(post_merge_repo: Path) -> None:
    """Simulates the remote advancing (a second, independent push to
    `origin/main`) between local `M`/`Q` preparation and the intended
    push -- the guard must detect it and refuse."""
    base_sha = _rev_parse(post_merge_repo, "HEAD")

    other_clone = post_merge_repo.parent / "other-clone"
    origin_url = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=post_merge_repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    _git(["clone", "-q", origin_url, str(other_clone)], post_merge_repo)
    _git(["config", "user.email", "t2@example.com"], other_clone)
    _git(["config", "user.name", "Test2"], other_clone)
    (other_clone / "advanced.txt").write_text("x\n", encoding="utf-8")
    _commit(other_clone, "someone else's commit")
    _git(["push", "-q", "origin", "main"], other_clone)

    with pytest.raises(coord.CoordinatorError, match="main has advanced"):
        coord.confirm_main_unchanged(base_sha)
