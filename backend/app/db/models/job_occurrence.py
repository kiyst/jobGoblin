import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

# Same four-character whitespace set as every other trim-only column in this
# project: space, tab, line feed, carriage return.
_COVERED_WHITESPACE = " \t\n\r"

# Every nullable, case-preserving free-text column below: trim-only,
# NULL-safe CHECK pair. `provider`/`source` are handled separately (they are
# NOT NULL and lowercased — see `_normalize_canonical_identifier`); the two
# `*_normalized` URL columns are handled separately too (see class
# docstring: this model never derives them from the raw URL columns).
_NULLABLE_TEXT_COLUMNS = (
    "source_tenant_id",
    "source_job_id",
    "requisition_id_raw",
    "source_url_normalized",
    "apply_url",
    "canonical_url",
    "canonical_url_normalized",
    "applicant_count_text",
)


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


class JobOccurrence(Base):
    """One observed appearance of a job on one source (docs/DATA_MODEL.md's
    `job_occurrences` section, §18; ADR 0004). This is the table the
    project's deterministic identity-resolution scheme is built on — its
    three partial unique indexes below *are* the scoped identity signals
    ADR 0004 defines. The actual match-precedence application logic
    (querying by these indexes in order, deciding new-vs-existing-occurrence,
    writing `identity_conflicts` rows) is Phase 4+ ingestion code, out of
    scope for this schema-only slice.

    `provider`/`source` are required canonical identifiers: lowercased and
    trimmed by the ORM, with a database `CHECK` requiring an already
    trimmed, lowercase, non-empty value — casing or whitespace differences
    must never let two logically-identical rows bypass the natural-key
    indexes below. `source_tenant_id`/`source_job_id`/`requisition_id_raw`
    are externally assigned identifiers and are deliberately **not**
    case-folded — only trimmed.

    `source_url_normalized`/`canonical_url_normalized` are **not** derived
    by this model from `source_url`/`canonical_url` — the database cannot
    guarantee a Python function's output agrees with its raw input, so no
    such guarantee is claimed. `app.normalization.url.normalize_url()` is a
    pure function callers (tests here; Phase 2's persistence path later)
    must call themselves and pass the result in explicitly. The one
    relationship the database *does* enforce is the CHECK that
    `canonical_url IS NULL` implies `canonical_url_normalized IS NULL` — a
    non-null `canonical_url` may still legitimately normalize to `NULL` if
    it's malformed, so this is a one-way implication, not full equivalence.

    `first_seen_at`/`last_seen_at` are NOT NULL with no server default and
    no ORM `onupdate` — they describe observation time (this occurrence's
    own first/most-recent sighting), not row-creation or row-update time, so
    nothing may silently substitute `now()`. Callers (and the test factory)
    must supply both explicitly, and re-observation is an explicit business
    event `last_seen_at` must be set to, not an incidental side effect of
    any other write.
    """

    __tablename__ = "job_occurrences"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_tenant_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    requisition_id_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url_normalized: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    applicant_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applicant_count_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
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
            r"source = lower(trim(both E'\t\n\r ' from source))",
            name="source_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from source) <> ''",
            name="source_not_empty",
        ),
        CheckConstraint(
            r"source_url = trim(both E'\t\n\r ' from source_url)",
            name="source_url_normalized_check",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from source_url) <> ''",
            name="source_url_not_empty",
        ),
        *(check for column in _NULLABLE_TEXT_COLUMNS for check in _trim_not_empty_checks(column)),
        CheckConstraint(
            "canonical_url IS NOT NULL OR canonical_url_normalized IS NULL",
            name="canonical_url_normalized_requires_url",
        ),
        CheckConstraint(
            "applicant_count IS NULL OR applicant_count >= 0",
            name="applicant_count_non_negative",
        ),
        CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="first_seen_at_le_last_seen_at",
        ),
    )

    @validates("provider", "source")
    def _normalize_canonical_identifier(self, _key: str, value: str) -> str:
        """Trims `_COVERED_WHITESPACE` and lowercases — these are canonical
        identifiers the natural-key indexes below compare directly, so
        casing/whitespace differences must never bypass them."""
        return value.strip(_COVERED_WHITESPACE).lower()

    @validates("source_url")
    def _normalize_source_url(self, _key: str, value: str) -> str:
        """Trim-only, case preserved — `source_url` is a required display/
        click-through value, not a canonical identifier."""
        return value.strip(_COVERED_WHITESPACE)

    @validates(*_NULLABLE_TEXT_COLUMNS)
    def _normalize_nullable_text(self, _key: str, value: str | None) -> str | None:
        """Trims `_COVERED_WHITESPACE` and converts a covered-whitespace-only
        value to `None` rather than failing ingestion. Case preserved —
        externally assigned identifiers and normalized-URL values are never
        case-folded by this validator."""
        if value is None:
            return None
        trimmed = value.strip(_COVERED_WHITESPACE)
        return trimmed or None


# Three partial unique indexes implement ADR 0004's scoped natural key —
# see the class docstring. A single combined index cannot express this: it
# would either fail to enforce uniqueness when `source_tenant_id` is NULL
# (PostgreSQL treats every NULL as distinct — the exact Rev 2 bug ADR 0004
# documents fixing) or incorrectly require `source_tenant_id` for sources
# that have no tenant concept at all (LinkedIn, Indeed).
Index(
    "uq_job_occurrences_tenant_natural_key",
    JobOccurrence.provider,
    JobOccurrence.source,
    JobOccurrence.source_tenant_id,
    JobOccurrence.source_job_id,
    unique=True,
    postgresql_where=(JobOccurrence.source_job_id.isnot(None))
    & (JobOccurrence.source_tenant_id.isnot(None)),
)
Index(
    "uq_job_occurrences_no_tenant_natural_key",
    JobOccurrence.provider,
    JobOccurrence.source,
    JobOccurrence.source_job_id,
    unique=True,
    postgresql_where=(JobOccurrence.source_job_id.isnot(None))
    & (JobOccurrence.source_tenant_id.is_(None)),
)
Index(
    "uq_job_occurrences_fallback_url_key",
    JobOccurrence.provider,
    JobOccurrence.source,
    JobOccurrence.source_url_normalized,
    unique=True,
    postgresql_where=JobOccurrence.source_job_id.is_(None),
)

# Lookup indexes (non-unique) — identity-resolution match-precedence steps
# 2/3 (ADR 0004) and the common "active occurrences for this job, freshest
# first" feed-rendering query.
Index("ix_job_occurrences_canonical_url_normalized", JobOccurrence.canonical_url_normalized)
Index(
    "ix_job_occurrences_tenant_requisition_lookup",
    JobOccurrence.provider,
    JobOccurrence.source,
    JobOccurrence.source_tenant_id,
    JobOccurrence.requisition_id_raw,
)
Index(
    "ix_job_occurrences_job_active_last_seen",
    JobOccurrence.job_id,
    JobOccurrence.is_active,
    JobOccurrence.last_seen_at.desc(),
)
