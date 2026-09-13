"""Outer coordinator for Workflow v3.2 receipt-eligible verification.

Runs from the clean authoring checkout fixed at candidate `C`. Never
performs verification itself -- it creates a disposable detached
worktree at `C`, launches *that worktree's own* `scripts/verify.py`
(via `python -m scripts.verify --gate ...`, `cwd` pointed at the
worktree's `backend/`) as a subprocess, waits for it to finish, cleans
every redirected cache, reconfirms the worktree's integrity snapshot is
unchanged, removes the worktree, reconfirms the authoring checkout
itself is still clean and at `C`, and only then -- in the authoring
checkout, never in the now-removed worktree -- atomically creates the
receipt. No receipt is possible if any of these stages fails.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from scripts import verification_receipts as vr
from scripts import verification_scope as vs
from scripts import verification_worktree as vw
from scripts.migration_matrix import capture_development_state

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
COORDINATOR_RUN_ROOT = BACKEND_DIR / ".verify-tmp"


class CoordinatorError(Exception):
    """A coordinator-lifecycle invariant was violated -- no receipt may be
    created when this is raised."""


@dataclass(frozen=True)
class ReceiptEligibleRequest:
    candidate_sha: str
    gate: str
    slice_id: str
    risk_class: str
    base_sha: str
    focus_targets: list[str]
    witness_refs: list[str]
    docs_only: bool = False


def _run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CoordinatorError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _require_clean_authoring_checkout(candidate_sha: str) -> None:
    head = _run_git(["rev-parse", "HEAD"], REPO_ROOT)
    if head != candidate_sha:
        raise CoordinatorError(
            f"authoring checkout HEAD ({head}) does not equal candidate_sha ({candidate_sha})"
        )
    status = _run_git(["status", "--porcelain=v2", "--untracked-files=all"], REPO_ROOT)
    if status.strip():
        raise CoordinatorError("authoring checkout is not clean -- refusing to proceed")


def _file_hash_at(relative_path: str) -> str:
    return vr.file_hash(REPO_ROOT / relative_path)


def _clean_cache_dirs(run_dir: Path) -> None:
    for name in (".ruff_cache", ".mypy_cache", "pycache", "pytest-basetemp"):
        candidate = run_dir / name
        if candidate.exists():
            shutil.rmtree(candidate)


def _postgresql_version(docs_only: bool) -> str | None:
    if docs_only:
        return None
    try:
        from app.config import get_settings

        version = asyncio.run(capture_development_state(get_settings().database_url))
    except Exception:  # noqa: BLE001 -- best-effort descriptor field, never blocks the run itself
        return None
    return version


def run_receipt_eligible_verification(request: ReceiptEligibleRequest) -> Path:
    _require_clean_authoring_checkout(request.candidate_sha)

    COORDINATOR_RUN_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="coordinator-", dir=str(COORDINATOR_RUN_ROOT)))

    worktree = vw.create_detached_worktree(request.candidate_sha, run_dir)
    initial_snapshot = vw.snapshot(worktree)
    if not initial_snapshot.clean:
        vw.remove_worktree(worktree)
        raise CoordinatorError("newly created worktree is not clean -- refusing to verify")

    step_json_path = run_dir / "steps.json"
    env = {**os.environ, **vw.run_cache_env(run_dir)}
    command = [
        sys.executable,
        "-m",
        "scripts.verify",
        "--level",
        "routine",
        "--gate",
        request.gate,
        "--emit-step-json",
        str(step_json_path),
    ]
    if request.docs_only:
        command.append("--docs-only")
    if request.focus_targets:
        command.extend(["--focus", *request.focus_targets])
    if request.witness_refs:
        command.extend(["--witness", *request.witness_refs])

    proc = subprocess.run(
        command, cwd=str(worktree / "backend"), env=env, capture_output=True, text=True
    )

    _clean_cache_dirs(run_dir)
    final_snapshot = vw.snapshot(worktree)
    snapshots_match = initial_snapshot.matches(final_snapshot)

    vw.remove_worktree(worktree)
    vw.confirm_no_leak(worktree)
    _require_clean_authoring_checkout(request.candidate_sha)

    if not step_json_path.is_file():
        raise CoordinatorError(
            f"worktree-isolated verify.py run produced no step JSON (exit {proc.returncode}); "
            f"stdout tail: {proc.stdout[-2000:]}"
        )
    step_data = json.loads(step_json_path.read_text(encoding="utf-8"))

    if not snapshots_match:
        raise CoordinatorError(
            "worktree integrity drifted between the initial and final snapshot -- refusing "
            "to emit a receipt"
        )

    changed_paths = _diff_paths(request.base_sha, request.candidate_sha)
    classifications = vs.classify_all(changed_paths)
    migration_triggered = any(vs.is_migration_trigger(p) for p in changed_paths)

    cleanup_status = "PASS" if (proc.returncode == 0 and step_data.get("all_passed")) else "FAIL"

    receipt_id = vr.generate_receipt_id()
    receipt = {
        "schema_version": "1",
        "receipt_id": receipt_id,
        "slice_id": request.slice_id,
        "risk_class": request.risk_class,
        "base_sha": request.base_sha,
        "candidate_sha": request.candidate_sha,
        "gate": request.gate,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "coordinator": {
            "authoring_checkout_head_at_start": request.candidate_sha,
            "worktree_initial_snapshot": {
                "tracked_tree_sha": initial_snapshot.tracked_tree_sha,
                "untracked_present": not initial_snapshot.status_porcelain_empty,
            },
            "run_cache_redirect": {
                "pytest_basetemp_redirected": True,
                "ruff_cache_redirected": True,
                "mypy_cache_redirected": True,
                "pycache_redirected": True,
            },
            "worktree_final_snapshot": {
                "tracked_tree_sha": final_snapshot.tracked_tree_sha,
                "untracked_present": not final_snapshot.status_porcelain_empty,
            },
            "worktree_removed": True,
            "worktree_leak_check": "no residual .git/worktrees entry, no residual directory",
            "authoring_checkout_head_at_receipt": request.candidate_sha,
            "authoring_checkout_clean_at_receipt": True,
        },
        "verifier_hash": _file_hash_at("backend/scripts/verify.py"),
        "checker_hash": _file_hash_at("backend/scripts/check_handoff.py"),
        "dependency_and_config_inputs": vr.dependency_and_config_inputs(
            REPO_ROOT, ["backend/pyproject.toml"]
        ),
        "environment_descriptor": vr.environment_descriptor(
            postgresql_version=_postgresql_version(request.docs_only)
        ),
        "steps": step_data["steps"],
        "full_suite": step_data["full_suite"],
        "focused_tests": step_data["focused_tests"],
        "mutation_witnesses": step_data["mutation_witnesses"],
        "affected_surface": {
            "base_sha": request.base_sha,
            "computed_categories": sorted({c.category for c in classifications}),
            "required_contract_families": sorted(vs.required_contract_families(classifications)),
            "required_guard_refs": [],
            "directly_executed_tests": sorted(
                {c.path for c in classifications if c.directly_execute}
            ),
            "not_applicable_reason": None,
        },
        "migration_matrix": {"triggered": migration_triggered},
        "cleanup": {"attempted": True, "status": cleanup_status},
        "approval_eligible": False,
    }
    receipt["approval_eligible"] = vr.compute_approval_eligible(receipt)

    vr.validate_receipt_schema(receipt)
    receipt_path = (
        REPO_ROOT / "docs" / "verification-receipts" / request.candidate_sha / f"{receipt_id}.json"
    )
    vr.write_receipt_atomic(receipt_path, receipt)
    return receipt_path


def _diff_paths(base_sha: str, candidate_sha: str) -> list[str]:
    output = _run_git(["diff", "--name-only", f"{base_sha}..{candidate_sha}"], REPO_ROOT)
    return [line for line in output.splitlines() if line.strip()]
