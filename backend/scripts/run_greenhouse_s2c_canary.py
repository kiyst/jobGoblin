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
import hashlib
import html
import json
import os
import re
import stat
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from pathlib import Path
from typing import IO, Any, Final

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
    reviewed selection (`None` when no fidelity review was performed)."""
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
            reviews = [entry["review"] for entry in selected]
            if any(r["full_capture_fidelity_disposition"] == "not_performed" for r in reviews):
                reasons[Verdict.INCONCLUSIVE].append("fidelity_review_unavailable")
            if any(
                r["full_capture_fidelity_disposition"] == "mismatch"
                or r["excerpt_replay_disposition"] == "mismatch"
                for r in reviews
            ):
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
# Attempt reservation and supervised worker.
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


@dataclass(frozen=True)
class WorkerResult:
    kind: str  # "exited" | "deadline_terminated" | "termination_unconfirmed"
    returncode: int | None


def supervise_worker(
    argv: Sequence[str],
    *,
    deadline_seconds: float = OUTER_DEADLINE_SECONDS,
    grace_seconds: float = TERMINATION_GRACE_SECONDS,
    env: Mapping[str, str] | None = None,
) -> WorkerResult:
    """Run the worker with one wall-clock deadline that starts immediately
    before launch. At the deadline: terminate, reap, escalate to kill, and
    confirm exit; unconfirmed termination is reported, never ignored."""
    start = time.monotonic()
    process = subprocess.Popen(  # fixed argv, no shell
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=dict(env) if env is not None else None,
    )
    try:
        returncode = process.wait(timeout=max(0.0, deadline_seconds - (time.monotonic() - start)))
        return WorkerResult("exited", returncode)
    except subprocess.TimeoutExpired:
        pass
    for stop in (process.terminate, process.kill):
        stop()
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            continue
        if process.poll() is not None:
            return WorkerResult("deadline_terminated", process.returncode)
    return WorkerResult("termination_unconfirmed", None)


def worker_main(paths: CanaryPaths) -> int:
    """The supervised worker: re-checks its preconditions, performs the one
    request and all automated processing, and writes the categorical
    summary. Spawns no process and prints nothing."""
    if os.environ.get(LIVE_ENV_VAR) != LIVE_ENV_VALUE:
        return 3
    if not paths.reservation.is_file() or not paths.staging_dir.is_dir():
        return 3
    if paths.raw.exists() or paths.summary.exists():
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
) -> str:
    """Preflight, reserve, stage, supervise, and record one terminal outcome.
    Returns the categorical terminal outcome."""
    record = live_preflight(
        request, env=env, paths=paths, head_sha=head_sha, tree_is_clean=tree_is_clean
    )
    handle = create_reservation(paths.reservation, record)
    try:
        try:
            os.mkdir(paths.staging_dir)
        except FileExistsError:
            append_terminal_outcome(handle, f"{Verdict.FAIL_CLOSED.value}:staging_exists")
            raise CanaryRefusal("staging_exists") from None
        worker = supervise_worker(worker_argv, deadline_seconds=deadline_seconds, env=env)
        if worker.kind == "termination_unconfirmed":
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
    `invalid_type` stays synthetic-only and is never selected."""
    eligible = [
        row
        for row in rows
        if row["disposition"] == "retained"
        and row["source_ordinal"] not in rejected
        and row["content_outcome"] != ContentOutcome.INVALID_TYPE.value
    ]
    chosen: list[tuple[int, str]] = []
    after = -1
    first = next((r for r in eligible if r["content_outcome"] == "converted"), None)
    if first is not None:
        chosen.append((first["source_ordinal"], "first_converted"))
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


_REVIEW_DISPOSITIONS: Final = frozenset({"faithful", "mismatch", "not_performed"})


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
    records = json.loads(raw_body.decode("utf-8"))["jobs"]
    rejected = frozenset(int(item["ordinal"]) for item in decisions.get("rejected", []))
    selections = list(decisions["selected"])
    if len(selections) > MAX_SELECTED:
        raise CanaryRefusal("too_many_selected")
    expected = expected_selection(summary["records"], rejected)
    actual = [(int(s["ordinal"]), str(s["selection_reason"])) for s in selections]
    if actual != expected[: len(actual)] or (expected and not actual):
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
        } - _REVIEW_DISPOSITIONS or not isinstance(review["reviewer"], str):
            raise CanaryRefusal("review_disposition_invalid")
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
    validate_fixture(document)
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


def validate_fixture(document: Mapping[str, Any]) -> None:
    """Structural and lineage validation of a projected fixture document:
    exact key sets, the five-field allowlist, limits, and recomputed
    projection/excerpt/golden hashes. Raises `CanaryRefusal`."""

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
    for index, (job, entry) in enumerate(zip(jobs, selected, strict=True)):
        require(set(job) <= set(PROJECTED_FIELDS), "projected_keys")
        location = job.get("location")
        require(not isinstance(location, dict) or set(location) <= {"name"}, "projected_location")
        require(set(entry) == _SELECTED_KEYS, "selected_keys")
        require(entry["replay_index"] == index, "replay_index")
        require(set(entry["review"]) == _REVIEW_KEYS, "review_keys")
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
        else:
            require(lineage["excerpt_sha256"] is None, "excerpt_not_applicable")


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


