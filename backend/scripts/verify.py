"""Canonical routine verification entry point (Workflow v3 tooling program,
slice 1: routine-verifier foundation).

Runs, in a fixed order, the checks `docs/LLM_WORKFLOW.md`'s verification
matrix already requires by hand for a "Python without schema" change
surface: Ruff format check, Ruff lint, mypy, the repository consistency
checker (`check_repo.py`, run as its own step — never assumed to be covered
merely because `tests/test_check_repo.py` also exercises its functions),
`git diff --check`, a disposable-test-database URL safety check, a real
test-database reachability preflight, an optional focused pytest selection,
then the full pytest suite.

    cd backend && python scripts/verify.py --level routine
    cd backend && python scripts/verify.py --level routine --focus tests/test_x.py::test_y

Only `--level routine` exists in this slice; `schema` and `high-risk` are
later, separately authorized slices (see docs/ROADMAP.md's revised
sequence) — passing any other value is an argparse usage error, never a
silent no-op.

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
import re
import shutil
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
    return [sys.executable, "-m", "ruff", "format", "--check", "."]


def ruff_check_command() -> list[str]:
    return [sys.executable, "-m", "ruff", "check", "."]


def mypy_command() -> list[str]:
    return [sys.executable, "-m", "mypy", "app", "tests", "scripts"]


def check_repo_command() -> list[str]:
    # `-m scripts.check_repo`, not a direct path invocation, so it resolves
    # identically regardless of caller cwd, the same way this file's own
    # imports do — see module docstring.
    return [sys.executable, "-m", "scripts.check_repo"]


def git_diff_check_command() -> list[str]:
    return ["git", "diff", "--check"]


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
    name: str, targets: list[str], basetemp: Path, runner: SubprocessRunner = _default_runner
) -> StepResult:
    command = pytest_command(targets, basetemp)
    start = time.monotonic()
    try:
        proc = runner(command, BACKEND_DIR)
    except OSError as exc:
        duration = time.monotonic() - start
        return StepResult(
            name,
            StepStatus.FAIL,
            duration,
            f"failed to launch pytest: {type(exc).__name__}",
            str(exc),
        )
    duration = time.monotonic() - start
    counts = parse_pytest_summary(proc.stdout or "")
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


def safe_rmtree(path: Path, *, must_be_under: Path) -> None:
    """Recursively deletes `path` only after confirming its *resolved*
    location is actually under `must_be_under`'s *resolved* location —
    never trusts an unresolved/relative path, and never deletes anything
    computed incorrectly (binding requirement). Raises rather than deleting
    if the check fails; deletion failures themselves are best-effort
    (`ignore_errors=True`) since this only ever runs during cleanup."""
    resolved = path.resolve()
    root = must_be_under.resolve()
    if not resolved.is_relative_to(root):
        raise RuntimeError(f"refusing to delete {resolved} — not located under {root}")
    shutil.rmtree(resolved, ignore_errors=True)


# --------------------------------------------------------------------------
# Step list construction
# --------------------------------------------------------------------------


def _build_steps(
    focus_targets: list[str],
    dev_url: str,
    test_url: str,
    run_dir: Path,
    *,
    runner: SubprocessRunner = _default_runner,
    connectivity_check: Callable[[str], None] = _real_connectivity_check,
) -> list[Step]:
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
        Step(
            "disposable test-database URL validation",
            lambda: db_url_validation_step(dev_url, test_url),
        ),
        Step(
            "test-database reachability preflight",
            lambda: db_reachability_step(test_url, connectivity_check),
        ),
    ]
    if focus_targets:
        steps.append(
            Step(
                "focused pytest",
                lambda: run_pytest_step("focused pytest", focus_targets, run_dir, runner),
            )
        )
    steps.append(
        Step("full pytest suite", lambda: run_pytest_step("full pytest suite", [], run_dir, runner))
    )
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
    return parser.parse_args(argv)


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

    run_dir = create_run_dir()
    try:
        steps = _build_steps(focus_targets, dev_url, test_url, run_dir)
        results = _run_steps(steps)
        _print_summary(results)
        return 0 if all(result.status is StepStatus.PASS for result in results) else 1
    finally:
        safe_rmtree(run_dir, must_be_under=VERIFY_TMP_ROOT)


if __name__ == "__main__":
    sys.exit(main())
