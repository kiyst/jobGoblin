from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.evaluate_phase3_corpus import (
    CorpusValidationError,
    MetricCounter,
    ParserComponentMetrics,
    SkillsMetrics,
    _evaluate_skills,
    _score_component,
    evaluate_corpus,
    load_corpus,
)

_KNOWN_IDS = frozenset({"python", "golang"})


def _base_annotation(**overrides: Any) -> dict[str, Any]:
    base = {
        "outcome": "present_supported",
        "expected_value": "remote",
        "expected_provenance": "inferred",
        "annotator_role": "user",
        "rubric_version": "v1",
        "annotation_provenance": "manual read against rubric v1",
        "frozen": True,
        "frozen_at": "2026-09-20T00:00:00Z",
    }
    base.update(overrides)
    return base


def _base_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "id": "rec-1",
        "provenance": {
            "provider": "greenhouse",
            "employer": "Acme",
            "template_family": "unknown",
            "capture": {
                "board_token": "acme",
                "job_id": "1",
                "accessed_at": "2026-09-20T00:00:00Z",
                "capture_method": "fetch_greenhouse_evaluation_postings.py",
            },
            "sanitization_lineage": "manually reviewed",
            "origin": "sanitized_capture",
        },
        "split": "dev",
        "fields": {
            "title": "Remote Software Engineer",
            "description": None,
            "location_raw": None,
            "compensation_text": None,
        },
        "annotations": {"remote_type": _base_annotation()},
    }
    record.update(overrides)
    return record


def _write_corpus(tmp_path: Path, records: list[dict[str, Any]]) -> Path:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(records), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Loader -- fail-closed rules
# ---------------------------------------------------------------------------
def test_load_corpus_accepts_a_well_formed_record(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, [_base_record()])
    records = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert len(records) == 1
    assert records[0].id == "rec-1"


