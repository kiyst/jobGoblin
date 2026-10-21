"""Normalized persistence through the real offline Greenhouse path, against the
disposable PostgreSQL test database (Phase 4 S3; ADR 0018).

The primary D2 proof (A6) runs the 30 reconstructed corpus envelopes through the
real `GreenhouseJobBoardProvider` over `httpx.MockTransport`, then the unchanged
bridge, `normalize_posting`, and `pipeline.run`/`persist_posting`, and compares
what PostgreSQL holds after a fresh-session reload with ADR 0014's committed D2
literals. `ConfigurableProvider` and directly built `DiscoveredJob`s appear only
as isolated failure/control cases.

Zero network: the autouse guard fails any real HTTP transport, and any socket
connection or name resolution other than the configured disposable test
database. Every parser version comes from the real builder over a real
configuration.
"""

from __future__ import annotations

import asyncio
import html
import json
import secrets
import socket
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import pytest
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import get_settings
from app.db.models import (
    CollectionRun,
    IdentityConflict,
    Job,
    JobNote,
    JobOccurrence,
    RawJobIngestion,
    User,
    UserJob,
)
from app.ingestion import normalized_fields as nf
from app.ingestion import persistence, pipeline, provider_execution
from app.ingestion.clock import FixedClock
from app.ingestion.hashing import canonical_json_hash
from app.ingestion.identity import resolve_identity
from app.ingestion.normalized_fields import (
    NormalizationBindingError,
    NormalizationContext,
    ProvenanceIntegrityError,
    build_normalization_context,
    verify_normalization_context,
)
from app.normalization.posting import PostingInputs, normalize_posting
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, load_taxonomy
from app.normalization.types import NormalizationResult
from app.normalization.url import normalize_url
from app.providers.fixture import FixtureProvider
from app.providers.greenhouse import GreenhouseBoard, GreenhouseJobBoardProvider
from app.providers.greenhouse_content import GreenhouseContentMode
from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult, SourceRunStats
from app.schemas.provider import ProviderCapabilities, SourceCapabilities, SourceQuery
from scripts.db_safety import resolve_test_database_url
from scripts.evaluate_phase3_corpus import load_corpus
from tests import test_normalization_posting_realistic as d2
from tests.support.configurable_provider import ConfigurableProvider

BACKEND_DIR = Path(__file__).resolve().parent.parent
CORPUS_PATH = BACKEND_DIR / "tests" / "fixtures" / "evaluation" / "phase3_realistic_corpus.json"
PROJECTED_FIXTURE = (
    BACKEND_DIR / "tests" / "fixtures" / "providers" / "greenhouse_s2c_projected.json"
)
DECLARED: GreenhouseContentMode = "declared-double-escaped"
QUERY = SourceQuery(sources=["greenhouse"])
COLUMNS = {
    "employment_type": "employment_type",
    "seniority": "seniority",
    "location.country": "country",
}
UNPERSISTED_NORMALIZED_COLUMNS = (
    "normalized_title",
    "job_family",
    "remote_type",
    "years_experience_min",
    "years_experience_max",
    "city",
    "state",
    "postal_code",
    "salary_min",
    "salary_max",
    "salary_currency",
    "salary_period",
    "annualized_salary_min",
    "annualized_salary_max",
    "compensation_text",
    "compensation_explicit",
    "description_raw",
    "description_clean",
)
TAXONOMY = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)


# ---------------------------------------------------------------------------
# Network guard: only the disposable test database may be reached.
# ---------------------------------------------------------------------------


def _db_endpoint() -> tuple[str, int]:
    url = urlsplit(resolve_test_database_url(get_settings().test_database_url))
    return (url.hostname or "localhost", url.port or 5432)


@pytest.fixture(autouse=True)
async def network_guard(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[list[str]]:
    """Installed inside the async fixture's lifetime, as in S1/S2b, so the event
    loop's own loopback socketpair predates it."""
    host, port = _db_endpoint()
    attempts: list[str] = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    async def no_http(self: Any, request: httpx.Request) -> httpx.Response:
        attempts.append("http")
        raise httpx.ConnectError("network disabled in tests")

    loopback = {"127.0.0.1", "::1", "localhost", host}

    def allowed(address: object) -> bool:
        """Loopback only: the local disposable database, and the event loop's
        own self-pipe. Every external host is refused."""
        return isinstance(address, tuple) and len(address) >= 2 and address[0] in loopback

    def connect(self: socket.socket, address: Any) -> Any:
        if allowed(address):
            return real_connect(self, address)
        attempts.append("connect")
        raise AssertionError("socket access attempted in an offline test")

    def connect_ex(self: socket.socket, address: Any) -> Any:
        if allowed(address):
            return real_connect_ex(self, address)
        attempts.append("connect_ex")
        raise AssertionError("socket access attempted in an offline test")

    def getaddrinfo(name: Any, service: Any, *args: Any, **kwargs: Any) -> Any:
        if name in loopback and service in (port, str(port)):
            return real_getaddrinfo(name, service, *args, **kwargs)
        attempts.append("getaddrinfo")
        raise AssertionError("name resolution attempted in an offline test")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_http)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield attempts
    assert attempts == []


# ---------------------------------------------------------------------------
# Offline Greenhouse provider, records, and cleanup
# ---------------------------------------------------------------------------


class Transport:
    """A counting `MockTransport` handler serving one fixed envelope per board."""

    def __init__(self, routes: dict[str, list[dict[str, Any]]]) -> None:
        self.bodies = {
            token: json.dumps({"jobs": records, "meta": {"total": len(records)}}).encode("utf-8")
            for token, records in routes.items()
        }
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        token = request.url.path.split("/")[3]
        self.calls.append(token)
        return httpx.Response(
            200, content=self.bodies[token], headers={"content-type": "application/json"}
        )


def _provider(
    boards: Sequence[GreenhouseBoard], routes: dict[str, list[dict[str, Any]]], *, now: datetime
) -> tuple[GreenhouseJobBoardProvider, Transport]:
    transport = Transport(routes)

    async def no_sleep(_: float) -> None:
        raise AssertionError("no retry expected")

    provider = GreenhouseJobBoardProvider(
        boards,
        transport_factory=lambda: httpx.MockTransport(transport),
        sleep=no_sleep,
        monotonic=lambda: 0.0,
        now=lambda: now,
    )
    return provider, transport


def _reconstruct_content(description: str) -> str:
    """ADR 0015's reconstruction: synthetic raw shape, not captured HTML."""
    return html.escape("<div>" + html.escape(description, quote=False) + "</div>", quote=False)


