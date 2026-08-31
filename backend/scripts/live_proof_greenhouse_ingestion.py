"""Manually-invoked, opt-in Greenhouse live-to-disposable-database ingestion
proof (Phase 4 prework, Class H). Approved with 17 binding clarifications;
this slice's own `Work done` entry in `docs/LLM_HANDOFF.md` is the durable
record of that approval (see `scripts/canary_greenhouse.py`'s own module
docstring for why no separate proposal document persists there — the same
two-iteration rotation rule applies).

Performs **exactly one** live HTTP request — via `scripts/canary_greenhouse.py`'s
already-approved, unmodified fetch/select/map functions — against Greenhouse's
public Job Board API, then routes that single already-fetched
`DiscoveredJob` through the real `app/ingestion/pipeline.py::run` twice
(insert, then a controlled offline re-observation) against a **freshly
created, migrated, and finally destroyed** disposable PostgreSQL database.
Never touches `jobgoblin`/`jobgoblin_test`.

Never imported by `pytest` or `scripts/verify.py` — this module lives under
`scripts/`, outside `pyproject.toml`'s `testpaths = ["tests"]`, exactly like
`canary_greenhouse.py`. `tests/test_live_proof_greenhouse_adapter.py`
exercises this module's pure/injectable pieces (the adapter, name
generation, the cleanup/leak-check step) entirely offline; it never calls
`main()`, `_run_proof()`, or anything that performs real `CREATE DATABASE`/
`DROP DATABASE`/network I/O.

Safety properties enforced throughout this module (binding requirements):

- **An explicit, required confirmation flag** (`--confirm-create-and-drop-local-test-database`)
  gates everything — `argparse`'s own `required=True` means a missing flag
  exits (code 2) before a single line of this module's own logic runs, let
  alone before any database or network action.
- **The disposable database name is generated internally, never
  caller-supplied** — a fixed safe prefix plus random lowercase hex
  (`_generate_database_name`). No caller input is ever interpolated into
  SQL; the generated name is re-validated against its own exact grammar
  (`_quote_identifier`) immediately before use, as defense in depth even
  though the generator can only ever produce a matching string.
- **Two independent, composed safety guards must pass before the database is
  created, and the database must exist, be migrated, and be reachable
  before the one live network request is made** —
  `scripts.db_safety.assert_safe_for_local_destructive_lifecycle` (disposable
  name + non-production + local-host-only) runs first; every later step is
  skipped (`NOT_RUN`) if it fails.
- **Cleanup (`DROP DATABASE ... WITH (FORCE)`) is always attempted**, via a
  `finally`-equivalent step list identical in spirit to
  `scripts/verify.py`'s own `_execute_and_cleanup` — including a leak check
  that reconnects afterward and confirms the name no longer exists in
  `pg_database`. A cleanup or leak-check failure alone makes the overall
  result non-PASS, printed as its own step, never silently folded into an
  otherwise-green summary. This guarantee holds for ordinary success,
  failure, and Python-level cancellation paths only — it cannot survive
  `SIGKILL`, host termination, or power loss, which no `finally` block can
  ever run under; if that happens, the printed disposable database name
  (safe, credential-free) is the operator's manual-cleanup pointer.
- **Alembic's subprocess output is captured, never printed** — a failure is
  reported as a step name, exit code, and redacted database target only;
  the subprocess's own environment (which carries the credential-bearing
  `DATABASE_URL` override) and its raw stdout/stderr are never included in
  any printed output.
- **The overall summary never prints an overall PASS unless cleanup and the
  leak check also passed** — the same "all steps, including cleanup, must
  be PASS" rule `scripts/verify.py` already established.

    python scripts/live_proof_greenhouse_ingestion.py \\
        --board-token gitlab --company GitLab \\
        --confirm-create-and-drop-local-test-database
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings, get_settings  # noqa: E402
from app.db.models import (  # noqa: E402
    CollectionRun,
    CollectionRunProviderAttempt,
    IdentityConflict,
    Job,
    JobOccurrence,
    RawJobIngestion,
    UserJob,
)
from app.db.session import check_database_connection  # noqa: E402
from app.ingestion import pipeline  # noqa: E402
from app.ingestion.clock import SystemClock  # noqa: E402
from app.ingestion.hashing import canonical_json_hash  # noqa: E402
from app.normalization.url import normalize_url  # noqa: E402
from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult, SourceRunStats  # noqa: E402
from app.schemas.provider import (  # noqa: E402
    ProviderCapabilities,
    ProviderHealth,
    SourceCapabilities,
    SourceHealth,
    SourceQuery,
)
from scripts import canary_greenhouse as canary  # noqa: E402
from scripts.db_safety import (  # noqa: E402
    assert_safe_for_local_destructive_lifecycle,
    redact_database_url,
)

DISPOSABLE_NAME_PREFIX = "jobgoblin_test_live_proof_"
_NAME_HEX_LENGTH = 16
_MAINTENANCE_DATABASE = "postgres"


class _StepStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT RUN"


@dataclass(frozen=True)
class _StepResult:
    name: str
    status: _StepStatus
    detail: str = ""


class UnsupportedSourceQueryError(ValueError):
    """Raised by `_SingleJobReplayProvider.discover()` for any `SourceQuery`
    whose `sources` is not exactly this provider's one supported source —
    a genuine caller/programmer error per `DiscoveryProvider`'s own
    documented contract (`app/providers/base.py`), never something to
    silently ignore or report through `DiscoveryResult.errors`."""


def _generate_database_name() -> str:
    """A fixed safe prefix plus random lowercase hex — never derived from,
    or influenced by, any caller-supplied input. Contains `"test"` (via the
    prefix) so `assert_is_disposable_test_database`'s existing name-based
    guard also accepts it on its own terms, not only via the narrower
    destructive-lifecycle guard."""
    return DISPOSABLE_NAME_PREFIX + secrets.token_hex(_NAME_HEX_LENGTH // 2)


def _quote_identifier(name: str) -> str:
    """Validates `name` against the exact grammar `_generate_database_name`
    can produce, then returns a double-quoted PostgreSQL identifier.
    Never trusts the grammar alone: this function re-validates and raises
    `ValueError` rather than quoting anything that doesn't match, even
    though every real caller only ever passes a freshly generated name.
    Doubling embedded `"` characters is dead code given the validated
    grammar (which contains none) — included anyway as the standard,
    unconditionally-correct PostgreSQL identifier-quoting rule, not as a
    substitute for the grammar check above."""
    expected_length = len(DISPOSABLE_NAME_PREFIX) + _NAME_HEX_LENGTH
    is_valid = (
        len(name) == expected_length
        and name.startswith(DISPOSABLE_NAME_PREFIX)
        and all(c in "0123456789abcdef" for c in name[len(DISPOSABLE_NAME_PREFIX) :])
    )
    if not is_valid:
        raise ValueError(f"refusing to quote an unexpected database name shape: {name!r}")
    return '"' + name.replace('"', '""') + '"'


class _SingleJobReplayProvider:
    """Minimal `DiscoveryProvider` wrapping exactly one already-fetched,
    already-validated `DiscoveredJob` — the live HTTP call and all
    validation/selection/mapping already happened, via
    `scripts/canary_greenhouse.py`'s own unmodified functions, before this
    object is ever constructed. `discover()` itself performs no I/O and
    cannot fail for network reasons; it can only reject a structurally
    unsupported `SourceQuery` (`UnsupportedSourceQueryError`), which is a
    genuine caller error per `DiscoveryProvider`'s own contract, not an
    anticipated runtime failure to report through `DiscoveryResult`.

    Structurally the live-data analogue of `app.providers.fixture.FixtureProvider`.
    """

    name = canary.DISCOVERED_JOB_PROVIDER

    def __init__(self, job: DiscoveredJob, *, source: str, called_at: datetime) -> None:
        if job.provider != self.name:
            raise ValueError(
                f"job.provider {job.provider!r} does not match provider.name {self.name!r}"
            )
        if job.source != source:
            raise ValueError(f"job.source {job.source!r} does not match source={source!r}")
        self._job = job
        self._source = source
        self._called_at = called_at

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        if query.sources != [self._source]:
            raise UnsupportedSourceQueryError(
                f"this provider only supports sources=[{self._source!r}], "
                f"got sources={query.sources!r}"
            )
        stats = [SourceRunStats(source=self._source, completed=True, jobs_found=1)]
        return DiscoveryResult(
            provider=self.name,
            jobs=[self._job],
            source_stats=stats,
            started_at=self._called_at,
            completed_at=self._called_at,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            sources={self._source: SourceCapabilities(source=self._source, max_concurrency=1)},
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            sources=[
                SourceHealth(
                    source=self._source,
                    healthy=True,
                    last_success_at=None,
                    last_failure_at=None,
                    consecutive_failures=0,
                    detail=None,
                )
            ],
            last_checked_at=self._called_at,
        )


def _admin_url(development_url: str, *, database: str) -> str:
    """Same host/port/credentials as the configured `DATABASE_URL`, with
    only the database name swapped — never a separately configured admin
    credential."""
    parsed = make_url(development_url)
    return parsed.set(database=database).render_as_string(hide_password=False)


async def _create_database(admin_url: str, quoted_name: str) -> None:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE DATABASE {quoted_name}"))
    finally:
        await engine.dispose()


async def _drop_database_if_exists(admin_url: str, quoted_name: str) -> None:
    """`WITH (FORCE)` (PostgreSQL 13+) terminates any lingering connections
    to the target database first, so a stray connection left open by an
    earlier failure never blocks cleanup. `IF EXISTS` makes this safe to
    call unconditionally in a cleanup path regardless of how far creation
    actually progressed."""
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {quoted_name} WITH (FORCE)"))
    finally:
        await engine.dispose()


async def _database_exists(admin_url: str, name: str) -> bool:
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name").bindparams(name=name)
            )
            return result.scalar_one_or_none() is not None
    finally:
        await engine.dispose()


SubprocessRunner = Callable[[list[str], dict[str, str]], subprocess.CompletedProcess[str]]


def _default_subprocess_runner(
    argv: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _run_alembic_upgrade(
    database_url: str, *, runner: SubprocessRunner = _default_subprocess_runner
) -> _StepResult:
    """Runs `alembic upgrade head` as a subprocess with `DATABASE_URL`
    overridden in that subprocess's own environment only —
    `migrations/env.py` unconditionally reads `get_settings().database_url`,
    and `get_settings()` is process-wide `@lru_cache`d, so a subprocess is
    the only way to point Alembic at a different URL without monkeypatching
    production config-loading code. Captured stdout/stderr and the
    subprocess's environment (which carries the credential-bearing URL) are
    never included in the returned `detail` — only the exit code and a
    redacted target."""
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    redacted = redact_database_url(database_url)
    try:
        completed = runner([sys.executable, "-m", "alembic", "upgrade", "head"], env)
    except subprocess.TimeoutExpired:
        return _StepResult(
            "migrate disposable database to head",
            _StepStatus.FAIL,
            f"timed out against {redacted}",
        )
    if completed.returncode != 0:
        return _StepResult(
            "migrate disposable database to head",
            _StepStatus.FAIL,
            f"alembic exited {completed.returncode} against {redacted}",
        )
    return _StepResult(
        "migrate disposable database to head", _StepStatus.PASS, f"applied against {redacted}"
    )


async def _reachability_preflight(database_url: str) -> _StepResult:
    settings = Settings(database_url=database_url)
    try:
        await check_database_connection(settings)
    except Exception as exc:
        return _StepResult(
            "disposable database reachability",
            _StepStatus.FAIL,
            f"{type(exc).__name__}: {redact_database_url(database_url)}",
        )
    return _StepResult(
        "disposable database reachability", _StepStatus.PASS, redact_database_url(database_url)
    )


async def _assert_state_after_run_one(
    engine: AsyncEngine, *, run_id: Any, job: DiscoveredJob, board_token: str, observed_at: datetime
) -> tuple[Any, Any]:
    async with AsyncSession(bind=engine) as session:
        collection_run = await session.get(CollectionRun, run_id)
        assert collection_run is not None, "CollectionRun row missing after run 1"
        assert collection_run.status == "completed", f"run 1 status={collection_run.status!r}"
        assert collection_run.jobs_discovered == 1
        assert collection_run.jobs_inserted == 1
        assert collection_run.jobs_updated == 0
        assert collection_run.failures == []

        attempts = (
            (
                await session.execute(
                    select(CollectionRunProviderAttempt).where(
                        CollectionRunProviderAttempt.collection_run_id == run_id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(attempts) == 1, f"expected 1 provider attempt, found {len(attempts)}"
        attempt = attempts[0]
        assert attempt.provider == "ats_scrapers"
        assert attempt.source == "greenhouse"
        assert attempt.status == "completed"
        assert attempt.jobs_discovered == 1
        assert attempt.jobs_inserted == 1
        assert attempt.jobs_updated == 0

        raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
        assert len(raw_rows) == 1, f"expected 1 RawJobIngestion, found {len(raw_rows)}"
        raw = raw_rows[0]
        assert raw.processing_status == "normalized"
        assert raw.job_occurrence_id is not None
        assert raw.raw_content_hash == canonical_json_hash(job.raw)
        assert raw.source_identifier == job.source_job_id

        jobs = (await session.execute(select(Job))).scalars().all()
        assert len(jobs) == 1, f"expected 1 Job, found {len(jobs)}"
        job_row = jobs[0]
        assert job_row.canonical_url == job.canonical_url
        assert job_row.first_seen_at == observed_at
        assert job_row.last_seen_at == observed_at

        occurrences = (await session.execute(select(JobOccurrence))).scalars().all()
        assert len(occurrences) == 1, f"expected 1 JobOccurrence, found {len(occurrences)}"
        occurrence = occurrences[0]
        assert occurrence.provider == "ats_scrapers"
        assert occurrence.source == "greenhouse"
        assert occurrence.source_tenant_id == board_token
        assert occurrence.source_job_id == job.source_job_id
        assert occurrence.requisition_id_raw == job.requisition_id_raw
        assert occurrence.source_url == job.canonical_url
        assert occurrence.canonical_url == job.canonical_url
        expected_normalized = normalize_url(
            job.canonical_url, provider="ats_scrapers", source="greenhouse"
        )
        assert occurrence.source_url_normalized == expected_normalized
        assert occurrence.posted_at == job.posted_at
        assert occurrence.is_active is True

        conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
        assert conflicts == [], f"expected zero IdentityConflict rows, found {len(conflicts)}"
        user_jobs = (await session.execute(select(UserJob))).scalars().all()
        assert user_jobs == [], f"expected zero UserJob rows, found {len(user_jobs)}"

        return occurrence.job_id, occurrence.id


async def _assert_state_after_run_two(
    engine: AsyncEngine,
    *,
    run2_id: Any,
    prior_job_id: Any,
    prior_occurrence_id: Any,
    job: DiscoveredJob,
    board_token: str,
    observed_at_2: datetime,
) -> None:
    async with AsyncSession(bind=engine) as session:
        runs = (await session.execute(select(CollectionRun))).scalars().all()
        assert len(runs) == 2, f"expected 2 CollectionRun rows, found {len(runs)}"
        run2 = await session.get(CollectionRun, run2_id)
        assert run2 is not None
        assert run2.status == "completed"
        assert run2.jobs_discovered == 1
        assert run2.jobs_inserted == 0
        assert run2.jobs_updated == 1

        attempts = (await session.execute(select(CollectionRunProviderAttempt))).scalars().all()
        assert len(attempts) == 2, f"expected 2 provider attempts, found {len(attempts)}"
        attempt2 = next(a for a in attempts if a.collection_run_id == run2_id)
        assert attempt2.jobs_discovered == 1
        assert attempt2.jobs_inserted == 0
        assert attempt2.jobs_updated == 1

        raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
        assert len(raw_rows) == 2, f"expected 2 RawJobIngestion rows, found {len(raw_rows)}"
        assert {r.processing_status for r in raw_rows} == {"normalized"}

        jobs = (await session.execute(select(Job))).scalars().all()
        assert len(jobs) == 1, f"expected still exactly 1 Job, found {len(jobs)}"
        assert jobs[0].id == prior_job_id
        assert jobs[0].last_seen_at == observed_at_2

        occurrences = (await session.execute(select(JobOccurrence))).scalars().all()
        assert (
            len(occurrences) == 1
        ), f"expected still exactly 1 JobOccurrence, found {len(occurrences)}"
        occurrence = occurrences[0]
        assert occurrence.id == prior_occurrence_id, "a second occurrence was created (duplicate)"
        assert occurrence.job_id == prior_job_id
        assert occurrence.last_seen_at == observed_at_2
        assert occurrence.last_seen_at > occurrence.first_seen_at
        # Natural key and descriptive fields must be unchanged by re-observation.
        assert occurrence.provider == "ats_scrapers"
        assert occurrence.source == "greenhouse"
        assert occurrence.source_tenant_id == board_token
        assert occurrence.source_job_id == job.source_job_id
        assert occurrence.requisition_id_raw == job.requisition_id_raw
        assert occurrence.canonical_url == job.canonical_url
        assert occurrence.is_active is True

        conflicts = (await session.execute(select(IdentityConflict))).scalars().all()
        assert conflicts == [], f"expected zero IdentityConflict rows, found {len(conflicts)}"
        user_jobs = (await session.execute(select(UserJob))).scalars().all()
        assert user_jobs == [], f"expected zero UserJob rows, found {len(user_jobs)}"


async def _run_two_pipeline_passes(
    engine: AsyncEngine, job: DiscoveredJob, board_token: str
) -> _StepResult:
    query = SourceQuery(sources=["greenhouse"])
    observed_at_1 = job.discovered_at

    try:
        provider1 = _SingleJobReplayProvider(job, source="greenhouse", called_at=observed_at_1)
        run1_id = await pipeline.run(
            engine, provider1, query, observed_at=observed_at_1, clock=SystemClock()
        )
        prior_job_id, prior_occurrence_id = await _assert_state_after_run_one(
            engine, run_id=run1_id, job=job, board_token=board_token, observed_at=observed_at_1
        )
    except AssertionError as exc:
        return _StepResult("pipeline run 1 (insert)", _StepStatus.FAIL, str(exc))
    except Exception as exc:
        return _StepResult("pipeline run 1 (insert)", _StepStatus.FAIL, type(exc).__name__)

    observed_at_2 = datetime.now(UTC)
    if observed_at_2 <= observed_at_1:
        observed_at_2 = observed_at_1 + timedelta(seconds=1)

    try:
        provider2 = _SingleJobReplayProvider(job, source="greenhouse", called_at=observed_at_2)
        run2_id = await pipeline.run(
            engine, provider2, query, observed_at=observed_at_2, clock=SystemClock()
        )
        await _assert_state_after_run_two(
            engine,
            run2_id=run2_id,
            prior_job_id=prior_job_id,
            prior_occurrence_id=prior_occurrence_id,
            job=job,
            board_token=board_token,
            observed_at_2=observed_at_2,
        )
    except AssertionError as exc:
        return _StepResult("pipeline run 2 (re-observation)", _StepStatus.FAIL, str(exc))
    except Exception as exc:
        return _StepResult("pipeline run 2 (re-observation)", _StepStatus.FAIL, type(exc).__name__)

    return _StepResult(
        "pipeline run 1+2 (insert, then re-observation without duplication)", _StepStatus.PASS, ""
    )


def _print_summary(results: list[_StepResult]) -> bool:
    print("=== live_proof_greenhouse_ingestion summary ===")
    for result in results:
        print(f"[{result.status.value:7s}] {result.name} - {result.detail}")
    overall_pass = all(r.status is _StepStatus.PASS for r in results)
    print("-------------------------------------------")
    print("OVERALL: PASS" if overall_pass else "OVERALL: FAIL")
    return overall_pass


async def _run_proof(board_token: str, company: str) -> bool:
    """Fail-fast sequence, `results` accumulated throughout; cleanup always
    runs in `finally` regardless of where the sequence stopped, and exactly
    one summary is printed at the very end — never before cleanup and the
    leak check have both had a chance to run and be recorded."""
    results: list[_StepResult] = []
    settings = get_settings()

    name = _generate_database_name()
    results.append(_StepResult("generate disposable database name", _StepStatus.PASS, name))

    quoted_name: str | None
    try:
        quoted_name = _quote_identifier(name)
    except ValueError as exc:
        results.append(
            _StepResult("quote disposable database identifier", _StepStatus.FAIL, str(exc))
        )
        quoted_name = None

    candidate_url = (
        make_url(settings.database_url).set(database=name).render_as_string(hide_password=False)
    )
    admin_url = _admin_url(settings.database_url, database=_MAINTENANCE_DATABASE)

    proceed = quoted_name is not None
    if proceed:
        try:
            assert_safe_for_local_destructive_lifecycle(
                candidate_url, settings.database_url, app_env=settings.app_env
            )
            results.append(
                _StepResult(
                    "local destructive-lifecycle safety guard",
                    _StepStatus.PASS,
                    redact_database_url(candidate_url),
                )
            )
        except RuntimeError as exc:
            results.append(
                _StepResult("local destructive-lifecycle safety guard", _StepStatus.FAIL, str(exc))
            )
            proceed = False

    try:
        if proceed:
            try:
                assert quoted_name is not None
                await _create_database(admin_url, quoted_name)
                results.append(
                    _StepResult(
                        "create disposable database",
                        _StepStatus.PASS,
                        redact_database_url(candidate_url),
                    )
                )
            except Exception as exc:
                results.append(
                    _StepResult("create disposable database", _StepStatus.FAIL, type(exc).__name__)
                )
                proceed = False

        if proceed:
            migrate_result = _run_alembic_upgrade(candidate_url)
            results.append(migrate_result)
            proceed = migrate_result.status is _StepStatus.PASS

        if proceed:
            reachability_result = await _reachability_preflight(candidate_url)
            results.append(reachability_result)
            proceed = reachability_result.status is _StepStatus.PASS

        mapped_job: DiscoveredJob | None = None
        if proceed:
            try:
                payload, metadata = await canary.fetch_greenhouse_jobs_raw(board_token)
                jobs = payload["jobs"]
                representative = canary.select_representative_job(jobs)
                discovered_at = datetime.now(UTC)
                mapped_job = canary.map_job_to_discovered_job(
                    representative,
                    board_token=board_token,
                    company=company,
                    discovered_at=discovered_at,
                )
                results.append(
                    _StepResult(
                        "single live Greenhouse request",
                        _StepStatus.PASS,
                        f"board_token={board_token} status={metadata.status_code} "
                        f"byte_count={metadata.byte_count} "
                        f"source_job_id={mapped_job.source_job_id}",
                    )
                )
            except (canary.CanaryFetchError, ValueError) as exc:
                results.append(
                    _StepResult("single live Greenhouse request", _StepStatus.FAIL, str(exc))
                )
                proceed = False

        if proceed and mapped_job is not None:
            engine = create_async_engine(candidate_url)
            try:
                pipeline_result = await _run_two_pipeline_passes(engine, mapped_job, board_token)
            finally:
                await engine.dispose()
            results.append(pipeline_result)
    finally:
        if quoted_name is not None:
            results.extend(
                await _perform_cleanup(
                    drop=lambda: _drop_database_if_exists(admin_url, quoted_name),
                    check_exists=lambda: _database_exists(admin_url, name),
                    name=name,
                )
            )

    return _print_summary(results)


async def _perform_cleanup(
    *,
    drop: Callable[[], Awaitable[None]],
    check_exists: Callable[[], Awaitable[bool]],
    name: str,
) -> list[_StepResult]:
    """Always attempts the drop, then always attempts the leak check —
    independent of whether the drop itself succeeded — and reports each as
    its own `_StepResult`. Decoupled from any real database via injectable
    `drop`/`check_exists` callables so the failure-reporting behavior
    (drop raising, or the leak check finding the database still present)
    is directly unit-testable offline, without a real PostgreSQL instance —
    the same pattern `scripts/verify.py`'s `cleanup_run_dir_step` already
    established for its own temporary-directory cleanup."""
    steps: list[_StepResult] = []
    try:
        await drop()
        steps.append(_StepResult("cleanup: drop disposable database", _StepStatus.PASS, name))
    except Exception as exc:
        steps.append(
            _StepResult("cleanup: drop disposable database", _StepStatus.FAIL, type(exc).__name__)
        )

    try:
        still_exists = await check_exists()
        if still_exists:
            steps.append(
                _StepResult(
                    "cleanup: leak check",
                    _StepStatus.FAIL,
                    f"database still exists, remove manually: {name}",
                )
            )
        else:
            steps.append(_StepResult("cleanup: leak check", _StepStatus.PASS, "confirmed absent"))
    except Exception as exc:
        steps.append(_StepResult("cleanup: leak check", _StepStatus.FAIL, type(exc).__name__))
    return steps


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="live_proof_greenhouse_ingestion.py",
        description=(
            "Manually-invoked, opt-in live-to-disposable-database Greenhouse "
            "ingestion proof. Creates and drops a local throwaway PostgreSQL "
            "database and makes exactly one live Greenhouse request."
        ),
    )
    parser.add_argument(
        "--board-token", required=True, help="Greenhouse board token, e.g. 'gitlab'."
    )
    parser.add_argument(
        "--company",
        required=True,
        help="Human-readable company display name, supplied explicitly — never inferred.",
    )
    parser.add_argument(
        "--confirm-create-and-drop-local-test-database",
        action="store_true",
        required=True,
        help=(
            "Required. Explicit acknowledgement that this run will create and "
            "then drop a local, throwaway PostgreSQL database."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        canary.validate_board_token(args.board_token)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    overall_pass = asyncio.run(_run_proof(args.board_token, args.company))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