def test_load_corpus_rejects_non_list_top_level(tmp_path: Path) -> None:
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    with pytest.raises(CorpusValidationError, match="JSON array"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unknown_top_level_record_field(tmp_path: Path) -> None:
    record = _base_record()
    record["unexpected"] = "field"
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="unrecognized field"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_missing_required_record_field(tmp_path: Path) -> None:
    record = _base_record()
    del record["split"]
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="missing required field"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_duplicate_record_id(tmp_path: Path) -> None:
    path = _write_corpus(tmp_path, [_base_record(), _base_record()])
    with pytest.raises(CorpusValidationError, match="duplicate record id"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unknown_annotation_parser_name(tmp_path: Path) -> None:
    record = _base_record(annotations={"not_a_real_parser": _base_annotation()})
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="unrecognized annotation key"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unknown_composite_component_name(tmp_path: Path) -> None:
    record = _base_record(annotations={"experience": {"not_a_real_component": _base_annotation()}})
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="unrecognized component"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_invalid_outcome(tmp_path: Path) -> None:
    record = _base_record(
        annotations={"remote_type": _base_annotation(outcome="not_a_real_outcome")}
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="outcome"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_non_null_value_with_unavailable_provenance(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "remote_type": _base_annotation(
                expected_value="remote", expected_provenance="unavailable"
            )
        }
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="null iff"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_null_value_with_non_unavailable_provenance(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "remote_type": _base_annotation(
                outcome="absent", expected_value=None, expected_provenance="inferred"
            )
        }
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="null iff"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_non_supported_outcome_with_non_null_expected_value(
    tmp_path: Path,
) -> None:
    record = _base_record(
        annotations={"remote_type": _base_annotation(outcome="ambiguous", expected_value="remote")}
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="requires a null expected_value"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_frozen_false(tmp_path: Path) -> None:
    record = _base_record(annotations={"remote_type": _base_annotation(frozen=False)})
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="frozen must be exactly true"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_frozen_as_truthy_non_bool(tmp_path: Path) -> None:
    record = _base_record(annotations={"remote_type": _base_annotation(frozen=1)})
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="frozen must be exactly true"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unresolved_disagreement(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "remote_type": _base_annotation(
                disagreement={
                    "second_annotation": {"expected_value": "hybrid"},
                    "adjudication": None,
                }
            )
        }
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="unresolved"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_resolved_disagreement(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "remote_type": _base_annotation(
                disagreement={
                    "second_annotation": {"expected_value": "hybrid"},
                    "adjudication": {"resolved_by": "user", "final_value": "remote"},
                }
            )
        }
    )
    path = _write_corpus(tmp_path, [record])
    records = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert len(records) == 1


def test_load_corpus_rejects_adjudication_inconsistent_with_expected_value(tmp_path: Path) -> None:
    """The adjudication is supposed to be authoritative -- recording one
    without the annotation's own scored `expected_value` actually
    reflecting it must fail closed, not silently score against a stale
    or unresolved value."""
    record = _base_record(
        annotations={
            "remote_type": _base_annotation(
                expected_value="remote",
                disagreement={
                    "second_annotation": {"expected_value": "hybrid"},
                    "adjudication": {"resolved_by": "user", "final_value": "onsite"},
                },
            )
        }
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="does not match the resolved"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_adjudication_without_final_value(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "remote_type": _base_annotation(
                disagreement={
                    "second_annotation": {"expected_value": "hybrid"},
                    "adjudication": {"resolved_by": "user"},
                }
            )
        }
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="final_value"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_non_scalar_expected_value(tmp_path: Path) -> None:
    record = _base_record(
        annotations={"remote_type": _base_annotation(expected_value={"not": "a scalar"})}
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="must be null, a string, or an int"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_negative_compensation_text_source_span(tmp_path: Path) -> None:
    record = _base_record()
    description = "Salary: $100k per year"
    record["fields"]["description"] = description
    record["fields"]["compensation_text"] = "$100k"
    record["fields"]["compensation_text_source_span"] = [-6, -1]
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="out of bounds"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_inverted_compensation_text_source_span(tmp_path: Path) -> None:
    record = _base_record()
    description = "Salary: $100k per year"
    record["fields"]["description"] = description
    record["fields"]["compensation_text"] = ""
    record["fields"]["compensation_text_source_span"] = [5, 2]
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="out of bounds"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_invalid_split(tmp_path: Path) -> None:
    record = _base_record(split="production")
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="split must be one of"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_invalid_provenance_origin(tmp_path: Path) -> None:
    record = _base_record()
    record["provenance"]["origin"] = "made_up"
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="origin must be one of"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_compensation_text_without_source_span(tmp_path: Path) -> None:
    record = _base_record()
    record["fields"]["compensation_text"] = "$100k"
    record["fields"]["description"] = "Salary: $100k per year"
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="source_span is required"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_compensation_text_mismatched_span(tmp_path: Path) -> None:
    record = _base_record()
    record["fields"]["description"] = "Salary: $100k per year"
    record["fields"]["compensation_text"] = "$100k"
    record["fields"]["compensation_text_source_span"] = [0, 5]  # "Salar" != "$100k"
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="exact substring"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_compensation_text_matching_span(tmp_path: Path) -> None:
    record = _base_record()
    description = "Salary: $100k per year"
    record["fields"]["description"] = description
    start = description.index("$100k")
    record["fields"]["compensation_text"] = "$100k"
    record["fields"]["compensation_text_source_span"] = [start, start + len("$100k")]
    path = _write_corpus(tmp_path, [record])
    records = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert records[0].fields["compensation_text"] == "$100k"


def test_load_corpus_rejects_source_span_present_when_compensation_text_null(
    tmp_path: Path,
) -> None:
    record = _base_record()
    record["fields"]["compensation_text_source_span"] = [0, 5]
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="must be absent"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_rejects_unknown_skill_canonical_id(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "skills": {
                "outcome": "present_supported",
                "expected_canonical_ids": ["not_a_real_skill"],
                "annotator_role": "user",
                "rubric_version": "v1",
                "annotation_provenance": "manual",
                "frozen": True,
                "frozen_at": "2026-09-20T00:00:00Z",
            }
        }
    )
    path = _write_corpus(tmp_path, [record])
    with pytest.raises(CorpusValidationError, match="unknown id"):
        load_corpus(path, known_canonical_ids=_KNOWN_IDS)


def test_load_corpus_accepts_known_skill_canonical_id(tmp_path: Path) -> None:
    record = _base_record(
        annotations={
            "skills": {
                "outcome": "present_supported",
                "expected_canonical_ids": ["python"],
                "annotator_role": "user",
                "rubric_version": "v1",
                "annotation_provenance": "manual",
                "frozen": True,
                "frozen_at": "2026-09-20T00:00:00Z",
            }
        }
    )
    path = _write_corpus(tmp_path, [record])
    records = load_corpus(path, known_canonical_ids=_KNOWN_IDS)
    assert records[0].annotations["skills"]["expected_canonical_ids"] == ["python"]


# ---------------------------------------------------------------------------
# Metrics -- numerator/denominator, N/A on zero denominator
# ---------------------------------------------------------------------------
def test_metric_counter_renders_na_on_zero_denominator() -> None:
    assert MetricCounter().render() == "N/A"


def test_metric_counter_renders_fraction() -> None:
    counter = MetricCounter()
    counter.add(hit=True)
    counter.add(hit=False)
    assert counter.render() == "1/2"


def test_score_component_supported_correctness() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        actual_value="remote",
        actual_provenance="inferred",
        raised=False,
    )
    assert metrics.supported_correctness.render() == "1/1"
    assert metrics.supported_abstention.render() == "0/1"
    # confidently_wrong shares supported_correctness's denominator (both
    # apply whenever the parser returned non-null on a present_supported
    # case) -- here the value matched, so it's "0 wrong", not N/A.
    assert metrics.confidently_wrong.render() == "0/1"
    assert metrics.provenance_correctness.render() == "1/1"


def test_score_component_supported_abstention() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        actual_value=None,
        actual_provenance="unavailable",
        raised=False,
    )
    assert metrics.supported_abstention.render() == "1/1"
    assert metrics.supported_correctness.render() == "N/A"


def test_score_component_confidently_wrong() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        actual_value="hybrid",
        actual_provenance="inferred",
        raised=False,
    )
    assert metrics.confidently_wrong.render() == "1/1"
    assert metrics.supported_correctness.render() == "0/1"


def test_score_component_false_positive_on_absent_never_pollutes_provenance_correctness() -> None:
    """A false positive on an `absent` case is counted only by its own
    dedicated metric -- it must never also register in
    `provenance_correctness`, which is scoped to `present_supported`
    only (each event class has its own denominator, never merged)."""
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="absent",
        expected_value=None,
        expected_provenance="unavailable",
        actual_value="remote",
        actual_provenance="inferred",
        raised=False,
    )
    assert metrics.false_positive_absent.render() == "1/1"
    assert metrics.provenance_correctness.render() == "N/A"