def _record(
    token: str,
    job_id: int,
    title: str | None,
    description: str | None = None,
    location: str | None = None,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "_synthetic": "SYNTHETIC record built for S3 tests",
        "id": job_id,
        "title": title,
        "absolute_url": url or f"https://job-boards.greenhouse.io/{token}/jobs/{job_id}",
        "location": None if location is None else {"name": location},
        "content": None if description is None else _reconstruct_content(description),
    }
    return record


def _board(token: str) -> GreenhouseBoard:
    return GreenhouseBoard(token, token.title(), content_mode=DECLARED)


def _context(provider: GreenhouseJobBoardProvider) -> NormalizationContext:
    return build_normalization_context(provider.board_content_modes)


def _unique_time() -> datetime:
    return datetime(2031, 1, 1, tzinfo=UTC) + timedelta(seconds=secrets.randbelow(10**8))


@dataclass
class Tracker:
    tokens: set[str] = field(default_factory=set)
    run_times: set[datetime] = field(default_factory=set)
    job_ids: set[uuid.UUID] = field(default_factory=set)
    user_ids: set[uuid.UUID] = field(default_factory=set)
    raw_ids: set[uuid.UUID] = field(default_factory=set)

    def token(self, label: str) -> str:
        value = f"{label}-s3-{secrets.token_hex(4)}"
        self.tokens.add(value)
        return value


@pytest.fixture
async def tracker(db_engine: AsyncEngine) -> AsyncIterator[Tracker]:
    tracked = Tracker()
    try:
        yield tracked
    finally:
        await _cleanup(db_engine, tracked)


async def _cleanup(engine: AsyncEngine, tracked: Tracker) -> None:
    async with AsyncSession(bind=engine) as session:
        job_ids = set(tracked.job_ids)
        raw_ids = set(tracked.raw_ids)
        if tracked.tokens:
            occurrences = (
                await session.execute(
                    select(JobOccurrence.id, JobOccurrence.job_id).where(
                        JobOccurrence.source_tenant_id.in_(tracked.tokens)
                    )
                )
            ).all()
            job_ids |= {job_id for _, job_id in occurrences}
            occurrence_ids = [occurrence_id for occurrence_id, _ in occurrences]
            conditions = [
                RawJobIngestion.raw_payload["absolute_url"].astext.like(f"%/{token}/jobs/%")
                for token in tracked.tokens
            ]
            if occurrence_ids:
                conditions.append(RawJobIngestion.job_occurrence_id.in_(occurrence_ids))
            raw_ids |= set(
                (await session.execute(select(RawJobIngestion.id).where(or_(*conditions))))
                .scalars()
                .all()
            )
        if raw_ids:
            await session.execute(
                delete(IdentityConflict).where(
                    IdentityConflict.incoming_raw_job_ingestion_id.in_(raw_ids)
                )
            )
            await session.execute(delete(RawJobIngestion).where(RawJobIngestion.id.in_(raw_ids)))
        if tracked.run_times:
            await session.execute(
                delete(CollectionRun).where(CollectionRun.started_at.in_(tracked.run_times))
            )
        if job_ids:
            await session.execute(delete(Job).where(Job.id.in_(job_ids)))
        if tracked.user_ids:
            await session.execute(delete(User).where(User.id.in_(tracked.user_ids)))
        await session.commit()


async def _run(
    engine: AsyncEngine,
    provider: Any,
    tracked: Tracker,
    *,
    observed_at: datetime,
    context: NormalizationContext | None = None,
) -> uuid.UUID:
    tracked.run_times.add(observed_at)
    return await pipeline.run(
        engine,
        provider,
        QUERY,
        observed_at=observed_at,
        clock=FixedClock(observed_at),
        normalization=context,
    )


@dataclass(frozen=True)
class Persisted:
    job: Job
    occurrence: JobOccurrence
    raws: list[RawJobIngestion]


async def _persisted(engine: AsyncEngine, token: str, job_id: str) -> Persisted:
    """A fresh-session reload of one posting's Job, occurrence, and raw rows."""
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        occurrence = (
            await session.execute(
                select(JobOccurrence).where(
                    JobOccurrence.source_tenant_id == token,
                    JobOccurrence.source_job_id == job_id,
                )
            )
        ).scalar_one()
        job = (await session.execute(select(Job).where(Job.id == occurrence.job_id))).scalar_one()
        raws = list(
            (
                await session.execute(
                    select(RawJobIngestion)
                    .where(RawJobIngestion.job_occurrence_id == occurrence.id)
                    .order_by(RawJobIngestion.created_at, RawJobIngestion.id)
                )
            )
            .scalars()
            .all()
        )
        return Persisted(job=job, occurrence=occurrence, raws=raws)


async def _raws_for(engine: AsyncEngine, token: str) -> list[RawJobIngestion]:
    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        return list(
            (
                await session.execute(
                    select(RawJobIngestion).where(
                        RawJobIngestion.raw_payload["absolute_url"].astext.like(f"%/{token}/jobs/%")
                    )
                )
            )
            .scalars()
            .all()
        )


async def _run_count(engine: AsyncEngine) -> int:
    async with AsyncSession(bind=engine) as session:
        return len((await session.execute(select(CollectionRun.id))).scalars().all())


def _entries(job: Job) -> dict[str, dict[str, str]]:
    """The stored provenance entries, typed for assertions."""
    return cast(dict[str, dict[str, str]], job.field_provenance or {})


def _values(job: Job) -> dict[str, object]:
    return {column: getattr(job, column) for column in ("employment_type", "seniority", "country")}


# ---------------------------------------------------------------------------
# The 30 reconstructed corpus envelopes through the real adapter (A6)
# ---------------------------------------------------------------------------


@dataclass
class Corpus:
    boards: list[GreenhouseBoard]
    routes: dict[str, list[dict[str, Any]]]
    record_ids: dict[tuple[str, str], str]  # (board token, job id) -> corpus record id
    inputs: dict[str, PostingInputs]
    envelope_records: dict[str, dict[str, Any]]


