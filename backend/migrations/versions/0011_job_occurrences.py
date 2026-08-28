"""add job_occurrences table

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-28

Ninth Phase 1 domain table (docs/DATA_MODEL.md's `job_occurrences` section,
§18; ADR 0004). Class H per docs/LLM_WORKFLOW.md: this is the table the
project's deterministic identity-resolution scheme is built on — its three
partial unique indexes below implement ADR 0004's scoped natural key
directly. The actual match-precedence application logic (querying by these
indexes in order, deciding new-vs-existing-occurrence, writing
`identity_conflicts` rows) is Phase 2+ ingestion code — Phase 2's offline
fixture pipeline is the first writer/user of this persistence and
deterministic-identity path; Phase 4 introduces the first live ATS
provider to reuse it. Out of scope here.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `provider`/`source` are required canonical identifiers: lowercased and
  trimmed by the ORM, with a database `CHECK` requiring an already trimmed,
  lowercase, non-empty value — casing/whitespace differences must never let
  two logically-identical rows bypass the natural-key indexes below. A
  second `CHECK` restricts both to a documented lowercase ASCII slug
  grammar (`^[a-z0-9][a-z0-9._-]*$`) so Python's and PostgreSQL's `lower()`
  can never disagree on stored values (the two implementations diverge for
  arbitrary Unicode input, which this grammar excludes by construction).
  `source_tenant_id`/`source_job_id`/`requisition_id_raw` are externally
  assigned identifiers and are deliberately **not** case-folded or
  slug-restricted, only trimmed (NULL-safe).
- `source_url_normalized`/`canonical_url_normalized` are **not** derived by
  this migration/model from `source_url`/`canonical_url` — the database
  cannot guarantee a Python function's output agrees with its raw input,
  so no such guarantee is claimed here. `app.normalization.url.
  normalize_url()` (new in this slice; ADR 0004) is a pure function
  callers must call themselves and pass the result in explicitly; Phase
  2's persistence path is responsible for calling it before comparison/
  write. A `CHECK` does enforce the one relationship the database *can*
  verify: `canonical_url IS NULL` implies `canonical_url_normalized IS
  NULL` (a non-null `canonical_url` may still legitimately normalize to
  `NULL` if malformed, so this is a one-way implication, not equivalence).
- `first_seen_at`/`last_seen_at` are NOT NULL with **no** server default
  and no ORM `onupdate` — they describe observation time, not row-
  creation/update time; a `CHECK` requires `first_seen_at <= last_seen_at`.
- `applicant_count` gets the established non-negative `CHECK`. `is_active`
  is NOT NULL with `server_default true`, matching `saved_searches.
  is_active`'s established pattern. `created_at`/`updated_at` follow the
  established global convention.
- Three partial unique indexes implement ADR 0004's NULL-safe scoped
  natural key (a single combined index cannot express this — see ADR 0004
  and the model's own docstring for the exact NULL-safety bug this fixes):
  tenant-scoped sources, no-tenant sources, and a fallback normalized-URL
  key when no stable per-posting ID exists at all. Plus three lookup
  indexes for identity-resolution match-precedence steps 2/3 and the
  common "active occurrences for this job, freshest first" query.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NULLABLE_TEXT_COLUMNS = (
    "source_tenant_id",
    "source_job_id",
    "requisition_id_raw",
    "source_url_normalized",
    "apply_url",
    "canonical_url",
    "canonical_url_normalized",
    "applicant_count_text",
)


def _trim_not_empty_checks(column: str) -> tuple[sa.CheckConstraint, sa.CheckConstraint]:
    return (
        sa.CheckConstraint(
            rf"{column} IS NULL OR {column} = trim(both E'\t\n\r ' from {column})",
            name=op.f(f"ck_job_occurrences_{column}_normalized"),
        ),
        sa.CheckConstraint(
            rf"{column} IS NULL OR trim(both E'\t\n\r ' from {column}) <> ''",
            name=op.f(f"ck_job_occurrences_{column}_not_empty"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "job_occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_tenant_id", sa.Text(), nullable=True),
        sa.Column("source_job_id", sa.Text(), nullable=True),
        sa.Column("requisition_id_raw", sa.Text(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_url_normalized", sa.Text(), nullable=True),
        sa.Column("apply_url", sa.Text(), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("canonical_url_normalized", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applicant_count", sa.Integer(), nullable=True),
        sa.Column("applicant_count_text", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            r"provider = lower(trim(both E'\t\n\r ' from provider))",
            name=op.f("ck_job_occurrences_provider_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from provider) <> ''",
            name=op.f("ck_job_occurrences_provider_not_empty"),
        ),
        sa.CheckConstraint(
            r"provider ~ '^[a-z0-9][a-z0-9._-]*$'",
            name=op.f("ck_job_occurrences_provider_slug_format"),
        ),
        sa.CheckConstraint(
            r"source = lower(trim(both E'\t\n\r ' from source))",
            name=op.f("ck_job_occurrences_source_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from source) <> ''",
            name=op.f("ck_job_occurrences_source_not_empty"),
        ),
        sa.CheckConstraint(
            r"source ~ '^[a-z0-9][a-z0-9._-]*$'",
            name=op.f("ck_job_occurrences_source_slug_format"),
        ),
        sa.CheckConstraint(
            r"source_url = trim(both E'\t\n\r ' from source_url)",
            name=op.f("ck_job_occurrences_source_url_normalized_check"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from source_url) <> ''",
            name=op.f("ck_job_occurrences_source_url_not_empty"),
        ),
        *(check for column in _NULLABLE_TEXT_COLUMNS for check in _trim_not_empty_checks(column)),
        sa.CheckConstraint(
            "canonical_url IS NOT NULL OR canonical_url_normalized IS NULL",
            name=op.f("ck_job_occurrences_canonical_url_normalized_requires_url"),
        ),
        sa.CheckConstraint(
            "applicant_count IS NULL OR applicant_count >= 0",
            name=op.f("ck_job_occurrences_applicant_count_non_negative"),
        ),
        sa.CheckConstraint(
            "first_seen_at <= last_seen_at",
            name=op.f("ck_job_occurrences_first_seen_at_le_last_seen_at"),
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_job_occurrences_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_occurrences")),
    )
    op.create_index(
        "uq_job_occurrences_tenant_natural_key",
        "job_occurrences",
        ["provider", "source", "source_tenant_id", "source_job_id"],
        unique=True,
        postgresql_where=sa.text("source_job_id IS NOT NULL AND source_tenant_id IS NOT NULL"),
    )
    op.create_index(
        "uq_job_occurrences_no_tenant_natural_key",
        "job_occurrences",
        ["provider", "source", "source_job_id"],
        unique=True,
        postgresql_where=sa.text("source_job_id IS NOT NULL AND source_tenant_id IS NULL"),
    )
    op.create_index(
        "uq_job_occurrences_fallback_url_key",
        "job_occurrences",
        ["provider", "source", "source_url_normalized"],
        unique=True,
        postgresql_where=sa.text("source_job_id IS NULL"),
    )
    op.create_index(
        "ix_job_occurrences_canonical_url_normalized",
        "job_occurrences",
        ["canonical_url_normalized"],
    )
    op.create_index(
        "ix_job_occurrences_tenant_requisition_lookup",
        "job_occurrences",
        ["provider", "source", "source_tenant_id", "requisition_id_raw"],
    )
    op.create_index(
        "ix_job_occurrences_job_active_last_seen",
        "job_occurrences",
        ["job_id", "is_active", sa.text("last_seen_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_job_occurrences_job_active_last_seen", table_name="job_occurrences")
    op.drop_index("ix_job_occurrences_tenant_requisition_lookup", table_name="job_occurrences")
    op.drop_index("ix_job_occurrences_canonical_url_normalized", table_name="job_occurrences")
    op.drop_index("uq_job_occurrences_fallback_url_key", table_name="job_occurrences")
    op.drop_index("uq_job_occurrences_no_tenant_natural_key", table_name="job_occurrences")
    op.drop_index("uq_job_occurrences_tenant_natural_key", table_name="job_occurrences")
    op.drop_table("job_occurrences")
