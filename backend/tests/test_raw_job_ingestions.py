import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import TextClause, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Job, JobOccurrence, RawJobIngestion
from tests.conftest import real_committed_raw_job_ingestion

_FETCHED_AT = datetime(2026, 1, 1, tzinfo=UTC)

_VALID_HASH = "a" * 64


async def _insert_job_occurrence(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> uuid.UUID:
    """Returns a real, committed `JobOccurrence`'s id (creating its parent
    `Job` first) — captured immediately after its own commit, matching
    `test_job_occurrences.py::_insert_job`'s rationale about attribute
    expiry after a later commit."""
    job = make_job(first_seen_at=_FETCHED_AT, last_seen_at=_FETCHED_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    job_id = job.id

    occurrence = make_job_occurrence(
        job_id=job_id, first_seen_at=_FETCHED_AT, last_seen_at=_FETCHED_AT
    )
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)
    return occurrence.id


_DIRECT_SQL_BASE_COLUMNS = {
    "provider": "'ats_scrapers'",
    "source": "'greenhouse'",
    "raw_payload": '\'{"title": "Backend Engineer"}\'::jsonb',
    "raw_content_hash": f"'{_VALID_HASH}'",
    "processing_status": "'fetched'",
}


def _direct_sql_insert_statement(
    overrides: dict[str, str], *, job_occurrence_id: uuid.UUID | None
) -> tuple[TextClause, dict[str, object]]:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", "fetched_at", *columns.keys()]
    column_values = ["gen_random_uuid()", "now()", *columns.values()]
    params: dict[str, object] = {}
    if job_occurrence_id is not None:
        column_names.append("job_occurrence_id")
        column_values.append(":job_occurrence_id")
        params["job_occurrence_id"] = job_occurrence_id
    stmt = text(
        f"INSERT INTO raw_job_ingestions ({', '.join(column_names)}) "
        f"VALUES ({', '.join(column_values)})"
    )
    return stmt, params


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession,
    overrides: dict[str, str],
    *,
    job_occurrence_id: uuid.UUID | None = None,
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id`/`fetched_at` are always supplied; `provider`/`source`/`raw_payload`/
    `raw_content_hash`/`processing_status` default to a valid row and are
    replaced (not duplicated) by any of the same keys in `overrides`.
    Asserts PostgreSQL itself rejects the insert, and that the session
    recovers."""
    stmt, params = _direct_sql_insert_statement(overrides, job_occurrence_id=job_occurrence_id)
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt.bindparams(**params) if params else stmt)
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_insert_accepted(
    db_session: AsyncSession,
    overrides: dict[str, str],
    *,
    job_occurrence_id: uuid.UUID | None = None,
) -> None:
    stmt, params = _direct_sql_insert_statement(overrides, job_occurrence_id=job_occurrence_id)
    await db_session.execute(stmt.bindparams(**params) if params else stmt)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(RawJobIngestion))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_ingestion(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT)
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert isinstance(ingestion.id, uuid.UUID)

    fetched = await db_session.get(RawJobIngestion, ingestion.id)
    assert fetched is not None
    assert fetched.provider == "ats_scrapers"
    assert fetched.source == "greenhouse"
    assert fetched.source_identifier is None
    assert fetched.job_occurrence_id is None
    assert fetched.fetched_at == _FETCHED_AT
    assert fetched.raw_payload == {"title": "Backend Engineer"}
    assert fetched.raw_content_hash == _VALID_HASH
    assert fetched.parser_version is None
    assert fetched.processing_status == "fetched"
    assert fetched.error_message is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


# --------------------------------------------------------------------------
# provider / source — canonical identifiers (generalized from job_occurrences)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_provider_and_source_are_lowercased_and_trimmed_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    column: str,
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, **{column: "\t ATS_Scrapers \n"})
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert getattr(ingestion, column) == "ats_scrapers"


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_non_lowercase_provider_or_source_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "'Greenhouse'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_whitespace_wrapped_provider_or_source_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: r"E'\tgreenhouse\n'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_empty_provider_or_source_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "''"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_non_ascii_provider_or_source_rejected_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    column: str,
) -> None:
    """The ASCII slug-format `CHECK`, not the ORM's `str.lower()` validator,
    is what rejects this — same rationale as `job_occurrences`."""
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, **{column: "café"})
    db_session.add(ingestion)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_non_ascii_provider_or_source_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "'café'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_embedded_space_provider_or_source_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "'green house'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_provider_or_source_starting_with_hyphen_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "'-leadinghyphen'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_provider_or_source_slug_format_accepts_dot_underscore_hyphen(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    column: str,
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, **{column: "job-spy_v2.test"})
    db_session.add(ingestion)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# Nullable, case-preserving text columns
# --------------------------------------------------------------------------

_NULLABLE_TEXT_COLUMNS = ("source_identifier", "parser_version", "error_message")


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_nullable_text_defaults_to_none(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    column: str,
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT)
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert getattr(ingestion, column) is None


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_nullable_text_whitespace_only_becomes_none_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    column: str,
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, **{column: "   \t\n  "})
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert getattr(ingestion, column) is None


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_nullable_text_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    column: str,
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, **{column: "  Mixed-Case Value  "})
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert getattr(ingestion, column) == "Mixed-Case Value"


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_direct_sql_empty_nullable_text_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: "''"})


@pytest.mark.parametrize("column", _NULLABLE_TEXT_COLUMNS)
async def test_direct_sql_whitespace_wrapped_nullable_text_rejected(
    db_session: AsyncSession, column: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {column: r"E'\tvalue\n'"})


# --------------------------------------------------------------------------
# raw_content_hash — required, trim/non-empty only, no format constraint
# --------------------------------------------------------------------------


async def test_direct_sql_raw_content_hash_omitted_rejected(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["raw_content_hash"]
    column_names = ["id", "fetched_at", *columns.keys()]
    column_values = ["gen_random_uuid()", "now()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO raw_job_ingestions ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_empty_raw_content_hash_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"raw_content_hash": "''"})


async def test_direct_sql_whitespace_wrapped_raw_content_hash_rejected(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"raw_content_hash": r"E'\thash\n'"})


async def test_raw_content_hash_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    ingestion = make_raw_job_ingestion(
        fetched_at=_FETCHED_AT, raw_content_hash="  MixedCaseHash123  "
    )
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert ingestion.raw_content_hash == "MixedCaseHash123"


async def test_raw_content_hash_arbitrary_non_hex_accepted(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    """No format/length CHECK is applied — deliberately not constraining an
    application-computed value beyond trim/non-empty."""
    ingestion = make_raw_job_ingestion(
        fetched_at=_FETCHED_AT, raw_content_hash="not-a-hex-digest-at-all"
    )
    db_session.add(ingestion)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# processing_status enum
# --------------------------------------------------------------------------


async def test_invalid_processing_status_rejected_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, processing_status="bogus_status")
    db_session.add(ingestion)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_invalid_processing_status_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"processing_status": "'bogus_status'"})


# --------------------------------------------------------------------------
# processing_status / job_occurrence_id consistency — Option B (only the
# safe direction is a database CHECK; see the model/migration docstrings).
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["fetched", "parse_error", "normalized", "identity_conflict"])
async def test_null_occurrence_accepted_for_every_status_on_orm_path(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    status: str,
) -> None:
    """`job_occurrence_id IS NULL` is accepted for every status — including
    `normalized`/`identity_conflict`, which is the documented, DB-permitted
    post-deletion historical state (see the dedicated test below), not just
    the transient `fetched`/`parse_error` states."""
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, processing_status=status)
    db_session.add(ingestion)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", ["fetched", "parse_error", "normalized", "identity_conflict"])
async def test_direct_sql_null_occurrence_accepted_for_every_status(
    db_session: AsyncSession, status: str
) -> None:
    await _assert_direct_sql_insert_accepted(db_session, {"processing_status": f"'{status}'"})


@pytest.mark.parametrize("status", ["fetched", "parse_error"])
async def test_unprocessed_status_with_non_null_occurrence_rejected_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    status: str,
) -> None:
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    ingestion = make_raw_job_ingestion(
        fetched_at=_FETCHED_AT, processing_status=status, job_occurrence_id=occurrence_id
    )
    db_session.add(ingestion)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("status", ["fetched", "parse_error"])
async def test_direct_sql_unprocessed_status_with_non_null_occurrence_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    status: str,
) -> None:
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    await _assert_direct_sql_insert_rejected(
        db_session, {"processing_status": f"'{status}'"}, job_occurrence_id=occurrence_id
    )


@pytest.mark.parametrize("status", ["normalized", "identity_conflict"])
async def test_terminal_status_with_non_null_occurrence_accepted_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    status: str,
) -> None:
    """The normal, fresh-write state Phase 2's persistence service will
    actually produce."""
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    ingestion = make_raw_job_ingestion(
        fetched_at=_FETCHED_AT, processing_status=status, job_occurrence_id=occurrence_id
    )
    db_session.add(ingestion)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", ["normalized", "identity_conflict"])
async def test_direct_sql_terminal_status_with_non_null_occurrence_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    status: str,
) -> None:
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    await _assert_direct_sql_insert_accepted(
        db_session, {"processing_status": f"'{status}'"}, job_occurrence_id=occurrence_id
    )


@pytest.mark.parametrize("status", ["normalized", "identity_conflict"])
async def test_terminal_status_with_null_occurrence_is_db_permitted_for_post_deletion_state(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
    status: str,
) -> None:
    """Not a state Phase 1's schema (or Phase 2's fresh persistence writes)
    would ever choose deliberately — it is the exact historical state
    `ON DELETE SET NULL` produces once a `normalized`/`identity_conflict`
    row's target occurrence is later deleted (see
    `test_deleting_occurrence_sets_ingestion_fk_null_and_preserves_row`
    below). The database must not reject it: enforcing both directions of
    the consistency invariant would turn that `ON DELETE SET NULL` into a
    `CHECK` violation, effectively behaving like `RESTRICT`. Phase 2's own
    persistence-service tests — not this schema-only slice — are
    responsible for proving a *fresh* terminal write always includes a
    non-null occurrence; Phase 1 has no ingestion service to test that
    contract against."""
    ingestion = make_raw_job_ingestion(
        fetched_at=_FETCHED_AT, processing_status=status, job_occurrence_id=None
    )
    db_session.add(ingestion)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# job_occurrence_id FK — nonexistent id, and ON DELETE SET NULL isolation
# --------------------------------------------------------------------------


async def test_nonexistent_job_occurrence_id_rejected(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    ingestion = make_raw_job_ingestion(
        fetched_at=_FETCHED_AT,
        processing_status="normalized",
        job_occurrence_id=uuid.uuid4(),
    )
    db_session.add(ingestion)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_occurrence_sets_ingestion_fk_null_and_preserves_row(
    db_engine: AsyncEngine,
) -> None:
    """Deleting one `JobOccurrence` must null out `job_occurrence_id` on its
    own `RawJobIngestion` row (never delete it — this is an audit trail,
    ADR 0005) while leaving a second, unrelated ingestion row (pointing at
    a different, undeleted occurrence) completely untouched."""
    async with (
        real_committed_raw_job_ingestion(db_engine, fetched_at=_FETCHED_AT) as (
            _session_1,
            _job_id_1,
            occurrence_id_1,
            ingestion_id_1,
        ),
        real_committed_raw_job_ingestion(
            db_engine,
            fetched_at=_FETCHED_AT,
            occurrence_kwargs={"source_url": "https://boards.greenhouse.io/other/jobs/2"},
        ) as (_session_2, _job_id_2, occurrence_id_2, ingestion_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            occurrence_1 = await delete_session.get(JobOccurrence, occurrence_id_1)
            assert occurrence_1 is not None
            await delete_session.delete(occurrence_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            ingestion_1 = await verify_session.get(RawJobIngestion, ingestion_id_1)
            assert ingestion_1 is not None
            assert ingestion_1.job_occurrence_id is None
            assert ingestion_1.processing_status == "normalized"
            assert ingestion_1.raw_payload == {"title": "Backend Engineer"}

            assert await verify_session.get(JobOccurrence, occurrence_id_1) is None

            ingestion_2 = await verify_session.get(RawJobIngestion, ingestion_id_2)
            assert ingestion_2 is not None
            assert ingestion_2.job_occurrence_id == occurrence_id_2

            occurrence_2 = await verify_session.get(JobOccurrence, occurrence_id_2)
            assert occurrence_2 is not None


# --------------------------------------------------------------------------
# raw_payload — NOT NULL top-level-JSON-object CHECK; application-level
# write-once convention, not schema-enforced immutability
# --------------------------------------------------------------------------


async def test_direct_sql_raw_payload_sql_null_rejected(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["raw_payload"]
    column_names = ["id", "fetched_at", *columns.keys()]
    column_values = ["gen_random_uuid()", "now()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO raw_job_ingestions ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_raw_payload_json_null_rejected(db_session: AsyncSession) -> None:
    """A JSON `null` is a valid, non-`NULL` jsonb value — distinct from the
    SQL `NULL` case above — and must still be rejected by the top-level-
    object `CHECK`."""
    await _assert_direct_sql_insert_rejected(db_session, {"raw_payload": "'null'::jsonb"})


async def test_direct_sql_raw_payload_array_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"raw_payload": "'[1, 2, 3]'::jsonb"})


@pytest.mark.parametrize("scalar", ["'\"hello\"'::jsonb", "'42'::jsonb", "'true'::jsonb"])
async def test_direct_sql_raw_payload_scalar_rejected(
    db_session: AsyncSession, scalar: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"raw_payload": scalar})


async def test_raw_payload_representative_object_round_trips_exactly(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    payload = {
        "title": "Senior Backend Engineer",
        "salary": {"min": 120000, "max": 160000, "currency": "USD"},
        "tags": ["python", "postgresql", "remote"],
        "remote": True,
        "notes": None,
    }
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT, raw_payload=payload)
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert ingestion.raw_payload == payload


async def test_raw_payload_unchanged_after_lifecycle_update_in_separate_session(
    db_engine: AsyncEngine,
) -> None:
    """Not an immutability guarantee the schema provides — omitting
    `MutableDict` only means in-place mutation isn't tracked; whole-value
    assignment and direct SQL `UPDATE`s remain possible. This proves the
    application-level write-once *convention* behaviorally: updating the
    lifecycle columns must not alter `raw_payload`, verified via semantic
    (deep) equality after a separate-session reload — PostgreSQL's jsonb
    storage does not preserve source key order, so this is not a byte-for-
    byte comparison."""
    payload = {"title": "Backend Engineer", "location": "Remote"}
    async with real_committed_raw_job_ingestion(
        db_engine,
        fetched_at=_FETCHED_AT,
        raw_payload=payload,
        processing_status="fetched",
        job_occurrence_id=None,
    ) as (session, _job_id, occurrence_id, ingestion_id):
        ingestion = await session.get(RawJobIngestion, ingestion_id)
        assert ingestion is not None
        ingestion.processing_status = "normalized"
        ingestion.job_occurrence_id = occurrence_id
        ingestion.error_message = "reprocessed"
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(RawJobIngestion, ingestion_id)
            assert reloaded is not None
            assert reloaded.processing_status == "normalized"
            assert reloaded.raw_payload == payload


# --------------------------------------------------------------------------
# fetched_at — NOT NULL, no server default
# --------------------------------------------------------------------------


async def test_direct_sql_fetched_at_omitted_rejected(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO raw_job_ingestions ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# created_at / updated_at — standard lifecycle pair, server-defaulted
# --------------------------------------------------------------------------


async def test_direct_sql_created_and_updated_at_default_to_now(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", "fetched_at", *columns.keys()]
    column_values = ["gen_random_uuid()", "now()", *columns.values()]
    result = await db_session.execute(
        text(
            f"INSERT INTO raw_job_ingestions ({', '.join(column_names)}) "
            f"VALUES ({', '.join(column_values)}) RETURNING created_at, updated_at"
        )
    )
    await db_session.commit()
    row = result.one()
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_updated_at_advances_on_real_committed_update(db_engine: AsyncEngine) -> None:
    async with real_committed_raw_job_ingestion(
        db_engine, fetched_at=_FETCHED_AT, processing_status="fetched", job_occurrence_id=None
    ) as (session, _job_id, occurrence_id, ingestion_id):
        ingestion = await session.get(RawJobIngestion, ingestion_id)
        assert ingestion is not None
        original_updated_at = ingestion.updated_at

        ingestion.processing_status = "normalized"
        ingestion.job_occurrence_id = occurrence_id
        await session.commit()
        await session.refresh(ingestion)

        assert ingestion.updated_at > original_updated_at


async def test_timestamps_are_utc_aware(
    db_session: AsyncSession,
    make_raw_job_ingestion: Callable[..., RawJobIngestion],
) -> None:
    ingestion = make_raw_job_ingestion(fetched_at=_FETCHED_AT)
    db_session.add(ingestion)
    await db_session.commit()
    await db_session.refresh(ingestion)

    assert ingestion.fetched_at.tzinfo is not None
    assert ingestion.created_at.tzinfo is not None
    assert ingestion.updated_at.tzinfo is not None
