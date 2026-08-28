import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Company, Job
from app.db.models.job import _NULLABLE_TEXT_COLUMNS, REMOTE_TYPES, SALARY_PERIODS
from tests.conftest import real_committed_company, real_committed_job

# `first_seen_at`/`last_seen_at` have no factory default at all (see
# `make_job` in conftest.py) — every test supplies them explicitly. These
# two constants are used by every test that doesn't care about the specific
# observation-time values, only that they satisfy `first_seen_at <=
# last_seen_at`.
_SEEN_AT = datetime(2026, 1, 1, tzinfo=UTC)
_LATER_SEEN_AT = datetime(2026, 1, 2, tzinfo=UTC)

_NON_NEGATIVE_INT_COLUMNS = (
    "salary_min",
    "salary_max",
    "annualized_salary_min",
    "annualized_salary_max",
    "years_experience_min",
    "years_experience_max",
)

_MIN_MAX_PAIRS = (
    ("salary_min", "salary_max"),
    ("annualized_salary_min", "annualized_salary_max"),
    ("years_experience_min", "years_experience_max"),
)


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession, columns_sql: str, values_sql: str
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely
    (still supplying the required `first_seen_at`/`last_seen_at`), assert
    PostgreSQL itself rejects it, and that the session recovers."""
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO jobs (id, first_seen_at, last_seen_at, {columns_sql}) "
                f"VALUES (gen_random_uuid(), now(), now(), {values_sql})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_job(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert isinstance(job.id, uuid.UUID)

    fetched = await db_session.get(Job, job.id)
    assert fetched is not None
    assert fetched.company_id is None
    assert fetched.requisition_id is None
    assert fetched.title is None
    assert fetched.remote_type is None
    assert fetched.salary_period is None
    assert fetched.compensation_explicit is None
    assert fetched.certifications is None
    assert fetched.field_provenance is None
    assert fetched.first_seen_at == _SEEN_AT
    assert fetched.last_seen_at == _SEEN_AT
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


# --------------------------------------------------------------------------
# Nullable trim-normalized text columns (parametrized over every column)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_nullable_text_defaults_to_none(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert getattr(job, column) is None


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_nullable_text_whitespace_only_becomes_none_on_orm_path(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    """These fields are optional — a covered-whitespace-only value is "not
    provided," not invalid input, so ingestion is not failed by it."""
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(job, column, "\t \n")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert getattr(job, column) is None


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_nullable_text_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(job, column, "\t Some Value \n")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert getattr(job, column) == "Some Value"


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_direct_sql_empty_text_rejected(db_session: AsyncSession, column: str) -> None:
    await _assert_direct_sql_insert_rejected(db_session, column, "''")


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_direct_sql_whitespace_wrapped_text_rejected(
    db_session: AsyncSession, column: str
) -> None:
    """An otherwise-valid value that isn't already trimmed is still
    rejected — the database never trims on write, only validates that it
    already is."""
    await _assert_direct_sql_insert_rejected(db_session, column, r"E'\tvalue\n'")


