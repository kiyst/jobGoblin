"""Offline tests for the Phase 4 S2c live-canary harness (ADR 0017).

Mocks and fakes only: every test runs with real network transports and DNS
resolution disabled, and none creates the real staging directory or
attempt reservation (`_no_live_side_effects`). The projected fixture and the
report do not exist yet; every record here is synthetic.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import html
import json
import os
import socket
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.hashing import canonical_json_hash
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, TaxonomyIndex, load_taxonomy
from app.providers import greenhouse as adapter
from app.providers.greenhouse import GreenhouseClientSettings
from app.providers.greenhouse_content import ContentOutcome, convert_greenhouse_content
from scripts import run_greenhouse_s2c_canary as canary

BACKEND_DIR = Path(__file__).resolve().parents[1]
HARNESS = BACKEND_DIR / "scripts" / "run_greenhouse_s2c_canary.py"
URL = "https://boards-api.greenhouse.io/v1/boards/discord/jobs?content=true"
SHA = "a" * 40

# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real transports and DNS resolution are impossible in these tests."""

    async def refuse_async(*_: object, **__: object) -> httpx.Response:
        raise AssertionError("real network transport used in an offline test")

    def refuse(*_: object, **__: object) -> Any:
        raise AssertionError("network resolution attempted in an offline test")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_async)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(autouse=True)
def _no_live_side_effects() -> Iterator[None]:
    """No test may create the real staging directory or reservation."""
    live = canary.LIVE_PATHS
    before = (os.path.lexists(live.staging_dir), os.path.lexists(live.reservation))
    yield
    assert (os.path.lexists(live.staging_dir), os.path.lexists(live.reservation)) == before


@pytest.fixture(scope="module")
def taxonomy() -> TaxonomyIndex:
    return load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)


@pytest.fixture
def paths(tmp_path: Path) -> canary.CanaryPaths:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    contract = runtime / "contract.md"
    contract.write_bytes(b"frozen contract\n")
    return canary.CanaryPaths(
        runtime_dir=runtime,
        staging_dir=runtime / "staging",
        reservation=runtime / "attempt.jsonl",
        contract=contract,
        fixture=tmp_path / "fixture.json",
        report=tmp_path / "report.md",
    )


# ---------------------------------------------------------------------------
# Synthetic records and transports.
# ---------------------------------------------------------------------------

_HTML = (
    "<div><p>Discord is building the place to talk and hang out.</p>"
    "<h2>What you'll do</h2><ul><li>Build Python services</li>"
    "<li>Operate PostgreSQL</li></ul><p>Full-time, Senior role.</p></div>"
)


def escaped(markup: str) -> str:
    """Greenhouse's observed double-escaped shape (ADR 0010)."""
    return html.escape(markup, quote=False)


def record(n: int, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": 4_000_000 + n,
        "absolute_url": f"https://job-boards.greenhouse.io/discord/jobs/{4_000_000 + n}",
        "title": "Senior Software Engineer, Backend",
        "location": {"name": "San Francisco, CA"},
        "content": escaped(_HTML),
        "requisition_id": f"R{n}",
        "first_published": "2026-09-01T10:00:00-04:00",
        "updated_at": "2026-09-02T10:00:00-04:00",
        "company_name": "Discord",
        "departments": [{"id": 1, "name": "Engineering"}],
        "offices": [],
        "metadata": None,
    }
    base.update(overrides)
    return base


def body_of(records: list[Any], **envelope: Any) -> bytes:
    document = {"jobs": records, "meta": {"total": len(records)}}
    document.update(envelope)
    return json.dumps(document).encode("utf-8")


class FlagStream(httpx.AsyncByteStream):
    """Response stream that records whether anything read it."""

    def __init__(self, data: bytes, *, fail_after: int | None = None) -> None:
        self.data = data
        self.read = False
        self.fail_after = fail_after

    async def __aiter__(self) -> Any:
        self.read = True
        if self.fail_after is not None:
            yield self.data[: self.fail_after]
            raise httpx.ReadError("interrupted")
        yield self.data

    async def aclose(self) -> None:
        return None


class Recorder:
    """A MockTransport handler that counts calls and returns a fixed reply."""

    def __init__(
        self,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        stream: httpx.AsyncByteStream | None = None,
    ) -> None:
        self.calls: list[httpx.Request] = []
        self.status = status
        self.headers = {"content-type": "application/json", **(headers or {})}
        self.stream = stream if stream is not None else FlagStream(body)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return httpx.Response(self.status, headers=self.headers, stream=self.stream)

    def factory(self) -> Callable[[], httpx.AsyncBaseTransport]:
        return lambda: httpx.MockTransport(self)


def run_pipeline(
    paths: canary.CanaryPaths, recorder: Recorder, taxonomy: TaxonomyIndex
) -> dict[str, Any]:
    paths.staging_dir.mkdir()
    return asyncio.run(canary.run_canary_pipeline(recorder.factory(), paths.raw, taxonomy))


# ---------------------------------------------------------------------------
# Contract constants.
# ---------------------------------------------------------------------------


def test_contract_constants_are_exact() -> None:
    assert canary.BOARD_TOKEN == "discord"
    assert canary.CONTENT_MODE == "declared-double-escaped"
    assert canary.REQUEST_HOST == "boards-api.greenhouse.io"
    assert canary.REQUEST_PATH == "/v1/boards/discord/jobs"
    assert canary.REQUEST_QUERY == "content=true"
    assert canary.ACCEPT_ENCODING == "identity"
    assert canary.MAX_RESPONSE_BYTES == 5_000_000
    assert canary.MAX_SOURCE_RECORDS == 500
    assert canary.OUTER_DEADLINE_SECONDS == 60.0
    assert (canary.MAX_SELECTED, canary.MAX_EXCERPT_CODE_POINTS) == (3, 2000)
    assert (canary.MAX_EXCERPT_UTF8_BYTES, canary.MAX_DISPLAY_CHARS) == (4096, 1000)
    assert canary.LIVE_PATHS.reservation.parent == canary.LIVE_PATHS.staging_dir.parent
    assert not canary.LIVE_PATHS.reservation.is_relative_to(canary.LIVE_PATHS.staging_dir)


def test_canary_settings_are_exact() -> None:
    """W8 witness: one attempt (no retry); every other bound is the
    reviewed adapter default; the response cap is exactly 5,000,000 bytes."""
    defaults = GreenhouseClientSettings()
    settings = canary.CANARY_SETTINGS
    assert settings.max_attempts == 1
    assert settings.max_response_bytes == 5_000_000
    for name in (
        "connect_timeout",
        "read_timeout",
        "write_timeout",
        "pool_timeout",
        "attempt_deadline",
        "backoff_base",
        "backoff_cap",
        "max_retry_after",
    ):
        assert getattr(settings, name) == getattr(defaults, name)


