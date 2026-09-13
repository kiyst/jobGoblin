"""Harness-owned defect-category taxonomy and the 35-historical-record
guard inventory (34 active, 1 superseded -- see the correction note
below `GUARD_INVENTORY`; Workflow v3.2 Slice 2). Imports nothing from
`app.normalization.*` --
this module's categories and guard descriptions are independently
authored, not derived from any parser's source or docstrings beyond
citing the historical commit that produced each guard.

The nine categories below restate (not import -- there is nothing to
import; they are prose in a markdown document) `docs/LLM_WORKFLOW.md`'s
historical-defect checklist. The tenth, `lexical_boundary_character_class`,
is a **staged** category this harness uses internally: five of the 35
guards below don't fit cleanly into the documented nine (a boundary or
character class defined too loosely accepts input it shouldn't,
independent of negation/numeric/structural semantics). Per Workflow
v3.2 Slice 2's binding proposal, `docs/LLM_WORKFLOW.md` itself is not
edited to add this as a tenth category -- that is deferred to Slice 3
or later. Using it here, internally, does not activate that change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal[
    "negation_exclusion_scope",
    "subject_attribution_misassignment",
    "numeric_context_confusion",
    "decimal_fractional_mishandling",
    "token_order_mask_precedence",
    "range_boundary_inversion",
    "structural_positional_gating",
    "provenance_cross_contamination",
    "missing_vs_wrong_distinction",
    "lexical_boundary_character_class",
]

CATEGORIES: frozenset[Category] = frozenset(
    {
        "negation_exclusion_scope",
        "subject_attribution_misassignment",
        "numeric_context_confusion",
        "decimal_fractional_mishandling",
        "token_order_mask_precedence",
        "range_boundary_inversion",
        "structural_positional_gating",
        "provenance_cross_contamination",
        "missing_vs_wrong_distinction",
        "lexical_boundary_character_class",
    }
)

Parser = Literal["location", "salary", "experience"]


GuardStatus = Literal["active", "superseded"]


@dataclass(frozen=True)
class Guard:
    guard_ref: str
    parser: Parser
    category: Category
    description: str
    historical_defect_ref: str
    status: GuardStatus = "active"
    superseded_by: str | None = None
    superseded_explanation: str | None = None

    def __post_init__(self) -> None:
        if self.status == "active":
            if self.superseded_by is not None or self.superseded_explanation is not None:
                raise ValueError(
                    f"{self.guard_ref}: an active guard must not declare superseded_by/"
                    "superseded_explanation"
                )
        else:  # superseded
            if not self.superseded_by:
                raise ValueError(f"{self.guard_ref}: a superseded guard requires superseded_by")
            if self.superseded_by == self.guard_ref:
                raise ValueError(f"{self.guard_ref}: superseded_by must not reference itself")
            if not self.superseded_explanation:
                raise ValueError(
                    f"{self.guard_ref}: a superseded guard requires superseded_explanation"
                )


# One entry per distinct guard/code path (not per function), per Workflow
# v3.2 Slice 2's binding decision to inventory guards rather than
# functions. Location findings 3 and 8 are separate guards even though
# both live inside `_is_recognized_state` (the whitespace-trim step and
# the exact-grammar-validation step are two distinct checks).
#
# **Factual correction discovered through source-history verification**
# (not part of the original binding arithmetic): `experience/g07-
# reversed-label-anchor`'s own historical fix (`2589eec` finding 1,
# anchoring `_LABEL_VALUE_RE.search` to `.match` inside
# `_extract_description_bounds`) was itself fully superseded by a later
# fix (`2fcdc0f` finding 3 -- `experience/g18-description-label-value-
# scope-removed`), which removed the description-side reversed-label
# acceptance path entirely. `_extract_description_bounds` in the current
# `experience.py` source no longer calls `_LABEL_VALUE_RE`/
# `_match_label_value_phrase` in any form -- there is no surviving code
# to mutate independently of g18's own guard. g07 is retained here as a
# **historical record**, marked `status="superseded"`: it has no primary
# witness and no executable mutant (a written approval is not a
# substitute for executable mutation evidence, and g18's own witness
# must never be double-counted as g07's).
#
# Corrected arithmetic: 35 historical guard records (location 8, salary
# 5, experience 22), of which 34 are active executable guards with
# exactly one primary witness and mutant each, and exactly 1
# (experience/g07) is superseded with neither. Experience: 22 historical
# / 21 active / 1 superseded. Salary: 5 active. Location: 8 active.
GUARD_INVENTORY: dict[str, Guard] = {
    g.guard_ref: g
    for g in (
        Guard(
            "location/g01-alias-trailing-period",
            "location",
            "lexical_boundary_character_class",
            "Dotted U.S./U.S.A. alias trailing-period compatibility.",
            "88cdb2f/071d8dc finding 1",
        ),
        Guard(
            "location/g02-state-zip-provenance",
            "location",
            "provenance_cross_contamination",
            "State+ZIP country provenance is INFERRED, not PARSED_DESCRIPTION.",
            "071d8dc finding 2",
        ),
        Guard(
            "location/g03-region-whitespace-trim",
            "location",
            "lexical_boundary_character_class",
            "Region-span whitespace trim step in _is_recognized_state.",
            "071d8dc finding 3",
        ),
        Guard(
            "location/g04-negation-standalone-word",
            "location",
            "negation_exclusion_scope",
            "Standalone negation/exclusion cue in a discarded geo/region span.",
            "071d8dc finding 4",
        ),
        Guard(
            "location/g05-country-conflict-discarded-span",
            "location",
            "missing_vs_wrong_distinction",
            "A recognized country in a discarded span is a conflict, not silently ignored.",
            "071d8dc finding 5",
        ),
        Guard(
            "location/g06-ascii-only-casefold",
            "location",
            "lexical_boundary_character_class",
            "ASCII-only case-insensitivity for state matching (re.ASCII).",
            "071d8dc finding 6",
        ),
        Guard(
            "location/g07-state-precedence-over-coordinator",
            "location",
            "token_order_mask_precedence",
            "State recognition runs before the standalone or/and coordinator check.",
            "071d8dc finding 7",
        ),
        Guard(
            "location/g08-exact-state-token-grammar",
            "location",
            "structural_positional_gating",
            "Exact state-token grammar validation step in _is_recognized_state.",
            "071d8dc finding 3/8",
        ),
        Guard(
            "salary/g01-covered-whitespace-class",
            "salary",
            "lexical_boundary_character_class",
            "Covered-whitespace character class, not bare backslash-s, at every boundary.",
            "261ffe3 finding 1",
        ),
        Guard(
            "salary/g02-label-boundary-strictness",
            "salary",
            "structural_positional_gating",
            "Label-boundary strictness: mandatory whitespace without a colon.",
            "261ffe3 finding 2",
        ),
        Guard(
            "salary/g03-currency-code-boundary-strictness",
            "salary",
            "structural_positional_gating",
            "Currency-code boundary strictness (prefix and suffix).",
            "261ffe3 finding 3",
        ),
        Guard(
            "salary/g04-period-boundary-by-shape",
            "salary",
            "structural_positional_gating",
            "Period-boundary strictness split by shape (slash vs. word).",
            "261ffe3 finding 4",
        ),
        Guard(
            "salary/g05-up-to-narrowed-forms",
            "salary",
            "token_order_mask_precedence",
            "'up...to' narrowed to exactly two accepted forms.",
            "261ffe3 finding 5",
        ),
        Guard(
            "experience/g01-attribution-frame",
            "experience",
            "subject_attribution_misassignment",
            "Closed applicant-attribution frame, not bare subject/verb adjacency.",
            "e13d8a6 pre-code amendment 2",
        ),
        Guard(
            "experience/g02-continuation-boundary",
            "experience",
            "negation_exclusion_scope",
            "Uniform continuation-boundary rule: only an empty remainder accepts.",
            "e13d8a6 pre-code amendment 3",
        ),
        Guard(
            "experience/g03-individual-number-redaction",
            "experience",
            "token_order_mask_precedence",
            "Atomic individual-number poisoning pass before segmentation.",
            "e13d8a6 pre-code amendment 4",
        ),
        Guard(
            "experience/g04-positional-preference-suppression",
            "experience",
            "subject_attribution_misassignment",
            "Positional, not lexical, preference-marker suppression.",
            "e13d8a6 pre-code amendment 5",
        ),
        Guard(
            "experience/g05-internal-conflict-precedence",
            "experience",
            "missing_vs_wrong_distinction",
            "Internal-conflict-before-cross-source reconciliation precedence.",
            "e13d8a6 pre-code amendment 6",
        ),
        Guard(
            "experience/g06-original-unicode-hyphen-disambiguation",
            "experience",
            "numeric_context_confusion",
            "Original Unicode dash vs. ASCII-hyphen range disambiguation.",
            "e13d8a6 pre-code amendment (Risk 5)",
        ),
        Guard(
            "experience/g07-reversed-label-anchor",
            "experience",
            "subject_attribution_misassignment",
            "Reversed label:value anchored with match, not search.",
            "2589eec finding 1",
            status="superseded",
            superseded_by="experience/g18-description-label-value-scope-removed",
            superseded_explanation=(
                "The description-side reversed-label acceptance path this guard anchored "
                "was removed entirely by a later fix (2fcdc0f finding 3, g18); "
                "_extract_description_bounds no longer calls _LABEL_VALUE_RE/"
                "_match_label_value_phrase in any form, so no code survives to mutate "
                "independently of g18's own guard."
            ),
        ),
        Guard(
            "experience/g08-title-leading-preference",
            "experience",
            "negation_exclusion_scope",
            "Title leading-preference marker (comma optional).",
            "2589eec finding 2 (leading marker)",
        ),
        Guard(
            "experience/g09-cross-segment-qualifier-following",
            "experience",
            "negation_exclusion_scope",
            "Cross-segment qualifier suppression, following segment.",
            "2589eec finding 2 (cross-segment)",
        ),
        Guard(
            "experience/g10-trailing-bound-marker",
            "experience",
            "range_boundary_inversion",
            "Trailing bound marker after the complete phrase.",
            "2589eec finding 3",
        ),
        Guard(
            "experience/g11-unsupported-prefix-poison",
            "experience",
            "negation_exclusion_scope",
            "Unsupported prefix poisoning ('less than'/'fewer than').",
            "2589eec finding 3 (prefix poison)",
        ),
        Guard(
            "experience/g12-fraction-slash-normalization",
            "experience",
            "numeric_context_confusion",
            "Fraction-slash NFKC normalization before poisoning.",
            "2589eec finding 4 (fraction slash)",
        ),
        Guard(
            "experience/g13-unicode-dash-poison",
            "experience",
            "numeric_context_confusion",
            "Unicode dash/minus poisoning, individual number.",
            "2589eec finding 4 (dash poison)",
        ),
        Guard(
            "experience/g14-multi-candidate-collection",
            "experience",
            "missing_vs_wrong_distinction",
            "Multi-candidate collection per title segment.",
            "2589eec finding 5",
        ),
        Guard(
            "experience/g15-title-segment-order-preservation",
            "experience",
            "structural_positional_gating",
            "Title-segment order preservation (original left-to-right order).",
            "2fcdc0f finding 1 (ordering)",
        ),
        Guard(
            "experience/g16-bidirectional-adjacency",
            "experience",
            "structural_positional_gating",
            "Bidirectional qualifier-adjacency check.",
            "2fcdc0f finding 1 (bidirectional)",
        ),
        Guard(
            "experience/g17-composite-range-poison-decimal-fraction",
            "experience",
            "decimal_fractional_mishandling",
            "Composite-range poisoning, decimal and fraction shapes.",
            "2fcdc0f finding 2",
        ),
        Guard(
            "experience/g18-description-label-value-scope-removed",
            "experience",
            "structural_positional_gating",
            "Description-side label:value exemption removed.",
            "2fcdc0f finding 3 (exemption removed)",
        ),
        Guard(
            "experience/g19-title-label-value-whole-anchor",
            "experience",
            "structural_positional_gating",
            "Whole-title anchoring for label:value plus mandatory unit.",
            "2fcdc0f finding 3 (whole-title anchor)",
        ),
        Guard(
            "experience/g20-empty-segment-adjacency",
            "experience",
            "structural_positional_gating",
            "Empty-segment adjacency walk to the nearest meaningful neighbor.",
            "1610f57 finding 1",
        ),
        Guard(
            "experience/g21-composite-range-poison-negative",
            "experience",
            "range_boundary_inversion",
            "Composite-range poisoning extended to the negative-number case.",
            "1610f57 finding 2",
        ),
        Guard(
            "experience/g22-composite-poison-casefold",
            "experience",
            "lexical_boundary_character_class",
            "Case-insensitivity on the three composite-range poison patterns.",
            "559e77a finding 1",
        ),
    )
}


def active_guards() -> dict[str, Guard]:
    return {ref: g for ref, g in GUARD_INVENTORY.items() if g.status == "active"}


def superseded_guards() -> dict[str, Guard]:
    return {ref: g for ref, g in GUARD_INVENTORY.items() if g.status == "superseded"}


assert (
    len(GUARD_INVENTORY) == 35
), f"expected 35 historical guard records, found {len(GUARD_INVENTORY)}"
assert len(active_guards()) == 34, f"expected 34 active guards, found {len(active_guards())}"
assert (
    len(superseded_guards()) == 1
), f"expected exactly 1 superseded guard, found {len(superseded_guards())}"

_BY_PARSER_TOTAL: dict[Parser, int] = {"location": 0, "salary": 0, "experience": 0}
_BY_PARSER_ACTIVE: dict[Parser, int] = {"location": 0, "salary": 0, "experience": 0}
for _guard in GUARD_INVENTORY.values():
    _BY_PARSER_TOTAL[_guard.parser] += 1
    if _guard.status == "active":
        _BY_PARSER_ACTIVE[_guard.parser] += 1
assert _BY_PARSER_TOTAL == {
    "location": 8,
    "salary": 5,
    "experience": 22,
}, f"per-parser historical guard counts drifted: {_BY_PARSER_TOTAL}"
assert _BY_PARSER_ACTIVE == {
    "location": 8,
    "salary": 5,
    "experience": 21,
}, f"per-parser active guard counts drifted: {_BY_PARSER_ACTIVE}"

# Every superseded guard's superseded_by must resolve to a *different*,
# *active* guard actually present in this inventory -- a dangling,
# self-referential, or non-active superseded_by is a taxonomy defect,
# not a valid historical record.
for _guard in superseded_guards().values():
    _target = GUARD_INVENTORY.get(_guard.superseded_by or "")
    assert _target is not None, (
        f"{_guard.guard_ref}: superseded_by {_guard.superseded_by!r} does not resolve to any "
        "guard in this inventory"
    )
    assert _target.status == "active", (
        f"{_guard.guard_ref}: superseded_by {_guard.superseded_by!r} must reference an active "
        f"guard, but it is {_target.status!r}"
    )

_LEXICAL_BOUNDARY_COUNT = sum(
    1 for g in active_guards().values() if g.category == "lexical_boundary_character_class"
)
assert _LEXICAL_BOUNDARY_COUNT == 5, (
    "lexical_boundary_character_class must cover exactly 5 active guards, found "
    f"{_LEXICAL_BOUNDARY_COUNT}"
)
