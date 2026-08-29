"""add user_jobs table

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-28

Fourteenth Phase 1 domain table (docs/DATA_MODEL.md's `user_jobs` section;
master spec §36; ADR 0006). Class H per docs/LLM_WORKFLOW.md: user-state
preservation, destructive lifecycle consequences (this table's own rows
disappear if either its user or its job is deleted), and this schema's
first service-layer invariant writer (`services/user_jobs.py::set_status()`,
implemented alongside this migration in the same slice — the only function
permitted to write `status`/`applied_at`/`status_changed_at` together).
`job_notes` (the next and final Phase 1 schema slice) is not part of this
migration.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `user_id`/`job_id` are both NOT NULL, `ON DELETE CASCADE` — a tracking
  row has no meaning without its user or its job. Not this schema's first
  CASCADE from `users` (`candidate_profiles.user_id`, `saved_searches.
  user_id` already use it) or from a domain aggregate more generally
  (`job_occurrences.job_id`, `collection_run_provider_attempts.
  collection_run_id`, the `saved_search_*` child tables, and
  `candidate_skills.candidate_profile_id` already use `ON DELETE CASCADE`)
  — only the specific pairing (cascading from both a user AND a job) is
  new here.
- `applied_at` is the single source of truth for "has the user applied" —
  no independent boolean. `status` is a plain `CHECK`-restricted enum (9
  values, ADR 0006), no ORM transform, no server default: fresh creation
  must explicitly supply `interested` or `not_interested`. A bidirectional
  `CHECK` requires `applied_at IS NULL` for the two pre-application
  statuses and `applied_at IS NOT NULL` for the seven post-application
  statuses — a hard database invariant, not application-code discipline
  alone. Backwards transitions are permitted; only the NULL-ness pairing
  is ever enforced, never a transition graph.
- `status_changed_at` is NOT NULL with **no** server default — a business
  timestamp explicitly supplied at row creation and updated only by
  `set_status()` when `status` actually changes. Deliberately **not** an
  ORM `onupdate` column like `updated_at`: `updated_at` advances on every
  write to this row (e.g. toggling `saved`), `status_changed_at` must not.
- `saved`/`hidden`/`archived` are independent booleans (NOT NULL,
  `server_default false`), orthogonal to `status`/`applied_at` and to each
  other — no `CHECK` relates any of them.
- `created_at`/`updated_at` follow the established global convention —
  not previously specified in this table's own design note.
- `UNIQUE (user_id, job_id)` — one tracking row per user per job.
- Index: `(job_id)` — PostgreSQL does not automatically index a
  referencing foreign-key column; `(user_id, job_id)` is already covered
  by the `UNIQUE` constraint's own index (leading column `user_id`), but
  `job_id` has no index of its own without this one. No separate `user_id`
  index is added, since the `UNIQUE` index already begins with it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

STATUSES = (
    "interested",
    "not_interested",
    "applied",
    "recruiter_contacted",
    "screening",
    "interviewing",
    "offer",
    "rejected_by_employer",
    "withdrawn_by_user",
)
_PRE_APPLICATION_STATUSES = ("interested", "not_interested")
_POST_APPLICATION_STATUSES = (
    "applied",
    "recruiter_contacted",
    "screening",
    "interviewing",
    "offer",
    "rejected_by_employer",
    "withdrawn_by_user",
)


def upgrade() -> None:
    op.create_table(
        "user_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("saved", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("archived", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
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
            "user_id",
            "job_id",
            name=op.f("uq_user_jobs_user_id"),
        ),
        sa.CheckConstraint(
            f"status IN {STATUSES}",
            name=op.f("ck_user_jobs_status_valid"),
        ),
        sa.CheckConstraint(
            f"(status IN {_PRE_APPLICATION_STATUSES} AND applied_at IS NULL) "
            f"OR (status IN {_POST_APPLICATION_STATUSES} AND applied_at IS NOT NULL)",
            name=op.f("ck_user_jobs_status_applied_at_consistency"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_jobs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name=op.f("fk_user_jobs_job_id_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_jobs")),
    )
    op.create_index(
        "ix_user_jobs_job_id",
        "user_jobs",
        ["job_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_jobs_job_id", table_name="user_jobs")
    op.drop_table("user_jobs")
