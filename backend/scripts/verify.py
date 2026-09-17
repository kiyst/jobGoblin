"""Canonical routine verification entry point (Workflow v3 tooling program,
slice 1: routine-verifier foundation; extended by the Workflow v3.1 pilot's
handoff-metadata validation, slice 0 of the pilot's own three-slice trial).

Runs, in a fixed order, the checks `docs/LLM_WORKFLOW.md`'s verification
matrix already requires by hand for a "Python without schema" change
surface: Ruff format check, Ruff lint, mypy, the repository consistency
checker (`check_repo.py`, run as its own step — never assumed to be covered
merely because `tests/test_check_repo.py` also exercises its functions),
`git diff --check` (with a command-local `safe.directory` override — see
`git_diff_check_command`), a disposable-test-database URL safety check, a
real test-database reachability preflight, an optional focused pytest
selection, the full pytest suite, this pilot's own handoff-metadata
validation step (see below), and, finally, this invocation's own
temporary-directory cleanup, itself reported as a PASS/FAIL step rather than
performed silently outside the result set (see `cleanup_run_dir_step`).

Ruff format/lint and mypy also cover `.claude/hooks/` (see
`CLAUDE_HOOKS_DIR`) — real, type-annotated Python this project owns, even
though it lives outside `backend/` and outside the shipped `app` package.

    cd backend && python scripts/verify.py --level routine
    cd backend && python scripts/verify.py --level routine --focus tests/test_x.py::test_y
    cd backend && python scripts/verify.py --level routine --docs-only

Only `--level routine` exists in this slice; `schema` and `high-risk` are
later, separately authorized slices (see docs/ROADMAP.md's revised
sequence) — passing any other value is an argparse usage error, never a
silent no-op.

**`--docs-only`** (Workflow v3.1 pilot): for a genuinely documentation-only
change, skips the disposable-database steps and the full/focused pytest
steps entirely (reported `NOT RUN`, never silently omitted) — `--focus`
and `--docs-only` are mutually exclusive, since focusing tests implies
running them. The handoff-metadata step (below) then requires
`docs/LLM_HANDOFF.md`'s newest `Work done` entry to declare
`verification_level: not_run`, so a docs-only invocation can never be used
to silently paper over a stale or fabricated test count.

**Handoff-metadata validation** (Workflow v3.1 pilot, `scripts/
check_handoff.py`): a required step (never optional, never skippable) that
reads `docs/LLM_HANDOFF.md`'s newest `Work done` entry's structured
`workflow-metadata` block and cross-checks it against what *this exact
invocation* just observed — the full-suite count, the focused-test count
and selector (when `--focus` was used), and (for `slice_kind: parser`) that
`--focus` was used at all and its selector matches the declared one. This
comparison reuses the counts this same run's own pytest step(s) already
parsed — it never launches a second pytest or `verify.py` subprocess to
re-derive them, and it never asserts anything about the underlying slice's
semantic correctness, only whether the block's mechanically-derivable
claims match reality.

Every step that runs a separate tool is invoked as `[sys.executable, "-m",
...]` — never a bare `ruff`/`mypy`/`pytest` resolved from `PATH`, never
`shell=True`, never a shell string built by concatenation — so the exact
same argument list runs unmodified on Windows and Linux, using whichever
Python environment this script was itself invoked with. `git diff --check`
is the one necessary exception: git is not a Python module.

Paths resolve from this file's own location (matching `check_repo.py`'s own
convention), not the caller's current working directory — invoking this
from `backend/` or from the repository root produces identical behavior.

Every required step is reported as PASS, FAIL, or NOT RUN with a duration —
never silently omitted, never labeled passing because it was skipped. Once
a step fails, every later step is reported NOT RUN rather than attempted;
this script never continues past a failure to save time at the cost of an
inaccurate report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent
TESTS_DIR = BACKEND_DIR / "tests"
VERIFY_TMP_ROOT = BACKEND_DIR / ".verify-tmp"

# Outside `backend/` entirely (repository-root Claude Code tooling, not part
# of the shipped application), but still real, type-annotated Python this
# project owns — Ruff/mypy must cover it too, not just `app`/`tests`/
# `scripts`. Confirmed empirically that both tools resolve `backend/
# pyproject.toml`'s own config (line length, target version, mypy strictness)
# for a path outside `backend/` when invoked with `cwd=BACKEND_DIR`, exactly
# as they already do for every in-tree target below — no separate config
# file is needed at the repository root.
CLAUDE_HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"

# This file is documented and invoked as a direct script
# (`python scripts/verify.py`), not as `python -m scripts.verify` — a direct
# script invocation puts only this file's own directory (`backend/scripts/`)
# on `sys.path`, not `backend/` itself, so `app.*`/`scripts.*` absolute
# imports below would otherwise fail. Explicitly ensuring `BACKEND_DIR` is on
# `sys.path` first makes this work identically under a direct-script
# invocation, `-m scripts.verify` from `backend/`, or `-m` from elsewhere.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings, get_settings  # noqa: E402
from app.db.session import check_database_connection  # noqa: E402
from scripts import check_handoff  # noqa: E402
from scripts.db_safety import (  # noqa: E402
    assert_is_disposable_test_database,
    redact_database_url,
    resolve_test_database_url,
)


class StepStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT RUN"


@dataclass(frozen=True)
class StepResult:
    name: str
    status: StepStatus
    duration_seconds: float
    detail: str = ""
    raw_output: str | None = None


@dataclass(frozen=True)
class Step:
    """One verification step. `run` is a zero-argument closure so the full
    step list can be *constructed* (for order/structure testing) without
    *executing* any of them — see `_build_steps` and `test_verify.py`."""

    name: str
    run: Callable[[], StepResult]


# A `subprocess.run` call, wrapped behind a type alias so tests can inject a
# fake runner and never launch a real process (binding requirement: no test
# may cause a real `pytest` subprocess to run the full suite recursively).
SubprocessRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def _default_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


# --------------------------------------------------------------------------
# Command construction — pure, no execution, trivially unit-testable.
# --------------------------------------------------------------------------


def ruff_format_command() -> list[str]:
    return [sys.executable, "-m", "ruff", "format", "--check", ".", str(CLAUDE_HOOKS_DIR)]


def ruff_check_command() -> list[str]:
    return [sys.executable, "-m", "ruff", "check", ".", str(CLAUDE_HOOKS_DIR)]


def mypy_command() -> list[str]:
    return [sys.executable, "-m", "mypy", "app", "tests", "scripts", str(CLAUDE_HOOKS_DIR)]


def check_repo_command() -> list[str]:
    # `-m scripts.check_repo`, not a direct path invocation, so it resolves
    # identically regardless of caller cwd, the same way this file's own
    # imports do — see module docstring.
    return [sys.executable, "-m", "scripts.check_repo"]


def git_diff_check_command() -> list[str]:
    """`-c safe.directory=<REPO_ROOT>` is command-local — scoped to this one
    `git` invocation via `-c`, never written to any global/user Git config —
    required because some environments this script runs in (confirmed:
    the Codex reviewer's own checkout) refuse to operate on this repository
    at all ("detected dubious ownership") without it. `REPO_ROOT` is always
    this script's own derived absolute path (never hardcoded), rendered with
    forward slashes via `Path.as_posix()` since Git's config-value parser
    treats a bare backslash as an escape character — a Windows path's native
    backslashes would otherwise be misparsed."""
    return ["git", "-c", f"safe.directory={REPO_ROOT.as_posix()}", "diff", "--check"]


def pytest_command(targets: list[str], basetemp: Path) -> list[str]:
    return [sys.executable, "-m", "pytest", "-q", f"--basetemp={basetemp}", *targets]


# --------------------------------------------------------------------------
# Pytest summary parsing
# --------------------------------------------------------------------------

# Matches pytest 8.3.4's final summary line's core content *after* stripping
# any `=` framing/whitespace and isolating the trailing "in <N.NN>s" — e.g.
# "1176 passed" from "============ 1176 passed in 108.02s ============", or
# "2 failed, 1174 passed, 3 skipped" from the unframed `-q` form
# "2 failed, 1174 passed, 3 skipped in 12.34s". Longer runs additionally
# append a parenthesized `H:MM:SS` breakdown — e.g.
# "1235 passed in 101.82s (0:01:41)" — confirmed empirically against this
# suite's own full-suite run, which crossed pytest's threshold for showing
# it; the trailing group is optional so both shapes match. Deliberately
# narrow: a summary line this doesn't recognize reports as unavailable
# rather than guessing (see `parse_pytest_summary`'s own docstring).
_DURATION_SUFFIX_RE = re.compile(r"^(?P<body>.*?)\s+in\s+\d+\.\d+s(?:\s+\(\d+:\d+:\d+\))?$")
_COUNT_PART_RE = re.compile(r"^(\d+)\s+([A-Za-z][A-Za-z-]*)$")


def parse_pytest_summary(output: str) -> dict[str, int] | None:
    """Parses pytest's own final summary line (e.g. `1176 passed`,
    `2 failed, 1174 passed, 3 skipped`, `1 error`, `5 deselected`), scanning
    from the *last* non-blank line backward so a warnings-summary section
    heading earlier in the output is never mistaken for the real result.
    Works with both the framed (`===... X in Y.YYs ...===`, default
    verbosity) and unframed (`X in Y.YYs`, `-q`) shapes pytest 8.3.4
    produces — this project always invokes pytest with `-q` (see
    `pytest_command`), but the parser accepts either so it stays correct if
    that ever changes.

    Returns `None` if no line matches the expected shape at all, or if any
    comma-separated part of a matching line isn't a `<count> <word>` pair —
    callers must report counts as **unavailable** in that case, never
    invent zero or silently omit the field (binding requirement)."""
    for line in reversed(output.splitlines()):
        candidate = line.strip().strip("=").strip()
        if not candidate:
            continue
        match = _DURATION_SUFFIX_RE.match(candidate)
        if not match:
            continue
        body = match.group("body").strip()
        if not body:
            return None
        counts: dict[str, int] = {}
        for part in body.split(","):
            part = part.strip()
            count_match = _COUNT_PART_RE.match(part)
            if not count_match:
                return None
            counts[count_match.group(2)] = int(count_match.group(1))
        return counts
    return None


# --------------------------------------------------------------------------
# Step execution
# --------------------------------------------------------------------------

_MAX_CAPTURED_OUTPUT = 8000  # characters printed on failure — enough to debug, not to flood


def _subprocess_step(
    name: str, command: list[str], cwd: Path, runner: SubprocessRunner = _default_runner
) -> StepResult:
    start = time.monotonic()
    try:
        proc = runner(command, cwd)
    except OSError as exc:
        duration = time.monotonic() - start
        return StepResult(
            name, StepStatus.FAIL, duration, f"failed to launch: {type(exc).__name__}", str(exc)
        )
    duration = time.monotonic() - start
    if proc.returncode == 0:
        return StepResult(name, StepStatus.PASS, duration, "ok")
    combined = (proc.stdout or "") + (proc.stderr or "")
    return StepResult(
        name,
        StepStatus.FAIL,
        duration,
        f"exit code {proc.returncode}",
        combined[-_MAX_CAPTURED_OUTPUT:],
    )


def _format_counts(counts: dict[str, int] | None) -> str:
    if counts is None:
        return "counts unavailable (summary line not recognized)"
    return ", ".join(f"{value} {key}" for key, value in counts.items())


def run_pytest_step(
    name: str,
    targets: list[str],
    basetemp: Path,
    runner: SubprocessRunner = _default_runner,
    *,
    counts_sink: dict[str, dict[str, int] | None] | None = None,
    counts_key: str = "",
) -> StepResult:
    """`counts_sink`/`counts_key` are an optional side-channel: when given,
    this step's parsed pytest counts are also written into
    `counts_sink[counts_key]` (as `None` if the summary line couldn't be
    parsed) — how the handoff-metadata step below reads *this same run's*
    actual counts without launching a second pytest subprocess to re-derive
    them."""
    command = pytest_command(targets, basetemp)
    start = time.monotonic()
    try:
        proc = runner(command, BACKEND_DIR)
    except OSError as exc:
        duration = time.monotonic() - start
        if counts_sink is not None:
            counts_sink[counts_key] = None
        return StepResult(
            name,
            StepStatus.FAIL,
            duration,
            f"failed to launch pytest: {type(exc).__name__}",
            str(exc),
        )
    duration = time.monotonic() - start
    counts = parse_pytest_summary(proc.stdout or "")
    if counts_sink is not None:
        counts_sink[counts_key] = counts
    detail = _format_counts(counts)
    if proc.returncode == 0:
        return StepResult(name, StepStatus.PASS, duration, detail)
    combined = (proc.stdout or "") + (proc.stderr or "")
    return StepResult(name, StepStatus.FAIL, duration, detail, combined[-_MAX_CAPTURED_OUTPUT:])


def db_url_validation_step(dev_url: str, test_url: str) -> StepResult:
    """Pure URL parsing/comparison — no network connection. The development
    database does not need to be reachable for this step; only its
    configured URL needs to be parsed and compared against the test
    target (binding requirement).

    Catches any exception, not just the guard's own `RuntimeError`: a
    malformed URL (missing `://`, unparseable entirely) makes
    `sqlalchemy.engine.make_url` raise `sqlalchemy.exc.ArgumentError`
    instead — confirmed by actually running this step against a malformed
    `TEST_DATABASE_URL`, which otherwise crashed the whole script with an
    uncaught traceback. Reports only the exception *type* name, never
    `str(exc)`: `ArgumentError`'s own message echoes the original
    unparseable input verbatim, which could otherwise echo back
    credential-like content the same way a leaked raw URL would."""
    name = "disposable test-database URL validation"
    start = time.monotonic()
    try:
        assert_is_disposable_test_database(test_url, dev_url)
    except RuntimeError as exc:
        duration = time.monotonic() - start
        return StepResult(name, StepStatus.FAIL, duration, str(exc))
    except Exception as exc:  # noqa: BLE001 - reported as a step failure, never re-raised
        duration = time.monotonic() - start
        return StepResult(
            name, StepStatus.FAIL, duration, f"failed to parse database URLs: {type(exc).__name__}"
        )
    duration = time.monotonic() - start
    return StepResult(
        name, StepStatus.PASS, duration, f"test target: {redact_database_url(test_url)}"
    )


def _real_connectivity_check(test_url: str) -> None:
    """Raises if the test database is unreachable. Uses the test URL only —
    never the development URL — via a throwaway `Settings` override, the
    same pattern `tests/conftest.py::unreachable_settings` already uses."""
    settings = Settings(database_url=test_url, database_connect_timeout_seconds=5.0)
    asyncio.run(check_database_connection(settings))


def db_reachability_step(
    test_url: str, connectivity_check: Callable[[str], None] = _real_connectivity_check
) -> StepResult:
    """The disposable test database must be reachable before pytest begins
    (binding requirement) — this is checked as its own step, never inferred
    from pytest's own eventual per-test connection failures, so an
    unreachable database is reported as one clear FAIL instead of a wall of
    unrelated-looking pytest errors."""
    name = "test-database reachability preflight"
    start = time.monotonic()
    try:
        connectivity_check(test_url)
    except Exception as exc:  # noqa: BLE001 - reported as a step failure, never re-raised
        duration = time.monotonic() - start
        # Exception type name only — never the raw exception message, which
        # some drivers embed the connection string inside (matches this
        # project's existing "exception type name only" logging posture).
        return StepResult(
            name,
            StepStatus.FAIL,
            duration,
            f"{redact_database_url(test_url)} unreachable: {type(exc).__name__}",
        )
    duration = time.monotonic() - start
    return StepResult(name, StepStatus.PASS, duration, f"{redact_database_url(test_url)} reachable")


def handoff_metadata_step() -> StepResult:
    """Workflow v3.2: validates `docs/LLM_HANDOFF.md`'s newest `Work done`
    entry's structured metadata block (schema v2 -- pending/published, see
    `scripts/check_handoff.py`). Purely structural: never launches a
    subprocess, never cross-checks a hand-typed count against this run's
    own pytest output -- that anti-fabrication role is now played by the
    receipt (built and self-verified by `verification_coordinator.py`),
    never by comparing prose numbers to a second observation."""
    name = "handoff metadata validation"
    start = time.monotonic()
    try:
        check_handoff.validate_handoff()
    except check_handoff.HandoffValidationError as exc:
        duration = time.monotonic() - start
        return StepResult(name, StepStatus.FAIL, duration, str(exc))
    duration = time.monotonic() - start
    return StepResult(name, StepStatus.PASS, duration, "ok")


def _development_state_to_dict(state: object) -> dict[str, object]:
    from scripts.migration_matrix import DevelopmentState

    if not isinstance(state, DevelopmentState):
        return {}
    return {
        "alembic_revision": state.alembic_revision,
        "schema_fingerprint": state.schema_fingerprint,
    }


def migration_matrix_step(
    dev_url: str, test_url: str, *, migration_sink: dict[str, object] | None = None
) -> StepResult:
    """Workflow v3.2: the complete migration/schema-change verification
    matrix (`scripts.migration_matrix.run_full_matrix`) -- only added to
    the step list when the caller (normally the coordinator, which
    computes this from the candidate's `base_sha..candidate_sha` diff
    *before* any step runs) determines a migration/model path actually
    changed. A raised `MigrationMatrixError` here is a hard step failure,
    never a soft warning; no receipt may be issued past it. `migration_sink`
    (when given) is populated with the full evidence -- development state
    before/after, the real PostgreSQL server version, and the fresh-
    database lifecycle -- so the receipt can record it, never just a bare
    `triggered: true` with no evidence."""
    name = "migration matrix"
    start = time.monotonic()
    from scripts.migration_matrix import MigrationMatrixError, run_full_matrix

    try:
        settings = get_settings()
        result = asyncio.run(run_full_matrix(dev_url, test_url, app_env=settings.app_env))
    except MigrationMatrixError as exc:
        duration = time.monotonic() - start
        if migration_sink is not None:
            migration_sink["triggered"] = True
            migration_sink["status"] = "FAIL"
            migration_sink["detail"] = str(exc)
        return StepResult(name, StepStatus.FAIL, duration, str(exc))
    duration = time.monotonic() - start
    if migration_sink is not None:
        migration_sink["triggered"] = True
        migration_sink["status"] = "PASS"
        migration_sink["dev_state_before"] = _development_state_to_dict(result.dev_state_before)
        migration_sink["dev_state_after"] = _development_state_to_dict(result.dev_state_after)
        migration_sink["postgresql_server_version"] = result.postgresql_server_version
        migration_sink["fresh_database_created"] = result.fresh_database_created
        migration_sink["fresh_database_cleaned_up"] = result.fresh_database_cleaned_up
        migration_sink["steps"] = list(result.steps)
    return StepResult(name, StepStatus.PASS, duration, result.detail)


def mutation_witness_command(guard_ref: str | None) -> list[str]:
    command = [sys.executable, "-m", "scripts.contract_mutation_witnesses"]
    if guard_ref is not None:
        command.extend(["--guard", guard_ref])
    return command


_WITNESS_SUMMARY_RE = re.compile(r"^PASS (?P<ref>\S+)$", re.MULTILINE)
_WITNESS_FAIL_RE = re.compile(r"^FAIL (?P<ref>\S+)", re.MULTILINE)


def mutation_witnesses_step(
    guard_refs: list[str], runner: SubprocessRunner = _default_runner
) -> tuple[StepResult, dict[str, int], list[str]]:
    """Runs `contract_mutation_witnesses.py` once per selected guard (the
    existing single-guard CLI is never modified) and aggregates the
    results here. `guard_refs` empty means "run every currently active
    guard" -- discovered dynamically by the script itself via
    `tests.contracts.taxonomy.active_guards()`, never a hardcoded count.
    Also returns the actual guard refs genuinely exercised this run (for
    the whole-registry case, parsed from that subprocess's own per-guard
    `PASS <ref>`/`FAIL <ref>` lines -- never a caller-supplied count taken
    on faith)."""
    name = "contract mutation witnesses"
    start = time.monotonic()
    targets: list[str | None] = list(guard_refs) if guard_refs else [None]
    passed = 0
    failed: list[str] = []
    guard_refs_ran: list[str] = []
    combined_output = ""
    for ref in targets:
        proc = runner(mutation_witness_command(ref), BACKEND_DIR)
        combined_output += (proc.stdout or "") + (proc.stderr or "")
        if ref is None:
            # Whole-registry invocation: parse its own aggregate summary line.
            match = re.search(r"(\d+) passed, (\d+) failed", proc.stdout or "")
            if match:
                passed += int(match.group(1))
                failed.extend(re.findall(r"^FAIL (\S+)", proc.stdout or "", re.MULTILINE))
            elif proc.returncode != 0:
                failed.append("(unparseable whole-registry run)")
            guard_refs_ran.extend(_WITNESS_SUMMARY_RE.findall(proc.stdout or ""))
            guard_refs_ran.extend(_WITNESS_FAIL_RE.findall(proc.stdout or ""))
        else:
            guard_refs_ran.append(ref)
            if proc.returncode == 0 and f"PASS {ref}" in (proc.stdout or ""):
                passed += 1
            else:
                failed.append(ref)
    duration = time.monotonic() - start
    counts = {"passed": passed, "failed": len(failed)}
    guard_refs_ran = sorted(set(guard_refs_ran))
    if failed:
        detail = f"{passed} passed, {len(failed)} failed: {failed}"
        return (StepResult(name, StepStatus.FAIL, duration, detail), counts, guard_refs_ran)
    return (
        StepResult(name, StepStatus.PASS, duration, f"{passed} passed, 0 failed"),
        counts,
        guard_refs_ran,
    )


def _run_steps(steps: list[Step]) -> list[StepResult]:
    results: list[StepResult] = []
    blocked = False
    for step in steps:
        if blocked:
            results.append(
                StepResult(step.name, StepStatus.NOT_RUN, 0.0, "blocked by an earlier failure")
            )
            continue
        result = step.run()
        results.append(result)
        if result.status is StepStatus.FAIL:
            blocked = True
    return results


def _print_summary(results: list[StepResult]) -> None:
    print()
    print("=== verify.py --level routine summary ===")
    for result in results:
        prefix = f"[{result.status.value:<7}] {result.name}"
        suffix = f"({result.duration_seconds:.2f}s) - {result.detail}"
        print(f"{prefix} {suffix}")
        if result.status is StepStatus.FAIL and result.raw_output:
            print("----- output -----")
            print(result.raw_output)
            print("-------------------")
    passed = sum(1 for r in results if r.status is StepStatus.PASS)
    failed = sum(1 for r in results if r.status is StepStatus.FAIL)
    not_run = sum(1 for r in results if r.status is StepStatus.NOT_RUN)
    total_duration = sum(r.duration_seconds for r in results)
    print("-------------------------------------------")
    if failed == 0 and not_run == 0:
        print(f"ALL {passed} CHECKS PASSED in {total_duration:.2f}s")
    else:
        print(
            f"{passed} passed, {failed} failed, {not_run} not run, "
            f"out of {len(results)} in {total_duration:.2f}s"
        )


# --------------------------------------------------------------------------
# Focus-target validation
# --------------------------------------------------------------------------


class FocusValidationError(ValueError):
    """A `--focus` target failed validation before any step ran."""


def validate_focus_target(target: str) -> str:
    """Accepts a bare file path or a `path::node_id` pytest target,
    identical to the syntax existing `Work done` entries already use.
    Returns `target` unchanged (it is passed to pytest exactly as given,
    never rewritten) after confirming it:

    - does not begin with `-` (never disguises an extra pytest flag);
    - resolves, via its portion before `::`, to a real file located under
      `backend/tests` (never `../`-escapes it or points elsewhere).
    """
    if target.startswith("-"):
        raise FocusValidationError(f"--focus target {target!r} must not begin with '-'")
    file_part = target.split("::", 1)[0]
    if not file_part:
        raise FocusValidationError(f"--focus target {target!r} has no file portion before '::'")
    resolved = (BACKEND_DIR / file_part).resolve()
    tests_root = TESTS_DIR.resolve()
    if not resolved.is_relative_to(tests_root) or not resolved.is_file():
        raise FocusValidationError(
            f"--focus target {target!r} does not resolve to a file under "
            f"{tests_root.relative_to(REPO_ROOT)}"
        )
    return target


# --------------------------------------------------------------------------
# Temporary-directory safety
# --------------------------------------------------------------------------


def _clear_readonly_and_retry(
    func: Callable[[str], None], target_path: str, exc_info: BaseException
) -> None:
    """`shutil.rmtree`'s `onexc` handler: a real Git repository's loose
    object files are created read-only (a deliberate Git safeguard against
    accidental corruption) -- on Windows this makes the *default*
    `shutil.rmtree` fail with `PermissionError` the moment cleanup reaches
    one, something this project's own test suite started doing the moment
    it began creating disposable Git repositories under a cleaned-up run
    directory (see `test_verification_worktree.py`/`test_check_review.py`/
    `test_verification_coordinator.py`). Clearing the read-only bit and
    retrying the exact failed operation is the standard, narrow fix -- it
    never suppresses a genuinely different failure, since `func` is called
    again and any other error still propagates."""
    os.chmod(target_path, stat.S_IWRITE)
    func(target_path)


def _default_remove(path: Path) -> None:
    shutil.rmtree(path, onexc=_clear_readonly_and_retry)


def safe_rmtree(
    path: Path, *, must_be_under: Path, remove: Callable[[Path], None] = _default_remove
) -> None:
    """Recursively deletes `path` only after confirming its *resolved*
    location is a **strict child** of `must_be_under`'s *resolved* location —
    never `must_be_under` itself, and never anything not actually located
    under it. Never trusts an unresolved/relative path, and never deletes
    anything computed incorrectly (binding requirement).

    Raises rather than deleting if either check fails. Deletion failures are
    never swallowed: `remove` (real default: `shutil.rmtree`, no
    `ignore_errors`) is called directly, so a permission error or any other
    failure propagates to the caller rather than being silently discarded —
    a verifier run that reports success while actually failing to clean up
    would reproduce the exact stale-directory problem this tool exists to
    eliminate. `remove` is injectable so tests can prove a deletion failure
    is genuinely surfaced without depending on real, unreliable-to-simulate
    filesystem permission behavior."""
    resolved = path.resolve()
    root = must_be_under.resolve()
    if resolved == root:
        raise RuntimeError(f"refusing to delete {resolved} — that is the root itself, not a child")
    if not resolved.is_relative_to(root):
        raise RuntimeError(f"refusing to delete {resolved} — not located under {root}")
    remove(resolved)


def cleanup_run_dir_step(
    run_dir: Path, *, remove: Callable[[Path], None] = _default_remove
) -> StepResult:
    """Reports this invocation's temporary-directory cleanup as its own
    PASS/FAIL step (binding requirement) — never silently performed outside
    the reported result set, and never assumed to have succeeded merely
    because it was attempted."""
    name = "temporary-directory cleanup"
    start = time.monotonic()
    try:
        safe_rmtree(run_dir, must_be_under=VERIFY_TMP_ROOT, remove=remove)
    except Exception as exc:  # noqa: BLE001 - reported as a step failure, never re-raised
        duration = time.monotonic() - start
        return StepResult(
            name, StepStatus.FAIL, duration, f"failed to remove {run_dir}: {type(exc).__name__}"
        )
    duration = time.monotonic() - start
    return StepResult(name, StepStatus.PASS, duration, f"removed {run_dir}")


# --------------------------------------------------------------------------
# Step list construction
# --------------------------------------------------------------------------


def _build_steps(
    focus_targets: list[str],
    dev_url: str,
    test_url: str,
    run_dir: Path,
    *,
    docs_only: bool = False,
    gate: str | None = None,
    witness_refs: list[str] | None = None,
    migration_required: bool = False,
    runner: SubprocessRunner = _default_runner,
    connectivity_check: Callable[[str], None] = _real_connectivity_check,
    witness_counts_sink: dict[str, int] | None = None,
    witness_guard_refs_sink: list[str] | None = None,
    migration_sink: dict[str, object] | None = None,
) -> list[Step]:
    # Shared across the focused/full pytest steps below and the trailing
    # handoff-metadata step — populated as a side effect of `run_pytest_step`
    # (via `counts_sink`), so the handoff-metadata step reads *this same
    # run's* actual counts without launching a second pytest subprocess.
    pytest_counts: dict[str, dict[str, int] | None] = {}

    steps = [
        Step(
            "ruff format --check",
            lambda: _subprocess_step(
                "ruff format --check", ruff_format_command(), BACKEND_DIR, runner
            ),
        ),
        Step(
            "ruff check",
            lambda: _subprocess_step("ruff check", ruff_check_command(), BACKEND_DIR, runner),
        ),
        Step("mypy", lambda: _subprocess_step("mypy", mypy_command(), BACKEND_DIR, runner)),
        Step(
            "check_repo.py",
            lambda: _subprocess_step("check_repo.py", check_repo_command(), BACKEND_DIR, runner),
        ),
        Step(
            "git diff --check",
            lambda: _subprocess_step(
                "git diff --check", git_diff_check_command(), REPO_ROOT, runner
            ),
        ),
    ]
    if not docs_only:
        steps.append(
            Step(
                "disposable test-database URL validation",
                lambda: db_url_validation_step(dev_url, test_url),
            )
        )
        steps.append(
            Step(
                "test-database reachability preflight",
                lambda: db_reachability_step(test_url, connectivity_check),
            )
        )
        if focus_targets:
            steps.append(
                Step(
                    "focused pytest",
                    lambda: run_pytest_step(
                        "focused pytest",
                        focus_targets,
                        run_dir,
                        runner,
                        counts_sink=pytest_counts,
                        counts_key="focused",
                    ),
                )
            )
        if gate != "fast":
            # --gate fast omits the full suite entirely -- only the
            # computed focused coverage (above) and selected active
            # witnesses (below) run. --gate final (or no --gate, the
            # compat profile) always runs the full suite.
            steps.append(
                Step(
                    "full pytest suite",
                    lambda: run_pytest_step(
                        "full pytest suite",
                        [],
                        run_dir,
                        runner,
                        counts_sink=pytest_counts,
                        counts_key="full",
                    ),
                )
            )
    if gate in ("fast", "final"):

        def _run_witnesses() -> StepResult:
            refs = list(witness_refs or []) if gate == "fast" else []
            result, counts, guard_refs_ran = mutation_witnesses_step(refs, runner)
            if witness_counts_sink is not None:
                witness_counts_sink.update(counts)
            if witness_guard_refs_sink is not None:
                witness_guard_refs_sink.extend(guard_refs_ran)
            return result

        steps.append(Step("contract mutation witnesses", _run_witnesses))

    if migration_required and not docs_only:
        steps.append(
            Step(
                "migration matrix",
                lambda: migration_matrix_step(dev_url, test_url, migration_sink=migration_sink),
            )
        )

    steps.append(Step("handoff metadata validation", handoff_metadata_step))
    return steps


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="Canonical verification entry point (Workflow v3 tooling program).",
    )
    parser.add_argument(
        "--level",
        choices=["routine"],
        required=True,
        help="Only 'routine' exists in this slice; 'schema'/'high-risk' are later slices.",
    )
    parser.add_argument(
        "--focus",
        nargs="+",
        default=None,
        metavar="TARGET",
        help="Optional pytest file paths and/or node IDs to run before the full suite.",
    )
    parser.add_argument(
        "--docs-only",
        action="store_true",
        help=(
            "For a genuinely documentation-only change, skips the disposable-database steps "
            "and the full/focused pytest steps entirely (reported NOT RUN). Mutually exclusive "
            "with --focus, since focusing tests implies running them."
        ),
    )
    parser.add_argument(
        "--gate",
        choices=["fast", "final", "docs"],
        default=None,
        help=(
            "Workflow v3.2: receipt-eligible verification profile. Omitted entirely, this "
            "invocation runs in the ordinary (compat) mode unchanged from before this "
            "activation slice -- no mutation-witness step, not receipt-eligible. Normally "
            "invoked by scripts/verification_coordinator.py from inside a disposable detached "
            "worktree, never directly against the mutable authoring checkout for a real "
            "receipt-issuing run."
        ),
    )
    parser.add_argument(
        "--witness",
        nargs="+",
        default=None,
        metavar="GUARD_REF",
        help="With --gate fast: the specific mutation-witness guard refs to run (the affected-"
        "surface-computed set plus any additions). Ignored for --gate final, which always runs "
        "every currently active guard.",
    )
    parser.add_argument(
        "--emit-step-json",
        default=None,
        metavar="PATH",
        help="Write this invocation's step results and parsed counts as JSON to PATH -- how "
        "scripts/verification_coordinator.py reads a worktree-isolated run's results without "
        "scraping console text.",
    )
    parser.add_argument(
        "--migration-required",
        action="store_true",
        help="Adds the 'migration matrix' step (scripts.migration_matrix.run_full_matrix). Set "
        "only by a caller that has already computed, from the candidate's base_sha..candidate_sha "
        "diff, that a migration/model path actually changed -- never inferred by this script "
        "itself.",
    )
    parser.add_argument(
        "--compat-v3.1",
        dest="compat_v3_1",
        action="store_true",
        help="The explicitly named Workflow v3.2 compatibility profile: reproduces exactly the "
        "pre-activation v3.1 check set (identical step list to omitting --gate) using the "
        "current code -- an honest substitute proving equivalent coverage, since the true "
        "pre-activation binary cannot run against code that postdates it. Mutually exclusive "
        "with --gate.",
    )
    args = parser.parse_args(argv)
    if args.docs_only and args.focus:
        parser.error("--docs-only and --focus are mutually exclusive")
    if args.gate == "docs" and not args.docs_only:
        parser.error("--gate docs requires --docs-only (the two must always be given together)")
    if args.docs_only and args.gate != "docs":
        parser.error("--docs-only requires --gate docs (the two must always be given together)")
    if args.compat_v3_1 and args.gate is not None:
        parser.error("--compat-v3.1 and --gate are mutually exclusive")
    return args


def create_run_dir() -> Path:
    """Creates and returns a fresh, uniquely-named directory under
    `VERIFY_TMP_ROOT` for exactly one invocation of this script.
    `tempfile.mkdtemp` guarantees the returned directory did not already
    exist and is atomically created, so two concurrent invocations (e.g.
    two terminals running `verify.py` at once) always receive two distinct
    directories — never a collision, and never one run's cleanup deleting
    the other's still-active files (binding requirement)."""
    VERIFY_TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=str(VERIFY_TMP_ROOT)))


