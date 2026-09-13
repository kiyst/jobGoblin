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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", required=True)
    parser.add_argument("--gate", default=None)
    parser.add_argument("--focus", nargs="+", default=None)
    parser.add_argument("--witness", nargs="+", default=None)
    parser.add_argument("--docs-only", action="store_true")
    parser.add_argument("--emit-step-json", default=None)
    args = parser.parse_args()
    payload = {
        "steps": [{"name": "stand-in check", "status": "PASS", "duration_seconds": 0.01}],
        "full_suite": {"status": "ran", "count": 7},
        "focused_tests": {"status": "not_run"},
        "mutation_witnesses": {"status": "ran", "passed": 3, "failed": 0},
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
    _git(["init", "-q"], root)
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
