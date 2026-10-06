"""Offline tests for the Phase 4 S2c live-canary harness (ADR 0017).

Mocks and fakes only: every test runs with real network transports and DNS
resolution disabled, and none creates the real staging directory or
attempt reservation (`_no_live_side_effects`). The projected fixture and the
report do not exist yet; every record here is synthetic.
"""

from __future__ import annotations

import ast
import asyncio
import dataclasses
import hashlib
import html
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
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


class _NoopContainment:
    """Only for fake processes: never assigns anything (their pid is the
    pytest process itself)."""

    def assign(self, pid: int) -> None:
        return None

    def close(self) -> None:
        return None


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
    paths.report.write_text("# S2c report\n", encoding="utf-8")
    binding = canary.CleanupBinding(SHA, CANDIDATE, None, canary.file_sha256(paths.report))
    canary.cleanup_staging(
        paths, expected_raw_sha256=None, expected_raw_bytes=None, binding=binding, git=_git()
    )
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
    stdin = None
    pid = os.getpid()  # a live process: the OS query never confirms death

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
    outcome = _run_live(paths, ["x"], deadline_seconds=0.01, containment_factory=_NoopContainment)
    assert outcome == "FAIL-CLOSED:worker_termination_unconfirmed"


def test_worker_refuses_without_its_preconditions(paths: canary.CanaryPaths) -> None:
    # No live env, no supervisor token, no reservation, no staging.
    assert canary.worker_main(paths, env={}, token="") == 3
    assert canary.worker_main(paths, env=_LIVE_ENV, token="") == 3


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
    # Without an eligible converted record, nothing is selected.
    assert canary.expected_selection(rows, frozenset({1, 2})) == []
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
        pytest.param("a" * 2002, 0, 2001, "excerpt_code_point_cap", id="code_points"),
        pytest.param("\U0001f600" * 1026, 0, 1025, "excerpt_utf8_byte_cap", id="utf8_bytes"),
        pytest.param("abc", 2, 1, "excerpt_offsets_invalid", id="inverted"),
        pytest.param("abc", 0, 4, "excerpt_offsets_invalid", id="past_end"),
        pytest.param("ab\ud800cd", 0, 4, "excerpt_not_utf8_encodable", id="surrogate"),
    ],
)
def test_excerpt_bounds_refuse(content: str, start: int, end: int, kind: str) -> None:
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.check_excerpt_bounds(content, start, end)
    assert refusal.value.kind == kind


def test_excerpt_bounds_accept_exact_limits() -> None:
    canary.check_excerpt_bounds("a" * 2001, 0, 2000)
    canary.check_excerpt_bounds("\U0001f600" * 1025, 1, 1025)


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
    canary.validate_fixture(document, taxonomy)
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
            "decisions_invalid",
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
    decisions = {"selected": [_decision(0, "first_converted", (0, len(content) - 1))]}
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
        canary.validate_fixture(document, taxonomy)
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


CANDIDATE = "c" * 40


def _git(
    *,
    head: str = CANDIDATE,
    status: str = "",
    range_objects: str = "",
    index: str = "",
    changed: str = "",
    log: str = "",
) -> Callable[[Any], str]:
    """A fake `git` for the cleanup binding; `rev-list` always lists the
    candidate as descending from the base."""

    def git(args: Any) -> str:
        outputs = {
            "rev-parse": head + "\n",
            "status": status,
            "rev-list": CANDIDATE + "\n" + range_objects,
            "ls-files": index,
            "diff": changed,
            "log": log,
        }
        return outputs.get(args[0], "")

    return git


def _approved(
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
    *,
    with_fixture: bool = True,
    report_text: str = "# S2c live canary report\n\nAggregates only.\n",
) -> tuple[dict[str, Any], canary.CleanupBinding]:
    """A staged run plus an approved fixture/report pair bound to CANDIDATE."""
    records = [record(1)]
    summary = run_pipeline(paths, Recorder(body_of(records)), taxonomy)
    canary.exclusive_write(paths.summary, json.dumps(summary).encode())
    (paths.staging_dir / "drafts").mkdir()
    (paths.staging_dir / "drafts" / "preview.json").write_bytes(b"{}")
    fixture_sha = None
    if with_fixture:
        span = _balanced_excerpt(records[0]["content"])
        document = canary.build_projection(
            paths.raw.read_bytes(),
            summary,
            {"selected": [_decision(0, "first_converted", span)]},
            taxonomy,
        )
        paths.fixture.write_text(json.dumps(document, indent=2), encoding="utf-8")
        fixture_sha = canary.file_sha256(paths.fixture)
    paths.report.write_text(report_text, encoding="utf-8")
    binding = canary.CleanupBinding(SHA, CANDIDATE, fixture_sha, canary.file_sha256(paths.report))
    return summary, binding


def _cleanup(
    paths: canary.CanaryPaths,
    summary: dict[str, Any],
    binding: canary.CleanupBinding,
    git: Callable[[Any], str],
) -> dict[str, Any]:
    capture = summary["capture"]
    return canary.cleanup_staging(
        paths,
        expected_raw_sha256=capture["complete_response_sha256"],
        expected_raw_bytes=capture["complete_response_bytes"],
        binding=binding,
        git=git,
    )


