"""Bounded, manually-invoked Greenhouse evaluation-posting acquisition
(realistic Phase 3 evaluation corpus, Class H -- external network access).
Approved by the user with binding acquisition/sanitization/retention
clarifications; that approval and this slice's outcome are recorded in
this slice's `Work done` entry in `docs/LLM_HANDOFF.md`.

Performs a bounded, two-phase fetch against Greenhouse's public Job Board
API for each of a small, explicitly named, closed set of board tokens, to
populate the realistic evaluation corpus `evaluate_phase3_corpus.py`
scores against. This is **not** a `DiscoveryProvider`, never imported by
one, and never writes to any database.

**Never a legal opinion**: `docs/SOURCE_CONNECTORS.md`'s existing caveat
that Greenhouse's own API terms of use were not independently reviewed is
preserved unchanged.

Safety properties enforced throughout this module (binding requirements):

- **No database writes of any kind.**
- **Two-phase fetch per board, never `content=true` on the list call**:
  (1) exactly one metadata-only `GET .../jobs` list request (Greenhouse's
  default list response already omits `content` entirely); (2) from that
  response alone -- before any description or parser output exists to
  examine -- deterministically select at most
  `MAX_DETAIL_REQUESTS_PER_BOARD` job ids (usable-id jobs, sorted by
  stringified id ascending, never Greenhouse's own response order); (3)
  exactly one detail `GET .../jobs/{id}` per selected id, with neither
  `questions=true` nor `pay_transparency=true`. At most
  `MAX_REQUESTS_PER_BOARD` requests per board.
- **Zero retries** -- matching `canary_greenhouse.py`'s own established
  property exactly, never reintroduced here.
- **Two independent, truly streaming byte caps**: `MAX_RESPONSE_BYTES` per
  individual streamed response and `MAX_TOTAL_RUN_BYTES` cumulative across
  every request this run makes (`_RunBudget`) -- every chunk is charged to
  the cumulative budget *first*, and only then is that response's own
  per-response ceiling evaluated for that chunk, so an oversized response
  can never evade the cumulative cap by being rejected before it is
  counted, and repeated oversized responses accumulate toward it exactly
  as any other bytes would. Exhausting the total-run budget raises
  `FatalBudgetExhaustedError`, deliberately not a subclass of
  `EvaluationFetchError`, so it aborts the entire run immediately instead
  of being treated as one board's ordinary failure -- taking precedence
  over an ordinary per-response overflow when one chunk triggers both.
- **A detail record must be usable to count toward board success**:
  matching `id`, a `title` containing meaningful text, and `content` that
  sanitizes successfully into a `description` containing meaningful text
  (`_is_usable_detail_candidate`/`_has_meaningful_text`) -- a value that is
  merely a non-empty string is not enough; whitespace-only (including
  NBSP) and Unicode-format-character-only (category `Cf`) text, and any
  mixture of the two, are rejected the same as missing/empty text. An
  unusable record is skipped, not staged, and does not abort the board.
- **Unsanitized response bodies exist only as in-process values for the
  duration of processing one job**, then are discarded -- never written
  to any file, temporary or otherwise, in raw form, at any point.
- **No field enumeration**: only `id`, `title`, `location.name`, and
  `content` are ever read from a parsed response. Every other key --
  documented or not, sensitive or not -- is never traversed, never
  logged, and cannot reach a staged or committed record, because nothing
  in this module ever accesses it.
- **Sanitization is HTML-to-text conversion (`greenhouse_html_convert.
  convert_html_to_text`) plus email/phone-pattern redaction, defense in
  depth only** -- this module never claims redaction guarantees the
  absence of personal/contact data; a mandatory manual read-through of
  every staged candidate, before any commit, is a separate, later step
  this module does not and cannot perform.
- **`compensation_text` is always `None` here** -- this module fetches no
  dedicated compensation field; a non-null value may only be introduced
  later, manually, as a verbatim substring of the sanitized description.
- **At least two distinct approved boards must each yield >=1 usable
  candidate, or nothing is staged at all** -- a board that fails or
  yields nothing is skipped, logged as unavailable, and never substituted
  with an unapproved board.
- **The staging file is fixed, gitignored, and atomic create-only**
  (`_write_json_atomic_create_only`, the same algorithm as
  `verification_receipts.write_receipt_atomic`) -- written only after the
  entire authorized batch succeeds; any failure leaves no staging file.
- **Operational metadata only in logs/errors** -- board token, job id,
  status code, byte counts, elapsed time, exception type. Never raw *or
  sanitized* posting text.

    python scripts/fetch_greenhouse_evaluation_postings.py \\
        --board gitlab:GitLab --board <token>:<Employer>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
REPO_ROOT = BACKEND_DIR.parent

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.canary_greenhouse import (  # noqa: E402
    GREENHOUSE_API_ORIGIN,
    REQUEST_TIMEOUT_SECONDS,
    CanaryFetchError,
    RawResponse,
    _is_usable_job_id,
    validate_and_parse_response,
    validate_board_token,
)
from scripts.greenhouse_html_convert import HtmlConversionError, convert_html_to_text  # noqa: E402

# Conservative, self-imposed -- matches canary_greenhouse.py's per-response
# cap exactly; the total-run cap is new to this module (a single-request
# canary has no separate "total" concept).
MAX_RESPONSE_BYTES = 5_000_000
MAX_TOTAL_RUN_BYTES = 20_000_000

MAX_DETAIL_REQUESTS_PER_BOARD = 10
MAX_REQUESTS_PER_BOARD = 1 + MAX_DETAIL_REQUESTS_PER_BOARD  # 11
MIN_SUCCESSFUL_BOARDS = 2

STAGING_PATH = BACKEND_DIR / ".evaluation-staging" / "greenhouse_candidates_staging.json"

_JOB_ID_RE = re.compile(r"^[0-9]{1,32}$")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\w)(\+?\d[\d().\-\s]{7,}\d)(?!\w)")
_REDACT_EMAIL = "[REDACTED_EMAIL]"
_REDACT_PHONE = "[REDACTED_PHONE]"


class EvaluationFetchError(RuntimeError):
    """Fail-closed error for any ordinary, per-board acquisition-boundary
    condition -- non-2xx status, an oversized individual response,
    unexpected content type, invalid JSON, malformed schema, a detail
    response whose `id` does not match the requested one, or fewer than
    `MIN_SUCCESSFUL_BOARDS` successful boards. Never includes raw or
    sanitized posting text, matching `canary_greenhouse.CanaryFetchError`'s
    own binding rule -- only operational metadata. `run_acquisition`
    catches this per board and continues to the next one; it must never
    catch `FatalBudgetExhaustedError` this way (see below)."""


class FatalBudgetExhaustedError(RuntimeError):
    """Raised the instant the cumulative total-run byte budget
    (`MAX_TOTAL_RUN_BYTES`) is exhausted by any streamed chunk, from any
    request, on any board. Deliberately **not** a subclass of
    `EvaluationFetchError`: it must propagate straight out of
    `run_acquisition`'s per-board `except EvaluationFetchError` handling
    uncaught, aborting the entire run immediately and contacting no
    further board -- exhausting the run-wide budget is a run-ending
    condition, never an ordinary single-board failure to skip past."""


@dataclass
class _RunBudget:
    """Tracks cumulative streamed bytes across every request this run
    makes. `consume` must be called for each streamed chunk before it is
    accepted into a response body -- a true streaming cap, never a check
    performed only after an entire response has already been downloaded."""

    max_total_bytes: int
    consumed_bytes: int = 0

    def consume(self, n: int) -> None:
        self.consumed_bytes += n
        if self.consumed_bytes > self.max_total_bytes:
            raise FatalBudgetExhaustedError(
                f"total-run byte cap exceeded: consumed={self.consumed_bytes} "
                f"cap={self.max_total_bytes}"
            )


def _redact_contact_patterns(text: str) -> str:
    """Defense in depth only -- never claimed to guarantee the absence of
    personal/contact data. A mandatory manual read-through of every
    staged candidate is a separate, later, human step."""
    text = _EMAIL_RE.sub(_REDACT_EMAIL, text)
    return _PHONE_RE.sub(_REDACT_PHONE, text)


def _build_detail_url(board_token: str, job_id: str) -> str:
    token = validate_board_token(board_token)
    if not _JOB_ID_RE.fullmatch(job_id):
        raise EvaluationFetchError(f"job id is not a conservative numeric id: {job_id!r}")
    return f"{GREENHOUSE_API_ORIGIN}/v1/boards/{token}/jobs/{job_id}"


async def _stream_get(
    url: str, *, client: httpx.AsyncClient, run_budget: _RunBudget
) -> tuple[int, str | None, bytes]:
    """One GET, streamed and capped exactly like
    `canary_greenhouse.fetch_greenhouse_jobs_raw`'s own request. Every
    chunk `httpx` yields is charged to the shared total-run budget
    *first* -- the cumulative cap measures bytes actually received over
    the wire, never only bytes a well-behaved response happened to stay
    under -- and only afterward is that chunk's effect on *this*
    response's own per-response ceiling evaluated. Consequently, if one
    chunk would exceed both caps simultaneously, `FatalBudgetExhaustedError`
    (raised by `run_budget.consume`, and deliberately not caught here)
    takes precedence over the ordinary per-response
    `EvaluationFetchError` and propagates straight out, aborting the
    entire run rather than only this response. Never retried; a
    transport failure raises immediately."""
    try:
        async with client.stream("GET", url) as response:
            status_code = response.status_code
            content_type = response.headers.get("content-type")
            chunks: list[bytes] = []
            total_bytes = 0
            over_response_cap = False
            async for chunk in response.aiter_bytes():
                chunk_len = len(chunk)
                run_budget.consume(chunk_len)
                total_bytes += chunk_len
                if total_bytes > MAX_RESPONSE_BYTES:
                    over_response_cap = True
                    break
                chunks.append(chunk)
            body = b"".join(chunks)
    except httpx.HTTPError as exc:
        raise EvaluationFetchError(f"request failed ({type(exc).__name__}): url={url}") from None
    if over_response_cap:
        raise EvaluationFetchError(f"per-response byte cap exceeded: url={url}")
    return status_code, content_type, body


def _select_job_ids(jobs: list[dict[str, Any]], *, limit: int) -> list[str]:
    """Deterministically selects at most `limit` job ids from a list
    response -- filters to jobs with a usable `id`, sorts by that id's
    stringified form ascending (never Greenhouse's own response order),
    de-duplicates by stringified id (never spending part of the detail
    budget re-fetching the same job twice), and takes the first `limit`.
    Runs strictly before any detail response, description text, or
    parser output exists to examine."""
    usable = [job for job in jobs if isinstance(job, dict) and _is_usable_job_id(job.get("id"))]
    ordered = sorted(usable, key=lambda job: str(job["id"]))
    seen: set[str] = set()
    deduplicated: list[str] = []
    for job in ordered:
        job_id = str(job["id"])
        if job_id in seen:
            continue
        seen.add(job_id)
        deduplicated.append(job_id)
    return deduplicated[:limit]


def _validate_detail_response(
    body: bytes,
    *,
    content_type: str | None,
    status_code: int,
    board_token: str,
    job_id: str,
) -> dict[str, Any]:
    if not 200 <= status_code < 300:
        raise EvaluationFetchError(
            f"non-2xx status on detail fetch: board_token={board_token} job_id={job_id} "
            f"status={status_code}"
        )
    if content_type is None or "json" not in content_type.lower():
        raise EvaluationFetchError(
            f"unexpected content-type on detail fetch: board_token={board_token} job_id={job_id}"
        )
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise EvaluationFetchError(
            f"invalid JSON on detail fetch ({type(exc).__name__}): "
            f"board_token={board_token} job_id={job_id}"
        ) from None
    if not isinstance(payload, dict):
        raise EvaluationFetchError(
            f"malformed detail schema: board_token={board_token} job_id={job_id}"
        )
    if str(payload.get("id")) != job_id:
        raise EvaluationFetchError(
            f"detail response id mismatch: board_token={board_token} job_id={job_id}"
        )
    return payload


@dataclass(frozen=True)
class SanitizedCandidate:
    board_token: str
    employer: str
    job_id: str
    title: str | None
    description: str | None
    location_raw: str | None
    accessed_at: str


def _sanitize_job_detail(
    payload: dict[str, Any], *, board_token: str, employer: str, accessed_at: str
) -> SanitizedCandidate:
    """Reads exactly `id`, `title`, `location.name`, and `content` from
    `payload` -- every other key, whatever it is, is never accessed."""
    job_id = str(payload.get("id"))

    title_raw = payload.get("title")
    title = _redact_contact_patterns(title_raw) if isinstance(title_raw, str) else None

    location_raw_value: str | None = None
    location_obj = payload.get("location")
    if isinstance(location_obj, dict):
        name = location_obj.get("name")
        if isinstance(name, str):
            location_raw_value = _redact_contact_patterns(name)

    description: str | None = None
    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        try:
            converted = convert_html_to_text(content)
        except HtmlConversionError as exc:
            raise EvaluationFetchError(
                f"HTML conversion failed for board_token={board_token} job_id={job_id} "
                f"({type(exc).__name__}) -- refusing to stage possibly-truncated text"
            ) from None
        description = _redact_contact_patterns(converted)

    return SanitizedCandidate(
        board_token=board_token,
        employer=employer,
        job_id=job_id,
        title=title,
        description=description,
        location_raw=location_raw_value,
        accessed_at=accessed_at,
    )


def _has_meaningful_text(value: str | None) -> bool:
    """True only if `value` contains at least one character that is
    neither whitespace (`str.isspace()` -- ASCII space/tab/newline and
    Unicode spaces such as NBSP) nor a Unicode **format** character
    (category `Cf` -- zero-width space, BOM, etc.), including a mixture
    of the two. Rejects `None`, `""`, and any string composed entirely
    of such characters. Deliberately narrow -- a purely mechanical
    presence check for *some* real text, never a broader semantic
    quality heuristic (grammar, language, minimum length, and so on are
    all out of scope)."""
    if value is None:
        return False
    return any(not char.isspace() and unicodedata.category(char) != "Cf" for char in value)


def _is_usable_detail_candidate(candidate: SanitizedCandidate) -> bool:
    """A detail record counts toward board success only once it clears
    every usability gate: a matching `id` (already enforced, fatally to
    the request, by `_validate_detail_response`), a `title` containing
    meaningful text, and `content` that sanitized successfully into a
    `description` containing meaningful text (`_has_meaningful_text`) --
    never merely a non-empty string, which a whitespace-only or
    Unicode-format-character-only value would still satisfy. A record
    failing this gate is skipped -- never counted, never staged --
    without aborting the rest of the board."""
    return _has_meaningful_text(candidate.title) and _has_meaningful_text(candidate.description)


async def _fetch_board(
    board_token: str, employer: str, *, client: httpx.AsyncClient, run_budget: _RunBudget
) -> list[SanitizedCandidate]:
    """One board's full two-phase fetch. Returns the sanitized candidates
    actually produced -- an empty list, not an exception, if the board is
    reachable but yields nothing usable, so the caller counts it
    accurately against `MIN_SUCCESSFUL_BOARDS`."""
    validate_board_token(board_token)
    list_url = f"{GREENHOUSE_API_ORIGIN}/v1/boards/{board_token}/jobs"
    start = time.monotonic()
    status_code, content_type, body = await _stream_get(
        list_url, client=client, run_budget=run_budget
    )
    elapsed = time.monotonic() - start
    raw = RawResponse(status_code=status_code, content_type=content_type, body=body)
    try:
        payload, _metadata = validate_and_parse_response(
            raw, board_token=board_token, elapsed_seconds=elapsed
        )
    except CanaryFetchError as exc:
        raise EvaluationFetchError(str(exc)) from None
    jobs = payload["jobs"]

    job_ids = _select_job_ids(jobs, limit=MAX_DETAIL_REQUESTS_PER_BOARD)
    accessed_at = datetime.now(UTC).isoformat()

    # Explicit, enforced ceiling -- never just an emergent consequence of
    # `_select_job_ids`'s own limit. 1 (the list request already made)
    # plus len(job_ids) must never exceed MAX_REQUESTS_PER_BOARD.
    if 1 + len(job_ids) > MAX_REQUESTS_PER_BOARD:
        raise EvaluationFetchError(
            f"board_token={board_token}: selected {len(job_ids)} detail requests, "
            f"which would exceed MAX_REQUESTS_PER_BOARD={MAX_REQUESTS_PER_BOARD}"
        )

    candidates: list[SanitizedCandidate] = []
    for job_id in job_ids:
        detail_url = _build_detail_url(board_token, job_id)
        status_code, content_type, body = await _stream_get(
            detail_url, client=client, run_budget=run_budget
        )
        detail_payload = _validate_detail_response(
            body,
            content_type=content_type,
            status_code=status_code,
            board_token=board_token,
            job_id=job_id,
        )
        try:
            candidate = _sanitize_job_detail(
                detail_payload, board_token=board_token, employer=employer, accessed_at=accessed_at
            )
        except EvaluationFetchError as exc:
            # A sanitization failure (e.g. unclosed <script>/<style>,
            # HtmlConversionError) is this one job's problem, never the
            # whole board's -- must not discard already-collected
            # candidates from earlier job ids or abort remaining ones.
            print(
                f"skipped unusable detail record: board_token={board_token} job_id={job_id} "
                f"(sanitization failed: {exc})",
                file=sys.stderr,
            )
            continue
        if not _is_usable_detail_candidate(candidate):
            print(
                f"skipped unusable detail record: board_token={board_token} job_id={job_id} "
                "(title or content has no meaningful text)",
                file=sys.stderr,
            )
            continue
        candidates.append(candidate)
    return candidates


async def run_acquisition(
    boards: list[tuple[str, str]], *, client: httpx.AsyncClient | None = None
) -> list[SanitizedCandidate]:
    """`boards` is the caller's already-authorized, closed
    `(board_token, employer)` list. Attempts every board once; a
    per-board failure is caught, logged as unavailable, and skipped --
    never retried, never substituted. Raises `EvaluationFetchError`
    without returning anything if fewer than `MIN_SUCCESSFUL_BOARDS`
    boards yield >=1 candidate, so the caller stages nothing."""
    run_budget = _RunBudget(max_total_bytes=MAX_TOTAL_RUN_BYTES)
    all_candidates: list[SanitizedCandidate] = []
    successful_boards: set[str] = set()

    owns_client = client is None
    active_client = (
        client
        if client is not None
        else httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
    )
    try:
        for board_token, employer in boards:
            try:
                candidates = await _fetch_board(
                    board_token, employer, client=active_client, run_budget=run_budget
                )
            except EvaluationFetchError as exc:
                print(
                    f"board unavailable, skipped: board_token={board_token} ({exc})",
                    file=sys.stderr,
                )
                continue
            if candidates:
                successful_boards.add(board_token)
                all_candidates.extend(candidates)
            else:
                print(
                    f"board unavailable, skipped: board_token={board_token} "
                    "(reachable, but yielded zero usable candidates)",
                    file=sys.stderr,
                )
    finally:
        if owns_client:
            await active_client.aclose()

    if len(successful_boards) < MIN_SUCCESSFUL_BOARDS:
        raise EvaluationFetchError(
            f"only {len(successful_boards)} board(s) yielded usable records "
            f"(need >= {MIN_SUCCESSFUL_BOARDS}); aborting with no staging file"
        )
    return all_candidates


def _write_json_atomic_create_only(path: Path, data: Any) -> None:
    """Same algorithm as `verification_receipts.write_receipt_atomic`:
    write-to-temp, fsync, then `os.link` (hard-link creation, refused by
    the filesystem if `path` already exists) -- never `os.replace`, which
    can silently overwrite. Duplicated, not imported: that function's
    signature is dict-only; this module's payload is a JSON array. The
    algorithm itself is reused verbatim, not independently re-derived."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=False) + "\n"
    fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError as exc:
            raise EvaluationFetchError(
                f"a staging file already exists at {path} -- create-only, refusing to overwrite"
            ) from exc
        except OSError as exc:
            raise EvaluationFetchError(
                f"atomic create-if-absent write unavailable for {path} ({type(exc).__name__})"
            ) from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _candidate_to_staged_dict(candidate: SanitizedCandidate) -> dict[str, Any]:
    return {
        "provenance": {
            "provider": "greenhouse",
            "employer": candidate.employer,
            "template_family": "unknown",
            "capture": {
                "board_token": candidate.board_token,
                "job_id": candidate.job_id,
                "accessed_at": candidate.accessed_at,
                "capture_method": "fetch_greenhouse_evaluation_postings.py",
            },
            "sanitization_lineage": (
                "title/location.name/content fetched via the public Greenhouse Job Board "
                "API detail endpoint (no questions=true, no pay_transparency=true); content "
                "HTML converted via greenhouse_html_convert.convert_html_to_text; email/phone-"
                "like patterns redacted; awaiting mandatory manual pre-commit review."
            ),
            "origin": "sanitized_capture",
        },
        "fields": {
            "title": candidate.title,
            "description": candidate.description,
            "location_raw": candidate.location_raw,
            "compensation_text": None,
        },
    }


def _parse_board_arg(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError(f"expected 'board_token:Employer Name', got {value!r}")
    token, _, employer = value.partition(":")
    if not token or not employer:
        raise argparse.ArgumentTypeError(f"expected 'board_token:Employer Name', got {value!r}")
    return token, employer


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fetch_greenhouse_evaluation_postings.py",
        description="Bounded, two-phase Greenhouse evaluation-posting acquisition.",
    )
    parser.add_argument(
        "--board",
        action="append",
        required=True,
        type=_parse_board_arg,
        dest="boards",
        metavar="board_token:Employer",
        help="Repeatable. Exactly the boards named in the user's authorization statement.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        candidates = asyncio.run(run_acquisition(args.boards))
    except FatalBudgetExhaustedError as exc:
        print(
            f"error: fatal total-run budget exhaustion, entire run aborted: {exc}", file=sys.stderr
        )
        return 1
    except EvaluationFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    staged = [_candidate_to_staged_dict(c) for c in candidates]
    try:
        _write_json_atomic_create_only(STAGING_PATH, staged)
    except EvaluationFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    boards_reached = {c.board_token for c in candidates}
    print(
        f"staged {len(staged)} candidate(s) from {len(boards_reached)} board(s) at {STAGING_PATH}"
    )
    print("MANUAL REVIEW REQUIRED before any content from this file may be committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
