import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

# The exact whitespace set this project normalizes: space, tab, line feed,
# carriage return (ASCII 0x20/0x09/0x0A/0x0D). Deliberately narrower than
# Python's bare `str.strip()`, which also strips other Unicode whitespace
# (e.g. non-breaking space) that PostgreSQL's `trim()` does not recognize —
# using the bare form here previously let a value like "\tperson@x.com\t"
# through, because Postgres's default `trim(email)` only strips plain spaces,
# not tabs/newlines, while the Python side stripped them. Both sides below use
# exactly this same four-character set, so they can no longer disagree. If
# this set is ever revised, both `_COVERED_WHITESPACE` and the CHECK
# constraints' SQL string below must be updated together.
_COVERED_WHITESPACE = " \t\n\r"


class User(Base):
    """A single account. Phase 1 slice: identity only.

    No authentication, sessions, or roles exist yet — see
    docs/ROADMAP.md and docs/PHASE_RISK_CHECKLIST.md's Phase 1 scope. Every
    other Phase 1 table's `user_id` FK points here.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # `Text`, not the default-mapped `String`/varchar — see docs/DATA_MODEL.md,
    # "email: text". Normalization (below) is what keeps this safe without a
    # length cap.
    email: Mapped[str] = mapped_column(Text, nullable=False)
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
        # The database is the authoritative backstop for both of these, not
        # just the `_normalize_email` validator below — see docs/DATA_MODEL.md.
        # `trim(both E'\t\n\r ' from email)` strips exactly `_COVERED_WHITESPACE`
        # above — same four characters, same set, on both sides. Postgres's
        # bare `trim(email)` (no explicit character list) only strips plain
        # spaces, which is what let whitespace-wrapped values through before.
        CheckConstraint(
            r"email = lower(trim(both E'\t\n\r ' from email))",
            name="email_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from email) <> ''",
            name="email_not_empty",
        ),
    )

    @validates("email")
    def _normalize_email(self, _key: str, value: str) -> str:
        """Trim `_COVERED_WHITESPACE` and lowercase before the row ever
        reaches the database.

        Deliberately does *not* attempt provider-specific transforms (dot-
        removal, plus-addressing, etc.) — see docs/DATA_MODEL.md. This is a
        convenience for the common path; the CHECK constraints above are what
        actually enforce it, including against writes that bypass the ORM —
        and they enforce exactly this same whitespace set, not Python's
        broader default `str.strip()`.
        """
        return value.strip(_COVERED_WHITESPACE).lower()


# A functional/expression unique index can't be expressed as a table-level
# UniqueConstraint (those only cover plain columns) — an Index is the only way
# to enforce uniqueness on lower(email) itself, so a case-different duplicate
# is rejected even though the stored value is already normalized.
Index("uq_users_email_lower", func.lower(User.email), unique=True)
