"""Outer coordinators for Workflow v3.2 receipt-eligible and post-merge
verification.

`run_receipt_eligible_verification` runs from the clean authoring checkout
fixed at candidate `C`. Never performs verification itself -- it fetches
`origin/main` and enforces `base_sha == origin/main` and its ancestry
*before* anything else runs; computes the `base_sha..candidate_sha` diff
and its required coverage *before* creating any worktree; creates a
disposable detached worktree at `C`; launches *that worktree's own*
`scripts/verify.py` (via `python -m scripts.verify --gate ...`, `cwd`
pointed at the worktree's `backend/`) with the computed coverage as its
`--focus`/`--witness` arguments (a caller may only add to this, never
narrow it); and, in a `finally` block that runs on every success,
exception, or cancellation path, cleans every redirected cache, removes
the worktree, and removes this run's own scratch directory entirely.
Only if every stage -- including cleanup -- succeeds does it, in the
authoring checkout, atomically create-only-write a receipt. No receipt
is possible if any stage fails.

`run_post_merge_verification` is the analogous outer coordinator for
`Q`'s post-merge evidence artifact: it verifies the *merged* tree at `M`
(never a pre-merge candidate), always full/final, and derives every
field it records (`base_sha`, `slice_id`, the original receipt
reference) from `check_review.validate_c_a_r_chain`'s own independently
re-validated chain -- never from caller-supplied input. It shares this
module's worktree/lock/cache-cleanup lifecycle but uses its own
`post-merge-coordinator-` run-directory prefix, and, unlike a receipt,
writes nothing at all on a failed run rather than a durable-but-
ineligible artifact.
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

from scripts import check_review as cr
from scripts import verification_lock as vl
from scripts import verification_receipts as vr
from scripts import verification_scope as vs
from scripts import verification_worktree as vw
from scripts.migration_matrix import query_postgresql_server_version

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
COORDINATOR_RUN_ROOT = BACKEND_DIR / ".verify-tmp"
_COORDINATOR_DIR_PREFIX = "coordinator-"
_POST_MERGE_DIR_PREFIX = "post-merge-coordinator-"
_KNOWN_COORDINATOR_DIR_PREFIXES = frozenset({_COORDINATOR_DIR_PREFIX, _POST_MERGE_DIR_PREFIX})

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
# review directories). "Stale" is proven, never guessed: every run holds an
# exclusive OS advisory lock (`verification_lock`) on its own directory for
# its entire lifetime; a directory is only ever removed here if this
# process can itself acquire that lock (meaning no live process holds it --
# the kernel releases an advisory lock automatically on process exit or
# crash, which is exactly the "provably abandoned" signal required). A
# directory currently owned by another active run is never touched,
# regardless of age; a directory with no lock file at all (a vanishingly
# rare crash window between mkdtemp and lock acquisition) is also left
# alone, since ownership cannot be proven either way.
# ---------------------------------------------------------------------------

_LOCK_FILE_NAME = ".owner.lock"


def cleanup_stale_coordinator_dirs(prefix: str = _COORDINATOR_DIR_PREFIX) -> list[str]:
    """Scoped to exactly one of the two known run-directory prefixes --
    the receipt-eligible coordinator's own `coordinator-` and the
    post-merge coordinator's own `post-merge-coordinator-` -- never an
    arbitrary caller-supplied string. An empty prefix would otherwise
    match every directory (`str.startswith("")` is always `True`); a
    typo'd prefix would instead silently clean up nothing. Both are
    rejected here, before any directory is ever scanned, rather than
    left to whichever failure mode happens to follow."""
    if prefix not in _KNOWN_COORDINATOR_DIR_PREFIXES:
        raise CoordinatorError(
            f"unrecognized coordinator directory prefix {prefix!r} -- must be one of "
            f"{sorted(_KNOWN_COORDINATOR_DIR_PREFIXES)}"
        )
    if not COORDINATOR_RUN_ROOT.is_dir():
        return []
    removed: list[str] = []
    for entry in COORDINATOR_RUN_ROOT.iterdir():
        if not (entry.is_dir() and entry.name.startswith(prefix)):
            continue
        lock_path = entry / _LOCK_FILE_NAME
        if not lock_path.is_file():
            continue  # cannot prove abandonment either way -- leave it alone
        handle = vl.try_acquire_exclusive_lock(lock_path)
        if handle is None:
            continue  # still owned by a live process -- never touched
        # Release (closing the file handle) *before* removing the
        # directory: on Windows, deleting a file still held open by this
        # same process fails outright.
        handle.release()
        try:
            _rmtree(entry)
            removed.append(entry.name)
        except OSError:
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


def confirm_main_unchanged(expected_sha: str) -> None:
    """Release-sequence guard: re-fetches `origin/main` and confirms it
    still equals `expected_sha` -- run immediately before pushing a
    locally-prepared `M` and `Q` together, so a remote that advanced in
    the meantime is caught before the push, never raced against. No
    fast-forward or partial-equivalence exception -- any mismatch means
    the locally-built `M`/`Q` were prepared against a base that is no
    longer the remote tip, and must not be pushed."""
    _fetch_origin_main()
    origin_main = _git(["rev-parse", "origin/main"], REPO_ROOT)
    if origin_main != expected_sha:
        raise CoordinatorError(
            f"origin/main ({origin_main}) no longer equals the expected pre-push tip "
            f"({expected_sha}) -- main has advanced; do not push a locally-built M/Q "
            "prepared against a stale base"
        )


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


def _file_hash_at(candidate_sha: str, relative_path: str) -> str:
    """The canonical committed-blob hash at `candidate_sha` -- never a
    working-tree read, which can diverge from a fresh checkout's bytes
    whenever a local checkout filter (e.g. `core.autocrlf`) converts line
    endings on smudge (see `verification_receipts.committed_file_hash`,
    the single mechanism this and `check_review.py`'s review-time
    recomputation both use)."""
    return vr.committed_file_hash(candidate_sha, relative_path, repo_root=REPO_ROOT)


def _clean_cache_dirs(run_dir: Path) -> None:
    for name in (".ruff_cache", ".mypy_cache", "pycache", "pytest-basetemp"):
        candidate = run_dir / name
        if candidate.exists():
            _rmtree(candidate)


def _postgresql_version(docs_only: bool) -> str | None:
    """The real PostgreSQL server version (`SELECT version()`), captured
    separately from any schema-state check -- never the development
    database's name or schema fingerprint."""
    if docs_only:
        return None
    try:
        from app.config import get_settings

        version = asyncio.run(query_postgresql_server_version(get_settings().database_url))
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

    # Acquire ownership of this run directory for its entire lifetime --
    # `cleanup_stale_coordinator_dirs` (stage 0, above) will never remove
    # a directory whose lock it cannot itself acquire. `mkdtemp` just
    # created this exact directory uniquely, so failure to acquire here
    # would mean something else already raced onto our own fresh path --
    # treated as a hard failure, never silently proceeding unlocked.
    lock_handle = vl.try_acquire_exclusive_lock(run_dir / _LOCK_FILE_NAME)
    if lock_handle is None:
        raise CoordinatorError(
            f"could not acquire ownership lock for fresh run directory {run_dir}"
        )

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
        # Release ownership before removing the directory that contains
        # the lock file -- on Windows, deleting a file this same process
        # still holds open fails outright.
        lock_handle.release()
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
        "verifier_hash": _file_hash_at(request.candidate_sha, "backend/scripts/verify.py"),
        "checker_hash": _file_hash_at(request.candidate_sha, "backend/scripts/check_handoff.py"),
        "dependency_and_config_inputs": vr.dependency_and_config_inputs(
            request.candidate_sha, ["backend/pyproject.toml"], repo_root=REPO_ROOT
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
        "migration_matrix": step_data.get("migration_matrix") or {"triggered": migration_required},
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


# ---------------------------------------------------------------------------
# Post-merge (`Q`) evidence producer.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PostMergeEligibleRequest:
    """Deliberately minimal: only the five commit SHAs needed to locate
    and independently re-validate the chain via Git plumbing. There is
    no `base_sha`/`slice_id`/`risk_class`/receipt-reference field here for
    a caller to forge -- every one of those is derived from `check_
    review.validate_c_a_r_chain`'s own independently re-validated output,
    never accepted as raw input. A caller cannot skip or redirect the
    migration check by supplying a different range: the migration
    trigger below is always computed from the chain-derived `base_sha`
    against `candidate_sha`, the exact same B..C pairing that determined
    `A`'s own original receipt's migration requirement."""

    candidate_sha: str  # C
    publication_sha: str  # A
    review_sha: str  # R
    merge_sha: str  # M
    expected_first_parent: str  # pre-merge main tip


def run_post_merge_verification(request: PostMergeEligibleRequest) -> Path:
    """Outer coordinator for Workflow v3.2's post-merge (`Q`) evidence.

    Mirrors `run_receipt_eligible_verification`'s structure and every
    lifecycle primitive it uses (worktree, lock, cache-cleanup, snapshot
    discipline) but verifies the *merged* tree at `M`, not a pre-merge
    candidate, and is always full/final -- never gated, never partial,
    never focus-narrowed.

    Only ever writes the artifact file; it never commits anything. The
    caller is responsible for committing `Q` afterward, bundling this
    file with the append-only merge-record edit to `docs/LLM_HANDOFF.md`
    in that single commit -- this function has no opinion about Git
    history beyond validating `M`'s own shape.

    Fails closed, explicitly, before ever writing: a failed verification
    run, a cleanup failure, or an artifact that would fail its own
    schema/evidence validation all produce *no file at all* -- never an
    artifact merely marked ineligible. Unlike a receipt (which records
    a failed run as `approval_eligible: false` for audit value), `Q`'s
    only meaning is structural (`check_review.validate_q` checks for its
    committed existence), so a durable-but-failed `Q` artifact would risk
    being mistaken for genuine evidence if ever accidentally committed.
    """
    # Stage 0: safe, own-prefix-only stale-directory cleanup.
    cleanup_stale_coordinator_dirs(prefix=_POST_MERGE_DIR_PREFIX)

    # Stage 1: independently re-derive the whole C -> A -> R chain --
    # never trust a caller-supplied base_sha/slice_id/receipt reference.
    # This is also what rejects a malformed committed `A` receipt before
    # any worktree exists: a schema-invalid receipt raises `verification_
    # receipts.ReceiptError` (from `vr.validate_receipt_schema`, called
    # inside `validate_c_a_r_chain`, uncaught there); a schema-valid but
    # cross-referenced-wrong receipt (e.g. a `receipt_id` mismatch against
    # the review metadata's own claim) raises `check_review.
    # ReviewValidationError` instead. Either way, nothing downstream ever
    # runs.
    review_fields = cr.validate_c_a_r_chain(
        request.candidate_sha, request.publication_sha, request.review_sha, repo_root=REPO_ROOT
    )

    # Stage 2: `M`'s own shape -- exactly two parents (first the expected
    # pre-merge main tip, second `R`), and `R..M` is zero-content-diff.
    cr.validate_merge(
        request.review_sha,
        request.merge_sha,
        request.expected_first_parent,
        repo_root=REPO_ROOT,
    )

    base_sha = review_fields["published_base_sha"]
    slice_id = review_fields["slice_id"]
    original_receipt_id = review_fields["receipt_id"]
    original_receipt_path = review_fields["receipt_path"]

    # Stage 3: clean authoring checkout precondition, at `M` -- post-merge
    # verification runs against the merged tree, not a pre-merge candidate.
    _require_clean_authoring_checkout(request.merge_sha)

    # Stage 4: migration trigger computed over the same base_sha..
    # candidate_sha (B..C) range that determined A's own original receipt's
    # migration requirement -- never base_sha..merge_sha, and never a
    # caller-supplied range. `C..M` is already provably diff-free of
    # substance (the validated C..A/A..R transitions plus R..M's own
    # zero-diff requirement), so B..C is both authoritative and sufficient.
    changed_paths = _diff_paths(base_sha, request.candidate_sha)
    migration_required = any(vs.is_migration_trigger(p) for p in changed_paths)

    COORDINATOR_RUN_ROOT.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=_POST_MERGE_DIR_PREFIX, dir=str(COORDINATOR_RUN_ROOT)))

    lock_handle = vl.try_acquire_exclusive_lock(run_dir / _LOCK_FILE_NAME)
    if lock_handle is None:
        raise CoordinatorError(
            f"could not acquire ownership lock for fresh run directory {run_dir}"
        )

    worktree: Path | None = None
    initial_snapshot = None
    final_snapshot = None
    proc: subprocess.CompletedProcess[str] | None = None
    step_json_path = run_dir / "steps.json"
    cleanup_ok = True

    try:
        worktree = vw.create_detached_worktree(request.merge_sha, run_dir)
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
            "final",
            "--emit-step-json",
            str(step_json_path),
        ]
        if migration_required:
            command.append("--migration-required")

        proc = subprocess.run(
            command, cwd=str(worktree / "backend"), env=env, capture_output=True, text=True
        )

        _clean_cache_dirs(run_dir)
        final_snapshot = vw.snapshot(worktree)
    finally:
        # Every cleanup stage is attempted unconditionally, on every path.
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
        step_data: dict[str, object] | None = None
        if step_json_path.is_file():
            try:
                step_data = json.loads(step_json_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                step_data = None
        lock_handle.release()
        try:
            if run_dir.exists():
                _rmtree(run_dir)
        except OSError:
            cleanup_ok = False

    if not cleanup_ok:
        raise CoordinatorError(
            "cleanup (cache/worktree/coordinator-run-directory) failed -- no post-merge "
            "artifact may be issued"
        )

    _require_clean_authoring_checkout(request.merge_sha)

    if proc is None or step_data is None:
        raise CoordinatorError(
            "worktree-isolated verify.py run produced no valid step JSON -- no post-merge "
            "artifact may be issued"
        )

    if (
        initial_snapshot is None
        or final_snapshot is None
        or not initial_snapshot.clean
        or not final_snapshot.clean
        or not initial_snapshot.matches(final_snapshot)
    ):
        raise CoordinatorError(
            "worktree integrity drifted between the initial and final snapshot -- refusing "
            "to emit a post-merge artifact"
        )

    # Explicit, single fail-closed gate -- every condition independently
    # required, none sufficient alone. A failed run produces *no* artifact,
    # never one merely marked ineligible: Q's only meaning is structural
    # (its committed existence is what `validate_q` checks), so nothing
    # resembling evidence may ever reach disk unless the run genuinely
    # passed.
    if proc.returncode != 0 or not step_data.get("all_passed"):
        raise CoordinatorError(
            "worktree-isolated verify.py run did not pass -- no post-merge artifact may be issued"
        )

    artifact = {
        "schema_version": "1",
        "kind": "post_merge_verification",
        "slice_id": slice_id,
        "base_sha": base_sha,
        "candidate_sha": request.candidate_sha,
        "publication_commit_sha": request.publication_sha,
        "review_commit_sha": request.review_sha,
        "original_receipt_id": original_receipt_id,
        "original_receipt_path": original_receipt_path,
        "merged_commit": request.merge_sha,
        "environment_descriptor": vr.environment_descriptor(
            postgresql_version=_postgresql_version(docs_only=False)
        ),
        "coordinator": {
            "authoring_checkout_head_at_start": request.merge_sha,
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
            "authoring_checkout_head_at_receipt": request.merge_sha,
            "authoring_checkout_clean_at_receipt": True,
        },
        "full_suite": step_data["full_suite"],
        "mutation_witnesses": step_data["mutation_witnesses"],
        "migration_matrix": step_data.get("migration_matrix") or {"triggered": migration_required},
        "steps": step_data["steps"],
        "cleanup": {"attempted": True, "status": "PASS"},
    }

    # Self-validate before ever writing -- schema/evidence correctness is
    # proven here, never merely assumed by construction.
    cr._validate_post_merge_artifact_schema(artifact)
    cr._validate_post_merge_artifact_evidence(artifact)

    artifact_path = (
        REPO_ROOT / "docs" / "post-merge" / request.merge_sha / f"{vr.generate_receipt_id()}.json"
    )
    vr.write_receipt_atomic(artifact_path, artifact)
    return artifact_path
