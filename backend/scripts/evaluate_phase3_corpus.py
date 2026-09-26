"""Fail-closed loader and minimal evaluator for the realistic Phase 3
evaluation corpus (Class H realistic-corpus evaluation slice).

Pure, read-only, no I/O beyond reading the one given corpus path and
calling the seven already-merged Phase 3 classifiers in-process. No
database, no network, no CI policy, no pass threshold, no dashboard, no
new verification framework -- a report only.

**Record schema** (one JSON array at the top level, duplicate JSON keys
rejected, at least one record required):

    {
      "id": "...",
      "provenance": {
        "provider": "...", "employer": "...", "template_family": "...",
        "capture": {"board_token": "...", "job_id": "...",
                     "accessed_at": "<aware ISO8601>", "capture_method": "..."},
        "sanitization_lineage": "...", "origin": "sanitized_capture",
        "manual_review": {"reviewer": "...", "reviewed_at": "<aware ISO8601>", "notes": "..."}
      },
      "split": "dev" | "holdout",
      "fields": {
        "title": str | null, "description": str | null,
        "location_raw": str | null, "compensation_text": str | null,
        "compensation_text_source_span": [start, end]  # required iff compensation_text is non-null
      },
      "annotations": {
        "remote_type": {...}, "employment_type": {...}, "seniority": {...},
        "experience": {"minimum": {...}, "maximum": {...}},
        "salary": {"minimum": {...}, "maximum": {...}, "currency": {...}, "period": {...}},
        "location": {"city": {...}, "state": {...}, "country": {...}, "postal_code": {...}},
        "skills": {"<every known canonical id>": {...per-id annotation...}}
      }
    }

Every scalar/component annotation:

    {
      "outcome": "present_supported" | "present_unsupported_form" | "absent" | "ambiguous",
      "expected_value": ..., "expected_provenance": "...",
      "annotator_role": "...", "rubric_version": "...",
      "annotation_provenance": "...", "frozen": true, "frozen_at": "<aware ISO8601>",
      "disagreement": {  # optional
        "second_annotation": {<same shape as above, minus disagreement>},
        "adjudication": {"final_outcome": ..., "final_value": ..., "final_provenance": ...,
                          "adjudicated_by": "...", "adjudicated_at": "<aware ISO8601>"}
      }
    }

A per-skill-id annotation is the same shape, keyed on `"outcome"` alone
(no `expected_value`/`expected_provenance` -- the outcome itself already
says whether `classify_skills` is expected to return that id); its
`adjudication` resolves `"final_outcome"` only.

A scalar/composite-component scored label's internal consistency --
`outcome` in the known set, `expected_value` valid for its specific
parser/component, `expected_provenance` a known `Provenance` tag,
`expected_value is None` iff `expected_provenance == "unavailable"`,
and, bidirectionally, `outcome == "present_supported"` iff
`expected_value` is non-null -- is validated by one single function,
`_validate_scored_label`, shared identically by the primary annotation,
`disagreement.second_annotation`, and `disagreement.adjudication`'s
resolved `final_outcome`/`final_value`/`final_provenance` triple, so
none of the three can drift into different rules. A
`present_supported` label is never null/unavailable, and every other
outcome always is -- `present_supported`/null/unavailable is rejected
exactly as forcefully as `absent`/non-null. An `adjudication` resolves
that *complete* label -- never a single field in isolation -- and the
primary annotation's own scored label must equal it exactly. A
`disagreement` block must also reflect an actual difference between the
primary and second annotation's scored label; one declared over two
identical labels fails closed.

**Annotations are exhaustive, on every record**: all three scalar
parsers, every composite component, and *every* known taxonomy canonical
id under `skills` must be present -- never a subset, never omitted.

**Fail-closed loader rules** (never a warning, never a silently-skipped
record): duplicate JSON keys anywhere; a non-list top level; an empty
corpus; unknown top-level record fields; a missing scalar parser,
composite component, or taxonomy id under `annotations`; a malformed
`expected_value`/`expected_provenance` (provenance one of the six
canonical `Provenance` strings; value type/closed-set matched to the
specific parser/component -- e.g. `remote_type` only accepts `"remote"`/
`"hybrid"`/`"onsite"`, never an arbitrary string, and a `bool` is never
accepted where an `int` is expected, since `bool` is an `int` subtype in
Python; `expected_value is None` iff `expected_provenance ==
"unavailable"`; `outcome == "present_supported"` iff `expected_value` is
non-null, so `present_supported`/null/unavailable and any other
outcome paired with a real value both fail closed); `frozen != true`; a
malformed or naive `frozen_at`/`accessed_at`/`reviewed_at`/
`adjudicated_at` timestamp; an unresolved or inconsistent
`disagreement`/`adjudication` (missing metadata, an incomplete or
invalid resolved label, the primary annotation's scored label not
matching that resolved label exactly, or a declared disagreement with
no actual difference between the two annotations); an invalid
`split`/`provenance.origin`; a malformed or absent `manual_review` block;
an invalid `capture.board_token`/`capture.job_id`; a non-null
`compensation_text` whose `fields.description[start:end]` does not equal
it exactly (bounds-checked, never a negative index or an inverted range).
After loading: an empty `dev` or `holdout` split, or an employer
appearing in both splits, both fail closed.

**Metrics**: every metric reports numerator and denominator explicitly;
a zero denominator prints `N/A`, never `0%`. Every `present_supported`
case with a completed (non-raising) invocation contributes to
`supported_correctness`, `supported_abstention`, and `confidently_wrong`
together, sharing one denominator -- an abstention is "incorrect" but
never also "confidently wrong" (those are mutually exclusive outcomes of
the same event). Runtime failure is counted exactly once per parser
*invocation*, never once per composite component. Skill precision/
recall and the three false-positive categories are derived from the
same frozen, exhaustive per-canonical-id representation. Deterministic
mismatch details are reported per record/parser/component, keyed by
id -- never posting text. Dev, holdout, combined, and per-employer
metrics are reported separately (keyed `"employer:<name>"`). Every
`template_family` in the currently-supported corpus is the fixed
literal `"unknown"`, so a per-template breakdown would only ever
duplicate the combined result -- the report states this explicitly
instead of computing one.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
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
    {
        "provider",
        "employer",
        "template_family",
        "capture",
        "sanitization_lineage",
        "origin",
        "manual_review",
    }
)
_REQUIRED_CAPTURE_FIELDS = frozenset({"board_token", "job_id", "accessed_at", "capture_method"})
_REQUIRED_MANUAL_REVIEW_FIELDS = frozenset({"reviewer", "reviewed_at", "notes"})
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
_REQUIRED_SKILL_ID_ANNOTATION_FIELDS = frozenset(
    {
        "outcome",
        "annotator_role",
        "rubric_version",
        "annotation_provenance",
        "frozen",
        "frozen_at",
    }
)
_OPTIONAL_ANNOTATION_FIELDS = frozenset({"disagreement"})
# A scalar/composite-component adjudication resolves the *complete*
# scored label (outcome, value, and provenance) -- never `final_value`
# alone, which let an adjudication that only ever resolved a null value
# silently "match" an `absent`/unavailable primary annotation even when
# the actual disagreement (e.g. absent vs. present_supported) was never
# resolved at all. A skill-id adjudication resolves `final_outcome` only,
# since a skill-id annotation itself carries no value/provenance.
_REQUIRED_SCALAR_ADJUDICATION_FIELDS = frozenset(
    {"final_outcome", "final_value", "final_provenance", "adjudicated_by", "adjudicated_at"}
)
_REQUIRED_SKILL_ADJUDICATION_FIELDS = frozenset(
    {"final_outcome", "adjudicated_by", "adjudicated_at"}
)

# Mirrors canary_greenhouse.py's own board-token grammar, declared
# independently (this module never imports network-adjacent code).
_BOARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_JOB_ID_RE = re.compile(r"^[0-9]{1,32}$")


def _is_bool_free_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _is_valid_aware_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


# One validator per parser/component -- closed-set for the three scalar
# parsers (never an arbitrary string), bool-excluded int for numeric
# components, non-empty str for free-text components. Never a bare
# `isinstance(x, str | int)`, which would silently accept a `bool` (an
# `int` subtype in Python) or a value from the wrong parser's vocabulary.
_EXPECTED_VALUE_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "remote_type": lambda v: v in {"remote", "hybrid", "onsite"},
    "employment_type": lambda v: v in {"full_time", "part_time", "seasonal", "internship"},
    "seniority": lambda v: v
    in {"entry_level", "mid_level", "senior", "staff", "principal", "director"},
    "experience.minimum": _is_bool_free_int,
    "experience.maximum": _is_bool_free_int,
    "salary.minimum": _is_bool_free_int,
    "salary.maximum": _is_bool_free_int,
    "salary.currency": _is_non_empty_str,
    "salary.period": _is_non_empty_str,
    "location.city": _is_non_empty_str,
    "location.state": _is_non_empty_str,
    "location.country": _is_non_empty_str,
    "location.postal_code": _is_non_empty_str,
}


class CorpusValidationError(Exception):
    """The corpus file is malformed, or violates a closed-schema,
    freeze, exhaustiveness, or consistency invariant -- always fails
    closed, never a warning or a silently-skipped/coerced record."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """`json.loads`'s `object_pairs_hook` -- by default, a duplicate JSON
    key is silently last-write-wins; this rejects it outright, at every
    nesting level, mirroring `taxonomy.py`'s own `_StrictYamlLoader`
    precedent for the equivalent YAML defect."""
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise CorpusValidationError(f"duplicate JSON key {key!r}")
        seen[key] = value
    return seen


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


def _validate_annotation_metadata(annotation: dict[str, Any], *, context: str) -> None:
    """`frozen`/`frozen_at`/`annotator_role`/`rubric_version`/
    `annotation_provenance` -- required identically by every annotation
    flavor (primary, `second_annotation`, and a per-skill-id entry)."""
    if annotation.get("frozen") is not True:
        raise CorpusValidationError(
            f"{context}.frozen must be exactly true, got {annotation.get('frozen')!r}"
        )
    if not _is_valid_aware_timestamp(annotation.get("frozen_at")):
        raise CorpusValidationError(
            f"{context}.frozen_at must be a timezone-aware ISO8601 timestamp string"
        )
    for key in ("annotator_role", "rubric_version", "annotation_provenance"):
        if not _is_non_empty_str(annotation.get(key)):
            raise CorpusValidationError(f"{context}.{key} must be a non-empty string")


def _validate_disagreement_envelope(
    annotation: dict[str, Any], *, context: str
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Shared shape/presence checks for a `disagreement` block, common to
    both the scalar/composite and skill-id flavors: exactly
    `second_annotation` and `adjudication`, `second_annotation` an
    object, `adjudication` present (not an unresolved `null`). Returns
    `(second_annotation, adjudication)` for the caller's flavor-specific
    validation, or `None` if there is no `disagreement` at all."""
    disagreement = annotation.get("disagreement")
    if disagreement is None:
        return None
    if not isinstance(disagreement, dict) or set(disagreement) != {
        "second_annotation",
        "adjudication",
    }:
        raise CorpusValidationError(
            f"{context}.disagreement must declare exactly 'second_annotation' and 'adjudication'"
        )
    second = disagreement["second_annotation"]
    if not isinstance(second, dict):
        raise CorpusValidationError(f"{context}.disagreement.second_annotation must be an object")
    adjudication = disagreement["adjudication"]
    if adjudication is None:
        raise CorpusValidationError(
            f"{context}.disagreement is unresolved (adjudication is missing/null)"
        )
    return second, adjudication


