"""Shared result/provenance types for Phase 3 normalization parsers
(docs/DATA_MODEL.md's Provenance section, docs/PHASE_RISK_CHECKLIST.md's
Phase 3 exit gate). Pure data types only — no ORM, no provider, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, TypeVar

T = TypeVar("T")


class Provenance(StrEnum):
    """docs/DATA_MODEL.md's Provenance section, in decreasing trust order.
    Exactly six values, matching that document's vocabulary exactly — a
    test asserts this count and the exact member values so a future edit
    can't silently add/remove/rename a tag without a test failing.
    """

    EXPLICIT_SOURCE = "explicit_source"
    STRUCTURED_METADATA = "structured_metadata"
    PARSED_DESCRIPTION = "parsed_description"
    DERIVED = "derived"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


_TYPE_ERROR = (
    "NormalizationResult invariant violated: provenance must be a " "Provenance enum member."
)
_NONE_INVARIANT_ERROR = (
    "NormalizationResult invariant violated: value must be None if and "
    "only if provenance is Provenance.UNAVAILABLE."
)


@dataclass(frozen=True)
class NormalizationResult(Generic[T]):
    """Pure in-memory (value, provenance) pair a Phase 3 parser returns for
    one atomic field. Never persisted directly — writing into
    `jobs.field_provenance` is a Phase 4+ ingestion-layer concern
    (docs/DATA_MODEL.md's "Field merging across occurrences"), and no
    `parser_version` is threaded here either.

    Deliberately narrow: this type represents exactly one atomic value with
    exactly one provenance tag. A composite parser producing several
    independently-provenanced fields (e.g. a future salary parser's
    min/max/currency/period) must not force them through one shared
    `NormalizationResult` — it should either return several independent
    `NormalizationResult` instances, one per atomic field, or define its
    own dedicated structured result type with a `NormalizationResult` per
    field. That choice is deferred to each such parser's own proposal.

    Invariants (enforced in `__post_init__`, both violations raising a
    fixed, categorical `ValueError` with no interpolated runtime content —
    `value`/`provenance` are never included in the message, since a future
    parser's `T` could carry arbitrary or sensitive text):
    - `provenance` must be an actual `Provenance` enum member, never a raw
      string or other value — checked first, since a raw string can share
      textual content with a real member (e.g. the literal `"unavailable"`)
      without being one, which would otherwise let a malformed provenance
      silently pass the invariant below.
    - `value is None` if and only if `provenance is Provenance.UNAVAILABLE`.
      A present value never carries `UNAVAILABLE`; `UNAVAILABLE` never
      carries a value.
    """

    value: T | None
    provenance: Provenance

    def __post_init__(self) -> None:
        if not isinstance(self.provenance, Provenance):
            raise ValueError(_TYPE_ERROR)
        if (self.value is None) != (self.provenance is Provenance.UNAVAILABLE):
            raise ValueError(_NONE_INVARIANT_ERROR)
