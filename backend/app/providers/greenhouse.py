"""Offline-tested `DiscoveryProvider` for Greenhouse's public Job Board API
(Phase 4 S1, Class H; `docs/DECISIONS/0013-direct-greenhouse-job-board-provider.md`).

Calls `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`
directly through `httpx` — never through `ats-scrapers` (ADR 0013) — and converts
each usable record straight into a `DiscoveredJob`. `httpx` and every
Greenhouse payload shape stay inside this module; nothing else in `app/` may
import `httpx`.

S1 boundaries (binding):

- Not wired into any registry, composition root, setting, or kill switch, so
  nothing at runtime can reach it yet. Live enablement is a later,
  separately authorized slice.
- No persistence, no normalization, no parser-input mapping: `description`
  and `compensation_text` are always `None` (HTML conversion is S2 work under
  ADR 0011's D2), and no salary field is read, composed, or inferred.
- `raw` is a deep copy of the whole parsed record — structurally identical to
  the source record, never an allowlisted subset (byte identity is impossible
  once JSON is parsed; see `app/ingestion/hashing.py`).
- No logger and no `print`. Every `ProviderError.detail`, warning, and raised
  message is a fixed categorical template whose only interpolated values are
  the validated board token and integers — never a response body, a record
  field, exception text, or a URL query.

`discover()` raises only for programmer errors (an unsupported
`SourceQuery.sources`); every anticipated connector failure is reported in
the returned `DiscoveryResult`, per `DiscoveryProvider`'s contract.
"""

from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import time
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.schemas.discovered_job import (
    DiscoveredJob,
    DiscoveryResult,
    ProviderError,
    ProviderErrorCategory,
    SourceRunStats,
)
from app.schemas.provider import (
    ProviderCapabilities,
    ProviderHealth,
    SourceCapabilities,
    SourceHealth,
    SourceQuery,
)

PROVIDER_NAME = "greenhouse"
SOURCE_NAME = "greenhouse"
GREENHOUSE_API_ORIGIN = "https://boards-api.greenhouse.io"

# Same covered-whitespace set as every model/natural-key trimming rule in
# `app/db/models/` and `app/ingestion/natural_key.py`.
_COVERED_WHITESPACE = " \t\n\r"

_BOARD_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")
_HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_RETRY_AFTER_RE = re.compile(r"[0-9]+")

# The only HTTP statuses retried in-adapter. HTTP 500 is deliberately absent.
_RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

_STATUS_CATEGORIES: dict[int, ProviderErrorCategory] = {
    401: ProviderErrorCategory.AUTH_ERROR,
    403: ProviderErrorCategory.BLOCKED,
    404: ProviderErrorCategory.NOT_FOUND,
    429: ProviderErrorCategory.RATE_LIMITED,
}

_ERROR_UNSUPPORTED_SOURCES = (
    "GreenhouseJobBoardProvider supports only sources=[] or sources=['greenhouse']"
)

_HEALTH_NOT_OBSERVED = "no discovery observed"
_HEALTH_SUCCEEDED = "discovery succeeded"
_HEALTH_PARTIAL = "partial discovery observed"
_HEALTH_FAILED = "discovery failed"


class GreenhouseConfigurationError(ValueError):
    """Invalid boards or settings — a wiring error, raised at construction.
    Messages are fixed strings."""


class UnsupportedSourceQueryError(ValueError):
    """`SourceQuery.sources` names anything other than `[]` or
    `["greenhouse"]` — a caller error under `DiscoveryProvider`'s contract."""