def _execute_and_cleanup(
    steps: list[Step], run_dir: Path, *, remove: Callable[[Path], None] = _default_remove
) -> list[StepResult]:
    """Runs `steps`, then *always* attempts this invocation's temporary-
    directory cleanup — including when an earlier step failed (binding
    requirement: cleanup is never skipped just because verification already
    failed) — and appends its own PASS/FAIL result to the returned list
    rather than performing it silently outside the reported results."""
    results: list[StepResult] = []
    try:
        results = _run_steps(steps)
    finally:
        results.append(cleanup_run_dir_step(run_dir, remove=remove))
    return results


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        focus_targets = [validate_focus_target(t) for t in (args.focus or [])]
    except FocusValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    settings = get_settings()
    dev_url = settings.database_url
    test_url = resolve_test_database_url(settings.test_database_url)

    if args.compat_v3_1:
        print("=== Workflow v3.2 compatibility profile (--compat-v3.1) ===")

    run_dir = create_run_dir()
    witness_counts: dict[str, int] = {}
    witness_guard_refs: list[str] = []
    migration_evidence: dict[str, object] = {}
    steps = _build_steps(
        focus_targets,
        dev_url,
        test_url,
        run_dir,
        docs_only=args.docs_only,
        gate=args.gate,
        witness_refs=args.witness,
        migration_required=args.migration_required,
        witness_counts_sink=witness_counts,
        witness_guard_refs_sink=witness_guard_refs,
        migration_sink=migration_evidence,
    )
    results = _execute_and_cleanup(steps, run_dir)

    _print_summary(results)

    if args.emit_step_json:
        _write_step_json(
            Path(args.emit_step_json),
            results,
            witness_counts,
            focus_targets,
            profile="compat-v3.1" if args.compat_v3_1 else (args.gate or "ungated"),
            migration_evidence=migration_evidence,
            witness_guard_refs=witness_guard_refs,
        )

    # A failed cleanup makes the overall exit nonzero too — every result,
    # including the cleanup step's own, must be PASS (binding requirement).
    return 0 if all(result.status is StepStatus.PASS for result in results) else 1