def _validate_adjudication_metadata(adjudication: dict[str, Any], *, context: str) -> None:
    """`adjudicated_by`/`adjudicated_at` -- required identically by both
    adjudication flavors."""
    if not _is_non_empty_str(adjudication["adjudicated_by"]):
        raise CorpusValidationError(f"{context}.adjudicated_by must be a non-empty string")
    if not _is_valid_aware_timestamp(adjudication["adjudicated_at"]):
        raise CorpusValidationError(
            f"{context}.adjudicated_at must be a timezone-aware ISO8601 timestamp string"
        )


def _validate_scored_label(
    *,
    outcome: Any,
    expected_value: Any,
    expected_provenance: Any,
    value_key: str,
    context: str,
    outcome_field: str = "outcome",
    value_field: str = "expected_value",
    provenance_field: str = "expected_provenance",
) -> None:
    """The single source of truth for a scalar/composite-component scored
    label's internal consistency -- shared identically by a primary
    annotation, a `disagreement.second_annotation`, and a
    `disagreement.adjudication`'s resolved `final_outcome`/`final_value`/
    `final_provenance` triple (via the `*_field` overrides, so error
    messages still name the actual JSON keys involved), so none of the
    three can ever drift into different rules. Validates, in order: the
    outcome is a known outcome; the value is valid for `value_key`'s
    specific parser/component vocabulary; the provenance is a known
    `Provenance` tag; the value is `None` iff the provenance is
    `'unavailable'`; and, bidirectionally, the outcome is
    `'present_supported'` iff the value is non-null (equivalently, iff
    the provenance is not `'unavailable'`) -- a `present_supported`
    label is never null/unavailable, and every other outcome always is."""
    if outcome not in _VALID_OUTCOMES:
        raise CorpusValidationError(
            f"{context}.{outcome_field} must be one of {sorted(_VALID_OUTCOMES)}, got {outcome!r}"
        )
    validator = _EXPECTED_VALUE_VALIDATORS[value_key]
    if expected_value is not None and not validator(expected_value):
        raise CorpusValidationError(f"{context}.{value_field} is not valid for {value_key!r}")
    if expected_provenance not in _VALID_PROVENANCE_VALUES:
        raise CorpusValidationError(
            f"{context}.{provenance_field} must be one of {sorted(_VALID_PROVENANCE_VALUES)}, "
            f"got {expected_provenance!r}"
        )
    if (expected_value is None) != (expected_provenance == Provenance.UNAVAILABLE.value):
        raise CorpusValidationError(
            f"{context}: {value_field} must be null iff {provenance_field} is 'unavailable'"
        )
    if (outcome == "present_supported") != (expected_value is not None):
        raise CorpusValidationError(
            f"{context}: {outcome_field} must be 'present_supported' iff {value_field} is "
            f"non-null and {provenance_field} is not 'unavailable'"
        )


