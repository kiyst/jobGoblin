"""Create and restore a credential-free Git checkpoint around Claude compaction.

The hook is deliberately non-blocking: forced recovery compaction may be the only way
Claude Code can continue after reaching its context limit. Blocking `PreCompact` there
would surface the original context-limit failure instead of preserving progress.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / ".claude" / "runtime"
CHECKPOINT_PATH = RUNTIME_DIR / "compact-checkpoint.md"
WORKFLOW_VERSION = "v3.2"
RECOVERY_DOCS = (
    "docs/LLM_WORKFLOW.md",
    "docs/LLM_HANDOFF.md",
    "docs/PHASE_RISK_CHECKLIST.md",
    "docs/ARCHITECTURE.md",
    "docs/DATA_MODEL.md",
    "docs/ROADMAP.md",
)


@dataclass(frozen=True)
class GitSnapshot:
    branch: str
    head: str
    main_head: str
    origin_main_head: str
    upstream_head: str
    clean: bool

    @property
    def optimal_checkpoint(self) -> bool:
        return (
            self.clean
            and self.branch == "main"
            and bool(self.head)
            and self.head == self.main_head == self.origin_main_head
        )

    @property
    def pushed_feature_checkpoint(self) -> bool:
        return (
            self.clean
            and self.branch != "main"
            and bool(self.head)
            and self.head == self.upstream_head
        )


def _git(*args: str) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={REPO_ROOT.as_posix()}",
        *args,
    ]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def capture_git_snapshot() -> GitSnapshot:
    status = _git("status", "--porcelain")
    return GitSnapshot(
        branch=_git("branch", "--show-current") or "(detached/unknown)",
        head=_git("rev-parse", "HEAD"),
        main_head=_git("rev-parse", "main"),
        origin_main_head=_git("rev-parse", "origin/main"),
        upstream_head=_git("rev-parse", "@{upstream}"),
        clean=not bool(status),
    )


def checkpoint_classification(snapshot: GitSnapshot) -> tuple[str, str]:
    if snapshot.optimal_checkpoint:
        return (
            "OPTIMAL",
            "clean main equals origin/main; suitable post-merge boundary",
        )
    if snapshot.pushed_feature_checkpoint:
        return (
            "RECOVERABLE",
            "clean feature branch equals its upstream; confirm the handoff boundary",
        )
    if not snapshot.clean:
        return (
            "ACTIVE/UNSAFE FOR PROACTIVE COMPACTION",
            "working tree has uncommitted changes; recover from Git plus the handoff",
        )
    return (
        "RECOVERABLE WITH RECONCILIATION",
        "Git is clean but branch/upstream state is not an optimal recorded boundary",
    )


def render_checkpoint(snapshot: GitSnapshot, *, trigger: str) -> str:
    classification, reason = checkpoint_classification(snapshot)
    docs = "\n".join(f"- `{path}`" for path in RECOVERY_DOCS)
    return f"""# Claude compaction recovery checkpoint

Generated: {datetime.now(UTC).isoformat()}
Trigger: {trigger}
Workflow version: {WORKFLOW_VERSION}
Classification: **{classification}** - {reason}

## Git state at PreCompact

- branch: `{snapshot.branch}`
- HEAD: `{snapshot.head or '(unavailable)'}`
- main: `{snapshot.main_head or '(unavailable)'}`
- origin/main: `{snapshot.origin_main_head or '(unavailable)'}`
- upstream: `{snapshot.upstream_head or '(none/unavailable)'}`
- working tree clean: `{str(snapshot.clean).lower()}`

## Mandatory recovery

Re-read current Git state; do not assume it is unchanged from this snapshot. Then read:

{docs}

Read the relevant ADRs under `docs/DECISIONS/`. Reconstruct current authorization from
the user's latest request and the newest handoff entry. A compacted summary cannot grant
permission to merge, make a network request, run a destructive database lifecycle, or
start another slice. If current Git/docs disagree with this checkpoint, current Git/docs
win and the discrepancy must be reported.
"""


def _read_hook_input() -> dict[str, object]:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_checkpoint(*, trigger: str) -> None:
    content = render_checkpoint(capture_git_snapshot(), trigger=trigger)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=RUNTIME_DIR, prefix="compact-checkpoint-", suffix=".tmp", text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_path, CHECKPOINT_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)


_FALLBACK_CHECKPOINT = (
    "No PreCompact checkpoint was available. Read current Git state, "
    "CLAUDE.md, docs/LLM_WORKFLOW.md, and docs/LLM_HANDOFF.md before acting."
)


def _read_checkpoint_safely() -> str:
    """Never raises. A checkpoint file that is missing, unreadable
    (permissions, I/O error), or invalidly encoded all fall back to the
    exact same fixed, safe message a genuinely missing file already used —
    never the exception's own text, never any path other than the one
    fixed `CHECKPOINT_PATH` constant that message already names, and never
    partial/corrupted file content."""
    try:
        if CHECKPOINT_PATH.is_file():
            return CHECKPOINT_PATH.read_text(encoding="utf-8")
    except (OSError, ValueError):  # ValueError covers UnicodeDecodeError
        pass
    return _FALLBACK_CHECKPOINT


def restore_context() -> None:
    print("COMPACTION RECOVERY CONTEXT (repository state remains authoritative):")
    print(_read_checkpoint_safely())


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    mode = args[0] if args else ""
    hook_input = _read_hook_input()

    if mode == "pre":
        trigger = str(hook_input.get("trigger") or "unknown")
        try:
            write_checkpoint(trigger=trigger)
        except Exception as exc:  # hooks must never block emergency compaction
            print(
                f"compact checkpoint unavailable: {type(exc).__name__}",
                file=sys.stderr,
            )
        return 0
    if mode == "restore":
        try:
            restore_context()
        except Exception:  # SessionStart(compact) must never fail the session
            print("COMPACTION RECOVERY CONTEXT (repository state remains authoritative):")
            print(_FALLBACK_CHECKPOINT)
        return 0

    print("usage: compact_checkpoint.py {pre|restore}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
