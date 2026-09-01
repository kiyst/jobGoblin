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
`fetch_greenhouse_jobs_raw`, `_create_database`, `_drop_database_if_exists`,
`_database_exists`, and `_run_alembic_upgrade`'s real subprocess runner are
never invoked here — confirmed by a dedicated grep-based test, mirroring
`test_canary_greenhouse_mapping.py`'s own established pattern. `_run_proof()`
*is* called directly by two orchestration-level tests, but only with every
one of those same functions replaced by a call-recording fake via
`monkeypatch` first, so no real I/O ever occurs even then. The
cleanup/leak-check step is exercised separately through injected fake
`drop`/`check_exists` callables.
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
from app.ingestion.hashing import canonical_json_hash
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


def _mapped_job(discovered_at: datetime, *, unique_suffix: str) -> DiscoveredJob:
    """Builds a `DiscoveredJob` from the committed fixture's descriptive
    fields, but with a synthetic, test-unique `id`/`absolute_url` derived
    from `unique_suffix` — never the real fixture's own stable identifiers
    — so a database-touching test can never collide with the committed
    sample's identity, with another test's identity, or with stale
    leftover data sharing the real fixture's id. The job dict is mutated
    *before* mapping, so `DiscoveredJob.raw`, `source_job_id`, and
    `canonical_url` all derive from the same synthetic values
    automatically: `raw` is exactly this mutated dict, so
    `canonical_json_hash(job.raw)` is already internally consistent with
    `source_job_id`/the URL fields with no separate bookkeeping required.
    Callers that re-observe the *same* synthetic posting twice (e.g. an
    insert then a re-observation) must reuse the same `unique_suffix`;
    callers representing a logically different test must use a distinct
    one."""
    fixture = _load_fixture()
    job_dict = dict(fixture["job"])
    synthetic_id = f"test-{unique_suffix}"
    job_dict["id"] = synthetic_id
    job_dict["absolute_url"] = (
        f"https://boards.greenhouse.io/test-{unique_suffix}/jobs/{synthetic_id}"
    )
    return canary.map_job_to_discovered_job(
        job_dict,
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
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC), unique_suffix="replay-accepts")
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
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC), unique_suffix="replay-rejects")
    provider = live_proof._SingleJobReplayProvider(
        job, source="greenhouse", called_at=job.discovered_at
    )

    with pytest.raises(live_proof.UnsupportedSourceQueryError):
        await provider.discover(SourceQuery(sources=bad_sources))


def test_replay_provider_construction_rejects_a_job_provider_mismatch() -> None:
    job = _mapped_job(
        datetime(2026, 1, 1, tzinfo=UTC), unique_suffix="replay-provider-mismatch"
    ).model_copy(update={"provider": "something_else"})
    with pytest.raises(ValueError, match="job.provider"):
        live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=job.discovered_at)


def test_replay_provider_construction_rejects_a_job_source_mismatch() -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC), unique_suffix="replay-source-mismatch")
    with pytest.raises(ValueError, match="job.source"):
        live_proof._SingleJobReplayProvider(job, source="lever", called_at=job.discovered_at)


async def test_replay_provider_capabilities_and_health() -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC), unique_suffix="replay-caps-health")
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
# _run_proof orchestration — a rejected target must never touch any
# database or network function at all, including cleanup. Every
# database/network-facing function is replaced with a call-recording fake
# via monkeypatch; none of them may ever be invoked in these two tests.
# --------------------------------------------------------------------------


def _patch_all_database_and_network_functions(
    monkeypatch: pytest.MonkeyPatch, calls: list[str]
) -> None:
    async def fake_create(*_args: Any, **_kwargs: Any) -> None:
        calls.append("create")

    async def fake_drop(*_args: Any, **_kwargs: Any) -> None:
        calls.append("drop")

    async def fake_exists(*_args: Any, **_kwargs: Any) -> bool:
        calls.append("exists")
        return False

    def fake_alembic(*_args: Any, **_kwargs: Any) -> live_proof._StepResult:
        calls.append("migrate")
        return live_proof._StepResult("migrate", live_proof._StepStatus.PASS, "")

    async def fake_reachability(*_args: Any, **_kwargs: Any) -> live_proof._StepResult:
        calls.append("reachability")
        return live_proof._StepResult("reachability", live_proof._StepStatus.PASS, "")

    async def fake_fetch(*_args: Any, **_kwargs: Any) -> Any:
        calls.append("fetch")
        raise AssertionError("fetch must never be called when the target is rejected")

    async def fake_pipeline_passes(*_args: Any, **_kwargs: Any) -> live_proof._StepResult:
        calls.append("pipeline")
        return live_proof._StepResult("pipeline", live_proof._StepStatus.PASS, "")

    monkeypatch.setattr(live_proof, "_create_database", fake_create)
    monkeypatch.setattr(live_proof, "_drop_database_if_exists", fake_drop)
    monkeypatch.setattr(live_proof, "_database_exists", fake_exists)
    monkeypatch.setattr(live_proof, "_run_alembic_upgrade", fake_alembic)
    monkeypatch.setattr(live_proof, "_reachability_preflight", fake_reachability)
    monkeypatch.setattr(live_proof.canary, "fetch_greenhouse_jobs_raw", fake_fetch)
    monkeypatch.setattr(live_proof, "_run_two_pipeline_passes", fake_pipeline_passes)


