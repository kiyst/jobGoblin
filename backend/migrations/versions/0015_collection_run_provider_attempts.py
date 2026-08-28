"""add collection_run_provider_attempts table

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-28

Thirteenth Phase 1 domain table (docs/DATA_MODEL.md's `collection_run_
provider_attempts` section; ARCHITECTURE.md §9; ADR 0005). Class H per
docs/LLM_WORKFLOW.md: this table is the authoritative per-source telemetry
record feeding Phase 12's provider-health anomaly detection, is Phase 2's
second fixture-proof writer alongside `identity_conflicts`, and depends on
`collection_runs` (Phase 1's twelfth table). Phase 2's offline fixture
pipeline is the first writer; this slice only migrates the schema.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `collection_run_id` is NOT NULL with `ON DELETE CASCADE` — an attempt
  row has no independent meaning without its parent run, unlike this
  schema's audit-trail FKs (`raw_job_ingestions`, `identity_conflicts` x2,
  `collection_runs.saved_search_id`), which are all `SET NULL`. `ON DELETE
  CASCADE` is not new to this schema — `job_occurrences.job_id`,
  `candidate_skills.candidate_profile_id`, and the `saved_search_*` child
  tables already use it; only the parent-table identity differs here.
- `provider`/`source` are the same canonical identifiers as
  `job_occurrences`/`raw_job_ingestions`: lowercased/trimmed by the ORM,
  `CHECK`-restricted to an already-canonical, non-empty ASCII-slug value
  (`^[a-z0-9][a-z0-9._-]*$`).
- `status` is a plain `CHECK`-restricted enum (`running`/`completed`/
  `partial`/`failed`), no server default — fresh creation must explicitly
  supply `'running'`. A bidirectional lifecycle `CHECK` requires
  `completed_at IS NULL` for `running` and `completed_at IS NOT NULL` for
  every terminal status. A second `CHECK` requires `completed_at >=
  started_at` when both are set. `started_at` is NOT NULL with no server
  default, matching `collection_runs.started_at`/`raw_job_ingestions.
  fetched_at`'s treatment.
- `jobs_discovered`/`jobs_inserted`/`jobs_updated`/`retry_count` are NOT
  NULL, `server_default 0`, each with a non-negative `CHECK`.
  `rate_limited`/`incomplete_results` are NOT NULL booleans,
  `server_default false`, independent of each other and of `status` — no
  `CHECK` requires `incomplete_results = true` to imply or be implied by
  `status = 'partial'`; that mapping is established by Phase 2's
  application logic, not the database.
- `error_category` is nullable text, `CHECK`-restricted to exactly the 8
  values ARCHITECTURE.md §6.3's `ProviderErrorCategory` Python enum
  currently defines (`timeout`, `rate_limited`, `auth_error`, `blocked`,
  `parse_error`, `not_found`, `upstream_error`, `unknown`) — kept as a
  plain string column in Phase 1, not a native Postgres enum type, so a
  future addition is a single migration adding one CHECK value, not a
  type-alteration migration. Phase 2+ must keep this list synchronized
  with that Python enum by hand. No `CHECK` ties it to `status`.
  `error_message` is nullable, case-preserving free text: ORM-trimmed with
  a covered-whitespace-only value collapsed to `NULL` (the same treatment
  as `raw_job_ingestions.error_message`), with a matching NULL-safe
  trim/non-empty `CHECK` pair. Sanitizing it against secrets/tokens is an
  application-level responsibility, not proven by this `CHECK`.
- `created_at`/`updated_at` follow the established global convention.
- `UNIQUE (collection_run_id, provider, source)` — one aggregate row per
  source execution per run.
- Indexes: `(provider, source, started_at DESC)` (Phase 12's volume-trend
  query) and `(collection_run_id)` (explicit, in addition to whatever the
  FK itself implies, for "all attempts for this run").
- Four constraint names required an explicit, shortened form: the FK and
  three `CHECK`s (`status`/`completed_at` consistency,
  `completed_at`/`started_at` ordering, `jobs_discovered`'s non-negative
  check) — this table's own name (33 characters) is long enough that the
  naming convention's full template would exceed Postgres's 63-byte
  identifier limit for these four, verified via direct DDL rendering
  before this migration was written.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

STATUSES = ("running", "completed", "partial", "failed")
_TERMINAL_STATUSES = ("completed", "partial", "failed")
ERROR_CATEGORIES = (
    "timeout",
    "rate_limited",
    "auth_error",
    "blocked",
    "parse_error",
    "not_found",
    "upstream_error",
    "unknown",
)


def upgrade() -> None:
    op.create_table(
        "collection_run_provider_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_run_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("jobs_discovered", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("jobs_inserted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("jobs_updated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("rate_limited", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_category", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "incomplete_results", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
        sa.UniqueConstraint(
            "collection_run_id",
            "provider",
            "source",
            name=op.f("uq_collection_run_provider_attempts_collection_run_id"),
        ),
        sa.CheckConstraint(
            f"status IN {STATUSES}",
            name=op.f("ck_collection_run_provider_attempts_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) "
            f"OR (status IN {_TERMINAL_STATUSES} AND completed_at IS NOT NULL)",
            name=op.f("ck_collection_run_provider_attempts_status_completed_at"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_collection_run_provider_attempts_completed_after_started"),
        ),
        sa.CheckConstraint(
            "jobs_discovered >= 0",
            name=op.f("ck_collection_run_provider_attempts_jobs_discovered_nonneg"),
        ),
        sa.CheckConstraint(
            "jobs_inserted >= 0",
            name=op.f("ck_collection_run_provider_attempts_jobs_inserted_non_negative"),
        ),
        sa.CheckConstraint(
            "jobs_updated >= 0",
            name=op.f("ck_collection_run_provider_attempts_jobs_updated_non_negative"),
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name=op.f("ck_collection_run_provider_attempts_retry_count_non_negative"),
        ),
        sa.CheckConstraint(
            r"provider = lower(trim(both E'\t\n\r ' from provider))",
            name=op.f("ck_collection_run_provider_attempts_provider_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from provider) <> ''",
            name=op.f("ck_collection_run_provider_attempts_provider_not_empty"),
        ),
        sa.CheckConstraint(
            r"provider ~ '^[a-z0-9][a-z0-9._-]*$'",
            name=op.f("ck_collection_run_provider_attempts_provider_slug_format"),
        ),
        sa.CheckConstraint(
            r"source = lower(trim(both E'\t\n\r ' from source))",
            name=op.f("ck_collection_run_provider_attempts_source_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from source) <> ''",
            name=op.f("ck_collection_run_provider_attempts_source_not_empty"),
        ),
        sa.CheckConstraint(
            r"source ~ '^[a-z0-9][a-z0-9._-]*$'",
            name=op.f("ck_collection_run_provider_attempts_source_slug_format"),
        ),
        sa.CheckConstraint(
            f"error_category IS NULL OR error_category IN {ERROR_CATEGORIES}",
            name=op.f("ck_collection_run_provider_attempts_error_category_valid"),
        ),
        sa.CheckConstraint(
            r"error_message IS NULL OR error_message = trim(both E'\t\n\r ' from error_message)",
            name=op.f("ck_collection_run_provider_attempts_error_message_normalized"),
        ),
        sa.CheckConstraint(
            r"error_message IS NULL OR trim(both E'\t\n\r ' from error_message) <> ''",
            name=op.f("ck_collection_run_provider_attempts_error_message_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            name="fk_collection_run_provider_attempts_collection_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_run_provider_attempts")),
    )
    op.create_index(
        "ix_collection_run_provider_attempts_provider_source_started_at",
        "collection_run_provider_attempts",
        ["provider", "source", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_collection_run_provider_attempts_collection_run_id",
        "collection_run_provider_attempts",
        ["collection_run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collection_run_provider_attempts_collection_run_id",
        table_name="collection_run_provider_attempts",
    )
    op.drop_index(
        "ix_collection_run_provider_attempts_provider_source_started_at",
        table_name="collection_run_provider_attempts",
    )
    op.drop_table("collection_run_provider_attempts")
