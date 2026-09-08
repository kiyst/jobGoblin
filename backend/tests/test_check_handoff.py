"""Unit tests for `scripts/check_handoff.py`.

No test in this file ever reads the repository's real `docs/LLM_HANDOFF.md`
or a real fixture file — every test constructs its own in-memory handoff
text and, where needed, a temporary fixture file, so this suite's outcome
never depends on unrelated, currently-in-progress repository state. No test
launches a subprocess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_handoff as ch

# --------------------------------------------------------------------------
# extract_latest_work_done_metadata_text — locating the newest entry only
# --------------------------------------------------------------------------


def _handoff(*, iterations: list[str]) -> str:
    return "# LLM Engineering Handoff\n\n---\n\n" + "\n\n---\n\n".join(iterations)


def _metadata_block(fields: dict[str, str]) -> str:
    body = "\n".join(f"{key}: {value}" for key, value in fields.items())
    return f"```workflow-metadata\n{body}\n```"


_PARSER_FIELDS = {
    "workflow_version": "v3.1-pilot",
    "slice_kind": "parser",
    "verification_level": "routine",
    "focused_test_selector": "backend/tests/test_normalization_x.py",
    "focused_test_count": "10",
    "full_suite_count": "1800",
    "fixture_path": "backend/tests/fixtures/normalization/x_cases.json",
    "fixture_count": "5",
}


def test_extracts_metadata_from_the_last_iterations_work_done_section() -> None:
    old_iteration = "## Iteration 1\n\n### Work done\n\nold entry, no metadata block at all.\n"
    new_iteration = (
        "## Iteration 2\n\n### Work done\n\nnewest entry.\n\n"
        + _metadata_block(_PARSER_FIELDS)
        + "\n"
    )
    text = _handoff(iterations=[old_iteration, new_iteration])

    raw = ch.extract_latest_work_done_metadata_text(text)
    fields = ch.parse_metadata_fields(raw)

    assert fields["slice_kind"] == "parser"
    assert fields["fixture_count"] == "5"


def test_ignores_a_historical_iteration_missing_the_block_entirely() -> None:
    """A rotated-out iteration predating this format must never fail —
    only the newest entry is ever inspected."""
    old_iteration_no_block = "## Iteration 1\n\n### Work done\n\nno metadata block here at all.\n"
    new_iteration = (
        "## Iteration 2\n\n### Work done\n\nnewest.\n\n" + _metadata_block(_PARSER_FIELDS) + "\n"
    )
    text = _handoff(iterations=[old_iteration_no_block, new_iteration])

    raw = ch.extract_latest_work_done_metadata_text(text)
    assert "slice_kind: parser" in raw


def test_stops_at_work_review_and_does_not_read_past_it() -> None:
    iteration = (
        "## Iteration 1\n\n### Work done\n\n"
        + _metadata_block(_PARSER_FIELDS)
        + "\n\n### Work review\n\n```workflow-metadata\nslice_kind: docs\n```\n"
    )
    text = _handoff(iterations=[iteration])

    raw = ch.extract_latest_work_done_metadata_text(text)
    fields = ch.parse_metadata_fields(raw)
    assert fields["slice_kind"] == "parser"  # not the Work review's own (hypothetical) block


def test_raises_when_no_iteration_heading_exists_at_all() -> None:
    with pytest.raises(ch.HandoffValidationError, match="no '## Iteration"):
        ch.extract_latest_work_done_metadata_text("# LLM Engineering Handoff\n\nno headings.\n")


def test_raises_when_newest_iteration_has_no_work_done_heading() -> None:
    text = _handoff(iterations=["## Iteration 1\n\nno Work done heading at all.\n"])
    with pytest.raises(ch.HandoffValidationError, match="no '### Work done'"):
        ch.extract_latest_work_done_metadata_text(text)


def test_raises_when_work_done_has_no_metadata_block() -> None:
    text = _handoff(iterations=["## Iteration 1\n\n### Work done\n\nprose only, no block.\n"])
    with pytest.raises(ch.HandoffValidationError, match="no 'workflow-metadata' block"):
        ch.extract_latest_work_done_metadata_text(text)


def test_raises_when_work_done_has_more_than_one_metadata_block() -> None:
    """Two fenced blocks in the same 'Work done' section previously let
    `.search`'s first-match behavior silently pick one and ignore a
    possibly-contradicting second block — a real defect found by
    constructing exactly this input."""
    text = _handoff(
        iterations=[
            "## Iteration 1\n\n### Work done\n\n"
            + _metadata_block(_PARSER_FIELDS)
            + "\n\nsome prose in between.\n\n"
            + _metadata_block(_TOOLING_FIELDS)
            + "\n"
        ]
    )
    with pytest.raises(ch.HandoffValidationError, match="more than one 'workflow-metadata' block"):
        ch.extract_latest_work_done_metadata_text(text)


# --------------------------------------------------------------------------
# parse_metadata_fields
# --------------------------------------------------------------------------


def test_parse_metadata_fields_splits_key_value_lines() -> None:
    fields = ch.parse_metadata_fields("a: 1\nb: two\n\nc: 3")
    assert fields == {"a": "1", "b": "two", "c": "3"}


def test_parse_metadata_fields_rejects_a_line_with_no_colon() -> None:
    with pytest.raises(ch.HandoffValidationError, match="malformed metadata line"):
        ch.parse_metadata_fields("a: 1\nthis line has no colon at all")


def test_parse_metadata_fields_rejects_a_duplicate_key() -> None:
    """Previously the second `full_suite_count` silently overwrote the
    first (last-one-wins), hiding a conflicting declaration instead of
    failing — a real defect found by constructing exactly this input."""
    with pytest.raises(
        ch.HandoffValidationError, match="duplicate metadata key 'full_suite_count'"
    ):
        ch.parse_metadata_fields("full_suite_count: 1800\nfull_suite_count: 5")


def test_parse_metadata_fields_rejects_an_empty_key() -> None:
    with pytest.raises(ch.HandoffValidationError, match="empty key"):
        ch.parse_metadata_fields(": some value with no key")


# --------------------------------------------------------------------------
# validate_structure — parser slice_kind
# --------------------------------------------------------------------------


def test_valid_parser_metadata_passes() -> None:
    ch.validate_structure(dict(_PARSER_FIELDS))  # must not raise


def test_unknown_metadata_key_is_rejected_even_in_an_otherwise_valid_block() -> None:
    """Codex review finding (commit d5fec38): an otherwise-valid block with
    an invented/typo key (e.g. `typo_full_sute_count`) previously passed
    `validate_structure` unnoticed — only required/conditional fields were
    checked, never the full key set against a closed schema. Reproduced
    with exactly the reviewer's own example typo, added to an otherwise
    fully-valid tooling block."""
    fields = dict(_TOOLING_FIELDS)
    fields["typo_full_sute_count"] = "1"
    with pytest.raises(ch.HandoffValidationError, match="unrecognized field"):
        ch.validate_structure(fields)


def test_missing_required_field_is_rejected() -> None:
    fields = dict(_PARSER_FIELDS)
    del fields["workflow_version"]
    with pytest.raises(ch.HandoffValidationError, match="missing required field"):
        ch.validate_structure(fields)


def test_empty_required_field_is_rejected() -> None:
    fields = dict(_PARSER_FIELDS)
    fields["focused_test_selector"] = ""
    with pytest.raises(ch.HandoffValidationError, match="empty required field"):
        ch.validate_structure(fields)


def test_unsupported_workflow_version_is_rejected() -> None:
    """Presence of `workflow_version` was previously checked, but never its
    value — a metadata block claiming a garbage or unsupported version
    string still passed. Reproduced by constructing exactly this input."""
    fields = dict(_PARSER_FIELDS)
    fields["workflow_version"] = "garbage"
    with pytest.raises(ch.HandoffValidationError, match="'workflow_version' must be"):
        ch.validate_structure(fields)


def test_empty_fixture_path_is_rejected_for_a_parser_slice() -> None:
    fields = dict(_PARSER_FIELDS)
    fields["fixture_path"] = ""
    with pytest.raises(ch.HandoffValidationError, match="'fixture_path' must not be empty"):
        ch.validate_structure(fields)


def test_unrecognized_slice_kind_is_rejected() -> None:
    fields = dict(_PARSER_FIELDS)
    fields["slice_kind"] = "bogus"
    with pytest.raises(ch.HandoffValidationError, match="'slice_kind' must be one of"):
        ch.validate_structure(fields)


def test_unrecognized_verification_level_is_rejected() -> None:
    fields = dict(_PARSER_FIELDS)
    fields["verification_level"] = "bogus"
    with pytest.raises(ch.HandoffValidationError, match="'verification_level' must be one of"):
        ch.validate_structure(fields)


def test_parser_slice_requires_fixture_fields() -> None:
    fields = dict(_PARSER_FIELDS)
    del fields["fixture_path"]
    del fields["fixture_count"]
    with pytest.raises(ch.HandoffValidationError, match="requires both 'fixture_path'"):
        ch.validate_structure(fields)


def test_parser_slice_requires_actual_focused_count_not_not_run() -> None:
    fields = dict(_PARSER_FIELDS)
    fields["focused_test_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    with pytest.raises(ch.HandoffValidationError, match="must be focus-tested"):
        ch.validate_structure(fields)


# --------------------------------------------------------------------------
# validate_structure — tooling slice_kind
# --------------------------------------------------------------------------

_TOOLING_FIELDS = {
    "workflow_version": "v3.1-pilot",
    "slice_kind": "tooling",
    "verification_level": "routine",
    "focused_test_selector": "backend/tests/test_check_handoff.py",
    "focused_test_count": "20",
    "full_suite_count": "1800",
}


def test_valid_tooling_metadata_passes() -> None:
    ch.validate_structure(dict(_TOOLING_FIELDS))


def test_tooling_slice_rejects_fixture_fields_as_inapplicable() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["fixture_path"] = "backend/tests/fixtures/normalization/x_cases.json"
    fields["fixture_count"] = "5"
    with pytest.raises(ch.HandoffValidationError, match="not applicable when slice_kind"):
        ch.validate_structure(fields)


def test_tooling_slice_may_omit_focused_test_with_none_selector() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["focused_test_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    ch.validate_structure(fields)  # must not raise


def test_numeric_focused_count_requires_a_real_selector_not_none() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["focused_test_selector"] = "none"
    with pytest.raises(ch.HandoffValidationError, match="requires a real 'focused_test_selector'"):
        ch.validate_structure(fields)


# --------------------------------------------------------------------------
# validate_structure — docs slice_kind and not_run semantics
# --------------------------------------------------------------------------

_DOCS_NOT_RUN_FIELDS = {
    "workflow_version": "v3.1-pilot",
    "slice_kind": "docs",
    "verification_level": "not_run",
    "focused_test_selector": "none",
    "focused_test_count": "not_run",
    "full_suite_count": "not_run",
    "lightweight_checks": "ruff format --check, check_repo.py, git diff --check",
}


def test_valid_docs_not_run_metadata_passes() -> None:
    ch.validate_structure(dict(_DOCS_NOT_RUN_FIELDS))


def test_not_run_is_rejected_for_a_parser_slice_even_structurally() -> None:
    """Previously `verification_level: not_run` was accepted for any
    `slice_kind` as long as the other not_run fields were consistent — a
    parser slice could bypass focus-testing entirely this way. Reproduced
    by constructing exactly this input; must be rejected independent of
    how `verify.py` was invoked (structural check alone, no run involved)."""
    fields = dict(_PARSER_FIELDS)
    fields["verification_level"] = "not_run"
    fields["focused_test_count"] = "not_run"
    fields["full_suite_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    fields["lightweight_checks"] = "ruff format --check"
    with pytest.raises(
        ch.HandoffValidationError, match="not_run is only permitted when slice_kind: docs"
    ):
        ch.validate_structure(fields)


def test_not_run_is_rejected_for_a_tooling_slice_even_structurally() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["verification_level"] = "not_run"
    fields["focused_test_count"] = "not_run"
    fields["full_suite_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    fields["lightweight_checks"] = "ruff format --check"
    with pytest.raises(
        ch.HandoffValidationError, match="not_run is only permitted when slice_kind: docs"
    ):
        ch.validate_structure(fields)


def test_docs_not_run_requires_none_focused_test_selector() -> None:
    fields = dict(_DOCS_NOT_RUN_FIELDS)
    fields["focused_test_selector"] = "backend/tests/test_x.py"
    with pytest.raises(
        ch.HandoffValidationError, match="not_run requires 'focused_test_selector: none'"
    ):
        ch.validate_structure(fields)


def test_docs_not_run_requires_lightweight_checks() -> None:
    fields = dict(_DOCS_NOT_RUN_FIELDS)
    del fields["lightweight_checks"]
    with pytest.raises(
        ch.HandoffValidationError, match="requires a non-empty 'lightweight_checks'"
    ):
        ch.validate_structure(fields)


def test_not_run_rejects_a_fabricated_full_suite_count() -> None:
    """The exact defect this schema exists to prevent: a docs-only entry
    that claims verification_level: not_run but still states a numeric
    count — which could only be a stale copy-paste, never a real
    observation, since the run that would have produced it never happened."""
    fields = dict(_DOCS_NOT_RUN_FIELDS)
    fields["full_suite_count"] = "1800"
    with pytest.raises(ch.HandoffValidationError, match="never a fabricated number"):
        ch.validate_structure(fields)


def test_not_run_rejects_a_fabricated_focused_count() -> None:
    fields = dict(_DOCS_NOT_RUN_FIELDS)
    fields["focused_test_count"] = "10"
    with pytest.raises(ch.HandoffValidationError, match="never a fabricated number"):
        ch.validate_structure(fields)


def test_docs_slice_may_also_declare_routine_verification_with_real_counts() -> None:
    """A docs change may still choose to run the full suite anyway — this
    is a legitimate, non-not_run path, and lightweight_checks must then be
    absent (not applicable)."""
    fields = {
        "workflow_version": "v3.1-pilot",
        "slice_kind": "docs",
        "verification_level": "routine",
        "focused_test_selector": "none",
        "focused_test_count": "not_run",
        "full_suite_count": "1800",
    }
    ch.validate_structure(fields)


def test_routine_level_rejects_lightweight_checks_as_inapplicable() -> None:
    fields = {
        "workflow_version": "v3.1-pilot",
        "slice_kind": "docs",
        "verification_level": "routine",
        "focused_test_selector": "none",
        "focused_test_count": "not_run",
        "full_suite_count": "1800",
        "lightweight_checks": "ruff format --check",
    }
    with pytest.raises(ch.HandoffValidationError, match="only applicable when verification_level"):
        ch.validate_structure(fields)


def test_routine_level_rejects_not_run_full_suite_count() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["full_suite_count"] = "not_run"
    with pytest.raises(ch.HandoffValidationError, match="requires an actual 'full_suite_count'"):
        ch.validate_structure(fields)


# --------------------------------------------------------------------------
# _require_int — ASCII-only integer parsing (Codex review finding: plain
# str.isdigit() accepts non-ASCII "digit" characters that int() itself then
# rejects with an unhandled ValueError)
# --------------------------------------------------------------------------


def test_require_int_accepts_a_plain_ascii_integer() -> None:
    assert ch._require_int({"n": "1800"}, "n") == 1800


def test_require_int_rejects_a_non_ascii_digit_character() -> None:
    """`'²'.isdigit()` is `True` in Python, but `int('²')` raises
    `ValueError` — the old `str.isdigit()` check let this reach `int()`
    unguarded. Reproduced with the exact superscript-two character."""
    with pytest.raises(ch.HandoffValidationError, match="must be a non-negative integer"):
        ch._require_int({"n": "²"}, "n")


def test_validate_structure_rejects_a_non_ascii_digit_full_suite_count() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["full_suite_count"] = "²"
    with pytest.raises(ch.HandoffValidationError, match="must be a non-negative integer"):
        ch.validate_structure(fields)


# --------------------------------------------------------------------------
# validate_fixture_count — real file cross-check
# --------------------------------------------------------------------------


def test_fixture_count_matches_actual_json_array_length(tmp_path: Path) -> None:
    fixture_file = tmp_path / "backend" / "tests" / "fixtures" / "normalization" / "x_cases.json"
    fixture_file.parent.mkdir(parents=True)
    fixture_file.write_text(json.dumps([{"id": "a"}, {"id": "b"}, {"id": "c"}]), encoding="utf-8")

    fields = dict(_PARSER_FIELDS)
    fields["fixture_path"] = "backend/tests/fixtures/normalization/x_cases.json"
    fields["fixture_count"] = "3"

    ch.validate_fixture_count(fields, repo_root=tmp_path)  # must not raise


def test_fixture_count_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture_file = tmp_path / "backend" / "tests" / "fixtures" / "normalization" / "x_cases.json"
    fixture_file.parent.mkdir(parents=True)
    fixture_file.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf-8")

    fields = dict(_PARSER_FIELDS)
    fields["fixture_path"] = "backend/tests/fixtures/normalization/x_cases.json"
    fields["fixture_count"] = "3"

    with pytest.raises(ch.HandoffValidationError, match="does not match the actual"):
        ch.validate_fixture_count(fields, repo_root=tmp_path)


def test_fixture_count_is_a_no_op_when_fixture_path_absent() -> None:
    ch.validate_fixture_count(dict(_TOOLING_FIELDS))  # must not raise, must not read anything


def test_fixture_path_must_contain_a_json_array_not_an_object(tmp_path: Path) -> None:
    fixture_file = tmp_path / "backend" / "tests" / "fixtures" / "normalization" / "x_cases.json"
    fixture_file.parent.mkdir(parents=True)
    fixture_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    fields = dict(_PARSER_FIELDS)
    fields["fixture_path"] = "backend/tests/fixtures/normalization/x_cases.json"

    with pytest.raises(ch.HandoffValidationError, match="must contain a JSON array"):
        ch.validate_fixture_count(fields, repo_root=tmp_path)


def test_fixture_path_missing_file_fails_closed(tmp_path: Path) -> None:
    fields = dict(_PARSER_FIELDS)
    fields["fixture_path"] = "backend/tests/fixtures/normalization/does_not_exist.json"
    with pytest.raises(ch.HandoffValidationError, match="could not be read"):
        ch.validate_fixture_count(fields, repo_root=tmp_path)


def test_fixture_path_invalid_json_fails_closed(tmp_path: Path) -> None:
    fixture_file = tmp_path / "backend" / "tests" / "fixtures" / "normalization" / "x_cases.json"
    fixture_file.parent.mkdir(parents=True)
    fixture_file.write_text("{not valid json", encoding="utf-8")

    fields = dict(_PARSER_FIELDS)
    fields["fixture_path"] = "backend/tests/fixtures/normalization/x_cases.json"

    with pytest.raises(ch.HandoffValidationError, match="not valid JSON"):
        ch.validate_fixture_count(fields, repo_root=tmp_path)


# --------------------------------------------------------------------------
# _read_handoff_text — file-read boundary hardening (Codex review finding:
# a missing/unreadable/undecodable handoff file previously raised
# FileNotFoundError/OSError/UnicodeDecodeError uncaught, bypassing both
# verify.py's handoff_metadata_step StepResult handling and this module's
# own main())
# --------------------------------------------------------------------------


def test_read_handoff_text_converts_a_missing_file_to_handoff_validation_error(
    tmp_path: Path,
) -> None:
    missing_path = tmp_path / "does_not_exist.md"
    with pytest.raises(ch.HandoffValidationError, match="could not be read"):
        ch._read_handoff_text(missing_path)


def test_read_handoff_text_converts_invalid_utf8_to_handoff_validation_error(
    tmp_path: Path,
) -> None:
    bad_path = tmp_path / "bad-encoding.md"
    bad_path.write_bytes(b"\xff\xfe\x00\x01 not valid utf-8")
    with pytest.raises(ch.HandoffValidationError, match="could not be decoded"):
        ch._read_handoff_text(bad_path)


def test_validate_handoff_converts_a_missing_file_to_handoff_validation_error(
    tmp_path: Path,
) -> None:
    """End-to-end through the real entry point `verify.py` calls: a missing
    `docs/LLM_HANDOFF.md` must surface as `HandoffValidationError` (which
    `verify.handoff_metadata_step` already catches and reports as a clean
    FAIL step), never as an uncaught `FileNotFoundError`."""
    missing_path = tmp_path / "docs" / "LLM_HANDOFF.md"
    with pytest.raises(ch.HandoffValidationError, match="could not be read"):
        ch.validate_handoff(
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=None,
            actual_focus_selector=None,
            handoff_path=missing_path,
            repo_root=tmp_path,
        )


def test_main_reports_failure_cleanly_for_a_missing_handoff_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(ch, "HANDOFF_PATH", tmp_path / "docs" / "LLM_HANDOFF.md")
    exit_code = ch.main()
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "handoff metadata validation failed" in output
    assert "could not be read" in output


# --------------------------------------------------------------------------
# validate_against_run — cross-checking this run's own observed counts
# --------------------------------------------------------------------------


def test_normal_run_matching_counts_passes() -> None:
    ch.validate_against_run(
        dict(_PARSER_FIELDS),
        docs_only=False,
        actual_full_suite_count=1800,
        actual_focused_count=10,
        actual_focus_selector="backend/tests/test_normalization_x.py",
    )


def test_normal_run_rejects_mismatched_full_suite_count() -> None:
    with pytest.raises(ch.HandoffValidationError, match="does not match this run's actual"):
        ch.validate_against_run(
            dict(_PARSER_FIELDS),
            docs_only=False,
            actual_full_suite_count=1801,
            actual_focused_count=10,
            actual_focus_selector="backend/tests/test_normalization_x.py",
        )


def test_normal_run_rejects_mismatched_focused_count() -> None:
    with pytest.raises(ch.HandoffValidationError, match="focused_test_count 10 does not match"):
        ch.validate_against_run(
            dict(_PARSER_FIELDS),
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=11,
            actual_focus_selector="backend/tests/test_normalization_x.py",
        )


def test_parser_slice_requires_focus_selector_to_match_actual_focus_used() -> None:
    with pytest.raises(ch.HandoffValidationError, match="does not match the --focus value"):
        ch.validate_against_run(
            dict(_PARSER_FIELDS),
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=10,
            actual_focus_selector="backend/tests/test_normalization_y.py",
        )


def test_parser_slice_requires_focus_to_have_been_used_at_all() -> None:
    """Isolated unit test of `validate_against_run` alone: a parser-slice
    metadata block that declares `focused_test_count: not_run` would
    already be rejected by `validate_structure` before reaching this
    function in the real pipeline — but `validate_against_run` must still
    independently refuse to treat an unfocused invocation as sufficient
    for a parser slice, as its own defense in depth."""
    fields = dict(_PARSER_FIELDS)
    fields["focused_test_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    with pytest.raises(ch.HandoffValidationError, match="requires this verify.py invocation"):
        ch.validate_against_run(
            fields,
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=None,
            actual_focus_selector=None,
        )


def test_tooling_slice_without_focus_is_accepted_when_declared_not_run() -> None:
    fields = dict(_TOOLING_FIELDS)
    fields["focused_test_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    ch.validate_against_run(
        fields,
        docs_only=False,
        actual_full_suite_count=1800,
        actual_focused_count=None,
        actual_focus_selector=None,
    )


def test_docs_only_run_rejects_a_parser_slice_kind() -> None:
    """Codex review finding: `--docs-only` previously only checked
    `verification_level`, never `slice_kind` — any parser-slice metadata
    (here, ordinary routine fields, deliberately *not* a not_run
    declaration) would silently pass a `--docs-only` run's cross-check as
    long as `docs_only` short-circuited before the count checks. Calling
    `validate_against_run` directly (bypassing `validate_structure`) isolates
    this specific check."""
    with pytest.raises(ch.HandoffValidationError, match="not 'docs'"):
        ch.validate_against_run(
            dict(_PARSER_FIELDS),
            docs_only=True,
            actual_full_suite_count=None,
            actual_focused_count=None,
            actual_focus_selector=None,
        )


def test_docs_only_run_rejects_a_tooling_slice_kind() -> None:
    with pytest.raises(ch.HandoffValidationError, match="not 'docs'"):
        ch.validate_against_run(
            dict(_TOOLING_FIELDS),
            docs_only=True,
            actual_full_suite_count=None,
            actual_focused_count=None,
            actual_focus_selector=None,
        )


def test_docs_only_run_with_docs_slice_kind_but_routine_level_still_requires_not_run() -> None:
    """Distinguishes the two independent `docs_only` checks: this fixture
    passes the (new) slice_kind check but must still fail the (pre-existing)
    verification_level check, proving both fire independently rather than
    one masking the other."""
    fields = {
        "workflow_version": "v3.1-pilot",
        "slice_kind": "docs",
        "verification_level": "routine",
        "focused_test_selector": "none",
        "focused_test_count": "not_run",
        "full_suite_count": "1800",
    }
    with pytest.raises(ch.HandoffValidationError, match="verify.py was invoked with --docs-only"):
        ch.validate_against_run(
            fields,
            docs_only=True,
            actual_full_suite_count=None,
            actual_focused_count=None,
            actual_focus_selector=None,
        )


def test_docs_only_run_with_not_run_declared_passes_without_further_checks() -> None:
    ch.validate_against_run(
        dict(_DOCS_NOT_RUN_FIELDS),
        docs_only=True,
        actual_full_suite_count=None,
        actual_focused_count=None,
        actual_focus_selector=None,
    )


def test_full_run_rejects_a_not_run_declaration() -> None:
    """The inverse mismatch: the suite genuinely ran (this is not a
    --docs-only invocation), but the metadata still claims not_run —
    always an error, never silently accepted as 'extra caution'."""
    with pytest.raises(ch.HandoffValidationError, match="actually ran the full suite"):
        ch.validate_against_run(
            dict(_DOCS_NOT_RUN_FIELDS),
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=None,
            actual_focus_selector=None,
        )


def test_unparseable_full_suite_summary_fails_closed_not_silently_accepted() -> None:
    with pytest.raises(ch.HandoffValidationError, match="could not be parsed"):
        ch.validate_against_run(
            dict(_TOOLING_FIELDS),
            docs_only=False,
            actual_full_suite_count=None,
            actual_focused_count=20,
            actual_focus_selector="backend/tests/test_check_handoff.py",
        )


# --------------------------------------------------------------------------
# validate_against_run — Codex review finding: omitted vs. unparseable focus,
# and focus-selector matching applying to every slice_kind (not only parser)
# --------------------------------------------------------------------------


def test_omitted_focus_is_accepted_for_tooling_declared_not_run() -> None:
    """Control case: --focus genuinely never given (actual_focus_selector
    is None) — the pre-existing, still-correct 'omitted' path."""
    fields = dict(_TOOLING_FIELDS)
    fields["focused_test_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    ch.validate_against_run(
        fields,
        docs_only=False,
        actual_full_suite_count=1800,
        actual_focused_count=None,
        actual_focus_selector=None,
    )


def test_focus_used_but_unparseable_rejects_a_not_run_declaration() -> None:
    """Codex review finding: previously, when --focus genuinely ran but its
    pytest summary line could not be parsed (actual_focused_count is None
    for a *different* reason than 'omitted'), a tooling/docs metadata
    declaring focused_test_count: not_run silently passed — indistinguishable
    from focus never having run at all. Reproduced by supplying a real
    actual_focus_selector (proving focus ran) alongside actual_focused_count
    of None (proving its summary didn't parse)."""
    fields = dict(_TOOLING_FIELDS)
    fields["focused_test_count"] = "not_run"
    fields["focused_test_selector"] = "none"
    with pytest.raises(ch.HandoffValidationError, match="declares focused_test_count: not_run"):
        ch.validate_against_run(
            fields,
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=None,
            actual_focus_selector="backend/tests/test_check_handoff.py",
        )


def test_focused_summary_unparseable_when_focus_was_used_fails_closed() -> None:
    """A numeric focused_test_count is declared, --focus genuinely ran, but
    its summary line didn't parse — must fail closed, never silently treat
    the declared count as unverifiable-but-fine."""
    with pytest.raises(
        ch.HandoffValidationError, match="focused pytest summary could not be parsed"
    ):
        ch.validate_against_run(
            dict(_TOOLING_FIELDS),
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=None,
            actual_focus_selector="backend/tests/test_check_handoff.py",
        )


def test_tooling_slice_focus_selector_mismatch_is_also_rejected() -> None:
    """Codex review finding: the declared-vs-actual focus-selector match
    was previously checked only when slice_kind == 'parser' — a tooling (or
    docs) slice with a genuinely mismatched selector, but matching counts,
    silently passed. Reproduced with matching counts (20) but a different
    actual selector than declared."""
    with pytest.raises(ch.HandoffValidationError, match="does not match the --focus value"):
        ch.validate_against_run(
            dict(_TOOLING_FIELDS),
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=20,
            actual_focus_selector="backend/tests/test_some_other_file.py",
        )


# --------------------------------------------------------------------------
# validate_handoff — end-to-end wiring (still no subprocess, real temp files)
# --------------------------------------------------------------------------


def test_validate_handoff_end_to_end_success(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "backend" / "tests" / "fixtures" / "normalization"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "x_cases.json").write_text(json.dumps([{"id": "a"}] * 5), encoding="utf-8")

    handoff_path = tmp_path / "docs" / "LLM_HANDOFF.md"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        _handoff(
            iterations=[
                "## Iteration 1\n\n### Work done\n\n" + _metadata_block(_PARSER_FIELDS) + "\n"
            ]
        ),
        encoding="utf-8",
    )

    ch.validate_handoff(
        docs_only=False,
        actual_full_suite_count=1800,
        actual_focused_count=10,
        actual_focus_selector="backend/tests/test_normalization_x.py",
        handoff_path=handoff_path,
        repo_root=tmp_path,
    )


