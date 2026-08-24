"""fix email whitespace-normalization checks

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-24

Migration `0002`'s CHECK constraints used PostgreSQL's bare `trim(email)`,
whose default trim character is an ordinary space only — while the ORM's
`_normalize_email` validator (`app/db/models/user.py`) uses Python's
`str.strip()`, which also strips tabs/newlines. That mismatch let a
tab/newline-wrapped value (e.g. `"\tperson@example.com\t"`) pass the
`ck_users_email_normalized` CHECK outright, since Postgres's `trim()` left it
unchanged on both sides of the equality.

This is a **forward-only correction**, not a rewrite of `0002`: `0002` is left
describing exactly what it originally did (and what any database that already
applied it actually has), so `alembic history`/`current` stay meaningful for
every database that reached `0002` before this fix existed — including the
`jobgoblin` development database. Upgrading from `0002` to `0003` replaces the
two email CHECK constraints with versions that trim exactly the four-character
set the ORM now uses (space, tab, LF, CR — see `_COVERED_WHITESPACE` in
`app/db/models/user.py`); downgrading restores the original (bare-`trim`)
constraints.
"""

from collections.abc import Sequence

from alembic import op

# `op.drop_constraint`/`op.create_check_constraint` re-apply the naming
# convention (app/db/base.py's NAMING_CONVENTION) to any name passed as a
# plain string — since these names are already fully resolved
# ("ck_users_..."), they must be wrapped in `op.f()` to mark them as already
# resolved. Passing the plain string here originally double-prefixed it to
# "ck_users_ck_users_email_normalized", which doesn't exist — caught by
# actually running this migration against a real database, not just review.

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NORMALIZED_CHECK_NAME = "ck_users_email_normalized"
_NOT_EMPTY_CHECK_NAME = "ck_users_email_not_empty"

# Same four-character whitespace set as `_COVERED_WHITESPACE` in
# app/db/models/user.py: space, tab, line feed, carriage return.
_FIXED_NORMALIZED_SQL = r"email = lower(trim(both E'\t\n\r ' from email))"
_FIXED_NOT_EMPTY_SQL = r"trim(both E'\t\n\r ' from email) <> ''"

_ORIGINAL_NORMALIZED_SQL = "email = lower(trim(email))"
_ORIGINAL_NOT_EMPTY_SQL = "trim(email) <> ''"


def upgrade() -> None:
    op.drop_constraint(op.f(_NORMALIZED_CHECK_NAME), "users", type_="check")
    op.drop_constraint(op.f(_NOT_EMPTY_CHECK_NAME), "users", type_="check")
    op.create_check_constraint(op.f(_NORMALIZED_CHECK_NAME), "users", _FIXED_NORMALIZED_SQL)
    op.create_check_constraint(op.f(_NOT_EMPTY_CHECK_NAME), "users", _FIXED_NOT_EMPTY_SQL)


def downgrade() -> None:
    op.drop_constraint(op.f(_NORMALIZED_CHECK_NAME), "users", type_="check")
    op.drop_constraint(op.f(_NOT_EMPTY_CHECK_NAME), "users", type_="check")
    op.create_check_constraint(op.f(_NORMALIZED_CHECK_NAME), "users", _ORIGINAL_NORMALIZED_SQL)
    op.create_check_constraint(op.f(_NOT_EMPTY_CHECK_NAME), "users", _ORIGINAL_NOT_EMPTY_SQL)
