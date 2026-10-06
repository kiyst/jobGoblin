"""Phase 4 S2c: bounded, read-only Greenhouse live canary harness (ADR 0017).

One separately authorized `GET /v1/boards/discord/jobs?content=true`
through the unchanged, published S1 adapter (`declared-double-escaped`),
the S2b converter and bridge, and S2's `normalize_posting`. Nothing is
registered, wired, or persisted. The frozen contract is
`.claude/runtime/phase4-s2c-frozen-contract.md` (gitignored).

Live operation is disabled by default. A live run requires every gate
element: the `live` subcommand, `JOBGOBLIN_S2C_LIVE_CANARY=authorized-once`,
the allowlisted board, a clean checkout whose HEAD is the authorized
advisory SHA, the frozen-contract and authorization-record hashes, no
existing attempt reservation, and no existing staging directory.

Request and capture rules:

- exactly one guarded GET; any other method, host, port, path, or query,
  and any second send, is refused before network I/O;
- adapter settings: `max_attempts=1` (no retry), redirects disabled,
  `max_response_bytes=5_000_000`;
- the locked `httpx` default User-Agent is kept and recorded; the only
  request-header override is `Accept-Encoding: identity`, and a
  non-identity `Content-Encoding` is refused without fallback;
- only a complete 200 JSON identity-encoded body that reaches EOF within
  the cap receives a complete-response hash; partial, oversized,
  interrupted, or unexpectedly encoded bodies never do, and non-200 or
  rejected bodies are never drained;
- the 500-record cap is checked before adapter conversion;
- the complete body is written once, exclusive-create, to gitignored
  staging and is never logged, printed, or committed;
- a persistent attempt reservation is created and fsynced before any
  transport exists, outside staging, and blocks every later attempt;
- the complete automated live operation runs in a supervised worker
  process with one 60-second wall-clock deadline; the supervisor
  terminates, reaps, and if necessary kills it.

Every printed line and recorded outcome is categorical: no response body,
record field, exception text, or URL query ever appears in output.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import hashlib
import html
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import IO, Any, Final, Protocol

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.hashing import canonical_json_hash  # noqa: E402
from app.normalization.posting import NormalizedPosting, normalize_posting  # noqa: E402
from app.normalization.taxonomy import (  # noqa: E402
    DEFAULT_SKILLS_TAXONOMY_PATH,
    TaxonomyIndex,
    load_taxonomy,
)
from app.providers.greenhouse import (  # noqa: E402
    GreenhouseBoard,
    GreenhouseClientSettings,
    GreenhouseJobBoardProvider,
    _duplicate_identity,
    _is_json_media_type,
    _validate_record,
)
from app.providers.greenhouse_content import (  # noqa: E402
    ContentOutcome,
    convert_greenhouse_content,
)
from app.providers.greenhouse_posting_inputs import greenhouse_posting_inputs  # noqa: E402
from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult  # noqa: E402
from app.schemas.provider import SourceQuery  # noqa: E402

# ---------------------------------------------------------------------------
# Contract constants.
# ---------------------------------------------------------------------------

BOARD_TOKEN: Final = "discord"
BOARD_COMPANY: Final = "Discord"
CONTENT_MODE: Final = "declared-double-escaped"
REQUEST_SCHEME: Final = "https"
REQUEST_HOST: Final = "boards-api.greenhouse.io"
REQUEST_PATH: Final = f"/v1/boards/{BOARD_TOKEN}/jobs"
REQUEST_QUERY: Final = "content=true"
ACCEPT_ENCODING: Final = "identity"
MAX_RESPONSE_BYTES: Final = 5_000_000
MAX_SOURCE_RECORDS: Final = 500
OUTER_DEADLINE_SECONDS: Final = 60.0
TERMINATION_GRACE_SECONDS: Final = 5.0
MAX_SELECTED: Final = 3
MAX_EXCERPT_CODE_POINTS: Final = 2000
MAX_EXCERPT_UTF8_BYTES: Final = 4096
MAX_DISPLAY_CHARS: Final = 1000
LIVE_ENV_VAR: Final = "JOBGOBLIN_S2C_LIVE_CANARY"
LIVE_ENV_VALUE: Final = "authorized-once"
FIXTURE_KIND: Final = "projected_live_record_with_exact_content_excerpt"
FIXTURE_SCHEMA_VERSION: Final = 1
SUMMARY_VERSION: Final = 1
PROJECTED_FIELDS: Final = ("id", "absolute_url", "title", "location", "content")

SALARY_STATEMENT: Final = (
    "No salary-specific parameters or endpoint were requested; no salary field was "
    "extracted or composed, and the salary classifier was not invoked. Incidental "
    "compensation text may occur in captured content. The bridge supplies no compensation "
    "input; ADR 0011 L4 remains open."
)

CANARY_SETTINGS: Final = GreenhouseClientSettings(
    max_attempts=1, max_response_bytes=MAX_RESPONSE_BYTES
)


def request_fingerprint() -> str:
    """Identity of the single permitted request, bound into the reservation."""
    text = (
        f"GET {REQUEST_SCHEME}://{REQUEST_HOST}{REQUEST_PATH}?{REQUEST_QUERY} "
        f"accept-encoding={ACCEPT_ENCODING}"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanaryPaths:
    """Every filesystem location the harness touches. Tests pass temporary
    paths; only the CLI uses `LIVE_PATHS`."""

    runtime_dir: Path
    staging_dir: Path
    reservation: Path
    contract: Path
    fixture: Path
    report: Path

    @property
    def raw(self) -> Path:
        return self.staging_dir / "raw-response.bin"

    @property
    def summary(self) -> Path:
        return self.staging_dir / "run-summary.json"

    @property
    def projection_preview(self) -> Path:
        return self.staging_dir / "projection-preview.json"

    @property
    def launch(self) -> Path:
        return self.staging_dir / "worker-launch.json"

    @property
    def claim(self) -> Path:
        return self.staging_dir / "worker-claim.json"


_RUNTIME_DIR = REPO_ROOT / ".claude" / "runtime"
LIVE_PATHS: Final = CanaryPaths(
    runtime_dir=_RUNTIME_DIR,
    staging_dir=_RUNTIME_DIR / "phase4-s2c-staging",
    reservation=_RUNTIME_DIR / "phase4-s2c-attempt.jsonl",
    contract=_RUNTIME_DIR / "phase4-s2c-frozen-contract.md",
    fixture=REPO_ROOT
    / "backend"
    / "tests"
    / "fixtures"
    / "providers"
    / "greenhouse_s2c_projected.json",
    report=REPO_ROOT / "docs" / "evaluation" / "phase4-s2c-live-canary.md",
)


class Verdict(StrEnum):
    """Exactly four verdicts, in precedence order (highest first)."""

    FAIL_CLOSED = "FAIL-CLOSED"
    INCONCLUSIVE = "INCONCLUSIVE"
    PASS_WITH_FINDINGS = "PASS-WITH-FINDINGS"
    PASS = "PASS"


# Closed fidelity-review vocabulary. A committed fixture records performed
# reviews only (`faithful` or `mismatch`).
REVIEW_DISPOSITIONS: Final = frozenset({"faithful", "mismatch", "not_performed"})
PERFORMED_DISPOSITIONS: Final = frozenset({"faithful", "mismatch"})

_PRECEDENCE: Final = (
    Verdict.FAIL_CLOSED,
    Verdict.INCONCLUSIVE,
    Verdict.PASS_WITH_FINDINGS,
    Verdict.PASS,
)


class CanaryRefusal(Exception):  # noqa: N818 - a refusal, not an error report
    """A categorical refusal. `kind` is a fixed token; it never carries a
    response body, field value, exception text, or URL."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


# ---------------------------------------------------------------------------
# Content-outcome classification (contract §6).
# ---------------------------------------------------------------------------

# `not_requested` (impossible under the fixed enabled mode) and `parser_error`
# are contract failures; every other non-`converted` outcome is a finding.
FAILURE_OUTCOMES: Final = frozenset({ContentOutcome.NOT_REQUESTED, ContentOutcome.PARSER_ERROR})
FINDING_OUTCOMES: Final = frozenset(ContentOutcome) - FAILURE_OUTCOMES - {ContentOutcome.CONVERTED}

# Adapter failure kinds (`failure=<kind>` in its categorical detail).
_INCONCLUSIVE_FAILURE_KINDS: Final = frozenset({"timeout", "deadline", "connect_error"})
_ADAPTER_DETAIL_RE: Final = re.compile(r"failure=([a-z_]+) status=([0-9]+|none)")


def classify_adapter_failure(kind: str, status: int | None) -> Verdict:
    """INCONCLUSIVE for bounded upstream transients (timeouts, connectivity,
    429, 5xx); FAIL-CLOSED for everything else (redirect, other status,
    media type, transport error, oversize, invalid JSON, envelope, no usable
    records)."""
    if kind in _INCONCLUSIVE_FAILURE_KINDS:
        return Verdict.INCONCLUSIVE
    if kind == "http_status" and status is not None and (status == 429 or 500 <= status <= 599):
        return Verdict.INCONCLUSIVE
    return Verdict.FAIL_CLOSED


# ---------------------------------------------------------------------------
# Request guard and recording transport.
# ---------------------------------------------------------------------------


def check_request_shape(request: httpx.Request) -> None:
    """Refuses, before any network I/O, every request other than the one
    permitted GET."""
    url = request.url
    if (
        request.method != "GET"
        or url.scheme != REQUEST_SCHEME
        or url.host != REQUEST_HOST
        or url.port is not None
        or url.userinfo != b""
        or url.fragment != ""
        or url.raw_path != f"{REQUEST_PATH}?{REQUEST_QUERY}".encode("ascii")
    ):
        raise CanaryRefusal("request_shape_refused")


@dataclass
class Capture:
    """What the recording transport observed. `body` is held in memory only
    for in-process derivation; it is never printed or logged."""

    request_sent: bool = False
    observed_user_agent: str | None = None
    status: int | None = None
    media_type_json: bool | None = None
    complete: bool = False
    partial: bool = False
    sha256: str | None = None
    byte_count: int | None = None
    source_record_count: int | None = None
    source_meta_total: int | None = None
    body: bytes | None = None


