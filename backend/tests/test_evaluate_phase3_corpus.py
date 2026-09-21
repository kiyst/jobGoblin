from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluate_phase3_corpus import (
    CorpusValidationError,
    MetricCounter,
    SplitEvaluation,
    _evaluate_composite,
    _evaluate_scalar,
    _evaluate_skills,
    evaluate_corpus,
    load_corpus,
)

_KNOWN_IDS = frozenset({"python", "golang", "javascript"})
_TS = "2026-09-20T00:00:00+00:00"


def _annotation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "outcome": "absent",
        "expected_value": None,
        "expected_provenance": "unavailable",
        "annotator_role": "user",
        "rubric_version": "v1",
        "annotation_provenance": "manual read against rubric v1",
        "frozen": True,
        "frozen_at": _TS,
    }
    base.update(overrides)
    return base


def _skill_annotation(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "outcome": "absent",
        "annotator_role": "user",
        "rubric_version": "v1",
        "annotation_provenance": "manual",
        "frozen": True,
        "frozen_at": _TS,
    }
    base.update(overrides)
    return base


def _all_skills(overrides: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    overrides = overrides or {}
    return {cid: overrides.get(cid, _skill_annotation()) for cid in _KNOWN_IDS}


def _composite(
    overrides: dict[str, dict[str, Any]] | None = None, *, components: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    overrides = overrides or {}
    return {c: overrides.get(c, _annotation()) for c in components}


def _base_annotations(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    base = {
        "remote_type": _annotation(),
        "employment_type": _annotation(),
        "seniority": _annotation(),
        "experience": _composite(components=("minimum", "maximum")),
        "salary": _composite(components=("minimum", "maximum", "currency", "period")),
        "location": _composite(components=("city", "state", "country", "postal_code")),
        "skills": _all_skills(),
    }
    base.update(overrides)
    return base


def _base_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": "rec-1",
        "provenance": {
            "provider": "greenhouse",
            "employer": "Acme",
            "template_family": "unknown",
            "capture": {
                "board_token": "acme",
                "job_id": "1",
                "accessed_at": _TS,
                "capture_method": "fetch_greenhouse_evaluation_postings.py",
            },
            "sanitization_lineage": "manually reviewed",
            "origin": "sanitized_capture",
            "manual_review": {"reviewer": "user", "reviewed_at": _TS, "notes": "looks fine"},
        },
        "split": "dev",
        "fields": {
            "title": "Remote Software Engineer",
            "description": None,
            "location_raw": None,
            "compensation_text": None,
        },
        "annotations": _base_annotations(),
    }
    record.update(overrides)
    return record


def _minimal_corpus() -> list[dict[str, Any]]:
    """The smallest corpus satisfying partitioning: one `dev` and one
    `holdout` record, disjoint employers."""
    dev = _base_record(id="dev-1", split="dev")
    holdout = _base_record(id="holdout-1", split="holdout")
    holdout["provenance"] = {**holdout["provenance"], "employer": "Globex"}
    return [dev, holdout]


def _write_corpus(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


def _write_raw(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loader -- structural fail-closed rules
# ---------------------------------------------------------------------------
def test_load_corpus_accepts_a_well_formed_minimal_corpus(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, _minimal_corpus())
    records = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert len(records) == 2


def test_load_corpus_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = _write_raw(tmp_path, '[{"id": "a", "id": "b"}]')
    with pytest.raises(CorpusValidationError, match="duplicate JSON key"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_duplicate_json_keys_in_nested_object(tmp_path: Path) -> None:
    raw = json.dumps(_minimal_corpus())
    # Inject a duplicate key inside a nested annotation object, by hand,
    # since json.dumps never produces one itself.
    injected = raw.replace('"outcome": "absent"', '"outcome": "absent", "outcome": "absent"', 1)
    path = _write_raw(tmp_path, injected)
    with pytest.raises(CorpusValidationError, match="duplicate JSON key"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_empty_corpus(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, [])
    with pytest.raises(CorpusValidationError, match="at least one record"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_non_list_top_level(tmp_path: Path) -> None:
    path = _write_raw(tmp_path, json.dumps({"not": "a list"}))
    with pytest.raises(CorpusValidationError, match="JSON array"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_duplicate_record_id(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[1]["id"] = records[0]["id"]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="duplicate record id"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


# ---------------------------------------------------------------------------
# Exhaustiveness -- every scalar parser, every composite component, every
# taxonomy id under skills must be present.
# ---------------------------------------------------------------------------
def test_load_corpus_rejects_missing_scalar_parser_annotation(tmp_path: Path) -> None:
    records = _minimal_corpus()
    del records[0]["annotations"]["seniority"]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="missing required annotation key"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_missing_composite_component(tmp_path: Path) -> None:
    records = _minimal_corpus()
    del records[0]["annotations"]["salary"]["currency"]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="missing required component"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_missing_skill_canonical_id(tmp_path: Path) -> None:
    records = _minimal_corpus()
    del records[0]["annotations"]["skills"]["python"]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="missing required canonical id"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unknown_skill_canonical_id(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["skills"]["not_a_real_skill"] = _skill_annotation()
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="unknown id"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_all_four_skill_outcomes_simultaneously(tmp_path: Path) -> None:
    """One record's skills annotations may mix all four outcomes across
    different canonical ids -- exercised end to end in the metrics
    section below; here just proving the loader accepts it."""
    records = _minimal_corpus()
    records[0]["annotations"]["skills"] = _all_skills(
        {
            "python": _skill_annotation(outcome="present_supported"),
            "golang": _skill_annotation(outcome="present_unsupported_form"),
            "javascript": _skill_annotation(outcome="ambiguous"),
        }
    )
    path = _write_corpus(tmp_path, records)
    records_loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert len(records_loaded) == 2


# ---------------------------------------------------------------------------
# Value/provenance validity, per parser/component
# ---------------------------------------------------------------------------
def test_load_corpus_rejects_boolean_where_int_expected(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["experience"]["minimum"] = _annotation(
        outcome="present_supported", expected_value=True, expected_provenance="inferred"
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="not valid for"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_a_real_int_where_int_expected(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["experience"]["minimum"] = _annotation(
        outcome="present_supported", expected_value=3, expected_provenance="inferred"
    )
    path = _write_corpus(tmp_path, records)
    records_loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert records_loaded[0].annotations["experience"]["minimum"]["expected_value"] == 3


def test_load_corpus_rejects_wrong_parser_expected_value(tmp_path: Path) -> None:
    """`"full_time"` is a valid `employment_type` value but not a valid
    `remote_type` value -- the validator must be parser-specific, not a
    bare type check."""
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported", expected_value="full_time", expected_provenance="inferred"
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="not valid for 'remote_type'"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_a_valid_remote_type_value(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported", expected_value="remote", expected_provenance="inferred"
    )
    path = _write_corpus(tmp_path, records)
    records_loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert records_loaded[0].annotations["remote_type"]["expected_value"] == "remote"


# ---------------------------------------------------------------------------
# Timestamps, capture, manual review
# ---------------------------------------------------------------------------
def test_load_corpus_rejects_naive_frozen_at(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"]["frozen_at"] = "2026-09-20T00:00:00"  # no tz
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="frozen_at"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_malformed_capture_board_token(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["provenance"]["capture"]["board_token"] = "not a token!"
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="board_token"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_malformed_capture_job_id(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["provenance"]["capture"]["job_id"] = "not-numeric"
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="job_id"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_naive_capture_accessed_at(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["provenance"]["capture"]["accessed_at"] = "2026-09-20T00:00:00"
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="accessed_at"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_missing_manual_review(tmp_path: Path) -> None:
    records = _minimal_corpus()
    del records[0]["provenance"]["manual_review"]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="missing required field"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_empty_manual_reviewer(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["provenance"]["manual_review"]["reviewer"] = ""
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="manual_review.reviewer"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_naive_manual_review_reviewed_at(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["provenance"]["manual_review"]["reviewed_at"] = "2026-09-20T00:00:00"
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="reviewed_at"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


# ---------------------------------------------------------------------------
# Disagreement / adjudication -- full shape and consistency
# ---------------------------------------------------------------------------
def _resolved_disagreement(
    *, second_value: Any, final_outcome: str, final_value: Any, final_provenance: str
) -> dict[str, Any]:
    return {
        "second_annotation": _annotation(
            outcome="present_supported", expected_value=second_value, expected_provenance="inferred"
        ),
        "adjudication": {
            "final_outcome": final_outcome,
            "final_value": final_value,
            "final_provenance": final_provenance,
            "adjudicated_by": "user",
            "adjudicated_at": _TS,
        },
    }


def test_load_corpus_accepts_a_fully_consistent_resolved_disagreement(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=_resolved_disagreement(
            second_value="hybrid",
            final_outcome="present_supported",
            final_value="remote",
            final_provenance="inferred",
        ),
    )
    path = _write_corpus(tmp_path, records)
    loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert loaded[0].annotations["remote_type"]["expected_value"] == "remote"


def test_load_corpus_accepts_disagreement_differing_only_in_outcome(tmp_path: Path) -> None:
    """Primary and second agree on `expected_value`/`expected_provenance`
    (both null/unavailable) and differ in `outcome` alone -- still a
    genuine, independently-detectable disagreement."""
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value=None,
        expected_provenance="unavailable",
        disagreement={
            "second_annotation": _annotation(
                outcome="absent", expected_value=None, expected_provenance="unavailable"
            ),
            "adjudication": {
                "final_outcome": "present_supported",
                "final_value": None,
                "final_provenance": "unavailable",
                "adjudicated_by": "user",
                "adjudicated_at": _TS,
            },
        },
    )
    path = _write_corpus(tmp_path, records)
    loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert loaded[0].annotations["remote_type"]["outcome"] == "present_supported"


def test_load_corpus_accepts_disagreement_differing_only_in_provenance(tmp_path: Path) -> None:
    """Primary and second agree on `outcome`/`expected_value` and differ
    in `expected_provenance` alone -- still a genuine disagreement."""
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement={
            "second_annotation": _annotation(
                outcome="present_supported", expected_value="remote", expected_provenance="derived"
            ),
            "adjudication": {
                "final_outcome": "present_supported",
                "final_value": "remote",
                "final_provenance": "inferred",
                "adjudicated_by": "user",
                "adjudicated_at": _TS,
            },
        },
    )
    path = _write_corpus(tmp_path, records)
    loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert loaded[0].annotations["remote_type"]["expected_provenance"] == "inferred"


def test_load_corpus_rejects_disagreement_with_no_actual_difference(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=_resolved_disagreement(
            second_value="remote",  # identical to the primary -- not a real disagreement
            final_outcome="present_supported",
            final_value="remote",
            final_provenance="inferred",
        ),
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="no actual difference"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_adjudication_inconsistent_with_expected_value(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=_resolved_disagreement(
            second_value="hybrid",
            final_outcome="present_supported",
            final_value="onsite",
            final_provenance="inferred",
        ),
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="does not match the resolved"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_adjudication_resolving_only_a_null_value(tmp_path: Path) -> None:
    """Sol's exact reproduction: a primary annotation that is absent/
    null/unavailable disagreeing with a second annotation that is
    present_supported/remote/inferred must not be silently accepted by
    an adjudication that resolves only a null `final_value` (the only
    field the previous schema checked) -- the adjudication must resolve
    the complete label (`final_outcome`/`final_value`/`final_provenance`),
    and an incomplete one fails closed rather than coincidentally
    matching the primary's own null value."""
    records = _minimal_corpus()
    disagreement = {
        "second_annotation": _annotation(
            outcome="present_supported", expected_value="remote", expected_provenance="inferred"
        ),
        "adjudication": {
            "final_value": None,
            "adjudicated_by": "user",
            "adjudicated_at": _TS,
        },
    }
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="absent",
        expected_value=None,
        expected_provenance="unavailable",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="adjudication must declare exactly"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unresolved_disagreement(tmp_path: Path) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="hybrid",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    disagreement["adjudication"] = None
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="unresolved"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_adjudication_missing_adjudicated_by(tmp_path: Path) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="hybrid",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    del disagreement["adjudication"]["adjudicated_by"]
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="adjudication must declare exactly"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_second_annotation_missing_metadata(tmp_path: Path) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="hybrid",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    del disagreement["second_annotation"]["rubric_version"]
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="rubric_version"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_second_annotation_with_invalid_outcome(tmp_path: Path) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="hybrid",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    disagreement["second_annotation"]["outcome"] = "not_a_real_outcome"
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="outcome must be one of"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_second_annotation_with_invalid_expected_provenance(
    tmp_path: Path,
) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="hybrid",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    disagreement["second_annotation"]["expected_provenance"] = "not_a_real_provenance"
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="expected_provenance must be one of"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_second_annotation_with_a_disagreement_of_its_own(
    tmp_path: Path,
) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="hybrid",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    disagreement["second_annotation"]["disagreement"] = _resolved_disagreement(
        second_value="onsite",
        final_outcome="present_supported",
        final_value="hybrid",
        final_provenance="inferred",
    )
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="unrecognized field"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_second_annotation_with_invalid_value(tmp_path: Path) -> None:
    records = _minimal_corpus()
    disagreement = _resolved_disagreement(
        second_value="not_a_real_remote_type_value",
        final_outcome="present_supported",
        final_value="remote",
        final_provenance="inferred",
    )
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        disagreement=disagreement,
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="not valid for"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_a_resolved_disagreement_on_a_skill_id_annotation(
    tmp_path: Path,
) -> None:
    records = _minimal_corpus()
    disagreement = {
        "second_annotation": _skill_annotation(outcome="present_unsupported_form"),
        "adjudication": {
            "final_outcome": "present_supported",
            "adjudicated_by": "user",
            "adjudicated_at": _TS,
        },
    }
    records[0]["annotations"]["skills"] = _all_skills(
        {"python": _skill_annotation(outcome="present_supported", disagreement=disagreement)}
    )
    path = _write_corpus(tmp_path, records)
    loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert loaded[0].annotations["skills"]["python"]["outcome"] == "present_supported"


def test_load_corpus_rejects_skill_id_disagreement_with_no_actual_difference(
    tmp_path: Path,
) -> None:
    records = _minimal_corpus()
    disagreement = {
        "second_annotation": _skill_annotation(outcome="present_supported"),
        "adjudication": {
            "final_outcome": "present_supported",
            "adjudicated_by": "user",
            "adjudicated_at": _TS,
        },
    }
    records[0]["annotations"]["skills"] = _all_skills(
        {"python": _skill_annotation(outcome="present_supported", disagreement=disagreement)}
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="no actual difference"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_skill_id_adjudication_inconsistent_with_outcome(
    tmp_path: Path,
) -> None:
    records = _minimal_corpus()
    disagreement = {
        "second_annotation": _skill_annotation(outcome="present_unsupported_form"),
        "adjudication": {
            "final_outcome": "ambiguous",
            "adjudicated_by": "user",
            "adjudicated_at": _TS,
        },
    }
    records[0]["annotations"]["skills"] = _all_skills(
        {"python": _skill_annotation(outcome="present_supported", disagreement=disagreement)}
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="does not match the resolved"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_skill_id_second_annotation_with_invalid_outcome(
    tmp_path: Path,
) -> None:
    records = _minimal_corpus()
    disagreement = {
        "second_annotation": {**_skill_annotation(), "outcome": "not_a_real_outcome"},
        "adjudication": {
            "final_outcome": "absent",
            "adjudicated_by": "user",
            "adjudicated_at": _TS,
        },
    }
    records[0]["annotations"]["skills"] = _all_skills(
        {"python": _skill_annotation(disagreement=disagreement)}
    )
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="outcome must be one of"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


# ---------------------------------------------------------------------------
# compensation_text substring validation
# ---------------------------------------------------------------------------
def test_load_corpus_accepts_compensation_text_matching_span(tmp_path: Path) -> None:
    records = _minimal_corpus()
    description = "Salary: $100k per year"
    start = description.index("$100k")
    records[0]["fields"]["description"] = description
    records[0]["fields"]["compensation_text"] = "$100k"
    records[0]["fields"]["compensation_text_source_span"] = [start, start + len("$100k")]
    path = _write_corpus(tmp_path, records)
    loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert loaded[0].fields["compensation_text"] == "$100k"


def test_load_corpus_rejects_negative_compensation_text_source_span(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["fields"]["description"] = "Salary: $100k per year"
    records[0]["fields"]["compensation_text"] = "$100k"
    records[0]["fields"]["compensation_text_source_span"] = [-6, -1]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="out of bounds"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_inverted_compensation_text_source_span(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[0]["fields"]["description"] = "Salary: $100k per year"
    records[0]["fields"]["compensation_text"] = ""
    records[0]["fields"]["compensation_text_source_span"] = [5, 2]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="out of bounds"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


# ---------------------------------------------------------------------------
# Partitioning
# ---------------------------------------------------------------------------
def test_load_corpus_rejects_empty_holdout_split(tmp_path: Path) -> None:
    records = [_base_record(id="dev-1", split="dev"), _base_record(id="dev-2", split="dev")]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="no 'holdout' split records"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_empty_dev_split(tmp_path: Path) -> None:
    records = [_base_record(id="h-1", split="holdout"), _base_record(id="h-2", split="holdout")]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="no 'dev' split records"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_same_employer_in_both_splits(tmp_path: Path) -> None:
    records = _minimal_corpus()
    records[1]["provenance"]["employer"] = records[0]["provenance"]["employer"]
    path = _write_corpus(tmp_path, records)
    with pytest.raises(CorpusValidationError, match="employer-disjoint"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_disjoint_employers(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, _minimal_corpus())
    loaded = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    dev_employers = {r.provenance["employer"] for r in loaded if r.split == "dev"}
    holdout_employers = {r.provenance["employer"] for r in loaded if r.split == "holdout"}
    assert not (dev_employers & holdout_employers)


# ---------------------------------------------------------------------------
# Metrics -- denominators, abstention vs. confidently-wrong, one runtime
# failure per invocation, skills' four-way outcome.
# ---------------------------------------------------------------------------
def test_metric_counter_renders_na_on_zero_denominator() -> None:
    assert MetricCounter().render() == "N/A"


def test_abstaining_supported_case_produces_correctness_zero_of_one() -> None:
    """An abstention is incorrect but never also confidently wrong --
    all three metrics share one denominator."""
    evaluation = SplitEvaluation()

    class _Result:
        value = None
        provenance = type("P", (), {"value": "unavailable"})()

    _evaluate_scalar(
        evaluation,
        record_id="r1",
        parser="remote_type",
        annotation=_annotation(
            outcome="present_supported", expected_value="remote", expected_provenance="inferred"
        ),
        fn=lambda: _Result(),
    )
    metrics = evaluation.get_component_metrics("remote_type")
    assert metrics.supported_correctness.render() == "0/1"
    assert metrics.supported_abstention.render() == "1/1"
    assert metrics.confidently_wrong.render() == "0/1"


def test_present_supported_correct_value_scores_correctness_one_of_one() -> None:
    evaluation = SplitEvaluation()

    class _Result:
        value = "remote"
        provenance = type("P", (), {"value": "inferred"})()

    _evaluate_scalar(
        evaluation,
        record_id="r1",
        parser="remote_type",
        annotation=_annotation(
            outcome="present_supported", expected_value="remote", expected_provenance="inferred"
        ),
        fn=lambda: _Result(),
    )
    metrics = evaluation.get_component_metrics("remote_type")
    assert metrics.supported_correctness.render() == "1/1"
    assert metrics.supported_abstention.render() == "0/1"
    assert metrics.confidently_wrong.render() == "0/1"
    assert metrics.provenance_correctness.render() == "1/1"


def test_present_supported_wrong_value_scores_confidently_wrong_one_of_one() -> None:
    evaluation = SplitEvaluation()

    class _Result:
        value = "hybrid"
        provenance = type("P", (), {"value": "inferred"})()

    _evaluate_scalar(
        evaluation,
        record_id="r1",
        parser="remote_type",
        annotation=_annotation(
            outcome="present_supported", expected_value="remote", expected_provenance="inferred"
        ),
        fn=lambda: _Result(),
    )
    metrics = evaluation.get_component_metrics("remote_type")
    assert metrics.confidently_wrong.render() == "1/1"
    assert metrics.supported_correctness.render() == "0/1"
    assert metrics.supported_abstention.render() == "0/1"


def test_composite_exception_counted_as_exactly_one_parser_invocation() -> None:
    """A single raising `classify_experience()` call must register as
    exactly one runtime failure for `experience` as a whole -- never one
    per component (2, here)."""
    evaluation = SplitEvaluation()

    def _raise() -> Any:
        raise RuntimeError("boom")

    annotations = {"minimum": _annotation(), "maximum": _annotation()}
    _evaluate_composite(
        evaluation,
        record_id="r1",
        parser="experience",
        annotations=annotations,
        fn=_raise,
        components=("minimum", "maximum"),
    )
    assert evaluation.get_runtime_failure("experience").render() == "1/1"
    # No component-level metrics are recorded at all for a raised invocation.
    assert "experience.minimum" not in evaluation.components
    assert "experience.maximum" not in evaluation.components


def test_composite_non_raising_call_scores_each_component_independently() -> None:
    evaluation = SplitEvaluation()

    class _Component:
        def __init__(self, value: Any, provenance: str) -> None:
            self.value = value
            self.provenance = type("P", (), {"value": provenance})()

    class _Result:
        minimum = _Component(3, "inferred")
        maximum = _Component(None, "unavailable")

    annotations = {
        "minimum": _annotation(
            outcome="present_supported", expected_value=3, expected_provenance="inferred"
        ),
        "maximum": _annotation(outcome="absent"),
    }
    _evaluate_composite(
        evaluation,
        record_id="r1",
        parser="experience",
        annotations=annotations,
        fn=lambda: _Result(),
        components=("minimum", "maximum"),
    )
    assert evaluation.get_runtime_failure("experience").render() == "0/1"
    assert (
        evaluation.get_component_metrics("experience.minimum").supported_correctness.render()
        == "1/1"
    )
    assert (
        evaluation.get_component_metrics("experience.maximum").false_positive_absent.render()
        == "0/1"
    )


class _FakeSkillMatch:
    def __init__(self, canonical_id: str) -> None:
        self.canonical_id = canonical_id


def test_skills_record_with_all_four_outcomes_simultaneously(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.evaluate_phase3_corpus as module

    # python: present_supported and correctly returned.
    # golang: present_unsupported_form but incorrectly returned anyway (false positive).
    # javascript: ambiguous, correctly NOT returned.
    # (a 4th, "absent", is folded into golang/javascript's own non-supported category coverage.)
    monkeypatch.setattr(
        module,
        "classify_skills",
        lambda title, description, *, taxonomy: [
            _FakeSkillMatch("python"),
            _FakeSkillMatch("golang"),
        ],
    )
    evaluation = SplitEvaluation()
    skills_annotations = {
        "python": _skill_annotation(outcome="present_supported"),
        "golang": _skill_annotation(outcome="present_unsupported_form"),
        "javascript": _skill_annotation(outcome="ambiguous"),
    }
    _evaluate_skills(
        evaluation,
        record_id="r1",
        skills_annotations=skills_annotations,
        title="t",
        description="d",
        taxonomy=None,
    )
    metrics = evaluation.skills
    assert metrics.recall.render() == "1/1"  # python, the only present_supported id, was returned
    assert (
        metrics.false_positive_unsupported_form.render() == "1/1"
    )  # golang returned despite unsupported
    assert metrics.false_positive_ambiguous.render() == "0/1"  # javascript correctly not returned
    # precision: of the 2 returned ids, only python (1) is genuinely present_supported.
    assert metrics.precision.render() == "1/2"
    assert metrics.false_positive_outside_frozen_set.render() == "1/2"
    assert evaluation.get_runtime_failure("skills").render() == "0/1"


def test_skills_runtime_failure_counted_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.evaluate_phase3_corpus as module

    def _raise(title: Any, description: Any, *, taxonomy: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "classify_skills", _raise)
    evaluation = SplitEvaluation()
    _evaluate_skills(
        evaluation,
        record_id="r1",
        skills_annotations=_all_skills({"python": _skill_annotation(outcome="present_supported")}),
        title="t",
        description="d",
        taxonomy=None,
    )
    assert evaluation.get_runtime_failure("skills").render() == "1/1"
    assert evaluation.skills.recall.render() == "N/A"


# ---------------------------------------------------------------------------
# End-to-end: real classifiers, dev/holdout/combined split reporting
# ---------------------------------------------------------------------------
def test_evaluate_corpus_reports_dev_holdout_and_combined_separately(tmp_path: Path) -> None:
    from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, load_taxonomy

    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    real_ids = taxonomy.canonical_ids()

    records = _minimal_corpus()
    records[0]["fields"]["title"] = "Software Engineer (Remote)"
    records[0]["annotations"]["remote_type"] = _annotation(
        outcome="present_supported", expected_value="remote", expected_provenance="inferred"
    )
    for record in records:
        record["annotations"]["skills"] = {cid: _skill_annotation() for cid in real_ids}
    path = _write_corpus(tmp_path, records)
    loaded = load_corpus(path, known_canonical_ids=real_ids)
    evaluations = evaluate_corpus(loaded, taxonomy=taxonomy)

    assert set(evaluations) == {"dev", "holdout", "combined"}
    dev_metrics = evaluations["dev"].components["remote_type"]
    assert dev_metrics.supported_correctness.render() == "1/1"
    holdout_metrics = evaluations["holdout"].components["remote_type"]
    assert holdout_metrics.supported_correctness.render() == "N/A"  # holdout record is "absent"
    combined_metrics = evaluations["combined"].components["remote_type"]
    assert combined_metrics.supported_correctness.render() == "1/1"
