"""add job_notes table

Revision ID: 0017
Revises: 0016
Create Date: 2026-08-28

Fifteenth and final Phase 1 domain table (docs/DATA_MODEL.md's `job_notes`
section; master spec §36). Class H per docs/LLM_WORKFLOW.md: user-state
preservation — the same reason `user_jobs` is Class H. Unlike `user_jobs`,
this slice introduces no service-layer code and no new CASCADE pattern; the
classification is driven by the user-state-preservation trigger itself, not
by novelty. `services/` remains the only layer ever permitted to write this
table (ARCHITECTURE.md §5); no CRUD service, API route, or workspace
behavior is implemented here — this table's Phase 1 consumers are its own
factory, PostgreSQL constraint tests, and cascade-isolation tests. Phase 10
is this table's first production CRUD writer, not the first consumer of the
schema itself. This is Phase 1's last schema slice.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `user_job_id` is NOT NULL, `ON DELETE CASCADE` — a note has no meaning
  without the tracking row it annotates. This table carries no direct
  `user_id` column: ownership is reached and enforced entirely through the
  required `user_job_id` -> `user_jobs.id` foreign key, matching this
  schema's existing precedent for tables one hop from a user-scoped parent
  (`saved_search_titles.saved_search_id`, `candidate_skills.
  candidate_profile_id` — neither carries a redundant `user_id` either).
  ARCHITECTURE.md §1.4 previously listed `job_notes` among tables that
  "carry a `user_id` foreign key from day one"; that enumeration is
  corrected (docs/ARCHITECTURE.md) to distinguish directly user-owned
  tables from child tables whose ownership is enforced through a required
  parent FK, rather than adding a redundant column here. Because
  `user_jobs` itself cascades from both `users.id` and `jobs.id`, deleting
  a `User` or a `Job` cascades two levels deep, through `user_jobs`, to
  this table — the same two-level-CASCADE shape already used by
  `saved_search_titles`/`saved_search_locations` (via `saved_searches.
  user_id`) and `candidate_skills` (via `candidate_profiles.user_id`), not
  a new pattern. What is new here is that `user_jobs` has two parent FKs,
  so `job_notes` is reachable by a two-level cascade from either `users` or
  `jobs`, not just one.
- `body` is required, case-preserving free text: NOT NULL, `CHECK`-enforced
  already-trimmed (established four-character whitespace set) and
  non-empty. Unlike `identity_conflicts.resolution` (optional narrative on
  an otherwise-complete row), a `job_notes` row's only reason to exist is
  to hold `body` — an empty or whitespace-only note is rejected outright,
  not collapsed to `NULL` (there is no `NULL` state for this column).
- No `UNIQUE` constraint: multiple notes may legitimately exist for the
  same `user_job_id` — a running list of timestamped notes, not one
  edit-in-place field.
- `created_at`/`updated_at` follow the established global convention —
  already specified for this table since Rev 3, unlike every other table
  this session (no table-doc-omission tension to resolve here).
- Index: `(user_job_id, created_at DESC)` — Phase 10's "all notes for this
  job, most recent first" lookup; PostgreSQL does not automatically index a
  referencing foreign-key column, so `user_job_id` has no index of its own
  without this one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "job_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_job_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
            r"body = trim(both E'\t\n\r ' from body)",
            name=op.f("ck_job_notes_body_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from body) <> ''",
            name=op.f("ck_job_notes_body_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["user_job_id"],
            ["user_jobs.id"],
            name=op.f("fk_job_notes_user_job_id_user_jobs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job_notes")),
    )
    op.create_index(
        "ix_job_notes_user_job_id_created_at",
        "job_notes",
        ["user_job_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_job_notes_user_job_id_created_at", table_name="job_notes")
    op.drop_table("job_notes")
