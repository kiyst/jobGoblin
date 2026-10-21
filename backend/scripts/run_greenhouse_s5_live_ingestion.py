"""Phase 4 S5: one bounded live Greenhouse ingestion into a disposable local
PostgreSQL database, read back through the S4 jobs API (ADR 0020).

The composition root for the first live ingestion. It reuses, unchanged:

- the S1 adapter (`GreenhouseJobBoardProvider`, board `discord`,
  `declared-double-escaped`), which embeds the S2b converter;
- S3's normalization context (`build_normalization_context`), verified again
  by `pipeline.run`;
- `pipeline.run` and its transaction boundaries, which are the only writers;
- the S4 routes (`create_app()`), with only the reader's session binding
  pointed at the disposable database; and
- the reviewed S2c supervision, reservation, request-shape, and
  failure-classification code, by import.

Nothing is registered, scheduled, or wired into the application. No file
under `app/` changes, so the D1 parser version is unchanged.

Live operation is disabled by default. `live` requires every gate element:
`JOBGOBLIN_S5_LIVE_INGESTION=authorized-once`, the allowlisted board, a clean
checkout whose HEAD is the authorized SHA, the authorization record and its
SHA-256, the expected parser version (checked offline, before any network
or database work), and no existing attempt directory. The attempt directory
is created exclusively and holds the fsynced reservation, so a second
attempt is always refused.

Sequence (the parent process is the supervisor):

1. preflight (gates, both database-safety guards, maintenance-database
   reachability);
2. reservation;
3. `CREATE DATABASE` of a generated `jobgoblin_test_s5_<hex>` name and
   `alembic upgrade head` on it;
4. a supervised worker (kill-on-close Job Object, one wall-clock deadline)
   that checks the database is fresh, makes the one guarded request through
   `pipeline.run`, checks the persisted rows, reads them back through
   `GET /jobs` and `GET /jobs/{id}`, re-observes the in-memory body offline,
   and writes a categorical summary;
5. `DROP DATABASE ... WITH (FORCE)` and a leak check, always, except that
   `--retain-database-on-pass` keeps a PASS database for local browsing; and
6. one terminal outcome appended to the reservation.

Request rules: exactly one `GET
https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true`; no
retry (`max_attempts=1`), no redirect, no proxy environment; the only header
override is `Accept-Encoding: identity`; a non-identity encoding, an
oversized body (5,000,000 bytes), more than 500 records, a different
request, and any second send are refused. The one-send latch is shared by
every transport the provider ever creates. The body is held in memory only
and never written to a file; complete records are persisted only to the
disposable database's `raw_job_ingestions` (ADR 0020 §5).

Every printed line and summary field is categorical: no title, URL path,
description, content, record field, or exception text.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import html
import json
import os
import re
import secrets
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.db.models import (  # noqa: E402
    CollectionRun,
    CollectionRunProviderAttempt,
    IdentityConflict,
    Job,
    JobOccurrence,
    RawJobIngestion,
)
from app.ingestion import pipeline  # noqa: E402
from app.ingestion.clock import Clock, SystemClock  # noqa: E402
from app.ingestion.normalized_fields import build_normalization_context  # noqa: E402
from app.main import create_app  # noqa: E402
from app.providers.greenhouse import (  # noqa: E402
    GreenhouseBoard,
    GreenhouseClientSettings,
    GreenhouseJobBoardProvider,
    _is_json_media_type,
)
from app.schemas.job_read import JobDetail, JobListItem, OccurrenceOut  # noqa: E402
from app.schemas.provider import SourceQuery  # noqa: E402
from app.services.job_read import job_reader, open_read_only_reader  # noqa: E402
from scripts import run_greenhouse_s2c_canary as s2c  # noqa: E402
from scripts.db_safety import (  # noqa: E402
    assert_is_disposable_test_database,
    assert_safe_for_local_destructive_lifecycle,
    redact_database_url,
)

# ---------------------------------------------------------------------------
# Contract constants. The request constants are S2c's, by reference.
# ---------------------------------------------------------------------------

BOARD_TOKEN: Final = s2c.BOARD_TOKEN
BOARD_COMPANY: Final = s2c.BOARD_COMPANY
CONTENT_MODE: Final = s2c.CONTENT_MODE
REQUEST_PATH: Final = s2c.REQUEST_PATH
ACCEPT_ENCODING: Final = s2c.ACCEPT_ENCODING
MAX_RESPONSE_BYTES: Final = s2c.MAX_RESPONSE_BYTES
MAX_SOURCE_RECORDS: Final = s2c.MAX_SOURCE_RECORDS
SOURCE: Final = "greenhouse"
LIVE_ENV_VAR: Final = "JOBGOBLIN_S5_LIVE_INGESTION"
LIVE_ENV_VALUE: Final = "authorized-once"
REHEARSAL_ENV_VALUE: Final = "rehearsal"
MODE_LIVE: Final = "live"
MODE_REHEARSAL: Final = "rehearsal"
REHEARSAL_RECORD_COUNT: Final = 3
WORKER_DEADLINE_SECONDS: Final = 120.0
ALEMBIC_TIMEOUT_SECONDS: Final = 120
ADMIN_CONNECT_TIMEOUT_SECONDS: Final = 10
ADMIN_COMMAND_TIMEOUT_SECONDS: Final = 30
DATABASE_NAME_PREFIX: Final = "jobgoblin_test_s5_"
_DATABASE_NAME_RE: Final = re.compile(r"jobgoblin_test_s5_[0-9a-f]{16}")
_MAINTENANCE_DATABASE: Final = "postgres"
SUMMARY_VERSION: Final = 1
API_PAGE_LIMIT: Final = 100
API_MAX_PAGES: Final = 20

S5_SETTINGS: Final = GreenhouseClientSettings(max_attempts=1, max_response_bytes=MAX_RESPONSE_BYTES)

Verdict = s2c.Verdict

# The exact response keys ADR 0019 allows; anything else is a contract breach.
LIST_KEYS: Final = frozenset(JobListItem.model_fields)
DETAIL_KEYS: Final = frozenset(JobDetail.model_fields)
OCCURRENCE_KEYS: Final = frozenset(OccurrenceOut.model_fields)


class S5Refusal(s2c.CanaryRefusal):
    """A categorical S5 refusal. Not an `httpx` exception, so a guard refusal
    raised inside the provider's transport is never degraded by the adapter
    into a graceful per-source failure: it propagates, and `pipeline.run`
    marks the run `failed`."""


@dataclass(frozen=True)
class AttemptPaths:
    directory: Path

    @property
    def reservation(self) -> Path:
        return self.directory / "attempt.jsonl"

    @property
    def launch(self) -> Path:
        return self.directory / "launch.json"

    @property
    def claim(self) -> Path:
        return self.directory / "claim.json"

    @property
    def summary(self) -> Path:
        return self.directory / "summary.json"


LIVE_PATHS: Final = AttemptPaths(REPO_ROOT / ".claude" / "runtime" / "phase4-s5-live")
REHEARSAL_ROOT: Final = REPO_ROOT / ".claude" / "runtime" / "phase4-s5-rehearsals"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Request guard.
# ---------------------------------------------------------------------------


@dataclass
class Capture:
    """What the guard observed. `body` stays in memory only."""

    request_sent: bool = False
    observed_user_agent: str | None = None
    status: int | None = None
    media_type_json: bool | None = None
    complete: bool = False
    sha256: str | None = None
    byte_count: int | None = None
    source_record_count: int | None = None
    source_meta_total: int | None = None
    source_record_ids: list[str] = field(default_factory=list)
    body: bytes | None = None


@dataclass
class SendLatch:
    """Process-wide: one latch is shared by every transport the live provider
    creates, so a second `discover()` (or a retry) can never send again."""

    sent: bool = False


def check_request_shape(request: httpx.Request, *, path: str = REQUEST_PATH) -> None:
    """S2c's request-shape rule, for the given board path. The live path is
    always S2c's `REQUEST_PATH`; tests pass their own board's path."""
    url = request.url
    if (
        request.method != "GET"
        or url.scheme != s2c.REQUEST_SCHEME
        or url.host != s2c.REQUEST_HOST
        or url.port is not None
        or url.userinfo != b""
        or url.fragment != ""
        or url.raw_path != f"{path}?{s2c.REQUEST_QUERY}".encode("ascii")
    ):
        raise S5Refusal("request_shape_refused")


class GuardTransport(httpx.AsyncBaseTransport):
    """Refuses every request but the one permitted GET and any second send,
    sets `Accept-Encoding: identity`, refuses a non-identity encoding,
    reads a bounded successful body into memory, enforces the record cap
    before adapter conversion, and hands the identical bytes to the
    unchanged adapter. Writes no file."""

    def __init__(
        self,
        inner: httpx.AsyncBaseTransport,
        latch: SendLatch,
        capture: Capture,
        *,
        path: str = REQUEST_PATH,
    ) -> None:
        self._inner = inner
        self._latch = latch
        self._capture = capture
        self._path = path

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._latch.sent:
            raise S5Refusal("second_request_refused")
        check_request_shape(request, path=self._path)
        request.headers["Accept-Encoding"] = ACCEPT_ENCODING
        self._latch.sent = True
        self._capture.request_sent = True
        self._capture.observed_user_agent = request.headers.get("user-agent")
        response = await self._inner.handle_async_request(request)
        self._capture.status = response.status_code
        if response.status_code != 200:
            return response  # never drained here; the adapter rejects it
        self._capture.media_type_json = _is_json_media_type(response.headers.get("content-type"))
        if not self._capture.media_type_json:
            return response  # never drained here; the adapter rejects it
        try:
            encoding = response.headers.get("content-encoding")
            if encoding is not None and encoding.strip(" \t").lower() != ACCEPT_ENCODING:
                raise S5Refusal("unexpected_content_encoding")
            body = await self._read_bounded(response)
        finally:
            await response.aclose()
        self._record(body)
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            stream=httpx.ByteStream(body),
            request=request,
            extensions=response.extensions,
        )

    async def _read_bounded(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_raw():
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise S5Refusal("response_cap_exceeded")
            chunks.append(chunk)
        return b"".join(chunks)

    def _record(self, body: bytes) -> None:
        capture = self._capture
        capture.complete = True
        capture.body = body
        capture.byte_count = len(body)
        capture.sha256 = hashlib.sha256(body).hexdigest()
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return  # the adapter reports invalid_json
        if not isinstance(envelope, dict) or not isinstance(envelope.get("jobs"), list):
            return  # the adapter reports envelope
        records = envelope["jobs"]
        capture.source_record_count = len(records)
        meta = envelope.get("meta")
        if isinstance(meta, dict) and s2c._strict_int(meta.get("total")):
            capture.source_meta_total = meta["total"]
        if capture.source_record_count > MAX_SOURCE_RECORDS:
            raise S5Refusal("record_cap_exceeded")
        capture.source_record_ids = [
            str(record["id"])
            for record in records
            if isinstance(record, dict) and s2c._strict_int(record.get("id"))
        ]

    async def aclose(self) -> None:
        await self._inner.aclose()


def guarded_factory(
    inner_factory: Callable[[], httpx.AsyncBaseTransport],
    latch: SendLatch,
    capture: Capture,
    *,
    path: str = REQUEST_PATH,
) -> Callable[[], httpx.AsyncBaseTransport]:
    def factory() -> httpx.AsyncBaseTransport:
        return GuardTransport(inner_factory(), latch, capture, path=path)

    return factory


def live_board() -> GreenhouseBoard:
    return GreenhouseBoard(BOARD_TOKEN, BOARD_COMPANY, content_mode=CONTENT_MODE)


# ---------------------------------------------------------------------------
# Redaction for the representative API output.
# ---------------------------------------------------------------------------

_REDACTED_TEXT_KEYS: Final = frozenset({"title", "location_raw", "description_clean"})
_URL_KEYS: Final = frozenset({"canonical_url", "source_url", "apply_url"})


def _redact_url(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    parts = urlsplit(value)
    if not parts.scheme or not parts.hostname:
        return f"<redacted:{len(value)} chars>"
    return f"{parts.scheme}://{parts.hostname}/<redacted>"


def redact_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """A privacy-safe copy of one API item: titles, locations, descriptions,
    company names, and URL paths are replaced; locally generated IDs,
    timestamps, booleans, provider/source, and taxonomy values are kept."""
    redacted: dict[str, Any] = {}
    for key, value in item.items():
        if key in _REDACTED_TEXT_KEYS:
            redacted[key] = f"<redacted:{len(value)} chars>" if isinstance(value, str) else value
        elif key in _URL_KEYS:
            redacted[key] = _redact_url(value)
        elif key == "company":
            redacted[key] = None if value is None else {"id": value.get("id"), "name": "<redacted>"}
        elif key == "occurrences":
            redacted[key] = [redact_item(occurrence) for occurrence in value]
        else:
            redacted[key] = value
    return redacted


# ---------------------------------------------------------------------------
# Persisted-state inspection (categorical counts only).
# ---------------------------------------------------------------------------


async def database_row_counts(engine: AsyncEngine) -> dict[str, int]:
    async with AsyncSession(bind=engine) as session:
        counts = {}
        for name, model in (
            ("collection_runs", CollectionRun),
            ("raw_job_ingestions", RawJobIngestion),
            ("jobs", Job),
            ("job_occurrences", JobOccurrence),
            ("identity_conflicts", IdentityConflict),
        ):
            counts[name] = (
                await session.execute(select(func.count()).select_from(model))
            ).scalar_one()
        return counts


async def database_now(engine: AsyncEngine) -> datetime:
    """The database server's clock, the same clock as `created_at`."""
    async with engine.connect() as conn:
        value: datetime = (await conn.execute(text("SELECT clock_timestamp()"))).scalar_one()
        return value


