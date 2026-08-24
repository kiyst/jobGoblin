"""baseline (empty)

Revision ID: 0001
Revises:
Create Date: 2026-08-24

Phase 0 baseline: proves the Alembic pipeline (upgrade/downgrade/upgrade)
works end-to-end against a real PostgreSQL database before any Phase 1
domain tables exist. Deliberately a no-op.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