def _validate_scalar_disagreement(
    annotation: dict[str, Any], *, context: str, value_key: str
) -> None:
    """Validates a scalar/composite-component `disagreement`: fully
    validates `second_annotation`'s own shape via the same
    flavor-specific validator used for the primary annotation (never
    just its scored field, and never a nested `disagreement`); validates
    `adjudication`'s complete resolved label -- `final_outcome`/
    `final_value`/`final_provenance` -- through the exact same
    `_validate_scored_label` used for the primary and second annotation,
    so none of the three can drift into different rules; and requires
    the primary annotation's own `(outcome, expected_value,
    expected_provenance)` triple to equal that resolved label exactly,
    never `final_value` alone (which would let an adjudication resolving
    only a coincidentally-matching null value silently pass despite
    never actually resolving the outcome/provenance disagreement). Also
    requires the primary and second annotation's scored labels to
    actually differ -- a `disagreement` block declared over two
    identical labels is not a real disagreement."""
    envelope = _validate_disagreement_envelope(annotation, context=context)
    if envelope is None:
        return
    second, adjudication = envelope

    _validate_scalar_annotation_shape(
        second,
        context=f"{context}.disagreement.second_annotation",
        value_key=value_key,
        allow_disagreement=False,
    )

    adjudication_context = f"{context}.disagreement.adjudication"
    if (
        not isinstance(adjudication, dict)
        or set(adjudication) != _REQUIRED_SCALAR_ADJUDICATION_FIELDS
    ):
        raise CorpusValidationError(
            f"{adjudication_context} must declare exactly "
            f"{sorted(_REQUIRED_SCALAR_ADJUDICATION_FIELDS)}"
        )
    _validate_adjudication_metadata(adjudication, context=adjudication_context)
    _validate_scored_label(
        outcome=adjudication["final_outcome"],
        expected_value=adjudication["final_value"],
        expected_provenance=adjudication["final_provenance"],
        value_key=value_key,
        context=adjudication_context,
        outcome_field="final_outcome",
        value_field="final_value",
        provenance_field="final_provenance",
    )

    primary_label = (
        annotation["outcome"],
        annotation["expected_value"],
        annotation["expected_provenance"],
    )
    final_label = (
        adjudication["final_outcome"],
        adjudication["final_value"],
        adjudication["final_provenance"],
    )
    if primary_label != final_label:
        raise CorpusValidationError(
            f"{context}'s (outcome, expected_value, expected_provenance) does not match the "
            "resolved disagreement.adjudication's (final_outcome, final_value, final_provenance)"
        )

    second_label = (second["outcome"], second["expected_value"], second["expected_provenance"])
    if primary_label == second_label:
        raise CorpusValidationError(
            f"{context}.disagreement declares no actual difference between the primary "
            "annotation's and second_annotation's scored label"
        )