def test_validate_handoff_end_to_end_failure_propagates_a_precise_message(tmp_path: Path) -> None:
    handoff_path = tmp_path / "docs" / "LLM_HANDOFF.md"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        _handoff(iterations=["## Iteration 1\n\n### Work done\n\nno metadata block.\n"]),
        encoding="utf-8",
    )

    with pytest.raises(ch.HandoffValidationError, match="no 'workflow-metadata' block"):
        ch.validate_handoff(
            docs_only=False,
            actual_full_suite_count=1800,
            actual_focused_count=None,
            actual_focus_selector=None,
            handoff_path=handoff_path,
            repo_root=tmp_path,
        )


def test_validate_handoff_end_to_end_docs_only_rejects_a_parser_entry(tmp_path: Path) -> None:
    """Codex review finding, exercised through the real end-to-end entry
    point: a `--docs-only` invocation (`docs_only=True`) must reject an
    ordinary, structurally-valid routine parser entry — `--docs-only` is
    never valid for a parser slice, independent of what verification_level
    it declares. Uses unmodified routine `_PARSER_FIELDS` so `validate_structure`
    passes cleanly and the rejection is specifically `validate_against_run`'s
    new `docs_only` + `slice_kind` cross-check."""
    handoff_path = tmp_path / "docs" / "LLM_HANDOFF.md"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        _handoff(
            iterations=[
                "## Iteration 1\n\n### Work done\n\n" + _metadata_block(_PARSER_FIELDS) + "\n"
            ]
        ),
        encoding="utf-8",
    )
    fixture_dir = tmp_path / "backend" / "tests" / "fixtures" / "normalization"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "x_cases.json").write_text(json.dumps([{"id": "a"}] * 5), encoding="utf-8")

    with pytest.raises(ch.HandoffValidationError, match="not 'docs'"):
        ch.validate_handoff(
            docs_only=True,
            actual_full_suite_count=None,
            actual_focused_count=None,
            actual_focus_selector=None,
            handoff_path=handoff_path,
            repo_root=tmp_path,
        )