def cleanup_staging(
    paths: CanaryPaths, *, expected_raw_sha256: str | None, expected_raw_bytes: int | None
) -> dict[str, Any]:
    """Verify, inventory, and delete the dedicated staging directory. The
    attempt reservation is never touched. Raises `CanaryRefusal` (and deletes
    nothing) when the raw capture does not match its recorded evidence."""
    if not os.path.lexists(paths.staging_dir):
        raise CanaryRefusal("staging_absent")
    if paths.raw.exists():
        if (
            file_sha256(paths.raw) != expected_raw_sha256
            or paths.raw.stat().st_size != expected_raw_bytes
        ):
            raise CanaryRefusal("raw_capture_mismatch")
    elif expected_raw_sha256 is not None:
        raise CanaryRefusal("raw_capture_missing")
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
        "inventory": inventory,
        "inventory_sha256": canonical_json_hash({"inventory": inventory}),
        "cleaned_at": _now_iso(),
    }


def verify_cleanup(
    paths: CanaryPaths, *, base_sha: str, git: Callable[[Sequence[str]], str]
) -> dict[str, bool]:
    """The fresh-process checker (contract §7 step 6)."""
    staging_rel = os.path.relpath(paths.staging_dir, REPO_ROOT).replace(os.sep, "/")
    changed = git(["log", "--format=", "--name-only", f"{base_sha}..HEAD"]).splitlines()
    results = {
        "staging_root_absent": not os.path.lexists(paths.staging_dir),
        "known_capture_paths_absent": not any(
            os.path.lexists(p) for p in (paths.raw, paths.summary, paths.projection_preview)
        ),
        "no_staging_residue": git(["status", "--porcelain", "--ignored", "--", staging_rel]) == "",
        "no_staging_path_in_index": git(["ls-files", "--", staging_rel]) == "",
        "no_runtime_path_in_commit_range": not any(
            line.startswith(".claude/runtime/") for line in changed
        ),
        "fixture_valid_or_absent": True,
        "report_screening_clean_or_absent": True,
    }
    if paths.fixture.exists():
        try:
            validate_fixture(json.loads(paths.fixture.read_text(encoding="utf-8")))
        except (CanaryRefusal, ValueError, KeyError, TypeError):
            results["fixture_valid_or_absent"] = False
    if paths.report.exists():
        results["report_screening_clean_or_absent"] = not screening_hits(
            paths.report.read_text(encoding="utf-8"), phone=False
        )
    return results


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _git_clean() -> bool:
    return git_output(["status", "--porcelain"]) == ""


def _print(payload: Mapping[str, Any]) -> None:
    print(json.dumps(dict(payload), indent=2, sort_keys=True))


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
    cleanup.add_argument("--base", required=True)
    check = sub.add_parser("verify-cleanup", help=argparse.SUPPRESS)
    check.add_argument("--base", required=True)
    return parser.parse_args(argv)


def _decisions(path: Path, paths: CanaryPaths) -> dict[str, Any]:
    if not path.resolve().is_relative_to(paths.staging_dir.resolve()):
        raise CanaryRefusal("decisions_outside_staging")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _staged_summary(paths: CanaryPaths) -> tuple[bytes, dict[str, Any]]:
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    return paths.raw.read_bytes(), summary


def main(argv: Sequence[str] | None = None, *, paths: CanaryPaths = LIVE_PATHS) -> int:
    args = _parse_args(argv)
    try:
        if args.command is None:
            _print({"result": "refused", "kind": "gate_disabled"})
            return 2
        if args.command == "_worker":
            return worker_main(paths)
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
            raw, summary = _staged_summary(paths)
            taxonomy = load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)
            document = build_projection(raw, summary, _decisions(args.decisions, paths), taxonomy)
            data = (json.dumps(document, indent=2, ensure_ascii=True) + "\n").encode("utf-8")
            target = paths.projection_preview if args.command == "project" else paths.fixture
            exclusive_write(target, data)
            _print({"result": "written", "path": target.name, "sha256": file_sha256(target)})
            return 0
        if args.command == "cleanup":
            attestation = cleanup_staging(
                paths,
                expected_raw_sha256=args.expected_raw_sha256,
                expected_raw_bytes=args.expected_raw_bytes,
            )
            checker = Path(__file__).resolve()
            completed = subprocess.run(  # fixed argv: a fresh checker process
                [sys.executable, str(checker), "verify-cleanup", "--base", args.base],
                capture_output=True,
                text=True,
                check=False,
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
            checks = verify_cleanup(paths, base_sha=args.base, git=git_output)
            _print(checks)
            return 0 if all(checks.values()) else 1
    except CanaryRefusal as refusal:
        _print({"result": "refused", "kind": refusal.kind})
        return 2
    except FileExistsError:
        _print({"result": "refused", "kind": "create_only_target_exists"})
        return 2
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