def _validate_skill_id_disagreement(annotation: dict[str, Any], *, context: str) -> None:
    """The per-skill-id counterpart of `_validate_scalar_disagreement` --
    a skill-id annotation is scored on `outcome` alone, so its
    adjudication resolves `final_outcome` only."""
    envelope = _validate_disagreement_envelope(annotation, context=context)
    if envelope is None:
        return
    second, adjudication = envelope

    _validate_skill_id_annotation_shape(
        second, context=f"{context}.disagreement.second_annotation", allow_disagreement=False
    )

    adjudication_context = f"{context}.disagreement.adjudication"
    if (
        not isinstance(adjudication, dict)
        or set(adjudication) != _REQUIRED_SKILL_ADJUDICATION_FIELDS
    ):
        raise CorpusValidationError(
            f"{adjudication_context} must declare exactly "
            f"{sorted(_REQUIRED_SKILL_ADJUDICATION_FIELDS)}"
        )
    _validate_adjudication_metadata(adjudication, context=adjudication_context)

    final_outcome = adjudication["final_outcome"]
    if final_outcome not in _VALID_OUTCOMES:
        raise CorpusValidationError(
            f"{adjudication_context}.final_outcome must be one of {sorted(_VALID_OUTCOMES)}, "
            f"got {final_outcome!r}"
        )
    if annotation["outcome"] != final_outcome:
        raise CorpusValidationError(
            f"{context}.outcome does not match the resolved disagreement.adjudication."
            "final_outcome"
        )
    if annotation["outcome"] == second["outcome"]:
        raise CorpusValidationError(
            f"{context}.disagreement declares no actual difference between the primary "
            "annotation's and second_annotation's outcome"
        )


def _validate_scalar_annotation_shape(
    annotation: dict[str, Any], *, context: str, value_key: str, allow_disagreement: bool
) -> None:
    """Validates one scalar/composite-component annotation's own shape --
    exact keys, the scored label (via `_validate_scored_label`), and
    shared metadata -- excluding disagreement recursion. Used for both
    the primary annotation (`allow_disagreement=True`) and a
    `disagreement.second_annotation` (`allow_disagreement=False`, which
    also forbids a nested `disagreement` key), so both are held to
    exactly the same rules."""
    allowed = _REQUIRED_ANNOTATION_FIELDS | (
        _OPTIONAL_ANNOTATION_FIELDS if allow_disagreement else frozenset()
    )
    _require_exact_keys(annotation, allowed, required=_REQUIRED_ANNOTATION_FIELDS, context=context)
    _validate_scored_label(
        outcome=annotation["outcome"],
        expected_value=annotation["expected_value"],
        expected_provenance=annotation["expected_provenance"],
        value_key=value_key,
        context=context,
    )
    _validate_annotation_metadata(annotation, context=context)


def _validate_scalar_annotation(
    annotation: dict[str, Any], *, context: str, value_key: str
) -> None:
    _validate_scalar_annotation_shape(
        annotation, context=context, value_key=value_key, allow_disagreement=True
    )
    _validate_scalar_disagreement(annotation, context=context, value_key=value_key)


def _validate_skill_id_annotation_shape(
    annotation: dict[str, Any], *, context: str, allow_disagreement: bool
) -> None:
    """The per-skill-id counterpart of `_validate_scalar_annotation_shape`
    -- same allow_disagreement contract, no `expected_value`/
    `expected_provenance` (a skill-id annotation is scored on `outcome`
    alone)."""
    allowed = _REQUIRED_SKILL_ID_ANNOTATION_FIELDS | (
        _OPTIONAL_ANNOTATION_FIELDS if allow_disagreement else frozenset()
    )
    _require_exact_keys(
        annotation, allowed, required=_REQUIRED_SKILL_ID_ANNOTATION_FIELDS, context=context
    )
    outcome = annotation["outcome"]
    if outcome not in _VALID_OUTCOMES:
        raise CorpusValidationError(
            f"{context}.outcome must be one of {sorted(_VALID_OUTCOMES)}, got {outcome!r}"
        )
    _validate_annotation_metadata(annotation, context=context)