async def test_run_proof_rejects_production_before_touching_any_database_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _patch_all_database_and_network_functions(monkeypatch, calls)
    monkeypatch.setattr(
        live_proof,
        "get_settings",
        lambda: live_proof.Settings(
            database_url="postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin",
            app_env="production",
        ),
    )

    result = await live_proof._run_proof("acme", "Acme")

    assert result is False
    assert calls == [], f"expected zero database/network calls, got {calls}"


async def test_run_proof_rejects_a_remote_host_before_touching_any_database_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _patch_all_database_and_network_functions(monkeypatch, calls)
    monkeypatch.setattr(
        live_proof,
        "get_settings",
        lambda: live_proof.Settings(
            database_url="postgresql+asyncpg://jobgoblin:jobgoblin@remote.example.com:5432/jobgoblin",
            app_env="development",
        ),
    )

    result = await live_proof._run_proof("acme", "Acme")

    assert result is False
    assert calls == [], f"expected zero database/network calls, got {calls}"


# --------------------------------------------------------------------------
# two pipeline.run() passes, offline, against the shared jobgoblin_test
# database — scoped to this test's own natural key only (binding
# requirement: no global-count assertions against a shared database)
# --------------------------------------------------------------------------


async def _capture_identity_scope(
    engine: AsyncEngine, *, board_token: str | None, source_job_id: str | None
) -> dict[str, set[Any]]:
    """A before/after snapshot of every row shape this natural key could
    touch, keyed by id — diffed by the caller (`_delete_new_rows`) to find
    exactly what a `pipeline.run()` call created, even when that call
    itself raised before ever returning a run id (so no id could be
    captured from a return value at all). `CollectionRun`/
    `CollectionRunProviderAttempt` have no natural-key column of their own
    and are snapshotted as the whole table — safe because this suite runs
    single-process and sequentially (no `pytest-xdist`), so no concurrent
    test can create an unrelated row between the "before" and "after"
    snapshots taken within one test."""
    async with AsyncSession(bind=engine) as session:
        collection_run_ids = set((await session.execute(select(CollectionRun.id))).scalars().all())
        occurrence_rows = (
            await session.execute(
                select(JobOccurrence.id, JobOccurrence.job_id).where(
                    JobOccurrence.provider == "ats_scrapers",
                    JobOccurrence.source == "greenhouse",
                    JobOccurrence.source_tenant_id == board_token,
                    JobOccurrence.source_job_id == source_job_id,
                )
            )
        ).all()
        occurrence_ids = {row.id for row in occurrence_rows}
        job_ids = {row.job_id for row in occurrence_rows}
        raw_ids = set(
            (
                await session.execute(
                    select(RawJobIngestion.id).where(
                        RawJobIngestion.provider == "ats_scrapers",
                        RawJobIngestion.source == "greenhouse",
                        RawJobIngestion.source_identifier == source_job_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        conflict_ids: set[Any] = set()
        if raw_ids:
            conflict_ids = set(
                (
                    await session.execute(
                        select(IdentityConflict.id).where(
                            IdentityConflict.incoming_raw_job_ingestion_id.in_(raw_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
    return {
        "collection_run_ids": collection_run_ids,
        "occurrence_ids": occurrence_ids,
        "job_ids": job_ids,
        "raw_ids": raw_ids,
        "conflict_ids": conflict_ids,
    }


async def _delete_new_rows(
    engine: AsyncEngine, before: dict[str, set[Any]], after: dict[str, set[Any]]
) -> None:
    """Deletes exactly the rows present in `after` but absent from
    `before`, in FK-safe order, through a fresh session — recovers every
    row a `pipeline.run()` call committed regardless of whether that call
    itself ever returned normally. `Job` cascades to `JobOccurrence`/
    `UserJob`; `CollectionRun` cascades to `CollectionRunProviderAttempt`.
    `RawJobIngestion`/`IdentityConflict` have no cascade pointing at them
    and are deleted explicitly."""
    async with AsyncSession(bind=engine) as session:
        for conflict_id in after["conflict_ids"] - before["conflict_ids"]:
            existing_conflict = await session.get(IdentityConflict, conflict_id)
            if existing_conflict is not None:
                await session.delete(existing_conflict)
        for raw_id in after["raw_ids"] - before["raw_ids"]:
            existing_raw = await session.get(RawJobIngestion, raw_id)
            if existing_raw is not None:
                await session.delete(existing_raw)
        for run_id in after["collection_run_ids"] - before["collection_run_ids"]:
            existing_run = await session.get(CollectionRun, run_id)
            if existing_run is not None:
                await session.delete(existing_run)
        for job_id in after["job_ids"] - before["job_ids"]:
            existing_job = await session.get(Job, job_id)
            if existing_job is not None:
                await session.delete(existing_job)
        await session.commit()


async def test_two_pipeline_runs_insert_then_update_without_duplication(
    db_engine: AsyncEngine,
) -> None:
    job = _mapped_job(datetime(2026, 1, 1, tzinfo=UTC), unique_suffix="two-runs-insert-update")
    board_token = job.source_tenant_id
    query = SourceQuery(sources=["greenhouse"])
    t1 = job.discovered_at
    t2 = t1 + timedelta(hours=6)

    before = await _capture_identity_scope(
        db_engine, board_token=board_token, source_job_id=job.source_job_id
    )

    try:
        provider1 = live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=t1)
        run1_id = await pipeline.run(
            db_engine, provider1, query, observed_at=t1, clock=FixedClock(t1)
        )

        async with AsyncSession(bind=db_engine) as session:
            run1 = await session.get(CollectionRun, run1_id)
            assert run1 is not None
            assert run1.status == "completed"
            assert run1.jobs_discovered == 1
            assert run1.jobs_inserted == 1
            assert run1.jobs_updated == 0
            assert run1.completed_at is not None
            assert run1.completed_at >= run1.started_at

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
            assert attempts[0].provider == "ats_scrapers"
            assert attempts[0].source == "greenhouse"
            assert attempts[0].status == "completed"
            assert attempts[0].jobs_inserted == 1
            assert attempts[0].jobs_updated == 0

            occurrence = (
                await session.execute(
                    select(JobOccurrence).where(
                        JobOccurrence.provider == "ats_scrapers",
                        JobOccurrence.source == "greenhouse",
                        JobOccurrence.source_tenant_id == board_token,
                        JobOccurrence.source_job_id == job.source_job_id,
                    )
                )
            ).scalar_one()
            occurrence_id = occurrence.id
            job_id = occurrence.job_id
            assert occurrence.first_seen_at == t1
            assert occurrence.last_seen_at == t1
            assert occurrence.is_active is True

            job_row_after_run1 = await session.get(Job, job_id)
            assert job_row_after_run1 is not None
            assert job_row_after_run1.title == live_proof._as_stored(job.title)
            assert job_row_after_run1.location_raw == live_proof._as_stored(job.location)
            assert job_row_after_run1.compensation_text == live_proof._as_stored(
                job.compensation_text
            )
            assert job_row_after_run1.canonical_url == live_proof._as_stored(job.canonical_url)

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
            assert len(raw_rows) == 1
            assert raw_rows[0].processing_status == "normalized"
            assert raw_rows[0].job_occurrence_id == occurrence_id
            assert raw_rows[0].raw_content_hash == canonical_json_hash(job.raw)

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
            assert attempts2[0].provider == "ats_scrapers"
            assert attempts2[0].source == "greenhouse"
            assert attempts2[0].status == "completed"
            assert attempts2[0].jobs_inserted == 0
            assert attempts2[0].jobs_updated == 1

            occurrences = (
                (
                    await session.execute(
                        select(JobOccurrence).where(
                            JobOccurrence.provider == "ats_scrapers",
                            JobOccurrence.source == "greenhouse",
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
            assert len(raw_rows) == 2
            for raw in raw_rows:
                assert raw.processing_status == "normalized"
                assert raw.job_occurrence_id == occurrence_id
                assert raw.raw_content_hash == canonical_json_hash(job.raw)
                assert raw.source_identifier == job.source_job_id

            job_row = await session.get(Job, job_id)
            assert job_row is not None
            assert job_row.title == live_proof._as_stored(job.title)
            assert job_row.location_raw == live_proof._as_stored(job.location)
            assert job_row.compensation_text == live_proof._as_stored(job.compensation_text)
            assert job_row.canonical_url == live_proof._as_stored(job.canonical_url)
            assert job_row.first_seen_at == t1
            assert job_row.last_seen_at == t2

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
        after = await _capture_identity_scope(
            db_engine, board_token=board_token, source_job_id=job.source_job_id
        )
        await _delete_new_rows(db_engine, before, after)


async def test_cleanup_removes_every_row_even_when_an_assertion_fails_afterward(
    db_engine: AsyncEngine,
) -> None:
    """Deliberately fails after run 1 to prove cleanup still runs, then
    re-queries through a *fresh* session/connection to prove nothing was
    left behind — not merely that cleanup was *called*."""
    job = _mapped_job(
        datetime(2026, 1, 2, tzinfo=UTC), unique_suffix="cleanup-after-assertion-failure"
    )
    board_token = job.source_tenant_id
    query = SourceQuery(sources=["greenhouse"])
    t1 = job.discovered_at

    before = await _capture_identity_scope(
        db_engine, board_token=board_token, source_job_id=job.source_job_id
    )

    with pytest.raises(AssertionError, match="deliberate failure"):
        try:
            provider = live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=t1)
            await pipeline.run(db_engine, provider, query, observed_at=t1, clock=FixedClock(t1))
            raise AssertionError("deliberate failure to prove cleanup still runs")
        finally:
            after = await _capture_identity_scope(
                db_engine, board_token=board_token, source_job_id=job.source_job_id
            )
            await _delete_new_rows(db_engine, before, after)

    final = await _capture_identity_scope(
        db_engine, board_token=board_token, source_job_id=job.source_job_id
    )
    assert final == before


async def test_cleanup_recovers_rows_left_by_a_pipeline_run_that_raises_mid_transaction(
    db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`pipeline.run()` commits its `CollectionRun`/
    `CollectionRunProviderAttempt` insert, then each job's
    `RawJobIngestion` row, as separate already-committed sub-transactions
    *before* `persist_posting` ever runs — so a failure inside
    `persist_posting` itself still leaves those earlier rows committed even
    though `pipeline.run()` never returns a run id at all. Monkeypatching
    `pipeline.persist_posting` to raise reproduces exactly that gap, and
    proves the before/after snapshot approach (not a return-value-derived
    id list) recovers every row regardless."""
    job = _mapped_job(
        datetime(2026, 1, 4, tzinfo=UTC), unique_suffix="cleanup-mid-transaction-failure"
    )
    board_token = job.source_tenant_id
    query = SourceQuery(sources=["greenhouse"])
    t1 = job.discovered_at

    before = await _capture_identity_scope(
        db_engine, board_token=board_token, source_job_id=job.source_job_id
    )

    async def _raise_after_commit(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("deliberate failure after a committed sub-transaction")

    monkeypatch.setattr(pipeline, "persist_posting", _raise_after_commit)

    provider = live_proof._SingleJobReplayProvider(job, source="greenhouse", called_at=t1)
    try:
        with pytest.raises(RuntimeError, match="deliberate failure"):
            await pipeline.run(db_engine, provider, query, observed_at=t1, clock=FixedClock(t1))
    finally:
        after = await _capture_identity_scope(
            db_engine, board_token=board_token, source_job_id=job.source_job_id
        )
        # Prove the gap was genuinely reproduced — an orphaned
        # RawJobIngestion and a failed CollectionRun really were left
        # behind — before cleanup removes the evidence.
        assert after["raw_ids"] - before["raw_ids"], "expected an orphaned RawJobIngestion row"
        assert (
            after["collection_run_ids"] - before["collection_run_ids"]
        ), "expected a failed CollectionRun row"
        assert not (
            after["job_ids"] - before["job_ids"]
        ), "persist_posting never ran; no Job should have been created"
        await _delete_new_rows(db_engine, before, after)

    final = await _capture_identity_scope(
        db_engine, board_token=board_token, source_job_id=job.source_job_id
    )
    assert final == before


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
