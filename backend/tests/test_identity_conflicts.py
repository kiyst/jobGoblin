import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import TextClause, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import IdentityConflict, Job, JobOccurrence, RawJobIngestion
from tests.conftest import real_committed_identity_conflict

_AT = datetime(2026, 1, 1, tzinfo=UTC)
_RESOLVED_AT = datetime(2030, 1, 1, tzinfo=UTC)

_EVIDENCE_MISMATCH_VALUE = '\'{"canonical_url_normalized": "https://example.com/old"}\'::jsonb'
_AMBIGUOUS_MATCH_VALUE = '\'["job-1", "job-2"]\'::jsonb'


async def _insert_job_occurrence(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> uuid.UUID:
    """Returns a real, committed `JobOccurrence`'s id (creating its parent
    `Job` first) — captured immediately after its own commit, matching
    `test_job_occurrences.py::_insert_job`'s rationale about attribute
    expiry after a later commit."""
    job = make_job(first_seen_at=_AT, last_seen_at=_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    job_id = job.id

    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_AT, last_seen_at=_AT)
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)
    return occurrence.id


_DIRECT_SQL_BASE_COLUMNS = {
    "conflict_type": "'evidence_mismatch'",
    "existing_value": _EVIDENCE_MISMATCH_VALUE,
    "incoming_value": _EVIDENCE_MISMATCH_VALUE,
    "status": "'open'",
}