def _validate_skill_id_annotation(annotation: dict[str, Any], *, context: str) -> None:
    _validate_skill_id_annotation_shape(annotation, context=context, allow_disagreement=True)
    _validate_skill_id_disagreement(annotation, context=context)


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
    missing_keys = _KNOWN_ANNOTATION_KEYS - set(annotations)
    if missing_keys:
        raise CorpusValidationError(
            f"record {record_id}: missing required annotation key(s) -- annotations are "
            f"exhaustive, never a subset: {sorted(missing_keys)}"
        )

    for parser in _SCALAR_PARSERS:
        _validate_scalar_annotation(
            annotations[parser],
            context=f"record {record_id}.annotations.{parser}",
            value_key=parser,
        )

    for parser, allowed_components in _COMPOSITE_PARSER_COMPONENTS.items():
        value = annotations[parser]
        if not isinstance(value, dict):
            raise CorpusValidationError(
                f"record {record_id}.annotations.{parser} must be a JSON object"
            )
        unknown_components = set(value) - allowed_components
        if unknown_components:
            raise CorpusValidationError(
                f"record {record_id}.annotations.{parser} has unrecognized component(s): "
                f"{sorted(unknown_components)}"
            )
        missing_components = allowed_components - set(value)
        if missing_components:
            raise CorpusValidationError(
                f"record {record_id}.annotations.{parser} is missing required component(s) -- "
                f"components are exhaustive, never a subset: {sorted(missing_components)}"
            )
        for component, component_annotation in value.items():
            _validate_scalar_annotation(
                component_annotation,
                context=f"record {record_id}.annotations.{parser}.{component}",
                value_key=f"{parser}.{component}",
            )

    skills_value = annotations["skills"]
    if not isinstance(skills_value, dict):
        raise CorpusValidationError(f"record {record_id}.annotations.skills must be a JSON object")
    unknown_ids = set(skills_value) - known_canonical_ids
    if unknown_ids:
        raise CorpusValidationError(
            f"record {record_id}.annotations.skills has unknown id(s): {sorted(unknown_ids)}"
        )
    missing_ids = known_canonical_ids - set(skills_value)
    if missing_ids:
        raise CorpusValidationError(
            f"record {record_id}.annotations.skills is missing required canonical id(s) -- "
            f"exhaustive over the whole taxonomy, never a subset: {sorted(missing_ids)}"
        )
    for canonical_id, id_annotation in skills_value.items():
        _validate_skill_id_annotation(
            id_annotation, context=f"record {record_id}.annotations.skills.{canonical_id}"
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
    if not isinstance(span, list) or len(span) != 2 or not all(_is_bool_free_int(x) for x in span):
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span must be a [start, end] "
            "pair of ints"
        )
    start, end = span
    description = fields["description"]
    if not isinstance(description, str):
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span requires a "
            "non-null description"
        )
    if not (0 <= start <= end <= len(description)):
        raise CorpusValidationError(
            f"record {record_id}.fields.compensation_text_source_span {span} is out of bounds "
            f"for a description of length {len(description)}"
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
        if not _is_non_empty_str(provenance[key]):
            raise CorpusValidationError(
                f"record {record_id}.provenance.{key} must be a non-empty string"
            )

    capture = provenance["capture"]
    _require_exact_keys(
        capture,
        _REQUIRED_CAPTURE_FIELDS,
        required=_REQUIRED_CAPTURE_FIELDS,
        context=f"record {record_id}.provenance.capture",
    )
    board_token = capture["board_token"]
    if not isinstance(board_token, str) or not _BOARD_TOKEN_RE.fullmatch(board_token):
        raise CorpusValidationError(
            f"record {record_id}.provenance.capture.board_token is not a conservative ASCII slug"
        )
    job_id = capture["job_id"]
    if not isinstance(job_id, str) or not _JOB_ID_RE.fullmatch(job_id):
        raise CorpusValidationError(
            f"record {record_id}.provenance.capture.job_id is not a conservative numeric id"
        )
    if not _is_valid_aware_timestamp(capture["accessed_at"]):
        raise CorpusValidationError(
            f"record {record_id}.provenance.capture.accessed_at must be a "
            "timezone-aware ISO8601 timestamp"
        )
    if not _is_non_empty_str(capture["capture_method"]):
        raise CorpusValidationError(
            f"record {record_id}.provenance.capture.capture_method must be a non-empty string"
        )

    manual_review = provenance["manual_review"]
    _require_exact_keys(
        manual_review,
        _REQUIRED_MANUAL_REVIEW_FIELDS,
        required=_REQUIRED_MANUAL_REVIEW_FIELDS,
        context=f"record {record_id}.provenance.manual_review",
    )
    if not _is_non_empty_str(manual_review["reviewer"]):
        raise CorpusValidationError(
            f"record {record_id}.provenance.manual_review.reviewer must be a non-empty string"
        )
    if not _is_valid_aware_timestamp(manual_review["reviewed_at"]):
        raise CorpusValidationError(
            f"record {record_id}.provenance.manual_review.reviewed_at must be a "
            "timezone-aware ISO8601 timestamp"
        )
    if not isinstance(manual_review["notes"], str):
        raise CorpusValidationError(
            f"record {record_id}.provenance.manual_review.notes must be a string"
        )


@dataclass(frozen=True)
class CorpusRecord:
    id: str
    provenance: dict[str, Any]
    split: str
    fields: dict[str, Any]
    annotations: dict[str, Any]


def _validate_partitioning(records: list[CorpusRecord]) -> None:
    dev_employers = {r.provenance["employer"] for r in records if r.split == "dev"}
    holdout_employers = {r.provenance["employer"] for r in records if r.split == "holdout"}
    if not dev_employers:
        raise CorpusValidationError("corpus has no 'dev' split records")
    if not holdout_employers:
        raise CorpusValidationError("corpus has no 'holdout' split records")
    overlap = dev_employers & holdout_employers
    if overlap:
        raise CorpusValidationError(
            f"employer(s) {sorted(overlap)} appear in both dev and holdout -- splits must be "
            "employer-disjoint"
        )


def load_corpus(path: Path, *, known_canonical_ids: frozenset[str]) -> list[CorpusRecord]:
    """Loads and validates the corpus at `path`. Fails closed on any
    malformed content -- never silently skips or coerces a bad record."""
    text = path.read_text(encoding="utf-8")
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise CorpusValidationError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, list):
        raise CorpusValidationError(f"{path} must contain a JSON array at the top level")
    if not raw:
        raise CorpusValidationError(f"{path} must contain at least one record")

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
        if not _is_non_empty_str(record_id):
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

    _validate_partitioning(records)
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
class MismatchDetail:
    record_id: str
    parser: str
    component: str | None
    category: str
    expected: Any
    actual: Any


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
        )