_ADAPTER_DETAIL_RE: Final = re.compile(r"failure=([a-z_]+) status=([0-9]+|none)")


async def run_state(engine: AsyncEngine, run_id: uuid.UUID) -> dict[str, Any]:
    async with AsyncSession(bind=engine) as session:
        run = await session.get(CollectionRun, run_id)
        assert run is not None
        attempt = (
            await session.execute(
                select(CollectionRunProviderAttempt).where(
                    CollectionRunProviderAttempt.collection_run_id == run_id
                )
            )
        ).scalar_one()
        kind: str | None = None
        status: int | None = None
        match = _ADAPTER_DETAIL_RE.search(attempt.error_message or "")
        if match is not None:
            kind = match.group(1)
            status = None if match.group(2) == "none" else int(match.group(2))
        return {
            "status": run.status,
            "jobs_discovered": run.jobs_discovered,
            "jobs_inserted": run.jobs_inserted,
            "jobs_updated": run.jobs_updated,
            "failure_count": len(run.failures),
            "attempt_status": attempt.status,
            "attempt_error_category": attempt.error_category,
            "attempt_failure_kind": kind,
            "attempt_failure_status": status,
            "incomplete_results": attempt.incomplete_results,
            "rate_limited": attempt.rate_limited,
            "retry_count": attempt.retry_count,
        }


