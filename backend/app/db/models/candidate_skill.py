import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

PRIORITIES = ("must_have", "preferred")

# Same four-character whitespace set as `User._COVERED_WHITESPACE`
# (app/db/models/user.py): space, tab, line feed, carriage return. Unlike
# `email`, `skill` is case-preserving — normalization here is whitespace-only,
# never lowercasing; case-insensitive matching is handled separately by the
# `lower(skill)` unique index below, not by mutating the stored value.
_COVERED_WHITESPACE = " \t\n\r"


class CandidateSkill(Base):
    """A single skill entry for a `candidate_profiles` row
    (docs/DATA_MODEL.md §candidate_skills). Normalized child table rather
    than an array column so each skill can carry its own `category` and
    `priority`, and so Phase 3 taxonomy matching has a row to attach to.

    `skill` is deliberately not lowercased on write — it is raw or
    already-canonical text (taxonomy resolution is a Phase 3 concern) and its
    case is preserved for display. Case-insensitive duplicate prevention is
    enforced separately by the functional unique index on
    `(candidate_profile_id, lower(skill))`.
    """

    __tablename__ = "candidate_skills"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
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
        # just the `_normalize_skill` validator below — same reasoning as
        # `users.email` (see app/db/models/user.py).
        CheckConstraint(
            r"skill = trim(both E'\t\n\r ' from skill)",
            name="skill_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from skill) <> ''",
            name="skill_not_empty",
        ),
        CheckConstraint(
            "priority IN ('must_have', 'preferred')",
            name="priority_valid",
        ),
    )

    @validates("skill")
    def _normalize_skill(self, _key: str, value: str) -> str:
        """Trim `_COVERED_WHITESPACE` before the row ever reaches the
        database — deliberately does not lowercase or otherwise touch case,
        unlike `User._normalize_email`. The CHECK constraints above enforce
        this same trim, including against writes that bypass the ORM."""
        return value.strip(_COVERED_WHITESPACE)


# A functional/expression unique index can't be expressed as a table-level
# UniqueConstraint (those only cover plain columns) — an Index is the only
# way to enforce case-insensitive uniqueness on lower(skill) while still
# storing and returning the original case.
Index(
    "uq_candidate_skills_profile_id_skill_lower",
    CandidateSkill.candidate_profile_id,
    func.lower(CandidateSkill.skill),
    unique=True,
)
