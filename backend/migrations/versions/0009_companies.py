"""add companies table

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-28

Seventh Phase 1 domain table (docs/DATA_MODEL.md's `companies` section) — the
next unimplemented Phase 1 table after the `saved_searches` group. No other
table is touched by this migration. Class H per docs/LLM_WORKFLOW.md: this is
the first migration to introduce a self-referential foreign key, the first to
use `ON DELETE SET NULL`, and the first to use a PostgreSQL generated
(`GENERATED ALWAYS AS ... STORED`) column.

Product rules resolved by explicit approval before this migration was
written (not inferred silently):

- `domain` is always stored pre-normalized by
  `app.normalization.company.normalize_domain()`, a pure function
  implementing the full IDNA2008/UTS #46 domain-canonicalization algorithm
  (trim, lowercase, scheme/userinfo/port/path/query/fragment stripping, one
  leading `www.` and one trailing DNS root-label dot removed, IDNA/UTS #46
  conversion). Malformed input never raises — it normalizes to `NULL`, same
  as an explicitly-unknown domain. This requires a new direct dependency,
  `idna==3.19` (BSD-3-Clause) — see `backend/pyproject.toml` for the
  replacement/removal note. The stdlib `str.encode("idna")` codec only
  implements the older IDNA2003 algorithm and mishandles inputs UTS #46
  (`uts46=True`) correctly accepts/rejects.
- Case-insensitive domain uniqueness is enforced by a functional, *partial*
  unique index — `UNIQUE (lower(domain)) WHERE domain IS NOT NULL` — so any
  number of companies with an unknown (`NULL`) domain coexist freely; `NULL`
  means "unknown", not "empty" or a value that could collide with another
  `NULL`.
- `normalized_name` is a PostgreSQL `GENERATED ALWAYS AS (...) STORED`
  column derived from `name` (trim `_COVERED_WHITESPACE`, collapse internal
  runs of that same four-character set to one space, lowercase) — not an
  independently writable column kept in sync by an ORM validator, which
  direct SQL or a bulk operation could otherwise bypass, storing a `name`/
  `normalized_name` pair that disagree. It gets a plain, non-unique index
  for lookup only: company names collide too often across sources for a
  name-only unique constraint to be safe (see docs/DATA_MODEL.md).
- `duplicate_of_company_id` is a nullable, self-referential foreign key
  (`companies.id`, `ON DELETE SET NULL`) reserved for a future (post-MVP)
  manual reconciliation workflow — nothing in Phase 1-6 populates or
  enforces it. A `CHECK` prevents only direct self-reference
  (`duplicate_of_company_id <> id`); a longer duplicate cycle
  (A -> B -> A) is out of scope for this migration and is a future
  reconciliation-workflow responsibility.
- `homepage_url`, `career_page_url`, and `industry` are nullable `text`
  columns with NULL-safe normalization `CHECK`s (non-NULL values must
  already be trimmed and non-empty) — no URL-format validation, per explicit
  decision. The ORM converts a covered-whitespace-only input to `NULL`
  rather than failing ingestion.
- `created_at`/`updated_at` follow the established pattern: non-null
  `timestamptz` columns with `server_default now()`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NORMALIZED_NAME_EXPRESSION = (
    r"lower(regexp_replace(trim(both E'\t\n\r ' from name), E'[\t\n\r ]+', ' ', 'g'))"
)


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "normalized_name",
            sa.Text(),
            sa.Computed(_NORMALIZED_NAME_EXPRESSION, persisted=True),
            nullable=False,
        ),
        sa.Column("domain", sa.Text(), nullable=True),
        sa.Column("homepage_url", sa.Text(), nullable=True),
        sa.Column("career_page_url", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("duplicate_of_company_id", sa.Uuid(), nullable=True),
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
            name=op.f("ck_companies_name_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from name) <> ''",
            name=op.f("ck_companies_name_not_empty"),
        ),
        sa.CheckConstraint(
            r"homepage_url IS NULL OR homepage_url = trim(both E'\t\n\r ' from homepage_url)",
            name=op.f("ck_companies_homepage_url_normalized"),
        ),
        sa.CheckConstraint(
            r"homepage_url IS NULL OR trim(both E'\t\n\r ' from homepage_url) <> ''",
            name=op.f("ck_companies_homepage_url_not_empty"),
        ),
        sa.CheckConstraint(
            r"career_page_url IS NULL OR "
            r"career_page_url = trim(both E'\t\n\r ' from career_page_url)",
            name=op.f("ck_companies_career_page_url_normalized"),
        ),
        sa.CheckConstraint(
            r"career_page_url IS NULL OR trim(both E'\t\n\r ' from career_page_url) <> ''",
            name=op.f("ck_companies_career_page_url_not_empty"),
        ),
        sa.CheckConstraint(
            r"industry IS NULL OR industry = trim(both E'\t\n\r ' from industry)",
            name=op.f("ck_companies_industry_normalized"),
        ),
        sa.CheckConstraint(
            r"industry IS NULL OR trim(both E'\t\n\r ' from industry) <> ''",
            name=op.f("ck_companies_industry_not_empty"),
        ),
        sa.CheckConstraint(
            "duplicate_of_company_id IS NULL OR duplicate_of_company_id <> id",
            name=op.f("ck_companies_duplicate_of_company_id_not_self"),
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_company_id"],
            ["companies.id"],
            name=op.f("fk_companies_duplicate_of_company_id_companies"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
    )
    # Expression/functional, partial unique index — a UNIQUE table
    # constraint can only cover plain columns, not lower(domain), and
    # cannot be made partial (WHERE domain IS NOT NULL). An index is the
    # only way to enforce case-insensitive domain uniqueness while letting
    # any number of NULL-domain companies coexist.
    op.create_index(
        "uq_companies_domain_lower",
        "companies",
        [sa.text("lower(domain)")],
        unique=True,
        postgresql_where=sa.text("domain IS NOT NULL"),
    )
    op.create_index("ix_companies_normalized_name", "companies", ["normalized_name"])


def downgrade() -> None:
    op.drop_index("ix_companies_normalized_name", table_name="companies")
    op.drop_index("uq_companies_domain_lower", table_name="companies")
    op.drop_table("companies")
