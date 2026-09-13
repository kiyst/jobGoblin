"""Outer coordinator for Workflow v3.2 receipt-eligible verification.

Runs from the clean authoring checkout fixed at candidate `C`. Never
performs verification itself -- it fetches `origin/main` and enforces
`base_sha == origin/main` and its ancestry *before* anything else runs;
computes the `base_sha..candidate_sha` diff and its required coverage
*before* creating any worktree; creates a disposable detached worktree at
`C`; launches *that worktree's own* `scripts/verify.py` (via `python -m
scripts.verify --gate ...`, `cwd` pointed at the worktree's `backend/`)
with the computed coverage as its `--focus`/`--witness` arguments (a
caller may only add to this, never narrow it); and, in a `finally` block
that runs on every success, exception, or cancellation path, cleans every
redirected cache, removes the worktree, and removes this run's own
scratch directory entirely. Only if every stage -- including cleanup --
succeeds does it, in the authoring checkout, atomically create-only-write
a receipt. No receipt is possible if any stage fails.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import stat
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
_COORDINATOR_DIR_PREFIX = "coordinator-"

_SLICE_ID_BASE_SUFFIX_RE = re.compile(r"-([0-9a-f]{7,40})$")


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


def _clear_readonly_and_retry(func: object, target_path: str, exc_info: object) -> None:
    os.chmod(target_path, stat.S_IWRITE)
    func(target_path)  # type: ignore[operator]


def _rmtree(path: Path) -> None:
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def _git(args: list[str], cwd: Path = REPO_ROOT) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CoordinatorError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Stage 0: safely remove any stale coordinator scratch directory left behind
# by a crashed prior run -- only our own prefix, never another `.verify-tmp`
# entry (e.g. `verify.py`'s own `run-*` directories, or unrelated named
# review directories).
# ---------------------------------------------------------------------------


def cleanup_stale_coordinator_dirs() -> list[str]:
    if not COORDINATOR_RUN_ROOT.is_dir():
        return []
    removed: list[str] = []
    for entry in COORDINATOR_RUN_ROOT.iterdir():
        if entry.is_dir() and entry.name.startswith(_COORDINATOR_DIR_PREFIX):
            try:
                _rmtree(entry)
                removed.append(entry.name)
            except OSError:
                # Best-effort only -- a directory still in use by another
                # concurrent run must never be force-removed out from under
                # it. Never touches anything outside our own prefix.
                continue
    return removed


# ---------------------------------------------------------------------------
# Stage 1: base authority -- fetch origin/main, enforce exact equality,
# ancestry, and slice_id-suffix consistency, before anything else runs.
# ---------------------------------------------------------------------------


def _fetch_origin_main() -> None:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "fetch", "origin", "main"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise CoordinatorError(f"git fetch origin main failed: {result.stderr.strip()}")


def enforce_base_authoritative(base_sha: str, candidate_sha: str, slice_id: str) -> None:
    """Fails closed unless **all** hold: `origin/main` (freshly fetched)
    equals `base_sha` exactly; `base_sha` is an ancestor of `candidate_sha`;
    and `slice_id`'s `<base-short-sha>` suffix is a prefix of `base_sha`.
    No fast-forward exception of any kind -- if main has advanced, this
    raises, and the only path forward is a fresh candidate/review cycle
    against the new base."""
    _fetch_origin_main()
    origin_main = _git(["rev-parse", "origin/main"], REPO_ROOT)
    if origin_main != base_sha:
        raise CoordinatorError(
            f"base_sha ({base_sha}) does not equal freshly-fetched origin/main "
            f"({origin_main}) -- main has advanced; a fresh candidate/review cycle "
            "against the new base is required, with no partial-equivalence shortcut"
        )

    is_ancestor = (
        subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPO_ROOT.as_posix()}",
                "merge-base",
                "--is-ancestor",
                base_sha,
                candidate_sha,
            ],
            cwd=REPO_ROOT,
        ).returncode
        == 0
    )
    if not is_ancestor:
        raise CoordinatorError(
            f"base_sha ({base_sha}) is not an ancestor of candidate ({candidate_sha})"
        )

    match = _SLICE_ID_BASE_SUFFIX_RE.search(slice_id)
    if not match or not base_sha.startswith(match.group(1)):
        raise CoordinatorError(
            f"slice_id ({slice_id!r})'s base suffix does not match base_sha ({base_sha!r})"
        )


def _require_clean_authoring_checkout(candidate_sha: str) -> None:
    head = _git(["rev-parse", "HEAD"], REPO_ROOT)
    if head != candidate_sha:
        raise CoordinatorError(
            f"authoring checkout HEAD ({head}) does not equal candidate_sha ({candidate_sha})"
        )
    status = _git(["status", "--porcelain=v2", "--untracked-files=all"], REPO_ROOT)
    if status.strip():
        raise CoordinatorError("authoring checkout is not clean -- refusing to proceed")


def _file_hash_at(relative_path: str) -> str:
    return vr.file_hash(REPO_ROOT / relative_path)


def _clean_cache_dirs(run_dir: Path) -> None:
    for name in (".ruff_cache", ".mypy_cache", "pycache", "pytest-basetemp"):
        candidate = run_dir / name
        if candidate.exists():
            _rmtree(candidate)


def _postgresql_version(docs_only: bool) -> str | None:
    if docs_only:
        return None
    try:
        from app.config import get_settings

        version = asyncio.run(capture_development_state(get_settings().database_url))
    except Exception:  # noqa: BLE001 -- best-effort descriptor field, never blocks the run itself
        return None
    return version


def _diff_paths(base_sha: str, candidate_sha: str) -> list[str]:
    output = _git(["diff", "--name-only", f"{base_sha}..{candidate_sha}"], REPO_ROOT)
    return [line for line in output.splitlines() if line.strip()]


def run_receipt_eligible_verification(request: ReceiptEligibleRequest) -> Path:
    # Stage 0: safe, own-prefix-only stale-directory cleanup.
    cleanup_stale_coordinator_dirs()

    # Stage 1: base authority, before anything else runs.
    enforce_base_authoritative(request.base_sha, request.candidate_sha, request.slice_id)

    # Stage 2: clean authoring checkout precondition.
    _require_clean_authoring_checkout(request.candidate_sha)

    # Stage 3: compute base_sha..candidate_sha coverage *before* executing
    # anything -- the single source of truth for both what runs and what
    # the receipt records.
    changed_paths = _diff_paths(request.base_sha, request.candidate_sha)
    coverage = vs.compute_required_coverage(changed_paths)
    migration_required = any(vs.is_migration_trigger(p) for p in changed_paths)

    # Stage 4: enforce forced-final categories -- a caller cannot request
    # `fast` against a diff that forces `final`.
    if coverage.forces_final and request.gate != "final":
        raise CoordinatorError(
            f"the base_sha..candidate_sha diff contains a category that forces --gate final; "
            f"requested gate was {request.gate!r}"
        )

    # Stage 5: mandatory coverage, caller additions only ever *add*.
    # `coverage.required_focus_targets` is repo-root-relative (it is
    # derived from `git diff --name-only`, always under `backend/`);
    # `verify.py --focus` resolves its targets relative to its own
    # `backend/` directory instead, and `request.focus_targets` (caller-
    # supplied) already follows that convention -- normalize the computed
    # set to match before taking the union, never the other way around.
    computed_focus_targets = {
        target.removeprefix("backend/") for target in coverage.required_focus_targets
    }
    focus_targets = sorted(computed_focus_targets | set(request.focus_targets))
    witness_refs = (
        sorted(coverage.required_guard_refs | set(request.witness_refs))
        if request.gate == "fast"
        else []
    )

    COORDINATOR_RUN_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=_COORDINATOR_DIR_PREFIX, dir=str(COORDINATOR_RUN_ROOT)))

    worktree: Path | None = None
    initial_snapshot = None
    final_snapshot = None
    proc: subprocess.CompletedProcess[str] | None = None
    step_json_path = run_dir / "steps.json"
    cleanup_ok = True

    try:
        worktree = vw.create_detached_worktree(request.candidate_sha, run_dir)
        initial_snapshot = vw.snapshot(worktree)
        if not initial_snapshot.clean:
            raise CoordinatorError("newly created worktree is not clean -- refusing to verify")

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
        if focus_targets:
            command.extend(["--focus", *focus_targets])
        if witness_refs:
            command.extend(["--witness", *witness_refs])
        if migration_required:
            command.append("--migration-required")

        proc = subprocess.run(
            command, cwd=str(worktree / "backend"), env=env, capture_output=True, text=True
        )

        _clean_cache_dirs(run_dir)
        final_snapshot = vw.snapshot(worktree)
    finally:
        # Every cleanup stage is attempted unconditionally, on every path
        # (success, an exception above, or -- since this is a synchronous,
        # uninterruptible block -- a cancellation raised into it) --
        # cleanup failure at any point blocks receipt emission below.
        try:
            _clean_cache_dirs(run_dir)
        except OSError:
            cleanup_ok = False
        if worktree is not None:
            try:
                vw.remove_worktree(worktree)
                vw.confirm_no_leak(worktree)
            except (vw.WorktreeError, OSError):
                cleanup_ok = False
        # Read the step JSON into memory before removing the run directory
        # that contains it -- the read itself is not "cleanup".
        step_data: dict[str, object] | None = None
        if step_json_path.is_file():
            try:
                step_data = json.loads(step_json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                step_data = None
        try:
            if run_dir.exists():
                _rmtree(run_dir)
        except OSError:
            cleanup_ok = False

    if not cleanup_ok:
        raise CoordinatorError(
            "cleanup (cache/worktree/coordinator-run-directory) failed -- no receipt may be issued"
        )

    _require_clean_authoring_checkout(request.candidate_sha)

    if proc is None or step_data is None:
        raise CoordinatorError(
            "worktree-isolated verify.py run produced no valid step JSON -- no receipt may "
            "be issued"
        )

    if (
        initial_snapshot is None
        or final_snapshot is None
        or not initial_snapshot.matches(final_snapshot)
    ):
        raise CoordinatorError(
            "worktree integrity drifted between the initial and final snapshot -- refusing "
            "to emit a receipt"
        )

    classifications = vs.classify_all(changed_paths)
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
            "required_contract_families": sorted(coverage.required_contract_families),
            "required_guard_refs": sorted(coverage.required_guard_refs),
            "directly_executed_tests": sorted(coverage.directly_executed_tests),
            "not_applicable_reason": coverage.not_applicable_reason,
        },
        "migration_matrix": {"triggered": migration_required},
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
