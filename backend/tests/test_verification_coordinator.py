"""Genuine end-to-end test of `verification_coordinator.py`: a real
disposable Git repository, a real `git worktree`, a real subprocess
invocation of a lightweight stand-in `scripts/verify.py`, and a real
atomic receipt write to disk -- not a mocked git/subprocess layer. The
full real project's own `scripts/verify.py` is exercised end-to-end
separately, against the actual activation candidate, as this slice's own
bootstrap-final run (see `docs/LLM_HANDOFF.md`) -- this test proves the
*coordinator's* lifecycle mechanics (worktree isolation, cache redirection,
snapshot comparison, cleanup ordering, create-only receipt emission) work
correctly in isolation, against a repository the test fully controls."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from scripts import verification_coordinator as coord

_STAND_IN_VERIFY_PY = """
import argparse
import json
import sys
from pathlib import Path

def _discover_active_guards():
    # A disposable test repo's own `backend/tests/__init__.py` (added by
    # some tests to exercise a real focus target) shadows the real
    # project's `.pth`-installed `tests` package for this subprocess --
    # this stand-in is only a lightweight mechanics fixture, so it falls
    # back to an empty inventory rather than crashing; the *real*
    # verify.py always runs against the real, complete `tests` package.
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
    parser.add_argument("--emit-step-json", default=None)
    args = parser.parse_args()

    # Mirrors the real verify.py's own --focus resolution: each target
    # must resolve to a real file under this script's own tests/
    # directory, relative to cwd -- catches exactly the class of bug
    # where a caller passes a repo-root-relative ("backend/tests/...")
    # path instead of a backend-relative ("tests/...") one.
    backend_dir = Path(__file__).resolve().parent.parent
    tests_root = (backend_dir / "tests").resolve()
    for target in args.focus or []:
        resolved = (backend_dir / target).resolve()
        if not resolved.is_relative_to(tests_root) or not resolved.is_file():
            print(f"error: bad --focus target {target!r}", file=sys.stderr)
            sys.exit(2)

    guard_refs = _discover_active_guards()

    payload = {
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
        "all_passed": True,
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


def _init_disposable_repo(root: Path) -> tuple[str, str]:
    """Returns (base_sha, candidate_sha)."""
    _git(["init", "-q", "-b", "main"], root)
    _git(["config", "user.email", "t@example.com"], root)
    _git(["config", "user.name", "Test"], root)

    # Matches the real repository's own root .gitignore: the coordinator's
    # scratch/run directory must never be tracked, or its own leftover
    # scratch content would make the authoring checkout look dirty.
    (root / ".gitignore").write_text("backend/.verify-tmp/\n", encoding="utf-8")

    (root / "backend" / "scripts").mkdir(parents=True)
    (root / "backend" / "scripts" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "scripts" / "verify.py").write_text(_STAND_IN_VERIFY_PY, encoding="utf-8")
    (root / "backend" / "scripts" / "check_handoff.py").write_text("# stand-in\n", encoding="utf-8")
    (root / "backend" / "pyproject.toml").write_text("[tool.example]\nx = 1\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "base"], root)
    base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    # A real `origin` remote whose `main` sits at exactly base_sha -- the
    # coordinator now fetches and enforces `base_sha == origin/main` before
    # anything else runs, so every disposable test repo needs a genuine
    # remote, not just a local-only history.
    origin_bare = root.parent / "origin.git"
    _git(["init", "-q", "--bare", "-b", "main", str(origin_bare)], root)
    _git(["remote", "add", "origin", str(origin_bare)], root)
    _git(["push", "-q", "origin", "main"], root)

    (root / "backend" / "scripts" / "extra.py").write_text("X = 1\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "candidate change"], root)
    candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    return base_sha, candidate_sha


@pytest.fixture()
def disposable_activation_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[Path, str, str], None, None]:
    # Deliberately *not* pytest's own `tmp_path`: this test nests a second,
    # real `git worktree` (plus a receipt path containing a 40-hex SHA and a
    # 36-char UUID) inside the disposable repo it creates. Combined with
    # `verify.py`'s own basetemp redirection (`.verify-tmp/run-<id>/...`)
    # when this suite is run *through* `scripts/verify.py` itself, pytest's
    # already-deep default `tmp_path` pushes the total path past Windows'
    # ~260-character limit -- a real, reproduced defect, not hypothetical.
    # A short-root temp directory keeps every nested path well under that
    # limit regardless of how this test file itself is invoked.
    root = Path(tempfile.mkdtemp(prefix="wfv32-")) / "repo"
    root.mkdir()
    try:
        base_sha, candidate_sha = _init_disposable_repo(root)

        monkeypatch.setattr(coord, "REPO_ROOT", root)
        monkeypatch.setattr(coord, "BACKEND_DIR", root / "backend")
        monkeypatch.setattr(coord, "COORDINATOR_RUN_ROOT", root / "backend" / ".verify-tmp")
        monkeypatch.setattr(coord.vw, "REPO_ROOT", root)

        yield root, base_sha, candidate_sha
    finally:
        shutil.rmtree(root.parent, ignore_errors=True)


def test_receipt_eligible_run_produces_a_valid_create_only_receipt(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    request = coord.ReceiptEligibleRequest(
        candidate_sha=candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    receipt_path = coord.run_receipt_eligible_verification(request)

    assert receipt_path.is_file()
    from scripts import verification_receipts as vr

    receipt = vr.load_receipt(receipt_path)
    vr.validate_receipt_schema(receipt)
    assert receipt["candidate_sha"] == candidate_sha
    assert receipt["base_sha"] == base_sha
    assert receipt["gate"] == "final"
    assert receipt["cleanup"]["status"] == "PASS"
    assert receipt["approval_eligible"] is True
    assert receipt["full_suite"] == {"status": "ran", "count": 7}
    assert receipt["affected_surface"]["computed_categories"] == ["unmapped"]

    # The authoring checkout must be untouched and the worktree fully gone --
    # `git worktree list` must show only the authoring checkout itself.
    assert (root / "backend" / "scripts" / "extra.py").is_file()
    worktree_list = subprocess.run(
        ["git", "worktree", "list"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    assert len(worktree_list.strip().splitlines()) == 1


def test_receipt_eligible_run_refuses_when_authoring_checkout_is_dirty(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    (root / "backend" / "scripts" / "extra.py").write_text("X = 2\n", encoding="utf-8")  # dirty

    request = coord.ReceiptEligibleRequest(
        candidate_sha=candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    with pytest.raises(coord.CoordinatorError, match="not clean"):
        coord.run_receipt_eligible_verification(request)


def test_receipt_eligible_run_refuses_when_head_does_not_match_candidate(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    request = coord.ReceiptEligibleRequest(
        candidate_sha=base_sha,  # HEAD is actually at candidate_sha, not base_sha
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    with pytest.raises(coord.CoordinatorError, match="does not equal"):
        coord.run_receipt_eligible_verification(request)


def test_receipt_survives_being_committed_as_a_and_a_fresh_candidate_gets_its_own_receipt(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    """Realistic sequence: the coordinator emits a receipt into the
    (now once-again clean, per its own reconfirmation) authoring checkout;
    the caller commits it as `A`; a later, independent candidate gets its
    own fresh receipt_id, never colliding with or overwriting the first."""
    root, base_sha, candidate_sha = disposable_activation_repo
    request = coord.ReceiptEligibleRequest(
        candidate_sha=candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    first_path = coord.run_receipt_eligible_verification(request)
    first_content = first_path.read_text(encoding="utf-8")

    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "A: publish receipt"], root)

    (root / "backend" / "scripts" / "extra2.py").write_text("Y = 1\n", encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "candidate 2"], root)
    candidate_sha_2 = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    request_2 = coord.ReceiptEligibleRequest(
        candidate_sha=candidate_sha_2,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    second_path = coord.run_receipt_eligible_verification(request_2)

    assert second_path != first_path
    assert first_path.read_text(encoding="utf-8") == first_content  # untouched
    assert second_path.is_file()


def test_diff_paths_reports_real_changed_files(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    paths = coord._diff_paths(base_sha, candidate_sha)
    assert paths == ["backend/scripts/extra.py"]


# ---------------------------------------------------------------------------
# enforce_base_authoritative -- Sol's correction 4
# ---------------------------------------------------------------------------


def test_enforce_base_authoritative_passes_for_the_real_fixture(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    coord.enforce_base_authoritative(base_sha, candidate_sha, f"2026-09-13-example-{base_sha[:7]}")


def test_enforce_base_authoritative_rejects_when_origin_main_has_advanced(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    # Advance origin/main independently of this checkout's own base_sha --
    # simulates another slice having merged in the meantime.
    other_clone = root.parent / "other-clone"
    subprocess.run(
        ["git", "clone", "-q", str(root.parent / "origin.git"), str(other_clone)],
        check=True,
        capture_output=True,
    )
    (other_clone / "unrelated.txt").write_text("x\n", encoding="utf-8")
    _git(["add", "-A"], other_clone)
    _git(
        ["-c", "user.email=t@example.com", "-c", "user.name=Test", "commit", "-q", "-m", "advance"],
        other_clone,
    )
    _git(["push", "-q", "origin", "main"], other_clone)

    with pytest.raises(coord.CoordinatorError, match="main has advanced"):
        coord.enforce_base_authoritative(
            base_sha, candidate_sha, f"2026-09-13-example-{base_sha[:7]}"
        )


def test_enforce_base_authoritative_rejects_mismatched_slice_id_suffix(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    with pytest.raises(coord.CoordinatorError, match="base suffix does not match"):
        coord.enforce_base_authoritative(base_sha, candidate_sha, "2026-09-13-example-0000000")


def test_enforce_base_authoritative_rejects_non_ancestor_base(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    # A base_sha equal to origin/main but not an ancestor of the given
    # "candidate" (an unrelated commit) must still be rejected.
    unrelated_dir = root.parent / "unrelated-checkout"
    subprocess.run(
        ["git", "clone", "-q", str(root.parent / "origin.git"), str(unrelated_dir)],
        check=True,
        capture_output=True,
    )
    _git(["config", "user.email", "t@example.com"], unrelated_dir)
    _git(["config", "user.name", "Test"], unrelated_dir)
    _git(["checkout", "-q", "--orphan", "unrelated-branch"], unrelated_dir)
    (unrelated_dir / "z.txt").write_text("z\n", encoding="utf-8")
    _git(["add", "-A"], unrelated_dir)
    _git(["commit", "-q", "-m", "unrelated root commit"], unrelated_dir)
    unrelated_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=unrelated_dir, check=True, capture_output=True, text=True
    ).stdout.strip()

    with pytest.raises(coord.CoordinatorError, match="is not an ancestor"):
        coord.enforce_base_authoritative(
            base_sha, unrelated_sha, f"2026-09-13-example-{base_sha[:7]}"
        )


# ---------------------------------------------------------------------------
# cleanup_stale_coordinator_dirs -- only our own prefix, never other entries
# ---------------------------------------------------------------------------


def test_cleanup_stale_coordinator_dirs_removes_only_own_prefix(tmp_path: Path) -> None:
    """ "Stale" is proven via the ownership lock, never guessed from the
    directory name/prefix alone: an abandoned (unlocked) coordinator
    directory is removed; a directory with no lock file at all is left
    alone (ownership unprovable); and paths outside our own prefix are
    never touched regardless."""
    run_root = tmp_path / ".verify-tmp"
    run_root.mkdir()

    abandoned_coordinator_dir = run_root / "coordinator-abandoned"
    abandoned_coordinator_dir.mkdir()
    (abandoned_coordinator_dir / "leftover.txt").write_text("x\n", encoding="utf-8")
    # A genuinely-abandoned run: the lock file exists but nothing holds it
    # (the handle that created it was already released).
    stale_lock_handle = coord.vl.try_acquire_exclusive_lock(
        abandoned_coordinator_dir / coord._LOCK_FILE_NAME
    )
    assert stale_lock_handle is not None
    stale_lock_handle.release()

    no_lock_coordinator_dir = run_root / "coordinator-no-lock-file"
    no_lock_coordinator_dir.mkdir()

    unrelated_verify_run_dir = run_root / "run-xyz789"
    unrelated_verify_run_dir.mkdir()
    unrelated_named_dir = run_root / "review-contracts"
    unrelated_named_dir.mkdir()

    original_root = coord.COORDINATOR_RUN_ROOT
    coord.COORDINATOR_RUN_ROOT = run_root
    try:
        removed = coord.cleanup_stale_coordinator_dirs()
    finally:
        coord.COORDINATOR_RUN_ROOT = original_root

    assert removed == ["coordinator-abandoned"]
    assert not abandoned_coordinator_dir.exists()
    assert no_lock_coordinator_dir.exists()  # no lock file -- left alone
    assert unrelated_verify_run_dir.exists()
    assert unrelated_named_dir.exists()


def test_cleanup_stale_coordinator_dirs_never_removes_an_actively_locked_run(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / ".verify-tmp"
    run_root.mkdir()
    active_dir = run_root / "coordinator-active"
    active_dir.mkdir()
    active_handle = coord.vl.try_acquire_exclusive_lock(active_dir / coord._LOCK_FILE_NAME)
    assert active_handle is not None
    try:
        original_root = coord.COORDINATOR_RUN_ROOT
        coord.COORDINATOR_RUN_ROOT = run_root
        try:
            removed = coord.cleanup_stale_coordinator_dirs()
        finally:
            coord.COORDINATOR_RUN_ROOT = original_root

        assert removed == []
        assert active_dir.exists()
    finally:
        active_handle.release()


def test_genuine_concurrent_coordinator_run_is_never_cleaned_up_by_another(
    tmp_path: Path,
) -> None:
    """A real second process holds the ownership lock on a coordinator
    run directory (simulating a genuinely concurrent, still-active
    receipt-eligible run) -- `cleanup_stale_coordinator_dirs`, called from
    this process while that lock is held, must never remove it."""
    import subprocess
    import sys
    import time

    run_root = tmp_path / ".verify-tmp"
    run_root.mkdir()
    active_dir = run_root / "coordinator-genuinely-concurrent"
    active_dir.mkdir()
    lock_path = active_dir / coord._LOCK_FILE_NAME
    backend_dir = str(Path(coord.__file__).resolve().parent.parent)

    holder_script = f"""
import sys
import time
sys.path.insert(0, {backend_dir!r})
from scripts import verification_lock as lock
from pathlib import Path

handle = lock.try_acquire_exclusive_lock(Path(sys.argv[1]))
if handle is None:
    print("FAILED_TO_ACQUIRE")
    sys.exit(1)
print("ACQUIRED", flush=True)
time.sleep(float(sys.argv[2]))
handle.release()
print("RELEASED", flush=True)
"""
    holder = subprocess.Popen(
        [sys.executable, "-c", holder_script, str(lock_path), "1.5"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5.0
        acquired = False
        while time.monotonic() < deadline:
            line = holder.stdout.readline() if holder.stdout else ""
            if "ACQUIRED" in line:
                acquired = True
                break
        assert acquired, "holder subprocess never reported acquiring the lock"

        original_root = coord.COORDINATOR_RUN_ROOT
        coord.COORDINATOR_RUN_ROOT = run_root
        try:
            removed = coord.cleanup_stale_coordinator_dirs()
        finally:
            coord.COORDINATOR_RUN_ROOT = original_root

        assert removed == []
        assert active_dir.exists()

        holder.wait(timeout=10)
        assert holder.returncode == 0
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait()


# ---------------------------------------------------------------------------
# Fail-closed: no receipt on verifier failure / malformed step JSON
# ---------------------------------------------------------------------------


def test_no_receipt_when_worktree_verify_invocation_fails(
    disposable_activation_repo: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    # Overwrite the stand-in verify.py, inside the *source* tree (so the
    # worktree checks out the failing version), to exit non-zero and never
    # write a step JSON at all.
    failing_verify_py = "import sys\nsys.exit(1)\n"
    (root / "backend" / "scripts" / "verify.py").write_text(failing_verify_py, encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "break verify.py"], root)
    broken_candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    request = coord.ReceiptEligibleRequest(
        candidate_sha=broken_candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    with pytest.raises(coord.CoordinatorError, match="no valid step JSON"):
        coord.run_receipt_eligible_verification(request)

    receipts_dir = root / "docs" / "verification-receipts" / broken_candidate_sha
    assert not receipts_dir.exists()
    # The authoring checkout itself must be clean and untouched afterward.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


def test_no_receipt_when_malformed_step_json_is_produced(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    root, base_sha, candidate_sha = disposable_activation_repo
    malformed_verify_py = (
        "import argparse, sys\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--level', required=True)\n"
        "p.add_argument('--gate', default=None)\n"
        "p.add_argument('--focus', nargs='+', default=None)\n"
        "p.add_argument('--witness', nargs='+', default=None)\n"
        "p.add_argument('--docs-only', action='store_true')\n"
        "p.add_argument('--emit-step-json', default=None)\n"
        "args = p.parse_args()\n"
        "if args.emit_step_json:\n"
        "    open(args.emit_step_json, 'w').write('not valid json{{{')\n"
        "sys.exit(0)\n"
    )
    (root / "backend" / "scripts" / "verify.py").write_text(malformed_verify_py, encoding="utf-8")
    _git(["add", "-A"], root)
    _git(["commit", "-q", "-m", "malformed step json"], root)
    broken_candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    request = coord.ReceiptEligibleRequest(
        candidate_sha=broken_candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    with pytest.raises(coord.CoordinatorError, match="no valid step JSON"):
        coord.run_receipt_eligible_verification(request)

    receipts_dir = root / "docs" / "verification-receipts" / broken_candidate_sha
    assert not receipts_dir.exists()


def test_no_receipt_when_worktree_removal_fails(
    disposable_activation_repo: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates a `git worktree remove` failure -- cleanup failure must
    block receipt emission even though verification itself succeeded."""
    root, base_sha, candidate_sha = disposable_activation_repo

    def _fail_remove(worktree_path: Path) -> None:
        raise coord.vw.WorktreeError("simulated worktree removal failure")

    monkeypatch.setattr(coord.vw, "remove_worktree", _fail_remove)

    request = coord.ReceiptEligibleRequest(
        candidate_sha=candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    with pytest.raises(coord.CoordinatorError, match="cleanup"):
        coord.run_receipt_eligible_verification(request)

    receipts_dir = root / "docs" / "verification-receipts" / candidate_sha
    assert not receipts_dir.exists()


def test_computed_focus_targets_are_converted_to_backend_relative_paths(
    disposable_activation_repo: tuple[Path, str, str],
) -> None:
    """Reproduces the real bug found while bootstrapping this correction:
    `verification_scope.compute_required_coverage` returns repo-root-
    relative paths (e.g. "backend/tests/test_x.py", matching `git diff
    --name-only`'s own output), but `verify.py --focus` resolves targets
    relative to its own `backend/` directory instead. The disposable
    repo's stand-in `verify.py` replicates the real script's own --focus
    validation, so a coordinator that failed to convert the prefix would
    make this test fail exactly the way the real bootstrap run once did."""
    root, base_sha, candidate_sha = disposable_activation_repo
    (root / "backend" / "tests").mkdir(parents=True, exist_ok=True)
    (root / "backend" / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "backend" / "tests" / "test_something.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8"
    )
    _git(["add", "-A"], root)
    _git(["commit", "-q", "--amend", "--no-edit"], root)
    new_candidate_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    request = coord.ReceiptEligibleRequest(
        candidate_sha=new_candidate_sha,
        gate="final",
        slice_id=f"2026-09-13-example-{base_sha[:7]}",
        risk_class="R",
        base_sha=base_sha,
        focus_targets=[],
        witness_refs=[],
    )
    receipt_path = coord.run_receipt_eligible_verification(request)

    from scripts import verification_receipts as vr

    receipt = vr.load_receipt(receipt_path)
    assert (
        "backend/tests/test_something.py" in receipt["affected_surface"]["directly_executed_tests"]
    )
