"""Output-affecting Greenhouse record semantics (Phase 4 S3, Class H;
`docs/DECISIONS/0018-d1-parser-version-and-normalized-persistence.md`).

Extracted unchanged from `app/providers/greenhouse.py` so that ADR 0018's D1
normalization manifest can hash exactly the code that decides a
`DiscoveredJob`'s values -- record validation (which records are kept, and
their `title`/`location`/IDs/URL/timestamp), duplicate identity, and the
content-mode gate that decides whether `content` is converted into
`description` -- without hashing the adapter's transport, retry, timeout, and
envelope code. Behavior is identical to the pre-extraction adapter.

Pure: no I/O, logging, network, or global state. Imports only the standard
library, `app.providers.greenhouse_content`, and `app.schemas.discovered_job`.
The adapter remains the only module that imports `httpx`.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from app.providers.greenhouse_content import (
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
