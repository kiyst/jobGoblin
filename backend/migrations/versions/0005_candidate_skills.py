"""add candidate_skills table

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24

Third Phase 1 domain table (docs/DATA_MODEL.md's `candidate_skills`
section). Normalized child table of `candidate_profiles` (`ON DELETE
CASCADE`) rather than an array column, so each skill can carry its own
`category` and `priority`.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `skill` is normalized the same way `users.email` is (see
  `app/db/models/user.py` and migration `0003`): trimmed of exactly the
  four-character whitespace set (space, tab, LF, CR), never empty after
  trim, and the trim invariant is enforced by database `CHECK`s in addition
  to an ORM `@validates` — but, unlike `email`, `skill` is **not**
  lowercased; its case is preserved for display.
- Case-insensitive, profile-scoped uniqueness is enforced by a functional
  unique index on `(candidate_profile_id, lower(skill))`, the same pattern
  `users` uses for `lower(email)` — a plain `UNIQUE` constraint can't
  express `lower(skill)`.
- `category` is nullable free text with no enum `CHECK` (the documented
  examples — language/framework/cloud/tool/etc. — are illustrative, not a
  closed set).
- `priority` is not null (this table's own convention: only `category` is
  documented as nullable) and restricted by `CHECK` to `must_have` /
  `preferred`.
- `created_at`/`updated_at` are added as non-null `timestamptz` columns with
  `server_default now()`, consistent with every other implemented table,
  even though the column list in `docs/DATA_MODEL.md`'s `candidate_skills`
  section omitted them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_skills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_profile_id", sa.Uuid(), nullable=False),
        sa.Column("skill", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            r"skill = trim(both E'\t\n\r ' from skill)",
            name=op.f("ck_candidate_skills_skill_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from skill) <> ''",
            name=op.f("ck_candidate_skills_skill_not_empty"),
        ),
        sa.CheckConstraint(
            "priority IN ('must_have', 'preferred')",
            name=op.f("ck_candidate_skills_priority_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_profile_id"],
            ["candidate_profiles.id"],
            name=op.f("fk_candidate_skills_candidate_profile_id_candidate_profiles"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_skills")),
    )
    # Expression/functional unique index — a UNIQUE table constraint can only
    # cover plain columns, not lower(skill), so an index is the only way to
    # enforce case-insensitive, per-profile uniqueness while still storing
    # and returning the original case.
    op.create_index(
        "uq_candidate_skills_profile_id_skill_lower",
        "candidate_skills",
        ["candidate_profile_id", sa.text("lower(skill)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_candidate_skills_profile_id_skill_lower", table_name="candidate_skills")
    op.drop_table("candidate_skills")