def _corpus(tracked: Tracker) -> Corpus:
    records = load_corpus(CORPUS_PATH, known_canonical_ids=TAXONOMY.canonical_ids())
    assert len(records) == 30
    tokens: dict[str, str] = {}
    routes: dict[str, list[dict[str, Any]]] = {}
    record_ids: dict[tuple[str, str], str] = {}
    inputs: dict[str, PostingInputs] = {}
    envelope_records: dict[str, dict[str, Any]] = {}
    for record in records:
        employer, job_id = record.id.split(":")
        token = tokens.setdefault(employer, tracked.token(employer))
        description = record.fields["description"]
        location_raw = record.fields["location_raw"]
        assert isinstance(description, str)
        envelope_record = {
            "_synthetic": "RECONSTRUCTED SYNTHETIC raw shape — not captured Greenhouse HTML",
            "id": int(job_id),
            "title": record.fields["title"],
            "absolute_url": f"https://job-boards.greenhouse.io/{token}/jobs/{job_id}",
            "location": None if location_raw is None else {"name": location_raw},
            "content": _reconstruct_content(description),
        }
        routes.setdefault(token, []).append(envelope_record)
        record_ids[(token, job_id)] = record.id
        inputs[record.id] = PostingInputs(
            title=record.fields["title"], description=description, location=location_raw
        )
        envelope_records[record.id] = envelope_record
    boards = [_board(token) for token in sorted(routes)]
    return Corpus(boards, routes, record_ids, inputs, envelope_records)


async def _assert_persisted_d2(engine: AsyncEngine, corpus: Corpus, version: str) -> None:
    """What PostgreSQL holds equals ADR 0014's committed D2 literals for the
    covered components, with provenance checked separately from values."""
    rows = {
        record_id: await _persisted(engine, token, job_id)
        for (token, job_id), record_id in corpus.record_ids.items()
    }
    assert len(rows) == 30
    assert set(COLUMNS) == set(d2.COVERED_COMPONENTS)
    for component, column in COLUMNS.items():
        persisted = {
            record_id: getattr(row.job, column)
            for record_id, row in rows.items()
            if getattr(row.job, column) is not None
        }
        assert persisted == d2.CORRECT[component], component
    for record_id, row in rows.items():
        job = row.job
        for column in UNPERSISTED_NORMALIZED_COLUMNS:
            assert getattr(job, column) is None, (record_id, column)
        direct = normalize_posting(corpus.inputs[record_id], taxonomy=TAXONOMY)
        expected: dict[str, NormalizationResult[Any]] = {
            "employment_type": direct.employment_type,
            "seniority": direct.seniority,
            "country": direct.location.country,
        }
        provenance = _entries(job)
        assert set(provenance) == {c for c in expected if getattr(job, c) is not None}
        for column, result in expected.items():
            assert getattr(job, column) == result.value, (record_id, column)
            if result.value is None:
                continue
            entry = provenance[column]
            assert entry["source"] == result.provenance.value, (record_id, column)
            assert entry["source"] in {"parsed_description", "inferred"}
            assert entry["provider"] == entry["provider_source"] == "greenhouse"
            assert entry["parser_version"] == version
            assert entry["occurrence_id"] == str(row.occurrence.id)
            assert entry["raw_job_ingestion_id"] in {str(raw.id) for raw in row.raws}
        for (exception_id, component), (_, emitted) in d2.PROVENANCE_EXCEPTIONS.items():
            if exception_id == record_id:
                assert provenance[COLUMNS[component]]["source"] == emitted
        for raw in row.raws:
            assert raw.raw_payload == corpus.envelope_records[record_id]
            assert raw.raw_content_hash == canonical_json_hash(corpus.envelope_records[record_id])
            assert raw.processing_status == "normalized"
            assert raw.parser_version is not None