def _direct_sql_insert_statement(
    overrides: dict[str, str],
    *,
    existing_job_occurrence_id: uuid.UUID | None = None,
    incoming_raw_job_ingestion_id: uuid.UUID | None = None,
) -> tuple[TextClause, dict[str, object]]:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    params: dict[str, object] = {}
    if existing_job_occurrence_id is not None:
        column_names.append("existing_job_occurrence_id")
        column_values.append(":existing_job_occurrence_id")
        params["existing_job_occurrence_id"] = existing_job_occurrence_id
    if incoming_raw_job_ingestion_id is not None:
        column_names.append("incoming_raw_job_ingestion_id")
        column_values.append(":incoming_raw_job_ingestion_id")
        params["incoming_raw_job_ingestion_id"] = incoming_raw_job_ingestion_id
    stmt = text(
        f"INSERT INTO identity_conflicts ({', '.join(column_names)}) "
        f"VALUES ({', '.join(column_values)})"
    )
    return stmt, params


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession,
    overrides: dict[str, str],
    *,
    existing_job_occurrence_id: uuid.UUID | None = None,
    incoming_raw_job_ingestion_id: uuid.UUID | None = None,
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id` is always supplied; `conflict_type`/`existing_value`/
    `incoming_value`/`status` default to a valid row and are replaced (not
    duplicated) by any of the same keys in `overrides`. Asserts PostgreSQL
    itself rejects the insert, and that the session recovers."""
    stmt, params = _direct_sql_insert_statement(
        overrides,
        existing_job_occurrence_id=existing_job_occurrence_id,
        incoming_raw_job_ingestion_id=incoming_raw_job_ingestion_id,
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(stmt.bindparams(**params) if params else stmt)
        await db_session.commit()
    await db_session.rollback()


async def _assert_direct_sql_insert_accepted(
    db_session: AsyncSession,
    overrides: dict[str, str],
    *,
    existing_job_occurrence_id: uuid.UUID | None = None,
    incoming_raw_job_ingestion_id: uuid.UUID | None = None,
) -> None:
    stmt, params = _direct_sql_insert_statement(
        overrides,
        existing_job_occurrence_id=existing_job_occurrence_id,
        incoming_raw_job_ingestion_id=incoming_raw_job_ingestion_id,
    )
    await db_session.execute(stmt.bindparams(**params) if params else stmt)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# Baseline
# --------------------------------------------------------------------------


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (
        await db_session.execute(select(func.count()).select_from(IdentityConflict))
    ).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_conflict(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict()
    db_session.add(conflict)
    await db_session.commit()
    await db_session.refresh(conflict)

    assert isinstance(conflict.id, uuid.UUID)

    fetched = await db_session.get(IdentityConflict, conflict.id)
    assert fetched is not None
    assert fetched.existing_job_occurrence_id is None
    assert fetched.incoming_raw_job_ingestion_id is None
    assert fetched.conflict_type == "evidence_mismatch"
    assert fetched.existing_value == {"canonical_url_normalized": "https://example.com/old"}
    assert fetched.incoming_value == {"canonical_url_normalized": "https://example.com/new"}
    assert fetched.status == "open"
    assert fetched.resolution is None
    assert fetched.resolved_at is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


# --------------------------------------------------------------------------
# conflict_type / status enums
# --------------------------------------------------------------------------


async def test_invalid_conflict_type_rejected_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(conflict_type="bogus_type")
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_invalid_conflict_type_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"conflict_type": "'bogus_type'"})


async def test_invalid_status_rejected_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(status="bogus_status")
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_invalid_status_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"status": "'bogus_status'"})


async def test_direct_sql_status_omitted_rejected(db_session: AsyncSession) -> None:
    """`status` is NOT NULL with no server default (approved decision 7:
    fresh conflict creation must explicitly supply `'open'`) — an
    otherwise-valid insert that omits the column entirely must be
    rejected by PostgreSQL itself, not merely by application code."""
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns["status"]
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO identity_conflicts ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# status / resolved_at lifecycle consistency matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["resolved", "ignored"])
async def test_terminal_status_with_resolved_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
    status: str,
) -> None:
    conflict = make_identity_conflict(status=status, resolved_at=_RESOLVED_AT)
    db_session.add(conflict)
    await db_session.commit()  # must not raise


@pytest.mark.parametrize("status", ["resolved", "ignored"])
async def test_direct_sql_terminal_status_with_resolved_at_accepted(
    db_session: AsyncSession, status: str
) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session, {"status": f"'{status}'", "resolved_at": "now()"}
    )


async def test_open_status_with_null_resolved_at_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(status="open", resolved_at=None)
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_open_status_with_non_null_resolved_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(status="open", resolved_at=_RESOLVED_AT)
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_open_status_with_non_null_resolved_at_rejected(
    db_session: AsyncSession,
) -> None:
    await _assert_direct_sql_insert_rejected(
        db_session, {"status": "'open'", "resolved_at": "now()"}
    )


@pytest.mark.parametrize("status", ["resolved", "ignored"])
async def test_terminal_status_with_null_resolved_at_rejected_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
    status: str,
) -> None:
    conflict = make_identity_conflict(status=status, resolved_at=None)
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("status", ["resolved", "ignored"])
async def test_direct_sql_terminal_status_with_null_resolved_at_rejected(
    db_session: AsyncSession, status: str
) -> None:
    await _assert_direct_sql_insert_rejected(db_session, {"status": f"'{status}'"})


# --------------------------------------------------------------------------
# resolved_at >= created_at ordering boundary
# --------------------------------------------------------------------------


async def test_direct_sql_resolved_at_equal_created_at_accepted(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session,
        {
            "status": "'resolved'",
            "created_at": "'2026-01-01T00:00:00+00'::timestamptz",
            "resolved_at": "'2026-01-01T00:00:00+00'::timestamptz",
        },
    )


async def test_direct_sql_resolved_at_after_created_at_accepted(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session,
        {
            "status": "'resolved'",
            "created_at": "'2026-01-01T00:00:00+00'::timestamptz",
            "resolved_at": "'2026-01-02T00:00:00+00'::timestamptz",
        },
    )


async def test_direct_sql_resolved_at_before_created_at_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_rejected(
        db_session,
        {
            "status": "'resolved'",
            "created_at": "'2026-01-02T00:00:00+00'::timestamptz",
            "resolved_at": "'2026-01-01T00:00:00+00'::timestamptz",
        },
    )


# --------------------------------------------------------------------------
# existing_value / incoming_value — conflict_type-conditional JSON shape
# --------------------------------------------------------------------------


async def test_evidence_mismatch_object_shapes_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(
        conflict_type="evidence_mismatch",
        existing_value={"canonical_url_normalized": "https://example.com/old"},
        incoming_value={"canonical_url_normalized": "https://example.com/new"},
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_ambiguous_match_array_shapes_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(
        conflict_type="ambiguous_match",
        existing_value=["job-1", "job-2"],
        incoming_value=["job-1", "job-2"],
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_direct_sql_evidence_mismatch_object_shape_accepted(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_accepted(db_session, {})


async def test_direct_sql_ambiguous_match_array_shape_accepted(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session,
        {
            "conflict_type": "'ambiguous_match'",
            "existing_value": _AMBIGUOUS_MATCH_VALUE,
            "incoming_value": _AMBIGUOUS_MATCH_VALUE,
        },
    )


async def test_evidence_mismatch_empty_object_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    """The shape `CHECK` only enforces the top-level JSON type, never
    non-emptiness — an empty object is a valid `evidence_mismatch`
    snapshot as far as the schema is concerned."""
    conflict = make_identity_conflict(
        conflict_type="evidence_mismatch", existing_value={}, incoming_value={}
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_ambiguous_match_empty_array_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    """Same rationale as the empty-object case above, for the array shape."""
    conflict = make_identity_conflict(
        conflict_type="ambiguous_match", existing_value=[], incoming_value=[]
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_direct_sql_evidence_mismatch_empty_object_accepted(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session, {"existing_value": "'{}'::jsonb", "incoming_value": "'{}'::jsonb"}
    )


async def test_direct_sql_ambiguous_match_empty_array_accepted(db_session: AsyncSession) -> None:
    await _assert_direct_sql_insert_accepted(
        db_session,
        {
            "conflict_type": "'ambiguous_match'",
            "existing_value": "'[]'::jsonb",
            "incoming_value": "'[]'::jsonb",
        },
    )


@pytest.mark.parametrize("column", ["existing_value", "incoming_value"])
@pytest.mark.parametrize(
    ("conflict_type", "wrong_shape_json"),
    [
        ("evidence_mismatch", "'[1, 2]'::jsonb"),
        ("evidence_mismatch", "'null'::jsonb"),
        ("evidence_mismatch", "'\"scalar\"'::jsonb"),
        ("evidence_mismatch", "'42'::jsonb"),
        ("ambiguous_match", "'{\"a\": 1}'::jsonb"),
        ("ambiguous_match", "'null'::jsonb"),
        ("ambiguous_match", "'\"scalar\"'::jsonb"),
        ("ambiguous_match", "'42'::jsonb"),
    ],
    ids=[
        "evidence_mismatch-array",
        "evidence_mismatch-json_null",
        "evidence_mismatch-scalar_string",
        "evidence_mismatch-scalar_number",
        "ambiguous_match-object",
        "ambiguous_match-json_null",
        "ambiguous_match-scalar_string",
        "ambiguous_match-scalar_number",
    ],
)
async def test_direct_sql_wrong_shape_rejected(
    db_session: AsyncSession,
    column: str,
    conflict_type: str,
    wrong_shape_json: str,
) -> None:
    other_column = "incoming_value" if column == "existing_value" else "existing_value"
    valid_other_value = (
        _EVIDENCE_MISMATCH_VALUE if conflict_type == "evidence_mismatch" else _AMBIGUOUS_MATCH_VALUE
    )
    await _assert_direct_sql_insert_rejected(
        db_session,
        {
            "conflict_type": f"'{conflict_type}'",
            column: wrong_shape_json,
            other_column: valid_other_value,
        },
    )


@pytest.mark.parametrize("column", ["existing_value", "incoming_value"])
async def test_direct_sql_sql_null_value_rejected(db_session: AsyncSession, column: str) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    del columns[column]
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO identity_conflicts ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            )
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# existing_job_occurrence_id / conflict_type nullness — the safe direction
# only is a CHECK
# --------------------------------------------------------------------------


async def test_ambiguous_match_with_null_occurrence_accepted_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(
        conflict_type="ambiguous_match",
        existing_value=["job-1", "job-2"],
        incoming_value=["job-1", "job-2"],
        existing_job_occurrence_id=None,
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_ambiguous_match_with_non_null_occurrence_rejected_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    conflict = make_identity_conflict(
        conflict_type="ambiguous_match",
        existing_value=["job-1", "job-2"],
        incoming_value=["job-1", "job-2"],
        existing_job_occurrence_id=occurrence_id,
    )
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_ambiguous_match_with_non_null_occurrence_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    await _assert_direct_sql_insert_rejected(
        db_session,
        {
            "conflict_type": "'ambiguous_match'",
            "existing_value": _AMBIGUOUS_MATCH_VALUE,
            "incoming_value": _AMBIGUOUS_MATCH_VALUE,
        },
        existing_job_occurrence_id=occurrence_id,
    )


async def test_evidence_mismatch_with_null_occurrence_is_db_permitted(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    """Not a state a fresh write would deliberately choose, but the
    reverse direction of this invariant is intentionally not a database
    `CHECK` — see the model docstring. Documents that the database
    permits it, the same way `raw_job_ingestions` documents its own
    analogous case."""
    conflict = make_identity_conflict(
        conflict_type="evidence_mismatch", existing_job_occurrence_id=None
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


async def test_evidence_mismatch_with_non_null_occurrence_accepted_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    occurrence_id = await _insert_job_occurrence(db_session, make_job, make_job_occurrence)
    conflict = make_identity_conflict(
        conflict_type="evidence_mismatch", existing_job_occurrence_id=occurrence_id
    )
    db_session.add(conflict)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# incoming_raw_job_ingestion_id — no CHECK of any kind
# --------------------------------------------------------------------------


@pytest.mark.parametrize("conflict_type", ["evidence_mismatch", "ambiguous_match"])
async def test_null_incoming_ingestion_accepted_for_every_conflict_type(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
    conflict_type: str,
) -> None:
    kwargs: dict[str, object] = {
        "conflict_type": conflict_type,
        "incoming_raw_job_ingestion_id": None,
    }
    if conflict_type == "ambiguous_match":
        kwargs["existing_value"] = ["job-1", "job-2"]
        kwargs["incoming_value"] = ["job-1", "job-2"]
    conflict = make_identity_conflict(**kwargs)
    db_session.add(conflict)
    await db_session.commit()  # must not raise


# --------------------------------------------------------------------------
# FK integrity — nonexistent parents rejected
# --------------------------------------------------------------------------


async def test_nonexistent_existing_job_occurrence_id_rejected(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(existing_job_occurrence_id=uuid.uuid4())
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_nonexistent_incoming_raw_job_ingestion_id_rejected(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(incoming_raw_job_ingestion_id=uuid.uuid4())
    db_session.add(conflict)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# Both independent ON DELETE SET NULL cascades — the primary novel tests
# --------------------------------------------------------------------------


async def test_deleting_occurrence_sets_existing_fk_null_and_preserves_row(
    db_engine: AsyncEngine,
) -> None:
    """Deleting the referenced `JobOccurrence` must null only
    `existing_job_occurrence_id`, leave `incoming_raw_job_ingestion_id`
    untouched, and preserve the conflict row — never delete it (ADR 0007).
    A second, unrelated conflict row must be completely unaffected."""
    async with (
        real_committed_identity_conflict(db_engine, at=_AT) as (
            _session_1,
            occurrence_id_1,
            ingestion_id_1,
            conflict_id_1,
        ),
        real_committed_identity_conflict(
            db_engine,
            at=_AT,
            occurrence_kwargs={"source_url": "https://boards.greenhouse.io/other/jobs/2"},
            ingestion_occurrence_kwargs={
                "source_url": "https://boards.greenhouse.io/other-ingestion/jobs/2"
            },
        ) as (_session_2, occurrence_id_2, ingestion_id_2, conflict_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            occurrence_1 = await delete_session.get(JobOccurrence, occurrence_id_1)
            assert occurrence_1 is not None
            await delete_session.delete(occurrence_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            conflict_1 = await verify_session.get(IdentityConflict, conflict_id_1)
            assert conflict_1 is not None
            assert conflict_1.existing_job_occurrence_id is None
            assert conflict_1.incoming_raw_job_ingestion_id == ingestion_id_1

            assert await verify_session.get(JobOccurrence, occurrence_id_1) is None

            conflict_2 = await verify_session.get(IdentityConflict, conflict_id_2)
            assert conflict_2 is not None
            assert conflict_2.existing_job_occurrence_id == occurrence_id_2
            assert conflict_2.incoming_raw_job_ingestion_id == ingestion_id_2

            occurrence_2 = await verify_session.get(JobOccurrence, occurrence_id_2)
            assert occurrence_2 is not None


async def test_deleting_ingestion_sets_incoming_fk_null_and_preserves_row(
    db_engine: AsyncEngine,
) -> None:
    """Deleting the referenced `RawJobIngestion` must null only
    `incoming_raw_job_ingestion_id`, leave `existing_job_occurrence_id`
    untouched, and preserve the conflict row. A second, unrelated conflict
    row must be completely unaffected."""
    async with (
        real_committed_identity_conflict(db_engine, at=_AT) as (
            _session_1,
            occurrence_id_1,
            ingestion_id_1,
            conflict_id_1,
        ),
        real_committed_identity_conflict(
            db_engine,
            at=_AT,
            occurrence_kwargs={"source_url": "https://boards.greenhouse.io/other/jobs/3"},
            ingestion_occurrence_kwargs={
                "source_url": "https://boards.greenhouse.io/other-ingestion/jobs/3"
            },
        ) as (_session_2, occurrence_id_2, ingestion_id_2, conflict_id_2),
    ):
        async with AsyncSession(bind=db_engine) as delete_session:
            ingestion_1 = await delete_session.get(RawJobIngestion, ingestion_id_1)
            assert ingestion_1 is not None
            await delete_session.delete(ingestion_1)
            await delete_session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            conflict_1 = await verify_session.get(IdentityConflict, conflict_id_1)
            assert conflict_1 is not None
            assert conflict_1.incoming_raw_job_ingestion_id is None
            assert conflict_1.existing_job_occurrence_id == occurrence_id_1

            assert await verify_session.get(RawJobIngestion, ingestion_id_1) is None

            conflict_2 = await verify_session.get(IdentityConflict, conflict_id_2)
            assert conflict_2 is not None
            assert conflict_2.incoming_raw_job_ingestion_id == ingestion_id_2
            assert conflict_2.existing_job_occurrence_id == occurrence_id_2


# --------------------------------------------------------------------------
# resolution — nullable, ORM-normalized, no CHECK
# --------------------------------------------------------------------------


async def test_resolution_defaults_to_none(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict()
    db_session.add(conflict)
    await db_session.commit()
    await db_session.refresh(conflict)

    assert conflict.resolution is None


async def test_resolution_whitespace_only_becomes_none_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(resolution="   \t\n  ")
    db_session.add(conflict)
    await db_session.commit()
    await db_session.refresh(conflict)

    assert conflict.resolution is None


async def test_resolution_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(resolution="  Confirmed Different Postings  ")
    db_session.add(conflict)
    await db_session.commit()
    await db_session.refresh(conflict)

    assert conflict.resolution == "Confirmed Different Postings"


async def test_direct_sql_resolution_not_normalized(db_session: AsyncSession) -> None:
    """No `CHECK` backs `resolution` — a direct SQL write bypassing the
    ORM's trim/blank-to-`None` convention is accepted as-is, unlike every
    other nullable text column in this schema."""
    await _assert_direct_sql_insert_accepted(db_session, {"resolution": r"E'\t  \n'"})

    result = await db_session.execute(
        text("SELECT resolution FROM identity_conflicts ORDER BY created_at DESC LIMIT 1")
    )
    stored = result.scalar_one()
    assert stored == "\t  \n"


# --------------------------------------------------------------------------
# existing_value / incoming_value — write-once snapshots, not Mutable-wrapped
# --------------------------------------------------------------------------


async def test_snapshots_unchanged_after_unrelated_lifecycle_update_in_separate_session(
    db_engine: AsyncEngine,
) -> None:
    """Not an immutability guarantee the schema provides — omitting
    `MutableDict`/`MutableList` only means in-place mutation isn't
    tracked. This proves the application-level write-once *convention*
    behaviorally: updating `status`/`resolution` must not alter either
    snapshot, verified via semantic (deep) equality after a separate-
    session reload — PostgreSQL's jsonb storage does not preserve source
    key order."""
    existing_value = {"canonical_url_normalized": "https://example.com/old"}
    incoming_value = {"canonical_url_normalized": "https://example.com/new"}
    async with real_committed_identity_conflict(
        db_engine,
        at=_AT,
        existing_value=existing_value,
        incoming_value=incoming_value,
    ) as (session, _occurrence_id, _ingestion_id, conflict_id):
        conflict = await session.get(IdentityConflict, conflict_id)
        assert conflict is not None
        conflict.status = "resolved"
        conflict.resolved_at = _RESOLVED_AT
        conflict.resolution = "confirmed different postings"
        await session.commit()

        async with AsyncSession(bind=db_engine) as verify_session:
            reloaded = await verify_session.get(IdentityConflict, conflict_id)
            assert reloaded is not None
            assert reloaded.status == "resolved"
            assert reloaded.existing_value == existing_value
            assert reloaded.incoming_value == incoming_value


# --------------------------------------------------------------------------
# created_at / updated_at — standard lifecycle pair, server-defaulted
# --------------------------------------------------------------------------


async def test_direct_sql_created_and_updated_at_default_to_now(db_session: AsyncSession) -> None:
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    column_names = ["id", *columns.keys()]
    column_values = ["gen_random_uuid()", *columns.values()]
    result = await db_session.execute(
        text(
            f"INSERT INTO identity_conflicts ({', '.join(column_names)}) "
            f"VALUES ({', '.join(column_values)}) RETURNING created_at, updated_at"
        )
    )
    await db_session.commit()
    row = result.one()
    assert row.created_at is not None
    assert row.updated_at is not None


async def test_updated_at_advances_on_real_committed_update(db_engine: AsyncEngine) -> None:
    async with real_committed_identity_conflict(db_engine, at=_AT) as (
        session,
        _occurrence_id,
        _ingestion_id,
        conflict_id,
    ):
        conflict = await session.get(IdentityConflict, conflict_id)
        assert conflict is not None
        original_updated_at = conflict.updated_at

        conflict.status = "ignored"
        conflict.resolved_at = _RESOLVED_AT
        await session.commit()
        await session.refresh(conflict)

        assert conflict.updated_at > original_updated_at


async def test_timestamps_are_utc_aware(
    db_session: AsyncSession,
    make_identity_conflict: Callable[..., IdentityConflict],
) -> None:
    conflict = make_identity_conflict(status="resolved", resolved_at=_RESOLVED_AT)
    db_session.add(conflict)
    await db_session.commit()
    await db_session.refresh(conflict)

    assert conflict.created_at.tzinfo is not None
    assert conflict.updated_at.tzinfo is not None
    assert conflict.resolved_at is not None
    assert conflict.resolved_at.tzinfo is not None