def test_score_component_false_positive_on_absent() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="absent",
        expected_value=None,
        expected_provenance="unavailable",
        actual_value="remote",
        actual_provenance="inferred",
        raised=False,
    )
    assert metrics.false_positive_absent.render() == "1/1"


def test_score_component_false_positive_on_unsupported_form() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="present_unsupported_form",
        expected_value=None,
        expected_provenance="unavailable",
        actual_value="remote",
        actual_provenance="inferred",
        raised=False,
    )
    assert metrics.false_positive_unsupported_form.render() == "1/1"


def test_score_component_false_positive_on_ambiguous() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="ambiguous",
        expected_value=None,
        expected_provenance="unavailable",
        actual_value="remote",
        actual_provenance="inferred",
        raised=False,
    )
    assert metrics.false_positive_ambiguous.render() == "1/1"


def test_score_component_no_false_positive_when_absent_and_parser_abstains() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="absent",
        expected_value=None,
        expected_provenance="unavailable",
        actual_value=None,
        actual_provenance="unavailable",
        raised=False,
    )
    assert metrics.false_positive_absent.render() == "0/1"


def test_score_component_runtime_failure_counted_and_skips_other_metrics() -> None:
    metrics = ParserComponentMetrics.empty()
    _score_component(
        metrics,
        outcome="present_supported",
        expected_value="remote",
        expected_provenance="inferred",
        actual_value=None,
        actual_provenance=None,
        raised=True,
    )
    assert metrics.runtime_failure.render() == "1/1"
    assert metrics.supported_correctness.render() == "N/A"
    assert metrics.opportunity_matrix["present_supported"] == 1


