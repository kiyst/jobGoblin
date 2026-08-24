from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Explicit naming convention so Alembic autogenerate produces stable,
# predictable constraint/index names instead of database-default names that
# vary and are hard to reference in later migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    No domain models exist yet (Phase 0 is scaffolding only) — this is the
    base Phase 1's models will inherit from, and the target of Alembic's
    `target_metadata` so autogenerate has something to diff against.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
