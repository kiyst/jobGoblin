"""add collection_runs table

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-28

Twelfth Phase 1 domain table (docs/DATA_MODEL.md's `collection_runs`
section). Class H per docs/LLM_WORKFLOW.md: this is
the scheduler execution record — "scheduler" is a named Class-H trigger —
with a three-column lifecycle `CHECK` (status/started_at/completed_at)
mirroring `collection_run_provider_attempts`' own already-documented
pattern. Phase 2's offline fixture pipeline is the first writer; this
slice only migrates the schema.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `saved_search_id` is nullable, `ON DELETE SET NULL` — a run's history
  outlives the saved search that triggered it. No other column's `CHECK`
  references this one's nullness, so there is no FK-vs-CHECK asymmetric
  design tension here, unlike `raw_job_ingestions`/`identity_conflicts`.
- `started_at` is NOT NULL with **no** server default — supplied
  explicitly by the scheduler/pipeline code, matching
  `raw_job_ingestions.fetched_at`'s treatment. `completed_at` is nullable
  only while `status = 'running'`; every terminal status
  (`completed`/`completed_with_errors`/`failed`) requires it non-null (a
  `CHECK`, mirroring `collection_run_provider_attempts`' own status/
  `completed_at` consistency pattern). A second `CHECK` requires
  `completed_at >= started_at` when both are set. `status` has no server
  default: fresh creation must explicitly supply `'running'`.
- `providers_attempted` (text[]) records providers whose execution
  actually began, not merely planned — a provider rejected during
  `QueryPlanner` validation (no `discover()` call made) is recorded in
  `failures` instead, never here. NOT NULL, `server_default '{}'`,
  `MutableList`-wrapped for in-place append tracking. Application code is
  responsible for avoiding duplicate entries; no database uniqueness is
  enforced on array elements.
- `providers_enforced_locally` (jsonb, shape `{provider: {source:
  [field, ...]}}`) is assembled in memory during planning and assigned as
  one complete value once planning finishes, never built up by repeated
  in-place mutation. NOT NULL, `server_default '{}'`, a `CHECK` requires a
  top-level JSON object. Deliberately **not** `MutableDict`-wrapped:
  nested in-place mutation is not tracked, the same limitation already
  documented for `jobs.field_provenance`.
- `failures` (jsonb array of `{provider, source, error}`) can accumulate
  at both planning time (a validation failure with no attempt row at all)
  and execution time, potentially across more than one write to the same
  row. NOT NULL, `server_default '[]'`, a `CHECK` requires a top-level
  JSON array, `MutableList`-wrapped for top-level append tracking. Nested
  mutation within an already-appended entry is not tracked; correcting an
  entry requires replacing the whole list. No `CHECK` ties `failures` or
  the three job counters to `status` — a `completed_with_errors` row may
  legitimately show accurate non-zero rollups alongside a non-empty
  `failures` array, mirroring `collection_run_provider_attempts`' own
  "no `CHECK` ties `error_category`/status" reasoning.
- `jobs_discovered`/`jobs_inserted`/`jobs_updated` are NOT NULL,
  `server_default 0`, each with a non-negative `CHECK` — the established
  `collection_run_provider_attempts` counter convention. `duration_ms`
  stays freely nullable with a NULL-safe non-negative `CHECK`.
- `created_at`/`updated_at` follow the established global convention,
  matching `collection_run_provider_attempts`' own sibling columns.
- Indexes: `(saved_search_id, started_at DESC)` (run history per search;
  also serves Phase 9's "is there already a run for this search" lookup
  by leading column) and `(status)` (Phase 9's "find all still-running
  rows" abandoned-run detection, not scoped to one search). These are
  lookup support only — they do not prevent overlapping runs under
  concurrency; Phase 9's own database-lock/partial-unique strategy for
  that is a separate, explicitly designed scheduler invariant, out of
  scope here. No uniqueness constraint of any kind in this slice.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

STATUSES = ("running", "completed", "completed_with_errors", "failed")
_TERMINAL_STATUSES = ("completed", "completed_with_errors", "failed")


def upgrade() -> None:
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("saved_search_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "providers_attempted",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column(
            "providers_enforced_locally",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("jobs_discovered", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("jobs_inserted", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("jobs_updated", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "failures",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
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
            f"status IN {STATUSES}",
            name=op.f("ck_collection_runs_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) "
            f"OR (status IN {_TERMINAL_STATUSES} AND completed_at IS NOT NULL)",
            name=op.f("ck_collection_runs_status_completed_at_consistency"),
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name=op.f("ck_collection_runs_completed_at_after_started_at"),
        ),
        sa.CheckConstraint(
            "jobs_discovered >= 0",
            name=op.f("ck_collection_runs_jobs_discovered_non_negative"),
        ),
        sa.CheckConstraint(
            "jobs_inserted >= 0",
            name=op.f("ck_collection_runs_jobs_inserted_non_negative"),
        ),
        sa.CheckConstraint(
            "jobs_updated >= 0",
            name=op.f("ck_collection_runs_jobs_updated_non_negative"),
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name=op.f("ck_collection_runs_duration_ms_non_negative"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(providers_enforced_locally) = 'object'",
            name=op.f("ck_collection_runs_providers_enforced_locally_is_object"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(failures) = 'array'",
            name=op.f("ck_collection_runs_failures_is_array"),
        ),
        sa.ForeignKeyConstraint(
            ["saved_search_id"],
            ["saved_searches.id"],
            name=op.f("fk_collection_runs_saved_search_id_saved_searches"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_runs")),
    )
    op.create_index(
        "ix_collection_runs_saved_search_id_started_at",
        "collection_runs",
        ["saved_search_id", sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_collection_runs_status",
        "collection_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_collection_runs_status", table_name="collection_runs")
    op.drop_index("ix_collection_runs_saved_search_id_started_at", table_name="collection_runs")
    op.drop_table("collection_runs")