def test_salary_statement_is_the_exact_contract_wording() -> None:
    assert canary.SALARY_STATEMENT == (
        "No salary-specific parameters or endpoint were requested; no salary field was "
        "extracted or composed, and the salary classifier was not invoked. Incidental "
        "compensation text may occur in captured content. The bridge supplies no "
        "compensation input; ADR 0011 L4 remains open."
    )


def test_every_content_outcome_has_exactly_one_classification() -> None:
    converted = {ContentOutcome.CONVERTED}
    failures = {ContentOutcome.NOT_REQUESTED, ContentOutcome.PARSER_ERROR}
    assert failures == canary.FAILURE_OUTCOMES
    assert set(ContentOutcome) - converted - failures == canary.FINDING_OUTCOMES
    assert len(canary.FINDING_OUTCOMES) == 11
    assert converted | canary.FAILURE_OUTCOMES | canary.FINDING_OUTCOMES == set(ContentOutcome)


@pytest.mark.parametrize(
    ("kind", "status", "expected"),
    [
        ("timeout", None, canary.Verdict.INCONCLUSIVE),
        ("deadline", None, canary.Verdict.INCONCLUSIVE),
        ("connect_error", None, canary.Verdict.INCONCLUSIVE),
        ("http_status", 429, canary.Verdict.INCONCLUSIVE),
        ("http_status", 500, canary.Verdict.INCONCLUSIVE),
        ("http_status", 503, canary.Verdict.INCONCLUSIVE),
        ("http_status", 599, canary.Verdict.INCONCLUSIVE),
        ("http_status", 404, canary.Verdict.FAIL_CLOSED),
        ("http_status", 403, canary.Verdict.FAIL_CLOSED),
        ("redirect", 301, canary.Verdict.FAIL_CLOSED),
        ("media_type", 200, canary.Verdict.FAIL_CLOSED),
        ("transport_error", None, canary.Verdict.FAIL_CLOSED),
        ("oversize", 200, canary.Verdict.FAIL_CLOSED),
        ("invalid_json", 200, canary.Verdict.FAIL_CLOSED),
        ("envelope", 200, canary.Verdict.FAIL_CLOSED),
        ("no_usable_records", 200, canary.Verdict.FAIL_CLOSED),
    ],
)
def test_adapter_failure_classification(kind: str, status: int | None, expected: Any) -> None:
    assert canary.classify_adapter_failure(kind, status) is expected


# ---------------------------------------------------------------------------
# Request guard, headers, and the single send.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "url"),
    [
        pytest.param("POST", URL, id="post"),
        pytest.param("GET", URL.replace("https", "http"), id="http"),
        pytest.param("GET", URL.replace("boards-api", "api"), id="other_host"),
        pytest.param("GET", URL.replace(".io/", ".io:8443/"), id="port"),
        pytest.param("GET", URL.replace("discord", "gitlab"), id="other_board"),
        pytest.param("GET", URL.replace("/jobs", "/jobs/1"), id="detail_endpoint"),
        pytest.param("GET", URL + "&questions=true", id="extra_query"),
        pytest.param("GET", URL.replace("content=true", "content=false"), id="query_value"),
        pytest.param("GET", URL.split("?")[0], id="missing_query"),
        pytest.param("GET", URL + "#x", id="fragment"),
        pytest.param("GET", URL.replace("https://", "https://u:p@"), id="userinfo"),
    ],
)
def test_request_shape_guard_refuses_before_send(method: str, url: str, tmp_path: Path) -> None:
    """W1 witness: every request but the one permitted GET is refused
    before the inner transport is reached."""
    recorder = Recorder(body_of([record(1)]))
    capture = canary.Capture()
    transport = canary.RecordingTransport(httpx.MockTransport(recorder), capture, tmp_path / "r")
    with pytest.raises(canary.CanaryRefusal) as refusal:
        asyncio.run(transport.handle_async_request(httpx.Request(method, url)))
    assert refusal.value.kind == "request_shape_refused"
    assert recorder.calls == []
    assert capture.request_sent is False


def test_second_send_is_refused_before_network(tmp_path: Path) -> None:
    """W2 witness."""
    recorder = Recorder(body_of([record(1)]))
    capture = canary.Capture()
    transport = canary.RecordingTransport(httpx.MockTransport(recorder), capture, tmp_path / "r")
    asyncio.run(transport.handle_async_request(httpx.Request("GET", URL)))
    with pytest.raises(canary.CanaryRefusal) as refusal:
        asyncio.run(transport.handle_async_request(httpx.Request("GET", URL)))
    assert refusal.value.kind == "second_request_refused"
    assert len(recorder.calls) == 1


