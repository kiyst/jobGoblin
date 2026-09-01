"""Read-only, manually-invoked Greenhouse live ATS canary (Phase 4 prework,
Class H — external network access). Approved by the user with 15 binding
clarifications on 2026-08-30; the approval and this slice's own outcome are
recorded in this slice's `Work done` entry in `docs/LLM_HANDOFF.md` (the
proposal itself was presented and approved in conversation, not committed
as a separate document — `docs/LLM_HANDOFF.md`'s own two-iteration rotation
rule means only the `Work done`/`Work review` record persists here, not a
standalone proposal artifact).

Performs **exactly one** HTTP GET per invocation against Greenhouse's public
Job Board API (`https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs`
— documented at <https://developers.greenhouse.io/job-board.html>, accessed
2026-08-30) for one caller-supplied board token, to prove a real posting can
be mapped onto `DiscoveredJob` and to surface exactly what would still be
needed to route it through the existing ingestion pipeline. This is **not**
a `DiscoveryProvider` and is never imported by one — see this slice's `Work
done` entry in `docs/LLM_HANDOFF.md` for the deliberately deferred follow-up
slice (a minimal adapter, still no `ats-scrapers` dependency, still no
`QueryPlanner`/`ProviderRegistry`, still no Phase 3 normalization).

Never a legal opinion: `docs/SOURCE_CONNECTORS.md`'s existing caveat that
Greenhouse's own API terms of use were not independently reviewed is
preserved unchanged — read the linked documentation yourself before relying
on this at any volume. No new rate-limit claim is made here either; this
script self-imposes a single request, a short timeout, and a conservative
response-size cap regardless of whatever Greenhouse's actual server-side
limits are.

Safety properties enforced throughout this module (binding requirements):

- **No database writes of any kind** — this module never imports
  `app.db.session` or opens a database connection. Repository writes are
  limited to this script itself, the offline test file, one sanitized
  fixture, and documentation — never `jobgoblin`/`jobgoblin_test`.
- **The unsanitized response body lives only in a local variable** — never
  printed, logged, cached, or written to disk in full. Only sanitized
  operational metadata (status code, content type, byte count, elapsed
  time, board token, exception type) ever leaves `fetch_greenhouse_jobs_raw`
  on either success or failure.
- **No `content=true` query parameter is ever sent** — Greenhouse's default
  Job Board response (confirmed empirically before writing this module)
  already omits the HTML job-description field entirely unless that
  parameter is added. Never requesting it sidesteps the entire
  redaction question for this canary: there is nothing description-shaped
  to accidentally leak because it was never fetched.
- **Exactly one request** — no retries, no pagination loop, no polling, no
  following a redirect to a different host (`follow_redirects=False`), no
  secondary per-job detail request.
- **The response is streamed, not buffered, past `MAX_RESPONSE_BYTES`** —
  `fetch_greenhouse_jobs_raw` reads the body incrementally and stops
  consuming bytes as soon as the cumulative count exceeds the cap, so an
  unexpectedly large upstream response is never fully read into memory
  first.
- **Only a job satisfying the required mapping shape is ever selected or
  mapped** — a usable `id`, an absolute HTTPS `absolute_url`, and, when
  present, a valid/timezone-aware `first_published`. A malformed present
  value excludes a job rather than silently degrading to `None` or an
  unstable/naive value.
- **The sanitized fixture is written only to `DEFAULT_FIXTURE_PATH`, and
  atomically** — there is no caller-supplied output path; a failed write
  can never leave a truncated fixture in place of the previously committed
  one.
- **The committed fixture is an explicit allowlist**, never a raw dump —
  see `FIXTURE_ALLOWED_JOB_FIELDS` and `build_sanitized_fixture`.

    python scripts/canary_greenhouse.py --board-token gitlab --company GitLab
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.discovered_job import DiscoveredJob  # noqa: E402

GREENHOUSE_API_ORIGIN = "https://boards-api.greenhouse.io"
GREENHOUSE_API_DOCS_URL = "https://developers.greenhouse.io/job-board.html"

# Conservative, self-imposed — not derived from any published Greenhouse
# limit (none is officially published per docs/SOURCE_CONNECTORS.md).
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RESPONSE_BYTES = 5_000_000

# A conservative ASCII slug: letters, digits, hyphen, underscore only.
# Rejects anything that could turn `_build_url`'s string interpolation into
# a path-traversal or unexpected-host construction.
_BOARD_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")

DEFAULT_FIXTURE_PATH = (
    BACKEND_DIR / "tests" / "fixtures" / "discovery" / "greenhouse_live_canary.json"
)

# Established project identity labels for this ATS (docs/SOURCE_CONNECTORS.md
# lists Greenhouse access via the `ats-scrapers` library's own
# `scrapers/greenhouse.py`) — this canary calls Greenhouse directly, not
# through that library, but keeps the same `provider`/`source` pair so
# ingestion identity keys stay stable across an eventual migration to a real
# adapter.
DISCOVERED_JOB_PROVIDER = "ats_scrapers"
DISCOVERED_JOB_SOURCE = "greenhouse"

# The explicit allowlist a committed fixture may ever contain — see
# `build_sanitized_fixture`. Adding a field here is always a deliberate,
# reviewed choice, never an accidental full-object dump. Deliberately
# excludes `content`/`description` (never requested at all — see module
# docstring), `metadata`/`data_compliance` (company-specific categorization
# tags, not needed for mapping/identity validation), and `internal_job_id`
# (a second internal identifier not used by any mapping). `company_name` is
# included specifically so the offline tests can prove it is genuinely
# ignored (company is supplied externally — binding requirement) even
# though it is present in the real payload.
FIXTURE_ALLOWED_JOB_FIELDS = (
    "id",
    "title",
    "absolute_url",
    "location",
    "requisition_id",
    "updated_at",
    "first_published",
    "company_name",
)


class CanaryFetchError(RuntimeError):
    """Raised for any fail-closed condition in the HTTP boundary or job
    selection: non-2xx status, unexpected content type, oversized
    response, invalid JSON, missing/empty/malformed job list, or no job
    with a usable identifier. Never includes the response body — only
    sanitized metadata (see `FetchMetadata`) and the exception type."""


def validate_board_token(board_token: str) -> str:
    """Rejects anything that is not a conservative ASCII slug — never
    accepts a value containing `/`, `..`, whitespace, or non-ASCII
    characters that could otherwise change the request's target path."""
    if not _BOARD_TOKEN_RE.fullmatch(board_token):
        raise ValueError(f"board token must be a conservative ASCII slug: {board_token!r}")
    return board_token