@dataclass
class SkillsMetrics:
    opportunity_matrix: dict[str, int]
    precision: MetricCounter
    recall: MetricCounter
    false_positive_absent: MetricCounter
    false_positive_unsupported_form: MetricCounter
    false_positive_ambiguous: MetricCounter
    false_positive_outside_frozen_set: MetricCounter

    @staticmethod
    def empty() -> SkillsMetrics:
        return SkillsMetrics(
            opportunity_matrix={outcome: 0 for outcome in sorted(_VALID_OUTCOMES)},
            precision=MetricCounter(),
            recall=MetricCounter(),
            false_positive_absent=MetricCounter(),
            false_positive_unsupported_form=MetricCounter(),
            false_positive_ambiguous=MetricCounter(),
            false_positive_outside_frozen_set=MetricCounter(),
        )


@dataclass
class SplitEvaluation:
    components: dict[str, ParserComponentMetrics] = field(default_factory=dict)
    skills: SkillsMetrics = field(default_factory=SkillsMetrics.empty)
    # Keyed by bare parser name (remote_type/employment_type/seniority/
    # experience/salary/location/skills) -- exactly one increment per
    # actual classify_*() invocation, never once per composite component.
    runtime_failure: dict[str, MetricCounter] = field(default_factory=dict)
    mismatches: list[MismatchDetail] = field(default_factory=list)

    def get_component_metrics(self, key: str) -> ParserComponentMetrics:
        return self.components.setdefault(key, ParserComponentMetrics.empty())

    def get_runtime_failure(self, parser: str) -> MetricCounter:
        return self.runtime_failure.setdefault(parser, MetricCounter())


class _CallFailed:
    __slots__ = ("exception",)

    def __init__(self, exception: BaseException) -> None:
        self.exception = exception


def _safe_call(fn: Any) -> Any:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 -- evaluator must never crash on one bad record
        return _CallFailed(exc)


def _score_component(
    evaluation: SplitEvaluation,
    *,
    record_id: str,
    parser: str,
    component: str | None,
    metrics_key: str,
    outcome: str,
    expected_value: Any,
    expected_provenance: str | None,
    actual_value: Any,
    actual_provenance: str | None,
) -> None:
    metrics = evaluation.get_component_metrics(metrics_key)
    metrics.opportunity_matrix[outcome] += 1
    is_present = actual_value is not None

    if outcome == "present_supported":
        # All three share one denominator -- every present_supported case
        # with a completed invocation contributes to each, mutually
        # exclusively: abstention (not present), confidently_wrong
        # (present and wrong), or correctness (present and right).
        metrics.supported_abstention.add(hit=not is_present)
        metrics.confidently_wrong.add(hit=is_present and actual_value != expected_value)
        metrics.supported_correctness.add(hit=is_present and actual_value == expected_value)
        if not is_present:
            evaluation.mismatches.append(
                MismatchDetail(
                    record_id, parser, component, "supported_abstention", expected_value, None
                )
            )
        elif actual_value != expected_value:
            evaluation.mismatches.append(
                MismatchDetail(
                    record_id, parser, component, "confidently_wrong", expected_value, actual_value
                )
            )
        if is_present:
            metrics.provenance_correctness.add(hit=actual_provenance == expected_provenance)
    elif outcome == "absent":
        metrics.false_positive_absent.add(hit=is_present)
        if is_present:
            evaluation.mismatches.append(
                MismatchDetail(
                    record_id, parser, component, "false_positive_absent", None, actual_value
                )
            )
    elif outcome == "present_unsupported_form":
        metrics.false_positive_unsupported_form.add(hit=is_present)
        if is_present:
            evaluation.mismatches.append(
                MismatchDetail(
                    record_id,
                    parser,
                    component,
                    "false_positive_unsupported_form",
                    None,
                    actual_value,
                )
            )
    elif outcome == "ambiguous":
        metrics.false_positive_ambiguous.add(hit=is_present)
        if is_present:
            evaluation.mismatches.append(
                MismatchDetail(
                    record_id, parser, component, "false_positive_ambiguous", None, actual_value
                )
            )


