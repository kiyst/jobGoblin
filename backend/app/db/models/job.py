import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

REMOTE_TYPES = ("remote", "hybrid", "onsite")
SALARY_PERIODS = ("hourly", "daily", "monthly", "annual")

# Same four-character whitespace set as every other trim-only column in this
# project: space, tab, line feed, carriage return.
_COVERED_WHITESPACE = " \t\n\r"

# Every nullable free-text column below: trim-only, case preserved, no
# format/enum validation beyond "already normalized and non-empty when
# present." Listed once so both the `@validates` handler and the CHECK
# constraints (`_trim_not_empty_checks` below) stay in sync by construction
# instead of by two independently-maintained lists.
_NULLABLE_TEXT_COLUMNS = (
    "requisition_id",
    "canonical_url",
    "preferred_apply_url",
    "title",
    "normalized_title",
    "job_family",
    "department",
    "team",
    "description_raw",
    "description_clean",
    "location_raw",
    "city",
    "state",
    "country",
    "postal_code",
    "employment_type",
    "seniority",
    "contract_type",
    "shift",
    "salary_currency",
    "education_requirement",
    "clearance_requirement",
    "visa_sponsorship_status",
    "travel_requirement",
    "compensation_text",
)


def _trim_not_empty_checks(column: str) -> tuple[CheckConstraint, CheckConstraint]:
    """NULL-safe trim/non-empty CHECK pair for one nullable text column —
    only constrains a non-NULL value, matching `Company`'s
    `homepage_url`/`career_page_url`/`industry` pattern."""
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


class Job(Base):
    """The canonical, resolved job record (docs/DATA_MODEL.md's `jobs`
    section, §20). Every field here is a **resolved** value across possibly
    many occurrences — see `field_provenance` below and the "Provenance"
    section of docs/DATA_MODEL.md. `requisition_id`/`canonical_url` are
    resolved *display* values only; identity/matching keys live entirely on
    `job_occurrences` (a separate, later slice), which is why this table
    declares no UNIQUE constraint of its own.

    `company_id` is nullable: `DiscoveredJob.company` is explicitly nullable
    in docs/ARCHITECTURE.md, and requiring a resolved company here would
    force ingestion to either reject an otherwise-valid job or manufacture a
    fake "unknown company" row — neither is acceptable. `ON DELETE RESTRICT`
    still applies whenever `company_id` is non-null: a company merge/delete
    must be an explicit reconciliation step, never an accidental cascade.

    `duplicate_group_id` is deliberately **omitted** from this migration:
    `duplicate_groups` is a Phase 6 table that does not exist yet, so no FK
    could be declared against it now. It will be added, with its FK, in a
    Phase 6 migration alongside `duplicate_groups` itself.

    `first_seen_at`/`last_seen_at` are NOT NULL with no server default —
    they describe observation time (the earliest/latest an occurrence of
    this job was actually seen), not row-creation time, so nothing may
    silently substitute `now()` for an omitted value. Callers (and the test
    factory) must supply both explicitly.

    `certifications` is wrapped with `MutableList.as_mutable` and
    `field_provenance` with `MutableDict.as_mutable` for the same reason as
    every other array/jsonb column in this schema: an in-place `.append()`/
    key-assignment on the loaded Python value is otherwise invisible to the
    unit-of-work and silently dropped on commit. `MutableDict` only
    instruments the wrapped dict's own top-level `__setitem__`/`__delitem__`
    — mutating a *nested* structure already stored inside `field_provenance`
    (e.g. `job.field_provenance["salary_min"]["source"] = "x"`) is invisible
    to the unit-of-work and would still be silently dropped on commit,
    exactly like `SavedSearch.enabled_sources`/`scoring_weights`. The
    correct pattern is to replace the complete per-field object:
    `job.field_provenance["salary_min"] = updated_entry`.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    requisition_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_apply_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_family: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    team: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    state: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    postal_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    remote_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    seniority: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    shift: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary_period: Mapped[str | None] = mapped_column(Text, nullable=True)
    annualized_salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annualized_salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compensation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    compensation_explicit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    years_experience_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    years_experience_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    education_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    certifications: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    clearance_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    visa_sponsorship_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    travel_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    application_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    field_provenance: Mapped[dict[str, object] | None] = mapped_column(
        MutableDict.as_mutable(JSONB()), nullable=True
    )
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
        *(check for column in _NULLABLE_TEXT_COLUMNS for check in _trim_not_empty_checks(column)),
        CheckConstraint(
            f"remote_type IS NULL OR remote_type IN {REMOTE_TYPES}",
            name="remote_type_valid",
        ),
        CheckConstraint(
            f"salary_period IS NULL OR salary_period IN {SALARY_PERIODS}",
            name="salary_period_valid",
        ),
        CheckConstraint("salary_min IS NULL OR salary_min >= 0", name="salary_min_non_negative"),
        CheckConstraint("salary_max IS NULL OR salary_max >= 0", name="salary_max_non_negative"),
        CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name="salary_min_le_max",
        ),
        CheckConstraint(
            "annualized_salary_min IS NULL OR annualized_salary_min >= 0",
            name="annualized_salary_min_non_negative",
        ),
        CheckConstraint(
            "annualized_salary_max IS NULL OR annualized_salary_max >= 0",
            name="annualized_salary_max_non_negative",
        ),
        CheckConstraint(
            "annualized_salary_min IS NULL OR annualized_salary_max IS NULL "
            "OR annualized_salary_min <= annualized_salary_max",
            name="annualized_salary_min_le_max",
        ),
        CheckConstraint(
            "years_experience_min IS NULL OR years_experience_min >= 0",
            name="years_experience_min_non_negative",
        ),
        CheckConstraint(
            "years_experience_max IS NULL OR years_experience_max >= 0",
            name="years_experience_max_non_negative",
        ),
        CheckConstraint(
            "years_experience_min IS NULL OR years_experience_max IS NULL "
            "OR years_experience_min <= years_experience_max",
            name="years_experience_min_le_max",
        ),
        CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name="latitude_in_range",
        ),
        CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name="longitude_in_range",
        ),
        CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name="latitude_longitude_both_or_neither",
        ),
        CheckConstraint(
            "field_provenance IS NULL OR jsonb_typeof(field_provenance) = 'object'",
            name="field_provenance_is_object",
        ),
        CheckConstraint(
            "first_seen_at <= last_seen_at",
            name="first_seen_at_le_last_seen_at",
        ),
    )

    @validates(*_NULLABLE_TEXT_COLUMNS)
    def _normalize_nullable_text(self, _key: str, value: str | None) -> str | None:
        """Trims `_COVERED_WHITESPACE` and converts a covered-whitespace-only
        value to `None` rather than failing ingestion — every field this
        validator applies to is optional, so a blank value is "not
        provided," not invalid input. Matches `Company`'s equivalent
        validator for its own nullable text columns."""
        if value is None:
            return None
        trimmed = value.strip(_COVERED_WHITESPACE)
        return trimmed or None


# Plain, non-unique index for the "list a company's jobs" query — not a
# uniqueness/correctness requirement, so not part of __table_args__ above.
Index("ix_jobs_company_id", Job.company_id)
