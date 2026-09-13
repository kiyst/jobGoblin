"""Genuine (non-mocked) tests: a real disposable Git repository, real
`git worktree` commands, real filesystem state -- proving the worktree
lifecycle actually behaves as the frozen contract requires."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts import verification_worktree as vw


def _init_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True)
    (path / "a.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "initial"], check=True)
    sha = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return sha


@pytest.fixture()
def disposable_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    sha = _init_repo(repo)
    monkeypatch.setattr(vw, "REPO_ROOT", repo)
    return repo, sha


def test_create_snapshot_remove_and_confirm_no_leak(disposable_repo: tuple[Path, str]) -> None:
    repo, sha = disposable_repo
    run_dir = repo.parent / "run"
    run_dir.mkdir()

    worktree = vw.create_detached_worktree(sha, run_dir)
    assert worktree.is_dir()

    initial = vw.snapshot(worktree)
    assert initial.clean
    assert initial.head_sha == sha

    final = vw.snapshot(worktree)
    assert initial.matches(final)

    vw.remove_worktree(worktree)
    vw.confirm_no_leak(worktree)
    assert not worktree.exists()


def test_snapshot_detects_unstaged_tracked_edit(disposable_repo: tuple[Path, str]) -> None:
    repo, sha = disposable_repo
    run_dir = repo.parent / "run2"
    run_dir.mkdir()
    worktree = vw.create_detached_worktree(sha, run_dir)

    initial = vw.snapshot(worktree)
    (worktree / "a.txt").write_text("mutated\n", encoding="utf-8")
    after_edit = vw.snapshot(worktree)

    assert not after_edit.diff_quiet
    assert not initial.matches(after_edit)

    (worktree / "a.txt").write_text("one\n", encoding="utf-8")  # restore before cleanup
    vw.remove_worktree(worktree)


def test_snapshot_detects_staged_edit(disposable_repo: tuple[Path, str]) -> None:
    repo, sha = disposable_repo
    run_dir = repo.parent / "run3"
    run_dir.mkdir()
    worktree = vw.create_detached_worktree(sha, run_dir)

    (worktree / "a.txt").write_text("staged-mutated\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(worktree), "add", "a.txt"], check=True)
    snap = vw.snapshot(worktree)
    assert not snap.diff_cached_quiet

    subprocess.run(["git", "-C", str(worktree), "reset", "-q"], check=True)
    (worktree / "a.txt").write_text("one\n", encoding="utf-8")
    vw.remove_worktree(worktree)


def test_snapshot_detects_untracked_file(disposable_repo: tuple[Path, str]) -> None:
    repo, sha = disposable_repo
    run_dir = repo.parent / "run4"
    run_dir.mkdir()
    worktree = vw.create_detached_worktree(sha, run_dir)

    initial = vw.snapshot(worktree)
    assert initial.status_porcelain_empty

    (worktree / "untracked.txt").write_text("surprise\n", encoding="utf-8")
    after = vw.snapshot(worktree)
    assert not after.status_porcelain_empty
    assert not initial.matches(after)

    (worktree / "untracked.txt").unlink()
    vw.remove_worktree(worktree)


def test_removed_worktree_cannot_be_removed_again(disposable_repo: tuple[Path, str]) -> None:
    repo, sha = disposable_repo
    run_dir = repo.parent / "run5"
    run_dir.mkdir()
    worktree = vw.create_detached_worktree(sha, run_dir)
    vw.remove_worktree(worktree)
    vw.confirm_no_leak(worktree)  # already gone -- confirmation itself passes
    with pytest.raises(vw.WorktreeError):
        vw.remove_worktree(worktree)  # a second removal attempt has nothing to remove


def test_run_cache_env_never_points_inside_worktree(disposable_repo: tuple[Path, str]) -> None:
    repo, sha = disposable_repo
    run_dir = repo.parent / "run6"
    run_dir.mkdir()
    env = vw.run_cache_env(run_dir)
    for value in env.values():
        assert str(run_dir) in value