def test_cleanup_inventories_deletes_staging_and_keeps_the_reservation(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary, binding = _approved(paths, taxonomy)
    paths.reservation.write_bytes(b'{"event": "reserved"}\n')
    reservation = paths.reservation.read_bytes()
    raw = paths.raw.read_bytes()
    attestation = _cleanup(paths, summary, binding, _git())
    assert not paths.staging_dir.exists()
    assert paths.reservation.read_bytes() == reservation
    assert attestation["pre_deletion_checks"] == dict.fromkeys(
        attestation["pre_deletion_checks"], True
    )
    assert attestation["raw_blob"] == canary.git_blob_id(raw)
    inventory = {entry["path"]: entry for entry in attestation["inventory"]}
    assert set(inventory) == {
        "drafts",
        "drafts/preview.json",
        "raw-response.bin",
        "run-summary.json",
    }
    assert inventory["raw-response.bin"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert attestation["inventory_sha256"] == canonical_json_hash(
        {"inventory": attestation["inventory"]}
    )
    assert "content" not in json.dumps(attestation["inventory"])
    checks = canary.verify_cleanup(
        paths, binding=binding, raw_blob=attestation["raw_blob"], git=_git()
    )
    assert checks == dict.fromkeys(checks, True)
    assert len(checks) == 14


def test_git_blob_id_matches_git() -> None:
    assert canary.git_blob_id(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_cleanup_refuses_a_raw_mismatch_and_deletes_nothing(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    _, binding = _approved(paths, taxonomy)
    with pytest.raises(canary.CanaryRefusal, match="raw_capture_mismatch"):
        canary.cleanup_staging(
            paths, expected_raw_sha256="0" * 64, expected_raw_bytes=1, binding=binding, git=_git()
        )
    assert paths.raw.exists()


def test_raw_response_copied_into_the_report_blocks_cleanup(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    """Approved hash and clean screening do not make a raw copy publishable."""
    summary = run_pipeline(paths, Recorder(body_of([record(1)])), taxonomy)
    raw_text = paths.raw.read_text(encoding="utf-8")
    paths.raw.unlink()
    shutil.rmtree(paths.staging_dir)
    summary, binding = _approved(paths, taxonomy, report_text=f"# Report\n\n{raw_text}\n")
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, binding, _git())
    assert refusal.value.kind == "publication_binding_failed:raw_bytes_absent_from_tracked_paths"
    assert paths.raw.exists()


@pytest.mark.parametrize("where", ["other_tracked_path", "commit_range_blob", "index_blob"])
def test_raw_response_under_any_filename_blocks_cleanup(
    where: str, paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, tmp_path: Path
) -> None:
    summary, binding = _approved(paths, taxonomy)
    raw = paths.raw.read_bytes()
    blob = canary.git_blob_id(raw)
    elsewhere = tmp_path / "innocent-name.json"
    elsewhere.write_bytes(raw)
    git = {
        "other_tracked_path": _git(changed=str(elsewhere) + "\n"),
        "commit_range_blob": _git(range_objects=f"{blob} docs/innocent.md\n"),
        "index_blob": _git(index=f"100644 {blob} 0\tdocs/innocent.md\n"),
    }[where]
    expected = {
        "other_tracked_path": "raw_bytes_absent_from_tracked_paths",
        "commit_range_blob": "raw_blob_absent_from_commit_range",
        "index_blob": "raw_blob_absent_from_index",
    }[where]
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, binding, git)
    assert refusal.value.kind == f"publication_binding_failed:{expected}"
    assert paths.raw.exists()


def _set_reviewer(paths: canary.CanaryPaths) -> None:
    document = json.loads(paths.fixture.read_text(encoding="utf-8"))
    document["selected"][0]["review"]["reviewer"] = "someone else"
    paths.fixture.write_text(json.dumps(document, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutate", "failed"),
    [
        pytest.param(_set_reviewer, "fixture_matches_approval", id="fixture_after_approval"),
        pytest.param(
            lambda p: p.report.write_text("# changed\n", encoding="utf-8"),
            "report_matches_approval",
            id="report_after_approval",
        ),
        pytest.param(
            lambda p: p.fixture.unlink(), "fixture_matches_approval", id="fixture_missing"
        ),
    ],
)
def test_artifact_changes_after_approval_block_cleanup(
    mutate: Callable[[canary.CanaryPaths], Any],
    failed: str,
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
) -> None:
    summary, binding = _approved(paths, taxonomy)
    mutate(paths)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, binding, _git())
    assert refusal.value.kind == f"publication_binding_failed:{failed}"
    assert paths.raw.exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publication_safe", False),
        ("excerpt_replay_disposition", "not_performed"),
        ("full_capture_fidelity_disposition", "not_performed"),
        ("full_capture_fidelity_disposition", "unknown"),
        ("reviewer", ""),
    ],
)
def test_unapproved_review_states_block_cleanup_even_when_hash_bound(
    field: str, value: Any, paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary, _ = _approved(paths, taxonomy)
    document = json.loads(paths.fixture.read_text(encoding="utf-8"))
    document["selected"][0]["review"][field] = value
    paths.fixture.write_text(json.dumps(document, indent=2), encoding="utf-8")
    binding = canary.CleanupBinding(
        SHA, CANDIDATE, canary.file_sha256(paths.fixture), canary.file_sha256(paths.report)
    )
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, binding, _git())
    assert refusal.value.kind == "publication_binding_failed:fixture_matches_approval"


@pytest.mark.parametrize(
    ("git", "failed"),
    [
        (_git(head="d" * 40), "head_is_candidate"),
        (_git(status=" M docs/x.md\n"), "tree_clean"),
    ],
)
def test_cleanup_is_bound_to_the_clean_reviewed_candidate(
    git: Callable[[Any], str], failed: str, paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary, binding = _approved(paths, taxonomy)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, binding, git)
    assert refusal.value.kind == f"publication_binding_failed:{failed}"


def test_malformed_binding_blocks_cleanup(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary, binding = _approved(paths, taxonomy)
    bad = canary.CleanupBinding(SHA, "not-a-sha", binding.fixture_sha256, binding.report_sha256)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, bad, _git())
    assert refusal.value.kind == "publication_binding_failed:binding_well_formed"


def test_findings_only_state_requires_an_absent_fixture(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary, binding = _approved(paths, taxonomy, with_fixture=False)
    paths.fixture.write_text("{}", encoding="utf-8")
    with pytest.raises(canary.CanaryRefusal) as refusal:
        _cleanup(paths, summary, binding, _git())
    assert refusal.value.kind == "publication_binding_failed:fixture_matches_approval"
    paths.fixture.unlink()
    _cleanup(paths, summary, binding, _git())
    assert not paths.staging_dir.exists()


def test_cleanup_refuses_links_without_following_them(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex, tmp_path: Path
) -> None:
    summary, binding = _approved(paths, taxonomy)
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"keep")
    try:
        os.symlink(outside, paths.staging_dir / "link")
    except OSError:
        pytest.skip("symlink creation is not permitted on this host")
    with pytest.raises(canary.CanaryRefusal, match="staging_link_refused"):
        _cleanup(paths, summary, binding, _git())
    assert outside.read_bytes() == b"keep"


def test_verify_cleanup_reports_each_failure(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    summary, binding = _approved(paths, taxonomy)
    blob = canary.git_blob_id(paths.raw.read_bytes())
    _cleanup(paths, summary, binding, _git())
    residue = canary.verify_cleanup(
        paths,
        binding=binding,
        raw_blob=blob,
        git=_git(
            status="!! staging/raw-response.bin\n",
            log=".claude/runtime/x\n",
            range_objects=f"{blob} docs/x.md\n",
        ),
    )
    for name in (
        "no_staging_residue",
        "tree_clean",
        "no_runtime_path_in_commit_range",
        "raw_blob_absent_from_commit_range",
    ):
        assert residue[name] is False
    paths.staging_dir.mkdir()
    _set_reviewer(paths)
    failing = canary.verify_cleanup(paths, binding=binding, raw_blob=blob, git=_git())
    assert failing["staging_root_absent"] is False
    assert failing["fixture_matches_approval"] is False


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
    canary.validate_fixture(json.loads(paths.projection_preview.read_text()), taxonomy)
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


# ---------------------------------------------------------------------------
# Correction 1: fidelity dispositions.
# ---------------------------------------------------------------------------

_OBSERVED: dict[str, Any] = {"run_verdict": None, "findings": []}


@pytest.mark.parametrize(
    ("full", "replay", "expected"),
    [
        pytest.param(
            "faithful",
            "not_performed",
            (canary.Verdict.INCONCLUSIVE, ["fidelity_review_unavailable"]),
            id="excerpt_replay_unavailable",
        ),
        pytest.param(
            "not_performed",
            "faithful",
            (canary.Verdict.INCONCLUSIVE, ["fidelity_review_unavailable"]),
            id="full_capture_unavailable",
        ),
        pytest.param("faithful", "faithful", (canary.Verdict.PASS, []), id="both_faithful"),
        pytest.param(
            "mismatch",
            "faithful",
            (canary.Verdict.PASS_WITH_FINDINGS, ["fidelity_mismatch"]),
            id="full_capture_mismatch",
        ),
        pytest.param(
            "faithful",
            "mismatch",
            (canary.Verdict.PASS_WITH_FINDINGS, ["fidelity_mismatch"]),
            id="excerpt_replay_mismatch",
        ),
    ],
)
def test_each_fidelity_disposition_in_isolation(full: str, replay: str, expected: Any) -> None:
    assert canary.compute_verdict(_OBSERVED, _selected(full, replay)) == expected


@pytest.mark.parametrize("value", ["maybe", "", None, ["faithful"], 1])
def test_fidelity_outside_the_closed_vocabulary_fails_closed(value: Any) -> None:
    for full, replay in ((value, "faithful"), ("faithful", value)):
        assert canary.compute_verdict(_OBSERVED, _selected(full, replay)) == (
            canary.Verdict.FAIL_CLOSED,
            ["review_disposition_invalid"],
        )


def test_fidelity_precedence_controls() -> None:
    # Unavailable review outranks a mismatch; a settled FAIL-CLOSED run outranks both.
    assert canary.compute_verdict(_OBSERVED, _selected("mismatch", "not_performed")) == (
        canary.Verdict.INCONCLUSIVE,
        ["fidelity_review_unavailable"],
    )
    failed = {"run_verdict": "FAIL-CLOSED", "run_kind": "record_cap_exceeded"}
    assert canary.compute_verdict(failed, _selected("faithful", "not_performed")) == (
        canary.Verdict.FAIL_CLOSED,
        ["record_cap_exceeded"],
    )
    assert canary.compute_verdict(
        _OBSERVED, _selected("faithful", "faithful"), cleanup_passed=False
    )[0] is (canary.Verdict.FAIL_CLOSED)
    vocabulary = {"faithful", "mismatch", "not_performed"}
    assert vocabulary == canary.REVIEW_DISPOSITIONS


# ---------------------------------------------------------------------------
# Correction 1: converted-first selection and proper excerpts.
# ---------------------------------------------------------------------------


def test_selection_is_empty_without_an_eligible_converted_record() -> None:
    assert (
        canary.expected_selection(_rows("absent", "mixed_literal_and_escaped_markup"), frozenset())
        == []
    )
    assert canary.expected_selection(_rows("absent", "converted", "blank"), frozenset({1})) == []
    assert canary.expected_selection(_rows("converted", disposition="invalid"), frozenset()) == []


def test_distinct_outcomes_are_eligible_only_after_the_first_converted_record() -> None:
    rows = _rows("absent", "blank", "converted", "blank", "absent")
    assert canary.expected_selection(rows, frozenset()) == [
        (2, "first_converted"),
        (3, "distinct_outcome"),
        (4, "distinct_outcome"),
    ]
    assert canary.expected_selection(_rows("converted", "absent"), frozenset()) == [
        (0, "first_converted"),
        (1, "distinct_outcome"),
    ]


def test_negative_only_projection_is_refused(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    raw, summary = _observed_run(
        paths, taxonomy, [record(1, content=None), record(2, content="  ")]
    )
    decisions = {"selected": [_decision(0, "distinct_outcome", None)]}
    with pytest.raises(canary.CanaryRefusal, match="no_converted_sample"):
        canary.build_projection(raw, summary, decisions, taxonomy)


_SHORT = escaped("<p>Build Python services.</p>")


@pytest.mark.parametrize(
    ("content", "start", "end"),
    [
        pytest.param(_SHORT, 0, len(_SHORT), id="short_description"),
        pytest.param("x", 0, 1, id="one_character"),
        pytest.param("", 0, 0, id="empty"),
    ],
)
def test_complete_source_excerpt_is_refused_however_short(
    content: str, start: int, end: int
) -> None:
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.check_excerpt_bounds(content, start, end)
    assert refusal.value.kind == "excerpt_is_complete_source"


def test_short_description_regression_through_the_builder(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    records = [record(1, content=_SHORT)]
    raw, summary = _observed_run(paths, taxonomy, records)
    whole = {"selected": [_decision(0, "first_converted", (0, len(_SHORT)))]}
    with pytest.raises(canary.CanaryRefusal, match="excerpt_is_complete_source"):
        canary.build_projection(raw, summary, whole, taxonomy)
    # Stable proper-excerpt control: the inner text only.
    inner = (len(escaped("<p>")), len(_SHORT) - len(escaped("</p>")))
    proper = {"selected": [_decision(0, "first_converted", inner)]}
    document = canary.build_projection(raw, summary, proper, taxonomy)
    assert document["replay_envelope"]["jobs"][0]["content"] == "Build Python services."
    assert document["selected"][0]["golden_expectations"]["content_outcome"] == "converted"


def _valid_document(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> dict[str, Any]:
    records = [record(1)]
    raw, summary = _observed_run(paths, taxonomy, records)
    span = _balanced_excerpt(records[0]["content"])
    return canary.build_projection(
        raw, summary, {"selected": [_decision(0, "first_converted", span)]}, taxonomy
    )


def _whole_source_lineage(document: dict[str, Any]) -> None:
    lineage = document["selected"][0]["lineage"]
    length = lineage["excerpt_code_points"]
    lineage.update(
        excerpt_start_code_point=0,
        excerpt_end_code_point_exclusive=length,
        original_content_code_points=length,
    )


@pytest.mark.parametrize(
    ("mutate", "kind"),
    [
        pytest.param(_whole_source_lineage, "excerpt_is_complete_source", id="whole_source"),
        pytest.param(
            lambda d: d["selected"][0]["review"].__setitem__("publication_safe", False),
            "review_not_publication_safe",
            id="unsafe",
        ),
        pytest.param(
            lambda d: d["selected"][0]["review"].__setitem__(
                "excerpt_replay_disposition", "not_performed"
            ),
            "review_not_performed",
            id="excerpt_review_unperformed",
        ),
        pytest.param(
            lambda d: d["selected"][0]["review"].__setitem__(
                "full_capture_fidelity_disposition", "pending"
            ),
            "review_not_performed",
            id="malformed_disposition",
        ),
        pytest.param(
            lambda d: d["selected"][0]["review"].__setitem__("reviewer", " "),
            "review_reviewer_invalid",
            id="blank_reviewer",
        ),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("selection_reason", "distinct_outcome"),
            "first_sample_not_converted",
            id="negative_only",
        ),
        pytest.param(
            lambda d: (
                d.__setitem__("selected", []),
                d["replay_envelope"].update(jobs=[], meta={"total": 0}),
            ),
            "fixture_without_converted_sample",
            id="empty",
        ),
    ],
)
def test_validate_fixture_rejects_unapproved_or_whole_source_states(
    mutate: Callable[[dict[str, Any]], Any],
    kind: str,
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
) -> None:
    document = _valid_document(paths, taxonomy)
    canary.validate_fixture(document, taxonomy)  # control
    mutate(document)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.validate_fixture(document, taxonomy)
    assert refusal.value.kind == kind


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(
            lambda d: d["selected"][0].__setitem__("ordinal", "SYNTHETIC"), id="ordinal_str"
        ),
        pytest.param(lambda d: d["selected"][0].__setitem__("ordinal", True), id="ordinal_bool"),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("excerpt", {"start": "0", "end": 9}),
            id="excerpt",
        ),
        pytest.param(lambda d: d["selected"][0].__setitem__("extra", 1), id="extra_key"),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("publication_safe", "yes"), id="safe_str"
        ),
        pytest.param(
            lambda d: d["selected"][0].__setitem__("selection_reason", "best"), id="reason"
        ),
        pytest.param(
            lambda d: d.__setitem__("rejected", [{"ordinal": 1, "reason": "x"}]), id="reject"
        ),
        pytest.param(lambda d: d.__setitem__("selected", "all"), id="selected_type"),
    ],
)
def test_decisions_are_type_checked_before_conversion(
    mutate: Callable[[dict[str, Any]], Any],
) -> None:
    decisions: dict[str, Any] = {"selected": [_decision(0, "first_converted", (1, 5))]}
    canary.validate_decisions(decisions)  # control
    mutate(decisions)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.validate_decisions(decisions)
    assert refusal.value.kind == "decisions_invalid"
    assert "SYNTHETIC" not in str(refusal.value)