def _is_positive_finite(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _is_strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class GreenhouseClientSettings:
    """Per-request limits. Owned by the caller's composition root; S1 adds no
    application setting or environment variable.

    Conservative per-board bound (Sol A11):
    `max_attempts × (pool + connect + write + read + attempt_deadline)
    + (max_attempts − 1) × max(backoff_cap, max_retry_after)` — 225 seconds
    with these defaults. A conservative bound, not a tight timing guarantee.
    """

    connect_timeout: float = 5.0
    read_timeout: float = 10.0
    write_timeout: float = 5.0
    pool_timeout: float = 5.0
    attempt_deadline: float = 30.0
    max_response_bytes: int = 5_000_000
    max_attempts: int = 3
    backoff_base: float = 0.5
    backoff_cap: float = 4.0
    max_retry_after: float = 30.0

    def __post_init__(self) -> None:
        for value in (
            self.connect_timeout,
            self.read_timeout,
            self.write_timeout,
            self.pool_timeout,
            self.attempt_deadline,
            self.backoff_base,
            self.backoff_cap,
            self.max_retry_after,
        ):
            if not _is_positive_finite(value):
                raise GreenhouseConfigurationError("settings values must be finite and positive")
        if not _is_strict_int(self.max_response_bytes) or self.max_response_bytes < 1:
            raise GreenhouseConfigurationError("max_response_bytes must be a positive integer")
        if not _is_strict_int(self.max_attempts) or not 1 <= self.max_attempts <= 5:
            raise GreenhouseConfigurationError("max_attempts must be an integer from 1 to 5")
        if self.backoff_cap < self.backoff_base:
            raise GreenhouseConfigurationError("backoff_cap must be at least backoff_base")

    def timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
            pool=self.pool_timeout,
        )


@dataclass(frozen=True)
class GreenhouseBoard:
    """One configured board. `board_token` is a lowercase slug, so no
    tenant-case ambiguity can reach the natural key; `company` is the only
    source of `DiscoveredJob.company` (never the payload's `company_name`)."""

    board_token: str
    company: str

    def __post_init__(self) -> None:
        if not isinstance(self.board_token, str) or not _BOARD_TOKEN_RE.fullmatch(self.board_token):
            raise GreenhouseConfigurationError("board_token must match ^[a-z0-9][a-z0-9_-]{0,99}$")
        if not isinstance(self.company, str) or not self.company.strip(_COVERED_WHITESPACE):
            raise GreenhouseConfigurationError("company must be a non-blank string")


# ---------------------------------------------------------------------------
# Record validation (Sol A5–A7). Each helper returns `(ok, value)`: `ok=False`
# means the record is malformed and is skipped.
# ---------------------------------------------------------------------------


def _optional_text(value: Any) -> tuple[bool, str | None]:
    """Absent/`null`/covered-whitespace-only → absent; any other `str` is
    kept verbatim; a present value of another type is malformed."""
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, None
    if not value.strip(_COVERED_WHITESPACE):
        return True, None
    return True, value


def _optional_requisition_id(value: Any) -> tuple[bool, str | None]:
    if isinstance(value, bool):
        return False, None
    if isinstance(value, int):
        return True, str(value)
    return _optional_text(value)


def _optional_location(value: Any) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    if not isinstance(value, dict):
        return False, None
    return _optional_text(value.get("name"))


def _optional_timestamp(value: Any) -> tuple[bool, datetime | None]:
    """Absent/`null` → `None`. Anything else must be a string that
    `datetime.fromisoformat` parses with an explicit timezone."""
    if value is None:
        return True, None
    if not isinstance(value, str):
        return False, None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False, None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return False, None
    return True, parsed


def _is_usable_id(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, str) and bool(value.strip(_COVERED_WHITESPACE))


def _is_usable_hostname(hostname: str | None) -> bool:
    if not hostname or not hostname.isascii() or len(hostname) > 253:
        return False
    return all(_HOST_LABEL_RE.fullmatch(label) for label in hostname.split("."))


def _is_valid_https_url(value: Any) -> bool:
    """HTTPS, a usable hostname and valid port, no username/password, and no
    embedded covered whitespace (Sol A7)."""
    if not isinstance(value, str) or not value:
        return False
    if any(char in value for char in _COVERED_WHITESPACE):
        return False
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    if parts.scheme != "https":
        return False
    if parts.username is not None or parts.password is not None:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    return _is_usable_hostname(parts.hostname)