async def persisted_state(
    engine: AsyncEngine, board_token: str, record_ids: Sequence[str], since: datetime
) -> dict[str, Any]:
    """Counts scoped to this board's records, and to raw rows the database
    created at or after `since` (a database-server timestamp)."""
    async with AsyncSession(bind=engine) as session:
        raws = (
            (
                await session.execute(
                    select(RawJobIngestion).where(
                        RawJobIngestion.provider == SOURCE,
                        RawJobIngestion.source_identifier.in_(list(record_ids)),
                        RawJobIngestion.created_at >= since,
                    )
                )
            )
            .scalars()
            .all()
        )
        occurrences = (
            (
                await session.execute(
                    select(JobOccurrence).where(
                        JobOccurrence.provider == SOURCE,
                        JobOccurrence.source_tenant_id == board_token,
                        JobOccurrence.source_job_id.in_(list(record_ids)),
                    )
                )
            )
            .scalars()
            .all()
        )
        job_ids = sorted({occurrence.job_id for occurrence in occurrences}, key=str)
        jobs = (
            (await session.execute(select(Job).where(Job.id.in_(job_ids)))).scalars().all()
            if job_ids
            else []
        )
        raw_ids = [raw.id for raw in raws]
        conflicts = (
            (
                await session.execute(
                    select(func.count())
                    .select_from(IdentityConflict)
                    .where(IdentityConflict.incoming_raw_job_ingestion_id.in_(raw_ids))
                )
            ).scalar_one()
            if raw_ids
            else 0
        )
        statuses: dict[str, int] = {}
        for raw in raws:
            statuses[raw.processing_status] = statuses.get(raw.processing_status, 0) + 1
        return {
            "raw_rows": len(raws),
            "raw_status_counts": dict(sorted(statuses.items())),
            "raw_parser_versions": sorted({raw.parser_version or "none" for raw in raws}),
            "occurrences": len(occurrences),
            "jobs": len(jobs),
            "identity_conflicts": conflicts,
            "normalized_non_null": {
                "employment_type": sum(job.employment_type is not None for job in jobs),
                "seniority": sum(job.seniority is not None for job in jobs),
                "country": sum(job.country is not None for job in jobs),
            },
            "_job_ids": [str(job_id) for job_id in job_ids],
            "_last_seen": {str(job.id): job.last_seen_at.isoformat() for job in jobs},
        }


# ---------------------------------------------------------------------------
# API read-back through the real S4 routes.
# ---------------------------------------------------------------------------


async def api_check(engine: AsyncEngine, job_ids: Sequence[str], *, exact: bool) -> dict[str, Any]:
    """Reads every persisted job back through `GET /jobs` (all pages) and
    `GET /jobs/{id}` on a fresh `create_app()`, over ASGI (no socket). Only
    the reader's session binding is overridden. `exact` additionally
    requires the listing to contain nothing else (a fresh database)."""
    app = create_app()
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def reader() -> AsyncIterator[Any]:
        async with open_read_only_reader(sessionmaker) as job_read:
            yield job_read

    app.dependency_overrides[job_reader] = reader
    result: dict[str, Any] = {
        "list_ok": False,
        "list_pages": 0,
        "listed_all_persisted": False,
        "listed_only_persisted": None,
        "list_keys_exact": False,
        "details_ok": False,
        "detail_keys_exact": False,
        "detail_occurrences_greenhouse": False,
        "representative_list_item": None,
        "representative_detail": None,
    }
    wanted = set(job_ids)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        listed: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(API_MAX_PAGES):
            params: dict[str, Any] = {"limit": API_PAGE_LIMIT}
            if cursor is not None:
                params["cursor"] = cursor
            response = await client.get("/jobs", params=params)
            result["list_pages"] += 1
            if response.status_code != 200:
                return result
            page = response.json()
            listed.extend(page["items"])
            cursor = page["next_cursor"]
            if cursor is None:
                break
        else:
            return result
        result["list_ok"] = True
        listed_ids = {item["id"] for item in listed}
        result["listed_all_persisted"] = bool(wanted) and wanted <= listed_ids
        result["listed_only_persisted"] = listed_ids <= wanted if exact else None
        result["list_keys_exact"] = all(set(item) == LIST_KEYS for item in listed)
        details_ok = bool(wanted)
        keys_exact = bool(wanted)
        greenhouse = bool(wanted)
        first_detail: dict[str, Any] | None = None
        for job_id in sorted(wanted):
            response = await client.get(f"/jobs/{job_id}")
            if response.status_code != 200:
                details_ok = False
                continue
            detail = response.json()
            first_detail = first_detail or detail
            keys_exact = keys_exact and set(detail) == DETAIL_KEYS
            occurrences = detail["occurrences"]
            keys_exact = keys_exact and all(set(o) == OCCURRENCE_KEYS for o in occurrences)
            greenhouse = (
                greenhouse
                and bool(occurrences)
                and all(o["provider"] == SOURCE and o["source"] == SOURCE for o in occurrences)
            )
        result["details_ok"] = details_ok
        result["detail_keys_exact"] = keys_exact
        result["detail_occurrences_greenhouse"] = greenhouse
        first_listed = next((item for item in listed if item["id"] in wanted), None)
        if first_listed is not None:
            result["representative_list_item"] = redact_item(first_listed)
            response = await client.get(f"/jobs/{first_listed['id']}")
            if response.status_code == 200:
                result["representative_detail"] = redact_item(response.json())
    return result