def _evaluate_scalar(
    evaluation: SplitEvaluation, *, record_id: str, parser: str, annotation: dict[str, Any], fn: Any
) -> None:
    result = _safe_call(fn)
    raised = isinstance(result, _CallFailed)
    evaluation.get_runtime_failure(parser).add(hit=raised)
    if raised:
        return
    _score_component(
        evaluation,
        record_id=record_id,
        parser=parser,
        component=None,
        metrics_key=parser,
        outcome=annotation["outcome"],
        expected_value=annotation["expected_value"],
        expected_provenance=annotation["expected_provenance"],
        actual_value=result.value,
        actual_provenance=result.provenance.value,
    )


def _evaluate_composite(
    evaluation: SplitEvaluation,
    *,
    record_id: str,
    parser: str,
    annotations: dict[str, Any],
    fn: Any,
    components: tuple[str, ...],
) -> None:
    result = _safe_call(fn)
    raised = isinstance(result, _CallFailed)
    # Exactly one increment for the whole invocation, regardless of how
    # many components this parser has.
    evaluation.get_runtime_failure(parser).add(hit=raised)
    for component in components:
        annotation = annotations[component]
        if raised:
            # No component-level score is recorded on a raised
            # invocation -- the failure is already captured once, at the
            # parser level, above.
            continue
        component_result = getattr(result, component)
        _score_component(
            evaluation,
            record_id=record_id,
            parser=parser,
            component=component,
            metrics_key=f"{parser}.{component}",
            outcome=annotation["outcome"],
            expected_value=annotation["expected_value"],
            expected_provenance=annotation["expected_provenance"],
            actual_value=component_result.value,
            actual_provenance=component_result.provenance.value,
        )


def _evaluate_skills(
    evaluation: SplitEvaluation,
    *,
    record_id: str,
    skills_annotations: dict[str, dict[str, Any]],
    title: str | None,
    description: str | None,
    taxonomy: Any,
) -> None:
    result = _safe_call(lambda t=title, d=description: classify_skills(t, d, taxonomy=taxonomy))
    raised = isinstance(result, _CallFailed)
    evaluation.get_runtime_failure("skills").add(hit=raised)
    if raised:
        return

    metrics = evaluation.skills
    returned_ids = {match.canonical_id for match in result}

    for canonical_id, annotation in skills_annotations.items():
        outcome = annotation["outcome"]
        metrics.opportunity_matrix[outcome] += 1
        is_returned = canonical_id in returned_ids
        if outcome == "present_supported":
            metrics.recall.add(hit=is_returned)
            if not is_returned:
                evaluation.mismatches.append(
                    MismatchDetail(
                        record_id, "skills", canonical_id, "recall_miss", canonical_id, None
                    )
                )
        elif outcome == "absent":
            metrics.false_positive_absent.add(hit=is_returned)
        elif outcome == "present_unsupported_form":
            metrics.false_positive_unsupported_form.add(hit=is_returned)
        elif outcome == "ambiguous":
            metrics.false_positive_ambiguous.add(hit=is_returned)
        if is_returned and outcome != "present_supported":
            evaluation.mismatches.append(
                MismatchDetail(
                    record_id,
                    "skills",
                    canonical_id,
                    f"false_positive_{outcome}",
                    None,
                    canonical_id,
                )
            )

    for canonical_id in returned_ids:
        annotation = skills_annotations[canonical_id]  # exhaustive schema guarantees presence
        supported = annotation["outcome"] == "present_supported"
        metrics.precision.add(hit=supported)
        metrics.false_positive_outside_frozen_set.add(hit=not supported)


def _evaluate_records(records: list[CorpusRecord], *, taxonomy: Any) -> SplitEvaluation:
    evaluation = SplitEvaluation()
    for record in records:
        title = record.fields["title"]
        description = record.fields["description"]
        annotations = record.annotations

        _evaluate_scalar(
            evaluation,
            record_id=record.id,
            parser="remote_type",
            annotation=annotations["remote_type"],
            fn=lambda t=title, d=description: classify_remote_type(t, d),
        )
        _evaluate_scalar(
            evaluation,
            record_id=record.id,
            parser="employment_type",
            annotation=annotations["employment_type"],
            fn=lambda t=title, d=description: classify_employment_type(t, d),
        )
        _evaluate_scalar(
            evaluation,
            record_id=record.id,
            parser="seniority",
            annotation=annotations["seniority"],
            fn=lambda t=title, d=description: classify_seniority(t, d),
        )
        _evaluate_composite(
            evaluation,
            record_id=record.id,
            parser="experience",
            annotations=annotations["experience"],
            fn=lambda t=title, d=description: classify_experience(t, d),
            components=("minimum", "maximum"),
        )
        compensation_text = record.fields["compensation_text"]
        _evaluate_composite(
            evaluation,
            record_id=record.id,
            parser="salary",
            annotations=annotations["salary"],
            fn=lambda c=compensation_text: classify_salary(c),
            components=("minimum", "maximum", "currency", "period"),
        )
        location_raw = record.fields["location_raw"]
        _evaluate_composite(
            evaluation,
            record_id=record.id,
            parser="location",
            annotations=annotations["location"],
            fn=lambda loc=location_raw: classify_location(loc),
            components=("city", "state", "country", "postal_code"),
        )
        _evaluate_skills(
            evaluation,
            record_id=record.id,
            skills_annotations=annotations["skills"],
            title=title,
            description=description,
            taxonomy=taxonomy,
        )
    return evaluation


