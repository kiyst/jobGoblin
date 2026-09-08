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


# --------------------------------------------------------------------------
# parse_metadata_fields
# --------------------------------------------------------------------------


def test_parse_metadata_fields_splits_key_value_lines() -> None:
    fields = ch.parse_metadata_fields("a: 1\nb: two\n\nc: 3")
    assert fields == {"a": "1", "b": "two", "c": "3"}


def test_parse_metadata_fields_rejects_a_line_with_no_colon() -> None:
    with pytest.raises(ch.HandoffValidationError, match="malformed metadata line"):
        ch.parse_metadata_fields("a: 1\nthis line has no colon at all")


# --------------------------------------------------------------------------
# validate_structure — parser slice_kind
# --------------------------------------------------------------------------


def test_valid_parser_metadata_passes() -> None:
    ch.validate_structure(dict(_PARSER_FIELDS))  # must not raise


def test_missing_required_field_is_rejected() -> None:
    fields = dict(_PARSER_FIELDS)
    del fields["workflow_version"]
    with pytest.raises(ch.HandoffValidationError, match="missing required field"):
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


def test_docs_only_run_requires_not_run_declared() -> None:
    with pytest.raises(ch.HandoffValidationError, match="verify.py was invoked with --docs-only"):
        ch.validate_against_run(
            dict(_TOOLING_FIELDS),
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