def exclusive_write(path: Path, data: bytes) -> None:
    """Create-only write with fsync; an existing path is never overwritten."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0))
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class RecordingTransport(httpx.AsyncBaseTransport):
    """Non-mutating recording wrapper around one inner transport.

    It refuses any request but the permitted one and any second send, sets
    `Accept-Encoding: identity` (the sole header override), records the
    observed User-Agent, buffers a bounded successful JSON body, hashes and
    stores it create-only, enforces the record cap, and then exposes the
    identical bytes to the unchanged adapter."""

    def __init__(self, inner: httpx.AsyncBaseTransport, capture: Capture, raw_path: Path) -> None:
        self._inner = inner
        self._capture = capture
        self._raw_path = raw_path

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._capture.request_sent:
            raise CanaryRefusal("second_request_refused")
        check_request_shape(request)
        request.headers["Accept-Encoding"] = ACCEPT_ENCODING
        self._capture.observed_user_agent = request.headers.get("user-agent")
        self._capture.request_sent = True
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
                raise CanaryRefusal("unexpected_content_encoding")
            body = await self._read_bounded(response)
        finally:
            await response.aclose()
        self._record_complete(body)
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
        try:
            async for chunk in response.aiter_raw():
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise CanaryRefusal("response_cap_exceeded")
                chunks.append(chunk)
        except BaseException:
            self._capture.partial = True
            raise
        return b"".join(chunks)

    def _record_complete(self, body: bytes) -> None:
        capture = self._capture
        capture.complete = True
        capture.body = body
        capture.byte_count = len(body)
        capture.sha256 = hashlib.sha256(body).hexdigest()
        exclusive_write(self._raw_path, body)
        try:
            envelope = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):
            return  # the adapter reports invalid_json
        if not isinstance(envelope, dict) or not isinstance(envelope.get("jobs"), list):
            return  # the adapter reports envelope
        capture.source_record_count = len(envelope["jobs"])
        meta = envelope.get("meta")
        if isinstance(meta, dict) and _strict_int(meta.get("total")):
            capture.source_meta_total = meta["total"]
        if capture.source_record_count > MAX_SOURCE_RECORDS:
            raise CanaryRefusal("record_cap_exceeded")

    async def aclose(self) -> None:
        await self._inner.aclose()


# ---------------------------------------------------------------------------
# Serialization of normalization results (golden values and aggregates).
# ---------------------------------------------------------------------------


def to_jsonable(value: Any) -> Any:
    """Deterministic JSON form of dataclass/enum/tuple results."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, tuple | list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    return value


def normalized_summary(normalized: NormalizedPosting) -> dict[str, Any]:
    """Every composed component except `inputs` (recorded separately)."""
    summary = to_jsonable(normalized)
    assert isinstance(summary, dict)
    summary.pop("inputs")
    return summary


_COMPONENTS: Final[tuple[tuple[str, Callable[[NormalizedPosting], object]], ...]] = (
    ("title", lambda n: n.title.canonical_title.value),
    ("remote_type", lambda n: n.remote_type.value),
    ("employment_type", lambda n: n.employment_type.value),
    ("seniority", lambda n: n.seniority.value),
    ("experience.minimum", lambda n: n.experience.minimum.value),
    ("experience.maximum", lambda n: n.experience.maximum.value),
    ("location.city", lambda n: n.location.city.value),
    ("location.state", lambda n: n.location.state.value),
    ("location.country", lambda n: n.location.country.value),
    ("location.postal_code", lambda n: n.location.postal_code.value),
)


def component_counts(results: Sequence[NormalizedPosting]) -> dict[str, int]:
    """Non-abstention counts per component, plus skills totals."""
    counts = {name: sum(1 for n in results if get(n) is not None) for name, get in _COMPONENTS}
    counts["skills.jobs_with_match"] = sum(1 for n in results if n.skills)
    counts["skills.matches"] = sum(len(n.skills) for n in results)
    return counts


# ---------------------------------------------------------------------------
# The live pipeline (runs inside the supervised worker).
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _outcome_counts(outcomes: Sequence[ContentOutcome]) -> dict[str, int]:
    counter = Counter(outcomes)
    return {outcome.value: counter.get(outcome, 0) for outcome in ContentOutcome}


def _content_warning_counts(warnings: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for warning in warnings:
        match = re.fullmatch(r"greenhouse content_unconverted=([a-z_]+) count=([0-9]+)", warning)
        if match:
            counts[match.group(1)] = int(match.group(2))
    return counts


def _completeness(warnings: Sequence[str], meta_total: int | None) -> str:
    for warning in warnings:
        match = re.fullmatch(
            rf"greenhouse board={BOARD_TOKEN} completeness_evidence=(malformed|mismatch)", warning
        )
        if match:
            return match.group(1)
    return "consistent" if meta_total is not None else "no_claim"


def _base_summary(capture: Capture, captured_at: str) -> dict[str, Any]:
    return {
        "summary_version": SUMMARY_VERSION,
        "board_token": BOARD_TOKEN,
        "request_path": REQUEST_PATH,
        "request_query": REQUEST_QUERY,
        "accept_encoding": ACCEPT_ENCODING,
        "observed_user_agent": capture.observed_user_agent,
        "captured_at": captured_at,
        "http_status": capture.status,
        "media_type_json": capture.media_type_json,
        "capture": {
            "complete": capture.complete,
            "partial": capture.partial,
            "complete_response_sha256": capture.sha256 if capture.complete else None,
            "complete_response_bytes": capture.byte_count if capture.complete else None,
        },
        "source_record_count": capture.source_record_count,
        "source_meta_total": capture.source_meta_total,
        "run_verdict": None,
        "run_kind": None,
        "findings": [],
        "aggregate": None,
        "component_counts": None,
        "records": [],
    }


def _stop(summary: dict[str, Any], verdict: Verdict, kind: str) -> dict[str, Any]:
    summary["run_verdict"] = verdict.value
    summary["run_kind"] = kind
    return summary


async def run_canary_pipeline(
    inner_factory: Callable[[], httpx.AsyncBaseTransport],
    raw_path: Path,
    taxonomy: TaxonomyIndex,
) -> dict[str, Any]:
    """One request through adapter -> converter -> bridge -> composition.

    Returns the categorical run summary. `run_verdict` is `FAIL-CLOSED` or
    `INCONCLUSIVE` when the run itself settles the verdict, otherwise `None`
    (observations pending post-run review)."""
    capture = Capture()
    provider = GreenhouseJobBoardProvider(
        [GreenhouseBoard(BOARD_TOKEN, BOARD_COMPANY, CONTENT_MODE)],
        settings=CANARY_SETTINGS,
        transport_factory=lambda: RecordingTransport(inner_factory(), capture, raw_path),
    )
    captured_at = _now_iso()
    try:
        result = await provider.discover(SourceQuery(sources=["greenhouse"]))
    except CanaryRefusal as refusal:
        return _stop(_base_summary(capture, captured_at), Verdict.FAIL_CLOSED, refusal.kind)
    summary = _base_summary(capture, captured_at)
    return _evaluate_result(summary, capture, result, taxonomy)


def _evaluate_result(
    summary: dict[str, Any],
    capture: Capture,
    result: DiscoveryResult,
    taxonomy: TaxonomyIndex,
) -> dict[str, Any]:
    for error in result.errors:
        match = _ADAPTER_DETAIL_RE.search(error.detail or "")
        if match:
            status = None if match.group(2) == "none" else int(match.group(2))
            kind = match.group(1)
            label = f"{kind}:{status}" if status is not None else kind
            return _stop(summary, classify_adapter_failure(kind, status), label)
    if capture.body is None or not capture.complete:
        return _stop(summary, Verdict.FAIL_CLOSED, "capture_incomplete")
    records = json.loads(capture.body.decode("utf-8"))["jobs"]
    if not records:
        return _stop(summary, Verdict.INCONCLUSIVE, "empty_board")

    # Diagnostic reconstruction with the adapter's own validators, cross-checked
    # against the adapter's result (no conversion logic is duplicated).
    valid = {i: v for i, rec in enumerate(records) if (v := _validate_record(rec)) is not None}
    identities = Counter(_duplicate_identity(v.job_id) for v in valid.values())
    retained = [i for i, v in valid.items() if identities[_duplicate_identity(v.job_id)] == 1]
    duplicates = len(valid) - len(retained)
    if len(retained) != len(result.jobs) or any(
        job.raw != records[i] for job, i in zip(result.jobs, retained, strict=False)
    ):
        return _stop(summary, Verdict.FAIL_CLOSED, "lineage_mismatch")

    outcomes: list[ContentOutcome] = []
    normalized: list[NormalizedPosting] = []
    rows: dict[int, dict[str, Any]] = {}
    for i, job in zip(retained, result.jobs, strict=True):
        conversion = convert_greenhouse_content(records[i].get("content"), mode=CONTENT_MODE)
        if conversion.text != job.description:
            return _stop(summary, Verdict.FAIL_CLOSED, "lineage_mismatch")
        outcomes.append(conversion.outcome)
        try:
            normalized.append(_normalize(job, taxonomy))
        except Exception:  # categorical: a suspected defect in merged S2/S2b code
            return _stop(summary, Verdict.FAIL_CLOSED, "bridge_or_normalization_exception")
        rows[i] = {
            "content_outcome": conversion.outcome.value,
            "description_code_points": len(job.description) if job.description else 0,
        }

    failures = [o for o in outcomes if o in FAILURE_OUTCOMES]
    if failures:
        return _stop(summary, Verdict.FAIL_CLOSED, f"content_outcome:{failures[0].value}")
    outcome_counts = _outcome_counts(outcomes)
    unconverted = {k: v for k, v in outcome_counts.items() if v and k != "converted"}
    if unconverted != _content_warning_counts(result.warnings):
        return _stop(summary, Verdict.FAIL_CLOSED, "lineage_mismatch")

    stats = result.source_stats[0]
    summary["aggregate"] = {
        "valid_count": len(valid),
        "invalid_count": len(records) - len(valid),
        "retained_count": len(retained),
        "skipped_count": len(records) - len(retained),
        "duplicate_count": duplicates,
        "completeness_disposition": _completeness(result.warnings, capture.source_meta_total),
        "conversion_outcomes": outcome_counts,
        "incomplete_results": stats.incomplete_results,
        "source_completed": stats.completed,
    }
    summary["component_counts"] = component_counts(normalized)
    summary["records"] = [
        {
            "source_ordinal": i,
            "disposition": (
                "retained" if i in rows else ("duplicate" if i in valid else "invalid")
            ),
            **rows.get(i, {"content_outcome": None, "description_code_points": None}),
        }
        for i in range(len(records))
    ]
    summary["findings"] = run_findings(summary)
    return summary


def _normalize(job: DiscoveredJob, taxonomy: TaxonomyIndex) -> NormalizedPosting:
    return normalize_posting(greenhouse_posting_inputs(job), taxonomy=taxonomy)


def run_findings(summary: Mapping[str, Any]) -> list[str]:
    """Categorical findings from a completed run; any finding prevents PASS."""
    aggregate = summary["aggregate"]
    findings = [
        f"content_outcome:{name}"
        for name, count in sorted(aggregate["conversion_outcomes"].items())
        if count and ContentOutcome(name) in FINDING_OUTCOMES
    ]
    if aggregate["invalid_count"]:
        findings.append("skipped_invalid_records")
    if aggregate["duplicate_count"]:
        findings.append("skipped_duplicate_records")
    if aggregate["completeness_disposition"] in ("malformed", "mismatch"):
        findings.append(f"completeness:{aggregate['completeness_disposition']}")
    if aggregate["incomplete_results"]:
        findings.append("incomplete_results")
    return findings


# ---------------------------------------------------------------------------
# Verdict.
# ---------------------------------------------------------------------------


def compute_verdict(
    summary: Mapping[str, Any],
    selected: Sequence[Mapping[str, Any]] | None,
    *,
    cleanup_passed: bool | None = None,
) -> tuple[Verdict, list[str]]:
    """Final verdict with strict precedence. `selected` is the fixture's
    reviewed selection (`None` when no fidelity review was performed).

    Both fidelity dispositions must come from the closed vocabulary; either
    one unavailable (`not_performed`) caps the verdict at INCONCLUSIVE, and
    PASS requires both to be `faithful`."""
    reasons: dict[Verdict, list[str]] = {verdict: [] for verdict in Verdict}
    if summary.get("run_verdict") is not None:
        reasons[Verdict(summary["run_verdict"])].append(str(summary["run_kind"]))
    if cleanup_passed is False:
        reasons[Verdict.FAIL_CLOSED].append("cleanup_failed")
    if summary.get("run_verdict") is None:
        reasons[Verdict.PASS_WITH_FINDINGS].extend(summary.get("findings", []))
        if selected is None:
            reasons[Verdict.INCONCLUSIVE].append("fidelity_review_unavailable")
        else:
            dispositions = [
                entry.get("review", {}).get(field)
                for entry in selected
                for field in (
                    "full_capture_fidelity_disposition",
                    "excerpt_replay_disposition",
                )
            ]
            if not all(isinstance(d, str) and d in REVIEW_DISPOSITIONS for d in dispositions):
                reasons[Verdict.FAIL_CLOSED].append("review_disposition_invalid")
            if "not_performed" in dispositions:
                reasons[Verdict.INCONCLUSIVE].append("fidelity_review_unavailable")
            if "mismatch" in dispositions:
                reasons[Verdict.PASS_WITH_FINDINGS].append("fidelity_mismatch")
            if not any(
                entry["golden_expectations"]["content_outcome"] == ContentOutcome.CONVERTED.value
                and entry["selection_reason"] == "first_converted"
                for entry in selected
            ):
                reasons[Verdict.PASS_WITH_FINDINGS].append("no_safe_converted_sample")
    for verdict in _PRECEDENCE:
        if reasons[verdict]:
            return verdict, reasons[verdict]
    return Verdict.PASS, []


# ---------------------------------------------------------------------------
# Attempt reservation, launch capability, and supervised worker.
# ---------------------------------------------------------------------------


def create_reservation(path: Path, record: Mapping[str, Any]) -> IO[bytes]:
    """Exclusively create the reservation and fsync its first record before
    any transport exists. Returns the open handle for the single terminal
    append. An existing reservation is never reset."""
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND | getattr(os, "O_BINARY", 0),
        )
    except FileExistsError as exc:
        raise CanaryRefusal("attempt_already_reserved") from exc
    handle = os.fdopen(fd, "ab")
    handle.write((json.dumps(dict(record), sort_keys=True) + "\n").encode("utf-8"))
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def append_terminal_outcome(handle: IO[bytes], outcome: str) -> None:
    line = {"event": "terminal", "outcome": outcome, "recorded_at": _now_iso()}
    handle.write((json.dumps(line, sort_keys=True) + "\n").encode("utf-8"))
    handle.flush()
    os.fsync(handle.fileno())
    handle.close()


