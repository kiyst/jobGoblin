from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "compact_checkpoint.py"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compact_checkpoint", HOOK_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _snapshot(**overrides: object) -> Any:
    values: dict[str, object] = {
        "branch": "main",
        "head": "abc123",
        "main_head": "abc123",
        "origin_main_head": "abc123",
        "upstream_head": "abc123",
        "clean": True,
    }
    values.update(overrides)
    return hook.GitSnapshot(**values)


def test_clean_synced_main_is_the_only_optimal_checkpoint() -> None:
    snapshot = _snapshot()

    assert snapshot.optimal_checkpoint is True
    assert hook.checkpoint_classification(snapshot)[0] == "OPTIMAL"


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"clean": False}, False),
        ({"branch": "feature"}, False),
        ({"origin_main_head": "older"}, False),
        ({"main_head": "older"}, False),
    ],
)
def test_optimal_checkpoint_fails_closed_when_main_state_differs(
    override: dict[str, object], expected: bool
) -> None:
    assert _snapshot(**override).optimal_checkpoint is expected


def test_clean_feature_equal_to_upstream_is_recoverable_not_optimal() -> None:
    snapshot = _snapshot(branch="phase-2/example")

    assert snapshot.optimal_checkpoint is False
    assert snapshot.pushed_feature_checkpoint is True
    assert hook.checkpoint_classification(snapshot)[0] == "RECOVERABLE"


def test_dirty_tree_is_classified_unsafe_for_proactive_compaction() -> None:
    snapshot = _snapshot(clean=False)

    classification, reason = hook.checkpoint_classification(snapshot)

    assert classification == "ACTIVE/UNSAFE FOR PROACTIVE COMPACTION"
    assert "uncommitted" in reason


def test_checkpoint_contains_no_environment_or_transcript_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret-user:secret-pass@example/db")
    checkpoint = hook.render_checkpoint(_snapshot(), trigger="auto")

    assert "secret-user" not in checkpoint
    assert "secret-pass" not in checkpoint
    assert "transcript" not in checkpoint.lower()
    assert "Trigger: auto" in checkpoint
    assert "docs/LLM_HANDOFF.md" in checkpoint


def test_write_checkpoint_is_atomic_and_restore_prints_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runtime_dir = tmp_path / "runtime"
    checkpoint_path = runtime_dir / "compact-checkpoint.md"
    monkeypatch.setattr(hook, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(hook, "CHECKPOINT_PATH", checkpoint_path)
    monkeypatch.setattr(hook, "capture_git_snapshot", lambda: _snapshot())

    hook.write_checkpoint(trigger="manual")
    hook.restore_context()

    output = capsys.readouterr().out
    assert checkpoint_path.exists()
    assert "Classification: **OPTIMAL**" in output
    assert "Trigger: manual" in output
    assert list(runtime_dir.glob("*.tmp")) == []
