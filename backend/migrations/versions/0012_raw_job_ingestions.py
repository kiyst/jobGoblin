"""add raw_job_ingestions table

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-28

Tenth Phase 1 domain table (docs/DATA_MODEL.md's `raw_job_ingestions`
section; ADR 0005/0007). Class H per docs/LLM_WORKFLOW.md: this table
preserves audit evidence across a destructive lifecycle event (a
referenced `JobOccurrence` may be deleted, `ON DELETE SET NULL`-ing this
table's own `job_occurrence_id`). Phase 4+ ingestion code is the first
writer; this slice only migrates the schema.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `provider`/`source` are the same canonical identifiers as
  `job_occurrences`: lowercased/trimmed by the ORM, `CHECK`-restricted to
  an already-canonical, ASCII-slug value (`^[a-z0-9][a-z0-9._-]*$`) —
  generalized from `job_occurrences` since these are this project's own
  internal categorization labels, not "raw" external data.
  `source_identifier`/`parser_version`/`error_message` are trim-only,
  case-preserving, NULL-safe (externally/diagnostically sourced text).
- `job_occurrence_id` is nullable, `ON DELETE SET NULL` — this table is an
  audit trail that must outlive the occurrence it once pointed at (ADR
  0005).
- `fetched_at` is NOT NULL with **no** server default: it represents the
  actual fetch event, which may differ from row-insertion time during
  buffering, replay, or backfill. `created_at`/`updated_at` are the
  separate, standard row-lifecycle pair.
- `raw_payload` is NOT NULL jsonb with a `CHECK` requiring a top-level JSON
  object. Stays NOT NULL through Phase 1; the later retention job
  described in docs/DATA_MODEL.md that nulls old payloads will need its
  own deliberate migration to relax this when actually built. Not
  `MutableDict`-wrapped: an immutable, write-once snapshot, unlike
  `jobs.field_provenance`'s incrementally-updated fields.
- `raw_content_hash` is NOT NULL, trim/non-empty `CHECK` only — no
  hex/length format constraint (application-computed, not user input).
- `processing_status` is NOT NULL, `CHECK`-restricted to `fetched` /
  `parse_error` / `normalized` / `identity_conflict`.
- The `processing_status`/`job_occurrence_id` consistency invariant is
  enforced in only one direction, deliberately: `fetched`/`parse_error`
  require `job_occurrence_id IS NULL` (a `CHECK` — these two states can
  never have an occurrence to link to, so `ON DELETE SET NULL` never
  touches them). The reverse (`normalized`/`identity_conflict` implying a
  non-null `job_occurrence_id`) is **not** a database `CHECK`: it holds at
  write time (Phase 2's persistence-service tests will prove that), but a
  real, already-committed `normalized` row must be allowed to end up with
  `job_occurrence_id IS NULL` after its target occurrence is later
  deleted — the exact historical audit-preservation state ADR 0005 exists
  to support, not a violation. Enforcing both directions as `CHECK`s would
  make `ON DELETE SET NULL` itself raise a `CHECK` violation on that
  cascade, effectively turning it into `RESTRICT` for `normalized`/
  `identity_conflict` rows — which contradicts the stated intent.
- Index: `(job_occurrence_id, fetched_at DESC)` — backs "the latest
  ingestion for this occurrence" (ADR 0005's derived query) and "all
  ingestions for this occurrence, freshest first."
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

PROCESSING_STATUSES = ("fetched", "parse_error", "normalized", "identity_conflict")
_UNPROCESSED_STATUSES = ("fetched", "parse_error")

_NULLABLE_TEXT_COLUMNS = ("source_identifier", "parser_version", "error_message")


def _trim_not_empty_checks(column: str) -> tuple[sa.CheckConstraint, sa.CheckConstraint]:
    return (
        sa.CheckConstraint(
            rf"{column} IS NULL OR {column} = trim(both E'\t\n\r ' from {column})",
            name=op.f(f"ck_raw_job_ingestions_{column}_normalized"),
        ),
        sa.CheckConstraint(
            rf"{column} IS NULL OR trim(both E'\t\n\r ' from {column}) <> ''",
            name=op.f(f"ck_raw_job_ingestions_{column}_not_empty"),
        ),
    )


def upgrade() -> None:
    op.create_table(
        "raw_job_ingestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_identifier", sa.Text(), nullable=True),
        sa.Column("job_occurrence_id", sa.Uuid(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("raw_content_hash", sa.Text(), nullable=False),
        sa.Column("parser_version", sa.Text(), nullable=True),
        sa.Column("processing_status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
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
            name=op.f("ck_raw_job_ingestions_provider_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from provider) <> ''",
            name=op.f("ck_raw_job_ingestions_provider_not_empty"),
        ),
        sa.CheckConstraint(
            r"provider ~ '^[a-z0-9][a-z0-9._-]*$'",
            name=op.f("ck_raw_job_ingestions_provider_slug_format"),
        ),
        sa.CheckConstraint(
            r"source = lower(trim(both E'\t\n\r ' from source))",
            name=op.f("ck_raw_job_ingestions_source_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from source) <> ''",
            name=op.f("ck_raw_job_ingestions_source_not_empty"),
        ),
        sa.CheckConstraint(
            r"source ~ '^[a-z0-9][a-z0-9._-]*$'",
            name=op.f("ck_raw_job_ingestions_source_slug_format"),
        ),
        *(check for column in _NULLABLE_TEXT_COLUMNS for check in _trim_not_empty_checks(column)),
        sa.CheckConstraint(
            r"raw_content_hash = trim(both E'\t\n\r ' from raw_content_hash)",
            name=op.f("ck_raw_job_ingestions_raw_content_hash_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from raw_content_hash) <> ''",
            name=op.f("ck_raw_job_ingestions_raw_content_hash_not_empty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(raw_payload) = 'object'",
            name=op.f("ck_raw_job_ingestions_raw_payload_is_object"),
        ),
        sa.CheckConstraint(
            f"processing_status IN {PROCESSING_STATUSES}",
            name=op.f("ck_raw_job_ingestions_processing_status_valid"),
        ),
        sa.CheckConstraint(
            f"processing_status NOT IN {_UNPROCESSED_STATUSES} OR job_occurrence_id IS NULL",
            name=op.f("ck_raw_job_ingestions_unprocessed_requires_null_occurrence"),
        ),
        sa.ForeignKeyConstraint(
            ["job_occurrence_id"],
            ["job_occurrences.id"],
            name=op.f("fk_raw_job_ingestions_job_occurrence_id_job_occurrences"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_job_ingestions")),
    )
    op.create_index(
        "ix_raw_job_ingestions_occurrence_fetched_at",
        "raw_job_ingestions",
        ["job_occurrence_id", sa.text("fetched_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_raw_job_ingestions_occurrence_fetched_at", table_name="raw_job_ingestions")
    op.drop_table("raw_job_ingestions")
