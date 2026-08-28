import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base
from app.normalization.company import normalize_domain

# Same four-character whitespace set as every other trim-only column in this
# project (`User._COVERED_WHITESPACE`, `SavedSearchLocation._COVERED_WHITESPACE`,
# etc.): space, tab, line feed, carriage return.
_COVERED_WHITESPACE = " \t\n\r"

# PostgreSQL expression for `normalized_name`'s generated column (see below):
# trim `_COVERED_WHITESPACE`, collapse any remaining internal run of that same
# four-character set to one ordinary space, then lowercase. Built with `E''`
# string literals the same way this project's CHECK constraints already are,
# so the pattern's tab/newline/carriage-return characters are real control
# characters, not the two-character sequences `\t`/`\n`/`\r` would be inside
# a plain quoted string.
_NORMALIZED_NAME_EXPRESSION = (
    r"lower(regexp_replace(trim(both E'\t\n\r ' from name), E'[\t\n\r ]+', ' ', 'g'))"
)


class Company(Base):
    """Deduplicated employer identity (docs/DATA_MODEL.md's `companies`
    section). Company identity resolution is deliberately not "solved" by a
    single unique constraint: `domain` is the one signal strong enough to
    enforce at the database level (via a case-insensitive, NULL-safe unique
    index); `normalized_name` is lookup-only, with no uniqueness, because
    company names collide too often for a name-only match to be safe.
    `duplicate_of_company_id` is schema reserved for a future (post-MVP)
    manual reconciliation workflow — nothing in Phase 1-6 populates or
    enforces it.

    `domain` is always stored pre-normalized by
    `app.normalization.company.normalize_domain()`, which never raises: a
    domain that can't be parsed into a valid hostname is stored as `NULL`,
    the same representation already used for "unknown" elsewhere in this
    schema.
    """

    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # A PostgreSQL `GENERATED ALWAYS AS (...) STORED` column, not an
    # independently writable field kept in sync by an ORM validator — a
    # validator-maintained mirror column can be bypassed by direct SQL or
    # bulk operations, silently storing a `name`/`normalized_name` pair that
    # disagree. Generating it in the database makes that impossible; see
    # `_NORMALIZED_NAME_EXPRESSION` above for the exact algorithm.
    normalized_name: Mapped[str] = mapped_column(
        Text,
        Computed(_NORMALIZED_NAME_EXPRESSION, persisted=True),
        nullable=False,
    )
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    career_page_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of_company_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
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
        CheckConstraint(r"name = trim(both E'\t\n\r ' from name)", name="name_normalized"),
        CheckConstraint(r"trim(both E'\t\n\r ' from name) <> ''", name="name_not_empty"),
        # NULL-safe: these three columns are nullable, so their normalization
        # CHECKs only constrain a non-NULL value — direct SQL still can't
        # store an empty, whitespace-only, or whitespace-wrapped value.
        CheckConstraint(
            r"homepage_url IS NULL OR homepage_url = trim(both E'\t\n\r ' from homepage_url)",
            name="homepage_url_normalized",
        ),
        CheckConstraint(
            r"homepage_url IS NULL OR trim(both E'\t\n\r ' from homepage_url) <> ''",
            name="homepage_url_not_empty",
        ),
        CheckConstraint(
            r"career_page_url IS NULL OR "
            r"career_page_url = trim(both E'\t\n\r ' from career_page_url)",
            name="career_page_url_normalized",
        ),
        CheckConstraint(
            r"career_page_url IS NULL OR trim(both E'\t\n\r ' from career_page_url) <> ''",
            name="career_page_url_not_empty",
        ),
        CheckConstraint(
            r"industry IS NULL OR industry = trim(both E'\t\n\r ' from industry)",
            name="industry_normalized",
        ),
        CheckConstraint(
            r"industry IS NULL OR trim(both E'\t\n\r ' from industry) <> ''",
            name="industry_not_empty",
        ),
        # A company cannot be recorded as its own duplicate. This prevents
        # only direct self-reference; a longer duplicate cycle (A -> B -> A)
        # is a future reconciliation-workflow responsibility, not something
        # Phase 1 populates or enforces at all.
        CheckConstraint(
            "duplicate_of_company_id IS NULL OR duplicate_of_company_id <> id",
            name="duplicate_of_company_id_not_self",
        ),
    )

    @validates("name")
    def _normalize_name(self, _key: str, value: str) -> str:
        """Trim `_COVERED_WHITESPACE` before the row ever reaches the
        database — case is preserved. `normalized_name` is derived from the
        stored value by PostgreSQL itself (see `normalized_name` above), not
        by this validator."""
        return value.strip(_COVERED_WHITESPACE)

    @validates("domain")
    def _normalize_domain(self, _key: str, value: str | None) -> str | None:
        """Delegates entirely to `normalize_domain()` — see
        `app.normalization.company` for the full algorithm. Never raises;
        unparseable input becomes `NULL`, same as an explicitly-unknown
        domain."""
        return normalize_domain(value)

    @validates("homepage_url", "career_page_url", "industry")
    def _normalize_nullable_text(self, _key: str, value: str | None) -> str | None:
        """Trims `_COVERED_WHITESPACE` and converts a covered-whitespace-only
        value to `None` rather than failing ingestion — these fields are
        optional, so a blank value is "not provided", not invalid input."""
        if value is None:
            return None
        trimmed = value.strip(_COVERED_WHITESPACE)
        return trimmed or None


# A functional/expression unique index can't be expressed as a table-level
# UniqueConstraint (those only cover plain columns) — an Index is the only
# way to enforce case-insensitive uniqueness while still storing and
# returning the original case. `postgresql_where` makes it partial: multiple
# companies with domain IS NULL coexist freely, since NULL means "unknown",
# not "empty string" or a value that could collide with another NULL.
Index(
    "uq_companies_domain_lower",
    func.lower(Company.domain),
    unique=True,
    postgresql_where=Company.domain.isnot(None),
)

# Plain, non-unique lookup index — see the conservative-collision rationale
# in this module's docstring: normalized_name deliberately has no uniqueness.
Index("ix_companies_normalized_name", Company.normalized_name)