def api_passed(api: Mapping[str, Any], *, exact: bool) -> str | None:
    """The first failed API check, or `None`."""
    for key in (
        "list_ok",
        "listed_all_persisted",
        "list_keys_exact",
        "details_ok",
        "detail_keys_exact",
        "detail_occurrences_greenhouse",
    ):
        if api.get(key) is not True:
            return f"api_{key}"
    if exact and api.get("listed_only_persisted") is not True:
        return "api_listed_only_persisted"
    return None


# ---------------------------------------------------------------------------
# The worker pipeline (testable with an injected inner transport).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestionPlan:
    board: GreenhouseBoard
    inner_transport_factory: Callable[[], httpx.AsyncBaseTransport]
    expected_parser_version: str
    request_path: str = REQUEST_PATH
    fresh_database: bool = True
    reobserve: bool = True
    clock: Clock = field(default_factory=SystemClock)


def _stop(summary: dict[str, Any], verdict: Any, reason: str) -> dict[str, Any]:
    summary["verdict"] = verdict.value
    summary["reason"] = reason
    return summary


def _request_summary(capture: Capture) -> dict[str, Any]:
    return {
        "sent": capture.request_sent,
        "observed_user_agent": capture.observed_user_agent,
        "status": capture.status,
        "media_type_json": capture.media_type_json,
        "complete": capture.complete,
        "byte_count": capture.byte_count,
        "sha256": capture.sha256,
        "source_record_count": capture.source_record_count,
        "source_meta_total": capture.source_meta_total,
    }


def _public(state: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if not key.startswith("_")}


def _completed_checks(
    run: Mapping[str, Any],
    persisted: Mapping[str, Any],
    capture: Capture,
    parser_version: str,
) -> str | None:
    """The first failed invariant of a `completed` run, or `None`."""
    n = capture.source_record_count
    if n is None or n < 1:
        return "no_source_records"
    if capture.source_meta_total is not None and capture.source_meta_total != n:
        return "meta_total_mismatch"
    if len(set(capture.source_record_ids)) != n:
        return "source_record_ids_not_unique"
    if run["jobs_discovered"] != n:
        return "jobs_discovered_mismatch"
    if run["attempt_status"] != "completed" or run["incomplete_results"]:
        return "attempt_not_completed"
    if run["jobs_inserted"] + run["jobs_updated"] != n:
        return "insert_update_count_mismatch"
    if persisted["raw_rows"] != n:
        return "raw_row_count_mismatch"
    if persisted["raw_status_counts"] != {"normalized": n}:
        return "raw_rows_not_all_normalized"
    if persisted["raw_parser_versions"] != [parser_version]:
        return "parser_version_mismatch"
    if persisted["identity_conflicts"] != 0:
        return "identity_conflicts"
    if persisted["occurrences"] != n:
        return "occurrence_count_mismatch"
    if persisted["jobs"] != run["jobs_inserted"]:
        return "job_count_mismatch"
    return None


async def reobserve(
    engine: AsyncEngine,
    plan: IngestionPlan,
    body: bytes,
    record_ids: Sequence[str],
    before: Mapping[str, Any],
    since: datetime,
) -> tuple[dict[str, Any], str | None]:
    """A second `pipeline.run` over the same in-memory body through a
    separate provider whose only transport is a `MockTransport`: zero
    network. Expects no new Job or Occurrence, every posting updated, the
    raw rows doubled and all normalized, and `last_seen_at` advanced."""

    def handler(request: httpx.Request) -> httpx.Response:
        check_request_shape(request, path=plan.request_path)
        return httpx.Response(200, content=body, headers={"content-type": "application/json"})

    provider = GreenhouseJobBoardProvider(
        [plan.board],
        settings=S5_SETTINGS,
        transport_factory=lambda: httpx.MockTransport(handler),
    )
    context = build_normalization_context(provider.board_content_modes)
    observed_at = plan.clock.now()
    run_id = await pipeline.run(
        engine,
        provider,
        SourceQuery(sources=[SOURCE]),
        observed_at=observed_at,
        clock=plan.clock,
        normalization=context,
    )
    run = await run_state(engine, run_id)
    after = await persisted_state(engine, plan.board.board_token, record_ids, since)
    n = len(record_ids)
    summary: dict[str, Any] = {"run": run, "persisted": _public(after)}
    advanced = bool(before["_last_seen"]) and all(
        job_id in after["_last_seen"]
        and datetime.fromisoformat(after["_last_seen"][job_id]) > datetime.fromisoformat(stamp)
        for job_id, stamp in before["_last_seen"].items()
    )
    summary["last_seen_advanced"] = advanced
    if context.parser_version != plan.expected_parser_version:
        return summary, "reobservation_parser_version"
    if run["status"] != "completed":
        return summary, "reobservation_run_not_completed"
    if run["jobs_inserted"] != 0 or run["jobs_updated"] != n:
        return summary, "reobservation_counts"
    if after["jobs"] != before["jobs"] or after["occurrences"] != before["occurrences"]:
        return summary, "reobservation_created_rows"
    if after["raw_rows"] != 2 * n or after["raw_status_counts"] != {"normalized": 2 * n}:
        return summary, "reobservation_raw_rows"
    if after["raw_parser_versions"] != [plan.expected_parser_version]:
        return summary, "reobservation_parser_version"
    if not advanced:
        return summary, "reobservation_last_seen"
    return summary, None


