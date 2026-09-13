"""Closed record schema for the deterministic parser-contract harness
(Workflow v3.2 Slice 2). Imports nothing from `app.normalization.*` --
per binding clarification 1, this module must not import or construct
the production `NormalizationResult` type. The value/provenance
consistency invariant it enforces (a field's value is `None` if and
only if its provenance is `"unavailable"`) is re-implemented here,
independently, as the harness's own rule -- this preserves the project
rule that only adapter modules may import production normalization
code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Parser = Literal["location", "salary", "experience"]
PARSERS: frozenset[Parser] = frozenset({"location", "salary", "experience"})

RecordKind = Literal["base", "generated"]

# Harness-owned provenance vocabulary -- deliberately duplicated, not
# imported, from `app.normalization.types.Provenance`'s six string
# values (documented in docs/DATA_MODEL.md). This is an independent
# declaration of a stable, documented vocabulary, not a derivation from
# production code.
Provenance = Literal[
    "explicit_source",
    "structured_metadata",
    "parsed_description",
    "derived",
    "inferred",
    "unavailable",
]
PROVENANCE_VALUES: frozenset[str] = frozenset(
    {
        "explicit_source",
        "structured_metadata",
        "parsed_description",
        "derived",
        "inferred",
        "unavailable",
    }
)

TransformName = Literal[
    "none",
    "ascii_recase",
    "nfkc_fullwidth_substitute",
    "insert_codepoint",
    "append_codepoints",
    "remove_boundary",
]
TRANSFORM_NAMES: frozenset[str] = frozenset(
    {
        "none",
        "ascii_recase",
        "nfkc_fullwidth_substitute",
        "insert_codepoint",
        "append_codepoints",
        "remove_boundary",
    }
)

# The exact parameter-key set each transform accepts -- no more, no
# fewer. Used by the loader to reject an extraneous/typo'd parameter
# key that `transforms.apply_transform`'s own required-key checks alone
# would otherwise silently ignore.
TRANSFORM_PARAMETER_KEYS: dict[str, frozenset[str]] = {
    "none": frozenset(),
    "ascii_recase": frozenset({"mode"}),
    "nfkc_fullwidth_substitute": frozenset({"start", "end"}),
    "insert_codepoint": frozenset({"codepoint", "position"}),
    "append_codepoints": frozenset({"codepoints"}),
    "remove_boundary": frozenset({"start", "end"}),
}

# Per-parser closed vocabularies. `semantic_form` and `boundary` are
# harness-owned descriptive applicability metadata -- independently
# named, not copied from any parser's private `_PRODUCTIONS` dictionary
# keys or otherwise derived from parser implementation. They are
# validated by the loader and used only to state applicability; they
# never drive production dispatch.
INPUT_FIELDS: dict[Parser, frozenset[str]] = {
    "location": frozenset({"location"}),
    "salary": frozenset({"compensation_text"}),
    "experience": frozenset({"title", "description"}),
}

OUTPUT_FIELDS: dict[Parser, frozenset[str]] = {
    "location": frozenset({"city", "state", "country", "postal_code"}),
    "salary": frozenset({"minimum", "maximum", "currency", "period"}),
    "experience": frozenset({"minimum", "maximum"}),
}

# The exact value type each output field requires when its provenance is
# not "unavailable" -- genuinely parser/field-discriminated, not a
# blanket "str or int" accepted for every field regardless of what it
# actually is. Location's four fields are all strings; salary's/
# experience's numeric bounds are integers; salary's currency/period are
# strings. `bool` is never valid for any field (checked separately,
# since Python's `bool` is a subclass of `int` and must never satisfy
# an `int`-typed field either).
OUTPUT_FIELD_TYPES: dict[Parser, dict[str, type]] = {
    "location": {"city": str, "state": str, "country": str, "postal_code": str},
    "salary": {"minimum": int, "maximum": int, "currency": str, "period": str},
    "experience": {"minimum": int, "maximum": int},
}

SEMANTIC_FORMS: dict[Parser, frozenset[str]] = {
    "location": frozenset(
        {
            "country_declaration",
            "city_state_pair",
            "city_state_postal_triplet",
            "city_country_pair",
            "city_region_country_triplet",
        }
    ),
    "salary": frozenset(
        {
            "single_amount_or_floor",
            "ceiling_only",
            "hyphen_bounded_range",
            "to_bounded_range",
            "between_and_bounded_range",
        }
    ),
    "experience": frozenset(
        {
            "bare_phrase",
            "hyphen_range_phrase",
            "to_range_phrase",
            "between_and_range_phrase",
            "open_lower_phrase",
            "open_upper_phrase",
            "trailing_marker_phrase",
            "label_value_phrase",
            "short_form_phrase",
            "zero_phrase",
        }
    ),
}

BOUNDARIES: dict[Parser, frozenset[str]] = {
    "location": frozenset(
        {
            "marker_prefix",
            "marker_suffix",
            "geo_span",
            "region_span",
            "state_token",
            "country_token",
            "postal_token",
            "whole_field",
        }
    ),
    "salary": frozenset(
        {
            "label_boundary",
            "code_boundary",
            "period_boundary",
            "range_separator",
            "whole_field",
        }
    ),
    "experience": frozenset(
        {
            "attribution_frame",
            "continuation_boundary",
            "numeric_redaction",
            "title_segment_adjacency",
            "preference_suppression",
            "casefold_consistency",
            "whole_field",
        }
    ),
}


class ContractRecordError(ValueError):
    """Raised by the loader for any fail-closed validation failure."""


@dataclass(frozen=True)
class Target:
    input_field: str
    semantic_form: str
    boundary: str


@dataclass(frozen=True)
class TransformSpec:
    name: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ExpectedField:
    value: object
    provenance: str

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE_VALUES:
            raise ContractRecordError(
                f"unrecognized provenance {self.provenance!r}; must be one of "
                f"{sorted(PROVENANCE_VALUES)}"
            )
        is_unavailable = self.provenance == "unavailable"
        is_none = self.value is None
        if is_unavailable != is_none:
            raise ContractRecordError(
                "value/provenance invariant violated: value must be None if and "
                f"only if provenance is 'unavailable' (value={self.value!r}, "
                f"provenance={self.provenance!r})"
            )


@dataclass(frozen=True)
class CaseRecord:
    record_id: str
    kind: RecordKind
    parser: Parser
    guard_ref: str
    target: Target
    original_input: dict[str, str | None]
    transform: TransformSpec
    expected_transformed_input: dict[str, str | None]
    expected_output: dict[str, ExpectedField]
    rationale: str
    is_primary_witness: bool = False
    base_record_id: str | None = None
    historical_defect_ref: str | None = None
