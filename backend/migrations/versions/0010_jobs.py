"""add jobs table

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-28

Eighth Phase 1 domain table (docs/DATA_MODEL.md's `jobs` section, §20) — the
canonical, resolved job record. Class H per docs/LLM_WORKFLOW.md: the first
migration to actually exercise `ON DELETE RESTRICT`, and a large canonical
record with many downstream dependencies, even though identity/dedup logic
itself is out of scope (that lives entirely on `job_occurrences`, a separate,
later slice — this table declares no UNIQUE constraint of its own).

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `company_id` is **nullable**: `DiscoveredJob.company` is explicitly
  nullable in docs/ARCHITECTURE.md, and requiring a resolved company would
  force ingestion to either reject an otherwise-valid job or manufacture a
  fake "unknown company" row. `ON DELETE RESTRICT` still applies whenever
  `company_id` is non-null. A plain, non-unique index supports the "list a
  company's jobs" query.
- `remote_type` is nullable text restricted by `CHECK` to exactly
  `remote`/`hybrid`/`onsite` when non-null — no `'unknown'` sentinel is
  stored; `NULL` means unknown, consistent with this schema's global
  NULL-means-unknown convention (correcting docs/DATA_MODEL.md's previously
  documented 4-value enum, which contradicted that convention).
- `salary_period` is nullable text restricted by `CHECK` to exactly
  `hourly`/`daily`/`monthly`/`annual` when non-null.
- `compensation_explicit` is a nullable boolean with no server default —
  `NULL` means not yet classified.
- `duplicate_group_id` is **omitted entirely** from this migration:
  `duplicate_groups` is a Phase 6 table that does not exist yet, so no FK
  could be declared against it now. It will be added, with its FK, in a
  Phase 6 migration alongside `duplicate_groups` itself.
- `first_seen_at`/`last_seen_at` are NOT NULL with **no** server default —
  they describe observation time, not row-creation time, so nothing may
  silently substitute `now()` for an omitted value. A `CHECK` requires
  `first_seen_at <= last_seen_at`.
- Every other nullable free-text column (see the full list in
  `app/db/models/job.py`'s `_NULLABLE_TEXT_COLUMNS`) gets the established
  NULL-safe trim/non-empty `CHECK` pair — no URL-format validation, no new
  enums beyond the two already documented above.
- Numeric ranges (`salary_min`/`salary_max`, `annualized_salary_min`/`max`,
  `years_experience_min`/`max`) each get a non-negative `CHECK` plus a
  `min <= max` `CHECK` when both are non-null, matching the established
  `candidate_profiles`/`saved_searches` pattern.
- `latitude`/`longitude` get the established coordinate-range and
  both-or-neither `CHECK`s, identical to `saved_search_locations`.
- `field_provenance` is nullable `jsonb`, restricted by `CHECK` to a
  top-level JSON object when non-null, matching
  `saved_searches.enabled_sources`/`scoring_weights`.
- `created_at`/`updated_at` follow the established global convention.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

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


def _trim_not_empty_checks(column: str) -> tuple[sa.CheckConstraint, sa.CheckConstraint]:
    return (
        sa.CheckConstraint(
            rf"{column} IS NULL OR {column} = trim(both E'\t\n\r ' from {column})",
            name=op.f(f"ck_jobs_{column}_normalized"),
        ),
        sa.CheckConstraint(
            rf"{column} IS NULL OR trim(both E'\t\n\r ' from {column}) <> ''",
            name=op.f(f"ck_jobs_{column}_not_empty"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=True),
        sa.Column("requisition_id", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("preferred_apply_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("normalized_title", sa.Text(), nullable=True),
        sa.Column("job_family", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("team", sa.Text(), nullable=True),
        sa.Column("description_raw", sa.Text(), nullable=True),
        sa.Column("description_clean", sa.Text(), nullable=True),
        sa.Column("location_raw", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("postal_code", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(), nullable=True),
        sa.Column("longitude", sa.Numeric(), nullable=True),
        sa.Column("remote_type", sa.Text(), nullable=True),
        sa.Column("employment_type", sa.Text(), nullable=True),
        sa.Column("seniority", sa.Text(), nullable=True),
        sa.Column("contract_type", sa.Text(), nullable=True),
        sa.Column("shift", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.Text(), nullable=True),
        sa.Column("salary_period", sa.Text(), nullable=True),
        sa.Column("annualized_salary_min", sa.Integer(), nullable=True),
        sa.Column("annualized_salary_max", sa.Integer(), nullable=True),
        sa.Column("compensation_text", sa.Text(), nullable=True),
        sa.Column("compensation_explicit", sa.Boolean(), nullable=True),
        sa.Column("years_experience_min", sa.Integer(), nullable=True),
        sa.Column("years_experience_max", sa.Integer(), nullable=True),
        sa.Column("education_requirement", sa.Text(), nullable=True),
        sa.Column("certifications", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("clearance_requirement", sa.Text(), nullable=True),
        sa.Column("visa_sponsorship_status", sa.Text(), nullable=True),
        sa.Column("travel_requirement", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("application_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("field_provenance", postgresql.JSONB(), nullable=True),
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
        *(check for column in _NULLABLE_TEXT_COLUMNS for check in _trim_not_empty_checks(column)),
        sa.CheckConstraint(
            "remote_type IS NULL OR remote_type IN ('remote', 'hybrid', 'onsite')",
            name=op.f("ck_jobs_remote_type_valid"),
        ),
        sa.CheckConstraint(
            "salary_period IS NULL OR salary_period IN ('hourly', 'daily', 'monthly', 'annual')",
            name=op.f("ck_jobs_salary_period_valid"),
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_min >= 0", name=op.f("ck_jobs_salary_min_non_negative")
        ),
        sa.CheckConstraint(
            "salary_max IS NULL OR salary_max >= 0", name=op.f("ck_jobs_salary_max_non_negative")
        ),
        sa.CheckConstraint(
            "salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max",
            name=op.f("ck_jobs_salary_min_le_max"),
        ),
        sa.CheckConstraint(
            "annualized_salary_min IS NULL OR annualized_salary_min >= 0",
            name=op.f("ck_jobs_annualized_salary_min_non_negative"),
        ),
        sa.CheckConstraint(
            "annualized_salary_max IS NULL OR annualized_salary_max >= 0",
            name=op.f("ck_jobs_annualized_salary_max_non_negative"),
        ),
        sa.CheckConstraint(
            "annualized_salary_min IS NULL OR annualized_salary_max IS NULL "
            "OR annualized_salary_min <= annualized_salary_max",
            name=op.f("ck_jobs_annualized_salary_min_le_max"),
        ),
        sa.CheckConstraint(
            "years_experience_min IS NULL OR years_experience_min >= 0",
            name=op.f("ck_jobs_years_experience_min_non_negative"),
        ),
        sa.CheckConstraint(
            "years_experience_max IS NULL OR years_experience_max >= 0",
            name=op.f("ck_jobs_years_experience_max_non_negative"),
        ),
        sa.CheckConstraint(
            "years_experience_min IS NULL OR years_experience_max IS NULL "
            "OR years_experience_min <= years_experience_max",
            name=op.f("ck_jobs_years_experience_min_le_max"),
        ),
        sa.CheckConstraint(
            "latitude IS NULL OR latitude BETWEEN -90 AND 90",
            name=op.f("ck_jobs_latitude_in_range"),
        ),
        sa.CheckConstraint(
            "longitude IS NULL OR longitude BETWEEN -180 AND 180",
            name=op.f("ck_jobs_longitude_in_range"),
        ),
        sa.CheckConstraint(
            "(latitude IS NULL) = (longitude IS NULL)",
            name=op.f("ck_jobs_latitude_longitude_both_or_neither"),
        ),
        sa.CheckConstraint(
            "field_provenance IS NULL OR jsonb_typeof(field_provenance) = 'object'",
            name=op.f("ck_jobs_field_provenance_is_object"),
        ),
        sa.CheckConstraint(
            "first_seen_at <= last_seen_at",
            name=op.f("ck_jobs_first_seen_at_le_last_seen_at"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name=op.f("fk_jobs_company_id_companies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_index("ix_jobs_company_id", "jobs", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_company_id", table_name="jobs")
    op.drop_table("jobs")
