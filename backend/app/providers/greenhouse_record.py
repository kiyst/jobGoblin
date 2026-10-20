"""Output-affecting Greenhouse record semantics (Phase 4 S3, Class H;
`docs/DECISIONS/0018-d1-parser-version-and-normalized-persistence.md`).

Extracted unchanged from `app/providers/greenhouse.py` so that ADR 0018's D1
normalization manifest can hash every application semantic that decides a
`DiscoveredJob`'s values, without hashing the adapter's transport, retry,
timeout, health, and diagnostics code:

- board configuration (`GreenhouseBoard`) and the validated board set, the
  single source of both the board -> content-mode snapshot D1 verification
  binds and the board each job is built with;
- response decoding and JSON parsing, and extraction of the `jobs` array;
- record validation (which records are kept, and their title, location, IDs,
  URL, and timestamp) and duplicate selection;
- the content-mode gate that decides whether `content` becomes `description`,
  and `DiscoveredJob` construction.

Behavior is identical to the pre-extraction adapter.

Pure: no I/O, logging, network, or global state. Imports only the standard
library, `app.providers.greenhouse_content`, and `app.schemas.discovered_job`.
The adapter remains the only module that imports `httpx`.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit

from app.providers.greenhouse_content import (
    CONTENT_MODES,
    ERROR_INVALID_CONTENT_MODE,
    ContentOutcome,
    GreenhouseContentMode,
    convert_greenhouse_content,
)
from app.schemas.discovered_job import DiscoveredJob

PROVIDER_NAME = "greenhouse"
SOURCE_NAME = "greenhouse"

# Same covered-whitespace set as every model/natural-key trimming rule in
# `app/db/models/` and `app/ingestion/natural_key.py`.
_COVERED_WHITESPACE = " \t\n\r"

_HOST_LABEL_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_BOARD_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,99}")


class GreenhouseConfigurationError(ValueError):
    """Invalid boards or settings — a wiring error, raised at construction.
    Messages are fixed strings."""


@dataclass(frozen=True)
class GreenhouseBoard:
    """One configured board. `board_token` is a lowercase slug, so no
    tenant-case ambiguity can reach the natural key; `company` is the only
    source of `DiscoveredJob.company` (never the payload's `company_name`).
    `content_mode` is declared here and never inferred; `"disabled"` (the
    default) leaves `content` untouched."""

    board_token: str
    company: str
    content_mode: GreenhouseContentMode = "disabled"

    def __post_init__(self) -> None:
        if not isinstance(self.board_token, str) or not _BOARD_TOKEN_RE.fullmatch(self.board_token):
            raise GreenhouseConfigurationError("board_token must match ^[a-z0-9][a-z0-9_-]{0,99}$")
        if not isinstance(self.company, str) or not self.company.strip(_COVERED_WHITESPACE):
            raise GreenhouseConfigurationError("company must be a non-blank string")
        if type(self.content_mode) is not str or self.content_mode not in CONTENT_MODES:
            raise GreenhouseConfigurationError(ERROR_INVALID_CONTENT_MODE)


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


def to_discovered_job(
    *,
    board_token: str,
    company: str,
    content_mode: GreenhouseContentMode,
    item: _ValidRecord,
    discovered_at: datetime,
) -> tuple[DiscoveredJob, ContentOutcome | None]:
    """The job, plus the content-conversion outcome on an enabled board
    (`None` when the board is disabled, in which case `content` is never read by
    key; only the whole-record deep copy for `raw` carries it). Conversion reads
    only the original `content` value and never
    writes to the record or to `raw`."""
    description: str | None = None
    content_outcome: ContentOutcome | None = None
    if content_mode != "disabled":
        conversion = convert_greenhouse_content(item.record.get("content"), mode=content_mode)
        description = conversion.text
        content_outcome = conversion.outcome
    job = DiscoveredJob(
        provider=PROVIDER_NAME,
        source=SOURCE_NAME,
        source_tenant_id=board_token,
        source_job_id=str(item.job_id),
        requisition_id_raw=item.requisition_id,
        title=item.title,
        company=company,
        location=item.location,
        source_url=item.absolute_url,
        apply_url=None,
        canonical_url=item.absolute_url,
        description=description,
        compensation_text=None,
        posted_at=item.posted_at,
        discovered_at=discovered_at,
        raw=copy.deepcopy(item.record),
    )
    return job, content_outcome


# ---------------------------------------------------------------------------
# Response decoding, record selection, and per-board job construction
# (Phase 4 S3 correction 1, ADR 0018). Moved unchanged from the adapter.
# ---------------------------------------------------------------------------


def _reject_constant(_: str) -> Any:
    raise ValueError("non-finite JSON constant")


def _parse_finite_float(literal: str) -> float:
    value = float(literal)
    if not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    return value


def decode_envelope(body: bytes) -> tuple[str | None, dict[str, Any] | None]:
    """`(None, payload)` for a JSON object with a `jobs` list; otherwise the
    fixed failure kind `invalid_json` or `envelope` and `None`."""
    try:
        payload = json.loads(
            body.decode("utf-8"),
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
        )
    except (ValueError, RecursionError):
        # `RecursionError`: pathologically nested JSON is malformed
        # input, never a programmer error to raise past this boundary.
        return "invalid_json", None
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        return "envelope", None
    return None, payload


def select_records(records: list[Any]) -> list[_ValidRecord]:
    """The valid records whose duplicate identity occurs exactly once."""
    valid = [checked for checked in map(_validate_record, records) if checked is not None]
    identities = Counter(_duplicate_identity(item.job_id) for item in valid)
    return [item for item in valid if identities[_duplicate_identity(item.job_id)] == 1]


@dataclass(frozen=True)
class BoardParse:
    """One board's HTTP 200 body, decoded. `failure` is a fixed kind
    (`invalid_json`, `envelope`, `no_usable_records`) or `None`; on success
    `jobs` pairs each `DiscoveredJob` with its content-conversion outcome."""

    failure: str | None
    payload: dict[str, Any] | None = None
    record_count: int = 0
    discovered_at: datetime | None = None
    jobs: tuple[tuple[DiscoveredJob, ContentOutcome | None], ...] = ()


class GreenhouseBoardSet:
    """The configured boards, validated once. The single source of both the
    board -> content-mode snapshot that D1 verification binds and the board
    (token, company, content mode) each job is built with, so the two cannot
    disagree without a change to this hashed module."""

    def __init__(self, boards: Sequence[GreenhouseBoard]) -> None:
        board_list = list(boards)
        if not board_list:
            raise GreenhouseConfigurationError("at least one board is required")
        if not all(isinstance(board, GreenhouseBoard) for board in board_list):
            raise GreenhouseConfigurationError("boards must be GreenhouseBoard instances")
        tokens = [board.board_token for board in board_list]
        if len(tokens) != len(set(tokens)):
            raise GreenhouseConfigurationError("board tokens must be unique")
        self._boards = tuple(board_list)
        self._by_token: Mapping[str, GreenhouseBoard] = MappingProxyType(
            {board.board_token: board for board in board_list}
        )

    @property
    def boards(self) -> tuple[GreenhouseBoard, ...]:
        return self._boards

    def content_modes(self) -> Mapping[str, GreenhouseContentMode]:
        """A fresh read-only board token -> declared content mode snapshot."""
        return MappingProxyType({board.board_token: board.content_mode for board in self._boards})

    def parse_body(
        self, board_token: str, body: bytes, *, now: Callable[[], datetime]
    ) -> BoardParse:
        """Decodes one board's body and builds its jobs with that board's own
        configuration. `now` is called once, only when jobs are built."""
        board = self._by_token[board_token]
        failure, payload = decode_envelope(body)
        if failure is not None:
            return BoardParse(failure)
        assert payload is not None
        records: list[Any] = payload["jobs"]
        kept = select_records(records)
        if records and not kept:
            return BoardParse("no_usable_records")
        discovered_at = now()
        jobs = tuple(
            to_discovered_job(
                board_token=board.board_token,
                company=board.company,
                content_mode=board.content_mode,
                item=item,
                discovered_at=discovered_at,
            )
            for item in kept
        )
        return BoardParse(None, payload, len(records), discovered_at, jobs)
