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
    true,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

REMOTE_RULES = ("remote_only", "hybrid_ok", "onsite_ok", "any")
POLLING_SCHEDULES = ("manual", "hourly", "daily", "weekly")

# Same four-character whitespace set as `User._COVERED_WHITESPACE` /
# `CandidateSkill._COVERED_WHITESPACE`: space, tab, line feed, carriage
# return. `name` is trim-only, like `skill` — never lowercased, since (unlike
# `email`) it carries no uniqueness requirement.
_COVERED_WHITESPACE = " \t\n\r"


class SavedSearch(Base):
    """ "What am I looking for right now" (docs/DATA_MODEL.md §saved_searches).

    Every `text[]` column is nullable with no server default: NULL means the
    user never specified that field. Every array column is wrapped with
    `MutableList.as_mutable` so an in-place `.append()`/`.remove()` on a
    loaded list is tracked and actually written on commit (the same bug
    caught on `CandidateProfile` — applied here from the start rather than
    fixed in a later pass).

    `enabled_sources` and `scoring_weights` are the first `jsonb` columns in
    this schema. Both are wrapped with `MutableDict.as_mutable` for the same
    reason the array columns are — but `MutableDict` (like `MutableList`)
    only instruments the wrapped collection's own top-level `__setitem__`/
    `__delitem__`. Mutating a *nested* dict or list already stored inside one
    of these columns (e.g. `saved_search.scoring_weights["nested"]["x"] = 1`)
    is invisible to the unit-of-work and would still be silently dropped on
    commit — only a top-level key assignment/deletion on the column itself
    is tracked. Both are also restricted by a `CHECK` to a top-level JSON
    *object* (not array/string/number/bool) when non-null; deeper shape
    (e.g. which keys `enabled_sources` may contain) is validated by Phase
    2's `QueryPlanner` against `ProviderRegistry`/`ProviderCapabilities`, not
    by a Phase 1 database constraint — see docs/ARCHITECTURE.md §6.5–6.6.
    """

    __tablename__ = "saved_searches"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    excluded_titles: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    industries: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    employment_types: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    seniority: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    must_have_skills: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    preferred_skills: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    excluded_keywords: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    preferred_companies: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    excluded_companies: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    enabled_providers: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)), nullable=True
    )
    # Plain `numeric`, deliberately without precision/scale (no rounding, no
    # maximum) — but, like the integer numeric fields below, still requires
    # a non-negative value via the CHECK in __table_args__.
    radius_miles: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    remote_rules: Mapped[str] = mapped_column(Text, nullable=False)
    salary_floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recency_limit_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled_sources: Mapped[dict[str, object] | None] = mapped_column(
        MutableDict.as_mutable(JSONB()), nullable=True
    )
    polling_schedule: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_weights: Mapped[dict[str, object] | None] = mapped_column(
        MutableDict.as_mutable(JSONB()), nullable=True
    )
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
            r"name = trim(both E'\t\n\r ' from name)",
            name="name_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from name) <> ''",
            name="name_not_empty",
        ),
        CheckConstraint(
            "radius_miles IS NULL OR radius_miles >= 0",
            name="radius_miles_non_negative",
        ),
        CheckConstraint(
            "remote_rules IN ('remote_only', 'hybrid_ok', 'onsite_ok', 'any')",
            name="remote_rules_valid",
        ),
        CheckConstraint(
            "polling_schedule IN ('manual', 'hourly', 'daily', 'weekly')",
            name="polling_schedule_valid",
        ),
        CheckConstraint(
            "salary_floor IS NULL OR salary_floor >= 0",
            name="salary_floor_non_negative",
        ),
        CheckConstraint(
            "preferred_salary IS NULL OR preferred_salary >= 0",
            name="preferred_salary_non_negative",
        ),
        CheckConstraint(
            "recency_limit_hours IS NULL OR recency_limit_hours >= 0",
            name="recency_limit_hours_non_negative",
        ),
        CheckConstraint(
            "salary_floor IS NULL OR preferred_salary IS NULL "
            "OR salary_floor <= preferred_salary",
            name="salary_floor_le_preferred_salary",
        ),
        CheckConstraint(
            "enabled_sources IS NULL OR jsonb_typeof(enabled_sources) = 'object'",
            name="enabled_sources_is_object",
        ),
        CheckConstraint(
            "scoring_weights IS NULL OR jsonb_typeof(scoring_weights) = 'object'",
            name="scoring_weights_is_object",
        ),
    )

    @validates("name")
    def _normalize_name(self, _key: str, value: str) -> str:
        """Trim `_COVERED_WHITESPACE` before the row ever reaches the
        database — case is preserved, unlike `User._normalize_email`."""
        return value.strip(_COVERED_WHITESPACE)


# Plain, non-unique index for the "list a user's saved searches" query — not
# a uniqueness/correctness requirement, so not part of __table_args__ above;
# a user may have any number of saved searches, including duplicate names.
Index("ix_saved_searches_user_id", SavedSearch.user_id)
