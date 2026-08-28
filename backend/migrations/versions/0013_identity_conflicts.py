"""add identity_conflicts table

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-28

Eleventh Phase 1 domain table (docs/DATA_MODEL.md's `identity_conflicts`
section; ADR 0007). Class H per docs/LLM_WORKFLOW.md: two independent
`ON DELETE SET NULL` relationships, a first-of-its-kind bidirectional
status/timestamp lifecycle `CHECK`, and a conflict_type-conditional JSON
shape `CHECK`. Phase 2's offline fixture pipeline is the first writer/user
of this table, producing both conflict fixtures per
docs/PHASE_RISK_CHECKLIST.md; this slice only migrates the schema.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `conflict_type`/`status` are plain `CHECK`-restricted enums, not
  canonical identifiers — no ORM trim/case transform, matching
  `raw_job_ingestions.processing_status`'s treatment (closed literal
  sets, not cross-table join keys).
- `existing_value`/`incoming_value` are NOT NULL jsonb whose shape depends
  on `conflict_type`: a JSON object for `evidence_mismatch`, a JSON array
  for `ambiguous_match`, enforced by a `CHECK` conditional on
  `conflict_type` for each column. Neither non-empty objects/arrays nor
  inner element schemas are enforced — only the top-level shape. Not
  `MutableDict`/`MutableList`-wrapped: immutable, write-once snapshots,
  same rationale as `raw_job_ingestions.raw_payload`.
- `existing_job_occurrence_id`/`incoming_raw_job_ingestion_id` are both
  nullable, `ON DELETE SET NULL` — this table is an audit trail that must
  outlive either referenced row. Only the safe direction of the
  `conflict_type`/`existing_job_occurrence_id` relationship is a database
  `CHECK`: `ambiguous_match` requires `existing_job_occurrence_id IS
  NULL` (safe — an `ambiguous_match` row never has a non-null value to
  begin with, so the FK cascade never touches it in a way that could
  violate this). The reverse (`evidence_mismatch` implying non-null) is
  **not** a `CHECK`, for the same reason `raw_job_ingestions`' analogous
  invariant isn't: enforcing it would turn `ON DELETE SET NULL` into
  `RESTRICT` in practice whenever a disputed occurrence is later deleted.
  `incoming_raw_job_ingestion_id` gets no `CHECK` at all — populated for
  both conflict types at write time, but must remain legitimately
  nullable after its own cascade fires.
- `status`/`resolved_at` consistency (`open` <=> `resolved_at IS NULL`;
  `resolved`/`ignored` <=> `resolved_at IS NOT NULL`) and
  `resolved_at >= created_at` ordering are both plain `CHECK`s — neither
  interacts with either FK's `ON DELETE SET NULL` (different columns
  entirely), so both are safe to enforce fully. `status` has no server
  default: fresh conflict creation must explicitly supply `'open'`.
- `resolution` is nullable, case-preserving, ORM-trimmed with blank
  collapsed to `NULL`, but has **no** backing `CHECK` — enforcing
  non-empty narrative text would be enforcing writing quality, which this
  project does nowhere else. A direct SQL write is not promised this
  normalization.
- `created_at`/`updated_at` follow the established global convention — a
  conflict row's creation moment is its detection moment, unlike
  `raw_job_ingestions.fetched_at`, so no separate business timestamp is
  needed.
- Indexes: `(status)`, `(existing_job_occurrence_id)`,
  `(incoming_raw_job_ingestion_id)` — three plain, non-unique indexes; no
  uniqueness constraint anywhere (a single ingestion can raise more than
  one conflict; a single occurrence can accumulate multiple conflicts).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

CONFLICT_TYPES = ("evidence_mismatch", "ambiguous_match")
STATUSES = ("open", "resolved", "ignored")


def upgrade() -> None:
    op.create_table(
        "identity_conflicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("existing_job_occurrence_id", sa.Uuid(), nullable=True),
        sa.Column("incoming_raw_job_ingestion_id", sa.Uuid(), nullable=True),
        sa.Column("conflict_type", sa.Text(), nullable=False),
        sa.Column("existing_value", postgresql.JSONB(), nullable=False),
        sa.Column("incoming_value", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=True),
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
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            f"conflict_type IN {CONFLICT_TYPES}",
            name=op.f("ck_identity_conflicts_conflict_type_valid"),
        ),
        sa.CheckConstraint(
            f"status IN {STATUSES}",
            name=op.f("ck_identity_conflicts_status_valid"),
        ),
        sa.CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) "
            "OR (status IN ('resolved', 'ignored') AND resolved_at IS NOT NULL)",
            name=op.f("ck_identity_conflicts_status_resolved_at_consistency"),
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= created_at",
            name=op.f("ck_identity_conflicts_resolved_at_after_created_at"),
        ),
        sa.CheckConstraint(
            "(conflict_type = 'evidence_mismatch' AND jsonb_typeof(existing_value) = 'object') "
            "OR (conflict_type = 'ambiguous_match' AND jsonb_typeof(existing_value) = 'array')",
            name=op.f("ck_identity_conflicts_existing_value_shape"),
        ),
        sa.CheckConstraint(
            "(conflict_type = 'evidence_mismatch' AND jsonb_typeof(incoming_value) = 'object') "
            "OR (conflict_type = 'ambiguous_match' AND jsonb_typeof(incoming_value) = 'array')",
            name=op.f("ck_identity_conflicts_incoming_value_shape"),
        ),
        sa.CheckConstraint(
            "conflict_type <> 'ambiguous_match' OR existing_job_occurrence_id IS NULL",
            name=op.f("ck_identity_conflicts_ambiguous_match_requires_null_occurrence"),
        ),
        sa.ForeignKeyConstraint(
            ["existing_job_occurrence_id"],
            ["job_occurrences.id"],
            name="fk_identity_conflicts_existing_occurrence",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["incoming_raw_job_ingestion_id"],
            ["raw_job_ingestions.id"],
            name="fk_identity_conflicts_incoming_ingestion",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identity_conflicts")),
    )
    op.create_index(
        "ix_identity_conflicts_status",
        "identity_conflicts",
        ["status"],
    )
    op.create_index(
        "ix_identity_conflicts_existing_job_occurrence_id",
        "identity_conflicts",
        ["existing_job_occurrence_id"],
    )
    op.create_index(
        "ix_identity_conflicts_incoming_raw_job_ingestion_id",
        "identity_conflicts",
        ["incoming_raw_job_ingestion_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_identity_conflicts_incoming_raw_job_ingestion_id", table_name="identity_conflicts"
    )
    op.drop_index(
        "ix_identity_conflicts_existing_job_occurrence_id", table_name="identity_conflicts"
    )
    op.drop_index("ix_identity_conflicts_status", table_name="identity_conflicts")
    op.drop_table("identity_conflicts")