_BOUND_RESERVATION_FIELDS: Final = (
    "board_token",
    "advisory_sha",
    "contract_sha256",
    "request_fingerprint",
    "authorization_identity",
    "authorization_sha256",
)


def launch_capability(reservation_line: bytes, token: str) -> dict[str, Any]:
    """The one-time supervisor launch capability: bound to the exact checked
    reservation line and to the hash of a secret token that only the
    supervisor holds and passes to its own worker over the stdin pipe."""
    record = json.loads(reservation_line.decode("utf-8"))
    if not isinstance(record, dict) or record.get("event") != "reserved":
        raise CanaryRefusal("reservation_invalid")
    capability = {key: record.get(key) for key in _BOUND_RESERVATION_FIELDS}
    capability["reservation_sha256"] = hashlib.sha256(reservation_line).hexdigest()
    capability["token_sha256"] = hashlib.sha256(token.encode("ascii")).hexdigest()
    return capability


def claim_worker(paths: CanaryPaths, token: str) -> None:
    """Validate the supervisor's launch capability against the open
    reservation and atomically claim the single worker slot, before any
    transport exists. A direct invocation, a missing or mismatched
    capability, a reservation that already has a terminal outcome, crash
    residue, a concurrent or duplicate launch, and a restart after the
    request began are all refused."""
    if not isinstance(token, str) or not _SHA256_RE.fullmatch(token):
        raise CanaryRefusal("worker_token_invalid")
    if not paths.staging_dir.is_dir() or not paths.reservation.is_file():
        raise CanaryRefusal("worker_state_missing")
    lines = paths.reservation.read_bytes().splitlines(keepends=True)
    if len(lines) != 1:
        raise CanaryRefusal("reservation_not_open")
    try:
        launch = json.loads(paths.launch.read_text(encoding="utf-8"))
        expected = launch_capability(lines[0], token)
    except (OSError, ValueError):
        raise CanaryRefusal("launch_capability_invalid") from None
    if (
        launch != expected
        or expected["board_token"] != BOARD_TOKEN
        or expected["request_fingerprint"] != request_fingerprint()
    ):
        raise CanaryRefusal("launch_capability_invalid")
    for path in (paths.claim, paths.raw, paths.summary):
        if os.path.lexists(path):
            raise CanaryRefusal("worker_already_claimed")
    claim = {"token_sha256": expected["token_sha256"], "claimed_at": _now_iso()}
    try:
        exclusive_write(paths.claim, json.dumps(claim, sort_keys=True).encode("utf-8"))
    except FileExistsError:
        raise CanaryRefusal("worker_already_claimed") from None


@dataclass(frozen=True)
class WorkerResult:
    # "exited" | "deadline_terminated" | "termination_unconfirmed" | "containment_failed"
    kind: str
    returncode: int | None


class SupervisionAborted(Exception):  # noqa: N818 - a categorical abort, not an error report
    """Supervision ended abnormally after launch (interrupt or supervision
    failure). The worker has already been stopped and reaped when
    `confirmed` is true."""

    def __init__(self, confirmed: bool) -> None:
        super().__init__("supervision_aborted")
        self.confirmed = confirmed


# ---------------------------------------------------------------------------
# Operating-system parent-loss containment (Windows Job Object).
# ---------------------------------------------------------------------------

_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: Final = 9
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Final = 0x2000
_PROCESS_TERMINATE: Final = 0x0001
_PROCESS_SET_QUOTA: Final = 0x0100
_PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
_STILL_ACTIVE: Final = 259
_ERROR_INVALID_PARAMETER: Final = 87


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kernel32() -> Any:
    """kernel32 with exact signatures. The supported execution platform is
    Windows; anything else refuses containment."""
    if sys.platform != "win32":
        raise CanaryRefusal("containment_unavailable")
    from ctypes import wintypes

    k = ctypes.WinDLL("kernel32", use_last_error=True)
    handle, dword, boolean, pointer = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.BOOL,
        ctypes.c_void_p,
    )
    k.CreateJobObjectW.argtypes, k.CreateJobObjectW.restype = [pointer, wintypes.LPCWSTR], handle
    k.SetInformationJobObject.argtypes = [handle, ctypes.c_int, pointer, dword]
    k.SetInformationJobObject.restype = boolean
    k.QueryInformationJobObject.argtypes = [handle, ctypes.c_int, pointer, dword, pointer]
    k.QueryInformationJobObject.restype = boolean
    k.AssignProcessToJobObject.argtypes, k.AssignProcessToJobObject.restype = (
        [handle, handle],
        boolean,
    )
    k.IsProcessInJob.argtypes = [handle, handle, ctypes.POINTER(boolean)]
    k.IsProcessInJob.restype = boolean
    k.OpenProcess.argtypes, k.OpenProcess.restype = [dword, boolean, dword], handle
    k.GetExitCodeProcess.argtypes = [handle, ctypes.POINTER(dword)]
    k.GetExitCodeProcess.restype = boolean
    k.CloseHandle.argtypes, k.CloseHandle.restype = [handle], boolean
    return k


def _kills_on_close(k: Any, job: Any) -> bool:
    """Reads back the job's limits (`job=None`: the calling process's job)."""
    info = _ExtendedLimitInformation()
    ok = k.QueryInformationJobObject(
        job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info), None
    )
    flags = info.BasicLimitInformation.LimitFlags
    return bool(ok) and bool(flags & _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)