def _all_template_families_unknown(records: list[CorpusRecord]) -> bool:
    return bool(records) and all(r.provenance["template_family"] == "unknown" for r in records)


def evaluate_corpus(records: list[CorpusRecord], *, taxonomy: Any) -> dict[str, SplitEvaluation]:
    """Returns `{"dev": ..., "holdout": ..., "combined": ..., "employer:<name>": ...}`
    -- one key per distinct `provenance.employer` value across the whole
    corpus (evaluated over all records for that employer, irrespective of
    split), plus the three fixed keys above. Each value is a fully
    independent `SplitEvaluation` over exactly that subset of records.
    Never gates, never asserts a threshold -- a report only.

    No per-`template_family` breakdown is computed: see
    `_all_template_families_unknown` and `render_report`'s explicit note
    below, which states rather than silently omits this."""
    dev_records = [r for r in records if r.split == "dev"]
    holdout_records = [r for r in records if r.split == "holdout"]
    evaluations: dict[str, SplitEvaluation] = {
        "dev": _evaluate_records(dev_records, taxonomy=taxonomy),
        "holdout": _evaluate_records(holdout_records, taxonomy=taxonomy),
        "combined": _evaluate_records(records, taxonomy=taxonomy),
    }
    employers = sorted({r.provenance["employer"] for r in records})
    for employer in employers:
        employer_records = [r for r in records if r.provenance["employer"] == employer]
        evaluations[f"employer:{employer}"] = _evaluate_records(employer_records, taxonomy=taxonomy)
    return evaluations


def render_report(
    evaluations: dict[str, SplitEvaluation], *, records: list[CorpusRecord] | None = None
) -> str:
    lines: list[str] = []
    ordered_split_names = [name for name in ("dev", "holdout", "combined") if name in evaluations]
    ordered_split_names += sorted(name for name in evaluations if name.startswith("employer:"))
    for split_name in ordered_split_names:
        evaluation = evaluations[split_name]
        lines.append(f"===== split: {split_name} =====")
        for key in sorted(evaluation.components):
            metrics = evaluation.components[key]
            lines.append(f"== {key} ==")
            lines.append(f"  opportunity matrix: {metrics.opportunity_matrix}")
            lines.append(f"  supported_correctness: {metrics.supported_correctness.render()}")
            lines.append(f"  supported_abstention: {metrics.supported_abstention.render()}")
            lines.append(f"  confidently_wrong: {metrics.confidently_wrong.render()}")
            lines.append(f"  false_positive_absent: {metrics.false_positive_absent.render()}")
            lines.append(
                f"  false_positive_unsupported_form: "
                f"{metrics.false_positive_unsupported_form.render()}"
            )
            lines.append(f"  false_positive_ambiguous: {metrics.false_positive_ambiguous.render()}")
            lines.append(f"  provenance_correctness: {metrics.provenance_correctness.render()}")
        skills = evaluation.skills
        lines.append("== skills ==")
        lines.append(f"  opportunity matrix: {skills.opportunity_matrix}")
        lines.append(f"  precision: {skills.precision.render()}")
        lines.append(f"  recall: {skills.recall.render()}")
        lines.append(f"  false_positive_absent: {skills.false_positive_absent.render()}")
        lines.append(
            f"  false_positive_unsupported_form: {skills.false_positive_unsupported_form.render()}"
        )
        lines.append(f"  false_positive_ambiguous: {skills.false_positive_ambiguous.render()}")
        lines.append(
            f"  false_positive_outside_frozen_set: "
            f"{skills.false_positive_outside_frozen_set.render()}"
        )
        lines.append("== runtime_failure (per parser invocation) ==")
        for parser in sorted(evaluation.runtime_failure):
            lines.append(f"  {parser}: {evaluation.runtime_failure[parser].render()}")
        lines.append(f"== mismatches ({len(evaluation.mismatches)}) ==")
        for mismatch in sorted(
            evaluation.mismatches, key=lambda m: (m.record_id, m.parser, m.component or "")
        ):
            lines.append(
                f"  record={mismatch.record_id} parser={mismatch.parser} "
                f"component={mismatch.component} category={mismatch.category} "
                f"expected={mismatch.expected!r} actual={mismatch.actual!r}"
            )
    if records is not None and _all_template_families_unknown(records):
        lines.append(
            "note: every record's provenance.template_family is 'unknown' -- a "
            "per-template breakdown would only ever duplicate the combined result "
            "above, so it is intentionally omitted; see the per-employer sections "
            "instead."
        )
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
    evaluations = evaluate_corpus(records, taxonomy=taxonomy)
    print(render_report(evaluations, records=records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