def _build_url(board_token: str) -> str:
    token = validate_board_token(board_token)
    return f"{GREENHOUSE_API_ORIGIN}/v1/boards/{token}/jobs"


@dataclass(frozen=True)
class FetchMetadata:
    """Sanitized operational metadata only — every field here is safe to
    print, log, or include in an error message (binding requirement)."""

    board_token: str
    status_code: int
    content_type: str | None
    byte_count: int
    elapsed_seconds: float


@dataclass(frozen=True)
class RawResponse:
    """An already-received HTTP response, decoupled from the actual network
    call so `validate_and_parse_response` is directly unit-testable offline
    against a synthetic instance — never a real Greenhouse request."""

    status_code: int
    content_type: str | None
    body: bytes


def validate_and_parse_response(
    response: RawResponse, *, board_token: str, elapsed_seconds: float
) -> tuple[dict[str, Any], FetchMetadata]:
    """Pure validation/parsing of an already-received HTTP response — no
    I/O. Fails closed on non-2xx status, an oversized body, an unexpected
    content type, invalid JSON, or a missing/empty/malformed `jobs` list.
    Never includes `response.body` in any raised message or returned
    value other than the parsed `jobs` payload itself."""
    byte_count = len(response.body)
    metadata = FetchMetadata(
        board_token=board_token,
        status_code=response.status_code,
        content_type=response.content_type,
        byte_count=byte_count,
        elapsed_seconds=elapsed_seconds,
    )
    if not 200 <= response.status_code < 300:
        raise CanaryFetchError(f"non-2xx status: {metadata}")
    if byte_count > MAX_RESPONSE_BYTES:
        raise CanaryFetchError(f"response too large: {metadata}")
    if response.content_type is None or "json" not in response.content_type.lower():
        raise CanaryFetchError(f"unexpected content-type: {metadata}")
    try:
        payload = json.loads(response.body)
    except ValueError as exc:
        raise CanaryFetchError(f"invalid JSON ({type(exc).__name__}): {metadata}") from None
    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        raise CanaryFetchError(f"malformed schema (missing/invalid 'jobs' list): {metadata}")
    if len(payload["jobs"]) == 0:
        raise CanaryFetchError(f"empty job list: {metadata}")
    return payload, metadata


