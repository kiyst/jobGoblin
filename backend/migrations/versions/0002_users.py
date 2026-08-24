"""add users table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-24

First Phase 1 domain table. Reviewed and hand-edited against
`alembic revision --autogenerate` output (which correctly detected the table,
both CHECK constraints, and the functional unique index, but used a
random-hex revision id and no descriptive comments — both fixed here to match
this project's migration-numbering convention and the model's own docstring).

Every other Phase 1 table's `user_id` FK will reference this one; no other
domain tables are introduced by this migration (see
docs/DECISIONS/0003-minimal-phase1-schema.md).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
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
        # Database-level backstop for email normalization — see
        # app/db/models/user.py's `_normalize_email` validator and
        # docs/DATA_MODEL.md. These reject any write that bypasses the ORM
        # (including a raw SQL INSERT/UPDATE), not just ORM-driven ones.
        # `trim(both E'\t\n\r ' from email)` strips exactly the same
        # four-character whitespace set (space, tab, LF, CR) as the model's
        # `_COVERED_WHITESPACE` — Postgres's bare `trim(email)` only strips
        # plain spaces, which previously let tab/newline-wrapped values pass.
        sa.CheckConstraint(
            r"email = lower(trim(both E'\t\n\r ' from email))",
            name=op.f("ck_users_email_normalized"),
        ),
        sa.CheckConstraint(
            r"trim(both E'\t\n\r ' from email) <> ''",
            name=op.f("ck_users_email_not_empty"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    # Expression/functional unique index — a UNIQUE table constraint can only
    # cover plain columns, not lower(email), so an index is the only way to
    # enforce case-insensitive uniqueness even though the stored value is
    # already normalized.
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
