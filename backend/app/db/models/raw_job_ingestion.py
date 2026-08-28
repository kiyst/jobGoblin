import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

PROCESSING_STATUSES = ("fetched", "parse_error", "normalized", "identity_conflict")

# States that, by ADR 0005/0007's own definition, can never have an
# occurrence to link to at all: `fetched` is the transient pre-processing
# state, `parse_error` means the payload itself was never usable.
_UNPROCESSED_STATUSES = ("fetched", "parse_error")

# Same four-character whitespace set as every other trim-only column in this
# project: space, tab, line feed, carriage return.
_COVERED_WHITESPACE = " \t\n\r"

# Every nullable, case-preserving free-text column below: trim-only,
# NULL-safe CHECK pair. `provider`/`source` are handled separately (NOT
# NULL, lowercased, slug-restricted — see `_normalize_canonical_identifier`);
# `raw_content_hash` is handled separately too (NOT NULL, trim-only, no
# blank-to-`None` collapse possible on a required column).
_NULLABLE_TEXT_COLUMNS = ("source_identifier", "parser_version", "error_message")


def _trim_not_empty_checks(column: str) -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint(
            rf"{column} IS NULL OR {column} = trim(both E'\t\n\r ' from {column})",
            name=f"{column}_normalized",
        ),
        CheckConstraint(
            rf"{column} IS NULL OR trim(both E'\t\n\r ' from {column}) <> ''",
            name=f"{column}_not_empty",
        ),
    )


class RawJobIngestion(Base):
    """Preserved pre-normalization payload, one row per individual discovered
    posting fetch — not per provider request/attempt (docs/DATA_MODEL.md's
    `raw_job_ingestions` section; ADR 0005). Phase 4+ ingestion code is the
    first writer; this Phase 1 slice only migrates the schema.

    `provider`/`source` are the same canonical identifiers as
    `job_occurrences`: lowercased/trimmed by the ORM, `CHECK`-restricted to
    an already-canonical, ASCII-slug value
    (`^[a-z0-9][a-z0-9._-]*$`) — they are this project's own internal
    categorization labels, not external "raw" data, so the cross-cutting
    "preserve raw values" principle does not apply to them the way it does
    to `raw_payload`. `source_identifier`/`parser_version`/`error_message`
    are trim-only, case-preserving, NULL-safe.

    `job_occurrence_id` is nullable with `ON DELETE SET NULL` — this table
    is an audit trail that must outlive the occurrence it once pointed at
    (ADR 0005). `raw_payload` stays NOT NULL through Phase 1 (a `CHECK`
    requires it be a top-level JSON object); the later retention job
    described in docs/DATA_MODEL.md that nulls old payloads to bound
    storage will need its own deliberate migration to relax this when that
    cleanup feature is actually built — not a speculative relaxation now.
    Deliberately **not** `MutableDict`-wrapped: unlike `jobs.field_provenance`
    (incrementally updated field-by-field), this column is an immutable,
    write-once snapshot set at insert and never edited in place afterward.
    Not wrapping it does not itself guarantee immutability — whole-value
    ORM assignment and direct SQL `UPDATE`s remain fully possible; this is
    an application-level convention (Phase 2's ingestion code must honor
    it), tested behaviorally here, not schema-enforced.

    `processing_status`/`job_occurrence_id` consistency is only enforced in
    the direction that can never conflict with `ON DELETE SET NULL`:
    `fetched`/`parse_error` require `job_occurrence_id IS NULL` (a `CHECK` —
    these two states can never have an occurrence to link to at all, so the
    FK cascade never touches them). The reverse — `normalized`/
    `identity_conflict` implying a non-null `job_occurrence_id` — is
    deliberately **not** a database `CHECK`: it holds at write time (Phase
    2's persistence-service tests will prove that), but a real,
    already-committed `normalized` row must be allowed to end up with
    `job_occurrence_id IS NULL` after its target occurrence is later
    deleted — that is exactly the historical audit-preservation state ADR
    0005 exists to support, not a data-integrity violation.

    `fetched_at` is NOT NULL with **no** server default: it represents the
    actual fetch event, which may differ from row-insertion time during
    buffering, replay, or backfill, so nothing may silently substitute
    `now()`. `created_at`/`updated_at` are the separate, standard row-
    lifecycle pair (per the established global convention), distinct from
    this business timestamp.
    """

    __tablename__ = "raw_job_ingestions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("job_occurrences.id", ondelete="SET NULL"),
        nullable=True,
    )
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSONB(), nullable=False)
    raw_content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parser_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            r"provider = lower(trim(both E'\t\n\r ' from provider))",
            name="provider_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from provider) <> ''",
            name="provider_not_empty",
        ),
        CheckConstraint(
            r"provider ~ '^[a-z0-9][a-z0-9._-]*$'",
            name="provider_slug_format",
        ),
        CheckConstraint(
            r"source = lower(trim(both E'\t\n\r ' from source))",
            name="source_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from source) <> ''",
            name="source_not_empty",
        ),
        CheckConstraint(
            r"source ~ '^[a-z0-9][a-z0-9._-]*$'",
            name="source_slug_format",
        ),
        *(check for column in _NULLABLE_TEXT_COLUMNS for check in _trim_not_empty_checks(column)),
        CheckConstraint(
            r"raw_content_hash = trim(both E'\t\n\r ' from raw_content_hash)",
            name="raw_content_hash_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from raw_content_hash) <> ''",
            name="raw_content_hash_not_empty",
        ),
        CheckConstraint(
            "jsonb_typeof(raw_payload) = 'object'",
            name="raw_payload_is_object",
        ),
        CheckConstraint(
            f"processing_status IN {PROCESSING_STATUSES}",
            name="processing_status_valid",
        ),
        CheckConstraint(
            f"processing_status NOT IN {_UNPROCESSED_STATUSES} OR job_occurrence_id IS NULL",
            name="unprocessed_requires_null_occurrence",
        ),
    )

    @validates("provider", "source")
    def _normalize_canonical_identifier(self, _key: str, value: str) -> str:
        """Trims `_COVERED_WHITESPACE` and lowercases — same canonical-
        identifier treatment as `job_occurrences.provider`/`.source`."""
        return value.strip(_COVERED_WHITESPACE).lower()

    @validates("raw_content_hash")
    def _normalize_raw_content_hash(self, _key: str, value: str) -> str:
        """Trim-only, case preserved — required, but not a canonical
        identifier compared across rows."""
        return value.strip(_COVERED_WHITESPACE)

    @validates(*_NULLABLE_TEXT_COLUMNS)
    def _normalize_nullable_text(self, _key: str, value: str | None) -> str | None:
        """Trims `_COVERED_WHITESPACE` and converts a covered-whitespace-only
        value to `None` rather than failing ingestion. Case preserved."""
        if value is None:
            return None
        trimmed = value.strip(_COVERED_WHITESPACE)
        return trimmed or None


# Backs "the latest ingestion for this occurrence" (ADR 0005's derived
# query, since the circular FK it replaces was removed) and the common
# "all ingestions for this occurrence, freshest first" lookup.
Index(
    "ix_raw_job_ingestions_occurrence_fetched_at",
    RawJobIngestion.job_occurrence_id,
    RawJobIngestion.fetched_at.desc(),
)