async def fetch_greenhouse_jobs_raw(
    board_token: str, *, client: httpx.AsyncClient | None = None
) -> tuple[dict[str, Any], FetchMetadata]:
    """The one real network call this script ever makes. No retries, no
    redirect-following (`follow_redirects=False`), no pagination, no
    second request of any kind. Streams the response body and stops
    consuming bytes as soon as the cumulative count exceeds
    `MAX_RESPONSE_BYTES`, so an oversized upstream response is never fully
    buffered in memory before the size cap is enforced.

    `client` is injectable so offline tests can exercise this function's
    real streaming behavior against an in-process `httpx.MockTransport` —
    never a real socket — and remain responsible for closing a client they
    supplied themselves. Production code always leaves it `None`, in which
    case this function opens and closes its own single-use client."""
    url = _build_url(board_token)
    start = time.monotonic()
    owns_client = client is None
    active_client = (
        client
        if client is not None
        else httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
    )
    try:
        try:
            async with active_client.stream("GET", url) as response:
                status_code = response.status_code
                content_type = response.headers.get("content-type")
                chunks: list[bytes] = []
                total_bytes = 0
                async for chunk in response.aiter_bytes():
                    total_bytes += len(chunk)
                    chunks.append(chunk)
                    if total_bytes > MAX_RESPONSE_BYTES:
                        break
                body = b"".join(chunks)
        except httpx.HTTPError as exc:
            elapsed = time.monotonic() - start
            raise CanaryFetchError(
                f"request failed ({type(exc).__name__}) after {elapsed:.2f}s: "
                f"board_token={board_token}"
            ) from None
    finally:
        if owns_client:
            await active_client.aclose()
    elapsed = time.monotonic() - start
    raw = RawResponse(status_code=status_code, content_type=content_type, body=body)
    return validate_and_parse_response(raw, board_token=board_token, elapsed_seconds=elapsed)


def _is_usable_job_id(value: Any) -> bool:
    """A usable identifier: a non-blank `str` or an `int` — never `bool`
    (a `bool` is an `int` subclass in Python but is never a real Greenhouse
    identifier) and never any other type."""
    if isinstance(value, bool) or not isinstance(value, int | str):
        return False
    return not (isinstance(value, str) and not value.strip())