def test_accept_encoding_identity_and_default_user_agent(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    """W5 witness: the only header override is `Accept-Encoding: identity`;
    the locked `httpx` default User-Agent is kept and recorded."""
    recorder = Recorder(body_of([record(1)]))
    summary = run_pipeline(paths, recorder, taxonomy)
    (request,) = recorder.calls
    assert request.headers["accept-encoding"] == "identity"
    assert request.headers["user-agent"] == f"python-httpx/{httpx.__version__}"
    assert summary["observed_user_agent"] == f"python-httpx/{httpx.__version__}"
    assert summary["accept_encoding"] == "identity"


def test_non_identity_content_encoding_fails_closed_without_draining(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    stream = FlagStream(body_of([record(1)]))
    recorder = Recorder(headers={"content-encoding": "gzip"}, stream=stream)
    summary = run_pipeline(paths, recorder, taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == (
        "FAIL-CLOSED",
        "unexpected_content_encoding",
    )
    assert stream.read is False
    assert summary["capture"]["complete_response_sha256"] is None
    assert not paths.raw.exists()


# ---------------------------------------------------------------------------
# Capture semantics.
# ---------------------------------------------------------------------------


def test_complete_capture_is_hashed_and_staged_exactly(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    body = body_of([record(1), record(2)])
    summary = run_pipeline(paths, Recorder(body), taxonomy)
    assert summary["capture"] == {
        "complete": True,
        "partial": False,
        "complete_response_sha256": hashlib.sha256(body).hexdigest(),
        "complete_response_bytes": len(body),
    }
    assert paths.raw.read_bytes() == body
    assert summary["source_record_count"] == 2
    assert summary["source_meta_total"] == 2


def _sized_body(size: int) -> bytes:
    prefix = body_of([record(1)])[:-1] + b', "pad": "'
    padded = prefix + b"x" * (size - len(prefix) - 2) + b'"}'
    assert len(padded) == size
    json.loads(padded)
    return padded


def test_body_at_exact_cap_is_complete(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> None:
    summary = run_pipeline(paths, Recorder(_sized_body(5_000_000)), taxonomy)
    assert summary["capture"]["complete"] is True
    assert summary["capture"]["complete_response_bytes"] == 5_000_000


def test_body_over_cap_is_partial_without_complete_hash(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    """W9 witness: one byte over 5,000,000 is a partial capture, FAIL-CLOSED,
    with no complete-response hash and no staged raw file."""
    summary = run_pipeline(paths, Recorder(_sized_body(5_000_001)), taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == ("FAIL-CLOSED", "response_cap_exceeded")
    assert summary["capture"] == {
        "complete": False,
        "partial": True,
        "complete_response_sha256": None,
        "complete_response_bytes": None,
    }
    assert not paths.raw.exists()


def test_interrupted_stream_is_partial_and_never_complete(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    stream = FlagStream(body_of([record(1)]), fail_after=10)
    summary = run_pipeline(paths, Recorder(stream=stream), taxonomy)
    assert summary["run_verdict"] == "FAIL-CLOSED"
    assert summary["run_kind"] == "transport_error"
    assert summary["capture"]["partial"] is True
    assert summary["capture"]["complete_response_sha256"] is None
    assert not paths.raw.exists()


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_status_is_inconclusive_with_one_request_and_no_drain(
    status: int, paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    stream = FlagStream(b"error page")
    recorder = Recorder(status=status, headers={"retry-after": "1"}, stream=stream)
    summary = run_pipeline(paths, recorder, taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == (
        "INCONCLUSIVE",
        f"http_status:{status}",
    )
    assert len(recorder.calls) == 1
    assert stream.read is False
    assert summary["capture"]["complete_response_sha256"] is None


def test_503_is_inconclusive_with_exactly_one_request(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    """W8 witness (behavioral): a retryable status produces no second
    attempt; a retry would hit the second-send refusal instead."""
    recorder = Recorder(status=503, stream=FlagStream(b""))
    summary = run_pipeline(paths, recorder, taxonomy)
    assert summary["run_kind"] == "http_status:503"
    assert len(recorder.calls) == 1


@pytest.mark.parametrize(
    ("status", "headers", "kind"),
    [
        (404, {}, "http_status:404"),
        (301, {"location": "https://example.com/"}, "redirect:301"),
        (200, {"content-type": "text/html"}, "media_type"),
    ],
)
def test_non_success_responses_fail_closed_without_draining(
    status: int,
    headers: dict[str, str],
    kind: str,
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
) -> None:
    stream = FlagStream(b"<html>x</html>")
    recorder = Recorder(status=status, headers=headers, stream=stream)
    summary = run_pipeline(paths, recorder, taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == ("FAIL-CLOSED", kind)
    assert stream.read is False
    assert len(recorder.calls) == 1


@pytest.mark.parametrize(
    ("body", "kind"),
    [
        (b"{not json", "invalid_json:200"),
        (b'{"meta": {"total": 0}}', "envelope:200"),
        (body_of([{"id": None}, {"title": "x"}]), "no_usable_records:200"),
    ],
)
def test_schema_failures_fail_closed(
    body: bytes, kind: str, paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary = run_pipeline(paths, Recorder(body), taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == ("FAIL-CLOSED", kind)


def test_empty_board_is_inconclusive(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> None:
    summary = run_pipeline(paths, Recorder(body_of([])), taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == ("INCONCLUSIVE", "empty_board")


def test_record_cap_is_enforced_before_conversion(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W10 witness: 501 records fail closed before the adapter converts a
    single record."""
    calls: list[object] = []
    original = adapter.convert_greenhouse_content

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter, "convert_greenhouse_content", counting)
    summary = run_pipeline(paths, Recorder(body_of([record(i) for i in range(501)])), taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == ("FAIL-CLOSED", "record_cap_exceeded")
    assert calls == []


def test_record_cap_accepts_exactly_five_hundred(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary = run_pipeline(paths, Recorder(body_of([record(i) for i in range(500)])), taxonomy)
    assert summary["run_verdict"] is None
    assert summary["aggregate"]["retained_count"] == 500


def test_exclusive_write_never_overwrites(tmp_path: Path) -> None:
    """W6 witness: the raw capture is exclusive-create; an existing file is
    never overwritten or appended."""
    target = tmp_path / "raw"
    canary.exclusive_write(target, b"first")
    with pytest.raises(FileExistsError):
        canary.exclusive_write(target, b"second")
    assert target.read_bytes() == b"first"


def test_pipeline_refuses_to_replace_an_existing_raw_capture(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    paths.staging_dir.mkdir()
    paths.raw.write_bytes(b"pre-existing")
    with pytest.raises(FileExistsError):
        asyncio.run(
            canary.run_canary_pipeline(
                Recorder(body_of([record(1)])).factory(), paths.raw, taxonomy
            )
        )
    assert paths.raw.read_bytes() == b"pre-existing"


# ---------------------------------------------------------------------------
# End to end through adapter, converter, bridge, and composition.
# ---------------------------------------------------------------------------


def test_end_to_end_observation_with_findings(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    records = [
        record(1),
        record(2, content=None),
        record(3, content="   "),
        record(4, id=None),  # invalid
        record(5),
        record(5),  # duplicate id: both skipped
        record(6, content=escaped("<p>A</p>") + "<b>"),  # mixed literal/escaped
    ]
    summary = run_pipeline(paths, Recorder(body_of(records)), taxonomy)
    assert summary["run_verdict"] is None
    aggregate = summary["aggregate"]
    assert {k: aggregate[k] for k in ("valid_count", "invalid_count", "retained_count")} == {
        "valid_count": 6,
        "invalid_count": 1,
        "retained_count": 4,
    }
    assert (aggregate["skipped_count"], aggregate["duplicate_count"]) == (3, 2)
    outcomes = {k: v for k, v in aggregate["conversion_outcomes"].items() if v}
    assert outcomes == {
        "converted": 1,
        "absent": 1,
        "blank": 1,
        "mixed_literal_and_escaped_markup": 1,
    }
    assert aggregate["incomplete_results"] is True
    assert summary["findings"] == [
        "content_outcome:absent",
        "content_outcome:blank",
        "content_outcome:mixed_literal_and_escaped_markup",
        "skipped_invalid_records",
        "skipped_duplicate_records",
        "incomplete_results",
    ]
    assert [r["disposition"] for r in summary["records"]] == [
        "retained",
        "retained",
        "retained",
        "invalid",
        "duplicate",
        "duplicate",
        "retained",
    ]
    counts = summary["component_counts"]
    assert counts["skills.jobs_with_match"] >= 1
    assert counts["seniority"] >= 1
    # Categorical only: no title, location, or content text in the summary.
    rendered = json.dumps(summary)
    for text in ("Senior Software Engineer", "San Francisco", "Discord is building", "&lt;"):
        assert text not in rendered


def test_clean_observation_has_no_findings(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary = run_pipeline(paths, Recorder(body_of([record(1), record(2)])), taxonomy)
    assert summary["run_verdict"] is None
    assert summary["findings"] == []
    assert summary["aggregate"]["completeness_disposition"] == "consistent"


def test_completeness_mismatch_is_a_finding(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    body = body_of([record(1)], meta={"total": 7})
    summary = run_pipeline(paths, Recorder(body), taxonomy)
    assert "completeness:mismatch" in summary["findings"]


def test_unexpected_disabled_mode_fails_closed(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`not_requested` under the fixed enabled mode is a contract failure."""
    monkeypatch.setattr(canary, "CONTENT_MODE", "disabled")
    summary = run_pipeline(paths, Recorder(body_of([record(1)])), taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == (
        "FAIL-CLOSED",
        "content_outcome:not_requested",
    )


def test_normalization_exception_fails_closed(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: Any, **__: Any) -> Any:
        raise RuntimeError("secret body text")

    monkeypatch.setattr(canary, "normalize_posting", boom)
    summary = run_pipeline(paths, Recorder(body_of([record(1)])), taxonomy)
    assert (summary["run_verdict"], summary["run_kind"]) == (
        "FAIL-CLOSED",
        "bridge_or_normalization_exception",
    )
    assert "secret body text" not in json.dumps(summary)


# ---------------------------------------------------------------------------
# Verdict precedence.
# ---------------------------------------------------------------------------


def _selected(
    fidelity: str = "faithful", replay: str = "faithful", outcome: str = "converted"
) -> list[dict[str, Any]]:
    return [
        {
            "selection_reason": "first_converted",
            "review": {
                "full_capture_fidelity_disposition": fidelity,
                "excerpt_replay_disposition": replay,
            },
            "golden_expectations": {"content_outcome": outcome},
        }
    ]


def test_verdict_precedence() -> None:
    observed: dict[str, Any] = {"run_verdict": None, "findings": []}
    assert canary.compute_verdict(observed, _selected()) == (canary.Verdict.PASS, [])
    assert canary.compute_verdict(observed, None)[0] is canary.Verdict.INCONCLUSIVE
    assert canary.compute_verdict(observed, _selected("not_performed"))[0] is (
        canary.Verdict.INCONCLUSIVE
    )
    assert canary.compute_verdict(observed, _selected("mismatch")) == (
        canary.Verdict.PASS_WITH_FINDINGS,
        ["fidelity_mismatch"],
    )
    assert canary.compute_verdict(observed, _selected(outcome="absent")) == (
        canary.Verdict.PASS_WITH_FINDINGS,
        ["no_safe_converted_sample"],
    )
    assert canary.compute_verdict(observed, [])[1] == ["no_safe_converted_sample"]
    with_findings = {"run_verdict": None, "findings": ["incomplete_results"]}
    assert canary.compute_verdict(with_findings, _selected())[0] is (
        canary.Verdict.PASS_WITH_FINDINGS
    )
    # Higher-priority conditions are never downgraded.
    assert canary.compute_verdict(with_findings, None)[0] is canary.Verdict.INCONCLUSIVE
    assert canary.compute_verdict(observed, _selected(), cleanup_passed=False) == (
        canary.Verdict.FAIL_CLOSED,
        ["cleanup_failed"],
    )
    settled = {"run_verdict": "INCONCLUSIVE", "run_kind": "empty_board"}
    assert canary.compute_verdict(settled, None) == (canary.Verdict.INCONCLUSIVE, ["empty_board"])
    failed = {"run_verdict": "FAIL-CLOSED", "run_kind": "outer_deadline"}
    assert canary.compute_verdict(failed, _selected())[0] is canary.Verdict.FAIL_CLOSED


# ---------------------------------------------------------------------------
# Live gate, reservation, and supervised worker.
# ---------------------------------------------------------------------------


def _authorization(paths: canary.CanaryPaths) -> tuple[Path, str]:
    auth = paths.runtime_dir / "authorization.md"
    auth.write_bytes(b"authorized: one GET\n")
    return auth, hashlib.sha256(auth.read_bytes()).hexdigest()


def _live_request(paths: canary.CanaryPaths, **overrides: Any) -> canary.LiveRequest:
    auth, auth_sha = _authorization(paths)
    fields: dict[str, Any] = {
        "board": "discord",
        "expected_sha": SHA,
        "contract_sha256": hashlib.sha256(paths.contract.read_bytes()).hexdigest(),
        "authorization_file": auth,
        "authorization_sha256": auth_sha,
    }
    fields.update(overrides)
    return canary.LiveRequest(**fields)


_LIVE_ENV = {canary.LIVE_ENV_VAR: canary.LIVE_ENV_VALUE}


def _preflight(
    paths: canary.CanaryPaths,
    request: canary.LiveRequest,
    *,
    env: dict[str, str] | None = None,
    head: str = SHA,
    clean: bool = True,
) -> dict[str, Any]:
    return canary.live_preflight(
        request,
        env=_LIVE_ENV if env is None else env,
        paths=paths,
        head_sha=lambda: head,
        tree_is_clean=lambda: clean,
    )


def test_live_preflight_refuses_without_live_env(paths: canary.CanaryPaths) -> None:
    """W3 witness: live operation is disabled by default."""
    for env in ({}, {canary.LIVE_ENV_VAR: "1"}, {canary.LIVE_ENV_VAR: "authorized-once "}):
        with pytest.raises(canary.CanaryRefusal) as refusal:
            _preflight(paths, _live_request(paths), env=env)
        assert refusal.value.kind == "gate_disabled"
    assert not paths.reservation.exists()


def test_live_preflight_refuses_non_allowlisted_board(paths: canary.CanaryPaths) -> None:
    """W4 witness: only `discord`; there is no fallback board."""
    for board in ("gitlab", "anthropic", "Discord", "discord "):
        with pytest.raises(canary.CanaryRefusal) as refusal:
            _preflight(paths, _live_request(paths, board=board))
        assert refusal.value.kind == "board_not_allowlisted"


@pytest.mark.parametrize(
    ("overrides", "head", "clean", "kind"),
    [
        ({}, "b" * 40, True, "sha_mismatch"),
        ({"expected_sha": "A" * 40}, "A" * 40, True, "sha_mismatch"),
        ({}, SHA, False, "dirty_tree"),
        ({"contract_sha256": "0" * 64}, SHA, True, "contract_mismatch"),
        ({"authorization_sha256": "0" * 64}, SHA, True, "authorization_mismatch"),
        ({"authorization_file": Path("missing.md")}, SHA, True, "authorization_mismatch"),
    ],
)
def test_live_preflight_refuses_each_binding_mismatch(
    overrides: dict[str, Any], head: str, clean: bool, kind: str, paths: canary.CanaryPaths
) -> None:
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _preflight(paths, _live_request(paths, **overrides), head=head, clean=clean)
    assert refusal.value.kind == kind
    assert not paths.reservation.exists()
    assert not paths.staging_dir.exists()


def test_live_preflight_refuses_existing_reservation(paths: canary.CanaryPaths) -> None:
    """W12 witness: an existing reservation blocks every later attempt,
    whatever its recorded outcome."""
    paths.reservation.write_bytes(b'{"event": "reserved"}\n')
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _preflight(paths, _live_request(paths))
    assert refusal.value.kind == "attempt_already_reserved"


def test_live_preflight_refuses_existing_staging(paths: canary.CanaryPaths) -> None:
    paths.staging_dir.mkdir()
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _preflight(paths, _live_request(paths))
    assert refusal.value.kind == "staging_exists"


def test_live_preflight_binds_the_reservation_record(paths: canary.CanaryPaths) -> None:
    request = _live_request(paths)
    record = _preflight(paths, request)
    assert record["board_token"] == "discord"
    assert record["advisory_sha"] == SHA
    assert record["contract_sha256"] == request.contract_sha256
    assert record["request_fingerprint"] == canary.request_fingerprint()
    assert record["authorization_identity"] == "authorization.md"
    assert record["authorization_sha256"] == request.authorization_sha256
    assert record["outcome"] == "reserved"


def test_create_reservation_is_exclusive(paths: canary.CanaryPaths) -> None:
    handle = canary.create_reservation(paths.reservation, {"event": "reserved"})
    handle.close()
    before = paths.reservation.read_bytes()
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.create_reservation(paths.reservation, {"event": "reserved"})
    assert refusal.value.kind == "attempt_already_reserved"
    assert paths.reservation.read_bytes() == before


def _worker_writing(summary: dict[str, Any], target: Path) -> list[str]:
    code = f"import pathlib; pathlib.Path({str(target)!r}).write_text({json.dumps(summary)!r})"
    return [sys.executable, "-c", code]


def _run_live(paths: canary.CanaryPaths, argv: list[str], **kwargs: Any) -> str:
    return canary.run_live(
        _live_request(paths),
        env={**os.environ, **_LIVE_ENV},
        paths=paths,
        head_sha=lambda: SHA,
        tree_is_clean=lambda: True,
        worker_argv=argv,
        **kwargs,
    )


def _reservation_lines(paths: canary.CanaryPaths) -> list[dict[str, Any]]:
    return [json.loads(line) for line in paths.reservation.read_text().splitlines()]


def test_run_live_reserves_stages_supervises_and_records_one_terminal_outcome(
    paths: canary.CanaryPaths,
) -> None:
    summary = {"run_verdict": None, "run_kind": None}
    outcome = _run_live(paths, _worker_writing(summary, paths.summary))
    assert outcome == "OBSERVED:pending_post_run_review"
    lines = _reservation_lines(paths)
    assert [line["event"] for line in lines] == ["reserved", "terminal"]
    assert lines[1]["outcome"] == outcome
    assert paths.staging_dir.is_dir()


def test_run_live_worker_without_summary_fails_closed(paths: canary.CanaryPaths) -> None:
    outcome = _run_live(paths, [sys.executable, "-c", "pass"])
    assert outcome == "FAIL-CLOSED:worker_failed"


def test_reservation_blocks_rerun_after_cleanup(paths: canary.CanaryPaths) -> None:
    summary = {"run_verdict": "INCONCLUSIVE", "run_kind": "http_status:503"}
    _run_live(paths, _worker_writing(summary, paths.summary))
    before = paths.reservation.read_bytes()
    canary.cleanup_staging(paths, expected_raw_sha256=None, expected_raw_bytes=None)
    assert not paths.staging_dir.exists()
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _run_live(paths, _worker_writing(summary, paths.summary))
    assert refusal.value.kind == "attempt_already_reserved"
    assert paths.reservation.read_bytes() == before


def test_crash_residue_reservation_still_consumes_the_authorization(
    paths: canary.CanaryPaths,
) -> None:
    canary.create_reservation(paths.reservation, {"event": "reserved"}).close()
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _preflight(paths, _live_request(paths))
    assert refusal.value.kind == "attempt_already_reserved"


_SLEEPER = [sys.executable, "-c", "import time; time.sleep(30)"]


def test_supervisor_terminates_and_reaps_worker_at_deadline() -> None:
    """W7 witness: the outer deadline terminates and reaps synchronous work."""
    start = time.monotonic()
    result = canary.supervise_worker(_SLEEPER, deadline_seconds=1.0, grace_seconds=5.0)
    assert result.kind == "deadline_terminated"
    assert result.returncode is not None
    assert time.monotonic() - start < 10


def test_supervisor_reports_a_normal_exit() -> None:
    result = canary.supervise_worker([sys.executable, "-c", "raise SystemExit(7)"])
    assert result == canary.WorkerResult("exited", 7)


def test_run_live_records_outer_deadline(paths: canary.CanaryPaths) -> None:
    outcome = _run_live(paths, _SLEEPER, deadline_seconds=1.0)
    assert outcome == "FAIL-CLOSED:outer_deadline"
    assert _reservation_lines(paths)[-1]["outcome"] == outcome


class _StuckProcess:
    returncode = None

    def __init__(self, *_: Any, **__: Any) -> None:
        self.stops: list[str] = []

    def wait(self, timeout: float | None = None) -> int:
        raise subprocess.TimeoutExpired("worker", timeout or 0)

    def terminate(self) -> None:
        self.stops.append("terminate")

    def kill(self) -> None:
        self.stops.append("kill")

    def poll(self) -> None:
        return None


def test_unconfirmed_termination_fails_closed(
    paths: canary.CanaryPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(canary.subprocess, "Popen", _StuckProcess)
    assert canary.supervise_worker(["x"], deadline_seconds=0.01, grace_seconds=0.01) == (
        canary.WorkerResult("termination_unconfirmed", None)
    )
    outcome = _run_live(paths, ["x"], deadline_seconds=0.01)
    assert outcome == "FAIL-CLOSED:worker_termination_unconfirmed"


def test_worker_refuses_without_its_preconditions(paths: canary.CanaryPaths) -> None:
    assert canary.worker_main(paths) == 3  # no live env, no reservation, no staging


def test_default_invocation_refuses(capsys: pytest.CaptureFixture[str]) -> None:
    assert canary.main([]) == 2
    assert json.loads(capsys.readouterr().out) == {"kind": "gate_disabled", "result": "refused"}


# ---------------------------------------------------------------------------
# Imports, process boundaries, and no persistence.
# ---------------------------------------------------------------------------

_ALLOWED_APP_IMPORTS = {
    "app.ingestion.hashing",
    "app.normalization.posting",
    "app.normalization.taxonomy",
    "app.providers.greenhouse",
    "app.providers.greenhouse_content",
    "app.providers.greenhouse_posting_inputs",
    "app.schemas.discovered_job",
    "app.schemas.provider",
}
_FORBIDDEN_PREFIXES = ("app.db", "app.ingestion.pipeline", "app.core", "sqlalchemy", "alembic")


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_harness_imports_only_allowed_modules() -> None:
    """W11 witness: no database, ingestion-persistence, or settings import."""
    names = _imports(ast.parse(HARNESS.read_text(encoding="utf-8")))
    assert {n for n in names if n.startswith("app")} == _ALLOWED_APP_IMPORTS
    assert not [n for n in names if n.startswith(_FORBIDDEN_PREFIXES)]


def test_offline_run_loads_no_database_module(tmp_path: Path) -> None:
    code = textwrap.dedent(
        f"""
        import asyncio, json, sys
        import httpx
        from scripts import run_greenhouse_s2c_canary as m
        from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, load_taxonomy
        body = {body_of([record(1)])!r}
        def handler(request):
            headers = {{"content-type": "application/json"}}
            return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))
        summary = asyncio.run(m.run_canary_pipeline(
            lambda: httpx.MockTransport(handler), m.Path({str(tmp_path / "raw")!r}),
            load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)))
        assert summary["run_verdict"] is None, summary
        print(json.dumps(sorted(n for n in sys.modules if n.startswith({_FORBIDDEN_PREFIXES!r}))))
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, check=True
    )
    assert json.loads(completed.stdout) == []


_WORKER_SIDE = {
    "worker_main",
    "run_canary_pipeline",
    "_evaluate_result",
    "_normalize",
    "RecordingTransport",
    "exclusive_write",
}


def test_worker_side_code_spawns_no_process() -> None:
    tree = ast.parse(HARNESS.read_text(encoding="utf-8"))
    found = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if node.name not in _WORKER_SIDE:
                continue
            found.add(node.name)
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name):
                    assert inner.id not in {"subprocess", "multiprocessing", "Popen"}
                if isinstance(inner, ast.Attribute):
                    assert inner.attr not in {"Popen", "system", "spawnv", "startfile", "execv"}
                    assert not inner.attr.startswith(("spawn", "exec", "fork"))
    assert found == _WORKER_SIDE


# ---------------------------------------------------------------------------
# Screening, selection, excerpts, projection, and the fixture.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "hits"),
    [
        ("Contact jane.doe@example.com", ["email"]),
        ("jane.doe&#64;example.com", ["email"]),
        ("jane.doe&amp;#64;example.com", ["email"]),
        ("Call +1 (415) 555-0100", ["phone"]),
        ("Call &#43;44 20 7946 0958", ["phone"]),
        ('<a href="mailto:x">apply</a>', ["mailto_or_tel"]),
        ("&lt;a href=&quot;tel:5550100&quot;&gt;", ["mailto_or_tel"]),
        ("see linkedin.com/in/someone", ["profile_url"]),
        ("Discord is hiring backend engineers in 2026.", []),
        ("Job 4012345006 in San Francisco, CA", []),
    ],
)
def test_screening_vectors(text: str, hits: list[str]) -> None:
    assert canary.screening_hits(text) == hits


def test_screening_without_phone_ignores_url_digits() -> None:
    url = "https://job-boards.greenhouse.io/discord/jobs/4012345006"
    assert canary.screening_hits(url, phone=False) == []


def _rows(*outcomes: str | None, disposition: str = "retained") -> list[dict[str, Any]]:
    return [
        {"source_ordinal": i, "disposition": disposition, "content_outcome": o}
        for i, o in enumerate(outcomes)
    ]


def test_selection_rule_follows_provider_order() -> None:
    rows = _rows("absent", "converted", "converted", "blank", "absent", "invalid_type", "mixed")
    assert canary.expected_selection(rows, frozenset()) == [
        (1, "first_converted"),
        (3, "distinct_outcome"),
        (4, "distinct_outcome"),
    ]
    assert canary.expected_selection(rows, frozenset({1})) == [
        (2, "first_converted"),
        (3, "distinct_outcome"),
        (4, "distinct_outcome"),
    ]
    assert canary.expected_selection(rows, frozenset({1, 2, 3, 4})) == [
        (0, "distinct_outcome"),
        (6, "distinct_outcome"),
    ]
    invalid = _rows("converted", disposition="duplicate")
    assert canary.expected_selection(invalid, frozenset()) == []


def test_projection_keeps_only_the_allowlist_and_exact_excerpt() -> None:
    source = record(1, location={"name": "Remote", "id": 9})
    projected = canary.project_record(source, (5, 25))
    assert set(projected) == {"id", "absolute_url", "title", "location", "content"}
    assert projected["location"] == {"name": "Remote"}
    assert projected["content"] == source["content"][5:25]
    missing = {k: v for k, v in record(2).items() if k not in ("title", "content")}
    assert set(canary.project_record(missing, None)) == {"id", "absolute_url", "location"}
    nulls = canary.project_record(record(3, title=None, content=None, location=None), None)
    assert (nulls["title"], nulls["content"], nulls["location"]) == (None, None, None)
    with pytest.raises(canary.CanaryRefusal, match="excerpt_required"):
        canary.project_record(record(4), None)
    with pytest.raises(canary.CanaryRefusal, match="excerpt_not_applicable"):
        canary.project_record(record(5, content=None), (0, 0))


@pytest.mark.parametrize(
    ("content", "start", "end", "kind"),
    [
        ("a" * 2001, 0, 2001, "excerpt_code_point_cap"),
        ("\U0001f600" * 1025, 0, 1025, "excerpt_utf8_byte_cap"),
        ("abc", 2, 1, "excerpt_offsets_invalid"),
        ("abc", 0, 4, "excerpt_offsets_invalid"),
        ("ab\ud800c", 0, 4, "excerpt_not_utf8_encodable"),
    ],
)
def test_excerpt_bounds_refuse(content: str, start: int, end: int, kind: str) -> None:
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.check_excerpt_bounds(content, start, end)
    assert refusal.value.kind == kind


def test_excerpt_bounds_accept_exact_limits() -> None:
    canary.check_excerpt_bounds("a" * 2000, 0, 2000)
    canary.check_excerpt_bounds("\U0001f600" * 1024, 0, 1024)


def _observed_run(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, records: list[Any]
) -> tuple[bytes, dict[str, Any]]:
    summary = run_pipeline(paths, Recorder(body_of(records)), taxonomy)
    return paths.raw.read_bytes(), summary


def _decision(ordinal: int, reason: str, excerpt: tuple[int, int] | None) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "selection_reason": reason,
        "excerpt": None if excerpt is None else {"start": excerpt[0], "end": excerpt[1]},
        "publication_safe": True,
        "full_capture_fidelity_disposition": "faithful",
        "excerpt_replay_disposition": "faithful",
        "reviewer": "test",
    }


def _balanced_excerpt(content: str) -> tuple[int, int]:
    end = content.index(escaped("</ul>")) + len(escaped("</ul>"))
    start = content.index(escaped("<h2>"))
    return start, end


def test_build_projection_produces_a_valid_bound_fixture(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    records = [record(1), record(2, content=None)]
    raw, summary = _observed_run(paths, taxonomy, records)
    span = _balanced_excerpt(records[0]["content"])
    decisions = {
        "selected": [
            _decision(0, "first_converted", span),
            _decision(1, "distinct_outcome", None),
        ]
    }
    document = canary.build_projection(raw, summary, decisions, taxonomy)
    canary.validate_fixture(document)
    evidence = document["source_evidence"]
    assert evidence["complete_response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert evidence["observed_user_agent"] == f"python-httpx/{httpx.__version__}"
    assert document["replay_envelope"]["meta"] == {"total": 2}
    first, second = document["selected"]
    lineage = first["lineage"]
    assert lineage["source_record_sha256"] == canonical_json_hash(records[0])
    assert lineage["excerpt_start_code_point"] == span[0]
    assert lineage["excerpt_end_code_point_exclusive"] == span[1]
    excerpt = records[0]["content"][span[0] : span[1]]
    assert lineage["excerpt_sha256"] == hashlib.sha256(excerpt.encode()).hexdigest()
    content_hash = hashlib.sha256(records[0]["content"].encode()).hexdigest()
    assert lineage["original_content_sha256"] == content_hash
    assert lineage["allowed_field_hashes"]["content"]["sha256"] == content_hash
    golden = first["golden_expectations"]
    expected = convert_greenhouse_content(excerpt, mode="declared-double-escaped")
    assert golden["content_outcome"] == "converted"
    assert golden["description"] == expected.text
    assert golden["posting_inputs"]["description"] == expected.text
    assert "salary" not in json.dumps(golden["normalized"])
    assert second["golden_expectations"]["content_outcome"] == "absent"
    assert second["lineage"]["excerpt_sha256"] is None
    # Prohibited source fields never reach the fixture.
    rendered = json.dumps(document)
    for prohibited in ("requisition_id", "first_published", "departments", "company_name"):
        assert prohibited not in rendered
    assert canary.compute_verdict(summary, document["selected"]) == (
        canary.Verdict.PASS_WITH_FINDINGS,
        ["content_outcome:absent", "incomplete_results"],
    )


def test_canonical_hashing_is_the_repository_algorithm() -> None:
    value = {"b": "é", "a": [1, 2]}
    expected = hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    assert canary.canonical_json_hash is canonical_json_hash
    assert canonical_json_hash(value) == expected


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        pytest.param(
            lambda d: d["selected"].__setitem__(0, _decision(1, "first_converted", (0, 10))),
            "selection_rule_violation",
            id="not_first_converted",
        ),
        pytest.param(
            lambda d: d.__setitem__("selected", []), "selection_rule_violation", id="none"
        ),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("excerpt", {"start": 0, "end": 2001}),
            "excerpt_code_point_cap",
            id="excerpt_cap",
        ),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("publication_safe", False),
            "not_publication_safe",
            id="unsafe",
        ),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("reviewer", None),
            "review_disposition_invalid",
            id="no_reviewer",
        ),
        pytest.param(
            lambda d: d["selected"].extend([_decision(2, "distinct_outcome", None)] * 3),
            "too_many_selected",
            id="too_many",
        ),
    ],
)
def test_build_projection_refuses_invalid_decisions(
    mutate: Callable[[dict[str, Any]], Any],
    kind: str,
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
) -> None:
    long_content = escaped("<p>" + "x" * 3000 + "</p>")
    records = [record(1, content=long_content), record(2, content=long_content)]
    raw, summary = _observed_run(paths, taxonomy, records)
    decisions: dict[str, Any] = {"selected": [_decision(0, "first_converted", (0, 100))]}
    mutate(decisions)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.build_projection(raw, summary, decisions, taxonomy)
    assert refusal.value.kind == kind


def test_build_projection_refuses_screening_hits(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    records = [record(1, content=escaped("<p>Email recruiter@example.com today</p>"))]
    raw, summary = _observed_run(paths, taxonomy, records)
    content = records[0]["content"]
    decisions = {"selected": [_decision(0, "first_converted", (0, len(content)))]}
    with pytest.raises(canary.CanaryRefusal, match="screening_hit"):
        canary.build_projection(raw, summary, decisions, taxonomy)


def test_build_projection_refuses_a_tampered_raw_capture(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    raw, summary = _observed_run(paths, taxonomy, [record(1)])
    decisions = {"selected": [_decision(0, "first_converted", (0, 10))]}
    with pytest.raises(canary.CanaryRefusal, match="raw_capture_mismatch"):
        canary.build_projection(raw + b" ", summary, decisions, taxonomy)
    settled = {**summary, "run_verdict": "INCONCLUSIVE"}
    with pytest.raises(canary.CanaryRefusal, match="run_not_observed"):
        canary.build_projection(raw, settled, decisions, taxonomy)


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        (
            lambda d: d["replay_envelope"]["jobs"][0].__setitem__("requisition_id", "R1"),
            "projected_keys",
        ),
        (lambda d: d["replay_envelope"]["meta"].__setitem__("total", 5), "fixture_meta_total"),
        (
            lambda d: d["replay_envelope"]["jobs"][0].__setitem__("title", "changed"),
            "projected_hash",
        ),
        (lambda d: d.__setitem__("extra", 1), "fixture_keys"),
        (
            lambda d: d["source_evidence"].__setitem__("request_query", "content=false"),
            "fixture_request",
        ),
        (
            lambda d: d["selected"][0]["golden_expectations"].__setitem__("description", "x"),
            "golden_hash",
        ),
        (
            lambda d: d["replay_envelope"]["jobs"][0].__setitem__(
                "location", {"name": "a", "id": 1}
            ),
            "projected_location",
        ),
    ],
)
def test_validate_fixture_detects_tampering(
    mutate: Callable[[dict[str, Any]], Any],
    kind: str,
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
) -> None:
    records = [record(1)]
    raw, summary = _observed_run(paths, taxonomy, records)
    span = _balanced_excerpt(records[0]["content"])
    document = canary.build_projection(
        raw, summary, {"selected": [_decision(0, "first_converted", span)]}, taxonomy
    )
    mutate(document)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.validate_fixture(document)
    assert refusal.value.kind == kind


# ---------------------------------------------------------------------------
# Report draft.
# ---------------------------------------------------------------------------


def test_report_draft_is_bounded(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> None:
    long_html = "<p>" + ("Build reliable Python services. " * 100) + "</p>"
    records = [record(1, content=escaped(long_html))]
    raw, summary = _observed_run(paths, taxonomy, records)
    decisions = {"selected": [_decision(0, "first_converted", (0, 1990))]}
    document = canary.build_projection(raw, summary, decisions, taxonomy)
    verdict, reasons = canary.compute_verdict(summary, document["selected"])
    report = canary.render_report_draft(summary, document, verdict, reasons)
    assert canary.SALARY_STATEMENT in report
    assert "[display truncated at 1,000 characters]" in report
    assert "Senior Software Engineer" not in report
    assert "San Francisco" not in report
    block = report.split("```text\n", 1)[1].split("\n```", 1)[0]
    assert len(block.split("\n[display truncated")[0]) == 1000


def test_display_excerpt_caps_at_one_thousand_characters() -> None:
    assert canary.display_excerpt("x" * 1000) == "x" * 1000
    capped = canary.display_excerpt("x" * 1001)
    assert capped.startswith("x" * 1000 + "\n[display truncated")
    assert canary.display_excerpt(None) == "(no converted text)"


# ---------------------------------------------------------------------------
# Raw cleanup and the cleanup checker.
# ---------------------------------------------------------------------------


def _staged(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> dict[str, Any]:
    summary = run_pipeline(paths, Recorder(body_of([record(1)])), taxonomy)
    canary.exclusive_write(paths.summary, json.dumps(summary).encode())
    (paths.staging_dir / "drafts").mkdir()
    (paths.staging_dir / "drafts" / "preview.json").write_bytes(b"{}")
    return summary


def test_cleanup_inventories_deletes_staging_and_keeps_the_reservation(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary = _staged(paths, taxonomy)
    paths.reservation.write_bytes(b'{"event": "reserved"}\n')
    reservation = paths.reservation.read_bytes()
    capture = summary["capture"]
    attestation = canary.cleanup_staging(
        paths,
        expected_raw_sha256=capture["complete_response_sha256"],
        expected_raw_bytes=capture["complete_response_bytes"],
    )
    assert not paths.staging_dir.exists()
    assert paths.reservation.read_bytes() == reservation
    inventory = {entry["path"]: entry for entry in attestation["inventory"]}
    assert set(inventory) == {
        "drafts",
        "drafts/preview.json",
        "raw-response.bin",
        "run-summary.json",
    }
    assert inventory["raw-response.bin"]["sha256"] == capture["complete_response_sha256"]
    assert attestation["inventory_sha256"] == canonical_json_hash(
        {"inventory": attestation["inventory"]}
    )
    assert "content" not in json.dumps(attestation["inventory"])


def test_cleanup_refuses_a_raw_mismatch_and_deletes_nothing(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    _staged(paths, taxonomy)
    with pytest.raises(canary.CanaryRefusal, match="raw_capture_mismatch"):
        canary.cleanup_staging(paths, expected_raw_sha256="0" * 64, expected_raw_bytes=1)
    assert paths.raw.exists()


def test_cleanup_refuses_links_without_following_them(
    paths: canary.CanaryPaths, tmp_path: Path
) -> None:
    paths.staging_dir.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    try:
        os.symlink(outside, paths.staging_dir / "link")
    except OSError:
        pytest.skip("symlink creation is not permitted on this host")
    with pytest.raises(canary.CanaryRefusal, match="staging_link_refused"):
        canary.cleanup_staging(paths, expected_raw_sha256=None, expected_raw_bytes=None)
    assert outside.read_bytes() == b"keep"


def _fake_git(outputs: dict[str, str]) -> Callable[[Any], str]:
    def git(args: Any) -> str:
        return outputs.get(args[0], "")

    return git


def test_verify_cleanup_reports_each_check(paths: canary.CanaryPaths) -> None:
    clean = canary.verify_cleanup(paths, base_sha=SHA, git=_fake_git({}))
    assert clean == dict.fromkeys(clean, True)
    assert len(clean) == 7
    residue = canary.verify_cleanup(
        paths,
        base_sha=SHA,
        git=_fake_git({"status": "!! staging/raw-response.bin\n", "log": ".claude/runtime/x\n"}),
    )
    assert residue["no_staging_residue"] is False
    assert residue["no_runtime_path_in_commit_range"] is False
    paths.staging_dir.mkdir()
    paths.fixture.write_text('{"schema_version": 1}')
    paths.report.write_text("contact someone@example.com")
    failing = canary.verify_cleanup(paths, base_sha=SHA, git=_fake_git({}))
    assert failing["staging_root_absent"] is False
    assert failing["fixture_valid_or_absent"] is False
    assert failing["report_screening_clean_or_absent"] is False


# ---------------------------------------------------------------------------
# CLI post-run commands (temporary paths only).
# ---------------------------------------------------------------------------


def test_cli_project_is_create_only_and_requires_staged_decisions(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [record(1)]
    summary = run_pipeline(paths, Recorder(body_of(records)), taxonomy)
    canary.exclusive_write(paths.summary, json.dumps(summary).encode())
    span = _balanced_excerpt(records[0]["content"])
    decisions = paths.staging_dir / "decisions.json"
    decisions.write_text(json.dumps({"selected": [_decision(0, "first_converted", span)]}))
    assert canary.main(["project", "--decisions", str(decisions)], paths=paths) == 0
    canary.validate_fixture(json.loads(paths.projection_preview.read_text()))
    assert canary.main(["project", "--decisions", str(decisions)], paths=paths) == 2
    assert "create_only_target_exists" in capsys.readouterr().out
    outside = paths.runtime_dir / "decisions.json"
    outside.write_text(decisions.read_text())
    assert canary.main(["project", "--decisions", str(outside)], paths=paths) == 2
    assert "decisions_outside_staging" in capsys.readouterr().out
    assert not paths.fixture.exists()


def test_cli_eligibility_is_categorical(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [record(1), record(2, content=escaped("<p>mail hr@example.com</p>"))]
    summary = run_pipeline(paths, Recorder(body_of(records)), taxonomy)
    canary.exclusive_write(paths.summary, json.dumps(summary).encode())
    assert canary.main(["eligibility"], paths=paths) == 0
    out = capsys.readouterr().out
    rows = json.loads(out)["eligible"]
    assert [r["screening_hits"] for r in rows] == [[], ["email"]]
    assert "example.com" not in out
    assert "Senior Software Engineer" not in out