class KillOnCloseJob:
    """Supervisor-owned, non-inheritable Windows Job Object with
    `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, verified by reading it back. When the
    supervisor's handle closes, including on supervisor crash or kill, the
    kernel terminates every assigned process without involving the worker's
    interpreter, threads, event loop, or GIL. Any setup failure is the
    categorical refusal `containment_unavailable`."""

    def __init__(self) -> None:
        self._k = _kernel32()
        self._handle: Any = self._k.CreateJobObjectW(None, None)
        if not self._handle:
            raise CanaryRefusal("containment_unavailable")
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = self._k.SetInformationJobObject(
            self._handle,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not configured or not _kills_on_close(self._k, self._handle):
            self.close()
            raise CanaryRefusal("containment_unavailable")

    def assign(self, pid: int) -> None:
        """Assign the worker and confirm membership; `containment_assignment_failed`
        otherwise."""
        k = self._k
        access = _PROCESS_SET_QUOTA | _PROCESS_TERMINATE | _PROCESS_QUERY_LIMITED_INFORMATION
        process = k.OpenProcess(access, False, pid)
        if not process:
            raise CanaryRefusal("containment_assignment_failed")
        try:
            from ctypes import wintypes

            inside = wintypes.BOOL(False)
            if (
                not k.AssignProcessToJobObject(self._handle, process)
                or not k.IsProcessInJob(process, self._handle, ctypes.byref(inside))
                or not inside.value
            ):
                raise CanaryRefusal("containment_assignment_failed")
        finally:
            k.CloseHandle(process)

    def close(self) -> None:
        """Closing the only handle terminates any process still assigned."""
        if self._handle:
            self._k.CloseHandle(self._handle)
            self._handle = None


def current_process_kill_on_close() -> bool:
    """Worker-side defense in depth: the calling process is inside a job with
    kill-on-close. The supervisor's assignment remains the guarantee."""
    try:
        return _kills_on_close(_kernel32(), None)
    except CanaryRefusal:
        return False


def process_has_exited(pid: int) -> bool | None:
    """Independent OS evidence: True (exited or no such process), False
    (still active), or None (state cannot be established)."""
    try:
        k = _kernel32()
    except CanaryRefusal:
        return None
    process = k.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not process:
        return True if ctypes.get_last_error() == _ERROR_INVALID_PARAMETER else None
    try:
        from ctypes import wintypes

        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(process, ctypes.byref(code)):
            return None
        return code.value != _STILL_ACTIVE
    finally:
        k.CloseHandle(process)


class Containment(Protocol):
    def assign(self, pid: int) -> None: ...

    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Supervised worker.
# ---------------------------------------------------------------------------


def _confirmed_exit(process: Any) -> bool:
    """Death is confirmed only by evidence: the reaped return code, or the
    operating system's process state."""
    try:
        if process.poll() is not None:
            return True
    except BaseException:  # fall through to the independent OS query
        pass
    try:
        return process_has_exited(int(process.pid)) is True
    except BaseException:  # no evidence means unconfirmed
        return False


def _stop_and_reap(process: Any, grace_seconds: float) -> tuple[bool, bool]:
    """Terminate, then kill; reap and confirm after each step. Failures and
    interruptions inside the shutdown sequence never skip escalation or
    confirmation. Returns `(confirmed, interrupted)`."""
    interrupted = False
    for stop in (process.terminate, process.kill):
        try:
            stop()
        except KeyboardInterrupt:
            interrupted = True
        except BaseException:  # escalation continues; confirmed below
            pass
        try:
            process.wait(timeout=grace_seconds)
        except KeyboardInterrupt:
            interrupted = True
        except BaseException:  # a failed wait never ends shutdown
            pass
        if _confirmed_exit(process):
            return True, interrupted
    return _confirmed_exit(process), interrupted


def supervise_worker(
    argv: Sequence[str],
    *,
    deadline_seconds: float = OUTER_DEADLINE_SECONDS,
    grace_seconds: float = TERMINATION_GRACE_SECONDS,
    env: Mapping[str, str] | None = None,
    stdin_payload: bytes | None = None,
    containment: Containment | None = None,
) -> WorkerResult:
    """Run the worker with one wall-clock deadline that starts immediately
    before launch.

    A launch token (`stdin_payload`) is released only after the worker has
    been assigned to `containment`; without containment no token is released
    at all. A failed assignment stops the worker before any token exists.
    At the deadline, and on any abnormal supervisor exit after launch, the
    worker is terminated, escalated to kill, and confirmed dead by evidence;
    otherwise the result is `termination_unconfirmed`. An interruption during
    shutdown is honoured (as `SupervisionAborted`) only after shutdown was
    attempted."""
    if stdin_payload is not None and containment is None:
        raise CanaryRefusal("containment_required")
    start = time.monotonic()
    process = subprocess.Popen(  # fixed argv, no shell
        list(argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(env) if env is not None else None,
    )
    try:
        try:
            if containment is not None:
                try:
                    containment.assign(process.pid)
                except CanaryRefusal:
                    confirmed, interrupted = _stop_and_reap(process, grace_seconds)
                    if interrupted:
                        raise SupervisionAborted(confirmed) from None
                    kind = "containment_failed" if confirmed else "termination_unconfirmed"
                    return WorkerResult(kind, None)
            if stdin_payload is not None and process.stdin is not None:
                try:
                    process.stdin.write(stdin_payload)
                    process.stdin.flush()
                except OSError:
                    pass  # the worker already exited; its result is reaped below
            remaining = max(0.0, deadline_seconds - (time.monotonic() - start))
            returncode = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            confirmed, interrupted = _stop_and_reap(process, grace_seconds)
            if interrupted:
                raise SupervisionAborted(confirmed) from None
            if confirmed:
                return WorkerResult("deadline_terminated", process.returncode)
            return WorkerResult("termination_unconfirmed", None)
        return WorkerResult("exited", returncode)
    except SupervisionAborted:
        raise
    except BaseException:
        raise SupervisionAborted(_stop_and_reap(process, grace_seconds)[0]) from None
    finally:
        if process.stdin is not None:
            with contextlib.suppress(OSError):
                process.stdin.close()


PARENT_LOST_EXIT: Final = 75
_TOKEN_LINE_LIMIT: Final = 128


def _hard_exit() -> None:
    os._exit(PARENT_LOST_EXIT)


def start_parent_loss_watchdog(
    stream: IO[bytes], on_lost: Callable[[], None] = _hard_exit
) -> threading.Thread:
    """Defense in depth only (it needs this interpreter to stay responsive):
    ends the worker when the supervisor's end of the stdin pipe closes. The
    containment guarantee is the supervisor's kill-on-close Job Object."""

    def watch() -> None:
        while stream.read(1):
            pass
        on_lost()

    thread = threading.Thread(target=watch, name="s2c-parent-loss", daemon=True)
    thread.start()
    return thread


def worker_main(
    paths: CanaryPaths,
    *,
    env: Mapping[str, str],
    token: str,
    in_containment: Callable[[], bool] = current_process_kill_on_close,
) -> int:
    """The supervised worker: confirms it runs inside a kill-on-close job,
    claims the single worker slot under the supervisor's launch capability,
    performs the one request and all automated processing, and writes the
    categorical summary. Spawns no process and prints nothing."""
    if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE:
        return 3
    if not in_containment():
        return 3
    try:
        claim_worker(paths, token)
    except CanaryRefusal:
        return 3
    try:
        taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
        summary = asyncio.run(run_canary_pipeline(httpx.AsyncHTTPTransport, paths.raw, taxonomy))
    except Exception as exc:  # categorical: the class name only
        summary = _stop(
            _base_summary(Capture(), _now_iso()),
            Verdict.FAIL_CLOSED,
            f"harness_exception:{type(exc).__name__}",
        )
    exclusive_write(paths.summary, json.dumps(summary, indent=2, sort_keys=True).encode("utf-8"))
    return 0


def worker_entry(paths: CanaryPaths, stdin: Any) -> int:
    """`_worker` CLI entry: blocks for the supervisor's token, which is only
    released after kernel containment is in place, arms the defense-in-depth
    watchdog, then runs the worker. An interactive stdin can never carry a
    supervisor launch."""
    if stdin.isatty():
        return 3
    token = stdin.buffer.readline(_TOKEN_LINE_LIMIT).decode("ascii", "replace").strip()
    start_parent_loss_watchdog(stdin.buffer)
    return worker_main(paths, env=os.environ, token=token)


# ---------------------------------------------------------------------------
# Live preflight and supervisor command.
# ---------------------------------------------------------------------------

_SHA_RE: Final = re.compile(r"[0-9a-f]{40}")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")


def git_output(args: Sequence[str]) -> str:
    completed = subprocess.run(  # fixed argv, no shell
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return completed.stdout


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class LiveRequest:
    board: str
    expected_sha: str
    contract_sha256: str
    authorization_file: Path
    authorization_sha256: str


def live_preflight(
    request: LiveRequest,
    *,
    env: Mapping[str, str],
    paths: CanaryPaths,
    head_sha: Callable[[], str],
    tree_is_clean: Callable[[], bool],
) -> dict[str, Any]:
    """Every gate element, checked before any reservation or transport.
    Returns the reservation record; raises `CanaryRefusal` otherwise."""
    if env.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE:
        raise CanaryRefusal("gate_disabled")
    if request.board != BOARD_TOKEN:
        raise CanaryRefusal("board_not_allowlisted")
    if not _SHA_RE.fullmatch(request.expected_sha) or head_sha() != request.expected_sha:
        raise CanaryRefusal("sha_mismatch")
    if not tree_is_clean():
        raise CanaryRefusal("dirty_tree")
    if not paths.contract.is_file() or file_sha256(paths.contract) != request.contract_sha256:
        raise CanaryRefusal("contract_mismatch")
    if (
        not _SHA256_RE.fullmatch(request.authorization_sha256)
        or not request.authorization_file.is_file()
        or file_sha256(request.authorization_file) != request.authorization_sha256
    ):
        raise CanaryRefusal("authorization_mismatch")
    if os.path.lexists(paths.reservation):
        raise CanaryRefusal("attempt_already_reserved")
    if os.path.lexists(paths.staging_dir):
        raise CanaryRefusal("staging_exists")
    try:
        load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
    except Exception as exc:
        raise CanaryRefusal("taxonomy_load_failed") from exc
    return {
        "event": "reserved",
        "outcome": "reserved",
        "board_token": BOARD_TOKEN,
        "advisory_sha": request.expected_sha,
        "contract_sha256": request.contract_sha256,
        "request_fingerprint": request_fingerprint(),
        "authorization_identity": request.authorization_file.name,
        "authorization_sha256": request.authorization_sha256,
        "reserved_at": _now_iso(),
    }


def run_live(
    request: LiveRequest,
    *,
    env: Mapping[str, str],
    paths: CanaryPaths,
    head_sha: Callable[[], str],
    tree_is_clean: Callable[[], bool],
    worker_argv: Sequence[str],
    deadline_seconds: float = OUTER_DEADLINE_SECONDS,
    containment_factory: Callable[[], Containment] = KillOnCloseJob,
) -> str:
    """Preflight, establish kernel containment, reserve, stage, issue the
    one-time launch capability, supervise, and record one terminal outcome
    after the worker is reaped. Unsupported or failed containment setup
    refuses before the reservation exists. Returns the categorical terminal
    outcome."""
    record = live_preflight(
        request, env=env, paths=paths, head_sha=head_sha, tree_is_clean=tree_is_clean
    )
    containment = containment_factory()
    try:
        return _reserve_and_supervise(
            record,
            containment,
            env=env,
            paths=paths,
            worker_argv=worker_argv,
            deadline_seconds=deadline_seconds,
        )
    finally:
        containment.close()


def _reserve_and_supervise(
    record: Mapping[str, Any],
    containment: Containment,
    *,
    env: Mapping[str, str],
    paths: CanaryPaths,
    worker_argv: Sequence[str],
    deadline_seconds: float,
) -> str:
    handle = create_reservation(paths.reservation, record)
    try:
        try:
            os.mkdir(paths.staging_dir)
        except FileExistsError:
            append_terminal_outcome(handle, f"{Verdict.FAIL_CLOSED.value}:staging_exists")
            raise CanaryRefusal("staging_exists") from None
        token = secrets.token_hex(32)
        reservation_line = paths.reservation.read_bytes().splitlines(keepends=True)[0]
        capability = launch_capability(reservation_line, token)
        exclusive_write(paths.launch, json.dumps(capability, sort_keys=True).encode("utf-8"))
        worker = supervise_worker(
            worker_argv,
            deadline_seconds=deadline_seconds,
            env=env,
            stdin_payload=(token + "\n").encode("ascii"),
            containment=containment,
        )
        if worker.kind == "containment_failed":
            outcome = f"{Verdict.FAIL_CLOSED.value}:containment_assignment_failed"
        elif worker.kind == "termination_unconfirmed":
            outcome = f"{Verdict.FAIL_CLOSED.value}:worker_termination_unconfirmed"
        elif worker.kind == "deadline_terminated":
            outcome = f"{Verdict.FAIL_CLOSED.value}:outer_deadline"
        elif worker.returncode != 0 or not paths.summary.is_file():
            outcome = f"{Verdict.FAIL_CLOSED.value}:worker_failed"
        else:
            summary = json.loads(paths.summary.read_text(encoding="utf-8"))
            if summary["run_verdict"] is None:
                outcome = "OBSERVED:pending_post_run_review"
            else:
                outcome = f"{summary['run_verdict']}:{summary['run_kind']}"
    except CanaryRefusal:
        raise
    except SupervisionAborted as aborted:
        kind = "supervisor_interrupted" if aborted.confirmed else "worker_termination_unconfirmed"
        append_terminal_outcome(handle, f"{Verdict.FAIL_CLOSED.value}:{kind}")
        raise
    except BaseException:
        append_terminal_outcome(handle, f"{Verdict.FAIL_CLOSED.value}:supervisor_exception")
        raise
    append_terminal_outcome(handle, outcome)
    return outcome


# ---------------------------------------------------------------------------
# Post-run: publication screening, selection, projection, fixture.
# ---------------------------------------------------------------------------

_EMAIL_RE: Final = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE: Final = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)|\d{2,4})[\s.-]\d{3,4}[\s.-]\d{3,4}"
)
_SCHEME_RE: Final = re.compile(r"\b(?:mailto|tel):", re.IGNORECASE)
_PROFILE_RE: Final = re.compile(
    r"(?:linkedin\.com/(?:in|pub)/|twitter\.com/|(?<![a-z0-9])x\.com/|facebook\.com/|instagram\.com/)",
    re.IGNORECASE,
)


