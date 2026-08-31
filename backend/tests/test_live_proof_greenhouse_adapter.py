"""Offline unit tests for `scripts/live_proof_greenhouse_ingestion.py`'s
pure/injectable pieces — the replay adapter, disposable-database-name
generation and identifier quoting, the cleanup/leak-check step, and CLI
argument parsing. Also exercises the full two-`pipeline.run()` insert/
re-observation flow against the real, already-migrated `jobgoblin_test`
database (via `db_engine`), scoped entirely to this test's own natural key
— never asserting global table counts, since `jobgoblin_test` is shared
across the whole suite (binding requirement; only the manually-invoked live
proof's own freshly created, isolated disposable database may assert
global counts).

**No test in this file ever performs a real `CREATE DATABASE`/
`DROP DATABASE`, subprocess invocation, or network request.** `main()`,
`_run_proof()`, `fetch_greenhouse_jobs_raw`, `_create_database`,
`_drop_database_if_exists`, `_database_exists`, and `_run_alembic_upgrade`'s
real subprocess runner are never invoked here — confirmed by a dedicated
grep-based test, mirroring `test_canary_greenhouse_mapping.py`'s own
established pattern. The cleanup/leak-check step is exercised entirely
through injected fake `drop`/`check_exists` callables instead.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import (
    CollectionRun,
    CollectionRunProviderAttempt,
    IdentityConflict,
    Job,
    JobOccurrence,
    RawJobIngestion,
    UserJob,
)
from app.ingestion import pipeline
from app.ingestion.clock import FixedClock
from app.schemas.discovered_job import DiscoveredJob, SourceRunStats
from app.schemas.provider import SourceQuery
from scripts import canary_greenhouse as canary
from scripts import live_proof_greenhouse_ingestion as live_proof

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "discovery" / "greenhouse_live_canary.json"
)


def _load_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data


def _mapped_job(discovered_at: datetime) -> DiscoveredJob:
    fixture = _load_fixture()
    return canary.map_job_to_discovered_job(
        dict(fixture["job"]),
        board_token=fixture["board_token"],
        company=fixture["company"],
        discovered_at=discovered_at,
    )


# --------------------------------------------------------------------------
# disposable database name generation / identifier quoting
# --------------------------------------------------------------------------


def test_generate_database_name_matches_the_expected_grammar() -> None:
    name = live_proof._generate_database_name()
    assert name.startswith(live_proof.DISPOSABLE_NAME_PREFIX)
    suffix = name[len(live_proof.DISPOSABLE_NAME_PREFIX) :]
    assert len(suffix) == live_proof._NAME_HEX_LENGTH
    assert all(c in "0123456789abcdef" for c in suffix)


def test_generate_database_name_contains_the_test_marker() -> None:
    assert "test" in live_proof._generate_database_name()


def test_generate_database_name_is_not_deterministic() -> None:
    assert live_proof._generate_database_name() != live_proof._generate_database_name()


def test_quote_identifier_accepts_a_genuinely_generated_name() -> None:
    name = live_proof._generate_database_name()
    assert live_proof._quote_identifier(name) == f'"{name}"'


@pytest.mark.parametrize(
    "bad_name",
    [
        live_proof.DISPOSABLE_NAME_PREFIX + "g" * 16,  # 'g' is not hex
        live_proof.DISPOSABLE_NAME_PREFIX + "a" * 15,  # too short
        live_proof.DISPOSABLE_NAME_PREFIX + "a" * 17,  # too long
        "different_prefix_" + "a" * 16,
        live_proof.DISPOSABLE_NAME_PREFIX[:-1] + '"; DROP DATABASE jobgoblin; --',
        "",
    ],
)
def test_quote_identifier_rejects_anything_not_matching_the_generated_grammar(
    bad_name: str,
) -> None:
    with pytest.raises(ValueError, match="unexpected database name shape"):
        live_proof._quote_identifier(bad_name)


# --------------------------------------------------------------------------
# _SingleJobReplayProvider
# --------------------------------------------------------------------------


async def test_replay_provider_accepts_the_exact_matching_query() -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC))
    provider = live_proof._SingleJobReplayProvider(
        job, source="greenhouse", called_at=job.discovered_at
    )

    result = await provider.discover(SourceQuery(sources=["greenhouse"]))

    assert result.provider == provider.name == "ats_scrapers" == canary.DISCOVERED_JOB_PROVIDER
    assert result.jobs == [job]
    assert result.jobs[0] is job  # the exact same in-memory object, never a copy
    assert result.source_stats == [
        SourceRunStats(source="greenhouse", completed=True, jobs_found=1)
    ]
    assert result.possibly_incomplete is False


@pytest.mark.parametrize("bad_sources", [["indeed"], ["greenhouse", "lever"], [], ["Greenhouse"]])
async def test_replay_provider_rejects_any_non_matching_query(bad_sources: list[str]) -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC))
    provider = live_proof._SingleJobReplayProvider(
        job, source="greenhouse", called_at=job.discovered_at
    )

    with pytest.raises(live_proof.UnsupportedSourceQueryError):
        await provider.discover(SourceQuery(sources=bad_sources))


def test_replay_provider_construction_rejects_a_job_provider_mismatch() -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC)).model_copy(
        update={"provider": "something_else"}
    )
    with pytest.raises(ValueError, match="job.provider"):
        live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=job.discovered_at)


def test_replay_provider_construction_rejects_a_job_source_mismatch() -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="job.source"):
        live_proof._SingleJobReplayProvider(job, source="lever", called_at=job.discovered_at)


async def test_replay_provider_capabilities_and_health() -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC))
    provider = live_proof._SingleJobReplayProvider(
        job, source="greenhouse", called_at=job.discovered_at
    )

    caps = provider.capabilities()
    assert caps.provider == "ats_scrapers"
    assert set(caps.sources) == {"greenhouse"}

    health = await provider.health()
    assert health.healthy is True
    assert health.provider == "ats_scrapers"
    assert len(health.sources) == 1
    assert health.sources[0].source == "greenhouse"
    assert health.sources[0].healthy is True


# --------------------------------------------------------------------------
# cleanup / leak-check step — injected fakes only, never a real database
# --------------------------------------------------------------------------


async def test_perform_cleanup_reports_pass_when_drop_and_leak_check_both_succeed() -> None:
    async def drop() -> None:
        return None

    async def check_exists() -> bool:
        return False

    steps = await live_proof._perform_cleanup(drop=drop, check_exists=check_exists, name="x")

    assert all(step.status is live_proof._StepStatus.PASS for step in steps)
    assert {step.name for step in steps} == {
        "cleanup: drop disposable database",
        "cleanup: leak check",
    }


async def test_perform_cleanup_reports_fail_when_drop_raises() -> None:
    async def drop() -> None:
        raise RuntimeError("boom")

    async def check_exists() -> bool:
        return False

    steps = await live_proof._perform_cleanup(drop=drop, check_exists=check_exists, name="x")

    by_name = {step.name: step for step in steps}
    assert by_name["cleanup: drop disposable database"].status is live_proof._StepStatus.FAIL
    assert by_name["cleanup: drop disposable database"].detail == "RuntimeError"
    # The leak check must still be attempted despite the drop failure.
    assert by_name["cleanup: leak check"].status is live_proof._StepStatus.PASS


async def test_perform_cleanup_reports_fail_when_leak_check_finds_database_still_present() -> None:
    async def drop() -> None:
        return None

    async def check_exists() -> bool:
        return True

    steps = await live_proof._perform_cleanup(
        drop=drop, check_exists=check_exists, name="leaked_db_name"
    )

    by_name = {step.name: step for step in steps}
    assert by_name["cleanup: drop disposable database"].status is live_proof._StepStatus.PASS
    assert by_name["cleanup: leak check"].status is live_proof._StepStatus.FAIL
    assert "leaked_db_name" in by_name["cleanup: leak check"].detail


async def test_perform_cleanup_leak_check_still_attempted_after_a_drop_failure() -> None:
    async def drop() -> None:
        raise RuntimeError("boom")

    checked: list[bool] = []

    async def check_exists() -> bool:
        checked.append(True)
        return False

    await live_proof._perform_cleanup(drop=drop, check_exists=check_exists, name="x")

    assert checked, "leak check was never attempted after the drop raised"


def test_print_summary_is_false_when_any_step_fails() -> None:
    results = [
        live_proof._StepResult("a", live_proof._StepStatus.PASS, ""),
        live_proof._StepResult("cleanup: leak check", live_proof._StepStatus.FAIL, "leaked"),
    ]
    assert live_proof._print_summary(results) is False


def test_print_summary_is_true_only_when_every_step_including_cleanup_passes() -> None:
    results = [
        live_proof._StepResult("a", live_proof._StepStatus.PASS, ""),
        live_proof._StepResult(
            "cleanup: drop disposable database", live_proof._StepStatus.PASS, ""
        ),
        live_proof._StepResult("cleanup: leak check", live_proof._StepStatus.PASS, ""),
    ]
    assert live_proof._print_summary(results) is True


def test_print_summary_is_false_when_results_list_is_empty_of_a_pass() -> None:
    """A cleanup failure alone, with no other steps, must still fail the
    overall result — `all()` over an empty-of-PASS list is never trivially
    true here since the list is never actually empty in real use, but this
    guards the exact `all(...)` semantics directly."""
    results = [
        live_proof._StepResult(
            "cleanup: drop disposable database", live_proof._StepStatus.FAIL, "x"
        )
    ]
    assert live_proof._print_summary(results) is False


# --------------------------------------------------------------------------
# CLI argument parsing — the confirmation flag is mandatory
# --------------------------------------------------------------------------


def test_parse_args_requires_the_confirmation_flag() -> None:
    with pytest.raises(SystemExit):
        live_proof._parse_args(["--board-token", "acme", "--company", "Acme"])


def test_parse_args_accepts_when_the_confirmation_flag_is_present() -> None:
    args = live_proof._parse_args(
        [
            "--board-token",
            "acme",
            "--company",
            "Acme",
            "--confirm-create-and-drop-local-test-database",
        ]
    )
    assert args.confirm_create_and_drop_local_test_database is True


# --------------------------------------------------------------------------
# two pipeline.run() passes, offline, against the shared jobgoblin_test
# database — scoped to this test's own natural key only (binding
# requirement: no global-count assertions against a shared database)
# --------------------------------------------------------------------------


async def _cleanup_scoped(
    engine: AsyncEngine,
    *,
    collection_run_ids: list[Any],
    job_ids: list[Any],
    raw_ingestion_ids: list[Any],
) -> None:
    """Deletes only what this test itself created, in FK-safe order —
    mirrors `test_ingestion_pipeline.py`'s own established `_cleanup`
    helper. `Job` cascades to `JobOccurrence`/`UserJob`; `CollectionRun`
    cascades to `CollectionRunProviderAttempt`. `RawJobIngestion`/
    `IdentityConflict` have no cascade pointing at them and are deleted
    explicitly. Always runs through a fresh session, so it succeeds even
    after an earlier session's transaction failed or was never committed.
    """
    async with AsyncSession(bind=engine) as session:
        if raw_ingestion_ids:
            conflicts = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.incoming_raw_job_ingestion_id.in_(raw_ingestion_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            for conflict in conflicts:
                await session.delete(conflict)
        for raw_id in raw_ingestion_ids:
            existing = await session.get(RawJobIngestion, raw_id)
            if existing is not None:
                await session.delete(existing)
        for run_id in collection_run_ids:
            existing_run = await session.get(CollectionRun, run_id)
            if existing_run is not None:
                await session.delete(existing_run)
        for job_id in job_ids:
            existing_job = await session.get(Job, job_id)
            if existing_job is not None:
                await session.delete(existing_job)
        await session.commit()


async def test_two_pipeline_runs_insert_then_update_without_duplication(
    db_engine: AsyncEngine,
) -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC))
    board_token = job.source_tenant_id
    query = SourceQuery(sources=["greenhouse"])
    t1 = job.discovered_at
    t2 = t1 + timedelta(hours=6)

    collection_run_ids: list[Any] = []
    job_ids: list[Any] = []
    raw_ingestion_ids: list[Any] = []

    try:
        provider1 = live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=t1)
        run1_id = await pipeline.run(
            db_engine, provider1, query, observed_at=t1, clock=FixedClock(t1)
        )
        collection_run_ids.append(run1_id)

        async with AsyncSession(bind=db_engine) as session:
            run1 = await session.get(CollectionRun, run1_id)
            assert run1 is not None
            assert run1.status == "completed"
            assert run1.jobs_discovered == 1
            assert run1.jobs_inserted == 1
            assert run1.jobs_updated == 0

            attempts = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run1_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts) == 1
            assert attempts[0].jobs_inserted == 1
            assert attempts[0].jobs_updated == 0

            occurrence = (
                await session.execute(
                    select(JobOccurrence).where(
                        JobOccurrence.source_tenant_id == board_token,
                        JobOccurrence.source_job_id == job.source_job_id,
                    )
                )
            ).scalar_one()
            job_ids.append(occurrence.job_id)
            occurrence_id = occurrence.id
            job_id = occurrence.job_id
            assert occurrence.first_seen_at == t1
            assert occurrence.last_seen_at == t1
            assert occurrence.is_active is True

            raw_rows = (
                (
                    await session.execute(
                        select(RawJobIngestion).where(
                            RawJobIngestion.provider == "ats_scrapers",
                            RawJobIngestion.source == "greenhouse",
                            RawJobIngestion.source_identifier == job.source_job_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            raw_ingestion_ids.extend(row.id for row in raw_rows)
            assert len(raw_rows) == 1
            assert raw_rows[0].processing_status == "normalized"

            conflicts = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.existing_job_occurrence_id == occurrence_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert conflicts == []

        provider2 = live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=t2)
        run2_id = await pipeline.run(
            db_engine, provider2, query, observed_at=t2, clock=FixedClock(t2)
        )
        collection_run_ids.append(run2_id)

        async with AsyncSession(bind=db_engine) as session:
            run2 = await session.get(CollectionRun, run2_id)
            assert run2 is not None
            assert run2.status == "completed"
            assert run2.jobs_discovered == 1
            assert run2.jobs_inserted == 0
            assert run2.jobs_updated == 1

            attempts2 = (
                (
                    await session.execute(
                        select(CollectionRunProviderAttempt).where(
                            CollectionRunProviderAttempt.collection_run_id == run2_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(attempts2) == 1
            assert attempts2[0].jobs_inserted == 0
            assert attempts2[0].jobs_updated == 1

            occurrences = (
                (
                    await session.execute(
                        select(JobOccurrence).where(
                            JobOccurrence.source_tenant_id == board_token,
                            JobOccurrence.source_job_id == job.source_job_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(occurrences) == 1, "a second occurrence was created (duplicate)"
            occurrence = occurrences[0]
            assert occurrence.id == occurrence_id
            assert occurrence.job_id == job_id
            assert occurrence.first_seen_at == t1
            assert occurrence.last_seen_at == t2
            assert occurrence.is_active is True
            # Natural key / descriptive fields unchanged by re-observation.
            assert occurrence.provider == "ats_scrapers"
            assert occurrence.source == "greenhouse"
            assert occurrence.source_tenant_id == board_token
            assert occurrence.source_job_id == job.source_job_id
            assert occurrence.canonical_url == job.canonical_url

            raw_rows = (
                (
                    await session.execute(
                        select(RawJobIngestion).where(
                            RawJobIngestion.provider == "ats_scrapers",
                            RawJobIngestion.source == "greenhouse",
                            RawJobIngestion.source_identifier == job.source_job_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            raw_ingestion_ids = [row.id for row in raw_rows]
            assert len(raw_rows) == 2
            assert {row.processing_status for row in raw_rows} == {"normalized"}

            job_row = await session.get(Job, job_id)
            assert job_row is not None
            assert job_row.last_seen_at == t2
            assert job_row.first_seen_at == t1

            conflicts = (
                (
                    await session.execute(
                        select(IdentityConflict).where(
                            IdentityConflict.existing_job_occurrence_id == occurrence_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert conflicts == []
            user_jobs = (
                (await session.execute(select(UserJob).where(UserJob.job_id == job_id)))
                .scalars()
                .all()
            )
            assert user_jobs == []
    finally:
        await _cleanup_scoped(
            db_engine,
            collection_run_ids=collection_run_ids,
            job_ids=job_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )


async def test_cleanup_removes_every_row_even_when_an_assertion_fails_afterward(
    db_engine: AsyncEngine,
) -> None:
    """Deliberately fails after run 1 to prove the `finally` cleanup still
    runs, then re-queries through a *fresh* session/connection to prove
    nothing was left behind — not merely that cleanup was *called*."""
    job = _mapped_job(datetime(2026, 1, 2, tzinfo=UTC))
    board_token = job.source_tenant_id
    query = SourceQuery(sources=["greenhouse"])
    t1 = job.discovered_at

    collection_run_ids: list[Any] = []
    job_ids: list[Any] = []
    raw_ingestion_ids: list[Any] = []

    with pytest.raises(AssertionError, match="deliberate failure"):
        try:
            provider = live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=t1)
            run_id = await pipeline.run(
                db_engine, provider, query, observed_at=t1, clock=FixedClock(t1)
            )
            collection_run_ids.append(run_id)

            async with AsyncSession(bind=db_engine) as session:
                occurrence = (
                    await session.execute(
                        select(JobOccurrence).where(
                            JobOccurrence.source_tenant_id == board_token,
                            JobOccurrence.source_job_id == job.source_job_id,
                        )
                    )
                ).scalar_one()
                job_ids.append(occurrence.job_id)
                raw_rows = (
                    (
                        await session.execute(
                            select(RawJobIngestion).where(
                                RawJobIngestion.provider == "ats_scrapers",
                                RawJobIngestion.source == "greenhouse",
                                RawJobIngestion.source_identifier == job.source_job_id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                raw_ingestion_ids.extend(row.id for row in raw_rows)

            raise AssertionError("deliberate failure to prove cleanup still runs")
        finally:
            await _cleanup_scoped(
                db_engine,
                collection_run_ids=collection_run_ids,
                job_ids=job_ids,
                raw_ingestion_ids=raw_ingestion_ids,
            )

    async with AsyncSession(bind=db_engine) as session:
        remaining_occurrences = (
            (
                await session.execute(
                    select(JobOccurrence).where(
                        JobOccurrence.source_tenant_id == board_token,
                        JobOccurrence.source_job_id == job.source_job_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert remaining_occurrences == []
        assert await session.get(CollectionRun, collection_run_ids[0]) is None
        assert await session.get(Job, job_ids[0]) is None


# --------------------------------------------------------------------------
# no test in this file (or scripts/verify.py) ever contacts Greenhouse or a
# real database lifecycle function
# --------------------------------------------------------------------------


def test_this_test_file_never_calls_the_real_network_or_database_lifecycle_functions() -> None:
    """Scans this file's own source, *excluding this test's own body*
    (which necessarily names the forbidden calls as literal strings to
    check for) — everything above this function's definition is every
    other test in the file."""
    source = Path(__file__).read_text(encoding="utf-8")
    boundary = source.index(
        "def test_this_test_file_never_calls_the_real_network_or_database_lifecycle_functions"
    )
    source_excluding_this_test = source[:boundary]
    forbidden_calls = [
        "fetch_greenhouse_jobs_raw(",
        "live_proof.main(",
        "live_proof._run_proof(",
        "live_proof._create_database(",
        "live_proof._drop_database_if_exists(",
        "live_proof._database_exists(",
        "live_proof._run_alembic_upgrade(",
    ]
    for forbidden in forbidden_calls:
        assert forbidden not in source_excluding_this_test, f"found forbidden call: {forbidden}"


def test_verify_py_never_references_the_live_proof_module() -> None:
    verify_source = (Path(__file__).resolve().parents[1] / "scripts" / "verify.py").read_text(
        encoding="utf-8"
    )
    assert "live_proof_greenhouse_ingestion" not in verify_source
