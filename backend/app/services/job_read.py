"""Read-only job queries for the local jobs API (Phase 4 S4;
`docs/DECISIONS/0019-local-read-only-jobs-api.md`).

This module owns every database interaction behind `GET /jobs` and
`GET /jobs/{job_id}`, plus session acquisition for them, so the route layer
(`app/api/`) never imports `app.db` or SQLAlchemy (ARCHITECTURE.md §5).

Read-only by construction:

- `open_read_only_reader` opens a session and always rolls it back; nothing here
  commits, flushes, adds, deletes, updates, or takes a row lock.
- The reader's first statement is `SET TRANSACTION READ ONLY`, so PostgreSQL
  itself rejects any write attempted in that transaction. It runs lazily, on the
  first query, so a database failure is raised inside the route's own error
  handling rather than during dependency setup.

Query validation is strict and non-reflective: every invalid input maps to a
fixed error whose message never contains the submitted value. Precedence: an
unknown or repeated parameter, the limit, `include_inactive`, and the filters
(`InvalidQueryError`) are checked before the cursor (`InvalidCursorError`).
"""

from __future__ import annotations

import base64
import binascii
import json
import unicodedata
import uuid
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.company import Company
from app.db.models.job import Job
from app.db.models.job_occurrence import JobOccurrence
from app.db.session import get_sessionmaker
from app.schemas.job_read import (
    CompanyRef,
    JobDetail,
    JobListItem,
    JobListPage,
    OccurrenceOut,
)

DEFAULT_LIMIT = 25
MAX_LIMIT = 100
SUBSTRING_FILTER_MAX_LENGTH = 200
EXACT_FILTER_MAX_LENGTH = 64
CURSOR_MAX_LENGTH = 256
JOB_ID_MAX_LENGTH = 64

_SUBSTRING_FILTERS = ("title", "location")
_EXACT_FILTERS = ("country", "employment_type", "seniority")
_ALLOWED_PARAMETERS = frozenset(
    {*_SUBSTRING_FILTERS, *_EXACT_FILTERS, "include_inactive", "limit", "cursor"}
)
_LIKE_ESCAPE = "\\"
_BASE64URL_ALPHABET = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


class InvalidQueryError(ValueError):
    """An invalid limit, filter, `include_inactive`, or unknown/repeated parameter."""


class InvalidCursorError(ValueError):
    """A malformed pagination cursor."""


@dataclass(frozen=True)
class CursorPosition:
    last_seen_at: datetime
    job_id: uuid.UUID


@dataclass(frozen=True)
class JobListQuery:
    title: str | None = None
    location: str | None = None
    country: str | None = None
    employment_type: str | None = None
    seniority: str | None = None
    include_inactive: bool = False
    limit: int = DEFAULT_LIMIT
    after: CursorPosition | None = None


def _clean_filter(raw: str, max_length: int) -> str:
    value = raw.strip()
    if not value or len(value) > max_length:
        raise InvalidQueryError
    if any(unicodedata.category(char) == "Cc" for char in value):
        raise InvalidQueryError
    return value


def _parse_limit(raw: str) -> int:
    if not (1 <= len(raw) <= 3) or not all("0" <= char <= "9" for char in raw):
        raise InvalidQueryError
    value = int(raw)
    if not 1 <= value <= MAX_LIMIT:
        raise InvalidQueryError
    return value


def parse_list_query(params: Iterable[tuple[str, str]]) -> JobListQuery:
    """Validates `GET /jobs` query parameters, given as (name, value) pairs."""
    values: dict[str, str] = {}
    for name, value in params:
        if name not in _ALLOWED_PARAMETERS or name in values:
            raise InvalidQueryError
        values[name] = value

    limit = _parse_limit(values["limit"]) if "limit" in values else DEFAULT_LIMIT
    include_inactive = False
    if "include_inactive" in values:
        if values["include_inactive"] not in ("true", "false"):
            raise InvalidQueryError
        include_inactive = values["include_inactive"] == "true"
    filters: dict[str, str] = {}
    for name in _SUBSTRING_FILTERS:
        if name in values:
            filters[name] = _clean_filter(values[name], SUBSTRING_FILTER_MAX_LENGTH)
    for name in _EXACT_FILTERS:
        if name in values:
            filters[name] = _clean_filter(values[name], EXACT_FILTER_MAX_LENGTH)
    after = decode_cursor(values["cursor"]) if "cursor" in values else None
    return JobListQuery(include_inactive=include_inactive, limit=limit, after=after, **filters)


def encode_cursor(position: CursorPosition) -> str:
    payload = json.dumps(
        {"i": str(position.job_id), "t": position.last_seen_at.isoformat()},
        sort_keys=True,
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii").rstrip("=")


def decode_cursor(raw: str) -> CursorPosition:
    if not (1 <= len(raw) <= CURSOR_MAX_LENGTH) or not set(raw) <= _BASE64URL_ALPHABET:
        raise InvalidCursorError
    try:
        decoded = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("ascii")
        payload = json.loads(decoded)
        if not isinstance(payload, dict) or set(payload) != {"i", "t"}:
            raise InvalidCursorError
        job_text, time_text = payload["i"], payload["t"]
        if not isinstance(job_text, str) or not isinstance(time_text, str):
            raise InvalidCursorError
        job_id = uuid.UUID(job_text)
        if str(job_id) != job_text:
            raise InvalidCursorError
        parsed = datetime.fromisoformat(time_text)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise InvalidCursorError
        # Normalizing to UTC also rejects instants outside Python's datetime
        # range (e.g. year 1 at +01:00), which would otherwise fail later when
        # bound as a timestamptz parameter.
        last_seen_at = parsed.astimezone(UTC)
    except (UnicodeDecodeError, binascii.Error, ValueError, TypeError, OverflowError) as exc:
        raise InvalidCursorError from exc
    return CursorPosition(last_seen_at=last_seen_at, job_id=job_id)


def parse_job_id(raw: str) -> uuid.UUID | None:
    """`None` for anything that is not a UUID (the route answers 404)."""
    if not (1 <= len(raw) <= JOB_ID_MAX_LENGTH):
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return None


def _escape_like(value: str) -> str:
    return value.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2).replace("%", "\\%").replace("_", "\\_")