def screening_hits(value: str, *, phone: bool = True) -> list[str]:
    """Defense-in-depth screening, never a guarantee. Runs on the value, its
    once- and twice-unescaped forms; a hit makes a record ineligible for
    publication (it is never redacted)."""
    hits: set[str] = set()
    once = html.unescape(value)
    for form in (value, once, html.unescape(once)):
        if _EMAIL_RE.search(form):
            hits.add("email")
        if phone and _PHONE_RE.search(form):
            hits.add("phone")
        if _SCHEME_RE.search(form):
            hits.add("mailto_or_tel")
        if _PROFILE_RE.search(form):
            hits.add("profile_url")
    return sorted(hits)


def _field_state(record: Mapping[str, Any], key: str) -> Any:
    return record.get(key, _MISSING)


class _Missing:
    pass


_MISSING: Final = _Missing()


def _location_name(record: Mapping[str, Any]) -> Any:
    location = record.get("location", _MISSING)
    if isinstance(location, dict):
        return location.get("name", _MISSING)
    return _MISSING if location is _MISSING else location


def _text_hash(value: Any) -> dict[str, Any]:
    if value is _MISSING:
        return {"state": "missing"}
    if value is None:
        return {"state": "null"}
    if not isinstance(value, str):
        return {"state": "non_string"}
    data = value.encode("utf-8")
    return {"state": "string", "sha256": hashlib.sha256(data).hexdigest(), "utf8_bytes": len(data)}


def project_record(record: Mapping[str, Any], excerpt: tuple[int, int] | None) -> dict[str, Any]:
    """The exact five-field projection. Missing versus explicit null is
    preserved; `location` keeps only `name`; string `content` is replaced by
    the exact contiguous excerpt `[start, end)`."""
    projected: dict[str, Any] = {}
    for key in ("id", "absolute_url", "title"):
        if key in record:
            projected[key] = record[key]
    if "location" in record:
        location = record["location"]
        if isinstance(location, dict):
            projected["location"] = {"name": location["name"]} if "name" in location else {}
        else:
            projected["location"] = location
    if "content" in record:
        content = record["content"]
        if isinstance(content, str):
            if excerpt is None:
                raise CanaryRefusal("excerpt_required")
            start, end = excerpt
            projected["content"] = content[start:end]
        else:
            if excerpt is not None:
                raise CanaryRefusal("excerpt_not_applicable")
            projected["content"] = content
    elif excerpt is not None:
        raise CanaryRefusal("excerpt_not_applicable")
    return projected


def check_excerpt_bounds(content: str, start: int, end: int) -> None:
    if not (_strict_int(start) and _strict_int(end) and 0 <= start <= end <= len(content)):
        raise CanaryRefusal("excerpt_offsets_invalid")
    if start == 0 and end == len(content):
        # C16: a complete source description is never committed, however short.
        raise CanaryRefusal("excerpt_is_complete_source")
    excerpt = content[start:end]
    if len(excerpt) > MAX_EXCERPT_CODE_POINTS:
        raise CanaryRefusal("excerpt_code_point_cap")
    try:
        encoded = excerpt.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise CanaryRefusal("excerpt_not_utf8_encodable") from exc
    if len(encoded) > MAX_EXCERPT_UTF8_BYTES:
        raise CanaryRefusal("excerpt_utf8_byte_cap")


def published_screening(projected: Mapping[str, Any], description: str | None) -> list[str]:
    """Screens every published value of a projected record."""
    hits: set[str] = set()
    for key in ("title", "content"):
        if isinstance(projected.get(key), str):
            hits.update(screening_hits(projected[key]))
    location = projected.get("location")
    if isinstance(location, dict) and isinstance(location.get("name"), str):
        hits.update(screening_hits(location["name"]))
    if isinstance(projected.get("absolute_url"), str):
        hits.update(screening_hits(projected["absolute_url"], phone=False))
    if description is not None:
        hits.update(screening_hits(description))
    return sorted(hits)


def expected_selection(
    rows: Sequence[Mapping[str, Any]], rejected: frozenset[int], limit: int = MAX_SELECTED
) -> list[tuple[int, str]]:
    """The contract selection rule over provider order (C17): the first
    eligible `converted` record, then the first later eligible record with a
    distinct actual non-`converted` outcome, then another; stop at three.
    Without an eligible `converted` record the selection is empty: a
    findings-only report is possible, a negative-only fixture is not.
    `invalid_type` stays synthetic-only and is never selected."""
    eligible = [
        row
        for row in rows
        if row["disposition"] == "retained"
        and row["source_ordinal"] not in rejected
        and row["content_outcome"] != ContentOutcome.INVALID_TYPE.value
    ]
    first = next((r for r in eligible if r["content_outcome"] == "converted"), None)
    if first is None:
        return []
    chosen = [(first["source_ordinal"], "first_converted")]
    after = first["source_ordinal"]
    seen = {"converted"}
    for row in eligible:
        if len(chosen) >= limit:
            break
        if row["source_ordinal"] > after and row["content_outcome"] not in seen:
            chosen.append((row["source_ordinal"], "distinct_outcome"))
            seen.add(row["content_outcome"])
            after = row["source_ordinal"]
    return chosen


_DECISION_KEYS: Final = frozenset(
    {
        "ordinal",
        "selection_reason",
        "excerpt",
        "publication_safe",
        "full_capture_fidelity_disposition",
        "excerpt_replay_disposition",
        "reviewer",
    }
)
_SELECTION_REASONS: Final = frozenset({"first_converted", "distinct_outcome"})
_REJECTION_REASONS: Final = frozenset({"not_publication_safe", "no_safe_excerpt"})


def validate_decisions(data: Any) -> dict[str, Any]:
    """Type-checks reviewer decisions before any conversion. Every violation
    is the single categorical refusal `decisions_invalid`; no value is ever
    echoed."""

    def require(condition: bool) -> None:
        if not condition:
            raise CanaryRefusal("decisions_invalid")

    def member(value: Any, allowed: frozenset[str]) -> bool:
        return isinstance(value, str) and value in allowed

    require(isinstance(data, dict) and set(data) <= {"selected", "rejected"})
    require(isinstance(data.get("selected"), list) and isinstance(data.get("rejected", []), list))
    for item in data.get("rejected", []):
        require(isinstance(item, dict) and set(item) == {"ordinal", "reason"})
        require(_strict_int(item["ordinal"]) and item["ordinal"] >= 0)
        require(member(item["reason"], _REJECTION_REASONS))
    for item in data["selected"]:
        require(isinstance(item, dict) and set(item) == _DECISION_KEYS)
        require(_strict_int(item["ordinal"]) and item["ordinal"] >= 0)
        require(member(item["selection_reason"], _SELECTION_REASONS))
        excerpt = item["excerpt"]
        require(
            excerpt is None
            or (
                isinstance(excerpt, dict)
                and set(excerpt) == {"start", "end"}
                and _strict_int(excerpt["start"])
                and _strict_int(excerpt["end"])
            )
        )
        require(isinstance(item["publication_safe"], bool))
        require(member(item["full_capture_fidelity_disposition"], REVIEW_DISPOSITIONS))
        require(member(item["excerpt_replay_disposition"], REVIEW_DISPOSITIONS))
        require(isinstance(item["reviewer"], str) and bool(item["reviewer"].strip()))
    validated: dict[str, Any] = data
    return validated


