"""Fail-closed loader and minimal evaluator for the realistic Phase 3
evaluation corpus (Class H realistic-corpus evaluation slice).

Pure, read-only, no I/O beyond reading the one given corpus path and
calling the seven already-merged Phase 3 classifiers in-process. No
database, no network, no CI policy, no pass threshold, no dashboard, no
new verification framework -- a report only.

**Record schema** (one JSON array at the top level):

    {
      "id": "...",
      "provenance": {
        "provider": "...", "employer": "...", "template_family": "...",
        "capture": {"board_token": "...", "job_id": "...",
                     "accessed_at": "...", "capture_method": "..."},
        "sanitization_lineage": "...", "origin": "sanitized_capture"
      },
      "split": "dev" | "holdout",
      "fields": {
        "title": str | null, "description": str | null,
        "location_raw": str | null, "compensation_text": str | null,
        "compensation_text_source_span": [start, end]  # required iff compensation_text is non-null
      },
      "annotations": {
        "<parser or parser.component>": {
          "outcome": "present_supported" | "present_unsupported_form" | "absent" | "ambiguous",
          "expected_value": ..., "expected_provenance": "...",
          "annotator_role": "...", "rubric_version": "...",
          "annotation_provenance": "...", "frozen": true, "frozen_at": "...",
          "disagreement": {"second_annotation": {...}, "adjudication": {...} | null}  # optional
        }
      }
    }

**Fail-closed loader rules** (never a warning, never a silently-skipped
record): unknown top-level record fields; an `annotations` key that is
not one of the seven known parsers (`remote_type`, `employment_type`,
`seniority`, `experience`, `salary`, `location`, `skills`) or, for a
composite parser, not one of its own known component names; a malformed
`expected_value`/`expected_provenance` (provenance must be one of the six
canonical `Provenance` strings; `expected_value is None` iff
`expected_provenance == "unavailable"`, mirroring `NormalizationResult`'s
own invariant); `frozen != true` (exactly the boolean `True`, not merely
truthy); an unresolved `disagreement` (`adjudication` missing or `None`);
an invalid `split` (not `"dev"`/`"holdout"`) or malformed `provenance`
block; a non-null `compensation_text` whose `fields.description[start:
end]` does not equal it exactly at the recorded
`compensation_text_source_span`.

**Metrics**: every metric reports numerator and denominator explicitly; a
zero denominator prints `N/A`, never `0%`. Runtime failures are counted
per parser invocation. Scalar/composite-component correctness is counted
per annotated output component. Skill precision/recall is set-based --
any returned skill outside the frozen `expected_canonical_ids` scores as
a false positive unconditionally; correcting a genuine annotation
omission is only ever a new corpus revision, never an in-place edit.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.normalization.employment import classify_employment_type  # noqa: E402
from app.normalization.experience import classify_experience  # noqa: E402
from app.normalization.location import classify_location  # noqa: E402
from app.normalization.remote import classify_remote_type  # noqa: E402
from app.normalization.salary import classify_salary  # noqa: E402
from app.normalization.seniority import classify_seniority  # noqa: E402
from app.normalization.skills import classify_skills  # noqa: E402
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, load_taxonomy  # noqa: E402
from app.normalization.types import Provenance  # noqa: E402

DEFAULT_CORPUS_PATH = (
    BACKEND_DIR / "tests" / "fixtures" / "evaluation" / "phase3_realistic_corpus.json"
)

_VALID_OUTCOMES = frozenset(
    {"present_supported", "present_unsupported_form", "absent", "ambiguous"}
)
_VALID_PROVENANCE_VALUES = frozenset(p.value for p in Provenance)
_VALID_SPLITS = frozenset({"dev", "holdout"})
_VALID_ORIGINS = frozenset({"sanitized_capture"})

_SCALAR_PARSERS = frozenset({"remote_type", "employment_type", "seniority"})
_COMPOSITE_PARSER_COMPONENTS: dict[str, frozenset[str]] = {
    "experience": frozenset({"minimum", "maximum"}),
    "salary": frozenset({"minimum", "maximum", "currency", "period"}),
    "location": frozenset({"city", "state", "country", "postal_code"}),
}
_KNOWN_ANNOTATION_KEYS = (
    _SCALAR_PARSERS | frozenset(_COMPOSITE_PARSER_COMPONENTS) | frozenset({"skills"})
)

_REQUIRED_RECORD_FIELDS = frozenset({"id", "provenance", "split", "fields", "annotations"})
_REQUIRED_PROVENANCE_FIELDS = frozenset(
    {"provider", "employer", "template_family", "capture", "sanitization_lineage", "origin"}
)
_REQUIRED_CAPTURE_FIELDS = frozenset({"board_token", "job_id", "accessed_at", "capture_method"})
_REQUIRED_FIELDS_FIELDS = frozenset({"title", "description", "location_raw", "compensation_text"})
_OPTIONAL_FIELDS_FIELDS = frozenset({"compensation_text_source_span"})
_REQUIRED_ANNOTATION_FIELDS = frozenset(
    {
        "outcome",
        "expected_value",
        "expected_provenance",
        "annotator_role",
        "rubric_version",
        "annotation_provenance",
        "frozen",
        "frozen_at",
    }
)
_OPTIONAL_ANNOTATION_FIELDS = frozenset({"disagreement"})
_REQUIRED_SKILLS_ANNOTATION_FIELDS = frozenset(
    {
        "outcome",
        "expected_canonical_ids",
        "annotator_role",
        "rubric_version",
        "annotation_provenance",
        "frozen",
        "frozen_at",
    }
)


class CorpusValidationError(Exception):
    """The corpus file is malformed, or violates a closed-schema,
    freeze, or consistency invariant -- always fails closed, never a
    warning or a silently-skipped/coerced record."""


def _require_exact_keys(
    obj: Any, allowed: frozenset[str], *, required: frozenset[str], context: str
) -> None:
    if not isinstance(obj, dict):
        raise CorpusValidationError(f"{context} must be a JSON object")
    unknown = set(obj) - allowed
    if unknown:
        raise CorpusValidationError(f"{context} declares unrecognized field(s): {sorted(unknown)}")
    missing = required - set(obj)
    if missing:
        raise CorpusValidationError(f"{context} is missing required field(s): {sorted(missing)}")


def _validate_frozen_annotation_common(
    annotation: dict[str, Any], *, context: str, scored_field: str
) -> None:
    """`scored_field` is whichever key this annotation's evaluator
    actually scores against (`"expected_value"` for a scalar/component
    annotation, `"expected_canonical_ids"` for skills) -- required so
    the disagreement/adjudication consistency check below can verify
    the *right* field, generically, for either caller."""
    if annotation.get("frozen") is not True:
        raise CorpusValidationError(
            f"{context}.frozen must be exactly true, got {annotation.get('frozen')!r}"
        )
    if not isinstance(annotation.get("frozen_at"), str) or not annotation["frozen_at"]:
        raise CorpusValidationError(f"{context}.frozen_at must be a non-empty string")
    for key in ("annotator_role", "rubric_version", "annotation_provenance"):
        if not isinstance(annotation.get(key), str) or not annotation[key]:
            raise CorpusValidationError(f"{context}.{key} must be a non-empty string")
    disagreement = annotation.get("disagreement")
    if disagreement is not None:
        if not isinstance(disagreement, dict) or "second_annotation" not in disagreement:
            raise CorpusValidationError(f"{context}.disagreement is malformed")
        adjudication = disagreement.get("adjudication")
        if adjudication is None:
            raise CorpusValidationError(
                f"{context}.disagreement is unresolved (adjudication is missing/null)"
            )
        if not isinstance(adjudication, dict) or "final_value" not in adjudication:
            raise CorpusValidationError(
                f"{context}.disagreement.adjudication must be an object with 'final_value'"
            )
        # The adjudication is the authoritative resolution -- recording
        # one without the annotation's own scored field actually
        # reflecting it would let evaluation silently score against a
        # stale or unresolved value instead.
        if annotation[scored_field] != adjudication["final_value"]:
            raise CorpusValidationError(
                f"{context}.{scored_field} does not match the resolved "
                f"disagreement.adjudication.final_value"
            )


def _validate_scalar_annotation(annotation: dict[str, Any], *, context: str) -> None:
    _require_exact_keys(
        annotation,
        _REQUIRED_ANNOTATION_FIELDS | _OPTIONAL_ANNOTATION_FIELDS,
        required=_REQUIRED_ANNOTATION_FIELDS,
        context=context,
    )
    outcome = annotation["outcome"]
    if outcome not in _VALID_OUTCOMES:
        raise CorpusValidationError(
            f"{context}.outcome must be one of {sorted(_VALID_OUTCOMES)}, got {outcome!r}"
        )
    expected_value = annotation["expected_value"]
    expected_provenance = annotation["expected_provenance"]
    if expected_value is not None and not isinstance(expected_value, str | int):
        raise CorpusValidationError(
            f"{context}.expected_value must be null, a string, or an int, "
            f"got {type(expected_value).__name__}"
        )
    if expected_provenance not in _VALID_PROVENANCE_VALUES:
        raise CorpusValidationError(
            f"{context}.expected_provenance must be one of {sorted(_VALID_PROVENANCE_VALUES)}, "
            f"got {expected_provenance!r}"
        )
    if (expected_value is None) != (expected_provenance == Provenance.UNAVAILABLE.value):
        raise CorpusValidationError(
            f"{context}: expected_value must be null iff expected_provenance is 'unavailable'"
        )
    if outcome != "present_supported" and expected_value is not None:
        raise CorpusValidationError(
            f"{context}: outcome {outcome!r} requires a null expected_value (the parser is "
            "expected to abstain)"
        )
    _validate_frozen_annotation_common(annotation, context=context, scored_field="expected_value")


def _validate_skills_annotation(
    annotation: dict[str, Any], *, context: str, known_canonical_ids: frozenset[str]
) -> None:
    _require_exact_keys(
        annotation,
        _REQUIRED_SKILLS_ANNOTATION_FIELDS | _OPTIONAL_ANNOTATION_FIELDS,
        required=_REQUIRED_SKILLS_ANNOTATION_FIELDS,
        context=context,
    )
    outcome = annotation["outcome"]
    if outcome not in _VALID_OUTCOMES:
        raise CorpusValidationError(
            f"{context}.outcome must be one of {sorted(_VALID_OUTCOMES)}, got {outcome!r}"
        )
    expected_ids = annotation["expected_canonical_ids"]
    if not isinstance(expected_ids, list) or not all(isinstance(x, str) for x in expected_ids):
        raise CorpusValidationError(f"{context}.expected_canonical_ids must be a list of strings")
    unknown_ids = set(expected_ids) - known_canonical_ids
    if unknown_ids:
        raise CorpusValidationError(
            f"{context}.expected_canonical_ids has unknown id(s): {sorted(unknown_ids)}"
        )
    _validate_frozen_annotation_common(
        annotation, context=context, scored_field="expected_canonical_ids"
    )


def _validate_annotations(
    annotations: Any, *, record_id: str, known_canonical_ids: frozenset[str]
) -> None:
    if not isinstance(annotations, dict):
        raise CorpusValidationError(f"record {record_id}: 'annotations' must be a JSON object")
    unknown_keys = set(annotations) - _KNOWN_ANNOTATION_KEYS
    if unknown_keys:
        raise CorpusValidationError(
            f"record {record_id}: unrecognized annotation key(s): {sorted(unknown_keys)}"
        )

    for key, value in annotations.items():
        if key in _SCALAR_PARSERS:
            _validate_scalar_annotation(value, context=f"record {record_id}.annotations.{key}")
        elif key == "skills":
            _validate_skills_annotation(
                value,
                context=f"record {record_id}.annotations.skills",
                known_canonical_ids=known_canonical_ids,
            )
        else:  # a composite parser
            if not isinstance(value, dict):
                raise CorpusValidationError(
                    f"record {record_id}.annotations.{key} must be a JSON object"
                )
            allowed_components = _COMPOSITE_PARSER_COMPONENTS[key]
            unknown_components = set(value) - allowed_components
            if unknown_components:
                raise CorpusValidationError(
                    f"record {record_id}.annotations.{key} has unrecognized component(s): "
                    f"{sorted(unknown_components)}"
                )
            for component, component_annotation in value.items():
                _validate_scalar_annotation(
                    component_annotation,
                    context=f"record {record_id}.annotations.{key}.{component}",
                )


def _validate_fields(fields: Any, *, record_id: str) -> None:
    _require_exact_keys(
        fields,
        _REQUIRED_FIELDS_FIELDS | _OPTIONAL_FIELDS_FIELDS,
        required=_REQUIRED_FIELDS_FIELDS,
        context=f"record {record_id}.fields",
    )
    for key in ("title", "description", "location_raw", "compensation_text"):
        if fields[key] is not None and not isinstance(fields[key], str):
            raise CorpusValidationError(f"record {record_id}.fields.{key} must be a string or null")

    compensation_text = fields["compensation_text"]
    has_span = "compensation_text_source_span" in fields
    if compensation_text is None:
        if has_span:
            raise CorpusValidationError(
                f"record {record_id}.fields.compensation_text_source_span must be absent when "
                "compensation_text is null"
            )
        return

    if not has_span:
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span is required when "
            "compensation_text is non-null"
        )
    span = fields["compensation_text_source_span"]
    if (
        not isinstance(span, list)
        or len(span) != 2
        or not all(isinstance(x, int) and not isinstance(x, bool) for x in span)
    ):
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span must be a [start, end] "
            "pair of ints"
        )
    start, end = span
    description = fields["description"]
    if not isinstance(description, str):
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span requires a non-null "
            "description"
        )
    # Reject negative indices and an inverted range explicitly -- Python's
    # permissive slicing would otherwise silently accept e.g. a negative
    # start (wrapping from the end) or start > end (an empty slice) as
    # long as the sliced text happened to match, which is not "an exact
    # substring at the recorded offsets" in any meaningful sense.
    if not (0 <= start <= end <= len(description)):
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span {span} is out of "
            f"bounds for a description of length {len(description)}"
        )
    if description[start:end] != compensation_text:
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text is not an exact substring of "
            "description at the recorded offsets"
        )


def _validate_provenance(provenance: Any, *, record_id: str) -> None:
    _require_exact_keys(
        provenance,
        _REQUIRED_PROVENANCE_FIELDS,
        required=_REQUIRED_PROVENANCE_FIELDS,
        context=f"record {record_id}.provenance",
    )
    if provenance["origin"] not in _VALID_ORIGINS:
        raise CorpusValidationError(
            f"record {record_id}.provenance.origin must be one of {sorted(_VALID_ORIGINS)}"
        )
    for key in ("provider", "employer", "template_family", "sanitization_lineage"):
        if not isinstance(provenance[key], str) or not provenance[key]:
            raise CorpusValidationError(
                f"record {record_id}.provenance.{key} must be a non-empty string"
            )
    _require_exact_keys(
        provenance["capture"],
        _REQUIRED_CAPTURE_FIELDS,
        required=_REQUIRED_CAPTURE_FIELDS,
        context=f"record {record_id}.provenance.capture",
    )


@dataclass(frozen=True)
class CorpusRecord:
    id: str
    provenance: dict[str, Any]
    split: str
    fields: dict[str, Any]
    annotations: dict[str, Any]


def load_corpus(path: Path, *, known_canonical_ids: frozenset[str]) -> list[CorpusRecord]:
    """Loads and validates the corpus at `path`. Fails closed on any
    malformed content -- never silently skips or coerces a bad record."""
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CorpusValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise CorpusValidationError(f"{path} must contain a JSON array at the top level")

    records: list[CorpusRecord] = []
    seen_ids: set[str] = set()
    for index, raw_record in enumerate(raw):
        context = f"entries[{index}]"
        if not isinstance(raw_record, dict):
            raise CorpusValidationError(f"{context} must be a JSON object")
        unknown = set(raw_record) - _REQUIRED_RECORD_FIELDS
        if unknown:
            raise CorpusValidationError(
                f"{context} declares unrecognized field(s): {sorted(unknown)}"
            )
        missing = _REQUIRED_RECORD_FIELDS - set(raw_record)
        if missing:
            raise CorpusValidationError(
                f"{context} is missing required field(s): {sorted(missing)}"
            )

        record_id = raw_record["id"]
        if not isinstance(record_id, str) or not record_id:
            raise CorpusValidationError(f"{context}.id must be a non-empty string")
        if record_id in seen_ids:
            raise CorpusValidationError(f"duplicate record id {record_id!r}")
        seen_ids.add(record_id)

        split_value = raw_record["split"]
        if split_value not in _VALID_SPLITS:
            raise CorpusValidationError(
                f"record {record_id}.split must be one of {sorted(_VALID_SPLITS)}, "
                f"got {split_value!r}"
            )
        _validate_provenance(raw_record["provenance"], record_id=record_id)
        _validate_fields(raw_record["fields"], record_id=record_id)
        _validate_annotations(
            raw_record["annotations"], record_id=record_id, known_canonical_ids=known_canonical_ids
        )

        records.append(
            CorpusRecord(
                id=record_id,
                provenance=raw_record["provenance"],
                split=raw_record["split"],
                fields=raw_record["fields"],
                annotations=raw_record["annotations"],
            )
        )
    return records


# ---------------------------------------------------------------------------
# Evaluator -- minimal, descriptive only, no thresholds.
# ---------------------------------------------------------------------------
@dataclass
class MetricCounter:
    numerator: int = 0
    denominator: int = 0

    def add(self, *, hit: bool) -> None:
        self.denominator += 1
        if hit:
            self.numerator += 1

    def render(self) -> str:
        if self.denominator == 0:
            return "N/A"
        return f"{self.numerator}/{self.denominator}"


@dataclass
class ParserComponentMetrics:
    opportunity_matrix: dict[str, int]
    supported_correctness: MetricCounter
    supported_abstention: MetricCounter
    confidently_wrong: MetricCounter
    false_positive_absent: MetricCounter
    false_positive_unsupported_form: MetricCounter
    false_positive_ambiguous: MetricCounter
    provenance_correctness: MetricCounter
    runtime_failure: MetricCounter

    @staticmethod
    def empty() -> ParserComponentMetrics:
        return ParserComponentMetrics(
            opportunity_matrix={outcome: 0 for outcome in sorted(_VALID_OUTCOMES)},
            supported_correctness=MetricCounter(),
            supported_abstention=MetricCounter(),
            confidently_wrong=MetricCounter(),
            false_positive_absent=MetricCounter(),
            false_positive_unsupported_form=MetricCounter(),
            false_positive_ambiguous=MetricCounter(),
            provenance_correctness=MetricCounter(),
            runtime_failure=MetricCounter(),
        )


def _score_component(
    metrics: ParserComponentMetrics,
    *,
    outcome: str,
    expected_value: Any,
    expected_provenance: str | None,
    actual_value: Any,
    actual_provenance: str | None,
    raised: bool,
) -> None:
    metrics.opportunity_matrix[outcome] += 1
    metrics.runtime_failure.add(hit=raised)
    if raised:
        return

    is_present = actual_value is not None
    if outcome == "present_supported":
        metrics.supported_abstention.add(hit=not is_present)
        if is_present:
            metrics.confidently_wrong.add(hit=actual_value != expected_value)
            metrics.supported_correctness.add(hit=actual_value == expected_value)
            # Gated on present_supported only -- a false positive on
            # absent/present_unsupported_form/ambiguous is already
            # counted by its own dedicated metric above; pooling it into
            # provenance_correctness too would silently re-merge those
            # separate event classes through this metric instead, which
            # this ADR's own "never merged" rule forbids.
            metrics.provenance_correctness.add(hit=actual_provenance == expected_provenance)
    elif outcome == "absent":
        metrics.false_positive_absent.add(hit=is_present)
    elif outcome == "present_unsupported_form":
        metrics.false_positive_unsupported_form.add(hit=is_present)
    elif outcome == "ambiguous":
        metrics.false_positive_ambiguous.add(hit=is_present)


@dataclass
class SkillsMetrics:
    opportunity_matrix: dict[str, int]
    precision: MetricCounter
    recall: MetricCounter
    false_positive_outside_frozen_set: MetricCounter
    runtime_failure: MetricCounter

    @staticmethod
    def empty() -> SkillsMetrics:
        return SkillsMetrics(
            opportunity_matrix={outcome: 0 for outcome in sorted(_VALID_OUTCOMES)},
            precision=MetricCounter(),
            recall=MetricCounter(),
            false_positive_outside_frozen_set=MetricCounter(),
            runtime_failure=MetricCounter(),
        )


def evaluate_corpus(records: list[CorpusRecord], *, taxonomy: Any) -> dict[str, Any]:
    """Runs the seven merged classifiers against every record's
    applicable, frozen annotations and returns the opportunity matrix
    plus every metric, each with an explicit numerator/denominator.
    Never gates, never asserts a threshold -- a report only."""
    component_metrics: dict[str, ParserComponentMetrics] = {}
    skills_metrics = SkillsMetrics.empty()

    def get_metrics(key: str) -> ParserComponentMetrics:
        return component_metrics.setdefault(key, ParserComponentMetrics.empty())

    for record in records:
        title = record.fields["title"]
        description = record.fields["description"]
        annotations = record.annotations

        if "remote_type" in annotations:
            _evaluate_scalar(
                get_metrics("remote_type"),
                annotations["remote_type"],
                lambda t=title, d=description: classify_remote_type(t, d),
            )
        if "employment_type" in annotations:
            _evaluate_scalar(
                get_metrics("employment_type"),
                annotations["employment_type"],
                lambda t=title, d=description: classify_employment_type(t, d),
            )
        if "seniority" in annotations:
            _evaluate_scalar(
                get_metrics("seniority"),
                annotations["seniority"],
                lambda t=title, d=description: classify_seniority(t, d),
            )
        if "experience" in annotations:
            result = _safe_call(lambda t=title, d=description: classify_experience(t, d))
            for component in ("minimum", "maximum"):
                if component in annotations["experience"]:
                    _evaluate_component(
                        get_metrics(f"experience.{component}"),
                        annotations["experience"][component],
                        result,
                        component,
                    )
        if "salary" in annotations:
            compensation_text = record.fields["compensation_text"]
            result = _safe_call(lambda c=compensation_text: classify_salary(c))
            for component in ("minimum", "maximum", "currency", "period"):
                if component in annotations["salary"]:
                    _evaluate_component(
                        get_metrics(f"salary.{component}"),
                        annotations["salary"][component],
                        result,
                        component,
                    )
        if "location" in annotations:
            location_raw = record.fields["location_raw"]
            result = _safe_call(lambda loc=location_raw: classify_location(loc))
            for component in ("city", "state", "country", "postal_code"):
                if component in annotations["location"]:
                    _evaluate_component(
                        get_metrics(f"location.{component}"),
                        annotations["location"][component],
                        result,
                        component,
                    )
        if "skills" in annotations:
            _evaluate_skills(skills_metrics, annotations["skills"], title, description, taxonomy)

    return {
        "components": component_metrics,
        "skills": skills_metrics,
    }


class _CallFailed:
    __slots__ = ("exception",)

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception


def _safe_call(fn: Any) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 -- evaluator must never crash on one bad record
        return _CallFailed(exc)


def _evaluate_scalar(metrics: ParserComponentMetrics, annotation: dict[str, Any], fn: Any) -> None:
    result = _safe_call(fn)
    raised = isinstance(result, _CallFailed)
    actual_value = None if raised else result.value
    actual_provenance = None if raised else result.provenance.value
    _score_component(
        metrics,
        outcome=annotation["outcome"],
        expected_value=annotation["expected_value"],
        expected_provenance=annotation["expected_provenance"],
        actual_value=actual_value,
        actual_provenance=actual_provenance,
        raised=raised,
    )


def _evaluate_component(
    metrics: ParserComponentMetrics, annotation: dict[str, Any], result: Any, component: str
) -> None:
    raised = isinstance(result, _CallFailed)
    actual_value = None
    actual_provenance = None
    if not raised:
        component_result = getattr(result, component)
        actual_value = component_result.value
        actual_provenance = component_result.provenance.value
    _score_component(
        metrics,
        outcome=annotation["outcome"],
        expected_value=annotation["expected_value"],
        expected_provenance=annotation["expected_provenance"],
        actual_value=actual_value,
        actual_provenance=actual_provenance,
        raised=raised,
    )


def _evaluate_skills(
    metrics: SkillsMetrics,
    annotation: dict[str, Any],
    title: str | None,
    description: str | None,
    taxonomy: Any,
) -> None:
    metrics.opportunity_matrix[annotation["outcome"]] += 1
    result = _safe_call(lambda: classify_skills(title, description, taxonomy=taxonomy))
    raised = isinstance(result, _CallFailed)
    metrics.runtime_failure.add(hit=raised)
    if raised:
        return

    expected_ids = set(annotation["expected_canonical_ids"])
    returned_ids = {match.canonical_id for match in result}

    for expected_id in expected_ids:
        metrics.recall.add(hit=expected_id in returned_ids)
    for returned_id in returned_ids:
        metrics.precision.add(hit=returned_id in expected_ids)
        metrics.false_positive_outside_frozen_set.add(hit=returned_id not in expected_ids)


def render_report(evaluation: dict[str, Any]) -> str:
    lines: list[str] = []
    for key in sorted(evaluation["components"]):
        metrics = evaluation["components"][key]
        lines.append(f"== {key} ==")
        lines.append(f"  opportunity matrix: {metrics.opportunity_matrix}")
        lines.append(f"  supported_correctness: {metrics.supported_correctness.render()}")
        lines.append(f"  supported_abstention: {metrics.supported_abstention.render()}")
        lines.append(f"  confidently_wrong: {metrics.confidently_wrong.render()}")
        lines.append(f"  false_positive_absent: {metrics.false_positive_absent.render()}")
        lines.append(
            f"  false_positive_unsupported_form: {metrics.false_positive_unsupported_form.render()}"
        )
        lines.append(f"  false_positive_ambiguous: {metrics.false_positive_ambiguous.render()}")
        lines.append(f"  provenance_correctness: {metrics.provenance_correctness.render()}")
        lines.append(f"  runtime_failure: {metrics.runtime_failure.render()}")

    skills = evaluation["skills"]
    lines.append("== skills ==")
    lines.append(f"  opportunity matrix: {skills.opportunity_matrix}")
    lines.append(f"  precision: {skills.precision.render()}")
    lines.append(f"  recall: {skills.recall.render()}")
    lines.append(
        f"  false_positive_outside_frozen_set: {skills.false_positive_outside_frozen_set.render()}"
    )
    lines.append(f"  runtime_failure: {skills.runtime_failure.render()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    corpus_path = DEFAULT_CORPUS_PATH if not argv else Path(argv[0])
    taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    known_canonical_ids = taxonomy.canonical_ids()
    try:
        records = load_corpus(corpus_path, known_canonical_ids=known_canonical_ids)
    except CorpusValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    evaluation = evaluate_corpus(records, taxonomy=taxonomy)
    print(render_report(evaluation))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
