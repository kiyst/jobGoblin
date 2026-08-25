"""add saved_searches table

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24

Fourth Phase 1 domain table (docs/DATA_MODEL.md's `saved_searches` section).
Only the parent table — `saved_search_titles` and `saved_search_locations`
remain separate future slices, same incremental pattern as
`candidate_profiles` -> `candidate_skills`.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- Every `text[]` column is nullable with no server default (NULL means
  "never specified"), same convention as `candidate_profiles`.
- `name` is normalized the same way `candidate_skills.skill` is: trimmed of
  the four-character whitespace set (space, tab, LF, CR), enforced by
  database `CHECK`s in addition to an ORM `@validates` — but, unlike
  `skill`, `name` has no uniqueness requirement, so there is no functional
  unique index here.
- `remote_rules` and `polling_schedule` are not null and `CHECK`-restricted
  to their documented enum values.
- `salary_floor`, `preferred_salary`, and `recency_limit_hours` each have a
  `CHECK` requiring the value be NULL or >= 0, plus an additional `CHECK`
  requiring `salary_floor <= preferred_salary` whenever both are non-null —
  the same pattern as `candidate_profiles`' salary fields.
- `radius_miles` is a deliberately **unconstrained** `numeric` column: no
  precision/scale and no non-negative `CHECK`, unlike the integer numeric
  fields above.
- `enabled_sources` and `scoring_weights` are `jsonb`, nullable, each
  restricted by a `CHECK` requiring the stored value be a top-level JSON
  *object* when non-null (`jsonb_typeof(...) = 'object'`) — deeper shape
  (e.g. which provider/source keys `enabled_sources` may contain) is a
  Phase 2 `QueryPlanner`-time concern (docs/ARCHITECTURE.md SS6.5-6.6), not a
  Phase 1 database constraint.
- `created_at`/`updated_at` are added as non-null `timestamptz` columns with
  `server_default now()`, consistent with every other implemented table,
  even though the column list in `docs/DATA_MODEL.md`'s `saved_searches`
  section omitted them (the same gap already fixed for `users` and
  `candidate_skills`).
- `is_active` is not null with `server_default true`, per its documented
  default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_ARRAY_COLUMNS = (
    "excluded_titles",
    "industries",
    "employment_types",
    "seniority",
    "must_have_skills",
    "preferred_skills",
    "excluded_keywords",
    "preferred_companies",
    "excluded_companies",
    "enabled_providers",
)


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        *(sa.Column(name, postgresql.ARRAY(sa.Text()), nullable=True) for name in _ARRAY_COLUMNS),
        sa.Column("radius_miles", sa.Numeric(), nullable=True),
        sa.Column("remote_rules", sa.Text(), nullable=False),
        sa.Column("salary_floor", sa.Integer(), nullable=True),
        sa.Column("preferred_salary", sa.Integer(), nullable=True),
        sa.Column("recency_limit_hours", sa.Integer(), nullable=True),
        sa.Column("enabled_sources", postgresql.JSONB(), nullable=True),
        sa.Column("polling_schedule", sa.Text(), nullable=False),
        sa.Column("scoring_weights", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
            r"name = trim(both E'\t\n\r ' from name)",
            name=op.f("ck_saved_searches_name_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from name) <> ''",
            name=op.f("ck_saved_searches_name_not_empty"),
        ),
        sa.CheckConstraint(
            "remote_rules IN ('remote_only', 'hybrid_ok', 'onsite_ok', 'any')",
            name=op.f("ck_saved_searches_remote_rules_valid"),
        ),
        sa.CheckConstraint(
            "polling_schedule IN ('manual', 'hourly', 'daily', 'weekly')",
            name=op.f("ck_saved_searches_polling_schedule_valid"),
        ),
        sa.CheckConstraint(
            "salary_floor IS NULL OR salary_floor >= 0",
            name=op.f("ck_saved_searches_salary_floor_non_negative"),
        ),
        sa.CheckConstraint(
            "preferred_salary IS NULL OR preferred_salary >= 0",
            name=op.f("ck_saved_searches_preferred_salary_non_negative"),
        ),
        sa.CheckConstraint(
            "recency_limit_hours IS NULL OR recency_limit_hours >= 0",
            name=op.f("ck_saved_searches_recency_limit_hours_non_negative"),
        ),
        sa.CheckConstraint(
            "salary_floor IS NULL OR preferred_salary IS NULL "
            "OR salary_floor <= preferred_salary",
            name=op.f("ck_saved_searches_salary_floor_le_preferred_salary"),
        ),
        sa.CheckConstraint(
            "enabled_sources IS NULL OR jsonb_typeof(enabled_sources) = 'object'",
            name=op.f("ck_saved_searches_enabled_sources_is_object"),
        ),
        sa.CheckConstraint(
            "scoring_weights IS NULL OR jsonb_typeof(scoring_weights) = 'object'",
            name=op.f("ck_saved_searches_scoring_weights_is_object"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_saved_searches_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_searches")),
    )
    # Plain, non-unique index for the "list a user's saved searches" query —
    # not a uniqueness/correctness requirement, see app/db/models/saved_search.py.
    op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_searches_user_id", table_name="saved_searches")
    op.drop_table("saved_searches")
