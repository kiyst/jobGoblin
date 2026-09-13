"""Disposable detached-worktree management for Workflow v3.2 receipt-eligible
verification.

A candidate `C` is verified in a worktree created via `git worktree add
--detach <tmp> C` -- never in the mutable authoring checkout. Integrity is
checked, before and after, on **all four** conditions the frozen contract
requires (an index/tree SHA alone cannot detect an unstaged tracked-file
edit): the exact `HEAD` SHA, `git diff --quiet`, `git diff --cached
--quiet`, and an empty `git status --porcelain=v2 --untracked-files=all`.
The committed tree SHA is recorded only as additional identity evidence.

Every tool this module's caller runs inside the worktree must redirect its
own cache/scratch output into the run directory this module creates
(`run_cache_env`) -- a freshly detached worktree starts with zero untracked
files, and the closed input policy requires it stay that way through the
final snapshot, with no exception list.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class WorktreeError(Exception):
    """A worktree lifecycle operation failed -- creation, snapshotting,
    removal, or leak confirmation."""


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", *args],
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        # `git diff --quiet`/`--cached --quiet` use exit 1 to mean "differs" --
        # a real invocation failure (git itself erroring) is any other code.
        raise WorktreeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


@dataclass(frozen=True)
class IntegritySnapshot:
    head_sha: str
    diff_quiet: bool
    diff_cached_quiet: bool
    status_porcelain_empty: bool
    tracked_tree_sha: str

    def matches(self, other: IntegritySnapshot) -> bool:
        return (
            self.head_sha == other.head_sha
            and self.diff_quiet == other.diff_quiet
            and self.diff_cached_quiet == other.diff_cached_quiet
            and self.status_porcelain_empty == other.status_porcelain_empty
            and self.tracked_tree_sha == other.tracked_tree_sha
        )

    @property
    def clean(self) -> bool:
        return self.diff_quiet and self.diff_cached_quiet and self.status_porcelain_empty


def snapshot(worktree_dir: Path) -> IntegritySnapshot:
    head = _git("rev-parse", "HEAD", cwd=worktree_dir).strip()
    diff_quiet = (
        subprocess.run(
            ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "diff", "--quiet"],
            cwd=worktree_dir,
        ).returncode
        == 0
    )
    diff_cached_quiet = (
        subprocess.run(
            ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "diff", "--cached", "--quiet"],
            cwd=worktree_dir,
        ).returncode
        == 0
    )
    status = _git("status", "--porcelain=v2", "--untracked-files=all", cwd=worktree_dir)
    tree_sha = _git("rev-parse", "HEAD^{tree}", cwd=worktree_dir).strip()
    return IntegritySnapshot(
        head_sha=head,
        diff_quiet=diff_quiet,
        diff_cached_quiet=diff_cached_quiet,
        status_porcelain_empty=(status.strip() == ""),
        tracked_tree_sha=tree_sha,
    )


def create_detached_worktree(candidate_sha: str, run_dir: Path) -> Path:
    worktree_path = run_dir / "worktree"
    _git("worktree", "add", "--detach", str(worktree_path), candidate_sha)
    return worktree_path


def remove_worktree(worktree_path: Path) -> None:
    _git("worktree", "remove", "--force", str(worktree_path))


def confirm_no_leak(worktree_path: Path) -> None:
    listing = _git("worktree", "list", "--porcelain")
    if str(worktree_path) in listing or worktree_path.resolve().as_posix() in listing.replace(
        "\\", "/"
    ):
        raise WorktreeError(f"worktree {worktree_path} still registered after removal")
    if worktree_path.exists():
        raise WorktreeError(f"worktree directory {worktree_path} still exists after removal")


def run_cache_env(run_dir: Path) -> dict[str, str]:
    """Environment overrides redirecting every tool's cache/scratch output
    into `run_dir`, never into the worktree's tracked area -- so a freshly
    detached worktree's untracked-file count can be proven zero again at
    the final snapshot, with no exception list."""
    return {
        "RUFF_CACHE_DIR": str(run_dir / ".ruff_cache"),
        "MYPY_CACHE_DIR": str(run_dir / ".mypy_cache"),
        "PYTHONPYCACHEPREFIX": str(run_dir / "pycache"),
        "PYTEST_ADDOPTS": f"--basetemp={run_dir / 'pytest-basetemp'}",
    }