async def run_worker_pipeline(engine: AsyncEngine, plan: IngestionPlan) -> dict[str, Any]:
    """Fresh-database check, the one guarded request through `pipeline.run`,
    persisted-state checks, API read-back, and offline re-observation.
    Returns the categorical summary with its verdict. Never prints."""
    capture = Capture()
    latch = SendLatch()
    summary: dict[str, Any] = {
        "summary_version": SUMMARY_VERSION,
        "verdict": None,
        "reason": None,
        "board_token": plan.board.board_token,
        "request": _request_summary(capture),
        "parser_version": None,
        "run": None,
        "persisted": None,
        "api": None,
        "reobservation": None,
    }
    if plan.fresh_database:
        counts = await database_row_counts(engine)
        summary["database_before"] = counts
        if any(counts.values()):
            return _stop(summary, Verdict.FAIL_CLOSED, "database_not_fresh")
    provider = GreenhouseJobBoardProvider(
        [plan.board],
        settings=S5_SETTINGS,
        transport_factory=guarded_factory(
            plan.inner_transport_factory, latch, capture, path=plan.request_path
        ),
    )
    context = build_normalization_context(provider.board_content_modes)
    summary["parser_version"] = context.parser_version
    if context.parser_version != plan.expected_parser_version:
        return _stop(summary, Verdict.FAIL_CLOSED, "parser_version_mismatch_before_request")

    since = await database_now(engine)
    started = plan.clock.now()
    run_id: uuid.UUID | None = None
    failure: str | None = None
    try:
        run_id = await pipeline.run(
            engine,
            provider,
            SourceQuery(sources=[SOURCE]),
            observed_at=started,
            clock=plan.clock,
            normalization=context,
        )
    except s2c.CanaryRefusal as refusal:
        failure = f"refusal:{refusal.kind}"
    except Exception as exc:  # categorical: the class name only
        failure = f"pipeline_exception:{type(exc).__name__}"
    summary["request"] = _request_summary(capture)

    record_ids = capture.source_record_ids
    persisted = await persisted_state(engine, plan.board.board_token, record_ids, since)
    summary["persisted"] = _public(persisted)
    if failure is not None:
        summary["database_after_failure"] = await database_row_counts(engine)
        return _stop(summary, Verdict.FAIL_CLOSED, failure)
    assert run_id is not None
    run = await run_state(engine, run_id)
    summary["run"] = run
    if run["status"] != "completed":
        kind = run["attempt_failure_kind"]
        if run["attempt_status"] == "failed" and kind is not None:
            verdict = s2c.classify_adapter_failure(kind, run["attempt_failure_status"])
            return _stop(summary, verdict, f"adapter:{kind}")
        if run["attempt_status"] == "partial":
            return _stop(summary, Verdict.INCONCLUSIVE, "attempt_partial")
        return _stop(summary, Verdict.FAIL_CLOSED, f"run_{run['status']}")
    problem = _completed_checks(run, persisted, capture, context.parser_version)
    if problem is not None:
        return _stop(summary, Verdict.FAIL_CLOSED, problem)

    api = await api_check(engine, persisted["_job_ids"], exact=plan.fresh_database)
    summary["api"] = api
    problem = api_passed(api, exact=plan.fresh_database)
    if problem is not None:
        return _stop(summary, Verdict.FAIL_CLOSED, problem)

    if plan.reobserve:
        assert capture.body is not None
        reobservation, problem = await reobserve(
            engine, plan, capture.body, record_ids, persisted, since
        )
        summary["reobservation"] = reobservation
        if problem is not None:
            return _stop(summary, Verdict.FAIL_CLOSED, problem)
    return _stop(summary, Verdict.PASS, "all_checks_passed")


def rehearsal_envelope() -> bytes:
    """A SYNTHETIC `discord`-shaped envelope for the offline rehearsal. It is
    built here, never captured, and served only by a `MockTransport`."""
    records = []
    for index in range(1, REHEARSAL_RECORD_COUNT + 1):
        job_id = 900_000_000 + index
        text_ = f"SYNTHETIC S5 rehearsal record {index}. This is a full-time position."
        records.append(
            {
                "id": job_id,
                "title": f"SYNTHETIC Rehearsal Engineer {index}",
                "absolute_url": f"https://job-boards.greenhouse.io/{BOARD_TOKEN}/jobs/{job_id}",
                "location": {"name": "Remote, Canada"},
                "content": html.escape(
                    "<div>" + html.escape(text_, quote=False) + "</div>", quote=False
                ),
            }
        )
    envelope = {"jobs": records, "meta": {"total": len(records)}}
    return json.dumps(envelope).encode("utf-8")


def rehearsal_transport() -> httpx.AsyncBaseTransport:
    """The rehearsal's only inner transport: no network."""
    body = rehearsal_envelope()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=_MemoryStream(body),
            headers={"content-type": "application/json; charset=utf-8"},
        )

    return httpx.MockTransport(handler)