def _write_step_json(
    path: Path,
    results: list[StepResult],
    witness_counts: dict[str, int],
    focus_targets: list[str],
    *,
    profile: str = "ungated",
    migration_evidence: dict[str, object] | None = None,
    witness_guard_refs: list[str] | None = None,
) -> None:
    def _find(name: str) -> StepResult | None:
        return next((r for r in results if r.name == name), None)

    focused = _find("focused pytest")
    full = _find("full pytest suite")
    payload = {
        "profile": profile,
        "steps": [
            {"name": r.name, "status": r.status.value, "duration_seconds": r.duration_seconds}
            for r in results
        ],
        "full_suite": (
            {"status": "ran", "count": _parse_passed(full)} if full else {"status": "not_run"}
        ),
        "focused_tests": (
            {"status": "ran", "selector": " ".join(focus_targets), "count": _parse_passed(focused)}
            if focused
            else {"status": "not_run"}
        ),
        "mutation_witnesses": (
            {
                "status": "ran",
                "guard_refs": sorted(witness_guard_refs) if witness_guard_refs else [],
                "passed": witness_counts.get("passed", 0),
                "failed": witness_counts.get("failed", 0),
            }
            if witness_counts
            else {"status": "not_run"}
        ),
        "migration_matrix": (
            dict(migration_evidence) if migration_evidence else {"triggered": False}
        ),
        "all_passed": all(r.status is StepStatus.PASS for r in results),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _parse_passed(result: StepResult) -> int | None:
    match = re.search(r"(\d+) passed", result.detail)
    return int(match.group(1)) if match else None


if __name__ == "__main__":
    sys.exit(main())