async def test_d2_corpus_persists_through_the_real_greenhouse_path(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    corpus = _corpus(tracker)
    t = _unique_time()
    provider, transport = _provider(corpus.boards, corpus.routes, now=t)
    context = _context(provider)
    run_id = await _run(db_engine, provider, tracker, observed_at=t, context=context)

    assert sorted(transport.calls) == sorted(board.board_token for board in corpus.boards)
    async with AsyncSession(bind=db_engine) as session:
        run = await session.get(CollectionRun, run_id)
        assert run is not None and run.status == "completed"
        assert (run.jobs_discovered, run.jobs_inserted, run.jobs_updated) == (30, 30, 0)
    await _assert_persisted_d2(db_engine, corpus, context.parser_version)
    for (token, job_id), _ in corpus.record_ids.items():
        (raw,) = (await _persisted(db_engine, token, job_id)).raws
        assert raw.parser_version == context.parser_version


async def test_corpus_rerun_is_idempotent_and_a_newer_version_follows_precedence(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    corpus = _corpus(tracker)
    t = _unique_time()
    provider, _ = _provider(corpus.boards, corpus.routes, now=t)
    v1 = _context(provider)
    await _run(db_engine, provider, tracker, observed_at=t, context=v1)

    async def snapshot() -> dict[str, tuple[dict[str, object], object]]:
        state: dict[str, tuple[dict[str, object], object]] = {}
        for (token, job_id), record_id in corpus.record_ids.items():
            row = await _persisted(db_engine, token, job_id)
            state[record_id] = (_values(row.job), row.job.field_provenance)
        return state

    first = await snapshot()

    # Rerun: same configuration, code, and observation time -> nothing changes.
    rerun_provider, _ = _provider(corpus.boards, corpus.routes, now=t)
    await _run(db_engine, rerun_provider, tracker, observed_at=t, context=_context(rerun_provider))
    assert await snapshot() == first
    for token, job_id in corpus.record_ids:
        row = await _persisted(db_engine, token, job_id)
        assert len(row.raws) == 2  # raw rows are append-only by design
        assert {raw.parser_version for raw in row.raws} == {v1.parser_version}
    await _assert_persisted_d2(db_engine, corpus, v1.parser_version)

    # A legitimately newer parser version: a real configuration change (one more
    # approved board) through the real builder. At the same observation instant
    # it is a no-op: identical values, and a version is never an ordering signal.
    extra = tracker.token("extra")
    boards_v2 = [*corpus.boards, _board(extra)]
    provider_v2, _ = _provider(boards_v2, {**corpus.routes, extra: []}, now=t)
    v2 = _context(provider_v2)
    assert v2.parser_version != v1.parser_version
    await _run(db_engine, provider_v2, tracker, observed_at=t, context=v2)
    assert await snapshot() == first
    for token, job_id in corpus.record_ids:
        newest = (await _persisted(db_engine, token, job_id)).raws[-1]
        assert newest.parser_version == v2.parser_version

    # Through a strictly later observation, the newer version's entries replace.
    later = t + timedelta(hours=1)
    provider_later, _ = _provider(boards_v2, {**corpus.routes, extra: []}, now=later)
    await _run(
        db_engine, provider_later, tracker, observed_at=later, context=_context(provider_later)
    )
    after_v2 = await snapshot()
    for (token, job_id), record_id in corpus.record_ids.items():
        values, entries = after_v2[record_id]
        assert values == first[record_id][0]  # same values: same parser output
        row = await _persisted(db_engine, token, job_id)
        newest = row.raws[-1]
        assert newest.parser_version == v2.parser_version
        for entry in cast(dict[str, dict[str, str]], entries or {}).values():
            assert entry["parser_version"] == v2.parser_version
            assert entry["raw_job_ingestion_id"] == str(newest.id)
            assert entry["observed_at"] == later.isoformat()
    await _assert_persisted_d2(db_engine, corpus, v2.parser_version)

    # An older observation under the older version never replaces the newer entry.
    older = t - timedelta(hours=1)
    provider_old, _ = _provider(corpus.boards, corpus.routes, now=older)
    await _run(db_engine, provider_old, tracker, observed_at=older, context=_context(provider_old))
    assert await snapshot() == after_v2


async def test_a_d2_regression_fails_the_persisted_check(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed covered output fails the write-path proof itself: it is never
    absorbed by updating a snapshot."""
    corpus = _corpus(tracker)
    target = next(iter(d2.CORRECT["seniority"]))
    real = nf.normalize_posting

    def regressed(inputs: PostingInputs, *, taxonomy: Any) -> Any:
        result = real(inputs, taxonomy=taxonomy)
        if inputs == corpus.inputs[target]:
            wrong = "director" if result.seniority.value != "director" else "senior"
            object.__setattr__(
                result,
                "seniority",
                NormalizationResult(cast(Any, wrong), result.seniority.provenance),
            )
        return result

    monkeypatch.setattr(nf, "normalize_posting", regressed)
    t = _unique_time()
    provider, _ = _provider(corpus.boards, corpus.routes, now=t)
    context = _context(provider)
    await _run(db_engine, provider, tracker, observed_at=t, context=context)
    with pytest.raises(AssertionError):
        await _assert_persisted_d2(db_engine, corpus, context.parser_version)


# ---------------------------------------------------------------------------
# The committed S2c projected record, end to end
# ---------------------------------------------------------------------------


async def test_offline_s2c_replay_persists_an_inspectable_job(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    document = json.loads(PROJECTED_FIXTURE.read_text(encoding="utf-8"))
    (record,) = document["replay_envelope"]["jobs"]
    golden = document["selected"][0]["golden_expectations"]["normalized"]
    token = tracker.token("replay")
    t = _unique_time()
    provider, transport = _provider([_board(token)], {token: [record]}, now=t)
    context = _context(provider)
    await _run(db_engine, provider, tracker, observed_at=t, context=context)

    assert transport.calls == [token]
    row = await _persisted(db_engine, token, str(record["id"]))
    expected = {
        "employment_type": golden["employment_type"],
        "seniority": golden["seniority"],
        "country": golden["location"]["country"],
    }
    for column, result in expected.items():
        assert getattr(row.job, column) == result["value"]
        entry = _entries(row.job).get(column)
        if result["value"] is None:
            assert entry is None
        else:
            assert entry is not None and entry["source"] == result["provenance"]
    (raw,) = row.raws
    assert raw.raw_payload == record
    assert raw.raw_content_hash == canonical_json_hash(record)
    assert raw.processing_status == "normalized"
    assert raw.parser_version == context.parser_version


# ---------------------------------------------------------------------------
# Precedence, abstention, and integrity on the write path
# ---------------------------------------------------------------------------


async def _ingest(
    engine: AsyncEngine,
    tracked: Tracker,
    token: str,
    record: dict[str, Any],
    observed_at: datetime,
) -> NormalizationContext:
    provider, _ = _provider([_board(token)], {token: [record]}, now=observed_at)
    context = _context(provider)
    await _run(engine, provider, tracked, observed_at=observed_at, context=context)
    return context


async def test_abstention_writes_nothing_and_never_erases(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("abstain")
    t = _unique_time()
    await _ingest(db_engine, tracker, token, _record(token, 1, "Software Engineer"), t)
    row = await _persisted(db_engine, token, "1")
    assert _values(row.job) == {"employment_type": None, "seniority": None, "country": None}
    assert row.job.field_provenance is None
    assert row.raws[0].parser_version is not None  # normalization ran; nothing to write

    full_time = _record(
        token, 1, "Software Engineer", "This is a full-time position.", "Toronto, Canada"
    )
    await _ingest(db_engine, tracker, token, full_time, t + timedelta(hours=1))
    written = await _persisted(db_engine, token, "1")
    assert _values(written.job) == {
        "employment_type": "full_time",
        "seniority": None,
        "country": "Canada",
    }

    await _ingest(
        db_engine, tracker, token, _record(token, 1, "Software Engineer"), t + timedelta(hours=2)
    )
    kept = await _persisted(db_engine, token, "1")
    assert _values(kept.job) == _values(written.job)
    assert kept.job.field_provenance == written.job.field_provenance


async def test_trust_and_recency_precedence_on_the_write_path(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("precedence")
    t = _unique_time()
    await _ingest(
        db_engine, tracker, token, _record(token, 1, "Staff Software Engineer (Part-Time)"), t
    )
    first = await _persisted(db_engine, token, "1")
    entries = _entries(first.job)
    assert _values(first.job)["employment_type"] == "part_time"
    assert entries["employment_type"]["source"] == "inferred"

    # Higher trust (parsed from the description) replaces an inferred value.
    stronger = _record(token, 1, "Staff Software Engineer", "This is a full-time position.")
    await _ingest(db_engine, tracker, token, stronger, t + timedelta(hours=1))
    second = await _persisted(db_engine, token, "1")
    assert second.job.employment_type == "full_time"
    assert _entries(second.job)["employment_type"]["source"] == "parsed_description"
    # Equal trust, newer observation: the seniority entry moves to the new raw row.
    assert _entries(second.job)["seniority"]["raw_job_ingestion_id"] == str(second.raws[-1].id)

    # Lower trust never overwrites higher trust, even when newer.
    await _ingest(
        db_engine,
        tracker,
        token,
        _record(token, 1, "Staff Software Engineer (Part-Time)"),
        t + timedelta(hours=2),
    )
    third = await _persisted(db_engine, token, "1")
    assert third.job.employment_type == "full_time"
    assert (
        _entries(third.job)["employment_type"]
        == (second.job.field_provenance or {})["employment_type"]
    )

    # A stronger existing tag is never displaced by a weaker parser result.
    async with AsyncSession(bind=db_engine) as session:
        job = await session.get(Job, third.job.id)
        assert job is not None
        explicit = dict(_entries(job)["seniority"])
        explicit["source"] = "explicit_source"
        job.seniority = "principal"
        job.field_provenance = {**_entries(job), "seniority": explicit}
        await session.commit()
    await _ingest(
        db_engine,
        tracker,
        token,
        _record(token, 1, "Senior Software Engineer"),
        t + timedelta(hours=3),
    )
    fourth = await _persisted(db_engine, token, "1")
    assert fourth.job.seniority == "principal"
    assert _entries(fourth.job)["seniority"] == explicit


@pytest.mark.parametrize("state", ["value_without_entry", "foreign_provider_entry"])
async def test_unrankable_existing_state_fails_closed_without_partial_writes(
    db_engine: AsyncEngine, tracker: Tracker, state: str
) -> None:
    token = tracker.token("integrity")
    t = _unique_time()
    await _ingest(db_engine, tracker, token, _record(token, 1, "Software Engineer"), t)
    seeded = await _persisted(db_engine, token, "1")
    async with AsyncSession(bind=db_engine) as session:
        job = await session.get(Job, seeded.job.id)
        assert job is not None
        job.employment_type = "full_time"
        if state == "foreign_provider_entry":
            job.field_provenance = {
                "employment_type": {
                    "source": "inferred",
                    "provider": "lever",
                    "provider_source": "lever",
                    "occurrence_id": str(seeded.occurrence.id),
                    "raw_job_ingestion_id": str(seeded.raws[0].id),
                    "parser_version": "jgnorm-v1:sha256:" + "a" * 64,
                    "observed_at": t.isoformat(),
                }
            }
        await session.commit()
    before = await _persisted(db_engine, token, "1")

    stronger = _record(
        token, 1, "Senior Software Engineer", "This is a full-time position.", "Toronto, Canada"
    )
    with pytest.raises(ProvenanceIntegrityError):
        await _ingest(db_engine, tracker, token, stronger, t + timedelta(hours=1))
    after = await _persisted(db_engine, token, "1")
    assert _values(after.job) == _values(before.job)
    assert after.job.field_provenance == before.job.field_provenance
    assert after.occurrence.last_seen_at == before.occurrence.last_seen_at
    unlinked = [raw for raw in await _raws_for(db_engine, token) if raw.job_occurrence_id is None]
    (failed_raw,) = unlinked
    assert (failed_raw.processing_status, failed_raw.parser_version) == ("fetched", None)


async def test_reingestion_preserves_user_owned_state(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("userstate")
    t = _unique_time()
    await _ingest(db_engine, tracker, token, _record(token, 1, "Software Engineer"), t)
    seeded = await _persisted(db_engine, token, "1")
    async with AsyncSession(bind=db_engine, expire_on_commit=False) as session:
        user = User(email=f"{token}@example.com")
        session.add(user)
        await session.flush()
        tracker.user_ids.add(user.id)
        user_job = UserJob(
            user_id=user.id,
            job_id=seeded.job.id,
            status="applied",
            status_changed_at=t,
            applied_at=t,
            saved=True,
        )
        session.add(user_job)
        await session.flush()
        session.add(JobNote(user_job_id=user_job.id, body="Spoke with the recruiter."))
        await session.commit()
        user_job_id = user_job.id

    async def user_state() -> tuple[dict[str, object], list[dict[str, object]]]:
        async with AsyncSession(bind=db_engine) as session:
            stored = await session.get(UserJob, user_job_id)
            assert stored is not None
            notes = (
                (await session.execute(select(JobNote).where(JobNote.user_job_id == user_job_id)))
                .scalars()
                .all()
            )
            return (
                {c.name: getattr(stored, c.name) for c in UserJob.__table__.columns},
                [{c.name: getattr(n, c.name) for c in JobNote.__table__.columns} for n in notes],
            )

    before = await user_state()
    changed = _record(
        token, 1, "Senior Software Engineer", "This is a full-time position.", "Toronto, Canada"
    )
    await _ingest(db_engine, tracker, token, changed, t + timedelta(hours=1))
    assert (await _persisted(db_engine, token, "1")).job.employment_type == "full_time"
    assert await user_state() == before


# ---------------------------------------------------------------------------
# Identity conflicts: Phase 2 behavior, no normalized writes
# ---------------------------------------------------------------------------


async def test_evidence_mismatch_writes_no_normalized_values(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("mismatch")
    t = _unique_time()
    await _ingest(db_engine, tracker, token, _record(token, 1, "Software Engineer"), t)
    moved = _record(
        token,
        1,
        "Senior Software Engineer",
        "This is a full-time position.",
        "Toronto, Canada",
        url=f"https://job-boards.greenhouse.io/{token}/jobs/1-moved",
    )
    await _ingest(db_engine, tracker, token, moved, t + timedelta(hours=1))
    row = await _persisted(db_engine, token, "1")
    assert _values(row.job) == {"employment_type": None, "seniority": None, "country": None}
    assert row.job.field_provenance is None
    conflicted = [raw for raw in row.raws if raw.processing_status == "identity_conflict"]
    (raw,) = conflicted
    assert raw.parser_version is None
    async with AsyncSession(bind=db_engine) as session:
        conflicts = (
            (
                await session.execute(
                    select(IdentityConflict).where(
                        IdentityConflict.incoming_raw_job_ingestion_id == raw.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert [c.conflict_type for c in conflicts] == ["evidence_mismatch"]


async def test_ambiguous_match_writes_no_normalized_values(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("ambiguous")
    seed_a, seed_b = tracker.token("seed-a"), tracker.token("seed-b")
    t = _unique_time()
    shared_url = f"https://job-boards.greenhouse.io/{token}/jobs/shared"
    canonical = normalize_url(shared_url, provider="greenhouse", source="greenhouse")
    async with AsyncSession(bind=db_engine) as session:
        for seed in (seed_a, seed_b):
            job = Job(first_seen_at=t, last_seen_at=t)
            session.add(job)
            await session.flush()
            tracker.job_ids.add(job.id)
            seed_url = f"https://job-boards.greenhouse.io/{seed}/jobs/9"
            session.add(
                JobOccurrence(
                    job_id=job.id,
                    provider="greenhouse",
                    source="greenhouse",
                    source_tenant_id=seed,
                    source_job_id="9",
                    source_url=seed_url,
                    source_url_normalized=normalize_url(
                        seed_url, provider="greenhouse", source="greenhouse"
                    ),
                    canonical_url=shared_url,
                    canonical_url_normalized=canonical,
                    first_seen_at=t,
                    last_seen_at=t,
                )
            )
        await session.commit()

    incoming = _record(
        token, 7, "Senior Software Engineer", "This is a full-time position.", url=shared_url
    )
    await _ingest(db_engine, tracker, token, incoming, t + timedelta(hours=1))
    row = await _persisted(db_engine, token, "7")
    assert row.job.id not in tracker.job_ids
    assert _values(row.job) == {"employment_type": None, "seniority": None, "country": None}
    assert row.job.field_provenance is None
    (raw,) = row.raws
    assert (raw.processing_status, raw.parser_version) == ("identity_conflict", None)


# ---------------------------------------------------------------------------
# Failure atomicity
# ---------------------------------------------------------------------------


async def test_a_parser_exception_aborts_the_run_without_partial_state(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tracker.token("parserfail")
    t = _unique_time()
    records = [
        _record(token, 1, "Senior Software Engineer", "This is a full-time position."),
        _record(token, 2, "Staff Software Engineer", "Poison description."),
    ]
    real = nf.normalize_posting

    def fail_on_poison(inputs: PostingInputs, *, taxonomy: Any) -> Any:
        if inputs.description == "Poison description.":
            raise RuntimeError("simulated parser defect")
        return real(inputs, taxonomy=taxonomy)

    monkeypatch.setattr(nf, "normalize_posting", fail_on_poison)
    provider, _ = _provider([_board(token)], {token: records}, now=t)
    with pytest.raises(RuntimeError, match="simulated parser defect"):
        await _run(db_engine, provider, tracker, observed_at=t, context=_context(provider))

    first = await _persisted(db_engine, token, "1")  # committed before the failure
    assert first.job.employment_type == "full_time"
    async with AsyncSession(bind=db_engine) as session:
        occurrence = (
            await session.execute(
                select(JobOccurrence).where(
                    JobOccurrence.source_tenant_id == token, JobOccurrence.source_job_id == "2"
                )
            )
        ).scalar_one_or_none()
        assert occurrence is None
        run = (
            await session.execute(select(CollectionRun).where(CollectionRun.started_at == t))
        ).scalar_one()
        assert run.status == "failed"
    poison = [raw for raw in await _raws_for(db_engine, token) if raw.raw_payload["id"] == 2]
    (raw,) = poison
    assert (raw.processing_status, raw.parser_version, raw.job_occurrence_id) == (
        "fetched",
        None,
        None,
    )


async def test_a_failure_after_the_normalized_flush_rolls_everything_back(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tracker.token("rollback")
    t = _unique_time()
    await _ingest(
        db_engine, tracker, token, _record(token, 1, "Staff Software Engineer (Part-Time)"), t
    )
    before = await _persisted(db_engine, token, "1")

    async def boom() -> None:
        raise RuntimeError("simulated rollback trigger")

    monkeypatch.setattr(persistence, "_after_normalized_flush", boom)
    stronger = _record(
        token, 1, "Senior Software Engineer", "This is a full-time position.", "Toronto, Canada"
    )
    with pytest.raises(RuntimeError, match="simulated rollback trigger"):
        await _ingest(db_engine, tracker, token, stronger, t + timedelta(hours=1))

    after = await _persisted(db_engine, token, "1")
    assert _values(after.job) == _values(before.job)
    assert after.job.field_provenance == before.job.field_provenance
    assert after.job.last_seen_at == before.job.last_seen_at
    assert after.occurrence.last_seen_at == before.occurrence.last_seen_at
    assert [raw.id for raw in after.raws] == [raw.id for raw in before.raws]
    (failed,) = [r for r in await _raws_for(db_engine, token) if r.job_occurrence_id is None]
    assert (failed.processing_status, failed.parser_version) == ("fetched", None)


# ---------------------------------------------------------------------------
# Opt-in activation and verification before any work (A1)
# ---------------------------------------------------------------------------


async def test_without_a_context_greenhouse_ingestion_is_phase2_raw_only(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("noctx")
    t = _unique_time()
    record = _record(
        token, 1, "Senior Software Engineer", "This is a full-time position.", "Toronto, Canada"
    )
    provider, _ = _provider([_board(token)], {token: [record]}, now=t)
    await _run(db_engine, provider, tracker, observed_at=t)
    row = await _persisted(db_engine, token, "1")
    assert _values(row.job) == {"employment_type": None, "seniority": None, "country": None}
    assert row.job.field_provenance is None
    (raw,) = row.raws
    assert (raw.processing_status, raw.parser_version) == ("normalized", None)


async def test_an_unmapped_provider_with_a_context_stays_raw_only(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("unmapped")
    t = _unique_time()
    job = DiscoveredJob(
        provider="fixture_provider",
        source="fixture_ats",
        source_tenant_id=token,
        source_job_id="1",
        requisition_id_raw=None,
        title="Senior Software Engineer",
        company=None,
        location="Toronto, Canada",
        source_url=f"https://example.com/{token}/jobs/1",
        apply_url=None,
        canonical_url=None,
        description="This is a full-time position.",
        compensation_text=None,
        posted_at=None,
        discovered_at=t,
        raw={"absolute_url": f"https://example.com/{token}/jobs/1"},
    )
    greenhouse, _ = _provider([_board(token)], {token: []}, now=t)
    tracker.run_times.add(t)
    await pipeline.run(
        db_engine,
        FixtureProvider([job], called_at=t),
        SourceQuery(sources=["fixture_ats"]),
        observed_at=t,
        clock=FixedClock(t),
        normalization=_context(greenhouse),
    )
    row = await _persisted(db_engine, token, "1")
    assert _values(row.job) == {"employment_type": None, "seniority": None, "country": None}
    (raw,) = row.raws
    assert (raw.processing_status, raw.parser_version) == ("normalized", None)


def _impostor(token: str, t: datetime) -> ConfigurableProvider:
    """Control only: claims the `greenhouse` name without the adapter's snapshot."""
    job = DiscoveredJob(
        provider="greenhouse",
        source="greenhouse",
        source_tenant_id=token,
        source_job_id="1",
        requisition_id_raw=None,
        title="Senior Software Engineer",
        company=None,
        location=None,
        source_url=f"https://job-boards.greenhouse.io/{token}/jobs/1",
        apply_url=None,
        canonical_url=None,
        description=None,
        compensation_text=None,
        posted_at=None,
        discovered_at=t,
        raw={"absolute_url": f"https://job-boards.greenhouse.io/{token}/jobs/1"},
    )
    return ConfigurableProvider(
        "greenhouse",
        capabilities=ProviderCapabilities(
            provider="greenhouse",
            sources={"greenhouse": SourceCapabilities(source="greenhouse", max_concurrency=1)},
        ),
        result=DiscoveryResult(
            provider="greenhouse",
            jobs=[job],
            source_stats=[SourceRunStats(source="greenhouse", completed=True, jobs_found=1)],
            started_at=t,
            completed_at=t,
        ),
    )


async def test_invalid_contexts_fail_before_any_run_row_or_provider_call(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("verify")
    t = _unique_time()
    record = _record(token, 1, "Senior Software Engineer")
    provider, transport = _provider([_board(token)], {token: [record]}, now=t)
    other_provider, _ = _provider([_board(tracker.token("other"))], {}, now=t)
    forged = _context(provider)
    object.__setattr__(forged, "_version", "jgnorm-v1:sha256:" + "f" * 64)
    impostor = _impostor(token, t)
    runs_before = await _run_count(db_engine)

    cases: list[tuple[Any, Any]] = [
        (provider, forged),  # syntactically valid, forged version
        (provider, _context(other_provider)),  # built for another configuration
        (provider, "jgnorm-v1:sha256:" + "0" * 64),  # a bare version string
        (impostor, _context(provider)),  # a "greenhouse" provider with no snapshot
    ]
    for case_provider, case_context in cases:
        with pytest.raises(NormalizationBindingError):
            await _run(db_engine, case_provider, tracker, observed_at=t, context=case_context)

    assert transport.calls == []
    assert impostor.discover_call_count == 0
    assert await _run_count(db_engine) == runs_before
    assert await _raws_for(db_engine, token) == []


async def test_persist_posting_accepts_only_a_verified_normalization(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("direct")
    t = _unique_time()
    provider, _ = _provider(
        [_board(token)], {token: [_record(token, 1, "Senior Software Engineer")]}, now=t
    )
    (job,) = (await provider.discover(QUERY)).jobs
    raw_id = await provider_execution._write_fetched_row(db_engine, job, job.discovered_at)
    tracker.raw_ids.add(raw_id)
    for unverified in (_context(provider), "jgnorm-v1:sha256:" + "0" * 64, object()):
        with pytest.raises(NormalizationBindingError):
            await persistence.persist_posting(
                db_engine,
                resolve_identity(job),
                job,
                t,
                raw_id,
                normalization=unverified,  # type: ignore[arg-type]
            )
    async with AsyncSession(bind=db_engine) as session:
        raw = await session.get(RawJobIngestion, raw_id)
        assert raw is not None
        assert (raw.processing_status, raw.parser_version) == ("fetched", None)


# ---------------------------------------------------------------------------
# A4: the locked Job row serializes competing normalized updates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("first", ["tier1", "tier2"])
async def test_competing_updates_through_different_occurrence_keys_serialize(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch, first: str
) -> None:
    board_a, board_b = tracker.token("lock-a"), tracker.token("lock-b")
    t = _unique_time()
    shared = f"https://job-boards.greenhouse.io/{board_a}/jobs/1"
    # The Job both postings resolve to, with nothing normalized yet.
    seed_provider, _ = _provider(
        [_board(board_a)], {board_a: [_record(board_a, 1, "Software Engineer")]}, now=t
    )
    await _run(db_engine, seed_provider, tracker, observed_at=t)
    seeded = await _persisted(db_engine, board_a, "1")

    t_a, t_b = t + timedelta(hours=1), t + timedelta(hours=2)
    tier1_record = _record(
        board_a, 1, "Senior Software Engineer", "This is a full-time position.", "Austin, TX"
    )
    tier2_record = _record(board_b, 2, "Staff Software Engineer (Part-Time)", url=shared)
    provider_a, _ = _provider(
        [_board(board_a), _board(board_b)], {board_a: [tier1_record], board_b: []}, now=t_a
    )
    provider_b, _ = _provider(
        [_board(board_a), _board(board_b)], {board_a: [], board_b: [tier2_record]}, now=t_b
    )
    (job_a,) = (await provider_a.discover(QUERY)).jobs
    (job_b,) = (await provider_b.discover(QUERY)).jobs
    verified = verify_normalization_context(_context(provider_a), provider_a)
    raw_a = await provider_execution._write_fetched_row(db_engine, job_a, job_a.discovered_at)
    raw_b = await provider_execution._write_fetched_row(db_engine, job_b, job_b.discovered_at)
    tracker.raw_ids |= {raw_a, raw_b}

    holding, release = asyncio.Event(), asyncio.Event()
    entered: list[int] = []

    async def hold_first() -> None:
        entered.append(1)
        if len(entered) == 1:
            holding.set()
            await release.wait()

    monkeypatch.setattr(persistence, "_after_normalized_flush", hold_first)

    def persist(job: DiscoveredJob, raw_id: uuid.UUID, observed: datetime) -> Any:
        return persistence.persist_posting(
            db_engine, resolve_identity(job), job, observed, raw_id, normalization=verified
        )

    order = [(job_a, raw_a, t_a), (job_b, raw_b, t_b)]
    if first == "tier2":
        order.reverse()
    first_task = asyncio.create_task(persist(*order[0]))
    await asyncio.wait_for(holding.wait(), timeout=30)
    second_task = asyncio.create_task(persist(*order[1]))
    await asyncio.sleep(0.5)
    assert not second_task.done()  # blocked on the Job row lock, not interleaved
    assert len(entered) == 1
    release.set()
    outcome_first, outcome_second = await asyncio.wait_for(
        asyncio.gather(first_task, second_task), timeout=30
    )
    assert outcome_first.job_id == outcome_second.job_id == seeded.job.id

    async with AsyncSession(bind=db_engine) as session:
        job = await session.get(Job, seeded.job.id)
        assert job is not None
        entries = _entries(job)
        # Trust decides employment (parsed beats a newer inferred value); recency
        # decides seniority (equal trust); the country only A supplied. The same
        # final state results in either lock order, with no lost update.
        assert _values(job) == {
            "employment_type": "full_time",
            "seniority": "staff",
            "country": "United States",
        }
        assert entries["employment_type"]["raw_job_ingestion_id"] == str(raw_a)
        assert entries["seniority"]["raw_job_ingestion_id"] == str(raw_b)
        assert entries["country"]["raw_job_ingestion_id"] == str(raw_a)
        for raw_id in (raw_a, raw_b):
            raw = await session.get(RawJobIngestion, raw_id)
            assert raw is not None
            assert (raw.processing_status, raw.parser_version) == (
                "normalized",
                verified.parser_version,
            )


# ---------------------------------------------------------------------------
# Correction 1: equal-time conflicts are refused, never ordered by version
# ---------------------------------------------------------------------------

FULL_TIME = "This is a full-time position."
PART_TIME = "We are hiring for a part-time role."


@pytest.mark.parametrize("order", ["v1_then_v2", "v2_then_v1", "same_version"])
async def test_equal_time_conflicting_values_are_refused_with_full_rollback(
    db_engine: AsyncEngine, tracker: Tracker, order: str
) -> None:
    token = tracker.token("equaltime")
    extra = tracker.token("equaltime-extra")
    t = _unique_time()

    def provider_for(version: str, description: str) -> GreenhouseJobBoardProvider:
        record = _record(token, 1, "Software Engineer", description)
        boards = [_board(token)]
        routes: dict[str, list[dict[str, Any]]] = {token: [record]}
        if version == "v2":
            boards.append(_board(extra))
            routes[extra] = []
        return _provider(boards, routes, now=t)[0]

    first_version, second_version = {
        "v1_then_v2": ("v1", "v2"),
        "v2_then_v1": ("v2", "v1"),
        "same_version": ("v1", "v1"),
    }[order]
    first = provider_for(first_version, FULL_TIME)
    await _run(db_engine, first, tracker, observed_at=t, context=_context(first))
    before = await _persisted(db_engine, token, "1")
    assert before.job.employment_type == "full_time"

    second = provider_for(second_version, PART_TIME)
    if order != "same_version":
        assert _context(second).parser_version != _context(first).parser_version
    with pytest.raises(ProvenanceIntegrityError):
        await _run(db_engine, second, tracker, observed_at=t, context=_context(second))

    after = await _persisted(db_engine, token, "1")
    assert _values(after.job) == _values(before.job)
    assert after.job.field_provenance == before.job.field_provenance
    assert after.job.last_seen_at == before.job.last_seen_at
    assert after.occurrence.last_seen_at == before.occurrence.last_seen_at
    assert [raw.id for raw in after.raws] == [raw.id for raw in before.raws]
    unlinked = [r for r in await _raws_for(db_engine, token) if r.job_occurrence_id is None]
    (refused,) = unlinked
    assert (refused.processing_status, refused.parser_version) == ("fetched", None)
    async with AsyncSession(bind=db_engine) as session:
        runs = (
            (await session.execute(select(CollectionRun).where(CollectionRun.started_at == t)))
            .scalars()
            .all()
        )
        assert sorted(run.status for run in runs) == ["completed", "failed"]


@pytest.mark.parametrize("first", ["agreeing", "conflicting"])
async def test_concurrent_equal_time_conflicting_write_is_refused_in_either_order(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch, first: str
) -> None:
    """Two postings resolving to one Job at the same instant: one agrees with
    the stored value (a no-op), one conflicts. The conflicting one is refused,
    and the stored state is identical whichever acquires the Job lock first."""
    board_a, board_b = tracker.token("eqlock-a"), tracker.token("eqlock-b")
    t = _unique_time()
    shared = f"https://job-boards.greenhouse.io/{board_a}/jobs/1"
    boards = [_board(board_a), _board(board_b)]
    seed_record = _record(board_a, 1, "Senior Software Engineer")
    seed_provider, _ = _provider(boards, {board_a: [seed_record], board_b: []}, now=t)
    await _run(db_engine, seed_provider, tracker, observed_at=t, context=_context(seed_provider))
    seeded = await _persisted(db_engine, board_a, "1")
    assert seeded.job.seniority == "senior"

    agreeing_record = _record(board_a, 1, "Senior Software Engineer")
    conflicting_record = _record(board_b, 2, "Staff Software Engineer", url=shared)
    provider, _ = _provider(
        boards, {board_a: [agreeing_record], board_b: [conflicting_record]}, now=t
    )
    jobs = {job.source_tenant_id: job for job in (await provider.discover(QUERY)).jobs}
    verified = verify_normalization_context(_context(provider), provider)
    raw_ids: dict[str, uuid.UUID] = {}
    for token in (board_a, board_b):
        raw_ids[token] = await provider_execution._write_fetched_row(
            db_engine, jobs[token], jobs[token].discovered_at
        )
    tracker.raw_ids |= set(raw_ids.values())

    holding, release = asyncio.Event(), asyncio.Event()
    flushes: list[str] = []

    async def hold_first() -> None:
        flushes.append("flush")
        if len(flushes) == 1:
            holding.set()
            await release.wait()

    monkeypatch.setattr(persistence, "_after_normalized_flush", hold_first)

    def persist(token: str) -> Any:
        job = jobs[token]
        return persistence.persist_posting(
            db_engine, resolve_identity(job), job, t, raw_ids[token], normalization=verified
        )

    if first == "agreeing":
        agreeing_task = asyncio.create_task(persist(board_a))
        await asyncio.wait_for(holding.wait(), timeout=30)
        conflicting_task = asyncio.create_task(persist(board_b))
        await asyncio.sleep(0.5)
        assert not conflicting_task.done()  # blocked on the Job row lock
        release.set()
        agreeing_outcome, conflicting_outcome = await asyncio.wait_for(
            asyncio.gather(agreeing_task, conflicting_task, return_exceptions=True), timeout=30
        )
    else:
        release.set()  # the conflicting write is refused before its flush seam
        (conflicting_outcome,) = await asyncio.wait_for(
            asyncio.gather(persist(board_b), return_exceptions=True), timeout=30
        )
        agreeing_outcome = await asyncio.wait_for(persist(board_a), timeout=30)

    assert isinstance(conflicting_outcome, ProvenanceIntegrityError)
    assert not isinstance(agreeing_outcome, BaseException)
    after = await _persisted(db_engine, board_a, "1")
    assert after.job.id == seeded.job.id
    assert _values(after.job) == _values(seeded.job)
    assert after.job.field_provenance == seeded.job.field_provenance
    async with AsyncSession(bind=db_engine) as session:
        refused = await session.get(RawJobIngestion, raw_ids[board_b])
        assert refused is not None
        assert (refused.processing_status, refused.parser_version) == ("fetched", None)
        assert refused.job_occurrence_id is None
        attached = (
            await session.execute(
                select(JobOccurrence).where(JobOccurrence.source_tenant_id == board_b)
            )
        ).scalar_one_or_none()
        assert attached is None  # the refused Tier 2 attach was rolled back
        agreed = await session.get(RawJobIngestion, raw_ids[board_a])
        assert agreed is not None
        assert (agreed.processing_status, agreed.parser_version) == (
            "normalized",
            verified.parser_version,
        )
