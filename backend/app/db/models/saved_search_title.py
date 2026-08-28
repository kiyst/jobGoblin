import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

# Same four-character whitespace set as `CandidateSkill._COVERED_WHITESPACE` /
# `SavedSearch._COVERED_WHITESPACE`: space, tab, line feed, carriage return.
# `title` is trim-only, like `skill`/`name` — never lowercased; case-insensitive
# matching is handled separately by the functional unique index below.
_COVERED_WHITESPACE = " \t\n\r"


class SavedSearchTitle(Base):
    """One title/alias for a `saved_searches` row
    (docs/DATA_MODEL.md §saved_search_titles). Split out rather than an array
    column on `saved_searches` because titles need per-entry alias expansion
    against `taxonomy/titles.yaml` in Phase 3, and because a title
    independently carries "this is the primary title" vs. "this is an
    acceptable alias" via `is_primary`.

    `is_primary` defaults to `false` and at most one title per saved search
    may be `true` (enforced by the partial unique index below) — but zero
    primary titles is a valid, unconstrained state at the database level;
    enforcing "exactly one" would need a trigger, which is deliberately not
    added here.
    """

    __tablename__ = "saved_search_titles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    saved_search_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("saved_searches.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
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
            r"title = trim(both E'\t\n\r ' from title)",
            name="title_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from title) <> ''",
            name="title_not_empty",
        ),
    )

    @validates("title")
    def _normalize_title(self, _key: str, value: str) -> str:
        """Trim `_COVERED_WHITESPACE` before the row ever reaches the
        database — case is preserved, unlike `User._normalize_email`."""
        return value.strip(_COVERED_WHITESPACE)


# A functional/expression unique index can't be expressed as a table-level
# UniqueConstraint (those only cover plain columns) — an Index is the only
# way to enforce case-insensitive, per-search uniqueness while still storing
# and returning the original case.
Index(
    "uq_saved_search_titles_search_id_title_lower",
    SavedSearchTitle.saved_search_id,
    func.lower(SavedSearchTitle.title),
    unique=True,
)

# Partial unique index: at most one primary title per saved search. Zero
# primary titles is unconstrained — this index only rejects a *second* true
# row for the same saved_search_id, never requires a first one.
Index(
    "uq_saved_search_titles_search_id_primary",
    SavedSearchTitle.saved_search_id,
    unique=True,
    postgresql_where=SavedSearchTitle.is_primary,
)
