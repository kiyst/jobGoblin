"""add candidate_profiles table

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-24

Second Phase 1 domain table (docs/DATA_MODEL.md's `candidate_profiles`
section). One-to-one with `users` for now — `user_id` is a non-null,
`ON DELETE CASCADE` foreign key that is also UNIQUE.

Three product rules were not determined by existing documentation and were
resolved by explicit approval before this migration was written (not
inferred silently):

- The five `text[]` columns (`target_role_families`, `certifications`,
  `preferred_industries`, `excluded_industries`, `preferred_locations`) are
  nullable with no server default. NULL means the candidate has never
  specified that field; a future write path may still store an empty array
  to mean "explicitly specified as none" — a distinct state this migration
  does not populate but leaves room for.
- `years_experience`, `salary_expectation_min`, and `salary_expectation_max`
  each have a `CHECK` requiring the value be NULL or >= 0.
- `salary_expectation_min` and `salary_expectation_max` have an additional
  `CHECK` requiring `salary_expectation_min <= salary_expectation_max`
  whenever both are non-null.

`remote_preference` is NOT NULL (unlike the array/salary/experience columns
above, its column note in docs/DATA_MODEL.md does not say "nullable",
matching this table's own convention of only marking nullable columns as
such) and is restricted by CHECK to the four values documented: `remote`,
`hybrid`, `onsite`, `no_preference`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("target_role_families", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("education", sa.Text(), nullable=True),
        sa.Column("certifications", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("clearance", sa.Text(), nullable=True),
        sa.Column("preferred_industries", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("excluded_industries", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("preferred_locations", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("relocation_willingness", sa.Boolean(), nullable=True),
        sa.Column("remote_preference", sa.Text(), nullable=False),
        sa.Column("salary_expectation_min", sa.Integer(), nullable=True),
        sa.Column("salary_expectation_max", sa.Integer(), nullable=True),
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
            "remote_preference IN ('remote', 'hybrid', 'onsite', 'no_preference')",
            name=op.f("ck_candidate_profiles_remote_preference_valid"),
        ),
        sa.CheckConstraint(
            "years_experience IS NULL OR years_experience >= 0",
            name=op.f("ck_candidate_profiles_years_experience_non_negative"),
        ),
        sa.CheckConstraint(
            "salary_expectation_min IS NULL OR salary_expectation_min >= 0",
            name=op.f("ck_candidate_profiles_salary_expectation_min_non_negative"),
        ),
        sa.CheckConstraint(
            "salary_expectation_max IS NULL OR salary_expectation_max >= 0",
            name=op.f("ck_candidate_profiles_salary_expectation_max_non_negative"),
        ),
        sa.CheckConstraint(
            "salary_expectation_min IS NULL OR salary_expectation_max IS NULL "
            "OR salary_expectation_min <= salary_expectation_max",
            name=op.f("ck_candidate_profiles_salary_expectation_min_le_max"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_candidate_profiles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_profiles")),
        sa.UniqueConstraint("user_id", name=op.f("uq_candidate_profiles_user_id")),
    )


def downgrade() -> None:
    op.drop_table("candidate_profiles")