# --------------------------------------------------------------------------
# remote_type / salary_period enums
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", REMOTE_TYPES)
async def test_remote_type_accepts_documented_values(
    db_session: AsyncSession, make_job: Callable[..., Job], value: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.remote_type = value
    db_session.add(job)
    await db_session.commit()  # must not raise


async def test_remote_type_null_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    """NULL means unknown — no `'unknown'` sentinel is ever stored."""
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.remote_type is None


@pytest.mark.parametrize("value", ["unknown", "Remote", "office", ""])
async def test_remote_type_rejects_invalid_values(
    db_session: AsyncSession, make_job: Callable[..., Job], value: str
) -> None:
    """`'unknown'` is explicitly rejected, not merely unused — proving the
    sentinel this schema's NULL-means-unknown convention rules out isn't
    silently accepted."""
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.remote_type = value
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("value", SALARY_PERIODS)
async def test_salary_period_accepts_documented_values(
    db_session: AsyncSession, make_job: Callable[..., Job], value: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.salary_period = value
    db_session.add(job)
    await db_session.commit()  # must not raise


async def test_salary_period_null_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.salary_period is None


@pytest.mark.parametrize("value", ["weekly", "Hourly", ""])
async def test_salary_period_rejects_invalid_values(
    db_session: AsyncSession, make_job: Callable[..., Job], value: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.salary_period = value
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Non-negative / min<=max numeric CHECKs (parametrized)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", _NON_NEGATIVE_INT_COLUMNS)
async def test_non_negative_integer_columns_accept_zero_and_positive(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(job, column, 0)
    db_session.add(job)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("column", _NON_NEGATIVE_INT_COLUMNS)
async def test_non_negative_integer_columns_reject_negative(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(job, column, -1)
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize(("min_column", "max_column"), _MIN_MAX_PAIRS)
async def test_min_le_max_accepts_equal_and_ordered_values(
    db_session: AsyncSession, make_job: Callable[..., Job], min_column: str, max_column: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(job, min_column, 5)
    setattr(job, max_column, 5)
    db_session.add(job)
    await db_session.commit()  # must not raise; equal is accepted


@pytest.mark.parametrize(("min_column", "max_column"), _MIN_MAX_PAIRS)
async def test_min_le_max_rejects_inverted_values(
    db_session: AsyncSession, make_job: Callable[..., Job], min_column: str, max_column: str
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(job, min_column, 10)
    setattr(job, max_column, 5)
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Coordinate range and pairing (mirrors saved_search_locations exactly)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("latitude", [Decimal(-90), Decimal(90)])
async def test_latitude_in_range_accepts_boundary_values(
    db_session: AsyncSession, make_job: Callable[..., Job], latitude: Decimal
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.latitude = latitude
    job.longitude = Decimal(0)
    db_session.add(job)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("latitude", [Decimal("-90.1"), Decimal("90.1")])
async def test_latitude_out_of_range_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], latitude: Decimal
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.latitude = latitude
    job.longitude = Decimal(0)
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("longitude", [Decimal(-180), Decimal(180)])
async def test_longitude_in_range_accepts_boundary_values(
    db_session: AsyncSession, make_job: Callable[..., Job], longitude: Decimal
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.latitude = Decimal(0)
    job.longitude = longitude
    db_session.add(job)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("longitude", [Decimal("-180.1"), Decimal("180.1")])
async def test_longitude_out_of_range_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], longitude: Decimal
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.latitude = Decimal(0)
    job.longitude = longitude
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_coordinate_pair_both_null_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()  # must not raise


async def test_coordinate_pair_both_non_null_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.latitude = Decimal("39.0437")
    job.longitude = Decimal("-77.4875")
    db_session.add(job)
    await db_session.commit()  # must not raise


async def test_coordinate_pair_latitude_only_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.latitude = Decimal("39.0437")
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_coordinate_pair_longitude_only_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.longitude = Decimal("-77.4875")
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_coordinate_pair_latitude_only_rejected(
    db_session: AsyncSession,
) -> None:
    """Bypasses the ORM entirely, proving the coordinate-pair CHECK is
    enforced by PostgreSQL itself, not merely by attribute-assignment order
    in application code."""
    await _assert_direct_sql_insert_rejected(db_session, "latitude, longitude", "39.0437, NULL")


async def test_direct_sql_coordinate_pair_longitude_only_rejected(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, "latitude, longitude", "NULL, -77.4875")


# --------------------------------------------------------------------------
# field_provenance (nullable jsonb, MutableDict-wrapped)
# --------------------------------------------------------------------------


async def test_field_provenance_defaults_to_none(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.field_provenance is None


async def test_field_provenance_accepts_a_valid_top_level_object(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    occurrence_id = str(uuid.uuid4())
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    job.field_provenance = {
        "salary_min": {"source": "explicit_source", "occurrence_id": occurrence_id}
    }
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.field_provenance == {
        "salary_min": {"source": "explicit_source", "occurrence_id": occurrence_id}
    }


async def test_field_provenance_rejects_a_non_object_json_array(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, "field_provenance", "'[]'::jsonb")


async def test_field_provenance_rejects_a_non_object_json_string(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, "field_provenance", "'\"x\"'::jsonb")


async def test_field_provenance_rejects_a_json_null_literal(
    db_session: AsyncSession,
) -> None:
    """A JSON `null` *value* (not SQL `NULL`) is not SQL-`NULL`, so the
    `IS NULL` half of the CHECK doesn't apply — `jsonb_typeof` reports it as
    `'null'`, not `'object'`, so it's still rejected."""
    await _assert_direct_sql_insert_rejected(db_session, "field_provenance", "'null'::jsonb")


async def test_setting_a_top_level_field_provenance_key_persists_after_reload(
    db_engine: AsyncEngine,
) -> None:
    """A plain `JSONB` column looks unchanged to SQLAlchemy's unit-of-work
    after an in-place top-level `dict.__setitem__` — the model wraps this
    column with `MutableDict.as_mutable` specifically so this mutation is
    tracked and actually written on commit."""
    async with real_committed_job(
        db_engine,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        field_provenance={"title": {"source": "explicit_source"}},
    ) as (session, job_id):
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.field_provenance is not None
        job.field_provenance["department"] = {"source": "inferred"}
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(Job, job_id)
            assert reloaded is not None
            assert reloaded.field_provenance == {
                "title": {"source": "explicit_source"},
                "department": {"source": "inferred"},
            }


async def test_replacing_a_per_field_provenance_object_persists_after_reload(
    db_engine: AsyncEngine,
) -> None:
    """The documented, supported workaround for `MutableDict`'s
    nested-mutation limitation (see
    `test_mutating_a_nested_field_provenance_value_is_not_tracked` below):
    replace the whole top-level per-field object rather than mutate it in
    place — `field_provenance["salary_min"] = updated_entry` is a top-level
    `__setitem__` on the column itself, so it *is* tracked."""
    async with real_committed_job(
        db_engine,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        field_provenance={"salary_min": {"source": "parsed_description"}},
    ) as (session, job_id):
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.field_provenance is not None
        job.field_provenance["salary_min"] = {"source": "explicit_source"}
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(Job, job_id)
            assert reloaded is not None
            assert reloaded.field_provenance == {"salary_min": {"source": "explicit_source"}}


async def test_mutating_a_nested_field_provenance_value_is_not_tracked(
    db_engine: AsyncEngine,
) -> None:
    """Documents `MutableDict`'s real limitation: only the wrapped column's
    own top-level `__setitem__`/`__delitem__` is instrumented. Mutating a
    dict already nested inside `field_provenance` in place (as opposed to
    replacing the whole top-level per-field entry, above) is invisible to
    the unit-of-work and is silently dropped on commit."""
    async with real_committed_job(
        db_engine,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        field_provenance={"salary_min": {"source": "parsed_description"}},
    ) as (session, job_id):
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.field_provenance is not None
        job.field_provenance["salary_min"]["source"] = "explicit_source"  # type: ignore[index]  # not tracked
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(Job, job_id)
            assert reloaded is not None
            assert reloaded.field_provenance == {"salary_min": {"source": "parsed_description"}}


# --------------------------------------------------------------------------
# certifications (nullable text[], MutableList-wrapped)
# --------------------------------------------------------------------------


async def test_certifications_defaults_to_none(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.certifications is None


async def test_certifications_explicit_empty_list_distinct_from_none(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    unset_job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(unset_job)

    explicit_job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    explicit_job.certifications = []
    db_session.add(explicit_job)

    await db_session.commit()
    await db_session.refresh(unset_job)
    await db_session.refresh(explicit_job)

    assert unset_job.certifications is None
    assert explicit_job.certifications == []


async def test_appending_to_certifications_persists_after_reload(db_engine: AsyncEngine) -> None:
    """A plain `ARRAY(Text)` column looks unchanged to SQLAlchemy's
    unit-of-work after an in-place `.append()` — the model wraps this column
    with `MutableList.as_mutable` specifically so this mutation is tracked
    and actually written on commit. Reloads from a genuinely separate
    session (not just `.refresh()` on the same object) so this proves the
    value was written to PostgreSQL, not merely echoed back from the
    original session's identity map."""
    async with real_committed_job(
        db_engine,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        certifications=["PMP"],
    ) as (session, job_id):
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.certifications is not None
        job.certifications.append("CISSP")
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(Job, job_id)
            assert reloaded is not None
            assert reloaded.certifications == ["PMP", "CISSP"]


# --------------------------------------------------------------------------
# company_id (nullable FK -> companies, ON DELETE RESTRICT)
# --------------------------------------------------------------------------


async def test_company_id_null_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()  # must not raise
    await db_session.refresh(job)

    assert job.company_id is None


async def test_company_id_valid_reference_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    company = Company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    company_id = company.id

    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, company_id=company_id)
    db_session.add(job)
    await db_session.commit()  # must not raise
    await db_session.refresh(job)

    assert job.company_id == company_id


async def test_company_id_nonexistent_reference_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, company_id=uuid.uuid4())
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(Job))).scalar_one()
    assert count == 0


async def test_deleting_an_unrelated_company_succeeds(db_engine: AsyncEngine) -> None:
    """A company with no job attached at all is deleted freely — `ON DELETE
    RESTRICT` only blocks deletion of a company that a job actually
    references."""
    async with real_committed_company(db_engine, name="Unrelated Corp") as (
        session,
        company_id,
    ):
        company = await session.get(Company, company_id)
        assert company is not None
        await session.delete(company)
        await session.commit()  # must not raise


async def test_deleting_a_referenced_company_is_rejected_and_both_rows_survive(
    db_engine: AsyncEngine,
) -> None:
    async with (
        real_committed_company(db_engine, name="Acme Corp") as (session, company_id),
        real_committed_job(
            db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, company_id=company_id
        ) as (_job_session, job_id),
    ):
        company = await session.get(Company, company_id)
        assert company is not None
        with pytest.raises(IntegrityError):
            await session.delete(company)
            await session.commit()
        await session.rollback()

        async with AsyncSession(bind=db_engine) as verify_session:
            assert await verify_session.get(Company, company_id) is not None
            assert await verify_session.get(Job, job_id) is not None


async def test_deleting_the_job_then_the_company_succeeds(db_engine: AsyncEngine) -> None:
    async with real_committed_company(db_engine, name="Acme Corp") as (session, company_id):
        async with real_committed_job(
            db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, company_id=company_id
        ) as (job_session, job_id):
            job = await job_session.get(Job, job_id)
            assert job is not None
            await job_session.delete(job)
            await job_session.commit()  # must not raise

        # The job's own real-commit helper has already deleted+cleaned up
        # the job by this point; deleting the now-unreferenced company must
        # succeed.
        company = await session.get(Company, company_id)
        assert company is not None
        await session.delete(company)
        await session.commit()  # must not raise


# --------------------------------------------------------------------------
# first_seen_at <= last_seen_at
# --------------------------------------------------------------------------


async def test_first_seen_at_equal_last_seen_at_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()  # must not raise


async def test_first_seen_at_before_last_seen_at_accepted(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_LATER_SEEN_AT)
    db_session.add(job)
    await db_session.commit()  # must not raise


async def test_first_seen_at_after_last_seen_at_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_LATER_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_first_seen_at_after_last_seen_at_rejected(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO jobs (id, first_seen_at, last_seen_at) "
                "VALUES (gen_random_uuid(), '2026-01-02T00:00:00+00', '2026-01-01T00:00:00+00')"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    now = datetime.now(UTC)
    assert abs((now - job.created_at).total_seconds()) < 60
    assert abs((now - job.updated_at).total_seconds()) < 60


async def test_updated_at_advances_on_orm_update(db_engine: AsyncEngine) -> None:
    """Same rationale as every other table's equivalent test: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction, so this uses real,
    separately-committed transactions."""
    async with real_committed_job(db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT) as (
        session,
        job_id,
    ):
        job = await session.get(Job, job_id)
        assert job is not None
        first_updated_at = job.updated_at

        job.title = "Backend Engineer"
        await session.commit()
        await session.refresh(job)

        assert job.updated_at > first_updated_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (await verify_session.execute(select(func.count()).select_from(Job))).scalar_one()
        assert count == 0