async def replay_envelope(
    envelope: Mapping[str, Any], taxonomy: TaxonomyIndex
) -> tuple[DiscoveryResult, list[NormalizedPosting]]:
    """Offline replay of a projected envelope through the unchanged adapter
    (via `httpx.MockTransport`), bridge, and composition."""
    body = json.dumps(envelope, ensure_ascii=True).encode("utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        check_request_shape(request)
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    provider = GreenhouseJobBoardProvider(
        [GreenhouseBoard(BOARD_TOKEN, BOARD_COMPANY, CONTENT_MODE)],
        settings=CANARY_SETTINGS,
        transport_factory=lambda: httpx.MockTransport(handler),
    )
    result = await provider.discover(SourceQuery(sources=["greenhouse"]))
    return result, [_normalize(job, taxonomy) for job in result.jobs]


def golden_for(job: DiscoveredJob, normalized: NormalizedPosting) -> dict[str, Any]:
    conversion = convert_greenhouse_content(job.raw.get("content"), mode=CONTENT_MODE)
    return {
        "content_outcome": conversion.outcome.value,
        "description": job.description,
        "posting_inputs": to_jsonable(normalized.inputs),
        "normalized": normalized_summary(normalized),
    }


_NEVER_DISTINCT: Final = frozenset(
    {ContentOutcome.CONVERTED.value, ContentOutcome.INVALID_TYPE.value}
)


def check_selection_semantics(entries: Sequence[tuple[Any, Any, Any]]) -> None:
    """Enforces the selection contract on actual replay outcomes, never on
    labels alone. `entries` is `(source_ordinal, selection_reason,
    actual_replay_outcome)` in replay order:

    - at least one record, and source ordinals strictly increasing;
    - the first is `first_converted` and actually replays as `converted`;
    - every later one is `distinct_outcome` with an actual outcome that is
      neither `converted` nor `invalid_type`, pairwise distinct."""
    if not entries:
        raise CanaryRefusal("fixture_without_converted_sample")
    ordinals = [entry[0] for entry in entries]
    if not all(_strict_int(o) and o >= 0 for o in ordinals) or any(
        a >= b for a, b in zip(ordinals, ordinals[1:], strict=False)
    ):
        raise CanaryRefusal("selection_ordinal_order")
    _, first_reason, first_outcome = entries[0]
    if first_reason != "first_converted" or first_outcome != ContentOutcome.CONVERTED.value:
        raise CanaryRefusal("first_sample_not_converted")
    later = entries[1:]
    outcomes = [outcome for _, _, outcome in later]
    if (
        any(reason != "distinct_outcome" for _, reason, _ in later)
        or any(outcome in _NEVER_DISTINCT for outcome in outcomes)
        or len(set(outcomes)) != len(outcomes)
    ):
        raise CanaryRefusal("distinct_outcome_violation")


def build_projection(
    raw_body: bytes,
    summary: Mapping[str, Any],
    decisions: Mapping[str, Any],
    taxonomy: TaxonomyIndex,
) -> dict[str, Any]:
    """Validates reviewer decisions against the selection rule and limits,
    projects and excerpts the selected records, replays them, and returns
    the complete fixture document. Raises `CanaryRefusal` on any violation."""
    if summary["run_verdict"] is not None:
        raise CanaryRefusal("run_not_observed")
    capture = summary["capture"]
    if (
        not capture["complete"]
        or hashlib.sha256(raw_body).hexdigest() != capture["complete_response_sha256"]
        or len(raw_body) != capture["complete_response_bytes"]
    ):
        raise CanaryRefusal("raw_capture_mismatch")
    decisions = validate_decisions(decisions)
    records = json.loads(raw_body.decode("utf-8"))["jobs"]
    rejected = frozenset(item["ordinal"] for item in decisions.get("rejected", []))
    selections = list(decisions["selected"])
    if len(selections) > MAX_SELECTED:
        raise CanaryRefusal("too_many_selected")
    if any(s["ordinal"] >= len(records) for s in selections):
        raise CanaryRefusal("decision_ordinal_out_of_range")
    expected = expected_selection(summary["records"], rejected)
    if not expected:
        raise CanaryRefusal("no_converted_sample")
    actual = [(s["ordinal"], s["selection_reason"]) for s in selections]
    if not actual or actual != expected[: len(actual)]:
        raise CanaryRefusal("selection_rule_violation")

    jobs: list[dict[str, Any]] = []
    lineages: list[dict[str, Any]] = []
    for selection in selections:
        record = records[int(selection["ordinal"])]
        excerpt_spec = selection.get("excerpt")
        excerpt = None
        content = record.get("content")
        if isinstance(content, str):
            if excerpt_spec is None:
                raise CanaryRefusal("excerpt_required")
            excerpt = (excerpt_spec["start"], excerpt_spec["end"])
            check_excerpt_bounds(content, *excerpt)
        projected = project_record(record, excerpt)
        jobs.append(projected)
        lineages.append(_lineage(record, projected, excerpt))
    envelope = {"jobs": jobs, "meta": {"total": len(jobs)}}
    result, normalized = asyncio.run(replay_envelope(envelope, taxonomy))
    if len(result.jobs) != len(jobs):
        raise CanaryRefusal("replay_dropped_record")

    selected: list[dict[str, Any]] = []
    for index, selection in enumerate(selections):
        golden = golden_for(result.jobs[index], normalized[index])
        if published_screening(jobs[index], golden["description"]):
            raise CanaryRefusal("screening_hit")
        review = {
            "publication_safe": selection["publication_safe"],
            "full_capture_fidelity_disposition": selection["full_capture_fidelity_disposition"],
            "excerpt_replay_disposition": selection["excerpt_replay_disposition"],
            "reviewer": selection["reviewer"],
        }
        if review["publication_safe"] is not True:
            raise CanaryRefusal("not_publication_safe")
        if {
            review["full_capture_fidelity_disposition"],
            review["excerpt_replay_disposition"],
        } - PERFORMED_DISPOSITIONS:
            raise CanaryRefusal("review_not_performed")
        lineage = lineages[index]
        lineage["golden_output_sha256"] = canonical_json_hash(golden)
        selected.append(
            {
                "source_ordinal": int(selection["ordinal"]),
                "selection_reason": selection["selection_reason"],
                "replay_index": index,
                "lineage": lineage,
                "review": review,
                "golden_expectations": golden,
            }
        )

    check_selection_semantics(
        [
            (
                entry["source_ordinal"],
                entry["selection_reason"],
                entry["golden_expectations"]["content_outcome"],
            )
            for entry in selected
        ]
    )

    source_evidence: dict[str, Any] = {
        "provider": "greenhouse",
        "board_token": BOARD_TOKEN,
        "request_path": REQUEST_PATH,
        "request_query": REQUEST_QUERY,
        "observed_user_agent": summary["observed_user_agent"],
        "accept_encoding": ACCEPT_ENCODING,
        "captured_at": summary["captured_at"],
        "complete_response_sha256": capture["complete_response_sha256"],
        "complete_response_bytes": capture["complete_response_bytes"],
        "source_record_count": summary["source_record_count"],
    }
    if summary["source_meta_total"] is not None:
        source_evidence["source_meta_total"] = summary["source_meta_total"]
    aggregate = summary["aggregate"]
    document = {
        "schema_version": FIXTURE_SCHEMA_VERSION,
        "fixture_kind": FIXTURE_KIND,
        "source_evidence": source_evidence,
        "aggregate_evidence": {
            key: aggregate[key]
            for key in (
                "valid_count",
                "invalid_count",
                "retained_count",
                "skipped_count",
                "duplicate_count",
                "completeness_disposition",
                "conversion_outcomes",
            )
        },
        "selected": selected,
        "replay_envelope": envelope,
    }
    validate_fixture(document, taxonomy)
    return document


def _lineage(
    record: Mapping[str, Any], projected: Mapping[str, Any], excerpt: tuple[int, int] | None
) -> dict[str, Any]:
    content = record.get("content")
    lineage: dict[str, Any] = {
        "source_record_sha256": canonical_json_hash(dict(record)),
        "allowed_field_hashes": {
            "title": _text_hash(_field_state(record, "title")),
            "location.name": _text_hash(_location_name(record)),
            "content": _text_hash(_field_state(record, "content")),
        },
        "original_content_sha256": None,
        "original_content_code_points": None,
        "original_content_utf8_bytes": None,
        "excerpt_start_code_point": None,
        "excerpt_end_code_point_exclusive": None,
        "excerpt_sha256": None,
        "excerpt_code_points": None,
        "excerpt_utf8_bytes": None,
        "projected_record_sha256": canonical_json_hash(dict(projected)),
        "golden_output_sha256": None,
    }
    if isinstance(content, str) and excerpt is not None:
        text = content[excerpt[0] : excerpt[1]]
        try:
            original = content.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CanaryRefusal("content_not_utf8_encodable") from exc
        lineage.update(
            original_content_sha256=hashlib.sha256(original).hexdigest(),
            original_content_code_points=len(content),
            original_content_utf8_bytes=len(original),
            excerpt_start_code_point=excerpt[0],
            excerpt_end_code_point_exclusive=excerpt[1],
            excerpt_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            excerpt_code_points=len(text),
            excerpt_utf8_bytes=len(text.encode("utf-8")),
        )
    return lineage


_TOP_KEYS: Final = {
    "schema_version",
    "fixture_kind",
    "source_evidence",
    "aggregate_evidence",
    "selected",
    "replay_envelope",
}
_SOURCE_EVIDENCE_KEYS: Final = {
    "provider",
    "board_token",
    "request_path",
    "request_query",
    "observed_user_agent",
    "accept_encoding",
    "captured_at",
    "complete_response_sha256",
    "complete_response_bytes",
    "source_record_count",
}
_AGGREGATE_KEYS: Final = {
    "valid_count",
    "invalid_count",
    "retained_count",
    "skipped_count",
    "duplicate_count",
    "completeness_disposition",
    "conversion_outcomes",
}
_SELECTED_KEYS: Final = {
    "source_ordinal",
    "selection_reason",
    "replay_index",
    "lineage",
    "review",
    "golden_expectations",
}
_LINEAGE_KEYS: Final = {
    "source_record_sha256",
    "allowed_field_hashes",
    "original_content_sha256",
    "original_content_code_points",
    "original_content_utf8_bytes",
    "excerpt_start_code_point",
    "excerpt_end_code_point_exclusive",
    "excerpt_sha256",
    "excerpt_code_points",
    "excerpt_utf8_bytes",
    "projected_record_sha256",
    "golden_output_sha256",
}
_REVIEW_KEYS: Final = {
    "publication_safe",
    "full_capture_fidelity_disposition",
    "excerpt_replay_disposition",
    "reviewer",
}


def validate_fixture(document: Mapping[str, Any], taxonomy: TaxonomyIndex) -> None:
    """Structural, lineage, and semantic validation of a projected fixture
    document: exact key sets, the five-field allowlist, performed and
    approved review states, proper excerpts within both limits, recomputed
    projection/excerpt/golden hashes, and an independent replay of every
    projected job through the unchanged adapter, converter, bridge, and
    composition. Golden expectations must equal the recomputed results, and
    the selection contract is enforced on the actual replay outcomes, so
    relabelling or recomputing editable hashes cannot pass. Raises
    `CanaryRefusal`."""

    def require(condition: bool, kind: str) -> None:
        if not condition:
            raise CanaryRefusal(kind)

    require(set(document) == _TOP_KEYS, "fixture_keys")
    require(document["schema_version"] == FIXTURE_SCHEMA_VERSION, "fixture_schema_version")
    require(document["fixture_kind"] == FIXTURE_KIND, "fixture_kind")
    evidence = document["source_evidence"]
    require(set(evidence) - {"source_meta_total"} == _SOURCE_EVIDENCE_KEYS, "fixture_evidence")
    require(
        evidence["board_token"] == BOARD_TOKEN
        and evidence["request_path"] == REQUEST_PATH
        and evidence["request_query"] == REQUEST_QUERY
        and evidence["accept_encoding"] == ACCEPT_ENCODING,
        "fixture_request",
    )
    require(set(document["aggregate_evidence"]) == _AGGREGATE_KEYS, "fixture_aggregate")
    require(
        set(document["aggregate_evidence"]["conversion_outcomes"])
        == {o.value for o in ContentOutcome},
        "fixture_outcomes",
    )
    envelope = document["replay_envelope"]
    require(set(envelope) == {"jobs", "meta"} and set(envelope["meta"]) == {"total"}, "envelope")
    jobs = envelope["jobs"]
    selected = document["selected"]
    require(len(jobs) == len(selected) <= MAX_SELECTED, "fixture_count")
    require(envelope["meta"]["total"] == len(jobs), "fixture_meta_total")
    require(len(selected) >= 1, "fixture_without_converted_sample")
    for index, (job, entry) in enumerate(zip(jobs, selected, strict=True)):
        require(set(job) <= set(PROJECTED_FIELDS), "projected_keys")
        location = job.get("location")
        require(not isinstance(location, dict) or set(location) <= {"name"}, "projected_location")
        require(set(entry) == _SELECTED_KEYS, "selected_keys")
        require(entry["replay_index"] == index, "replay_index")
        review = entry["review"]
        require(set(review) == _REVIEW_KEYS, "review_keys")
        require(review["publication_safe"] is True, "review_not_publication_safe")
        require(
            all(
                isinstance(review[field], str) and review[field] in PERFORMED_DISPOSITIONS
                for field in ("full_capture_fidelity_disposition", "excerpt_replay_disposition")
            ),
            "review_not_performed",
        )
        require(
            isinstance(review["reviewer"], str) and bool(review["reviewer"].strip()),
            "review_reviewer_invalid",
        )
        lineage = entry["lineage"]
        require(set(lineage) == _LINEAGE_KEYS, "lineage_keys")
        require(lineage["projected_record_sha256"] == canonical_json_hash(job), "projected_hash")
        require(
            lineage["golden_output_sha256"] == canonical_json_hash(entry["golden_expectations"]),
            "golden_hash",
        )
        content = job.get("content")
        if isinstance(content, str):
            data = content.encode("utf-8")
            require(len(content) <= MAX_EXCERPT_CODE_POINTS, "excerpt_code_point_cap")
            require(len(data) <= MAX_EXCERPT_UTF8_BYTES, "excerpt_utf8_byte_cap")
            require(lineage["excerpt_sha256"] == hashlib.sha256(data).hexdigest(), "excerpt_hash")
            require(
                lineage["excerpt_code_points"] == len(content)
                and lineage["excerpt_utf8_bytes"] == len(data)
                and lineage["excerpt_end_code_point_exclusive"]
                - lineage["excerpt_start_code_point"]
                == len(content),
                "excerpt_counts",
            )
            start = lineage["excerpt_start_code_point"]
            end = lineage["excerpt_end_code_point_exclusive"]
            original = lineage["original_content_code_points"]
            require(
                all(_strict_int(v) for v in (start, end, original))
                and 0 <= start < end <= original,
                "excerpt_offsets_invalid",
            )
            require(not (start == 0 and end == original), "excerpt_is_complete_source")
        else:
            require(lineage["excerpt_sha256"] is None, "excerpt_not_applicable")

    # Independent semantic replay: actual outcomes, never labels.
    result, normalized = asyncio.run(replay_envelope(envelope, taxonomy))
    require(len(result.jobs) == len(jobs), "replay_dropped_record")
    recomputed = [golden_for(job, n) for job, n in zip(result.jobs, normalized, strict=True)]
    for entry, golden in zip(selected, recomputed, strict=True):
        require(entry["golden_expectations"] == golden, "golden_mismatch")
    check_selection_semantics(
        [
            (entry["source_ordinal"], entry["selection_reason"], golden["content_outcome"])
            for entry, golden in zip(selected, recomputed, strict=True)
        ]
    )


# ---------------------------------------------------------------------------
# Report draft.
# ---------------------------------------------------------------------------


def display_excerpt(text: str | None) -> str:
    """Converted text for display, capped at 1,000 characters per record."""
    if text is None:
        return "(no converted text)"
    if len(text) <= MAX_DISPLAY_CHARS:
        return text
    return text[:MAX_DISPLAY_CHARS] + "\n[display truncated at 1,000 characters]"


def render_report_draft(
    summary: Mapping[str, Any],
    document: Mapping[str, Any] | None,
    verdict: Verdict,
    reasons: Sequence[str],
) -> str:
    """Bounded report draft: aggregates for all records, categorical rows,
    and converted text only for selected excerpts (≤1,000 characters).
    Never titles, locations, warnings, exception text, or raw keys."""
    lines = [
        "# Phase 4 S2c live canary report (draft)",
        "",
        f"Verdict: **{verdict.value}**" + (f" ({', '.join(reasons)})" if reasons else ""),
        "",
        "## Request",
        "",
        f"- Board: `{summary['board_token']}`; request `GET {summary['request_path']}"
        f"?{summary['request_query']}`; one attempt; no retry, redirect, or fallback.",
        f"- User-Agent (locked `httpx` default, observed): `{summary['observed_user_agent']}`;"
        f" `Accept-Encoding: {summary['accept_encoding']}`.",
        f"- Captured at {summary['captured_at']}; HTTP status {summary['http_status']}.",
        f"- Caps: {MAX_RESPONSE_BYTES:,} bytes, {MAX_SOURCE_RECORDS} records, "
        f"{OUTER_DEADLINE_SECONDS:.0f}-second supervised deadline.",
    ]
    capture = summary["capture"]
    if capture["complete"]:
        lines.append(
            f"- Complete response: {capture['complete_response_bytes']:,} bytes, SHA-256 "
            f"`{capture['complete_response_sha256']}`."
        )
    else:
        lines.append("- No complete-response hash (capture absent or partial).")
    aggregate = summary.get("aggregate")
    if aggregate:
        lines += [
            "",
            "## Source records",
            "",
            f"- Source records: {summary['source_record_count']}; source meta.total: "
            f"{summary['source_meta_total']}; completeness: "
            f"{aggregate['completeness_disposition']}.",
            f"- Valid {aggregate['valid_count']}, invalid {aggregate['invalid_count']}, "
            f"duplicate {aggregate['duplicate_count']}, retained {aggregate['retained_count']}.",
            "",
            "## Conversion outcomes (declared mode `declared-double-escaped`)",
            "",
            "| Outcome | Count |",
            "|---|---|",
        ]
        lines += [f"| `{k}` | {v} |" for k, v in aggregate["conversion_outcomes"].items() if v]
        lines += ["", "## Normalized components (non-abstention counts, retained jobs)", ""]
        lines += [f"- `{k}`: {v}" for k, v in summary["component_counts"].items()]
        lines += [
            "",
            "Covered at the corpus boundary only: employment_type, seniority, "
            "location.country, skills recall. Unproven: remote_type, experience, city, "
            "state, postal code. Title is smoke evidence only. Live values are not accuracy "
            "evidence.",
            "",
            "## Records (categorical)",
            "",
            "| Ordinal | Disposition | Content outcome | Description code points |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {r['source_ordinal']} | {r['disposition']} | {r['content_outcome']} | "
            f"{r['description_code_points']} |"
            for r in summary["records"]
        ]
    if document is not None:
        lines += ["", "## Selected projected samples", ""]
        for entry in document["selected"]:
            golden = entry["golden_expectations"]
            lines += [
                f"### Ordinal {entry['source_ordinal']} ({entry['selection_reason']})",
                "",
                f"Replay outcome `{golden['content_outcome']}`; full-capture fidelity "
                f"`{entry['review']['full_capture_fidelity_disposition']}`; excerpt replay "
                f"`{entry['review']['excerpt_replay_disposition']}`. This is the complete "
                "conversion of the bounded excerpt, not of the complete source description.",
                "",
                "```text",
                display_excerpt(golden["description"]),
                "```",
                "",
            ]
    lines += ["", "## Salary", "", SALARY_STATEMENT, ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Raw cleanup and the fresh-process cleanup checker.
# ---------------------------------------------------------------------------

_FILE_ATTRIBUTE_REPARSE_POINT: Final = 0x400


def _is_link(path: Path) -> bool:
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def staging_inventory(staging_dir: Path) -> list[dict[str, Any]]:
    """Relative paths, sizes, and SHA-256 values only, never contents.
    Links, junctions, and reparse points are refused, never followed."""
    if _is_link(staging_dir):
        raise CanaryRefusal("staging_link_refused")
    root = staging_dir.resolve(strict=True)
    entries: list[dict[str, Any]] = []
    pending = [staging_dir]
    while pending:
        directory = pending.pop()
        for child in sorted(Path(directory).iterdir()):
            if _is_link(child):
                raise CanaryRefusal("staging_link_refused")
            if not child.resolve(strict=True).is_relative_to(root):
                raise CanaryRefusal("staging_escape_refused")
            if child.is_dir():
                pending.append(child)
                entries.append({"path": child.relative_to(staging_dir).as_posix(), "kind": "dir"})
            else:
                entries.append(
                    {
                        "path": child.relative_to(staging_dir).as_posix(),
                        "kind": "file",
                        "bytes": child.stat().st_size,
                        "sha256": file_sha256(child),
                    }
                )
    return sorted(entries, key=lambda e: e["path"])


def git_blob_id(data: bytes) -> str:
    """Git's object id for `data` as a blob (an identity, not a security hash)."""
    header = b"blob %d\x00" % len(data)
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


@dataclass(frozen=True)
class CleanupBinding:
    """The exact immutable post-run advisory candidate and the approved
    publication-artifact hashes that cleanup is bound to. `fixture_sha256`
    is `None` only when the approved state is a findings-only report."""

    base_sha: str
    candidate_sha: str
    fixture_sha256: str | None
    report_sha256: str


def _repo_rel(path: Path) -> str:
    return os.path.relpath(path, REPO_ROOT).replace(os.sep, "/")


def publication_checks(
    paths: CanaryPaths, binding: CleanupBinding, git: Callable[[Sequence[str]], str]
) -> dict[str, bool]:
    """Binding to the reviewed candidate and approved artifacts: HEAD is the
    candidate, the tree is clean, and the fixture/report bytes equal the
    approved hashes (so any post-approval change fails). The fixture must
    also validate, including performed and approved review states. Content
    screening is recorded but never establishes publication safety alone."""
    well_formed = (
        bool(_SHA_RE.fullmatch(binding.base_sha))
        and bool(_SHA_RE.fullmatch(binding.candidate_sha))
        and bool(_SHA256_RE.fullmatch(binding.report_sha256))
        and (binding.fixture_sha256 is None or bool(_SHA256_RE.fullmatch(binding.fixture_sha256)))
    )
    if not well_formed:
        return {"binding_well_formed": False}
    in_range = git(["rev-list", f"{binding.base_sha}..{binding.candidate_sha}"]).split()
    report_ok = paths.report.is_file() and file_sha256(paths.report) == binding.report_sha256
    checks = {
        "binding_well_formed": True,
        "head_is_candidate": git(["rev-parse", "HEAD"]).strip() == binding.candidate_sha,
        "tree_clean": git(["status", "--porcelain"]) == "",
        "candidate_descends_from_base": binding.candidate_sha in in_range,
        "report_matches_approval": report_ok,
        "report_screening_clean": report_ok
        and not screening_hits(paths.report.read_text(encoding="utf-8"), phone=False),
        "fixture_matches_approval": False,
    }
    if binding.fixture_sha256 is None:
        checks["fixture_matches_approval"] = not os.path.lexists(paths.fixture)
    elif paths.fixture.is_file() and file_sha256(paths.fixture) == binding.fixture_sha256:
        try:
            validate_fixture(
                json.loads(paths.fixture.read_text(encoding="utf-8")),
                load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH),
            )
            checks["fixture_matches_approval"] = True
        except Exception:  # any validation or replay failure means not approved
            checks["fixture_matches_approval"] = False
    return checks


def raw_absence_checks(
    raw: bytes, paths: CanaryPaths, binding: CleanupBinding, git: Callable[[Sequence[str]], str]
) -> dict[str, bool]:
    """While raw staging exists: the known raw-response bytes, regardless of
    filename, are absent from the proposed commit range, the index, and every
    changed or publication file."""
    blob = git_blob_id(raw)
    span = f"{binding.base_sha}..{binding.candidate_sha}"
    range_objects = {
        line.split(" ", 1)[0] for line in git(["rev-list", "--objects", span]).split("\n")
    }
    index_objects = {
        fields_[1]
        for line in git(["ls-files", "-s"]).splitlines()
        if len(fields_ := line.split()) > 1
    }
    changed = [
        line
        for line in git(["diff", "--name-only", binding.base_sha, binding.candidate_sha]).split(
            "\n"
        )
        if line
    ]
    forms = {raw, raw.replace(b"\n", b"\r\n")} - {b""}
    targets = {REPO_ROOT / rel for rel in changed} | {paths.fixture, paths.report}
    contained = any(
        target.is_file() and any(form in target.read_bytes() for form in forms)
        for target in targets
    )
    return {
        "raw_blob_absent_from_commit_range": blob not in range_objects,
        "raw_blob_absent_from_index": blob not in index_objects,
        "raw_bytes_absent_from_tracked_paths": not contained,
    }


def cleanup_staging(
    paths: CanaryPaths,
    *,
    expected_raw_sha256: str | None,
    expected_raw_bytes: int | None,
    binding: CleanupBinding,
    git: Callable[[Sequence[str]], str],
) -> dict[str, Any]:
    """Verify the publication binding and raw absence, then inventory and
    delete the dedicated staging directory. The attempt reservation is never
    touched. Any failed check raises `CanaryRefusal` and deletes nothing."""
    if not os.path.lexists(paths.staging_dir):
        raise CanaryRefusal("staging_absent")
    raw: bytes | None = None
    if paths.raw.exists():
        raw = paths.raw.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_raw_sha256 or len(raw) != expected_raw_bytes:
            raise CanaryRefusal("raw_capture_mismatch")
    elif expected_raw_sha256 is not None:
        raise CanaryRefusal("raw_capture_missing")
    pre_deletion = publication_checks(paths, binding, git)
    if raw is not None:
        pre_deletion.update(raw_absence_checks(raw, paths, binding, git))
    failed = sorted(name for name, ok in pre_deletion.items() if not ok)
    if failed:
        raise CanaryRefusal(f"publication_binding_failed:{failed[0]}")
    inventory = staging_inventory(paths.staging_dir)
    for entry in sorted(inventory, key=lambda e: e["path"].count("/"), reverse=True):
        target = paths.staging_dir / entry["path"]
        if entry["kind"] == "file":
            os.unlink(target)
        else:
            os.rmdir(target)
    os.rmdir(paths.staging_dir)
    return {
        "raw_sha256": expected_raw_sha256,
        "raw_bytes": expected_raw_bytes,
        "raw_blob": git_blob_id(raw) if raw is not None else None,
        "pre_deletion_checks": pre_deletion,
        "inventory": inventory,
        "inventory_sha256": canonical_json_hash({"inventory": inventory}),
        "cleaned_at": _now_iso(),
    }


def verify_cleanup(
    paths: CanaryPaths,
    *,
    binding: CleanupBinding,
    raw_blob: str | None,
    git: Callable[[Sequence[str]], str],
) -> dict[str, bool]:
    """The fresh-process checker (contract §7 step 6), bound to the same
    candidate and approved artifacts."""
    staging_rel = _repo_rel(paths.staging_dir)
    span = f"{binding.base_sha}..{binding.candidate_sha}"
    known = (paths.raw, paths.summary, paths.projection_preview, paths.launch, paths.claim)
    results = {
        "staging_root_absent": not os.path.lexists(paths.staging_dir),
        "known_capture_paths_absent": not any(os.path.lexists(p) for p in known),
        "no_staging_residue": git(["status", "--porcelain", "--ignored", "--", staging_rel]) == "",
        "no_staging_path_in_index": git(["ls-files", "--", staging_rel]) == "",
    }
    results.update(publication_checks(paths, binding, git))
    if results.get("binding_well_formed"):
        changed = git(["log", "--format=", "--name-only", span]).splitlines()
        results["no_runtime_path_in_commit_range"] = not any(
            line.startswith(".claude/runtime/") for line in changed
        )
        if raw_blob is not None:
            objects = {
                line.split(" ", 1)[0] for line in git(["rev-list", "--objects", span]).split("\n")
            }
            index = git(["ls-files", "-s"])
            results["raw_blob_absent_from_commit_range"] = raw_blob not in objects
            results["raw_blob_absent_from_index"] = raw_blob not in index
    return results


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _git_clean() -> bool:
    return git_output(["status", "--porcelain"]) == ""


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), indent=2, sort_keys=True))