# ---------------------------------------------------------------------------
# Correction 1: exclusive supervisor-to-worker authorization.
# ---------------------------------------------------------------------------


def _launched(paths: canary.CanaryPaths) -> str:
    """Reservation, staging, and the supervisor's one-time launch capability."""
    canary.create_reservation(paths.reservation, _preflight(paths, _live_request(paths))).close()
    paths.staging_dir.mkdir()
    token = secrets.token_hex(32)
    line = paths.reservation.read_bytes().splitlines(keepends=True)[0]
    canary.exclusive_write(
        paths.launch, json.dumps(canary.launch_capability(line, token), sort_keys=True).encode()
    )
    return token


@pytest.fixture
def pipeline_calls(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Replaces the live pipeline and forbids any real transport construction."""
    calls: list[Path] = []

    async def fake(_: Any, raw_path: Path, __: Any) -> dict[str, Any]:
        calls.append(raw_path)
        return {"run_verdict": "INCONCLUSIVE", "run_kind": "http_status:503"}

    def no_transport(*_: Any, **__: Any) -> None:
        raise AssertionError("transport constructed")

    monkeypatch.setattr(canary, "run_canary_pipeline", fake)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "__init__", no_transport)
    return calls


def test_worker_with_its_supervisor_capability_runs_once(
    paths: canary.CanaryPaths, pipeline_calls: list[Path]
) -> None:
    token = _launched(paths)
    assert canary.worker_main(paths, env=_LIVE_ENV, token=token, in_containment=lambda: True) == 0
    assert pipeline_calls == [paths.raw]
    claim = json.loads(paths.claim.read_text())
    launch = json.loads(paths.launch.read_text())
    assert (
        claim["token_sha256"]
        == launch["token_sha256"]
        == hashlib.sha256(token.encode()).hexdigest()
    )
    assert token not in paths.launch.read_text()
    # Duplicate launch with the same capability is refused before any transport.
    assert canary.worker_main(paths, env=_LIVE_ENV, token=token, in_containment=lambda: True) == 3
    assert pipeline_calls == [paths.raw]


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(lambda p, t: "", id="direct_no_token"),
        pytest.param(lambda p, t: secrets.token_hex(32), id="wrong_token"),
        pytest.param(lambda p, t: (p.launch.unlink(), t)[1], id="launch_missing"),
        pytest.param(
            lambda p, t: (
                p.launch.write_text(
                    json.dumps({**json.loads(p.launch.read_text()), "advisory_sha": "b" * 40})
                ),
                t,
            )[1],
            id="launch_identity_mismatch",
        ),
        pytest.param(
            lambda p, t: (
                p.reservation.write_bytes(p.reservation.read_bytes() + b'{"event": "terminal"}\n'),
                t,
            )[1],
            id="reservation_closed",
        ),
        pytest.param(
            lambda p, t: (
                p.reservation.write_bytes(
                    p.reservation.read_bytes().replace(b"discord", b"gitlab")
                ),
                t,
            )[1],
            id="reservation_altered",
        ),
        pytest.param(lambda p, t: (p.raw.write_bytes(b"partial"), t)[1], id="raw_residue"),
    ],
)
def test_worker_refuses_without_a_valid_supervisor_launch(
    tamper: Callable[[canary.CanaryPaths, str], str],
    paths: canary.CanaryPaths,
    pipeline_calls: list[Path],
) -> None:
    token = tamper(paths, _launched(paths))
    assert canary.worker_main(paths, env=_LIVE_ENV, token=token, in_containment=lambda: True) == 3
    assert pipeline_calls == []
    assert not paths.claim.exists()


def test_restart_after_the_request_began_is_refused(
    paths: canary.CanaryPaths, pipeline_calls: list[Path]
) -> None:
    """Crash residue: the claim exists but no raw capture or summary does."""
    token = _launched(paths)
    canary.claim_worker(paths, token)
    assert not paths.raw.exists() and not paths.summary.exists()
    assert canary.worker_main(paths, env=_LIVE_ENV, token=token, in_containment=lambda: True) == 3
    assert pipeline_calls == []


def test_concurrent_worker_claims_admit_exactly_one(paths: canary.CanaryPaths) -> None:
    token = _launched(paths)
    results: list[str] = []
    barrier = threading.Barrier(8)

    def attempt() -> None:
        barrier.wait()
        try:
            canary.claim_worker(paths, token)
            results.append("claimed")
        except canary.CanaryRefusal as refusal:
            results.append(refusal.kind)

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["claimed"] + ["worker_already_claimed"] * 7


def test_direct_worker_cli_cannot_self_authorize() -> None:
    completed = subprocess.run(
        [sys.executable, str(HARNESS), "_worker"],
        cwd=BACKEND_DIR,
        env={**os.environ, **_LIVE_ENV},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )
    # Refused either by the missing capability or by parent-loss containment
    # (stdin is not a supervisor pipe); never authorized.
    assert completed.returncode in (3, canary.PARENT_LOST_EXIT)
    assert (completed.stdout, completed.stderr) == ("", "")


class _Stdin:
    def __init__(self, data: bytes, *, tty: bool = False) -> None:
        self.buffer = io.BytesIO(data)
        self.tty = tty

    def isatty(self) -> bool:
        return self.tty


def test_worker_entry_reads_the_token_and_arms_parent_loss_containment(
    paths: canary.CanaryPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[Any] = []
    monkeypatch.setattr(canary, "start_parent_loss_watchdog", lambda s: events.append(("watch", s)))

    def fake_worker(_: Any, *, env: Any, token: str) -> int:
        events.append(("worker", token))
        return 0

    monkeypatch.setattr(canary, "worker_main", fake_worker)
    stdin = _Stdin(b"ab12\nignored")
    assert canary.worker_entry(paths, stdin) == 0
    assert events == [("watch", stdin.buffer), ("worker", "ab12")]
    events.clear()
    assert canary.worker_entry(paths, _Stdin(b"ab12\n", tty=True)) == 3
    assert events == []


_CLAIMING_WORKER = """
import json, sys
from pathlib import Path
from scripts import run_greenhouse_s2c_canary as m
p = m.CanaryPaths(**{{k: Path(v) for k, v in json.loads(sys.argv[1]).items()}})
token = sys.stdin.buffer.readline().decode().strip()
m.claim_worker(p, token)
p.summary.write_text(json.dumps({{"run_verdict": None, "run_kind": None}}))
"""


def test_supervisor_launches_its_worker_with_a_one_time_stdin_capability(
    paths: canary.CanaryPaths,
) -> None:
    layout = {f.name: str(getattr(paths, f.name)) for f in dataclasses.fields(paths)}
    argv = [sys.executable, "-c", _CLAIMING_WORKER.format(), json.dumps(layout)]
    outcome = canary.run_live(
        _live_request(paths),
        env={**os.environ, **_LIVE_ENV, "PYTHONPATH": str(BACKEND_DIR)},
        paths=paths,
        head_sha=lambda: SHA,
        tree_is_clean=lambda: True,
        worker_argv=argv,
    )
    assert outcome == "OBSERVED:pending_post_run_review"
    launch = json.loads(paths.launch.read_text())
    assert json.loads(paths.claim.read_text())["token_sha256"] == launch["token_sha256"]
    line = paths.reservation.read_bytes().splitlines(keepends=True)[0]
    assert launch["reservation_sha256"] == hashlib.sha256(line).hexdigest()
    assert launch["advisory_sha"] == SHA


# ---------------------------------------------------------------------------
# Correction 1: supervisor interruption and parent-loss containment.
# ---------------------------------------------------------------------------


class _ScriptedProcess:
    """Fake worker: the first wait raises `first`; it exits after
    `stops_needed` stop calls (never, when larger than two)."""

    stdin = None
    pid = os.getpid()  # a live process: the OS query never confirms death

    def __init__(self, first: BaseException, stops_needed: int = 1) -> None:
        self.first: BaseException | None = first
        self.stops: list[str] = []
        self.stops_needed = stops_needed
        self.returncode: int | None = None

    def wait(self, timeout: float | None = None) -> int:
        if self.first is not None:
            first, self.first = self.first, None
            raise first
        if len(self.stops) >= self.stops_needed:
            self.returncode = -9
            return -9
        raise subprocess.TimeoutExpired("worker", timeout or 0)

    def terminate(self) -> None:
        self.stops.append("terminate")

    def kill(self) -> None:
        self.stops.append("kill")

    def poll(self) -> int | None:
        return self.returncode


@pytest.mark.parametrize(
    ("first", "stops_needed", "stops", "confirmed"),
    [
        pytest.param(KeyboardInterrupt(), 1, ["terminate"], True, id="interrupt"),
        pytest.param(OSError("wait failed"), 1, ["terminate"], True, id="supervision_failure"),
        pytest.param(KeyboardInterrupt(), 2, ["terminate", "kill"], True, id="graceful_failed"),
        pytest.param(KeyboardInterrupt(), 3, ["terminate", "kill"], False, id="unkillable"),
    ],
)
def test_abnormal_supervisor_exit_stops_and_reaps_the_worker(
    first: BaseException,
    stops_needed: int,
    stops: list[str],
    confirmed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _ScriptedProcess(first, stops_needed)
    monkeypatch.setattr(canary.subprocess, "Popen", lambda *_, **__: process)
    with pytest.raises(canary.SupervisionAborted) as aborted:
        canary.supervise_worker(["x"], deadline_seconds=5, grace_seconds=0.01)
    assert aborted.value.confirmed is confirmed
    assert process.stops == stops


@pytest.mark.parametrize(
    ("stops_needed", "outcome"),
    [
        (1, "FAIL-CLOSED:supervisor_interrupted"),
        (3, "FAIL-CLOSED:worker_termination_unconfirmed"),
    ],
)
def test_interrupted_run_live_records_after_reaping_and_keeps_the_reservation(
    stops_needed: int, outcome: str, paths: canary.CanaryPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = _ScriptedProcess(KeyboardInterrupt(), stops_needed)
    monkeypatch.setattr(canary.subprocess, "Popen", lambda *_, **__: process)
    with pytest.raises(canary.SupervisionAborted):
        _run_live(paths, ["x"], containment_factory=_NoopContainment)
    lines = _reservation_lines(paths)
    assert [line["event"] for line in lines] == ["reserved", "terminal"]
    assert lines[-1]["outcome"] == outcome
    assert process.stops
    with pytest.raises(canary.CanaryRefusal, match="attempt_already_reserved"):
        _preflight(paths, _live_request(paths))


def test_real_worker_is_reaped_when_supervision_is_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[subprocess.Popen[bytes]] = []

    class InterruptingPopen(subprocess.Popen[bytes]):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.interrupt = True
            started.append(self)

        def wait(self, timeout: float | None = None) -> int:
            if self.interrupt:
                self.interrupt = False
                raise KeyboardInterrupt
            return super().wait(timeout)

    monkeypatch.setattr(canary.subprocess, "Popen", InterruptingPopen)
    with pytest.raises(canary.SupervisionAborted) as aborted:
        canary.supervise_worker(_SLEEPER, deadline_seconds=30, grace_seconds=5)
    assert aborted.value.confirmed is True
    assert started[0].poll() is not None


_WATCHED = (
    "import sys, time\n"
    "from scripts import run_greenhouse_s2c_canary as m\n"
    "m.start_parent_loss_watchdog(sys.stdin.buffer)\n"
    "time.sleep(30)\n"
)


def test_parent_loss_watchdog_ends_the_worker_when_the_pipe_closes() -> None:
    child = subprocess.Popen(
        [sys.executable, "-c", _WATCHED], cwd=BACKEND_DIR, stdin=subprocess.PIPE
    )
    try:
        assert child.stdin is not None
        child.stdin.write(b"token\n")
        child.stdin.flush()
        time.sleep(0.5)
        assert child.poll() is None
        child.stdin.close()
        assert child.wait(timeout=15) == canary.PARENT_LOST_EXIT
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


def test_killing_the_supervisor_process_ends_its_worker(tmp_path: Path) -> None:
    marker = tmp_path / "worker-ended"
    worker = (
        "import os, sys, time, pathlib\n"
        "from scripts import run_greenhouse_s2c_canary as m\n"
        f"mark = pathlib.Path({str(marker)!r})\n"
        "m.start_parent_loss_watchdog(sys.stdin.buffer,"
        " lambda: (mark.write_text('parent lost'), os._exit(m.PARENT_LOST_EXIT)))\n"
        "time.sleep(30)\n"
    )
    supervisor = (
        "import subprocess, sys, time\n"
        f"child = subprocess.Popen([sys.executable, '-c', {worker!r}], stdin=subprocess.PIPE)\n"
        "print(child.pid, flush=True)\n"
        "time.sleep(30)\n"
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", supervisor], cwd=BACKEND_DIR, stdout=subprocess.PIPE
    )
    assert parent.stdout is not None
    assert parent.stdout.readline().strip()
    time.sleep(0.5)
    parent.kill()
    parent.wait()
    deadline = time.monotonic() + 15
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert marker.read_text() == "parent lost"


# ---------------------------------------------------------------------------
# Correction 1: fail-closed CLI output (stdout/stderr sentinels).
# ---------------------------------------------------------------------------

SENTINEL = "SYNTHETIC_PRIVATE_TEXT"


def _cli(paths: canary.CanaryPaths, argv: list[str], prelude: str = "") -> Any:
    layout = {f.name: str(getattr(paths, f.name)) for f in dataclasses.fields(paths)}
    code = (
        "import json, sys\n"
        "from pathlib import Path\n"
        "from scripts import run_greenhouse_s2c_canary as m\n"
        f"layout = json.loads({json.dumps(layout)!r})\n"
        "p = m.CanaryPaths(**{k: Path(v) for k, v in layout.items()})\n"
        f"{prelude}\n"
        f"raise SystemExit(m.main({argv!r}, paths=p))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120
    )


def _stage_for_cli(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> Path:
    records = [record(1, title=f"{SENTINEL} title")]
    summary = run_pipeline(paths, Recorder(body_of(records)), taxonomy)
    canary.exclusive_write(paths.summary, json.dumps(summary).encode())
    decisions = paths.staging_dir / "decisions.json"
    span = _balanced_excerpt(records[0]["content"])
    decisions.write_text(json.dumps({"selected": [_decision(0, "first_converted", span)]}))
    return decisions


def _assert_categorical(completed: Any, kind: str) -> None:
    assert completed.returncode == 2
    assert json.loads(completed.stdout) == {"kind": kind, "result": "refused"}
    assert completed.stderr == ""
    assert SENTINEL not in completed.stdout + completed.stderr


def test_malformed_decisions_produce_only_categorical_output(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    decisions = _stage_for_cli(paths, taxonomy)
    data = json.loads(decisions.read_text())
    data["selected"][0]["ordinal"] = SENTINEL
    decisions.write_text(json.dumps(data))
    _assert_categorical(
        _cli(paths, ["project", "--decisions", str(decisions)]), "decisions_invalid"
    )
    decisions.write_text("{not json " + SENTINEL)
    _assert_categorical(
        _cli(paths, ["project", "--decisions", str(decisions)]), "decisions_invalid"
    )


@pytest.mark.parametrize(
    ("argv_kind", "target"),
    [("project", "build_projection"), ("eligibility", "published_screening")],
)
def test_post_run_failures_produce_only_categorical_output(
    argv_kind: str, target: str, paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    decisions = _stage_for_cli(paths, taxonomy)
    argv = ["project", "--decisions", str(decisions)] if argv_kind == "project" else ["eligibility"]
    prelude = (
        "def boom(*a, **k):\n"
        f"    raise RuntimeError({SENTINEL!r}) from ValueError({SENTINEL!r})\n"
        f"m.{target} = boom"
    )
    _assert_categorical(_cli(paths, argv, prelude), "operational_failure")
    assert not paths.projection_preview.exists()


def test_cli_interrupt_is_categorical(paths: canary.CanaryPaths) -> None:
    prelude = "def stop(*a, **k):\n    raise KeyboardInterrupt\nm._staged_summary = stop"
    completed = _cli(paths, ["eligibility"], prelude)
    assert completed.returncode == 130
    assert json.loads(completed.stdout) == {"kind": "interrupted", "result": "refused"}
    assert completed.stderr == ""


# ---------------------------------------------------------------------------
# Correction 2: kernel containment ordering and setup failures.
# ---------------------------------------------------------------------------

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Job Object containment")

_TOKEN_SINK = (
    "import sys, pathlib\n"
    "line = sys.stdin.buffer.readline()\n"
    "pathlib.Path(sys.argv[1]).write_bytes(line)\n"
)


@windows_only
def test_kill_on_close_job_is_configured_and_verified() -> None:
    job = canary.KillOnCloseJob()
    try:
        assert canary._kills_on_close(canary._kernel32(), job._handle) is True
    finally:
        job.close()


@windows_only
def test_token_is_released_only_after_kernel_assignment(tmp_path: Path) -> None:
    sink = tmp_path / "token"
    observed: list[bool] = []

    class Recording(canary.KillOnCloseJob):
        def assign(self, pid: int) -> None:
            time.sleep(0.5)  # a worker that already had the token would have written it
            observed.append(sink.exists())
            super().assign(pid)

    job = Recording()
    try:
        result = canary.supervise_worker(
            [sys.executable, "-c", _TOKEN_SINK, str(sink)],
            stdin_payload=b"secret-token\n",
            containment=job,
        )
    finally:
        job.close()
    assert result == canary.WorkerResult("exited", 0)
    assert observed == [False]
    assert sink.read_bytes() == b"secret-token\n"


class _FailingContainment:
    def assign(self, pid: int) -> None:
        raise canary.CanaryRefusal("containment_assignment_failed")

    def close(self) -> None:
        return None


def test_failed_assignment_releases_no_token_and_reaps_the_worker(tmp_path: Path) -> None:
    sink = tmp_path / "token"
    started: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = real_popen(*args, **kwargs)
        started.append(process)
        return process

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(canary.subprocess, "Popen", recording_popen)
        result = canary.supervise_worker(
            [sys.executable, "-c", _TOKEN_SINK, str(sink)],
            stdin_payload=b"secret-token\n",
            containment=_FailingContainment(),
            grace_seconds=5,
        )
    assert result == canary.WorkerResult("containment_failed", None)
    assert started[0].poll() is not None
    assert not sink.exists() or sink.read_bytes() == b""


def test_a_token_is_never_released_without_containment(monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[Any] = []
    monkeypatch.setattr(canary.subprocess, "Popen", lambda *a, **k: launched.append(a))
    with pytest.raises(canary.CanaryRefusal, match="containment_required"):
        canary.supervise_worker(["x"], stdin_payload=b"token\n")
    assert launched == []


def test_unsupported_containment_refuses_before_any_reservation(
    paths: canary.CanaryPaths,
) -> None:
    def unavailable() -> Any:
        raise canary.CanaryRefusal("containment_unavailable")

    with pytest.raises(canary.CanaryRefusal, match="containment_unavailable"):
        _run_live(paths, [sys.executable, "-c", "pass"], containment_factory=unavailable)
    assert not paths.reservation.exists()
    assert not paths.staging_dir.exists()


def test_failed_assignment_in_run_live_is_fail_closed_and_keeps_the_reservation(
    paths: canary.CanaryPaths,
) -> None:
    outcome = _run_live(
        paths,
        [sys.executable, "-c", _TOKEN_SINK, "unused"],
        containment_factory=_FailingContainment,
    )
    assert outcome == "FAIL-CLOSED:containment_assignment_failed"
    assert [line["event"] for line in _reservation_lines(paths)] == ["reserved", "terminal"]
    assert not paths.claim.exists()


def test_non_windows_platforms_refuse_containment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(canary.sys, "platform", "linux")
    with pytest.raises(canary.CanaryRefusal, match="containment_unavailable"):
        canary.KillOnCloseJob()
    assert canary.current_process_kill_on_close() is False
    assert canary.process_has_exited(os.getpid()) is None


def test_worker_refuses_outside_kill_on_close_containment(
    paths: canary.CanaryPaths, pipeline_calls: list[Path]
) -> None:
    token = _launched(paths)
    assert canary.worker_main(paths, env=_LIVE_ENV, token=token, in_containment=lambda: False) == 3
    assert pipeline_calls == []
    assert not paths.claim.exists()


@windows_only
def test_process_state_queries_are_evidence_based() -> None:
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    assert canary.process_has_exited(done.pid) is True
    assert canary.process_has_exited(os.getpid()) is False


# ---------------------------------------------------------------------------
# Correction 2: supervisor loss in every phase (real processes, offline).
# ---------------------------------------------------------------------------

_PHASE_WORKER = r"""
import json, os, re, sys
from pathlib import Path
import httpx
from scripts import run_greenhouse_s2c_canary as m

cfg = json.loads(Path(sys.argv[1]).read_text())
out = Path(cfg["out"])
phase = cfg["phase"]


def mark(name):
    (out / name).write_text(name)


def hog():
    mark("in_phase")
    re.search(r"(a+)+$", "a" * 64 + "!")  # holds the GIL for an unbounded time
    mark("phase_returned")


def block_io():
    mark("in_phase")
    read_end, _write_end = os.pipe()
    os.read(read_end, 1)  # blocking I/O that never completes
    mark("phase_returned")


mark("started")
line = sys.stdin.buffer.readline().strip()
if not line:
    mark("no_token")
    raise SystemExit(3)
mark("token_received")
if phase == "before_claim":
    block_io()
token = line.decode("ascii")
p = m.CanaryPaths(**{k: Path(v) for k, v in cfg["paths"].items()})
record = {
    "event": "reserved",
    "board_token": m.BOARD_TOKEN,
    "advisory_sha": "a" * 40,
    "contract_sha256": "0" * 64,
    "request_fingerprint": m.request_fingerprint(),
    "authorization_identity": "authorization.md",
    "authorization_sha256": "0" * 64,
}
m.create_reservation(p.reservation, record).close()
p.staging_dir.mkdir()
first = p.reservation.read_bytes().splitlines(keepends=True)[0]
m.exclusive_write(p.launch, json.dumps(m.launch_capability(first, token), sort_keys=True).encode())

original_write = m.exclusive_write


def staged_write(path, data):
    if phase == "claim" and path == p.claim:
        original_write(path, data)
        hog()
    if (phase == "capture" and path == p.raw) or (phase == "summary" and path == p.summary):
        hog()
    return original_write(path, data)


m.exclusive_write = staged_write
body = json.dumps({"jobs": [cfg["record"]], "meta": {"total": 1}}).encode()


def handler(request):
    if phase == "request":
        hog()
    if phase == "blocking_io":
        block_io()
    headers = {"content-type": "application/json"}
    return httpx.Response(200, headers=headers, stream=httpx.ByteStream(body))


class OfflineTransport(httpx.MockTransport):
    def __init__(self, *args, **kwargs):
        if phase == "transport":
            hog()
        super().__init__(handler)


httpx.AsyncHTTPTransport = OfflineTransport
if phase == "gil":
    m.claim_worker(p, token)
    hog()
m.worker_main(p, env={m.LIVE_ENV_VAR: m.LIVE_ENV_VALUE}, token=token)
mark("worker_returned")
"""

_PHASE_SUPERVISOR = r"""
import json, subprocess, sys, time
from pathlib import Path
from scripts import run_greenhouse_s2c_canary as m

cfg = json.loads(Path(sys.argv[1]).read_text())
job = m.KillOnCloseJob()
child = subprocess.Popen(
    [sys.executable, cfg["worker_script"], sys.argv[1]], stdin=subprocess.PIPE
)
print(child.pid, flush=True)
if cfg["phase"] != "before_assignment":
    job.assign(child.pid)
    child.stdin.write((cfg["token"] + "\n").encode("ascii"))
    child.stdin.flush()
time.sleep(120)
"""

_PHASE_READY = {"before_assignment": "started", "token_received": "token_received"}


def _wait_for(predicate: Callable[[], bool], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@windows_only
@pytest.mark.parametrize(
    "phase",
    [
        "before_assignment",
        "before_claim",
        "claim",
        "transport",
        "blocking_io",
        "gil",
        "request",
        "capture",
        "summary",
    ],
)
def test_supervisor_loss_contains_the_worker_in_every_phase(phase: str, tmp_path: Path) -> None:
    out = tmp_path / "markers"
    out.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    layout = {
        "runtime_dir": runtime,
        "staging_dir": runtime / "staging",
        "reservation": runtime / "attempt.jsonl",
        "contract": runtime / "contract.md",
        "fixture": tmp_path / "fixture.json",
        "report": tmp_path / "report.md",
    }
    worker_script = tmp_path / "phase_worker.py"
    worker_script.write_text(_PHASE_WORKER, encoding="utf-8")
    supervisor_script = tmp_path / "phase_supervisor.py"
    supervisor_script.write_text(_PHASE_SUPERVISOR, encoding="utf-8")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "out": str(out),
                "phase": phase,
                "token": secrets.token_hex(32),
                "worker_script": str(worker_script),
                "paths": {k: str(v) for k, v in layout.items()},
                "record": record(1),
            }
        ),
        encoding="utf-8",
    )
    supervisor = subprocess.Popen(
        [sys.executable, str(supervisor_script), str(config)],
        cwd=BACKEND_DIR,
        env={**os.environ, "PYTHONPATH": str(BACKEND_DIR)},
        stdout=subprocess.PIPE,
    )
    assert supervisor.stdout is not None
    worker_pid = int(supervisor.stdout.readline())
    try:
        ready = "started" if phase == "before_assignment" else "in_phase"
        assert _wait_for(lambda: (out / ready).exists(), 60), f"{phase}: worker never reached phase"
        supervisor.kill()  # supervisor loss: its job handle closes with it
        supervisor.wait(timeout=30)
        assert _wait_for(lambda: canary.process_has_exited(worker_pid) is True, 15)
        assert not (out / "phase_returned").exists()
        assert not (out / "worker_returned").exists()
        staging = layout["staging_dir"]
        if phase == "before_assignment":
            assert not (out / "token_received").exists()
            assert not staging.exists()
        if phase in ("before_claim", "transport", "blocking_io", "request", "capture"):
            assert not (staging / "run-summary.json").exists()
        if phase in ("transport", "blocking_io", "request", "capture"):
            assert not (staging / "raw-response.bin").exists()
        if phase == "summary":
            assert not (staging / "run-summary.json").exists()
    finally:
        if supervisor.poll() is None:
            supervisor.kill()
        if canary.process_has_exited(worker_pid) is False:
            subprocess.run(["taskkill", "/F", "/PID", str(worker_pid)], capture_output=True)


# ---------------------------------------------------------------------------
# Correction 2: robust shutdown escalation and evidence-based confirmation.
# ---------------------------------------------------------------------------


class _ShutdownProcess:
    """Fake worker that times out at the deadline, then follows a script.
    `pid` defaults to this live test process, so OS evidence never confirms
    its death."""

    stdin = None

    def __init__(
        self,
        *,
        dies_on: tuple[str, ...] = ("terminate",),
        terminate_error: BaseException | None = None,
        kill_error: BaseException | None = None,
        wait_error: BaseException | None = None,
        poll_error: BaseException | None = None,
        pid: int | None = None,
    ) -> None:
        self.pid = os.getpid() if pid is None else pid
        self.calls: list[str] = []
        self.dead = False
        self.deadline_seen = False
        self.dies_on = dies_on
        self.errors = {"terminate": terminate_error, "kill": kill_error}
        self.wait_error = wait_error
        self.poll_error = poll_error

    @property
    def returncode(self) -> int | None:
        return -9 if self.dead else None

    def _stop(self, name: str) -> None:
        self.calls.append(name)
        if name in self.dies_on:
            self.dead = True
        error = self.errors[name]
        if error is not None:
            raise error

    def terminate(self) -> None:
        self._stop("terminate")

    def kill(self) -> None:
        self._stop("kill")

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if not self.deadline_seen:
            self.deadline_seen = True
            raise subprocess.TimeoutExpired("worker", timeout or 0)
        if self.wait_error is not None:
            raise self.wait_error
        if self.dead:
            return -9
        raise subprocess.TimeoutExpired("worker", timeout or 0)

    def poll(self) -> int | None:
        self.calls.append("poll")
        if self.poll_error is not None:
            raise self.poll_error
        return self.returncode


def _supervise_fake(process: _ShutdownProcess, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(canary.subprocess, "Popen", lambda *a, **k: process)
    return canary.supervise_worker(["x"], deadline_seconds=0.01, grace_seconds=0.01)


def test_repeated_wait_failures_still_escalate_and_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _ShutdownProcess(dies_on=("kill",), wait_error=OSError(SENTINEL))
    result = _supervise_fake(process, monkeypatch)
    assert result == canary.WorkerResult("deadline_terminated", -9)
    assert process.calls.count("terminate") == 1 and process.calls.count("kill") == 1
    assert SENTINEL not in repr(result)


def test_terminate_failure_still_escalates_to_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _ShutdownProcess(dies_on=("kill",), terminate_error=OSError(SENTINEL))
    assert _supervise_fake(process, monkeypatch).kind == "deadline_terminated"
    assert "kill" in process.calls


def test_kill_failure_without_evidence_is_unconfirmed(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _ShutdownProcess(dies_on=(), kill_error=OSError(SENTINEL))
    result = _supervise_fake(process, monkeypatch)
    assert result == canary.WorkerResult("termination_unconfirmed", None)
    assert process.calls.count("kill") == 1


@windows_only
def test_poll_failure_falls_back_to_operating_system_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exited = subprocess.Popen([sys.executable, "-c", "pass"])
    exited.wait()
    confirmed = _ShutdownProcess(dies_on=(), poll_error=OSError(SENTINEL), pid=exited.pid)
    assert _supervise_fake(confirmed, monkeypatch).kind == "deadline_terminated"
    alive = _ShutdownProcess(dies_on=(), poll_error=OSError(SENTINEL))
    assert _supervise_fake(alive, monkeypatch).kind == "termination_unconfirmed"


@pytest.mark.parametrize(
    ("kwargs", "confirmed"),
    [
        pytest.param(
            {"terminate_error": KeyboardInterrupt(), "dies_on": ("kill",)}, True, id="terminate"
        ),
        pytest.param({"wait_error": KeyboardInterrupt(), "dies_on": ("kill",)}, True, id="wait"),
        pytest.param(
            {"terminate_error": KeyboardInterrupt(), "dies_on": ()}, False, id="unconfirmed"
        ),
    ],
)
def test_interruption_during_shutdown_completes_shutdown_first(
    kwargs: dict[str, Any], confirmed: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = _ShutdownProcess(**kwargs)
    with pytest.raises(canary.SupervisionAborted) as aborted:
        _supervise_fake(process, monkeypatch)
    assert aborted.value.confirmed is confirmed
    assert "kill" in process.calls
    assert str(aborted.value) == "supervision_aborted"


# ---------------------------------------------------------------------------
# Correction 2: replay-converted-first builder and semantic fixture validation.
# ---------------------------------------------------------------------------

_SPLIT_SOURCE = escaped("<p>Build Python.</p><script>noop</script>")
_SCRIPT_PART = escaped("<script>noop</script>")
_TEXT_PART = escaped("<p>Build Python.</p>")


def test_source_converted_but_excerpt_abstained_first_sample_is_refused(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    records = [record(1, content=_SPLIT_SOURCE)]
    raw, summary = _observed_run(paths, taxonomy, records)
    assert summary["records"][0]["content_outcome"] == "converted"
    start = _SPLIT_SOURCE.index(_SCRIPT_PART)
    abstaining = {"selected": [_decision(0, "first_converted", (start, start + len(_SCRIPT_PART)))]}
    with pytest.raises(canary.CanaryRefusal, match="first_sample_not_converted"):
        canary.build_projection(raw, summary, abstaining, taxonomy)
    # Stable converted-excerpt control from the same source record.
    converting = {"selected": [_decision(0, "first_converted", (0, len(_TEXT_PART)))]}
    document = canary.build_projection(raw, summary, converting, taxonomy)
    assert document["selected"][0]["golden_expectations"]["content_outcome"] == "converted"


def test_later_sample_whose_excerpt_converts_is_refused(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    mixed = escaped("<p>Alpha</p>") + "<b>"
    records = [record(1), record(2, content=mixed)]
    raw, summary = _observed_run(paths, taxonomy, records)
    span = _balanced_excerpt(records[0]["content"])
    decisions = {
        "selected": [
            _decision(0, "first_converted", span),
            _decision(1, "distinct_outcome", (0, len(escaped("<p>Alpha</p>")))),
        ]
    }
    with pytest.raises(canary.CanaryRefusal, match="distinct_outcome_violation"):
        canary.build_projection(raw, summary, decisions, taxonomy)


def _three_sample_document(paths: canary.CanaryPaths, taxonomy: TaxonomyIndex) -> dict[str, Any]:
    records = [record(1), record(2, content=None), record(3, content="   ")]
    raw, summary = _observed_run(paths, taxonomy, records)
    span = _balanced_excerpt(records[0]["content"])
    decisions = {
        "selected": [
            _decision(0, "first_converted", span),
            _decision(1, "distinct_outcome", None),
            _decision(2, "distinct_outcome", (0, 1)),
        ]
    }
    document = canary.build_projection(raw, summary, decisions, taxonomy)
    outcomes = [e["golden_expectations"]["content_outcome"] for e in document["selected"]]
    assert outcomes == ["converted", "absent", "blank"]
    return document


def _recompute_everything(document: dict[str, Any], taxonomy: TaxonomyIndex) -> None:
    """An attacker's full recomputation: honest goldens for the tampered jobs
    and every editable hash, count, and offset made self-consistent."""
    envelope = document["replay_envelope"]
    envelope["meta"]["total"] = len(envelope["jobs"])
    result, normalized = asyncio.run(canary.replay_envelope(envelope, taxonomy))
    for index, (job, entry) in enumerate(zip(envelope["jobs"], document["selected"], strict=True)):
        entry["replay_index"] = index
        entry["golden_expectations"] = canary.golden_for(result.jobs[index], normalized[index])
        _rehash(job, entry)


def _rehash(job: dict[str, Any], entry: dict[str, Any]) -> None:
    lineage = entry["lineage"]
    lineage["projected_record_sha256"] = canonical_json_hash(job)
    content = job.get("content")
    if isinstance(content, str):
        data = content.encode("utf-8")
        start = lineage["excerpt_start_code_point"] or 1
        lineage.update(
            excerpt_sha256=hashlib.sha256(data).hexdigest(),
            excerpt_code_points=len(content),
            excerpt_utf8_bytes=len(data),
            excerpt_start_code_point=start,
            excerpt_end_code_point_exclusive=start + len(content),
            original_content_code_points=max(
                lineage["original_content_code_points"] or 0, start + len(content) + 1
            ),
        )
    else:
        lineage.update(
            excerpt_sha256=None,
            excerpt_code_points=None,
            excerpt_utf8_bytes=None,
            excerpt_start_code_point=None,
            excerpt_end_code_point_exclusive=None,
        )
    lineage["golden_output_sha256"] = canonical_json_hash(entry["golden_expectations"])


def _negative_only(d: dict[str, Any]) -> None:
    d["selected"].pop(0)
    d["replay_envelope"]["jobs"].pop(0)
    d["selected"][0]["selection_reason"] = "first_converted"


def _abstaining_first(d: dict[str, Any]) -> None:
    d["replay_envelope"]["jobs"][0]["content"] = _SCRIPT_PART


def _repeated_outcome(d: dict[str, Any]) -> None:
    d["replay_envelope"]["jobs"][2]["content"] = None


def _converted_later(d: dict[str, Any]) -> None:
    d["replay_envelope"]["jobs"][1]["content"] = _TEXT_PART


def _out_of_order(d: dict[str, Any]) -> None:
    a, b = d["selected"][1], d["selected"][2]
    a["source_ordinal"], b["source_ordinal"] = b["source_ordinal"], a["source_ordinal"]


def _relabelled_first(d: dict[str, Any]) -> None:
    d["selected"][0]["selection_reason"] = "distinct_outcome"


def _falsified_label(d: dict[str, Any]) -> None:
    d["selected"][1]["golden_expectations"]["content_outcome"] = "blank"
    d["selected"][2]["golden_expectations"]["content_outcome"] = "absent"
    for job, entry in zip(d["replay_envelope"]["jobs"], d["selected"], strict=True):
        _rehash(job, entry)


@pytest.mark.parametrize(
    ("tamper", "recompute", "kind"),
    [
        pytest.param(_negative_only, True, "first_sample_not_converted", id="negative_only"),
        pytest.param(_abstaining_first, True, "first_sample_not_converted", id="first_abstains"),
        pytest.param(_repeated_outcome, True, "distinct_outcome_violation", id="repeated"),
        pytest.param(_converted_later, True, "distinct_outcome_violation", id="converted_later"),
        pytest.param(_out_of_order, False, "selection_ordinal_order", id="out_of_order"),
        pytest.param(_relabelled_first, False, "first_sample_not_converted", id="relabelled"),
        pytest.param(_falsified_label, False, "golden_mismatch", id="falsified_label"),
    ],
)
def test_validator_enforces_actual_replay_outcomes_despite_recomputed_hashes(
    tamper: Callable[[dict[str, Any]], None],
    recompute: bool,
    kind: str,
    paths: canary.CanaryPaths,
    taxonomy: TaxonomyIndex,
) -> None:
    document = _three_sample_document(paths, taxonomy)
    canary.validate_fixture(document, taxonomy)  # control
    tamper(document)
    if recompute:
        _recompute_everything(document, taxonomy)
    with pytest.raises(canary.CanaryRefusal) as refusal:
        canary.validate_fixture(document, taxonomy)
    assert refusal.value.kind == kind


def test_three_sample_fixture_is_a_stable_control(
    paths: canary.CanaryPaths, taxonomy: TaxonomyIndex
) -> None:
    document = _three_sample_document(paths, taxonomy)
    _recompute_everything(document, taxonomy)  # honest recomputation changes nothing
    canary.validate_fixture(document, taxonomy)