def _active_expression() -> Any:
    return (
        exists()
        .where(JobOccurrence.job_id == Job.id, JobOccurrence.is_active.is_(True))
        .label("active")
    )


def _job_columns() -> Select[Any]:
    return select(Job, Company.id, Company.name, _active_expression()).outerjoin(
        Company, Company.id == Job.company_id
    )


def _list_item(job: Job, company_id: Any, company_name: Any, active: bool) -> dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "company": None if company_id is None else CompanyRef(id=company_id, name=company_name),
        "location_raw": job.location_raw,
        "country": job.country,
        "employment_type": job.employment_type,
        "seniority": job.seniority,
        "canonical_url": job.canonical_url,
        "first_seen_at": job.first_seen_at,
        "last_seen_at": job.last_seen_at,
        "active": bool(active),
    }


class JobReader:
    """Read-only queries over persisted jobs. Construct only through
    `open_read_only_reader`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._read_only = False

    async def _ensure_read_only(self) -> None:
        if not self._read_only:
            await self._session.execute(text("SET TRANSACTION READ ONLY"))
            self._read_only = True

    async def list_jobs(self, query: JobListQuery) -> JobListPage:
        await self._ensure_read_only()
        statement = _job_columns()
        conditions: list[ColumnElement[bool]] = []
        if not query.include_inactive:
            conditions.append(
                exists().where(JobOccurrence.job_id == Job.id, JobOccurrence.is_active.is_(True))
            )
        if query.title is not None:
            conditions.append(
                Job.title.ilike(f"%{_escape_like(query.title)}%", escape=_LIKE_ESCAPE)
            )
        if query.location is not None:
            conditions.append(
                Job.location_raw.ilike(f"%{_escape_like(query.location)}%", escape=_LIKE_ESCAPE)
            )
        for value, column in (
            (query.country, Job.country),
            (query.employment_type, Job.employment_type),
            (query.seniority, Job.seniority),
        ):
            if value is not None:
                conditions.append(func.lower(column) == func.lower(value))
        if query.after is not None:
            boundary_time, boundary_id = query.after.last_seen_at, query.after.job_id
            conditions.append(
                or_(
                    Job.last_seen_at < boundary_time,
                    and_(Job.last_seen_at == boundary_time, Job.id < boundary_id),
                )
            )
        statement = (
            statement.where(*conditions)
            .order_by(Job.last_seen_at.desc(), Job.id.desc())
            .limit(query.limit + 1)
        )
        rows = (await self._session.execute(statement)).all()
        page = rows[: query.limit]
        items = [JobListItem(**_list_item(*row)) for row in page]
        next_cursor = None
        if len(rows) > query.limit and items:
            last = items[-1]
            next_cursor = encode_cursor(CursorPosition(last.last_seen_at, last.id))
        return JobListPage(items=items, next_cursor=next_cursor)

    async def get_job(self, job_id: uuid.UUID) -> JobDetail | None:
        """Any job by ID, active or not; `None` if no row exists."""
        await self._ensure_read_only()
        row = (await self._session.execute(_job_columns().where(Job.id == job_id))).one_or_none()
        if row is None:
            return None
        job = row[0]
        occurrences = (
            (
                await self._session.execute(
                    select(JobOccurrence)
                    .where(JobOccurrence.job_id == job_id)
                    .order_by(JobOccurrence.last_seen_at.desc(), JobOccurrence.id.desc())
                )
            )
            .scalars()
            .all()
        )
        return JobDetail(
            **_list_item(*row),
            description_clean=job.description_clean,
            occurrences=[
                OccurrenceOut(
                    provider=occurrence.provider,
                    source=occurrence.source,
                    source_url=occurrence.source_url,
                    apply_url=occurrence.apply_url,
                    is_active=occurrence.is_active,
                    first_seen_at=occurrence.first_seen_at,
                    last_seen_at=occurrence.last_seen_at,
                )
                for occurrence in occurrences
            ],
        )


@asynccontextmanager
async def open_read_only_reader(
    sessionmaker: Callable[[], AsyncSession],
) -> AsyncIterator[JobReader]:
    """A `JobReader` over a fresh session that is always rolled back, never
    committed. Performs no database I/O itself; the reader's first query
    opens the read-only transaction."""
    async with sessionmaker() as session:
        try:
            yield JobReader(session)
        finally:
            await session.rollback()


async def job_reader() -> AsyncIterator[JobReader]:
    """FastAPI dependency for the jobs routes (wired in `app/api/deps.py`)."""
    async with open_read_only_reader(get_sessionmaker()) as reader:
        yield reader
