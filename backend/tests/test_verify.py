"""Unit tests for `scripts/verify.py`.

Every test here injects or monkeypatches the subprocess runner and/or the
database connectivity check — **no test in this file ever launches a real
subprocess**, and specifically never a real `pytest` subprocess, which
would otherwise recursively re-run the full suite (including this very
test) from inside itself. The genuine end-to-end
`python scripts/verify.py --level routine` invocation is a separate,
external verification step documented in `docs/LLM_HANDOFF.md`'s `Work
done` entry for this slice — it is never invoked from within `pytest`.

Accordingly, `verify.main()` itself is never called anywhere in this file;
every smaller unit it composes (command builders, step-execution functions,
`_build_steps`, `_run_steps`, the summary parser, focus validation, and the
temp-directory safety guard) is tested directly and independently instead.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from scripts import verify

# --------------------------------------------------------------------------
# Command construction
# --------------------------------------------------------------------------


def test_ruff_format_command_uses_sys_executable_module_invocation() -> None:
    assert verify.ruff_format_command() == [
        sys.executable,
        "-m",
        "ruff",
        "format",
        "--check",
        ".",
        str(verify.CLAUDE_HOOKS_DIR),
    ]


def test_ruff_check_command_uses_sys_executable_module_invocation() -> None:
    assert verify.ruff_check_command() == [
        sys.executable,
        "-m",
        "ruff",
        "check",
        ".",
        str(verify.CLAUDE_HOOKS_DIR),
    ]


def test_mypy_command_covers_app_tests_scripts_and_claude_hooks() -> None:
    assert verify.mypy_command() == [
        sys.executable,
        "-m",
        "mypy",
        "app",
        "tests",
        "scripts",
        str(verify.CLAUDE_HOOKS_DIR),
    ]


def test_claude_hooks_dir_resolves_to_the_real_repository_hooks_directory() -> None:
    """Not a placeholder path — it must actually exist and actually contain
    the hook this coverage exists for, or the command-construction tests
    above would be asserting coverage of a directory with nothing in it."""
    assert verify.CLAUDE_HOOKS_DIR == verify.REPO_ROOT / ".claude" / "hooks"
    assert verify.CLAUDE_HOOKS_DIR.is_dir()
    assert (verify.CLAUDE_HOOKS_DIR / "compact_checkpoint.py").is_file()


def test_check_repo_command_uses_module_invocation_not_a_direct_path() -> None:
    """Must run as `-m scripts.check_repo`, not a bare path, so it resolves
    identically regardless of caller cwd — never assumed to be covered
    merely by `test_check_repo.py` exercising its functions in-process."""
    assert verify.check_repo_command() == [sys.executable, "-m", "scripts.check_repo"]


def test_git_diff_check_command_is_the_one_non_python_step() -> None:
    """Must include a command-local `-c safe.directory=<REPO_ROOT>` (forward
    slashes, never backslashes) so this exact argv also works in an
    environment that refuses to operate on this checkout otherwise — a real
    defect found by running the genuine verifier in the Codex reviewer's own
    environment. Never mutates global/user Git config: the override is
    scoped to this one invocation via `-c`."""
    expected_root = verify.REPO_ROOT.as_posix()
    assert verify.git_diff_check_command() == [
        "git",
        "-c",
        f"safe.directory={expected_root}",
        "diff",
        "--check",
    ]
    assert "\\" not in verify.git_diff_check_command()[2]


def test_pytest_command_includes_basetemp_and_targets_as_separate_argv_elements() -> None:
    basetemp = Path("/tmp/some-run-dir")
    command = verify.pytest_command(["tests/test_x.py::test_y"], basetemp)
    assert command == [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        f"--basetemp={basetemp}",
        "tests/test_x.py::test_y",
    ]


def test_pytest_command_with_no_targets_runs_the_full_suite() -> None:
    basetemp = Path("/tmp/some-run-dir")
    command = verify.pytest_command([], basetemp)
    assert command == [sys.executable, "-m", "pytest", "-q", f"--basetemp={basetemp}"]


# --------------------------------------------------------------------------
# Pytest summary parsing — narrowly scoped to pinned pytest 8.3.4's shapes
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("1176 passed in 108.02s", {"passed": 1176}),
        (
            "============================== 5 passed in 0.08s ==============================",
            {"passed": 5},
        ),
        ("2 failed, 1174 passed, 3 skipped in 12.34s", {"failed": 2, "passed": 1174, "skipped": 3}),
        (
            "2 failed, 1174 passed, 3 skipped, 1 warning in 12.34s",
            {"failed": 2, "passed": 1174, "skipped": 3, "warning": 1},
        ),
        ("1 error in 0.12s", {"error": 1}),
        ("5 deselected in 0.02s", {"deselected": 5}),
        # Longer runs append a parenthesized H:MM:SS breakdown — confirmed
        # empirically against this suite's own genuine full-suite run.
        ("1235 passed in 101.82s (0:01:41)", {"passed": 1235}),
    ],
)
def test_parse_pytest_summary_recognizes_pinned_version_shapes(
    output: str, expected: dict[str, int]
) -> None:
    assert verify.parse_pytest_summary(output) == expected


def test_parse_pytest_summary_uses_the_last_matching_line_not_an_earlier_section_heading() -> None:
    """A "warnings summary" section heading (framed, no "in Xs" suffix)
    appearing earlier in real pytest output must never be mistaken for the
    final result line."""
    output = (
        "=================== warnings summary ===================\n"
        "tests/test_x.py::test_y\n"
        "  some warning text\n"
        "============== 3 passed, 1 warning in 1.23s =============="
    )
    assert verify.parse_pytest_summary(output) == {"passed": 3, "warning": 1}


def test_parse_pytest_summary_returns_none_for_unrecognized_output() -> None:
    assert (
        verify.parse_pytest_summary("Traceback (most recent call last):\nSomeError: boom") is None
    )


def test_parse_pytest_summary_returns_none_for_malformed_count_part() -> None:
    """A line that has the right trailing shape but an unparseable count
    part must fail closed to "unavailable", never guess partial counts."""
    assert verify.parse_pytest_summary("oh no, 3 passed in 1.23s") is None


def test_parse_pytest_summary_returns_none_for_empty_output() -> None:
    assert verify.parse_pytest_summary("") is None


# --------------------------------------------------------------------------
# Fakes for step-execution tests — never launch a real subprocess.
# --------------------------------------------------------------------------


def _fake_completed_process(
    returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=["fake"], returncode=returncode, stdout=stdout, stderr=stderr
    )


# --------------------------------------------------------------------------
# _subprocess_step
# --------------------------------------------------------------------------


def test_subprocess_step_reports_pass_on_zero_exit_code() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(0)

    result = verify._subprocess_step("a step", ["irrelevant"], Path("."), fake_runner)
    assert result.status is verify.StepStatus.PASS
    assert result.name == "a step"
    assert result.raw_output is None


def test_subprocess_step_reports_fail_on_nonzero_exit_code_and_captures_output() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(1, stdout="stdout text", stderr="stderr text")

    result = verify._subprocess_step("a step", ["irrelevant"], Path("."), fake_runner)
    assert result.status is verify.StepStatus.FAIL
    assert "exit code 1" in result.detail
    assert result.raw_output is not None
    assert "stdout text" in result.raw_output
    assert "stderr text" in result.raw_output


def test_subprocess_step_reports_fail_when_the_command_cannot_even_launch() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise OSError("no such file or directory")

    result = verify._subprocess_step("a step", ["irrelevant"], Path("."), fake_runner)
    assert result.status is verify.StepStatus.FAIL
    assert "OSError" in result.detail


def test_subprocess_step_truncates_very_long_captured_output() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(1, stdout="x" * 50_000)

    result = verify._subprocess_step("a step", ["irrelevant"], Path("."), fake_runner)
    assert result.raw_output is not None
    assert len(result.raw_output) <= verify._MAX_CAPTURED_OUTPUT


# --------------------------------------------------------------------------
# run_pytest_step
# --------------------------------------------------------------------------


def test_run_pytest_step_reports_pass_with_parsed_counts() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(0, stdout="1176 passed in 108.02s")

    result = verify.run_pytest_step("full pytest suite", [], Path("/tmp/x"), fake_runner)
    assert result.status is verify.StepStatus.PASS
    assert result.detail == "1176 passed"


def test_run_pytest_step_reports_pass_with_unavailable_counts_never_zero_or_omitted() -> None:
    """If the subprocess succeeds but its summary line can't be parsed, the
    step is still PASS (determined by exit code), but counts must say
    unavailable, never invent zero or silently drop the field."""

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(0, stdout="totally unrecognized output")

    result = verify.run_pytest_step("full pytest suite", [], Path("/tmp/x"), fake_runner)
    assert result.status is verify.StepStatus.PASS
    assert "unavailable" in result.detail


def test_run_pytest_step_reports_fail_on_nonzero_exit_regardless_of_parsed_counts() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(1, stdout="2 failed, 3 passed in 1.00s")

    result = verify.run_pytest_step("full pytest suite", [], Path("/tmp/x"), fake_runner)
    assert result.status is verify.StepStatus.FAIL
    assert result.detail == "2 failed, 3 passed"
    assert result.raw_output is not None


def test_run_pytest_step_passes_focus_targets_as_argv_elements() -> None:
    captured_command: list[str] = []

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        captured_command.extend(command)
        return _fake_completed_process(0, stdout="1 passed in 0.01s")

    verify.run_pytest_step(
        "focused pytest", ["tests/test_x.py::test_y"], Path("/tmp/x"), fake_runner
    )
    assert "tests/test_x.py::test_y" in captured_command


def test_run_pytest_step_writes_parsed_counts_into_the_counts_sink() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(0, stdout="7 passed in 1.00s")

    sink: dict[str, dict[str, int] | None] = {}
    verify.run_pytest_step(
        "full pytest suite", [], Path("/tmp/x"), fake_runner, counts_sink=sink, counts_key="full"
    )
    assert sink == {"full": {"passed": 7}}


def test_run_pytest_step_writes_none_into_the_counts_sink_when_the_summary_is_unparseable() -> None:
    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(0, stdout="totally unrecognized output")

    sink: dict[str, dict[str, int] | None] = {}
    verify.run_pytest_step(
        "full pytest suite", [], Path("/tmp/x"), fake_runner, counts_sink=sink, counts_key="full"
    )
    assert sink == {"full": None}


def test_run_pytest_step_writes_none_into_the_counts_sink_when_launch_fails() -> None:
    def failing_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        raise OSError("no such file")

    sink: dict[str, dict[str, int] | None] = {}
    result = verify.run_pytest_step(
        "full pytest suite", [], Path("/tmp/x"), failing_runner, counts_sink=sink, counts_key="full"
    )
    assert result.status is verify.StepStatus.FAIL
    assert sink == {"full": None}


def test_run_pytest_step_never_touches_the_sink_when_none_is_given() -> None:
    """`counts_sink=None` (the default) must not raise — every existing call
    site that predates this side channel must keep working unmodified."""

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return _fake_completed_process(0, stdout="1 passed in 0.01s")

    result = verify.run_pytest_step("full pytest suite", [], Path("/tmp/x"), fake_runner)
    assert result.status is verify.StepStatus.PASS


# --------------------------------------------------------------------------
# db_url_validation_step / db_reachability_step — URL safety and redaction
# --------------------------------------------------------------------------

_DEV_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin"
_TEST_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test"


def test_db_url_validation_step_passes_for_a_distinct_test_database() -> None:
    result = verify.db_url_validation_step(_DEV_URL, _TEST_URL)
    assert result.status is verify.StepStatus.PASS


def test_db_url_validation_step_fails_when_test_url_is_the_development_database() -> None:
    result = verify.db_url_validation_step(_DEV_URL, _DEV_URL)
    assert result.status is verify.StepStatus.FAIL
    assert "matches the configured development database" in result.detail


def test_db_url_validation_step_fails_when_test_url_has_no_test_marker() -> None:
    same_looking_url = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/some_other_db"
    result = verify.db_url_validation_step(_DEV_URL, same_looking_url)
    assert result.status is verify.StepStatus.FAIL
    assert "does not contain 'test'" in result.detail


def test_db_url_validation_step_never_leaks_credentials_in_its_detail() -> None:
    secret_url = "postgresql+asyncpg://realuser:supersecretpassword@localhost:5432/jobgoblin"
    result = verify.db_url_validation_step(secret_url, secret_url)
    assert result.status is verify.StepStatus.FAIL
    assert "supersecretpassword" not in result.detail
    assert "realuser" not in result.detail


def test_db_url_validation_step_fails_cleanly_on_a_malformed_url_never_crashes() -> None:
    """A malformed, unparseable URL makes SQLAlchemy's `make_url` raise
    `ArgumentError`, not the guard's own `RuntimeError` — proves this is
    still caught and reported as a clean FAIL, never an uncaught traceback
    (a real defect found by actually running this step against a malformed
    `TEST_DATABASE_URL`)."""
    result = verify.db_url_validation_step(_DEV_URL, "not-a-valid-url-at-all")
    assert result.status is verify.StepStatus.FAIL
    assert "ArgumentError" in result.detail


def test_db_url_validation_step_never_echoes_a_malformed_urls_raw_content() -> None:
    """`ArgumentError`'s own message echoes its input verbatim — if that
    input happened to look credential-bearing, only the exception type
    name may appear in the report, never the raw message. This string is
    missing `://` entirely, so SQLAlchemy's `make_url` genuinely rejects
    it (confirmed empirically) rather than leniently parsing it."""
    result = verify.db_url_validation_step(
        _DEV_URL, "user:supersecretpassword@localhost/db-no-scheme"
    )
    assert result.status is verify.StepStatus.FAIL
    assert "supersecretpassword" not in result.detail


def test_db_url_validation_step_pass_detail_reports_a_redacted_target_never_raw() -> None:
    secret_url = "postgresql+asyncpg://realuser:supersecretpassword@localhost:5432/jobgoblin_test"
    result = verify.db_url_validation_step(_DEV_URL, secret_url)
    assert result.status is verify.StepStatus.PASS
    assert "supersecretpassword" not in result.detail
    assert "realuser" not in result.detail
    assert "jobgoblin_test" in result.detail


def test_db_reachability_step_passes_when_connectivity_check_does_not_raise() -> None:
    result = verify.db_reachability_step(_TEST_URL, connectivity_check=lambda url: None)
    assert result.status is verify.StepStatus.PASS
    assert "reachable" in result.detail


def test_db_reachability_step_fails_when_connectivity_check_raises() -> None:
    def failing_check(url: str) -> None:
        raise ConnectionRefusedError("nope")

    result = verify.db_reachability_step(_TEST_URL, connectivity_check=failing_check)
    assert result.status is verify.StepStatus.FAIL
    assert "unreachable" in result.detail
    assert "ConnectionRefusedError" in result.detail


def test_db_reachability_step_never_leaks_the_raw_exception_message() -> None:
    """Only the exception *type name* may appear — some drivers embed the
    full connection string (including credentials) in their exception's
    string representation."""

    def failing_check(url: str) -> None:
        raise RuntimeError("connection failed: postgresql://realuser:supersecretpassword@host/db")

    result = verify.db_reachability_step(_TEST_URL, connectivity_check=failing_check)
    assert result.status is verify.StepStatus.FAIL
    assert "supersecretpassword" not in result.detail
    assert "realuser" not in result.detail
    assert "RuntimeError" in result.detail


def test_db_reachability_step_only_ever_receives_the_test_url_never_the_dev_url() -> None:
    received: list[str] = []

    def recording_check(url: str) -> None:
        received.append(url)

    verify.db_reachability_step(_TEST_URL, connectivity_check=recording_check)
    assert received == [_TEST_URL]


# --------------------------------------------------------------------------
# handoff_metadata_step — Workflow v3.1 pilot
# --------------------------------------------------------------------------


def test_handoff_metadata_step_passes_when_validate_handoff_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(verify.check_handoff, "validate_handoff", lambda **kwargs: None)
    result = verify.handoff_metadata_step(docs_only=False, pytest_counts={}, focus_targets=[])
    assert result.status is verify.StepStatus.PASS


def test_handoff_metadata_step_fails_when_validate_handoff_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raising(**kwargs: object) -> None:
        raise verify.check_handoff.HandoffValidationError("declared count does not match")

    monkeypatch.setattr(verify.check_handoff, "validate_handoff", raising)
    result = verify.handoff_metadata_step(docs_only=False, pytest_counts={}, focus_targets=[])
    assert result.status is verify.StepStatus.FAIL
    assert "declared count does not match" in result.detail


def test_handoff_metadata_step_passes_through_observed_counts_and_selector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def recording(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(verify.check_handoff, "validate_handoff", recording)
    verify.handoff_metadata_step(
        docs_only=False,
        pytest_counts={"full": {"passed": 12}, "focused": {"passed": 2}},
        focus_targets=["tests/test_x.py::test_y"],
    )
    assert captured == {
        "docs_only": False,
        "actual_full_suite_count": 12,
        "actual_focused_count": 2,
        "actual_focus_selector": "tests/test_x.py::test_y",
    }


def test_handoff_metadata_step_reports_unavailable_counts_as_none_not_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pytest step whose summary line couldn't be parsed writes `None`
    into the sink (see `run_pytest_step`'s own tests above) — this step must
    forward that `None` unchanged, never coerce it to `0`."""
    captured: dict[str, object] = {}

    def recording(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(verify.check_handoff, "validate_handoff", recording)
    verify.handoff_metadata_step(docs_only=False, pytest_counts={"full": None}, focus_targets=[])
    assert captured["actual_full_suite_count"] is None
    assert captured["actual_focused_count"] is None
    assert captured["actual_focus_selector"] is None


# --------------------------------------------------------------------------
# _run_steps — ordering, aggregation, fail-fast NOT RUN behavior
# --------------------------------------------------------------------------


def _passing_step(name: str) -> verify.Step:
    return verify.Step(name, lambda: verify.StepResult(name, verify.StepStatus.PASS, 0.01))


def _failing_step(name: str) -> verify.Step:
    return verify.Step(name, lambda: verify.StepResult(name, verify.StepStatus.FAIL, 0.01, "boom"))


def test_run_steps_all_pass_reports_all_pass_in_order() -> None:
    steps = [_passing_step("a"), _passing_step("b"), _passing_step("c")]
    results = verify._run_steps(steps)
    assert [r.name for r in results] == ["a", "b", "c"]
    assert all(r.status is verify.StepStatus.PASS for r in results)


def test_run_steps_marks_every_step_after_a_failure_as_not_run() -> None:
    steps = [_passing_step("a"), _failing_step("b"), _passing_step("c"), _passing_step("d")]
    results = verify._run_steps(steps)
    statuses = {r.name: r.status for r in results}
    assert statuses["a"] is verify.StepStatus.PASS
    assert statuses["b"] is verify.StepStatus.FAIL
    assert statuses["c"] is verify.StepStatus.NOT_RUN
    assert statuses["d"] is verify.StepStatus.NOT_RUN


def test_run_steps_not_run_results_carry_a_zero_duration_and_a_clear_reason() -> None:
    steps = [_failing_step("a"), _passing_step("b")]
    results = verify._run_steps(steps)
    not_run = next(r for r in results if r.name == "b")
    assert not_run.status is verify.StepStatus.NOT_RUN
    assert not_run.duration_seconds == 0.0
    assert "blocked" in not_run.detail


def test_run_steps_never_calls_run_on_a_step_after_blocking() -> None:
    """Proves NOT RUN steps are never even attempted — not attempted-and-
    discarded, actually skipped — by making the step's own `run` raise if
    called at all."""

    def _must_not_run() -> verify.StepResult:
        raise AssertionError("this step's run() must never be called")

    steps = [_failing_step("a"), verify.Step("b", _must_not_run)]
    results = verify._run_steps(steps)
    assert results[1].status is verify.StepStatus.NOT_RUN


# --------------------------------------------------------------------------
# _build_steps — ordering and structure only, never executed.
# --------------------------------------------------------------------------


def _unused_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    raise AssertionError("no step should be executed while only testing _build_steps' structure")


def _unused_connectivity_check(url: str) -> None:
    raise AssertionError("no step should be executed while only testing _build_steps' structure")


def test_build_steps_without_focus_has_the_required_order_and_no_focused_step() -> None:
    steps = verify._build_steps(
        [],
        _DEV_URL,
        _TEST_URL,
        Path("/tmp/run-dir"),
        runner=_unused_runner,
        connectivity_check=_unused_connectivity_check,
    )
    assert [s.name for s in steps] == [
        "ruff format --check",
        "ruff check",
        "mypy",
        "check_repo.py",
        "git diff --check",
        "disposable test-database URL validation",
        "test-database reachability preflight",
        "full pytest suite",
        "handoff metadata validation",
    ]


def test_build_steps_with_focus_inserts_focused_pytest_before_full_suite() -> None:
    steps = verify._build_steps(
        ["tests/test_x.py::test_y"],
        _DEV_URL,
        _TEST_URL,
        Path("/tmp/run-dir"),
        runner=_unused_runner,
        connectivity_check=_unused_connectivity_check,
    )
    names = [s.name for s in steps]
    assert names[-3:] == ["focused pytest", "full pytest suite", "handoff metadata validation"]
    assert names.count("focused pytest") == 1


def test_build_steps_docs_only_skips_database_and_pytest_steps() -> None:
    """Workflow v3.1 pilot: `--docs-only` must skip the disposable-database
    steps and both pytest steps entirely — never attempt to construct them,
    since `_unused_runner`/`_unused_connectivity_check` would raise if
    called — while still ending in the required handoff-metadata step."""
    steps = verify._build_steps(
        ["tests/test_x.py::test_y"],
        _DEV_URL,
        _TEST_URL,
        Path("/tmp/run-dir"),
        docs_only=True,
        runner=_unused_runner,
        connectivity_check=_unused_connectivity_check,
    )
    assert [s.name for s in steps] == [
        "ruff format --check",
        "ruff check",
        "mypy",
        "check_repo.py",
        "git diff --check",
        "handoff metadata validation",
    ]


def test_build_steps_handoff_metadata_step_reflects_docs_only_and_observed_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The trailing step's own closure must be wired to the same `docs_only`
    flag and to a `pytest_counts` sink populated by the full/focused pytest
    steps that ran earlier in the same `_build_steps` call — proven here by
    running the whole step list through a fake runner and confirming the
    handoff-metadata step sees real, non-placeholder counts."""

    def fake_runner(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        joined = " ".join(command)
        if "pytest" not in joined:
            return _fake_completed_process(0)
        return _fake_completed_process(0, stdout="3 passed in 0.10s")

    def fake_validate_handoff(
        *,
        docs_only: bool,
        actual_full_suite_count: int | None,
        actual_focused_count: int | None,
        actual_focus_selector: str | None,
    ) -> None:
        observed["docs_only"] = docs_only
        observed["actual_full_suite_count"] = actual_full_suite_count
        observed["actual_focused_count"] = actual_focused_count
        observed["actual_focus_selector"] = actual_focus_selector

    observed: dict[str, object] = {}
    monkeypatch.setattr(verify.check_handoff, "validate_handoff", fake_validate_handoff)

    steps = verify._build_steps(
        ["tests/test_x.py::test_y"],
        _DEV_URL,
        _TEST_URL,
        Path("/tmp/run-dir"),
        runner=fake_runner,
        connectivity_check=lambda url: None,
    )
    for step in steps:
        step.run()

    assert observed == {
        "docs_only": False,
        "actual_full_suite_count": 3,
        "actual_focused_count": 3,
        "actual_focus_selector": "tests/test_x.py::test_y",
    }


# --------------------------------------------------------------------------
# Focus-target validation
# --------------------------------------------------------------------------


def test_validate_focus_target_accepts_a_real_test_file_path() -> None:
    target = "tests/test_verify.py"
    assert verify.validate_focus_target(target) == target


def test_validate_focus_target_accepts_a_real_test_file_with_node_id() -> None:
    target = "tests/test_verify.py::test_validate_focus_target_accepts_a_real_test_file_path"
    assert verify.validate_focus_target(target) == target


def test_validate_focus_target_rejects_a_target_starting_with_dash() -> None:
    with pytest.raises(verify.FocusValidationError, match="must not begin with '-'"):
        verify.validate_focus_target("--maxfail=1")


def test_validate_focus_target_rejects_a_real_file_outside_backend_tests() -> None:
    """`app/main.py` genuinely exists (proving this isn't merely the
    nonexistent-file check) but is not located under `backend/tests` —
    must still be rejected."""
    with pytest.raises(verify.FocusValidationError, match="does not resolve to a file under"):
        verify.validate_focus_target("app/main.py")


def test_validate_focus_target_rejects_a_path_traversal_attempt() -> None:
    with pytest.raises(verify.FocusValidationError, match="does not resolve to a file under"):
        verify.validate_focus_target("../../etc/passwd")


def test_validate_focus_target_rejects_a_nonexistent_file() -> None:
    with pytest.raises(verify.FocusValidationError, match="does not resolve to a file under"):
        verify.validate_focus_target("tests/test_this_file_does_not_exist.py")


def test_validate_focus_target_rejects_empty_file_portion_before_double_colon() -> None:
    with pytest.raises(verify.FocusValidationError, match="no file portion"):
        verify.validate_focus_target("::test_y")


def test_validate_focus_target_returns_the_target_string_unchanged() -> None:
    """The validated string must be exactly what gets passed to pytest —
    never resolved to an absolute path or otherwise rewritten."""
    target = "tests/test_verify.py::test_validate_focus_target_returns_the_target_string_unchanged"
    assert verify.validate_focus_target(target) == target


# --------------------------------------------------------------------------
# safe_rmtree — temporary-directory safety
# --------------------------------------------------------------------------


def test_safe_rmtree_removes_a_directory_actually_under_the_given_root(tmp_path: Path) -> None:
    root = tmp_path / ".verify-tmp"
    root.mkdir()
    child = root / "run-abc123"
    child.mkdir()
    (child / "marker.txt").write_text("x")

    verify.safe_rmtree(child, must_be_under=root)

    assert not child.exists()
    assert root.exists()  # only the child is removed, never the root itself


def test_safe_rmtree_refuses_to_delete_a_path_outside_the_root(tmp_path: Path) -> None:
    root = tmp_path / ".verify-tmp"
    root.mkdir()
    outside = tmp_path / "not-under-verify-tmp"
    outside.mkdir()
    (outside / "important.txt").write_text("do not delete me")

    with pytest.raises(RuntimeError, match="not located under"):
        verify.safe_rmtree(outside, must_be_under=root)

    assert outside.exists()
    assert (outside / "important.txt").exists()


def test_safe_rmtree_refuses_a_sibling_directory_that_merely_shares_a_name_prefix(
    tmp_path: Path,
) -> None:
    """A naive string-prefix check (`str(path).startswith(str(root))`)
    would incorrectly accept `.verify-tmp-evil` as "under" `.verify-tmp` —
    proves the check is a real path-hierarchy check, not string matching."""
    root = tmp_path / ".verify-tmp"
    root.mkdir()
    lookalike = tmp_path / ".verify-tmp-evil"
    lookalike.mkdir()

    with pytest.raises(RuntimeError, match="not located under"):
        verify.safe_rmtree(lookalike, must_be_under=root)

    assert lookalike.exists()


def test_safe_rmtree_refuses_to_delete_the_root_itself(tmp_path: Path) -> None:
    """`path == must_be_under` must be rejected — a strict-child check, not
    merely `is_relative_to` (every path is "relative to" itself)."""
    root = tmp_path / ".verify-tmp"
    root.mkdir()

    with pytest.raises(RuntimeError, match="that is the root itself"):
        verify.safe_rmtree(root, must_be_under=root)

    assert root.exists()


def test_safe_rmtree_never_ignores_a_deletion_failure(tmp_path: Path) -> None:
    """A deletion failure must propagate, never be swallowed
    (`ignore_errors=True` is no longer used) — proven via an injected
    `remove` that raises, since real filesystem permission failures are
    unreliable to simulate portably."""
    root = tmp_path / ".verify-tmp"
    root.mkdir()
    child = root / "run-abc123"
    child.mkdir()

    def _failing_remove(path: Path) -> None:
        raise PermissionError("simulated: cannot delete")

    with pytest.raises(PermissionError, match="simulated"):
        verify.safe_rmtree(child, must_be_under=root, remove=_failing_remove)

    assert child.exists()  # the failure is real — nothing was actually removed


def test_safe_rmtree_deletion_of_a_nonexistent_child_now_fails_closed(tmp_path: Path) -> None:
    """Without `ignore_errors=True`, deleting an already-gone (but safely
    located) child now correctly raises rather than silently succeeding —
    the opposite of this test's own pre-correction behavior."""
    root = tmp_path / ".verify-tmp"
    root.mkdir()
    child = root / "run-does-not-exist"  # never created

    with pytest.raises(FileNotFoundError):
        verify.safe_rmtree(child, must_be_under=root)


# --------------------------------------------------------------------------
# create_run_dir — concurrent-run isolation
# --------------------------------------------------------------------------


def test_create_run_dir_returns_a_directory_under_verify_tmp_root() -> None:
    run_dir = verify.create_run_dir()
    try:
        assert run_dir.is_dir()
        assert run_dir.resolve().is_relative_to(verify.VERIFY_TMP_ROOT.resolve())
    finally:
        verify.safe_rmtree(run_dir, must_be_under=verify.VERIFY_TMP_ROOT)


def test_create_run_dir_produces_distinct_directories_across_invocations() -> None:
    """Simulates two concurrent `verify.py` invocations: each gets its own
    unique directory, so one's cleanup can never remove the other's still-
    active files."""
    run_dir_a = verify.create_run_dir()
    run_dir_b = verify.create_run_dir()
    try:
        assert run_dir_a != run_dir_b
        assert run_dir_a.is_dir()
        assert run_dir_b.is_dir()
        # Writing into one must never appear in the other.
        (run_dir_a / "marker.txt").write_text("belongs to run A only")
        assert not (run_dir_b / "marker.txt").exists()
    finally:
        verify.safe_rmtree(run_dir_a, must_be_under=verify.VERIFY_TMP_ROOT)
        verify.safe_rmtree(run_dir_b, must_be_under=verify.VERIFY_TMP_ROOT)


def test_create_run_dir_cleanup_of_one_run_never_deletes_a_concurrent_runs_directory() -> None:
    run_dir_a = verify.create_run_dir()
    run_dir_b = verify.create_run_dir()
    try:
        (run_dir_b / "still-active.txt").write_text("run B is still working")

        verify.safe_rmtree(run_dir_a, must_be_under=verify.VERIFY_TMP_ROOT)

        assert not run_dir_a.exists()
        assert run_dir_b.exists()
        assert (run_dir_b / "still-active.txt").exists()
    finally:
        verify.safe_rmtree(run_dir_b, must_be_under=verify.VERIFY_TMP_ROOT)


# --------------------------------------------------------------------------
# cleanup_run_dir_step — reported as its own PASS/FAIL result
# --------------------------------------------------------------------------


def test_cleanup_run_dir_step_reports_pass_and_actually_removes_the_directory() -> None:
    run_dir = verify.create_run_dir()
    result = verify.cleanup_run_dir_step(run_dir)
    assert result.status is verify.StepStatus.PASS
    assert result.name == "temporary-directory cleanup"
    assert not run_dir.exists()


def test_cleanup_run_dir_step_reports_fail_when_removal_raises() -> None:
    run_dir = verify.create_run_dir()
    try:

        def _failing_remove(path: Path) -> None:
            raise PermissionError("simulated: cannot delete")

        result = verify.cleanup_run_dir_step(run_dir, remove=_failing_remove)
        assert result.status is verify.StepStatus.FAIL
        assert "PermissionError" in result.detail
        assert run_dir.exists()  # the failure is real
    finally:
        verify.safe_rmtree(run_dir, must_be_under=verify.VERIFY_TMP_ROOT)


# --------------------------------------------------------------------------
# _execute_and_cleanup — cleanup always attempted, always reported
# --------------------------------------------------------------------------


def test_execute_and_cleanup_reports_cleanup_after_all_steps_pass() -> None:
    run_dir = verify.create_run_dir()
    steps = [_passing_step("a"), _passing_step("b")]

    results = verify._execute_and_cleanup(steps, run_dir)

    names_and_statuses = {r.name: r.status for r in results}
    assert names_and_statuses["a"] is verify.StepStatus.PASS
    assert names_and_statuses["b"] is verify.StepStatus.PASS
    assert names_and_statuses["temporary-directory cleanup"] is verify.StepStatus.PASS
    assert not run_dir.exists()


def test_execute_and_cleanup_still_runs_cleanup_after_an_earlier_verification_failure() -> None:
    """Binding requirement: cleanup must always be attempted, including
    after a verification step already failed — never skipped just because
    the run is already going to be reported as failed."""
    run_dir = verify.create_run_dir()
    steps = [_failing_step("a"), _passing_step("b")]

    results = verify._execute_and_cleanup(steps, run_dir)

    by_name = {r.name: r for r in results}
    assert by_name["a"].status is verify.StepStatus.FAIL
    assert by_name["b"].status is verify.StepStatus.NOT_RUN
    assert by_name["temporary-directory cleanup"].status is verify.StepStatus.PASS
    assert not run_dir.exists()


def test_execute_and_cleanup_surfaces_a_cleanup_failure_as_its_own_result() -> None:
    run_dir = verify.create_run_dir()
    try:

        def _failing_remove(path: Path) -> None:
            raise OSError("simulated: disk error")

        results = verify._execute_and_cleanup([_passing_step("a")], run_dir, remove=_failing_remove)

        by_name = {r.name: r for r in results}
        assert by_name["a"].status is verify.StepStatus.PASS
        assert by_name["temporary-directory cleanup"].status is verify.StepStatus.FAIL
        # All results being PASS is what main() uses to decide the exit code —
        # a failed cleanup must make that condition false.
        assert not all(r.status is verify.StepStatus.PASS for r in results)
    finally:
        verify.safe_rmtree(run_dir, must_be_under=verify.VERIFY_TMP_ROOT)


def test_execute_and_cleanup_isolates_concurrent_run_directories() -> None:
    """Cleaning up one invocation's run directory must never touch a
    concurrent invocation's still-active directory."""
    run_dir_a = verify.create_run_dir()
    run_dir_b = verify.create_run_dir()
    try:
        (run_dir_b / "still-active.txt").write_text("run B's own file")

        results = verify._execute_and_cleanup([_passing_step("a")], run_dir_a)

        cleanup_result = next(r for r in results if r.name == "temporary-directory cleanup")
        assert cleanup_result.status is verify.StepStatus.PASS
        assert not run_dir_a.exists()
        assert run_dir_b.exists()
        assert (run_dir_b / "still-active.txt").exists()
    finally:
        verify.safe_rmtree(run_dir_b, must_be_under=verify.VERIFY_TMP_ROOT)


# --------------------------------------------------------------------------
# CLI argument parsing
# --------------------------------------------------------------------------


def test_parse_args_accepts_level_routine() -> None:
    args = verify._parse_args(["--level", "routine"])
    assert args.level == "routine"
    assert args.focus is None


def test_parse_args_rejects_an_unimplemented_level() -> None:
    with pytest.raises(SystemExit):
        verify._parse_args(["--level", "schema"])


def test_parse_args_requires_level() -> None:
    with pytest.raises(SystemExit):
        verify._parse_args([])


def test_parse_args_collects_multiple_focus_targets() -> None:
    args = verify._parse_args(
        ["--level", "routine", "--focus", "tests/test_a.py::test_x", "tests/test_b.py"]
    )
    assert args.focus == ["tests/test_a.py::test_x", "tests/test_b.py"]


def test_parse_args_accepts_docs_only_alone() -> None:
    args = verify._parse_args(["--level", "routine", "--docs-only"])
    assert args.docs_only is True
    assert args.focus is None


def test_parse_args_defaults_docs_only_to_false() -> None:
    args = verify._parse_args(["--level", "routine"])
    assert args.docs_only is False


def test_parse_args_rejects_docs_only_combined_with_focus() -> None:
    with pytest.raises(SystemExit):
        verify._parse_args(
            ["--level", "routine", "--docs-only", "--focus", "tests/test_a.py::test_x"]
        )


# --------------------------------------------------------------------------
# _print_summary — output formatting (no execution involved)
# --------------------------------------------------------------------------


def test_print_summary_reports_all_passed_when_nothing_failed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = [
        verify.StepResult("a", verify.StepStatus.PASS, 1.0, "ok"),
        verify.StepResult("b", verify.StepStatus.PASS, 2.0, "ok"),
    ]
    verify._print_summary(results)
    output = capsys.readouterr().out
    assert "ALL 2 CHECKS PASSED" in output


def test_print_summary_reports_failed_and_not_run_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = [
        verify.StepResult("a", verify.StepStatus.PASS, 1.0, "ok"),
        verify.StepResult("b", verify.StepStatus.FAIL, 2.0, "boom", raw_output="full output here"),
        verify.StepResult("c", verify.StepStatus.NOT_RUN, 0.0, "blocked"),
    ]
    verify._print_summary(results)
    output = capsys.readouterr().out
    assert "1 passed, 1 failed, 1 not run" in output
    assert "full output here" in output  # raw output printed for the FAIL step


def test_print_summary_never_prints_raw_output_for_a_passing_step(
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = [
        verify.StepResult("a", verify.StepStatus.PASS, 1.0, "ok", raw_output="should not appear")
    ]
    verify._print_summary(results)
    output = capsys.readouterr().out
    assert "should not appear" not in output
