import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

CONFLICT_TYPES = ("evidence_mismatch", "ambiguous_match")
STATUSES = ("open", "resolved", "ignored")

# Same four-character whitespace set as every other trim-only column in this
# project: space, tab, line feed, carriage return.
_COVERED_WHITESPACE = " \t\n\r"


class IdentityConflict(Base):
    """Quarantine record for deterministic identity resolution's two
    conflict outcomes (docs/DATA_MODEL.md's `identity_conflicts` section;
    ADR 0007). Deliberately **not** `duplicate_groups`: this table holds
    exact-match signals that couldn't be safely applied, not probabilistic
    similarity suggestions (Phase 6). Phase 2's offline fixture pipeline is
    the first writer/user of this table; this Phase 1 slice only migrates
    the schema.

    `conflict_type` and `status` are plain `CHECK`-restricted enums, not
    canonical identifiers — no ORM trim/case transform, matching
    `raw_job_ingestions.processing_status`'s treatment, since both are
    closed literal sets, not cross-table join keys.

    `existing_value`/`incoming_value` are NOT NULL jsonb whose *shape*
    depends on `conflict_type`: a JSON object (disputed field → value) for
    `evidence_mismatch`, a JSON array (candidate job/occurrence ids) for
    `ambiguous_match` — enforced by a `CHECK` conditional on `conflict_type`
    for each column. Neither non-empty objects/arrays nor inner element
    schemas are enforced — only the top-level shape, matching this
    project's posture of not validating what isn't demonstrated necessary.
    Deliberately **not** `MutableDict`/`MutableList`-wrapped: immutable,
    write-once snapshots, same rationale as `raw_job_ingestions.raw_payload`.

    `existing_job_occurrence_id`/`incoming_raw_job_ingestion_id` are both
    nullable with `ON DELETE SET NULL` — this table is an audit trail that
    must outlive either referenced row (ADR 0007). Only the safe direction
    of the `conflict_type`/`existing_job_occurrence_id` relationship is a
    database `CHECK`: `ambiguous_match` requires `existing_job_occurrence_id
    IS NULL` (safe — an `ambiguous_match` row never has a non-null value to
    begin with, so `ON DELETE SET NULL` never touches it in a way that could
    violate this). The reverse — `evidence_mismatch` implying a non-null
    `existing_job_occurrence_id` — is deliberately **not** a `CHECK`: a
    real, already-committed `evidence_mismatch` row must be allowed to end
    up with `existing_job_occurrence_id IS NULL` after its disputed
    occurrence is later deleted, the same historical audit-preservation
    state `raw_job_ingestions` already established this pattern for.
    `incoming_raw_job_ingestion_id` gets no `CHECK` at all: it is populated
    for *both* conflict types at write time (no type-based branching), but
    must remain legitimately nullable after its own `ON DELETE SET NULL`
    fires — a write-time convention Phase 2's persistence-service tests
    own proving, not a permanent schema guarantee.

    `status`/`resolved_at` consistency and `resolved_at >= created_at`
    ordering are both plain `CHECK`s — neither interacts with either FK's
    `ON DELETE SET NULL` (different columns entirely), so both directions
    are safe to enforce fully, unlike the FK-adjacent invariants above.
    `status` has **no** server default: fresh conflict creation must
    explicitly supply `'open'`, matching this project's "no silent
    substitution for a business-meaningful value" posture.

    `resolution` is nullable, case-preserving free text: the ORM trims and
    collapses a covered-whitespace-only value to `None`, but there is
    **no** backing `CHECK` — per this table's own design, enforcing
    non-empty narrative text would be enforcing writing quality, which
    this project deliberately does nowhere else. A direct SQL write is
    **not** promised this normalization: an untrimmed or blank `resolution`
    written outside the ORM is not rejected, unlike every other nullable
    text column in this schema.

    `created_at`/`updated_at` are the standard row-lifecycle pair —
    unlike `raw_job_ingestions.fetched_at`, a conflict row's creation
    moment *is* its detection moment, with no buffering/replay distinction,
    so the plain global convention applies directly.
    """

    __tablename__ = "identity_conflicts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    existing_job_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "job_occurrences.id",
            ondelete="SET NULL",
            # Explicit, shortened name: the naming convention's full
            # template exceeds Postgres's 63-byte identifier limit and
            # would otherwise be silently truncated with an auto-appended
            # hash suffix.
            name="fk_identity_conflicts_existing_occurrence",
        ),
        nullable=True,
    )
    incoming_raw_job_ingestion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "raw_job_ingestions.id",
            ondelete="SET NULL",
            name="fk_identity_conflicts_incoming_ingestion",
        ),
        nullable=True,
    )
    conflict_type: Mapped[str] = mapped_column(Text, nullable=False)
    existing_value: Mapped[dict[str, object] | list[object]] = mapped_column(
        JSONB(), nullable=False
    )
    incoming_value: Mapped[dict[str, object] | list[object]] = mapped_column(
        JSONB(), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"conflict_type IN {CONFLICT_TYPES}",
            name="conflict_type_valid",
        ),
        CheckConstraint(
            f"status IN {STATUSES}",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) "
            "OR (status IN ('resolved', 'ignored') AND resolved_at IS NOT NULL)",
            name="status_resolved_at_consistency",
        ),
        CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name="resolved_at_after_created_at",
        ),
        CheckConstraint(
            "(conflict_type = 'evidence_mismatch' AND jsonb_typeof(existing_value) = 'object') "
            "OR (conflict_type = 'ambiguous_match' AND jsonb_typeof(existing_value) = 'array')",
            name="existing_value_shape",
        ),
        CheckConstraint(
            "(conflict_type = 'evidence_mismatch' AND jsonb_typeof(incoming_value) = 'object') "
            "OR (conflict_type = 'ambiguous_match' AND jsonb_typeof(incoming_value) = 'array')",
            name="incoming_value_shape",
        ),
        CheckConstraint(
            "conflict_type <> 'ambiguous_match' OR existing_job_occurrence_id IS NULL",
            name="ambiguous_match_requires_null_occurrence",
        ),
    )

    @validates("resolution")
    def _normalize_resolution(self, _key: str, value: str | None) -> str | None:
        """Trims `_COVERED_WHITESPACE` and converts a covered-whitespace-
        only value to `None`. Case preserved. No corresponding `CHECK` —
        see class docstring; a direct SQL write bypasses this entirely."""
        if value is None:
            return None
        trimmed = value.strip(_COVERED_WHITESPACE)
        return trimmed or None


Index("ix_identity_conflicts_status", IdentityConflict.status)
Index(
    "ix_identity_conflicts_existing_job_occurrence_id",
    IdentityConflict.existing_job_occurrence_id,
)
Index(
    "ix_identity_conflicts_incoming_raw_job_ingestion_id",
    IdentityConflict.incoming_raw_job_ingestion_id,
)