def _is_absolute_https_url(value: Any) -> bool:
    """An absolute `https://` URL with a non-empty host — never a relative
    path, a `javascript:`/`data:` scheme, or a bare string."""
    if not isinstance(value, str) or not value:
        return False
    parsed = urlsplit(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_valid_optional_first_published(value: Any) -> bool:
    """`first_published` is optional: absent (`None`) is always valid.
    When present, it must be a string parseable by `datetime.fromisoformat`
    that carries an explicit timezone — a naive timestamp is ambiguous and
    is rejected rather than silently accepted."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _has_required_mapping_shape(job: Any) -> bool:
    """The full shape `map_job_to_discovered_job` requires: a usable `id`,
    an absolute HTTPS `absolute_url`, and — when present — a valid,
    timezone-aware `first_published`. Used both to filter candidates in
    `select_representative_job` and, redundantly, inside
    `map_job_to_discovered_job` itself as defense in depth."""
    return (
        isinstance(job, dict)
        and _is_usable_job_id(job.get("id"))
        and _is_absolute_https_url(job.get("absolute_url"))
        and _is_valid_optional_first_published(job.get("first_published"))
    )


def select_representative_job(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically selects one job: filters to jobs satisfying the
    required mapping shape (usable `id`, absolute HTTPS `absolute_url`, and
    a valid/aware `first_published` when present), sorts by that `id`'s
    stringified form ascending, and returns the first. Never relies on the
    order Greenhouse's response happened to arrive in (binding
    requirement). A malformed present value (not merely a missing one)
    excludes a job from selection rather than propagating an unstable
    identity or invalid timestamp downstream."""
    valid_jobs = [job for job in jobs if _has_required_mapping_shape(job)]
    if not valid_jobs:
        raise CanaryFetchError(
            "no job in the response satisfies the required mapping shape "
            "(usable id, absolute HTTPS absolute_url, and a valid/aware "
            "first_published when present)"
        )
    return sorted(valid_jobs, key=lambda job: str(job["id"]))[0]


def map_job_to_discovered_job(
    job: dict[str, Any],
    *,
    board_token: str,
    company: str,
    discovered_at: datetime,
) -> DiscoveredJob:
    """Pure mapping, no I/O — takes one already-fetched, already-parsed
    Greenhouse job dict plus caller-supplied board token/company/
    observation time. Exercised identically online and offline (against
    the sanitized fixture), since it never touches the network itself.

    - `source_tenant_id`/`source_job_id` come from the board token and the
      job's own `id` — a clean Tier-1 `NaturalKeyDomain.TENANT` natural key.
    - `requisition_id_raw` comes from Greenhouse's own distinct
      `requisition_id` field (confirmed present and different from `id` in
      a real response — resolves the proposal's own "to confirm" item).
    - `canonical_url`/`source_url` both come from `absolute_url` — the one
      link Greenhouse's public API provides per posting.
    - `apply_url` stays `None` — the public Job Board API does not expose a
      distinct apply link separate from `absolute_url`; never invented by
      copying it (binding requirement).
    - `posted_at` comes from `first_published` only — a field name that is
      itself an explicit publish-time claim, unlike `updated_at` (a
      last-modified time), which is never used for this field (binding
      requirement). Absent that field, `posted_at` stays `None`; a
      *present* but malformed or timezone-naive value raises `ValueError`
      rather than silently mapping to `None` or a naive datetime.
    - `description`/`compensation_text` stay `None` — this canary never
      requests `content=true`, so there is no HTML description or
      compensation text to map in the first place.
    - `company` is exactly the caller-supplied value — never
      `job.get("company_name")`, even though that field is present in the
      real payload (binding requirement: company supplied externally).
    """
    job_id = job.get("id")
    if not _is_usable_job_id(job_id):
        raise ValueError("job is missing a required, usable 'id' field")
    source_job_id = str(job_id)

    absolute_url = job.get("absolute_url")
    if not _is_absolute_https_url(absolute_url):
        raise ValueError("job is missing a required absolute HTTPS 'absolute_url' field")
    assert isinstance(absolute_url, str)

    title = job.get("title")
    title = title if isinstance(title, str) else None

    location: str | None = None
    location_obj = job.get("location")
    if isinstance(location_obj, dict):
        location_name = location_obj.get("name")
        location = location_name if isinstance(location_name, str) else None

    requisition_id = job.get("requisition_id")
    requisition_id_raw = str(requisition_id) if requisition_id is not None else None

    first_published = job.get("first_published")
    if not _is_valid_optional_first_published(first_published):
        raise ValueError("job has a malformed or timezone-naive 'first_published' field")
    posted_at = datetime.fromisoformat(first_published) if first_published is not None else None

    return DiscoveredJob(
        provider=DISCOVERED_JOB_PROVIDER,
        source=DISCOVERED_JOB_SOURCE,
        source_tenant_id=board_token,
        source_job_id=source_job_id,
        requisition_id_raw=requisition_id_raw,
        title=title,
        company=company,
        location=location,
        source_url=absolute_url,
        apply_url=None,
        canonical_url=absolute_url,
        description=None,
        compensation_text=None,
        posted_at=posted_at,
        discovered_at=discovered_at,
        raw=job,
    )


def build_sanitized_fixture(
    job: dict[str, Any], *, board_token: str, company: str, accessed_at: str
) -> dict[str, Any]:
    """Builds the exact, explicit-allowlist subset of one Greenhouse job
    dict safe to commit as a test fixture. Labeled explicitly as a
    sanitized derived sample, never a byte- or structure-preserved raw
    payload (binding requirement)."""
    allowed_job = {key: job[key] for key in FIXTURE_ALLOWED_JOB_FIELDS if key in job}
    return {
        "_fixture_kind": "sanitized_derived_sample",
        "_note": (
            "This is a sanitized, explicit-allowlist derived sample of one real "
            "Greenhouse Job Board API response job entry — NOT a byte- or "
            "structure-preserved raw payload. See "
            "backend/scripts/canary_greenhouse.py::FIXTURE_ALLOWED_JOB_FIELDS for "
            "the exact allowlist. HTML description/content was never requested "
            "for this canary and is not present anywhere in this file."
        ),
        "_source_api": f"{GREENHOUSE_API_ORIGIN}/v1/boards/{{board_token}}/jobs",
        "_source_docs": GREENHOUSE_API_DOCS_URL,
        "_accessed_at": accessed_at,
        "board_token": board_token,
        "company": company,
        "job": allowed_job,
    }


def _write_fixture_atomically(fixture: dict[str, Any], destination: Path) -> None:
    """Writes `fixture` as pretty-printed, sorted-key JSON to `destination`
    atomically: the content is written to a sibling temporary file first,
    then moved into place with `os.replace` (an atomic rename on both POSIX
    and Windows for a same-directory move). A failed write or an
    interrupted process therefore can never leave the previously committed
    fixture truncated or partially overwritten — either the old content or
    the fully-written new content is present, never a partial file. There
    is deliberately no caller-supplied destination path (binding
    requirement): repository writes are constrained to the one authorized
    fixture location."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(fixture, indent=2, sort_keys=True) + "\n")
        os.replace(tmp_name, destination)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="canary_greenhouse.py",
        description="Read-only, single-request Greenhouse live ATS canary.",
    )
    parser.add_argument(
        "--board-token", required=True, help="Greenhouse board token, e.g. 'gitlab'."
    )
    parser.add_argument(
        "--company",
        required=True,
        help="Human-readable company display name, supplied explicitly — never inferred.",
    )
    return parser.parse_args(argv)


async def run_canary(board_token: str, company: str) -> None:
    discovered_at = datetime.now(UTC)
    payload, metadata = await fetch_greenhouse_jobs_raw(board_token)
    print(
        f"fetch ok: {asdict(metadata)}",
    )
    jobs = payload["jobs"]
    print(f"jobs_count={len(jobs)}")

    representative = select_representative_job(jobs)
    discovered_job = map_job_to_discovered_job(
        representative, board_token=board_token, company=company, discovered_at=discovered_at
    )
    print(
        "mapped:"
        f" source_tenant_id={discovered_job.source_tenant_id!r}"
        f" source_job_id={discovered_job.source_job_id!r}"
        f" requisition_id_raw={discovered_job.requisition_id_raw!r}"
        f" title={discovered_job.title!r}"
        f" location={discovered_job.location!r}"
        f" canonical_url={discovered_job.canonical_url!r}"
        f" apply_url={discovered_job.apply_url!r}"
        f" posted_at={discovered_job.posted_at!r}"
        f" discovered_at={discovered_job.discovered_at!r}"
    )

    fixture = build_sanitized_fixture(
        representative,
        board_token=board_token,
        company=company,
        accessed_at=discovered_at.isoformat(),
    )
    _write_fixture_atomically(fixture, DEFAULT_FIXTURE_PATH)
    print(f"fixture written: {DEFAULT_FIXTURE_PATH}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        validate_board_token(args.board_token)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        asyncio.run(run_canary(args.board_token, args.company))
    except CanaryFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
