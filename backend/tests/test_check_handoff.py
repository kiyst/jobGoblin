"""Tests for Workflow v3.2's schema-v2 handoff-metadata validator.

Supersedes the prior Workflow v3.1-pilot test suite, which exercised a
schema and a `validate_against_run` cross-check mechanism this activation
removes entirely (counts now live authoritatively in the receipt, never
hand-typed into the handoff -- see `docs/DECISIONS/0009-workflow-v3.2-
activation.md`)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_handoff as ch

_BASE_SHA = "6" * 40
_SLICE_ID = f"2026-09-13-example-slice-{_BASE_SHA[:7]}"
_CANDIDATE_SHA = "c" * 40
_RECEIPT_ID = "12345678-1234-4123-8123-123456789012"


def _pending_fields(**overrides: str) -> dict[str, str]:
    fields = {
        "workflow_version": "v3.2",
        "state": "pending",
        "slice_id": _SLICE_ID,
        "slice_kind": "tooling",
        "risk_class": "H",
        "base_sha": _BASE_SHA,
        "declared_gate": "final",
    }
    fields.update(overrides)
    return fields


def _published_fields(**overrides: str) -> dict[str, str]:
    fields = _pending_fields(
        state="published",
        executed_gate="final",
        candidate_sha=_CANDIDATE_SHA,
        receipt_id=_RECEIPT_ID,
        receipt_path=f"docs/verification-receipts/{_CANDIDATE_SHA}/{_RECEIPT_ID}.json",
    )
    fields.update(overrides)
    return fields


def _render(fields: dict[str, str]) -> str:
    return "\n".join(f"{k}: {v}" for k, v in fields.items())


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_metadata_fields_rejects_duplicate_key() -> None:
    with pytest.raises(ch.HandoffValidationError, match="duplicate metadata key"):
        ch.parse_metadata_fields("a: 1\na: 2\n")


def test_parse_metadata_fields_rejects_malformed_line() -> None:
    with pytest.raises(ch.HandoffValidationError, match="malformed metadata line"):
        ch.parse_metadata_fields("not-a-key-value-line\n")


def test_parse_metadata_fields_ignores_blank_lines() -> None:
    fields = ch.parse_metadata_fields("a: 1\n\nb: 2\n")
    assert fields == {"a": "1", "b": "2"}


# ---------------------------------------------------------------------------
# Pending state
# ---------------------------------------------------------------------------


def test_valid_pending_block_passes() -> None:
    ch.validate_structure(_pending_fields())


def test_pending_rejects_published_only_fields() -> None:
    fields = _pending_fields()
    fields["candidate_sha"] = _CANDIDATE_SHA
    with pytest.raises(ch.HandoffValidationError, match="must not declare"):
        ch.validate_structure(fields)


@pytest.mark.parametrize("missing", list(ch._ALWAYS_REQUIRED_FIELDS))
def test_pending_missing_required_field_rejected(missing: str) -> None:
    fields = _pending_fields()
    del fields[missing]
    with pytest.raises(ch.HandoffValidationError, match="missing required"):
        ch.validate_structure(fields)


def test_unknown_field_rejected() -> None:
    fields = _pending_fields()
    fields["typo_full_sute_count"] = "1"
    with pytest.raises(ch.HandoffValidationError, match="unrecognized field"):
        ch.validate_structure(fields)


def test_wrong_workflow_version_rejected() -> None:
    fields = _pending_fields(workflow_version="v3.1-pilot")
    with pytest.raises(ch.HandoffValidationError, match="workflow_version"):
        ch.validate_structure(fields)


def test_invalid_state_rejected() -> None:
    fields = _pending_fields(state="in_progress")
    with pytest.raises(ch.HandoffValidationError, match="'state'"):
        ch.validate_structure(fields)


def test_invalid_slice_kind_rejected() -> None:
    fields = _pending_fields(slice_kind="feature")
    with pytest.raises(ch.HandoffValidationError, match="slice_kind"):
        ch.validate_structure(fields)


def test_invalid_risk_class_rejected() -> None:
    fields = _pending_fields(risk_class="Z")
    with pytest.raises(ch.HandoffValidationError, match="risk_class"):
        ch.validate_structure(fields)


def test_invalid_declared_gate_rejected() -> None:
    fields = _pending_fields(declared_gate="ultra")
    with pytest.raises(ch.HandoffValidationError, match="declared_gate"):
        ch.validate_structure(fields)


def test_malformed_base_sha_rejected() -> None:
    fields = _pending_fields(base_sha="not-a-sha")
    with pytest.raises(ch.HandoffValidationError, match="base_sha"):
        ch.validate_structure(fields)


def test_malformed_slice_id_rejected() -> None:
    fields = _pending_fields(slice_id="not-a-valid-slice-id")
    with pytest.raises(ch.HandoffValidationError, match="slice_id"):
        ch.validate_structure(fields)


def test_slice_id_base_suffix_must_match_base_sha() -> None:
    fields = _pending_fields(slice_id=f"2026-09-13-example-slice-{'a' * 7}")
    with pytest.raises(ch.HandoffValidationError, match="does not match"):
        ch.validate_structure(fields)


# ---------------------------------------------------------------------------
# Published state
# ---------------------------------------------------------------------------


def test_valid_published_block_passes() -> None:
    ch.validate_structure(_published_fields())


@pytest.mark.parametrize("missing", list(ch._PUBLISHED_ONLY_REQUIRED_FIELDS))
def test_published_missing_required_field_rejected(missing: str) -> None:
    fields = _published_fields()
    del fields[missing]
    with pytest.raises(ch.HandoffValidationError, match="missing required"):
        ch.validate_structure(fields)


def test_executed_gate_must_equal_declared_gate() -> None:
    fields = _published_fields(executed_gate="fast")
    with pytest.raises(ch.HandoffValidationError, match="must equal"):
        ch.validate_structure(fields)


def test_declared_gate_is_retained_unchanged_from_pending_to_published() -> None:
    # The published block must literally carry declared_gate forward --
    # never silently renamed to `gate`.
    fields = _published_fields()
    assert fields["declared_gate"] == "final"
    assert fields["executed_gate"] == "final"


def test_malformed_candidate_sha_rejected() -> None:
    fields = _published_fields(candidate_sha="short")
    with pytest.raises(ch.HandoffValidationError, match="candidate_sha"):
        ch.validate_structure(fields)


def test_malformed_receipt_id_rejected() -> None:
    fields = _published_fields(receipt_id="not-a-uuid")
    with pytest.raises(ch.HandoffValidationError):
        ch.validate_structure(fields)


def test_receipt_path_must_be_derived_exactly() -> None:
    fields = _published_fields(receipt_path="docs/verification-receipts/wrong/path.json")
    with pytest.raises(ch.HandoffValidationError, match="receipt_path"):
        ch.validate_structure(fields)


@pytest.mark.parametrize(
    "count_field", ["full_suite_count", "focused_test_count", "mutation_witness_count"]
)
def test_optional_count_fields_must_be_non_negative_int_when_present(count_field: str) -> None:
    fields = _published_fields(**{count_field: "not-an-int"})
    with pytest.raises(ch.HandoffValidationError, match="non-negative integer"):
        ch.validate_structure(fields)


def test_optional_count_fields_accepted_when_valid() -> None:
    fields = _published_fields(full_suite_count="2323", focused_test_count="130")
    ch.validate_structure(fields)


# ---------------------------------------------------------------------------
# Fixture cross-check (parser slice_kind)
# ---------------------------------------------------------------------------


def test_parser_slice_requires_fixture_fields() -> None:
    fields = _pending_fields(slice_kind="parser")
    with pytest.raises(ch.HandoffValidationError, match="fixture_path"):
        ch.validate_structure(fields)


def test_non_parser_slice_rejects_fixture_fields() -> None:
    fields = _pending_fields(
        fixture_path="tests/contracts/records/location.json", fixture_count="8"
    )
    with pytest.raises(ch.HandoffValidationError, match="not applicable"):
        ch.validate_structure(fields)


def test_fixture_count_cross_checked_against_real_file(tmp_path: Path) -> None:
    fixture = tmp_path / "records.json"
    fixture.write_text('[{"a": 1}, {"a": 2}]', encoding="utf-8")
    fields = _pending_fields(slice_kind="parser", fixture_path="records.json", fixture_count="2")
    ch.validate_fixture_count(fields, repo_root=tmp_path)


def test_fixture_count_mismatch_is_rejected(tmp_path: Path) -> None:
    fixture = tmp_path / "records.json"
    fixture.write_text('[{"a": 1}, {"a": 2}]', encoding="utf-8")
    fields = _pending_fields(slice_kind="parser", fixture_path="records.json", fixture_count="99")
    with pytest.raises(ch.HandoffValidationError, match="does not match"):
        ch.validate_fixture_count(fields, repo_root=tmp_path)


# ---------------------------------------------------------------------------
# End-to-end extraction from a full handoff document
# ---------------------------------------------------------------------------


def _document_with(fields: dict[str, str], *, iterations: int = 1) -> str:
    block = "```workflow-metadata\n" + _render(fields) + "\n```\n"
    sections = []
    for i in range(1, iterations + 1):
        sections.append(f"## Iteration {i}\n\n### Work done\n\n{block if i == iterations else ''}")
    return "\n\n".join(sections)


def test_extracts_metadata_from_newest_iteration_only() -> None:
    doc = _document_with(_pending_fields(), iterations=2)
    text = ch.extract_latest_work_done_metadata_text(doc)
    fields = ch.parse_metadata_fields(text)
    assert fields["state"] == "pending"


def test_validate_handoff_end_to_end(tmp_path: Path) -> None:
    handoff = tmp_path / "LLM_HANDOFF.md"
    handoff.write_text(_document_with(_pending_fields()), encoding="utf-8")
    ch.validate_handoff(handoff_path=handoff, repo_root=tmp_path)


def test_validate_handoff_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ch.HandoffValidationError, match="could not be read"):
        ch.validate_handoff(handoff_path=tmp_path / "missing.md", repo_root=tmp_path)


def test_no_iteration_heading_rejected() -> None:
    with pytest.raises(ch.HandoffValidationError, match="Iteration"):
        ch.extract_latest_work_done_metadata_text("no headings here")


def test_no_work_done_section_rejected() -> None:
    with pytest.raises(ch.HandoffValidationError, match="Work done"):
        ch.extract_latest_work_done_metadata_text("## Iteration 1\n\n### Work review\n")


def test_no_metadata_block_rejected() -> None:
    with pytest.raises(ch.HandoffValidationError, match="workflow-metadata"):
        ch.extract_latest_work_done_metadata_text(
            "## Iteration 1\n\n### Work done\n\nno block here\n"
        )


def test_more_than_one_metadata_block_rejected() -> None:
    doc = (
        "## Iteration 1\n\n### Work done\n\n"
        "```workflow-metadata\na: 1\n```\n"
        "```workflow-metadata\nb: 2\n```\n"
    )
    with pytest.raises(ch.HandoffValidationError, match="more than one"):
        ch.extract_latest_work_done_metadata_text(doc)


def test_main_reports_ok_for_valid_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    handoff = tmp_path / "LLM_HANDOFF.md"
    handoff.write_text(_document_with(_pending_fields()), encoding="utf-8")
    monkeypatch.setattr(ch, "HANDOFF_PATH", handoff)
    monkeypatch.setattr(ch, "REPO_ROOT", tmp_path)
    assert ch.main() == 0
    assert "ok" in capsys.readouterr().out


def test_main_reports_failure_for_invalid_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    handoff = tmp_path / "LLM_HANDOFF.md"
    handoff.write_text(_document_with(_pending_fields(risk_class="Z")), encoding="utf-8")
    monkeypatch.setattr(ch, "HANDOFF_PATH", handoff)
    monkeypatch.setattr(ch, "REPO_ROOT", tmp_path)
    assert ch.main() == 1
    assert "failed" in capsys.readouterr().out