class _MemoryStream(httpx.AsyncByteStream):
    """An unread, streamed in-memory body, as a real transport returns it."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self._body), 65536):
            yield self._body[start : start + 65536]


# ---------------------------------------------------------------------------
# Disposable database lifecycle (parent process only).
# ---------------------------------------------------------------------------


def generate_database_name() -> str:
    return DATABASE_NAME_PREFIX + secrets.token_hex(8)


def quote_database_name(name: str) -> str:
    if not _DATABASE_NAME_RE.fullmatch(name):
        raise S5Refusal("database_name_invalid")
    return f'"{name}"'


def database_url(development_url: str, name: str) -> str:
    """Same host, port, and credentials as `DATABASE_URL`; only the name
    differs. Never printed (see `redact_database_url`)."""
    return make_url(development_url).set(database=name).render_as_string(hide_password=False)


def assert_database_target(name: str, development_url: str, *, app_env: str) -> str:
    """Both database-safety guards on the generated name. Returns its URL."""
    quote_database_name(name)
    url = database_url(development_url, name)
    try:
        assert_is_disposable_test_database(url, development_url)
        assert_safe_for_local_destructive_lifecycle(url, development_url, app_env=app_env)
    except RuntimeError:
        raise S5Refusal("database_target_refused") from None
    return url


def _admin_engine(development_url: str) -> AsyncEngine:
    return create_async_engine(
        database_url(development_url, _MAINTENANCE_DATABASE),
        isolation_level="AUTOCOMMIT",
        connect_args={
            "timeout": ADMIN_CONNECT_TIMEOUT_SECONDS,
            "command_timeout": ADMIN_COMMAND_TIMEOUT_SECONDS,
        },
    )


async def _admin(development_url: str, statement: str, **params: Any) -> Any:
    engine = _admin_engine(development_url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(statement).bindparams(**params))).scalar_one_or_none()
    finally:
        await engine.dispose()


async def admin_reachable(development_url: str) -> bool:
    try:
        return bool(await _admin(development_url, "SELECT 1") == 1)
    except Exception:
        return False


async def create_database(development_url: str, name: str) -> None:
    await _admin(development_url, f"CREATE DATABASE {quote_database_name(name)}")


async def drop_database(development_url: str, name: str) -> None:
    await _admin(
        development_url, f"DROP DATABASE IF EXISTS {quote_database_name(name)} WITH (FORCE)"
    )


async def database_exists(development_url: str, name: str) -> bool:
    quote_database_name(name)
    found = await _admin(
        development_url, "SELECT 1 FROM pg_database WHERE datname = :name", name=name
    )
    return bool(found == 1)


def migrate_database(url: str) -> bool:
    """`alembic upgrade head` in a subprocess whose environment alone points
    `DATABASE_URL` at the disposable database. Output is discarded."""
    env = dict(os.environ)
    env["DATABASE_URL"] = url
    try:
        completed = subprocess.run(  # fixed argv, no shell
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(BACKEND_DIR),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=ALEMBIC_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False
    return completed.returncode == 0


# ---------------------------------------------------------------------------
# Gates, reservation, and supervision.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiveRequest:
    board: str
    expected_sha: str
    expected_parser_version: str
    authorization_file: Path
    authorization_sha256: str
    retain_database_on_pass: bool = False


def request_fingerprint() -> str:
    return s2c.request_fingerprint()


def live_parser_version() -> str:
    """The parser version the live provider's context will carry, computed
    offline from the same board configuration."""
    provider = GreenhouseJobBoardProvider([live_board()], settings=S5_SETTINGS)
    return build_normalization_context(provider.board_content_modes).parser_version


def live_preflight(
    request: LiveRequest,
    *,
    env: Mapping[str, str],
    paths: AttemptPaths,
    head_sha: Callable[[], str],
    tree_is_clean: Callable[[], bool],
    database_name: str,
    development_url: str,
    app_env: str,
) -> dict[str, Any]:
    """Every gate element, before any reservation, database, or transport.
    Returns the reservation record; raises `S5Refusal` otherwise."""
    if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE:
        raise S5Refusal("gate_disabled")
    if request.board != BOARD_TOKEN:
        raise S5Refusal("board_not_allowlisted")
    if not s2c._SHA_RE.fullmatch(request.expected_sha) or head_sha() != request.expected_sha:
        raise S5Refusal("sha_mismatch")
    if not tree_is_clean():
        raise S5Refusal("dirty_tree")
    if (
        not s2c._SHA256_RE.fullmatch(request.authorization_sha256)
        or not request.authorization_file.is_file()
        or s2c.file_sha256(request.authorization_file) != request.authorization_sha256
    ):
        raise S5Refusal("authorization_mismatch")
    if live_parser_version() != request.expected_parser_version:
        raise S5Refusal("parser_version_mismatch")
    if os.path.lexists(paths.directory):
        raise S5Refusal("attempt_already_reserved")
    assert_database_target(database_name, development_url, app_env=app_env)
    return {
        "event": "reserved",
        "outcome": "reserved",
        "mode": MODE_LIVE,
        "board_token": BOARD_TOKEN,
        "advisory_sha": request.expected_sha,
        "request_fingerprint": request_fingerprint(),
        "parser_version": request.expected_parser_version,
        "authorization_identity": request.authorization_file.name,
        "authorization_sha256": request.authorization_sha256,
        "database_name": database_name,
        "retain_database_on_pass": request.retain_database_on_pass,
        "reserved_at": _now_iso(),
    }


def reserve(paths: AttemptPaths, record: Mapping[str, Any]) -> Any:
    """Exclusively create the attempt directory, then the fsynced reservation.
    Either existing refuses; nothing is ever reset."""
    try:
        os.mkdir(paths.directory)
    except FileExistsError:
        raise S5Refusal("attempt_already_reserved") from None
    return s2c.create_reservation(paths.reservation, record)


def launch_capability(reservation_line: bytes, token: str) -> dict[str, Any]:
    record = json.loads(reservation_line.decode("utf-8"))
    if not isinstance(record, dict) or record.get("event") != "reserved":
        raise S5Refusal("reservation_invalid")
    capability = {
        key: record.get(key)
        for key in (
            "mode",
            "board_token",
            "advisory_sha",
            "request_fingerprint",
            "parser_version",
            "authorization_sha256",
            "database_name",
        )
    }
    capability["reservation_sha256"] = hashlib.sha256(reservation_line).hexdigest()
    capability["token_sha256"] = hashlib.sha256(token.encode("ascii")).hexdigest()
    return capability


def claim_worker(paths: AttemptPaths, token: str) -> dict[str, Any]:
    """Validate the supervisor's launch capability against the open
    reservation and claim the single worker slot, before any transport or
    database connection. Returns the capability."""
    if not isinstance(token, str) or not s2c._SHA256_RE.fullmatch(token):
        raise S5Refusal("worker_token_invalid")
    if not paths.reservation.is_file():
        raise S5Refusal("worker_state_missing")
    lines = paths.reservation.read_bytes().splitlines(keepends=True)
    if len(lines) != 1:
        raise S5Refusal("reservation_not_open")
    try:
        launch = json.loads(paths.launch.read_text(encoding="utf-8"))
        expected = launch_capability(lines[0], token)
    except (OSError, ValueError):
        raise S5Refusal("launch_capability_invalid") from None
    if (
        launch != expected
        or expected["board_token"] != BOARD_TOKEN
        or expected["request_fingerprint"] != request_fingerprint()
    ):
        raise S5Refusal("launch_capability_invalid")
    for path in (paths.claim, paths.summary):
        if os.path.lexists(path):
            raise S5Refusal("worker_already_claimed")
    claim = {"token_sha256": expected["token_sha256"], "claimed_at": _now_iso()}
    try:
        s2c.exclusive_write(paths.claim, json.dumps(claim, sort_keys=True).encode("utf-8"))
    except FileExistsError:
        raise S5Refusal("worker_already_claimed") from None
    return expected


async def _worker_async(capability: Mapping[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    url = assert_database_target(
        capability["database_name"], settings.database_url, app_env=settings.app_env
    )
    engine = create_async_engine(url)
    try:
        inner: Callable[[], httpx.AsyncBaseTransport] = (
            httpx.AsyncHTTPTransport if capability["mode"] == MODE_LIVE else rehearsal_transport
        )
        plan = IngestionPlan(
            board=live_board(),
            inner_transport_factory=inner,
            expected_parser_version=capability["parser_version"],
        )
        return await run_worker_pipeline(engine, plan)
    finally:
        await engine.dispose()


def worker_main(
    paths: AttemptPaths,
    *,
    env: Mapping[str, str],
    token: str,
    in_containment: Callable[[], bool] = s2c.current_process_kill_on_close,
) -> int:
    """The supervised worker. Prints nothing; writes only the summary. The
    environment gate must match the reserved mode: live only under
    `authorized-once` in the live attempt directory; the rehearsal only
    under `rehearsal`, and its inner transport is a `MockTransport`."""
    gate = env.get(LIVE_ENV_VAR)
    if gate not in (LIVE_ENV_VALUE, REHEARSAL_ENV_VALUE):
        return 3
    if not in_containment():
        return 3
    try:
        capability = claim_worker(paths, token)
    except s2c.CanaryRefusal:
        return 3
    live = capability.get("mode") == MODE_LIVE
    if live != (gate == LIVE_ENV_VALUE) or (live and paths != LIVE_PATHS):
        return 3
    if not live and capability.get("mode") != MODE_REHEARSAL:
        return 3
    try:
        summary = asyncio.run(_worker_async(capability))
    except Exception as exc:  # categorical: the class name only
        summary = {
            "summary_version": SUMMARY_VERSION,
            "verdict": Verdict.FAIL_CLOSED.value,
            "reason": f"worker_exception:{type(exc).__name__}",
        }
    s2c.exclusive_write(
        paths.summary, json.dumps(summary, indent=2, sort_keys=True).encode("utf-8")
    )
    return 0


def worker_entry(paths: AttemptPaths, stdin: Any) -> int:
    """`_worker` entry: one blocking read of the supervisor's token, which is
    released only after kernel containment is in place (S2c's rule)."""
    if stdin.isatty():
        return 3
    token = stdin.buffer.readline(128).decode("ascii", "replace").strip()
    return worker_main(paths, env=os.environ, token=token)


@dataclass
class LiveOutcome:
    outcome: str
    worker: str | None = None
    database_created: bool = False
    database_migrated: bool = False
    database_dropped: bool | None = None
    database_retained: bool = False
    summary: dict[str, Any] | None = None


def _outcome_from_worker(worker: Any, paths: AttemptPaths) -> tuple[str, dict[str, Any] | None]:
    if worker.kind == "containment_failed":
        return f"{Verdict.FAIL_CLOSED.value}:containment_assignment_failed", None
    if worker.kind == "termination_unconfirmed":
        return f"{Verdict.FAIL_CLOSED.value}:worker_termination_unconfirmed", None
    if worker.kind == "deadline_terminated":
        return f"{Verdict.FAIL_CLOSED.value}:outer_deadline", None
    if worker.returncode != 0 or not paths.summary.is_file():
        return f"{Verdict.FAIL_CLOSED.value}:worker_failed", None
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    return f"{summary['verdict']}:{summary['reason']}", summary


def run_live(
    request: LiveRequest,
    *,
    env: Mapping[str, str],
    paths: AttemptPaths,
    head_sha: Callable[[], str],
    tree_is_clean: Callable[[], bool],
    worker_argv: Sequence[str],
    development_url: str,
    app_env: str,
    deadline_seconds: float = WORKER_DEADLINE_SECONDS,
    containment_factory: Callable[[], Any] = s2c.KillOnCloseJob,
    migrate: Callable[[str], bool] = migrate_database,
) -> LiveOutcome:
    """Preflight, containment, reservation, database create and migrate,
    supervised worker, database drop and leak check, terminal outcome."""
    name = generate_database_name()
    record = live_preflight(
        request,
        env=env,
        paths=paths,
        head_sha=head_sha,
        tree_is_clean=tree_is_clean,
        database_name=name,
        development_url=development_url,
        app_env=app_env,
    )
    return _attempt(
        record,
        name,
        env=env,
        paths=paths,
        worker_argv=worker_argv,
        development_url=development_url,
        app_env=app_env,
        deadline_seconds=deadline_seconds,
        containment_factory=containment_factory,
        migrate=migrate,
        keep=request.retain_database_on_pass,
    )


def run_rehearsal(
    *,
    paths: AttemptPaths,
    worker_argv: Sequence[str],
    development_url: str,
    app_env: str,
    deadline_seconds: float = WORKER_DEADLINE_SECONDS,
    containment_factory: Callable[[], Any] = s2c.KillOnCloseJob,
    migrate: Callable[[str], bool] = migrate_database,
) -> LiveOutcome:
    """The complete live machinery -- reservation, database create and
    migrate, the supervised worker under kill-on-close containment, the
    guard, `pipeline.run`, the API read-back, re-observation, drop and leak
    check -- with the worker's inner transport replaced by a `MockTransport`
    serving `rehearsal_envelope()`. No network. Never retains the database."""
    name = generate_database_name()
    assert_database_target(name, development_url, app_env=app_env)
    if os.path.lexists(paths.directory):
        raise S5Refusal("attempt_already_reserved")
    record = {
        "event": "reserved",
        "outcome": "reserved",
        "mode": MODE_REHEARSAL,
        "board_token": BOARD_TOKEN,
        "advisory_sha": None,
        "request_fingerprint": request_fingerprint(),
        "parser_version": live_parser_version(),
        "authorization_sha256": None,
        "database_name": name,
        "retain_database_on_pass": False,
        "reserved_at": _now_iso(),
    }
    env = dict(os.environ)
    env[LIVE_ENV_VAR] = REHEARSAL_ENV_VALUE
    return _attempt(
        record,
        name,
        env=env,
        paths=paths,
        worker_argv=worker_argv,
        development_url=development_url,
        app_env=app_env,
        deadline_seconds=deadline_seconds,
        containment_factory=containment_factory,
        migrate=migrate,
        keep=False,
    )


def _attempt(
    record: Mapping[str, Any],
    name: str,
    *,
    env: Mapping[str, str],
    paths: AttemptPaths,
    worker_argv: Sequence[str],
    development_url: str,
    app_env: str,
    deadline_seconds: float,
    containment_factory: Callable[[], Any],
    migrate: Callable[[str], bool],
    keep: bool,
) -> LiveOutcome:
    if not asyncio.run(admin_reachable(development_url)):
        raise S5Refusal("database_server_unreachable")
    containment = containment_factory()
    try:
        handle = reserve(paths, record)
        result = LiveOutcome(outcome=f"{Verdict.FAIL_CLOSED.value}:supervisor_exception")
        try:
            result = _create_and_supervise(
                name,
                containment,
                env=env,
                paths=paths,
                worker_argv=worker_argv,
                development_url=development_url,
                app_env=app_env,
                deadline_seconds=deadline_seconds,
                migrate=migrate,
            )
        finally:
            _cleanup(result, name, development_url, keep=keep)
            s2c.append_terminal_outcome(handle, result.outcome)
        return result
    finally:
        containment.close()


def _create_and_supervise(
    name: str,
    containment: Any,
    *,
    env: Mapping[str, str],
    paths: AttemptPaths,
    worker_argv: Sequence[str],
    development_url: str,
    app_env: str,
    deadline_seconds: float,
    migrate: Callable[[str], bool],
) -> LiveOutcome:
    url = assert_database_target(name, development_url, app_env=app_env)
    result = LiveOutcome(outcome=f"{Verdict.FAIL_CLOSED.value}:database_create_failed")
    try:
        asyncio.run(create_database(development_url, name))
    except Exception:
        return result
    result.database_created = True
    if not migrate(url):
        result.outcome = f"{Verdict.FAIL_CLOSED.value}:database_migrate_failed"
        return result
    result.database_migrated = True
    token = secrets.token_hex(32)
    reservation_line = paths.reservation.read_bytes().splitlines(keepends=True)[0]
    s2c.exclusive_write(
        paths.launch,
        json.dumps(launch_capability(reservation_line, token), sort_keys=True).encode("utf-8"),
    )
    try:
        worker = s2c.supervise_worker(
            worker_argv,
            deadline_seconds=deadline_seconds,
            env=env,
            stdin_payload=(token + "\n").encode("ascii"),
            containment=containment,
        )
    except s2c.SupervisionAborted as aborted:
        kind = "supervisor_interrupted" if aborted.confirmed else "worker_termination_unconfirmed"
        result.outcome = f"{Verdict.FAIL_CLOSED.value}:{kind}"
        return result
    result.worker = worker.kind
    result.outcome, result.summary = _outcome_from_worker(worker, paths)
    return result


def _cleanup(result: LiveOutcome, name: str, development_url: str, *, keep: bool) -> None:
    """Always drops the database, except a PASS with `keep`. A failed drop or
    leak check turns the outcome FAIL-CLOSED."""
    passed = result.outcome.startswith(f"{Verdict.PASS.value}:")
    if passed and keep:
        result.database_retained = True
        return
    try:
        asyncio.run(drop_database(development_url, name))
        result.database_dropped = not asyncio.run(database_exists(development_url, name))
    except Exception:
        result.database_dropped = False
    if not result.database_dropped:
        result.outcome = f"{Verdict.FAIL_CLOSED.value}:cleanup_failed"


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _git_head() -> str:
    return s2c.git_output(["rev-parse", "HEAD"]).strip()


def _git_clean() -> bool:
    return s2c.git_output(["status", "--porcelain"]).strip() == ""


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("parser-version", help="print the live board's parser version (offline)")
    live = sub.add_parser("live", help="the single authorized live ingestion")
    live.add_argument("--board", required=True)
    live.add_argument("--expected-sha", required=True)
    live.add_argument("--expected-parser-version", required=True)
    live.add_argument("--authorization-file", required=True, type=Path)
    live.add_argument("--authorization-sha256", required=True)
    live.add_argument("--retain-database-on-pass", action="store_true")
    rehearse = sub.add_parser(
        "rehearse", help="offline rehearsal of the live machinery (no network)"
    )
    rehearse.add_argument(
        "--confirm-create-and-drop-local-test-database", action="store_true", required=True
    )
    worker = sub.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--attempt-dir", type=Path, required=True)
    return parser.parse_args(argv)


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: Sequence[str] | None = None, *, paths: AttemptPaths = LIVE_PATHS) -> int:
    args = _parse_args(argv)
    if args.command == "parser-version":
        _print({"board_token": BOARD_TOKEN, "parser_version": live_parser_version()})
        return 0
    if args.command == "_worker":
        return worker_entry(AttemptPaths(args.attempt_dir.resolve()), sys.stdin)
    settings = get_settings()
    if args.command == "rehearse":
        rehearsal = AttemptPaths(
            REHEARSAL_ROOT / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
        )
        REHEARSAL_ROOT.mkdir(parents=True, exist_ok=True)
        try:
            result = run_rehearsal(
                paths=rehearsal,
                worker_argv=_worker_argv(rehearsal),
                development_url=settings.database_url,
                app_env=settings.app_env,
            )
        except s2c.CanaryRefusal as refusal:
            _print({"outcome": "REFUSED", "kind": refusal.kind})
            return 2
        _print(_payload(result, rehearsal, settings.database_url))
        return 0 if result.outcome.startswith(f"{Verdict.PASS.value}:") else 1
    request = LiveRequest(
        board=args.board,
        expected_sha=args.expected_sha,
        expected_parser_version=args.expected_parser_version,
        authorization_file=args.authorization_file,
        authorization_sha256=args.authorization_sha256,
        retain_database_on_pass=args.retain_database_on_pass,
    )
    try:
        result = run_live(
            request,
            env=os.environ,
            paths=paths,
            head_sha=_git_head,
            tree_is_clean=_git_clean,
            worker_argv=_worker_argv(paths),
            development_url=settings.database_url,
            app_env=settings.app_env,
        )
    except s2c.CanaryRefusal as refusal:
        _print({"outcome": "REFUSED", "kind": refusal.kind})
        return 2
    _print(_payload(result, paths, settings.database_url))
    return 0 if result.outcome.startswith(f"{Verdict.PASS.value}:") else 1


def _worker_argv(paths: AttemptPaths) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        "--attempt-dir",
        str(paths.directory),
    ]


def _payload(result: LiveOutcome, paths: AttemptPaths, development_url: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "outcome": result.outcome,
        "worker": result.worker,
        "database_created": result.database_created,
        "database_migrated": result.database_migrated,
        "database_dropped": result.database_dropped,
        "database_retained": result.database_retained,
        "summary_path": str(paths.summary.relative_to(REPO_ROOT))
        if paths.summary.is_file()
        else None,
    }
    if result.database_retained:
        url = database_url(development_url, _retained_name(paths))
        payload["retained_database"] = redact_database_url(url)
    return payload


def _retained_name(paths: AttemptPaths) -> str:
    record = json.loads(paths.reservation.read_bytes().splitlines()[0].decode("utf-8"))
    name = str(record["database_name"])
    quote_database_name(name)
    return name


if __name__ == "__main__":
    sys.exit(main())