def _add_binding_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--fixture-sha256", required=True, help="hex digest, or 'absent'")
    parser.add_argument("--report-sha256", required=True)


def _binding(args: argparse.Namespace) -> CleanupBinding:
    fixture = None if args.fixture_sha256 == "absent" else args.fixture_sha256
    return CleanupBinding(args.base, args.candidate, fixture, args.report_sha256)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 4 S2c Greenhouse live canary (disabled by default; ADR 0017)."
    )
    sub = parser.add_subparsers(dest="command")
    live = sub.add_parser("live", help="the single authorized live attempt")
    live.add_argument("--board", required=True)
    live.add_argument("--expected-sha", required=True)
    live.add_argument("--contract-sha256", required=True)
    live.add_argument("--authorization-file", required=True, type=Path)
    live.add_argument("--authorization-sha256", required=True)
    sub.add_parser("_worker", help=argparse.SUPPRESS)
    sub.add_parser("eligibility", help="categorical selection candidates from staging")
    for name in ("project", "build-fixture"):
        cmd = sub.add_parser(name, help="projection preview / create-only tracked fixture")
        cmd.add_argument("--decisions", required=True, type=Path)
    cleanup = sub.add_parser("cleanup", help="verified deletion of raw staging")
    cleanup.add_argument("--expected-raw-sha256")
    cleanup.add_argument("--expected-raw-bytes", type=int)
    _add_binding_args(cleanup)
    check = sub.add_parser("verify-cleanup", help=argparse.SUPPRESS)
    _add_binding_args(check)
    check.add_argument("--raw-blob")
    return parser.parse_args(argv)


