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

    `User` (`app/db/models/user.py`), `CandidateProfile`
    (`app/db/models/candidate_profile.py`), `CandidateSkill`
    (`app/db/models/candidate_skill.py`), `SavedSearch`
    (`app/db/models/saved_search.py`), `SavedSearchTitle`
    (`app/db/models/saved_search_title.py`), `SavedSearchLocation`
    (`app/db/models/saved_search_location.py`), `Company`
    (`app/db/models/company.py`), `Job` (`app/db/models/job.py`),
    `JobOccurrence` (`app/db/models/job_occurrence.py`),
    `RawJobIngestion` (`app/db/models/raw_job_ingestion.py`),
    `IdentityConflict` (`app/db/models/identity_conflict.py`),
    `CollectionRun` (`app/db/models/collection_run.py`),
    `CollectionRunProviderAttempt`
    (`app/db/models/collection_run_provider_attempt.py`), and `UserJob`
    (`app/db/models/user_job.py`) are the Phase 1 models registered
    against this base so far; every other Phase 1 table will follow the
    same pattern. This is also Alembic's
    `target_metadata` (see
    `migrations/env.py`, which imports `app.db.models` so autogenerate has
    something to diff against).
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
