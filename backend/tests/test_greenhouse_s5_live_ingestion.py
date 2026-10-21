"""Offline proof of the Phase 4 S5 live-ingestion composition (ADR 0020).

Everything here is offline. The S5 worker pipeline runs the real
`GreenhouseJobBoardProvider` over `httpx.MockTransport` (behind the real S5
request guard), the real normalization context, `pipeline.run`, and the real
S4 routes against the disposable PostgreSQL test database. The autouse S3
network guard fails any real HTTP transport and any non-loopback socket.
The database lifecycle (`CREATE`/`DROP DATABASE`) and the supervisor are
exercised with fakes; no test creates or drops a database.
"""

from __future__ import annotations

import ast
import asyncio
import json
import secrets
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import CollectionRun
from app.ingestion import persistence
from app.ingestion.normalized_fields import build_normalization_context
from app.providers.greenhouse import GreenhouseBoard, GreenhouseJobBoardProvider
from app.providers.greenhouse_content import GreenhouseContentMode
from app.schemas.provider import SourceQuery
from scripts import run_greenhouse_s2c_canary as s2c
from scripts import run_greenhouse_s5_live_ingestion as s5
from tests.test_normalized_persistence import (  # noqa: F401 - autouse network guard
    PROJECTED_FIXTURE,
    Tracker,
    _cleanup,
    _ingest,
    _record,
    network_guard,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BACKEND_DIR / "scripts" / "run_greenhouse_s5_live_ingestion.py"
DECLARED: GreenhouseContentMode = "declared-double-escaped"
LIVE_VERSION = "jgnorm-v1:sha256:f086bdd675c364dc250b0770dafedb13c75d3809b905bda6f7373bee62441e32"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TrackingClock:
    """Strictly increasing, unique times; every value is tracked for cleanup."""

    def __init__(self, tracked: Tracker) -> None:
        self._tracked = tracked
        self._next = datetime(2032, 1, 1, tzinfo=UTC) + timedelta(seconds=secrets.randbelow(10**8))

    def now(self) -> datetime:
        value = self._next
        self._next = value + timedelta(seconds=1)
        self._tracked.run_times.add(value)
        return value


@pytest.fixture
async def tracker(db_engine: AsyncEngine) -> AsyncIterator[Tracker]:
    tracked = Tracker()
    try:
        yield tracked
    finally:
        await _cleanup(db_engine, tracked)


def _records(token: str, count: int) -> list[dict[str, Any]]:
    return [
        _record(
            token,
            1000 + index,
            f"Synthetic S5 Role {index} Engineer",
            "This is a full-time position.",
            "Toronto, Canada",
        )
        for index in range(count)
    ]


def _envelope(records: list[dict[str, Any]], *, total: int | None = None) -> bytes:
    meta_total = len(records) if total is None else total
    return json.dumps({"jobs": records, "meta": {"total": meta_total}}).encode("utf-8")


class BodyStream(httpx.AsyncByteStream):
    """An unread streamed body, as a real transport returns it."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self._body), 65536):
            yield self._body[start : start + 65536]


@dataclass
class Served:
    calls: int = 0


def _serving(
    body: bytes | None = None,
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
    exc: Exception | None = None,
) -> tuple[Callable[[], httpx.AsyncBaseTransport], Served]:
    served = Served()

    def handler(request: httpx.Request) -> httpx.Response:
        served.calls += 1
        if exc is not None:
            raise exc
        return httpx.Response(
            status,
            stream=BodyStream(body or b""),
            headers=headers if headers is not None else {"content-type": "application/json"},
        )

    return (lambda: httpx.MockTransport(handler)), served


def _board(token: str) -> GreenhouseBoard:
    return GreenhouseBoard(token, token.title(), content_mode=DECLARED)


def _version(token: str) -> str:
    return build_normalization_context({token: DECLARED}).parser_version


def _plan(
    tracked: Tracker,
    token: str,
    factory: Callable[[], httpx.AsyncBaseTransport],
    **overrides: Any,
) -> s5.IngestionPlan:
    values: dict[str, Any] = {
        "board": _board(token),
        "inner_transport_factory": factory,
        "expected_parser_version": _version(token),
        "request_path": f"/v1/boards/{token}/jobs",
        "fresh_database": False,
        "clock": TrackingClock(tracked),
    }
    values.update(overrides)
    return s5.IngestionPlan(**values)


async def _runs(engine: AsyncEngine, tracked: Tracker) -> list[CollectionRun]:
    async with AsyncSession(bind=engine) as session:
        return list(
            (
                await session.execute(
                    select(CollectionRun)
                    .where(CollectionRun.started_at.in_(tracked.run_times))
                    .order_by(CollectionRun.started_at)
                )
            )
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# Constants and parser version
# ---------------------------------------------------------------------------


def test_request_constants_are_s2c_frozen_values() -> None:
    assert s5.BOARD_TOKEN == "discord"
    assert s5.REQUEST_PATH == "/v1/boards/discord/jobs"
    assert s2c.REQUEST_HOST == "boards-api.greenhouse.io"
    assert s2c.REQUEST_QUERY == "content=true"
    assert s5.ACCEPT_ENCODING == "identity"
    assert s5.MAX_RESPONSE_BYTES == 5_000_000
    assert s5.MAX_SOURCE_RECORDS == 500
    assert s5.S5_SETTINGS.max_attempts == 1
    assert s5.S5_SETTINGS.max_response_bytes == 5_000_000
    assert s5.request_fingerprint() == s2c.request_fingerprint()
    board = s5.live_board()
    assert (board.board_token, board.company, board.content_mode) == (
        "discord",
        "Discord",
        DECLARED,
    )


def test_live_parser_version_is_computed_offline() -> None:
    assert s5.live_parser_version() == LIVE_VERSION


# ---------------------------------------------------------------------------
# Request guard
# ---------------------------------------------------------------------------


def _guard(
    body: bytes = b'{"jobs": []}', **kwargs: Any
) -> tuple[s5.GuardTransport, s5.Capture, Served]:
    factory, served = _serving(body, **kwargs)
    capture = s5.Capture()
    return s5.GuardTransport(factory(), s5.SendLatch(), capture), capture, served


PERMITTED = "https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true"


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("POST", PERMITTED),
        ("GET", "http://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true"),
        ("GET", "https://example.invalid/v1/boards/discord/jobs?content=true"),
        ("GET", "https://boards-api.greenhouse.io:8443/v1/boards/discord/jobs?content=true"),
        ("GET", "https://boards-api.greenhouse.io/v1/boards/other/jobs?content=true"),
        ("GET", "https://boards-api.greenhouse.io/v1/boards/discord/jobs"),
        ("GET", "https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=false"),
        ("GET", PERMITTED + "#x"),
    ],
)
async def test_guard_refuses_every_other_request_before_io(method: str, url: str) -> None:
    guard, capture, served = _guard()
    with pytest.raises(s5.S5Refusal) as refused:
        await guard.handle_async_request(httpx.Request(method, url))
    assert refused.value.kind == "request_shape_refused"
    assert served.calls == 0 and capture.request_sent is False


async def test_guard_sets_identity_encoding_and_refuses_a_second_send() -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(
            200, stream=BodyStream(b'{"jobs": []}'), headers={"content-type": "application/json"}
        )

    latch = s5.SendLatch()
    capture = s5.Capture()
    factory = s5.guarded_factory(lambda: httpx.MockTransport(handler), latch, capture)
    first = factory()
    await first.handle_async_request(httpx.Request("GET", PERMITTED, headers={"user-agent": "x"}))
    assert seen[0]["accept-encoding"] == "identity"
    assert capture.observed_user_agent == "x" and capture.complete
    second = factory()  # a fresh transport shares the process-wide latch
    with pytest.raises(s5.S5Refusal) as refused:
        await second.handle_async_request(httpx.Request("GET", PERMITTED))
    assert refused.value.kind == "second_request_refused"
    assert len(seen) == 1


async def test_guard_refuses_non_identity_encoding() -> None:
    guard, _, _ = _guard(headers={"content-type": "application/json", "content-encoding": "gzip"})
    with pytest.raises(s5.S5Refusal) as refused:
        await guard.handle_async_request(httpx.Request("GET", PERMITTED))
    assert refused.value.kind == "unexpected_content_encoding"


async def test_guard_refuses_oversized_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(s5, "MAX_RESPONSE_BYTES", 10)
    guard, capture, _ = _guard(b'{"jobs": [], "pad": "xxxxxxxx"}')
    with pytest.raises(s5.S5Refusal) as refused:
        await guard.handle_async_request(httpx.Request("GET", PERMITTED))
    assert refused.value.kind == "response_cap_exceeded"
    assert capture.complete is False and capture.sha256 is None


async def test_guard_refuses_more_than_500_records() -> None:
    guard, _, _ = _guard(_envelope([{"id": i} for i in range(501)]))
    with pytest.raises(s5.S5Refusal) as refused:
        await guard.handle_async_request(httpx.Request("GET", PERMITTED))
    assert refused.value.kind == "record_cap_exceeded"


async def test_guard_does_not_drain_a_non_200_response() -> None:
    guard, capture, _ = _guard(b"nope", status=503)
    response = await guard.handle_async_request(httpx.Request("GET", PERMITTED))
    assert response.status_code == 503
    assert capture.status == 503 and capture.complete is False


def test_guard_refusal_is_not_an_httpx_exception() -> None:
    assert not issubclass(s5.S5Refusal, httpx.HTTPError)
    assert issubclass(s5.S5Refusal, s2c.CanaryRefusal)


async def test_second_discover_on_the_live_provider_is_refused_before_io() -> None:
    factory, served = _serving(_envelope([]))
    latch, capture = s5.SendLatch(), s5.Capture()
    provider = GreenhouseJobBoardProvider(
        [s5.live_board()],
        settings=s5.S5_SETTINGS,
        transport_factory=s5.guarded_factory(factory, latch, capture),
    )
    await provider.discover(SourceQuery(sources=["greenhouse"]))
    with pytest.raises(s5.S5Refusal) as refused:
        await provider.discover(SourceQuery(sources=["greenhouse"]))
    assert refused.value.kind == "second_request_refused"
    assert served.calls == 1


# ---------------------------------------------------------------------------
# Worker pipeline: success, replay, re-observation, API visibility
# ---------------------------------------------------------------------------


async def test_complete_path_passes_and_is_readable_through_the_api(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("s5-pass")
    records = _records(token, 3)
    body = _envelope(records)
    factory, served = _serving(body)
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))

    assert summary["verdict"] == "PASS", summary["reason"]
    assert served.calls == 1  # re-observation never uses the injected transport
    assert summary["request"]["sent"] is True
    assert summary["request"]["byte_count"] == len(body)
    assert summary["request"]["source_record_count"] == 3
    assert summary["run"]["status"] == "completed"
    assert (summary["run"]["jobs_inserted"], summary["run"]["jobs_updated"]) == (3, 0)
    persisted = summary["persisted"]
    assert persisted["raw_status_counts"] == {"normalized": 3}
    assert persisted["raw_parser_versions"] == [_version(token)]
    assert (persisted["jobs"], persisted["occurrences"], persisted["identity_conflicts"]) == (
        3,
        3,
        0,
    )
    assert persisted["normalized_non_null"]["employment_type"] == 3
    assert persisted["normalized_non_null"]["country"] == 3

    api = summary["api"]
    assert api["listed_all_persisted"] and api["details_ok"] and api["detail_keys_exact"]
    item = api["representative_list_item"]
    assert set(item) == s5.LIST_KEYS
    assert item["title"].startswith("<redacted:") and item["location_raw"].startswith("<redacted:")
    assert item["canonical_url"] == "https://job-boards.greenhouse.io/<redacted>"
    assert item["employment_type"] == "full_time" and item["country"] == "Canada"
    detail = api["representative_detail"]
    assert set(detail) == s5.DETAIL_KEYS
    assert detail["occurrences"][0]["provider"] == "greenhouse"
    assert detail["occurrences"][0]["source_url"] == "https://job-boards.greenhouse.io/<redacted>"

    again = summary["reobservation"]
    assert again["run"]["status"] == "completed"
    assert (again["run"]["jobs_inserted"], again["run"]["jobs_updated"]) == (0, 3)
    assert again["persisted"]["raw_status_counts"] == {"normalized": 6}
    assert (again["persisted"]["jobs"], again["persisted"]["occurrences"]) == (3, 3)
    assert again["last_seen_advanced"] is True

    text = json.dumps(summary)
    for record in records:
        assert record["title"] not in text
        assert f"/{token}/jobs/" not in text
    assert "full-time position" not in text and "Toronto" not in text


async def test_committed_s2c_projected_record_replays_through_the_composition(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    document = json.loads(PROJECTED_FIXTURE.read_text(encoding="utf-8"))
    (record,) = document["replay_envelope"]["jobs"]
    token = tracker.token("s5-replay")
    factory, _ = _serving(_envelope([record]))
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert summary["verdict"] == "PASS", summary["reason"]
    assert summary["persisted"]["raw_status_counts"] == {"normalized": 1}


async def test_api_exact_listing_detects_unrelated_rows(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("s5-exact")
    other = tracker.token("s5-other")
    await _ingest(
        db_engine, tracker, other, _records(other, 1)[0], datetime(2033, 1, 1, tzinfo=UTC)
    )
    factory, _ = _serving(_envelope(_records(token, 1)))
    summary = await s5.run_worker_pipeline(
        db_engine, _plan(tracker, token, factory, reobserve=False)
    )
    assert summary["verdict"] == "PASS"
    job_ids = (
        await s5.persisted_state(db_engine, token, ["1000"], datetime.min.replace(tzinfo=UTC))
    )["_job_ids"]
    api = await s5.api_check(db_engine, job_ids, exact=True)
    assert api["listed_all_persisted"] is True
    assert api["listed_only_persisted"] is False
    assert s5.api_passed(api, exact=True) == "api_listed_only_persisted"


# ---------------------------------------------------------------------------
# Fail-closed and inconclusive outcomes
# ---------------------------------------------------------------------------


async def test_parser_version_mismatch_refuses_before_any_request_or_row(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("s5-version")
    factory, served = _serving(_envelope(_records(token, 1)))
    summary = await s5.run_worker_pipeline(
        db_engine,
        _plan(tracker, token, factory, expected_parser_version=LIVE_VERSION),
    )
    assert (summary["verdict"], summary["reason"]) == (
        "FAIL-CLOSED",
        "parser_version_mismatch_before_request",
    )
    assert served.calls == 0
    assert await _runs(db_engine, tracker) == []


async def test_non_fresh_database_refuses_before_any_request(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def not_fresh(engine: AsyncEngine) -> dict[str, int]:
        return {"jobs": 1}

    monkeypatch.setattr(s5, "database_row_counts", not_fresh)
    token = tracker.token("s5-fresh")
    factory, served = _serving(_envelope(_records(token, 1)))
    summary = await s5.run_worker_pipeline(
        db_engine, _plan(tracker, token, factory, fresh_database=True)
    )
    assert (summary["verdict"], summary["reason"]) == ("FAIL-CLOSED", "database_not_fresh")
    assert served.calls == 0


@pytest.mark.parametrize(
    ("serve", "verdict", "reason"),
    [
        ({"status": 429}, "INCONCLUSIVE", "adapter:http_status"),
        ({"status": 503}, "INCONCLUSIVE", "adapter:http_status"),
        ({"status": 404}, "FAIL-CLOSED", "adapter:http_status"),
        (
            {"status": 301, "headers": {"location": "https://example.invalid/"}},
            "FAIL-CLOSED",
            "adapter:redirect",
        ),
        ({"headers": {"content-type": "text/html"}}, "FAIL-CLOSED", "adapter:media_type"),
        ({"body": b"{not json"}, "FAIL-CLOSED", "adapter:invalid_json"),
        ({"body": b'{"no_jobs": []}'}, "FAIL-CLOSED", "adapter:envelope"),
        ({"exc": httpx.ReadTimeout("t")}, "INCONCLUSIVE", "adapter:timeout"),
        ({"exc": httpx.ConnectError("c")}, "INCONCLUSIVE", "adapter:connect_error"),
    ],
)
async def test_provider_failures_are_never_pass_and_write_no_rows(
    db_engine: AsyncEngine,
    tracker: Tracker,
    serve: dict[str, Any],
    verdict: str,
    reason: str,
) -> None:
    token = tracker.token("s5-fail")
    body = serve.pop("body", _envelope(_records(token, 1)))
    factory, served = _serving(body, **serve)
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert (summary["verdict"], summary["reason"]) == (verdict, reason)
    assert served.calls == 1  # max_attempts=1: no retry
    assert summary["run"]["status"] == "completed_with_errors"
    assert summary["run"]["attempt_status"] == "failed"
    assert summary["persisted"]["raw_rows"] == 0
    assert summary["api"] is None and summary["reobservation"] is None


async def test_content_abstention_is_inconclusive_not_pass(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    token = tracker.token("s5-abstain")
    records = _records(token, 2)
    records[1]["content"] = None
    factory, _ = _serving(_envelope(records))
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert (summary["verdict"], summary["reason"]) == ("INCONCLUSIVE", "attempt_partial")
    assert summary["run"]["status"] == "completed_with_errors"


async def test_duplicate_records_are_never_pass(db_engine: AsyncEngine, tracker: Tracker) -> None:
    token = tracker.token("s5-dup")
    (record,) = _records(token, 1)
    factory, _ = _serving(_envelope([record, dict(record)]))
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert summary["verdict"] != "PASS"


async def test_meta_total_mismatch_is_never_pass(db_engine: AsyncEngine, tracker: Tracker) -> None:
    token = tracker.token("s5-meta")
    factory, _ = _serving(_envelope(_records(token, 2), total=3))
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert summary["verdict"] != "PASS"


async def test_identity_conflict_is_fail_closed(db_engine: AsyncEngine, tracker: Tracker) -> None:
    token = tracker.token("s5-conflict")
    await _ingest(
        db_engine,
        tracker,
        token,
        _record(token, 1, "Software Engineer"),
        datetime(2031, 6, 1, tzinfo=UTC),
    )
    moved = _record(
        token,
        1,
        "Senior Software Engineer",
        "This is a full-time position.",
        "Toronto, Canada",
        url=f"https://job-boards.greenhouse.io/{token}/jobs/1-moved",
    )
    factory, _ = _serving(_envelope([moved]))
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert (summary["verdict"], summary["reason"]) == ("FAIL-CLOSED", "run_completed_with_errors")
    assert summary["persisted"]["identity_conflicts"] == 1


@pytest.mark.parametrize(
    ("records", "headers", "kind"),
    [
        (501, None, "record_cap_exceeded"),
        (
            1,
            {"content-type": "application/json", "content-encoding": "br"},
            "unexpected_content_encoding",
        ),
    ],
)
async def test_guard_refusal_fails_the_run_before_any_raw_row(
    db_engine: AsyncEngine,
    tracker: Tracker,
    records: int,
    headers: dict[str, str] | None,
    kind: str,
) -> None:
    token = tracker.token("s5-refuse")
    factory, _ = _serving(_envelope(_records(token, records)), headers=headers)
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert (summary["verdict"], summary["reason"]) == ("FAIL-CLOSED", f"refusal:{kind}")
    assert summary["persisted"]["raw_rows"] == 0
    (run,) = await _runs(db_engine, tracker)
    assert run.status == "failed"


async def test_failure_at_posting_k_is_per_posting_atomic_and_fail_closed(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def fail_second() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected after the normalized flush")

    monkeypatch.setattr(persistence, "_after_normalized_flush", fail_second)
    token = tracker.token("s5-k")
    factory, _ = _serving(_envelope(_records(token, 3)))
    summary = await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    assert (summary["verdict"], summary["reason"]) == (
        "FAIL-CLOSED",
        "pipeline_exception:RuntimeError",
    )
    persisted = summary["persisted"]
    # Posting 1 is complete; posting 2 rolled back whole; posting 3 never ran.
    assert persisted["raw_status_counts"] == {"fetched": 2, "normalized": 1}
    assert persisted["raw_parser_versions"] == sorted(["none", _version(token)])
    assert (persisted["jobs"], persisted["occurrences"]) == (1, 1)
    assert persisted["normalized_non_null"]["employment_type"] == 1
    (run,) = await _runs(db_engine, tracker)
    assert run.status == "failed"


async def test_cancellation_during_persistence_is_fail_closed(
    db_engine: AsyncEngine, tracker: Tracker, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def cancel() -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(persistence, "_after_normalized_flush", cancel)
    token = tracker.token("s5-cancel")
    factory, _ = _serving(_envelope(_records(token, 2)))
    with pytest.raises(asyncio.CancelledError):
        await s5.run_worker_pipeline(db_engine, _plan(tracker, token, factory))
    (run,) = await _runs(db_engine, tracker)
    assert run.status == "failed"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_redaction_keeps_only_categorical_values() -> None:
    item = {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": "Secret Title",
        "company": {"id": "c", "name": "Name"},
        "location_raw": "Somewhere",
        "country": "Canada",
        "employment_type": "full_time",
        "seniority": None,
        "canonical_url": "https://job-boards.greenhouse.io/discord/jobs/123?gh_jid=1",
        "first_seen_at": "t",
        "last_seen_at": "t",
        "active": True,
        "description_clean": "text",
        "occurrences": [{"source_url": "not a url", "apply_url": None, "provider": "greenhouse"}],
    }
    redacted = s5.redact_item(item)
    assert redacted["title"] == "<redacted:12 chars>"
    assert redacted["location_raw"] == "<redacted:9 chars>"
    assert redacted["description_clean"] == "<redacted:4 chars>"
    assert redacted["company"] == {"id": "c", "name": "<redacted>"}
    assert redacted["canonical_url"] == "https://job-boards.greenhouse.io/<redacted>"
    assert redacted["occurrences"][0]["source_url"] == "<redacted:9 chars>"
    assert redacted["occurrences"][0]["apply_url"] is None
    assert (redacted["country"], redacted["employment_type"]) == ("Canada", "full_time")


# ---------------------------------------------------------------------------
# Gates, database target, reservation, supervision, and cleanup (fakes only)
# ---------------------------------------------------------------------------

DEV_URL = "postgresql+asyncpg://u:p@localhost:5432/jobgoblin"


@pytest.fixture
def auth_file(tmp_path: Path) -> tuple[Path, str]:
    path = tmp_path / "authorization.md"
    path.write_text("authorized once\n", encoding="utf-8")
    return path, s2c.file_sha256(path)


def _request(auth: tuple[Path, str], **overrides: Any) -> s5.LiveRequest:
    values: dict[str, Any] = {
        "board": "discord",
        "expected_sha": "a" * 40,
        "expected_parser_version": LIVE_VERSION,
        "authorization_file": auth[0],
        "authorization_sha256": auth[1],
    }
    values.update(overrides)
    return s5.LiveRequest(**values)


ENV = {s5.LIVE_ENV_VAR: s5.LIVE_ENV_VALUE}


def _preflight(
    request: s5.LiveRequest,
    paths: s5.AttemptPaths,
    *,
    env: dict[str, str] = ENV,
    head: str = "a" * 40,
    clean: bool = True,
    name: str | None = None,
    dev: str = DEV_URL,
    app_env: str = "development",
) -> dict[str, Any]:
    return s5.live_preflight(
        request,
        env=env,
        paths=paths,
        head_sha=lambda: head,
        tree_is_clean=lambda: clean,
        database_name=name or s5.generate_database_name(),
        development_url=dev,
        app_env=app_env,
    )


def test_preflight_accepts_only_the_complete_gate(
    tmp_path: Path, auth_file: tuple[Path, str]
) -> None:
    paths = s5.AttemptPaths(tmp_path / "attempt")
    record = _preflight(_request(auth_file), paths)
    assert record["board_token"] == "discord"
    assert record["parser_version"] == LIVE_VERSION
    assert record["request_fingerprint"] == s2c.request_fingerprint()
    assert record["database_name"].startswith("jobgoblin_test_s5_")
    assert not paths.directory.exists()


@pytest.mark.parametrize(
    ("change", "kind"),
    [
        ({"env": {}}, "gate_disabled"),
        ({"env": {s5.LIVE_ENV_VAR: "yes"}}, "gate_disabled"),
        ({"request": {"board": "other"}}, "board_not_allowlisted"),
        ({"head": "b" * 40}, "sha_mismatch"),
        ({"request": {"expected_sha": "short"}}, "sha_mismatch"),
        ({"clean": False}, "dirty_tree"),
        ({"request": {"authorization_sha256": "0" * 64}}, "authorization_mismatch"),
        (
            {"request": {"expected_parser_version": "jgnorm-v1:sha256:" + "0" * 64}},
            "parser_version_mismatch",
        ),
        ({"name": "jobgoblin_dev"}, "database_name_invalid"),
        ({"app_env": "production"}, "database_target_refused"),
        (
            {"dev": "postgresql+asyncpg://u:p@db.example.invalid:5432/jobgoblin"},
            "database_target_refused",
        ),
    ],
)
def test_preflight_refuses_each_missing_gate_element(
    tmp_path: Path, auth_file: tuple[Path, str], change: dict[str, Any], kind: str
) -> None:
    paths = s5.AttemptPaths(tmp_path / "attempt")
    request = _request(auth_file, **change.pop("request", {}))
    with pytest.raises(s5.S5Refusal) as refused:
        _preflight(request, paths, **change)
    assert refused.value.kind == kind
    assert not paths.directory.exists()


def test_preflight_refuses_an_existing_attempt(tmp_path: Path, auth_file: tuple[Path, str]) -> None:
    paths = s5.AttemptPaths(tmp_path / "attempt")
    paths.directory.mkdir()
    with pytest.raises(s5.S5Refusal) as refused:
        _preflight(_request(auth_file), paths)
    assert refused.value.kind == "attempt_already_reserved"


def test_database_name_grammar_and_url() -> None:
    name = s5.generate_database_name()
    assert s5.quote_database_name(name) == f'"{name}"'
    for bad in ("jobgoblin_test", "jobgoblin_test_s5_XYZ", 'x"; DROP', name + "0"):
        with pytest.raises(s5.S5Refusal):
            s5.quote_database_name(bad)
    url = s5.assert_database_target(name, DEV_URL, app_env="development")
    assert url.endswith(f"@localhost:5432/{name}")


@dataclass
class FakeLifecycle:
    created: list[str]
    dropped: list[str]
    exists_after_drop: bool = False
    drop_fails: bool = False


@pytest.fixture
def lifecycle(monkeypatch: pytest.MonkeyPatch) -> FakeLifecycle:
    fake = FakeLifecycle(created=[], dropped=[])

    async def reachable(url: str) -> bool:
        return True

    async def create(url: str, name: str) -> None:
        fake.created.append(name)

    async def drop(url: str, name: str) -> None:
        if fake.drop_fails:
            raise OSError("drop failed")
        fake.dropped.append(name)

    async def exists(url: str, name: str) -> bool:
        return fake.exists_after_drop

    monkeypatch.setattr(s5, "admin_reachable", reachable)
    monkeypatch.setattr(s5, "create_database", create)
    monkeypatch.setattr(s5, "drop_database", drop)
    monkeypatch.setattr(s5, "database_exists", exists)
    return fake


class NoContainment:
    def assign(self, pid: int) -> None:
        pass

    def close(self) -> None:
        pass


def _fake_supervisor(
    monkeypatch: pytest.MonkeyPatch,
    paths: s5.AttemptPaths,
    *,
    kind: str = "exited",
    returncode: int | None = 0,
    verdict: str | None = "PASS",
) -> None:
    def supervise(argv: Any, **kwargs: Any) -> s2c.WorkerResult:
        token = kwargs["stdin_payload"].decode("ascii").strip()
        s5.claim_worker(paths, token)  # the real capability check
        if verdict is not None:
            s2c.exclusive_write(
                paths.summary,
                json.dumps({"verdict": verdict, "reason": "all_checks_passed"}).encode("utf-8"),
            )
        return s2c.WorkerResult(kind, returncode)

    monkeypatch.setattr(s2c, "supervise_worker", supervise)


def _run_live(
    tmp_path: Path, auth: tuple[Path, str], paths: s5.AttemptPaths, **request: Any
) -> s5.LiveOutcome:
    return s5.run_live(
        _request(auth, **request),
        env=ENV,
        paths=paths,
        head_sha=lambda: "a" * 40,
        tree_is_clean=lambda: True,
        worker_argv=["unused"],
        development_url=DEV_URL,
        app_env="development",
        containment_factory=NoContainment,
        migrate=lambda url: True,
    )


def _terminal(paths: s5.AttemptPaths) -> dict[str, Any]:
    lines = paths.reservation.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    terminal: dict[str, Any] = json.loads(lines[1])
    return terminal


def test_live_pass_drops_the_database_and_records_one_terminal_outcome(
    tmp_path: Path,
    auth_file: tuple[Path, str],
    lifecycle: FakeLifecycle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = s5.AttemptPaths(tmp_path / "attempt")
    _fake_supervisor(monkeypatch, paths)
    result = _run_live(tmp_path, auth_file, paths)
    assert result.outcome == "PASS:all_checks_passed"
    assert lifecycle.created == lifecycle.dropped and len(lifecycle.created) == 1
    assert result.database_dropped is True and result.database_retained is False
    assert _terminal(paths)["outcome"] == "PASS:all_checks_passed"
    with pytest.raises(s5.S5Refusal) as refused:
        _run_live(tmp_path, auth_file, paths)
    assert refused.value.kind == "attempt_already_reserved"


def test_retention_keeps_only_a_pass_database(
    tmp_path: Path,
    auth_file: tuple[Path, str],
    lifecycle: FakeLifecycle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = s5.AttemptPaths(tmp_path / "pass")
    _fake_supervisor(monkeypatch, paths)
    result = _run_live(tmp_path, auth_file, paths, retain_database_on_pass=True)
    assert result.database_retained is True and lifecycle.dropped == []

    paths = s5.AttemptPaths(tmp_path / "fail")
    _fake_supervisor(monkeypatch, paths, verdict="FAIL-CLOSED")
    result = _run_live(tmp_path, auth_file, paths, retain_database_on_pass=True)
    assert result.outcome.startswith("FAIL-CLOSED:")
    assert result.database_retained is False and len(lifecycle.dropped) == 1


@pytest.mark.parametrize(
    ("kind", "returncode", "verdict", "outcome"),
    [
        ("deadline_terminated", None, None, "FAIL-CLOSED:outer_deadline"),
        ("termination_unconfirmed", None, None, "FAIL-CLOSED:worker_termination_unconfirmed"),
        ("containment_failed", None, None, "FAIL-CLOSED:containment_assignment_failed"),
        ("exited", 1, None, "FAIL-CLOSED:worker_failed"),
        ("exited", 0, None, "FAIL-CLOSED:worker_failed"),
    ],
)
def test_worker_failures_are_fail_closed_and_always_drop(
    tmp_path: Path,
    auth_file: tuple[Path, str],
    lifecycle: FakeLifecycle,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    returncode: int | None,
    verdict: str | None,
    outcome: str,
) -> None:
    paths = s5.AttemptPaths(tmp_path / "attempt")
    _fake_supervisor(monkeypatch, paths, kind=kind, returncode=returncode, verdict=verdict)
    result = _run_live(tmp_path, auth_file, paths, retain_database_on_pass=True)
    assert result.outcome == outcome
    assert result.database_dropped is True and len(lifecycle.dropped) == 1
    assert _terminal(paths)["outcome"] == outcome


@pytest.mark.parametrize("failure", ["drop_fails", "exists_after_drop"])
def test_cleanup_failure_turns_a_pass_into_fail_closed(
    tmp_path: Path,
    auth_file: tuple[Path, str],
    lifecycle: FakeLifecycle,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    setattr(lifecycle, failure, True)
    paths = s5.AttemptPaths(tmp_path / "attempt")
    _fake_supervisor(monkeypatch, paths)
    result = _run_live(tmp_path, auth_file, paths)
    assert result.outcome == "FAIL-CLOSED:cleanup_failed"
    assert _terminal(paths)["outcome"] == "FAIL-CLOSED:cleanup_failed"


def test_migration_failure_never_launches_the_worker_and_drops(
    tmp_path: Path,
    auth_file: tuple[Path, str],
    lifecycle: FakeLifecycle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("worker launched")

    monkeypatch.setattr(s2c, "supervise_worker", never)
    paths = s5.AttemptPaths(tmp_path / "attempt")
    result = s5.run_live(
        _request(auth_file),
        env=ENV,
        paths=paths,
        head_sha=lambda: "a" * 40,
        tree_is_clean=lambda: True,
        worker_argv=["unused"],
        development_url=DEV_URL,
        app_env="development",
        containment_factory=NoContainment,
        migrate=lambda url: False,
    )
    assert result.outcome == "FAIL-CLOSED:database_migrate_failed"
    assert len(lifecycle.dropped) == 1


def test_worker_refuses_without_gate_containment_or_capability(tmp_path: Path) -> None:
    paths = s5.AttemptPaths(tmp_path / "attempt")
    token = "f" * 64
    assert s5.worker_main(paths, env={}, token=token, in_containment=lambda: True) == 3
    assert s5.worker_main(paths, env=ENV, token=token, in_containment=lambda: False) == 3
    assert s5.worker_main(paths, env=ENV, token=token, in_containment=lambda: True) == 3
    assert not paths.summary.exists()


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_script_imports_no_parallel_fetch_path() -> None:
    imports = _imports(SCRIPT)
    for forbidden in (
        "scripts.canary_greenhouse",
        "scripts.live_proof_greenhouse_ingestion",
        "app.ingestion.persistence",
        "app.ingestion.provider_execution",
        "app.ingestion.orchestrator",
        "app.db.session",
    ):
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imports)


def test_script_writes_only_through_the_pipeline() -> None:
    """The only ORM write path is `pipeline.run`; the script itself issues
    only SELECTs and the administrative CREATE/DROP DATABASE statements."""
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        ".add(",
        ".commit(",
        ".flush(",
        "TRUNCATE",
        "persist_posting",
        "_write_fetched_row",
    ):
        assert forbidden not in source, forbidden
    sqlalchemy_names = {name for name in _imports(SCRIPT) if name.startswith("sqlalchemy.")}
    assert sqlalchemy_names <= {
        "sqlalchemy.func",
        "sqlalchemy.select",
        "sqlalchemy.text",
        "sqlalchemy.engine",
        "sqlalchemy.engine.make_url",
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.ext.asyncio.AsyncEngine",
        "sqlalchemy.ext.asyncio.AsyncSession",
        "sqlalchemy.ext.asyncio.async_sessionmaker",
        "sqlalchemy.ext.asyncio.create_async_engine",
    }
    statements = {
        line.strip() for line in source.splitlines() if "DATABASE" in line and 'f"' in line
    }
    assert all("CREATE DATABASE" in s or "DROP DATABASE IF EXISTS" in s for s in statements)


# ---------------------------------------------------------------------------
# Offline rehearsal
# ---------------------------------------------------------------------------


async def test_rehearsal_envelope_passes_the_live_shaped_composition(
    db_engine: AsyncEngine, tracker: Tracker
) -> None:
    """The rehearsal's synthetic `discord` envelope through the live board, the
    live request path, and the live parser version, over `MockTransport`."""
    tracker.tokens.add(s5.BOARD_TOKEN)
    plan = s5.IngestionPlan(
        board=s5.live_board(),
        inner_transport_factory=s5.rehearsal_transport,
        expected_parser_version=LIVE_VERSION,
        fresh_database=False,
        clock=TrackingClock(tracker),
    )
    summary = await s5.run_worker_pipeline(db_engine, plan)
    assert summary["verdict"] == "PASS", summary["reason"]
    assert summary["persisted"]["jobs"] == s5.REHEARSAL_RECORD_COUNT
    assert summary["reobservation"]["last_seen_advanced"] is True
    assert b"SYNTHETIC" in s5.rehearsal_envelope()


def test_rehearsal_runs_the_machinery_and_always_drops(
    tmp_path: Path, lifecycle: FakeLifecycle, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = s5.AttemptPaths(tmp_path / "rehearsal")
    seen: dict[str, Any] = {}

    def supervise(argv: Any, **kwargs: Any) -> s2c.WorkerResult:
        seen.update(kwargs["env"])
        token = kwargs["stdin_payload"].decode("ascii").strip()
        capability = s5.claim_worker(paths, token)
        assert capability["mode"] == "rehearsal"
        s2c.exclusive_write(
            paths.summary, json.dumps({"verdict": "PASS", "reason": "all_checks_passed"}).encode()
        )
        return s2c.WorkerResult("exited", 0)

    monkeypatch.setattr(s2c, "supervise_worker", supervise)
    result = s5.run_rehearsal(
        paths=paths,
        worker_argv=["unused"],
        development_url=DEV_URL,
        app_env="development",
        containment_factory=NoContainment,
        migrate=lambda url: True,
    )
    assert result.outcome == "PASS:all_checks_passed"
    assert seen[s5.LIVE_ENV_VAR] == s5.REHEARSAL_ENV_VALUE
    assert result.database_dropped is True and result.database_retained is False
    assert _terminal(paths)["outcome"] == "PASS:all_checks_passed"


@pytest.mark.parametrize(
    ("mode", "gate"),
    [
        ("live", s5.LIVE_ENV_VALUE),  # live outside the live attempt directory
        ("live", s5.REHEARSAL_ENV_VALUE),
        ("rehearsal", s5.LIVE_ENV_VALUE),
    ],
)
def test_worker_refuses_a_mode_and_gate_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    gate: str,
) -> None:
    def never(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("worker proceeded")

    monkeypatch.setattr(s5, "_worker_async", never)
    paths = s5.AttemptPaths(tmp_path / "attempt")
    record = {
        "event": "reserved",
        "mode": mode,
        "board_token": "discord",
        "request_fingerprint": s2c.request_fingerprint(),
        "parser_version": LIVE_VERSION,
        "database_name": s5.generate_database_name(),
    }
    handle = s5.reserve(paths, record)
    handle.close()
    token = secrets.token_hex(32)
    line = paths.reservation.read_bytes().splitlines(keepends=True)[0]
    s2c.exclusive_write(
        paths.launch, json.dumps(s5.launch_capability(line, token), sort_keys=True).encode()
    )
    code = s5.worker_main(
        paths, env={s5.LIVE_ENV_VAR: gate}, token=token, in_containment=lambda: True
    )
    assert code == 3
    assert not paths.summary.exists()