def test_validate_handoff_end_to_end_docs_only_rejects_a_tooling_entry(tmp_path: Path) -> None:
    handoff_path = tmp_path / "docs" / "LLM_HANDOFF.md"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        _handoff(
            iterations=[
                "## Iteration 1\n\n### Work done\n\n" + _metadata_block(_TOOLING_FIELDS) + "\n"
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ch.HandoffValidationError, match="not 'docs'"):
        ch.validate_handoff(
            docs_only=True,
            actual_full_suite_count=None,
            actual_focused_count=None,
            actual_focus_selector=None,
            handoff_path=handoff_path,
            repo_root=tmp_path,
        )


def test_validate_handoff_end_to_end_docs_only_accepts_a_docs_entry(tmp_path: Path) -> None:
    handoff_path = tmp_path / "docs" / "LLM_HANDOFF.md"
    handoff_path.parent.mkdir(parents=True)
    handoff_path.write_text(
        _handoff(
            iterations=[
                "## Iteration 1\n\n### Work done\n\n" + _metadata_block(_DOCS_NOT_RUN_FIELDS) + "\n"
            ]
        ),
        encoding="utf-8",
    )

    ch.validate_handoff(
        docs_only=True,
        actual_full_suite_count=None,
        actual_focused_count=None,
        actual_focus_selector=None,
        handoff_path=handoff_path,
        repo_root=tmp_path,
    )  # must not raise