def _decisions(path: Path, paths: CanaryPaths) -> dict[str, Any]:
    if not path.resolve().is_relative_to(paths.staging_dir.resolve()):
        raise CanaryRefusal("decisions_outside_staging")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CanaryRefusal("decisions_invalid") from None
    return validate_decisions(data)


def _staged_summary(paths: CanaryPaths) -> tuple[bytes, dict[str, Any]]:
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    return paths.raw.read_bytes(), summary


def main(argv: Sequence[str] | None = None, *, paths: CanaryPaths = LIVE_PATHS) -> int:
    """Every outcome is a fixed categorical line; no exception message,
    traceback, or staged value is ever printed."""
    args = _parse_args(argv)
    try:
        return _dispatch(args, paths)
    except CanaryRefusal as refusal:
        _print({"result": "refused", "kind": refusal.kind})
        return 2
    except FileExistsError:
        _print({"result": "refused", "kind": "create_only_target_exists"})
        return 2
    except SupervisionAborted:
        _print({"result": "refused", "kind": "supervision_aborted"})
        return 2
    except KeyboardInterrupt:
        _print({"result": "refused", "kind": "interrupted"})
        return 130
    except Exception:  # categorical: never the message or traceback
        _print({"result": "refused", "kind": "operational_failure"})
        return 2


def _dispatch(args: argparse.Namespace, paths: CanaryPaths) -> int:
    if args.command is None:
        _print({"result": "refused", "kind": "gate_disabled"})
        return 2
    if args.command == "_worker":
        return worker_entry(paths, sys.stdin)
    if args.command == "live":
        outcome = run_live(
            LiveRequest(
                args.board,
                args.expected_sha,
                args.contract_sha256,
                args.authorization_file,
                args.authorization_sha256,
            ),
            env=os.environ,
            paths=paths,
            head_sha=lambda: git_output(["rev-parse", "HEAD"]).strip(),
            tree_is_clean=_git_clean,
            worker_argv=[sys.executable, str(Path(__file__).resolve()), "_worker"],
        )
        _print({"result": "terminal", "outcome": outcome})
        return 0
    if args.command == "eligibility":
        raw, summary = _staged_summary(paths)
        records = json.loads(raw.decode("utf-8"))["jobs"]
        rows = []
        for row in summary["records"]:
            if row["disposition"] != "retained":
                continue
            record = records[row["source_ordinal"]]
            hits = published_screening(project_record_full(record), None)
            rows.append({**row, "screening_hits": hits})
        _print({"eligible": rows})
        return 0
    if args.command in ("project", "build-fixture"):
        decisions = _decisions(args.decisions, paths)
        raw, summary = _staged_summary(paths)
        taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
        document = build_projection(raw, summary, decisions, taxonomy)
        data = (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
        target = paths.projection_preview if args.command == "project" else paths.fixture
        exclusive_write(target, data)
        _print({"result": "written", "path": target.name, "sha256": file_sha256(target)})
        return 0
    if args.command == "cleanup":
        binding = _binding(args)
        attestation = cleanup_staging(
            paths,
            expected_raw_sha256=args.expected_raw_sha256,
            expected_raw_bytes=args.expected_raw_bytes,
            binding=binding,
            git=git_output,
        )
        checker = Path(__file__).resolve()
        argv = [
            sys.executable,
            str(checker),
            "verify-cleanup",
            "--base",
            binding.base_sha,
            "--candidate",
            binding.candidate_sha,
            "--fixture-sha256",
            binding.fixture_sha256 or "absent",
            "--report-sha256",
            binding.report_sha256,
        ]
        if attestation["raw_blob"] is not None:
            argv += ["--raw-blob", attestation["raw_blob"]]
        completed = subprocess.run(  # fixed argv: a fresh checker process
            argv, capture_output=True, text=True, check=False
        )
        checks = json.loads(completed.stdout)
        attestation.update(
            checker={"path": checker.name, "sha256": file_sha256(checker)},
            executing_sha=git_output(["rev-parse", "HEAD"]).strip(),
            checks=checks,
            passed=completed.returncode == 0 and all(checks.values()),
        )
        _print(attestation)
        return 0 if attestation["passed"] else 1
    if args.command == "verify-cleanup":
        checks = verify_cleanup(
            paths, binding=_binding(args), raw_blob=args.raw_blob, git=git_output
        )
        _print(checks)
        return 0 if all(checks.values()) else 1
    return 2


def project_record_full(record: Mapping[str, Any]) -> dict[str, Any]:
    """Screening view of a retained record's allowlisted fields with its
    complete content (staging-side eligibility only; never published)."""
    view = {key: record[key] for key in ("title", "absolute_url") if key in record}
    if isinstance(record.get("location"), dict) and "name" in record["location"]:
        view["location"] = {"name": record["location"]["name"]}
    if isinstance(record.get("content"), str):
        view["content"] = record["content"]
    return view


if __name__ == "__main__":
    raise SystemExit(main())