def _duplicate_identity(job_id: int | str) -> str:
    """Matches downstream natural-key trimming, so `1`, `"1"`, and `" 1 "`
    are one identity (Sol A6)."""
    return str(job_id).strip(" \t\n\r")


@dataclass(frozen=True)
class _ValidRecord:
    record: dict[str, Any]
    job_id: int | str
    absolute_url: str
    title: str | None
    location: str | None
    requisition_id: str | None
    posted_at: datetime | None


def _validate_record(record: Any) -> _ValidRecord | None:
    if not isinstance(record, dict):
        return None
    job_id = record.get("id")
    if not _is_usable_id(job_id):
        return None
    absolute_url = record.get("absolute_url")
    if not _is_valid_https_url(absolute_url):
        return None
    title_ok, title = _optional_text(record.get("title"))
    location_ok, location = _optional_location(record.get("location"))
    requisition_ok, requisition_id = _optional_requisition_id(record.get("requisition_id"))
    posted_ok, posted_at = _optional_timestamp(record.get("first_published"))
    if not (title_ok and location_ok and requisition_ok and posted_ok):
        return None
    assert isinstance(job_id, int | str)
    assert isinstance(absolute_url, str)
    return _ValidRecord(
        record=record,
        job_id=job_id,
        absolute_url=absolute_url,
        title=title,
        location=location,
        requisition_id=requisition_id,
        posted_at=posted_at,
    )


# ---------------------------------------------------------------------------
# Envelope and media type (Sol A8).
# ---------------------------------------------------------------------------


def _is_json_media_type(content_type: str | None) -> bool:
    """`application/json` or `application/<subtype>+json`, ignoring case and
    parameters — never a substring match such as `text/notjson`."""
    if content_type is None:
        return False
    media_type = content_type.split(";", 1)[0].strip(_COVERED_WHITESPACE).lower()
    if media_type == "application/json":
        return True
    kind, slash, subtype = media_type.partition("/")
    return (
        slash == "/"
        and kind == "application"
        and "/" not in subtype
        and subtype.endswith("+json")
        and len(subtype) > len("+json")
    )


def _reject_constant(_: str) -> Any:
    raise ValueError("non-finite JSON constant")


def _parse_finite_float(literal: str) -> float:
    value = float(literal)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def _completeness_problem(payload: dict[str, Any], record_count: int) -> str | None:
    """`None` when there is no completeness claim or it holds; otherwise the
    fixed warning suffix `malformed` or `mismatch`. Compared against the
    number of records returned, not the usable count."""
    if "meta" not in payload:
        return None
    meta = payload["meta"]
    if not isinstance(meta, dict):
        return "malformed"
    if "total" not in meta:
        return None
    total = meta["total"]
    if not _is_strict_int(total) or total < 0:
        return "malformed"
    if total != record_count:
        return "mismatch"
    return None


# ---------------------------------------------------------------------------
# Board outcomes (Sol A1).
# ---------------------------------------------------------------------------