# ---------------------------------------------------------------------------
# Skills -- set-based precision/recall, outside-frozen-set is a false positive
# ---------------------------------------------------------------------------
class _FakeSkillMatch:
    def __init__(self, canonical_id: str) -> None:
        self.canonical_id = canonical_id


def test_evaluate_skills_scores_precision_recall_and_outside_set_false_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scripts.evaluate_phase3_corpus as module

    monkeypatch.setattr(
        module,
        "classify_skills",
        lambda title, description, *, taxonomy: [
            _FakeSkillMatch("python"),
            _FakeSkillMatch("rlang"),
        ],
    )
    metrics = SkillsMetrics.empty()
    annotation = {
        "outcome": "present_supported",
        "expected_canonical_ids": ["python", "golang"],
        "annotator_role": "user",
        "rubric_version": "v1",
        "annotation_provenance": "manual",
        "frozen": True,
        "frozen_at": "t",
    }
    _evaluate_skills(metrics, annotation, "title", "description", taxonomy=None)

    # returned = {python, rlang}; expected = {python, golang}
    assert metrics.precision.render() == "1/2"  # python hits, rlang doesn't
    assert metrics.recall.render() == "1/2"  # python found, golang missed
    assert metrics.false_positive_outside_frozen_set.render() == "1/2"  # rlang is outside


def test_evaluate_skills_runtime_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.evaluate_phase3_corpus as module

    def _raise(title: Any, description: Any, *, taxonomy: Any) -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(module, "classify_skills", _raise)
    metrics = SkillsMetrics.empty()
    annotation = {
        "outcome": "present_supported",
        "expected_canonical_ids": ["python"],
        "annotator_role": "user",
        "rubric_version": "v1",
        "annotation_provenance": "manual",
        "frozen": True,
        "frozen_at": "t",
    }
    _evaluate_skills(metrics, annotation, "title", "description", taxonomy=None)
    assert metrics.runtime_failure.render() == "1/1"
    assert metrics.precision.render() == "N/A"


# ---------------------------------------------------------------------------
# End-to-end smoke test: real classifiers, one simple controlled record
# ---------------------------------------------------------------------------
def test_evaluate_corpus_end_to_end_against_real_classifiers(tmp_path: Path) -> None:
    from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, load_taxonomy

    # "Remote Software Engineer" (undelimited leading "Remote") is a
    # documented, deliberate false negative in remote.py's own title
    # structural rule -- use a title that structurally qualifies instead
    # (a parenthetical marker).
    record = _base_record(
        fields={**_base_record()["fields"], "title": "Software Engineer (Remote)"}
    )
    record["annotations"] = {
        "remote_type": _base_annotation(
            outcome="present_supported", expected_value="remote", expected_provenance="inferred"
        )
    }
    path = _write_corpus(tmp_path, [record])
    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    records = load_corpus(path, known_canonical_ids=taxonomy.canonical_ids())
    evaluation = evaluate_corpus(records, taxonomy=taxonomy)

    metrics = evaluation["components"]["remote_type"]
    assert metrics.supported_correctness.render() == "1/1"
    assert metrics.runtime_failure.render() == "0/1"
