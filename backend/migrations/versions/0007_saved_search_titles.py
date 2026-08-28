"""add saved_search_titles table

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-24

Fifth Phase 1 domain table (docs/DATA_MODEL.md's `saved_search_titles`
section). Only this table — `saved_search_locations` remains a separate
future slice, same incremental pattern as every prior Phase 1 table.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `title` is normalized the same way `candidate_skills.skill` and
  `saved_searches.name` are: trimmed of the four-character whitespace set
  (space, tab, LF, CR), enforced by database `CHECK`s in addition to an ORM
  `@validates` normalizer — case preserved, never lowercased.
- Case-insensitive, per-search uniqueness is enforced by a functional unique
  index on `(saved_search_id, lower(title))`, the same pattern `users` uses
  for `lower(email)` and `candidate_skills` uses for `lower(skill)`.
- `is_primary` is not null with `server_default false`. At most one primary
  title per saved search is enforced by a partial unique index on
  `saved_search_id WHERE is_primary`. Zero primary titles is a valid,
  unconstrained state — enforcing "exactly one" would need a trigger, which
  is deliberately not added.
- `created_at`/`updated_at` are added as non-null `timestamptz` columns with
  `server_default now()`, consistent with every other implemented table,
  even though the column list in `docs/DATA_MODEL.md`'s
  `saved_search_titles` section omitted them (the same recurring gap
  already fixed for `users`, `candidate_skills`, and `saved_searches`).
- No separate plain index on `saved_search_id`: it is already the leading
  column of the composite unique index above, so a second index would be
  redundant for lookups.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "saved_search_titles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("saved_search_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
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
            r"title = trim(both E'\t\n\r ' from title)",
            name=op.f("ck_saved_search_titles_title_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from title) <> ''",
            name=op.f("ck_saved_search_titles_title_not_empty"),
        ),
        sa.ForeignKeyConstraint(
            ["saved_search_id"],
            ["saved_searches.id"],
            name=op.f("fk_saved_search_titles_saved_search_id_saved_searches"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_search_titles")),
    )
    # Expression/functional unique index — a UNIQUE table constraint can only
    # cover plain columns, not lower(title), so an index is the only way to
    # enforce case-insensitive, per-search uniqueness while still storing
    # and returning the original case.
    op.create_index(
        "uq_saved_search_titles_search_id_title_lower",
        "saved_search_titles",
        ["saved_search_id", sa.text("lower(title)")],
        unique=True,
    )
    # Partial unique index: at most one primary title per saved search. Zero
    # primary titles is unconstrained.
    op.create_index(
        "uq_saved_search_titles_search_id_primary",
        "saved_search_titles",
        ["saved_search_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_index("uq_saved_search_titles_search_id_primary", table_name="saved_search_titles")
    op.drop_index("uq_saved_search_titles_search_id_title_lower", table_name="saved_search_titles")
    op.drop_table("saved_search_titles")