class _Outcome(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"


@dataclass(frozen=True)
class _AttemptFailure:
    kind: str
    category: ProviderErrorCategory
    retryable: bool
    status: int | None = None
    retry_after: int | None = None


@dataclass
class _BoardResult:
    outcome: _Outcome
    jobs: list[DiscoveredJob]
    errors: list[ProviderError]
    warnings: list[str]
    completeness_failed: bool
    retries: int
    rate_limited: bool


def _failure_detail(board: GreenhouseBoard, kind: str, status: int | None, attempts: int) -> str:
    status_text = str(status) if status is not None else "none"
    return (
        f"greenhouse board={board.board_token} failure={kind} "
        f"status={status_text} attempts={attempts}"
    )


def _parse_retry_after(value: str | None) -> int | None:
    if value is None or not _RETRY_AFTER_RE.fullmatch(value):
        return None
    return int(value)


def _status_failure(status: int, retry_after: str | None) -> _AttemptFailure:
    category = _STATUS_CATEGORIES.get(status, ProviderErrorCategory.UPSTREAM_ERROR)
    kind = "redirect" if 300 <= status < 400 else "http_status"
    return _AttemptFailure(
        kind=kind,
        category=category,
        retryable=status in _RETRYABLE_STATUSES,
        status=status,
        retry_after=_parse_retry_after(retry_after),
    )


class GreenhouseJobBoardProvider:
    """`DiscoveryProvider` for one or more configured Greenhouse boards,
    reported as the single source `greenhouse`.

    `transport_factory` (Sol A9) supplies one fresh transport per
    `discover()` call that queries boards; `None` means a new
    `httpx.AsyncHTTPTransport()`. Exactly one client wraps it for that call,
    and both are closed on every exit. `sleep`, `monotonic`, and `now` are
    injectable so retries, deadlines, and timestamps are deterministic in
    tests without wall-clock waiting.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        boards: Sequence[GreenhouseBoard],
        *,
        settings: GreenhouseClientSettings | None = None,
        transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        board_list = list(boards)
        if not board_list:
            raise GreenhouseConfigurationError("at least one board is required")
        if not all(isinstance(board, GreenhouseBoard) for board in board_list):
            raise GreenhouseConfigurationError("boards must be GreenhouseBoard instances")
        tokens = [board.board_token for board in board_list]
        if len(tokens) != len(set(tokens)):
            raise GreenhouseConfigurationError("board tokens must be unique")
        resolved_settings = settings if settings is not None else GreenhouseClientSettings()
        if not isinstance(resolved_settings, GreenhouseClientSettings):
            raise GreenhouseConfigurationError("settings must be GreenhouseClientSettings")
        self._boards = tuple(board_list)
        self._settings = resolved_settings
        self._transport_factory = transport_factory
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now
        self._last_success_at: datetime | None = None
        self._last_failure_at: datetime | None = None
        self._consecutive_failures = 0
        self._health_detail = _HEALTH_NOT_OBSERVED
        self._healthy = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            sources={SOURCE_NAME: SourceCapabilities(source=SOURCE_NAME, max_concurrency=1)},
        )

    async def health(self) -> ProviderHealth:
        """No network call: reports what the most recent discovery observed
        (Sol A4). Provider health equals the single source's health."""
        return ProviderHealth(
            provider=self.name,
            healthy=self._healthy,
            sources=[
                SourceHealth(
                    source=SOURCE_NAME,
                    healthy=self._healthy,
                    last_success_at=self._last_success_at,
                    last_failure_at=self._last_failure_at,
                    consecutive_failures=self._consecutive_failures,
                    detail=self._health_detail,
                )
            ],
            last_checked_at=self._now(),
        )

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        if query.sources not in ([], [SOURCE_NAME]):
            raise UnsupportedSourceQueryError(_ERROR_UNSUPPORTED_SOURCES)
        started_at = self._now()
        if not query.sources:
            return DiscoveryResult(
                provider=self.name, started_at=started_at, completed_at=self._now()
            )

        start = self._monotonic()
        transport = (
            self._transport_factory()
            if self._transport_factory is not None
            else httpx.AsyncHTTPTransport()
        )
        board_results: list[_BoardResult] = []
        try:
            async with httpx.AsyncClient(
                transport=transport,
                timeout=self._settings.timeout(),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                for board in self._boards:
                    board_results.append(await self._discover_board(client, board))
        finally:
            await transport.aclose()

        return self._aggregate(board_results, started_at, start)

    def _aggregate(
        self, board_results: list[_BoardResult], started_at: datetime, start: float
    ) -> DiscoveryResult:
        usable = [result for result in board_results if result.outcome is not _Outcome.FAILURE]
        completed = bool(usable)
        degraded = any(
            result.outcome is not _Outcome.SUCCESS or result.completeness_failed
            for result in board_results
        )
        jobs = [job for result in board_results for job in result.jobs]
        stats = SourceRunStats(
            source=SOURCE_NAME,
            completed=completed,
            jobs_found=len(jobs) if completed else 0,
            incomplete_results=completed and degraded,
            duration_ms=int((self._monotonic() - start) * 1000),
            rate_limited=any(result.rate_limited for result in board_results),
            retry_count=sum(result.retries for result in board_results),
        )
        completed_at = self._now()
        self._record_health(completed=completed, degraded=degraded, observed_at=completed_at)
        return DiscoveryResult(
            provider=self.name,
            jobs=jobs if completed else [],
            source_stats=[stats],
            errors=[error for result in board_results for error in result.errors],
            warnings=[warning for result in board_results for warning in result.warnings],
            started_at=started_at,
            completed_at=completed_at,
        )

    def _record_health(self, *, completed: bool, degraded: bool, observed_at: datetime) -> None:
        if completed:
            self._healthy = True
            self._last_success_at = observed_at
            self._consecutive_failures = 0
            if degraded:
                self._last_failure_at = observed_at
                self._health_detail = _HEALTH_PARTIAL
            else:
                self._health_detail = _HEALTH_SUCCEEDED
        else:
            self._healthy = False
            self._last_failure_at = observed_at
            self._consecutive_failures += 1
            self._health_detail = _HEALTH_FAILED

    async def _discover_board(
        self, client: httpx.AsyncClient, board: GreenhouseBoard
    ) -> _BoardResult:
        attempts = 0
        retries = 0
        rate_limited = False
        while True:
            attempts += 1
            outcome = await self._attempt(client, board)
            if isinstance(outcome, bytes):
                return self._board_from_body(board, outcome, attempts, retries, rate_limited)
            if outcome.status == 429:
                rate_limited = True
            wait = self._retry_wait(outcome, attempts)
            if wait is None:
                error = ProviderError(
                    source=SOURCE_NAME,
                    category=outcome.category,
                    retryable=outcome.retryable,
                    detail=_failure_detail(board, outcome.kind, outcome.status, attempts),
                    occurred_at=self._now(),
                )
                return _BoardResult(
                    outcome=_Outcome.FAILURE,
                    jobs=[],
                    errors=[error],
                    warnings=[],
                    completeness_failed=False,
                    retries=retries,
                    rate_limited=rate_limited,
                )
            retries += 1
            await self._sleep(wait)

    def _retry_wait(self, failure: _AttemptFailure, attempts: int) -> float | None:
        """Seconds to wait before the next attempt, or `None` to stop."""
        if not failure.retryable:
            return None
        if attempts >= self._settings.max_attempts:
            return None
        if failure.retry_after is not None:
            if failure.retry_after > self._settings.max_retry_after:
                return None
            return float(failure.retry_after)
        return float(
            min(self._settings.backoff_base * 2 ** (attempts - 1), self._settings.backoff_cap)
        )

    def _deadline_exceeded(self, attempt_start: float) -> bool:
        return self._monotonic() - attempt_start > self._settings.attempt_deadline

    async def _attempt(
        self, client: httpx.AsyncClient, board: GreenhouseBoard
    ) -> bytes | _AttemptFailure:
        """One GET. Returns the complete body of an HTTP 200 JSON response,
        or a categorized failure. The body is streamed and never read past
        the size cap."""
        url = f"{GREENHOUSE_API_ORIGIN}/v1/boards/{board.board_token}/jobs"
        attempt_start = self._monotonic()
        try:
            async with client.stream("GET", url, params={"content": "true"}) as response:
                if response.status_code != 200:
                    return _status_failure(
                        response.status_code, response.headers.get("retry-after")
                    )
                if not _is_json_media_type(response.headers.get("content-type")):
                    return _AttemptFailure("media_type", ProviderErrorCategory.PARSE_ERROR, False)
                if self._deadline_exceeded(attempt_start):
                    return _AttemptFailure("deadline", ProviderErrorCategory.TIMEOUT, True)
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > self._settings.max_response_bytes:
                        return _AttemptFailure("oversize", ProviderErrorCategory.PARSE_ERROR, False)
                    chunks.append(chunk)
                    if self._deadline_exceeded(attempt_start):
                        return _AttemptFailure("deadline", ProviderErrorCategory.TIMEOUT, True)
                if self._deadline_exceeded(attempt_start):
                    return _AttemptFailure("deadline", ProviderErrorCategory.TIMEOUT, True)
                return b"".join(chunks)
        except httpx.TimeoutException:
            return _AttemptFailure("timeout", ProviderErrorCategory.TIMEOUT, True)
        except httpx.ConnectError:
            return _AttemptFailure("connect_error", ProviderErrorCategory.UPSTREAM_ERROR, True)
        except httpx.TransportError:
            return _AttemptFailure("transport_error", ProviderErrorCategory.UPSTREAM_ERROR, False)

    def _board_from_body(
        self,
        board: GreenhouseBoard,
        body: bytes,
        attempts: int,
        retries: int,
        rate_limited: bool,
    ) -> _BoardResult:
        def failed(kind: str) -> _BoardResult:
            error = ProviderError(
                source=SOURCE_NAME,
                category=ProviderErrorCategory.PARSE_ERROR,
                retryable=False,
                detail=_failure_detail(board, kind, 200, attempts),
                occurred_at=self._now(),
            )
            return _BoardResult(_Outcome.FAILURE, [], [error], [], False, retries, rate_limited)

        try:
            payload = json.loads(
                body.decode("utf-8"),
                parse_constant=_reject_constant,
                parse_float=_parse_finite_float,
            )
        except (ValueError, RecursionError):
            # `RecursionError`: pathologically nested JSON is malformed
            # input, never a programmer error to raise past this boundary.
            return failed("invalid_json")
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            return failed("envelope")
        records: list[Any] = payload["jobs"]

        valid = [checked for checked in map(_validate_record, records) if checked is not None]
        identities = Counter(_duplicate_identity(item.job_id) for item in valid)
        kept = [item for item in valid if identities[_duplicate_identity(item.job_id)] == 1]
        if records and not kept:
            return failed("no_usable_records")

        discovered_at = self._now()
        jobs = [self._to_discovered_job(board, item, discovered_at) for item in kept]
        skipped = len(records) - len(kept)
        problem = _completeness_problem(payload, len(records))
        errors: list[ProviderError] = []
        warnings: list[str] = []
        if skipped:
            errors.append(
                ProviderError(
                    source=SOURCE_NAME,
                    category=ProviderErrorCategory.PARSE_ERROR,
                    retryable=False,
                    detail=f"greenhouse board={board.board_token} skipped_records={skipped}",
                    occurred_at=discovered_at,
                )
            )
        if problem is not None:
            warnings.append(f"greenhouse board={board.board_token} completeness_evidence={problem}")
        partial = bool(kept) and (bool(skipped) or problem is not None)
        return _BoardResult(
            outcome=_Outcome.PARTIAL if partial else _Outcome.SUCCESS,
            jobs=jobs,
            errors=errors,
            warnings=warnings,
            completeness_failed=problem is not None,
            retries=retries,
            rate_limited=rate_limited,
        )

    def _to_discovered_job(
        self, board: GreenhouseBoard, item: _ValidRecord, discovered_at: datetime
    ) -> DiscoveredJob:
        return DiscoveredJob(
            provider=PROVIDER_NAME,
            source=SOURCE_NAME,
            source_tenant_id=board.board_token,
            source_job_id=str(item.job_id),
            requisition_id_raw=item.requisition_id,
            title=item.title,
            company=board.company,
            location=item.location,
            source_url=item.absolute_url,
            apply_url=None,
            canonical_url=item.absolute_url,
            description=None,
            compensation_text=None,
            posted_at=item.posted_at,
            discovered_at=discovered_at,
            raw=copy.deepcopy(item.record),
        )
