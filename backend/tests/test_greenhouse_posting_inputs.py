"""Offline tests for the Greenhouse content-enabled adapter path and the strict
`DiscoveredJob` -> `PostingInputs` mapping (Phase 4 S2b; ADR 0015).

Zero-network enforcement follows S1 (ADR 0013): the autouse `network_guard`
replaces `httpx.AsyncHTTPTransport.handle_async_request` with a fixed
`httpx.ConnectError` and turns socket connection and resolution into hard
failures. Every discovery here uses a fresh `httpx.MockTransport`.

Fixtures and evidence boundaries:

- Every Greenhouse record built here is SYNTHETIC — not captured from
  Greenhouse. No captured raw `content` HTML exists in this repository.
- The 30 corpus envelopes are RECONSTRUCTED SYNTHETIC raw shape: each corpus
  record's captured, sanitized, human-reviewed text is wrapped as
  `html.escape("<div>" + html.escape(description, quote=False) + "</div>",
  quote=False)`. For these 30 reconstructed synthetic envelopes, S1→S2b
  produces the same three parser-input strings as the published S2 corpus
  invocation and therefore reproduces its pinned outputs. This is regression
  evidence for that exact reconstructed shape, not captured raw-HTML,
  list-endpoint encoding, generalization, or live-provider evidence. Title
  remains smoke-only.
- `greenhouse_live_canary.json` is a sanitized, allowlisted, derived sample with
  no `content`; it proves only existing title/location behavior.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import html
import json
import re
import socket
from collections import Counter
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.hashing import canonical_json_hash
from app.normalization.posting import NormalizedPosting, PostingInputs, normalize_posting
from app.normalization.taxonomy import DEFAULT_SKILLS_TAXONOMY_PATH, TaxonomyIndex, load_taxonomy
from app.providers.greenhouse import (
    GreenhouseBoard,
    GreenhouseConfigurationError,
    GreenhouseJobBoardProvider,
    _ValidRecord,
)
from app.providers.greenhouse_content import ContentOutcome, GreenhouseContentMode
from app.providers.greenhouse_posting_inputs import greenhouse_posting_inputs
from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult
from app.schemas.provider import SourceQuery
from scripts.evaluate_phase3_corpus import CorpusRecord, load_corpus

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
GREENHOUSE_MODULE = APP_DIR / "providers" / "greenhouse.py"
CONTENT_MODULE = APP_DIR / "providers" / "greenhouse_content.py"
MAPPER_MODULE = APP_DIR / "providers" / "greenhouse_posting_inputs.py"
CORPUS_PATH = BACKEND_DIR / "tests" / "fixtures" / "evaluation" / "phase3_realistic_corpus.json"
CANARY_FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "discovery" / "greenhouse_live_canary.json"

# A15 evidence identities.
CORPUS_CANONICAL_JSON_SHA256 = "ca6e129110b71801e18d6bfba84d59376c689f67cb470f1335ab8805cd388f00"
CORPUS_CANONICAL_LF_SHA256 = "1863541bb784419be16bf4ffcf88bf1b4408c951a03b12008e9645e9f18e6930"
CANARY_CANONICAL_LF_SHA256 = "690b0a5d0f85599c44b88d2d2b483114ba4bc0db19647238feee280a2a6db4d5"

SYNTHETIC = "SYNTHETIC — not captured from Greenhouse"
SENTINEL = "SENTINEL-9e2a-content-must-not-leak"
FIXED_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
GREENHOUSE_QUERY = SourceQuery(sources=["greenhouse"])
DECLARED: GreenhouseContentMode = "declared-double-escaped"

ACME = GreenhouseBoard(board_token="acme-synthetic", company="Acme Synthetic Co")
ACME_DECLARED = GreenhouseBoard(
    board_token="acme-synthetic", company="Acme Synthetic Co", content_mode=DECLARED
)
BETA_DECLARED = GreenhouseBoard(
    board_token="beta-synthetic", company="Beta Synthetic Co", content_mode=DECLARED
)

ESCAPED_CONTENT = "&lt;p&gt;Synthetic &lt;b&gt;platform&lt;/b&gt; role.&lt;/p&gt;"
ESCAPED_CONTENT_TEXT = "Synthetic platform role."
MIXED_CONTENT = "<p>Mixed &lt;b&gt;markup&lt;/b&gt;</p>"
CONTENT_WARNING_RE = re.compile(r"greenhouse content_unconverted=([a-z_]+) count=([0-9]+)")


def canonical_lf_sha256(path: Path) -> str:
    text = path.read_bytes().decode("utf-8")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Network guard
# ---------------------------------------------------------------------------


@dataclass
class SocketGuard:
    calls: list[str] = field(default_factory=list)


@pytest.fixture(autouse=True)
async def network_guard(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SocketGuard]:
    """Installed inside the async fixture's own lifetime, as in S1, so the
    event loop's own loopback socketpair predates the hard-fail backups."""
    guard = SocketGuard()

    async def blocked_transport(self: Any, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network disabled in tests")

    def hard_fail(name: str) -> Callable[..., Any]:
        def _blocked(*args: Any, **kwargs: Any) -> Any:
            guard.calls.append(name)
            raise AssertionError(f"socket access attempted in an offline test: {name}")

        return _blocked

    with monkeypatch.context() as patch:
        patch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", blocked_transport)
        patch.setattr(socket.socket, "connect", hard_fail("socket.connect"))
        patch.setattr(socket.socket, "connect_ex", hard_fail("socket.connect_ex"))
        patch.setattr(socket, "create_connection", hard_fail("socket.create_connection"))
        patch.setattr(socket, "getaddrinfo", hard_fail("socket.getaddrinfo"))
        yield guard
    assert guard.calls == []


# ---------------------------------------------------------------------------
# Synthetic payload builders
# ---------------------------------------------------------------------------


def synthetic_record(
    job_id: Any = 1000001, board: str = "acme-synthetic", **overrides: Any
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "_synthetic": SYNTHETIC,
        "id": job_id,
        "internal_job_id": 9000001,
        "title": "Synthetic Platform Engineer",
        "absolute_url": f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}",
        "location": {"name": "Remote, Synthetic Region"},
        "requisition_id": "SYN-REQ-1",
        "first_published": "2026-09-01T09:30:00-04:00",
        "updated_at": "2026-09-15T10:00:00-04:00",
        "company_name": "Payload Company Name (must be ignored)",
        "content": ESCAPED_CONTENT,
        "metadata": [{"id": 1, "name": "Synthetic Tag", "value": ["a", {"nested": True}]}],
        "unknown_future_field": {"kept": [1, 2.5, None, "x"]},
    }
    record.update(overrides)
    return record


def envelope(records: list[Any]) -> dict[str, Any]:
    return {"jobs": records, "meta": {"total": len(records)}}


def json_response(payload: Any) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def fake_transport(routes: dict[str, httpx.Response]) -> Callable[[], httpx.AsyncBaseTransport]:
    def handler(request: httpx.Request) -> httpx.Response:
        return routes[request.url.path.split("/")[3]]

    return lambda: httpx.MockTransport(handler)


def make_provider(
    routes: dict[str, httpx.Response], boards: tuple[GreenhouseBoard, ...]
) -> GreenhouseJobBoardProvider:
    async def no_sleep(seconds: float) -> None:
        raise AssertionError("no retry expected")

    return GreenhouseJobBoardProvider(
        boards,
        transport_factory=fake_transport(routes),
        sleep=no_sleep,
        monotonic=lambda: 0.0,
        now=lambda: FIXED_NOW,
    )


async def discover_records(
    board: GreenhouseBoard, records: list[Any]
) -> tuple[GreenhouseJobBoardProvider, DiscoveryResult]:
    provider = make_provider({board.board_token: json_response(envelope(records))}, (board,))
    return provider, await provider.discover(GREENHOUSE_QUERY)


def valid_record(record: dict[str, Any]) -> _ValidRecord:
    return _ValidRecord(
        record=record,
        job_id=record["id"],
        absolute_url=record["absolute_url"],
        title=record["title"],
        location=record["location"]["name"],
        requisition_id=None,
        posted_at=None,
    )


def make_job(**overrides: Any) -> DiscoveredJob:
    values: dict[str, Any] = {
        "provider": "greenhouse",
        "source": "greenhouse",
        "source_tenant_id": "acme-synthetic",
        "source_job_id": "1000001",
        "requisition_id_raw": None,
        "title": "Synthetic Platform Engineer",
        "company": None,
        "location": "Remote, Synthetic Region",
        "source_url": "https://job-boards.greenhouse.io/acme-synthetic/jobs/1000001",
        "apply_url": None,
        "canonical_url": None,
        "description": "Synthetic description.",
        "compensation_text": None,
        "posted_at": None,
        "discovered_at": FIXED_NOW,
        "raw": {},
    }
    values.update(overrides)
    return DiscoveredJob(**values)


@pytest.fixture(scope="module")
def taxonomy() -> TaxonomyIndex:
    return load_taxonomy(DEFAULT_SKILLS_TAXONOMY_PATH)


# ---------------------------------------------------------------------------
# Board configuration (A3)
# ---------------------------------------------------------------------------


def test_disabled_is_the_default_content_mode() -> None:
    assert GreenhouseBoard("acme-synthetic", "Acme").content_mode == "disabled"


class _StrSubclass(str):
    pass


@pytest.mark.parametrize(
    "mode", ["standard", "Disabled", "", None, 1, SENTINEL, _StrSubclass("disabled")]
)
def test_invalid_content_mode_raises_the_fixed_message(mode: Any) -> None:
    with pytest.raises(GreenhouseConfigurationError) as raised:
        GreenhouseBoard("acme-synthetic", "Acme", content_mode=mode)
    assert str(raised.value) == "content_mode must be 'disabled' or 'declared-double-escaped'"
    assert SENTINEL not in str(raised.value)


# ---------------------------------------------------------------------------
# Disabled boards (A5)
# ---------------------------------------------------------------------------


class ContentRaisingRecord(dict[str, Any]):
    """Raises on any keyed access to `content`: indexing, `.get`, membership,
    `pop`, or `setdefault`. Deep copying (S1's raw preservation) iterates the
    underlying items and is allowed."""

    def _guard(self, key: object) -> None:
        if type(key) is str and key == "content":
            raise AssertionError("content was accessed on a disabled board")

    def __getitem__(self, key: str) -> Any:
        self._guard(key)
        return super().__getitem__(key)

    def get(self, key: str, default: Any = None) -> Any:
        self._guard(key)
        return super().get(key, default)

    def __contains__(self, key: object) -> bool:
        self._guard(key)
        return super().__contains__(key)

    def pop(self, key: str, *args: Any) -> Any:
        self._guard(key)
        return super().pop(key, *args)

    def setdefault(self, key: str, default: Any = None) -> Any:
        self._guard(key)
        return super().setdefault(key, default)


def test_disabled_board_never_touches_content() -> None:
    record = ContentRaisingRecord(synthetic_record())
    with pytest.raises(AssertionError):
        record.get("content")
    provider = make_provider({}, (ACME,))
    job, outcome = provider._to_discovered_job(ACME, valid_record(record), FIXED_NOW)
    assert outcome is None
    assert job.description is None
    assert job.raw == dict(record)


async def test_disabled_board_never_converts() -> None:
    records = [
        synthetic_record(1),
        synthetic_record(2, content=MIXED_CONTENT),
        synthetic_record(3, content=None),
    ]
    provider, result = await discover_records(ACME, records)
    assert [job.description for job in result.jobs] == [None, None, None]
    assert result.warnings == []
    assert result.errors == []
    (stats,) = result.source_stats
    assert stats.completed is True
    assert stats.incomplete_results is False
    assert result.possibly_incomplete is False
    assert (await provider.health()).sources[0].detail == "discovery succeeded"


# ---------------------------------------------------------------------------
# Enabled boards (A9, A10)
# ---------------------------------------------------------------------------


async def test_declared_board_converts_content() -> None:
    provider, result = await discover_records(ACME_DECLARED, [synthetic_record()])
    (job,) = result.jobs
    assert job.description == ESCAPED_CONTENT_TEXT
    assert result.warnings == []
    assert result.source_stats[0].incomplete_results is False
    assert (await provider.health()).sources[0].detail == "discovery succeeded"


async def test_description_populated_on_declared_board() -> None:
    _, result = await discover_records(ACME_DECLARED, [synthetic_record()])
    assert result.jobs[0].description == ESCAPED_CONTENT_TEXT


async def test_mixed_boards_in_one_discover() -> None:
    routes = {
        "acme-synthetic": json_response(envelope([synthetic_record(1)])),
        "beta-synthetic": json_response(envelope([synthetic_record(2, board="beta-synthetic")])),
    }
    beta_disabled = GreenhouseBoard("beta-synthetic", "Beta Synthetic Co")
    result = await make_provider(routes, (ACME_DECLARED, beta_disabled)).discover(GREENHOUSE_QUERY)
    assert [(job.source_tenant_id, job.description) for job in result.jobs] == [
        ("acme-synthetic", ESCAPED_CONTENT_TEXT),
        ("beta-synthetic", None),
    ]
    assert result.warnings == []


async def test_conversion_failure_keeps_record() -> None:
    records = [
        synthetic_record(1),
        synthetic_record(2, content=MIXED_CONTENT),
        synthetic_record(3, content=None),
        synthetic_record(4, content=5),
        synthetic_record(5, content=" \t\n"),
    ]
    del records[2]["content"]
    provider, result = await discover_records(ACME_DECLARED, records)
    assert [(job.source_job_id, job.description) for job in result.jobs] == [
        ("1", ESCAPED_CONTENT_TEXT),
        ("2", None),
        ("3", None),
        ("4", None),
        ("5", None),
    ]
    assert result.errors == []
    (stats,) = result.source_stats
    assert stats.completed is True
    assert stats.jobs_found == 5
    assert stats.incomplete_results is True
    assert result.possibly_incomplete is True
    assert (await provider.health()).sources[0].detail == "partial discovery observed"


async def test_board_whose_records_all_fail_conversion_still_completes() -> None:
    records = [synthetic_record(1, content=MIXED_CONTENT), synthetic_record(2, content="&ltx")]
    provider, result = await discover_records(ACME_DECLARED, records)
    assert len(result.jobs) == 2
    assert all(job.description is None for job in result.jobs)
    (stats,) = result.source_stats
    assert stats.completed is True
    assert stats.incomplete_results is True
    assert result.possibly_incomplete is True
    health = await provider.health()
    assert health.healthy is True
    assert health.sources[0].detail == "partial discovery observed"


async def test_successful_empty_declared_board_remains_complete() -> None:
    provider, result = await discover_records(ACME_DECLARED, [])
    (stats,) = result.source_stats
    assert stats.completed is True
    assert stats.incomplete_results is False
    assert result.warnings == []
    assert (await provider.health()).sources[0].detail == "discovery succeeded"


async def test_all_board_failure_is_unchanged() -> None:
    provider = make_provider({"acme-synthetic": httpx.Response(404)}, (ACME_DECLARED,))
    result = await provider.discover(GREENHOUSE_QUERY)
    (stats,) = result.source_stats
    assert stats.completed is False
    assert result.jobs == []
    assert [error.detail for error in result.errors] == [
        "greenhouse board=acme-synthetic failure=http_status status=404 attempts=1"
    ]
    assert result.warnings == []


async def test_malformed_id_skipping_unchanged_on_enabled_board() -> None:
    records = [synthetic_record(1), synthetic_record(None)]
    _, result = await discover_records(ACME_DECLARED, records)
    assert [job.source_job_id for job in result.jobs] == ["1"]
    assert [error.detail for error in result.errors] == [
        "greenhouse board=acme-synthetic skipped_records=1"
    ]
    assert result.source_stats[0].incomplete_results is True
    assert result.warnings == []


SENTINEL_BOARD = GreenhouseBoard(
    board_token="sentinel-9e2a-board", company="Sentinel Co", content_mode=DECLARED
)


def _failing_routes() -> tuple[dict[str, httpx.Response], tuple[GreenhouseBoard, ...]]:
    leak = f"<p>{SENTINEL} &lt;b&gt;</p>"
    acme = [
        synthetic_record(1, content=leak, title=SENTINEL),
        synthetic_record(2, content=MIXED_CONTENT),
        synthetic_record(3, content=f"&lt;p&gt;{SENTINEL}&lt;/p&gt;"),
    ]
    sentinel_board = [
        synthetic_record(10, board="sentinel-9e2a-board", content=leak),
        synthetic_record(11, board="sentinel-9e2a-board", content=None),
        synthetic_record(12, board="sentinel-9e2a-board", content=f"&amp;lt;{SENTINEL}"),
    ]
    routes = {
        "acme-synthetic": json_response(envelope(acme)),
        "sentinel-9e2a-board": json_response(envelope(sentinel_board)),
    }
    return routes, (ACME_DECLARED, SENTINEL_BOARD)


async def test_conversion_warning_has_no_content() -> None:
    routes, boards = _failing_routes()
    result = await make_provider(routes, boards).discover(GREENHOUSE_QUERY)
    assert result.warnings == [
        "greenhouse content_unconverted=absent count=1",
        "greenhouse content_unconverted=mixed_literal_and_escaped_markup count=3",
        "greenhouse content_unconverted=residual_nested_encoding count=1",
    ]
    text = "\n".join(result.warnings)
    for forbidden in (SENTINEL, "sentinel-9e2a-board", "acme-synthetic", "http", "10", "Mixed"):
        assert forbidden not in text


async def test_conversion_warning_counts_are_categorical() -> None:
    routes, boards = _failing_routes()
    result = await make_provider(routes, boards).discover(GREENHOUSE_QUERY)
    counts: Counter[str] = Counter()
    for warning in result.warnings:
        match = CONTENT_WARNING_RE.match(warning)
        assert match is not None
        counts[match.group(1)] += int(match.group(2))
    assert counts == {
        "absent": 1,
        "mixed_literal_and_escaped_markup": 3,
        "residual_nested_encoding": 1,
    }
    assert sum(1 for job in result.jobs if job.description is not None) == 1


async def test_content_warnings_follow_existing_s1_diagnostics() -> None:
    records = [synthetic_record(1, content=MIXED_CONTENT), synthetic_record(2, id=True)]
    _, result = await discover_records(ACME_DECLARED, records)
    assert [error.detail for error in result.errors] == [
        "greenhouse board=acme-synthetic skipped_records=1"
    ]
    assert result.warnings == [
        "greenhouse content_unconverted=mixed_literal_and_escaped_markup count=1"
    ]


# ---------------------------------------------------------------------------
# Raw preservation (A13)
# ---------------------------------------------------------------------------


async def test_raw_equals_source_record_after_conversion() -> None:
    record = synthetic_record()
    _, result = await discover_records(ACME_DECLARED, [record])
    (job,) = result.jobs
    assert job.raw == record
    assert canonical_json_hash(job.raw) == canonical_json_hash(record)
    assert job.raw["content"] == ESCAPED_CONTENT
    assert "description" not in job.raw


def test_conversion_never_mutates_or_aliases_the_source_record() -> None:
    record = synthetic_record()
    before = copy.deepcopy(record)
    provider = make_provider({}, (ACME_DECLARED,))
    job, outcome = provider._to_discovered_job(ACME_DECLARED, valid_record(record), FIXED_NOW)
    assert outcome is ContentOutcome.CONVERTED
    assert job.description == ESCAPED_CONTENT_TEXT
    assert record == before
    assert job.raw == record
    assert canonical_json_hash(job.raw) == canonical_json_hash(before)
    assert job.raw is not record
    assert job.raw["metadata"] is not record["metadata"]
    assert job.raw["unknown_future_field"] is not record["unknown_future_field"]


async def test_compensation_text_stays_none_on_a_declared_board() -> None:
    record = synthetic_record(
        content="&lt;p&gt;Salary: $150,000 - $200,000 per year&lt;/p&gt;",
        pay_transparency={"min": 150000, "max": 200000},
    )
    _, result = await discover_records(ACME_DECLARED, [record])
    (job,) = result.jobs
    assert job.compensation_text is None
    assert job.description == "Salary: $150,000 - $200,000 per year"


def test_discovered_job_schema_is_unchanged() -> None:
    assert list(DiscoveredJob.model_fields) == [
        "provider",
        "source",
        "source_tenant_id",
        "source_job_id",
        "requisition_id_raw",
        "title",
        "company",
        "location",
        "source_url",
        "apply_url",
        "canonical_url",
        "description",
        "compensation_text",
        "posted_at",
        "discovered_at",
        "raw",
    ]


# ---------------------------------------------------------------------------
# Mapper (A12)
# ---------------------------------------------------------------------------


def test_three_field_wiring_exact() -> None:
    job = make_job(title="T-sentinel", description="D-sentinel", location="L-sentinel")
    assert greenhouse_posting_inputs(job) == PostingInputs(
        title="T-sentinel", description="D-sentinel", location="L-sentinel"
    )


@pytest.mark.parametrize(
    "title",
    [
        "Manager, Solutions Architects - San Francisco ",
        "  Senior\tEngineer \r\n",
        " Lead​ Engineer﻿",
        "",
        None,
    ],
)
def test_mapper_preserves_title_verbatim(title: str | None) -> None:
    mapped = greenhouse_posting_inputs(make_job(title=title))
    assert mapped.title == title
    assert type(mapped.title) is type(title)


@pytest.mark.parametrize(
    "value",
    [" Remote, US ", " Berlin​", "Line one\n\nLine two ", "", None],
)
def test_mapper_preserves_location_and_description_verbatim(value: str | None) -> None:
    mapped = greenhouse_posting_inputs(make_job(location=value, description=value))
    assert mapped.location == value
    assert mapped.description == value
    assert type(mapped.location) is type(value)
    assert type(mapped.description) is type(value)


def test_mapper_identity_is_preserved_diagnostic_only() -> None:
    """Optional diagnostic evidence; string identity is not a public contract."""
    job = make_job()
    mapped = greenhouse_posting_inputs(job)
    assert mapped.title is job.title
    assert mapped.description is job.description
    assert mapped.location is job.location


def test_direct_description_mapping() -> None:
    mapped = greenhouse_posting_inputs(make_job(description="Direct text", raw={"content": "X"}))
    assert mapped.description == "Direct text"


@pytest.mark.parametrize(
    ("provider", "source"),
    [("fixture", "greenhouse"), ("greenhouse", "lever"), ("ats_scrapers", "greenhouse"), ("", "")],
)
def test_non_greenhouse_job_rejected(provider: str, source: str) -> None:
    with pytest.raises(ValueError) as raised:
        greenhouse_posting_inputs(make_job(provider=provider, source=source))
    assert str(raised.value) == (
        "greenhouse_posting_inputs accepts only greenhouse provider/source jobs"
    )


@pytest.mark.parametrize("value", [None, {}, "job", PostingInputs("t", "d", "l")])
def test_non_discovered_job_rejected(value: Any) -> None:
    with pytest.raises(TypeError) as raised:
        greenhouse_posting_inputs(value)
    assert str(raised.value) == "greenhouse_posting_inputs requires a DiscoveredJob instance"


def test_greenhouse_job_accepted() -> None:
    assert greenhouse_posting_inputs(make_job()) == PostingInputs(
        title="Synthetic Platform Engineer",
        description="Synthetic description.",
        location="Remote, Synthetic Region",
    )


class TracingJob(DiscoveredJob):
    """Records every non-dunder attribute read."""

    def __getattribute__(self, name: str) -> Any:
        if not name.startswith("__"):
            _ACCESS_LOG.append(name)
        return super().__getattribute__(name)


_ACCESS_LOG: list[str] = []


@pytest.mark.parametrize("description", [None, "Present description"])
def test_mapper_reads_only_allowlisted_attributes(description: str | None) -> None:
    job = TracingJob(
        **{
            **make_job().model_dump(),
            "description": description,
            "company": "Senior Remote Python Co",
            "raw": {"content": f"&lt;p&gt;{SENTINEL}&lt;/p&gt;", "title": SENTINEL},
        }
    )
    _ACCESS_LOG.clear()
    mapped = greenhouse_posting_inputs(job)
    accessed = set(_ACCESS_LOG)
    _ACCESS_LOG.clear()
    assert accessed == {"provider", "source", "title", "description", "location"}
    assert mapped.description == description


BAIT = "Senior Staff Remote Full-time Python Kubernetes $200,000 - $250,000 per year"


def _bait_job(**overrides: Any) -> DiscoveredJob:
    return make_job(
        source_tenant_id=BAIT,
        source_job_id=BAIT,
        requisition_id_raw=BAIT,
        company=BAIT,
        source_url=f"https://example.invalid/{BAIT.replace(' ', '-')}",
        apply_url="https://example.invalid/apply/senior-remote-python",
        canonical_url="https://example.invalid/canonical/senior-remote-python",
        compensation_text=BAIT,
        posted_at=datetime(2020, 1, 1, tzinfo=UTC),
        discovered_at=datetime(2021, 1, 1, tzinfo=UTC),
        raw={
            "company_name": BAIT,
            "metadata": [{"name": "Seniority", "value": "Senior"}],
            "departments": [{"name": "Remote Python Platform"}],
            "offices": [{"name": "Remote, US", "location": "San Francisco, CA"}],
            "updated_at": "2026-09-15T10:00:00-04:00",
            "first_published": "2026-09-01T09:30:00-04:00",
            "requisition_id": BAIT,
            "absolute_url": "https://example.invalid/senior",
            "pay_transparency": {"min": 200000, "max": 250000},
            "content": f"&lt;p&gt;{BAIT}&lt;/p&gt;",
            "title": BAIT,
            "location": {"name": BAIT},
        },
        **overrides,
    )


@pytest.mark.parametrize("description", [None, "Plain synthetic description."])
def test_non_allowlisted_fields_never_reach_inputs(
    description: str | None, taxonomy: TaxonomyIndex
) -> None:
    baseline = make_job(description=description, company=None)
    bait = _bait_job(description=description)
    assert greenhouse_posting_inputs(bait) == greenhouse_posting_inputs(baseline)
    assert normalize_posting(greenhouse_posting_inputs(bait), taxonomy=taxonomy) == (
        normalize_posting(greenhouse_posting_inputs(baseline), taxonomy=taxonomy)
    )


def test_mapper_does_not_mutate_the_job() -> None:
    job = _bait_job()
    before = job.model_dump()
    raw_before = copy.deepcopy(job.raw)
    greenhouse_posting_inputs(job)
    assert job.model_dump() == before
    assert job.raw == raw_before


# ---------------------------------------------------------------------------
# normalize_posting interaction and salary exclusion
# ---------------------------------------------------------------------------


async def test_mapped_inputs_flow_into_normalize_posting_unaltered(
    taxonomy: TaxonomyIndex,
) -> None:
    record = synthetic_record(
        title="Senior Backend Engineer",
        location={"name": "Remote, US"},
        content=(
            "&lt;p&gt;Full-time role.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;5+ years of Python"
            "&lt;/li&gt;&lt;li&gt;Kubernetes&lt;/li&gt;&lt;/ul&gt;"
        ),
    )
    _, result = await discover_records(ACME_DECLARED, [record])
    mapped = greenhouse_posting_inputs(result.jobs[0])
    assert mapped == PostingInputs(
        title="Senior Backend Engineer",
        description="Full-time role.\n5+ years of Python\nKubernetes",
        location="Remote, US",
    )
    posting = normalize_posting(mapped, taxonomy=taxonomy)
    assert posting.inputs is mapped
    direct = normalize_posting(
        PostingInputs(
            title="Senior Backend Engineer",
            description="Full-time role.\n5+ years of Python\nKubernetes",
            location="Remote, US",
        ),
        taxonomy=taxonomy,
    )
    assert posting == direct


def test_no_salary_input_or_output_exists() -> None:
    assert [f.name for f in fields(PostingInputs)] == ["title", "description", "location"]
    assert "salary" not in {f.name for f in fields(NormalizedPosting)}


# ---------------------------------------------------------------------------
# Canary sample (A15): title/location only
# ---------------------------------------------------------------------------


def test_canary_fixture_identity() -> None:
    assert canonical_lf_sha256(CANARY_FIXTURE) == CANARY_CANONICAL_LF_SHA256


async def test_canary_title_and_location_map_verbatim() -> None:
    job_record = json.loads(CANARY_FIXTURE.read_text(encoding="utf-8"))["job"]
    assert "content" not in job_record
    gitlab = GreenhouseBoard("gitlab", "GitLab")
    _, result = await discover_records(gitlab, [job_record])
    mapped = greenhouse_posting_inputs(result.jobs[0])
    assert mapped == PostingInputs(
        title="Manager, Solutions Architects - San Francisco ",
        description=None,
        location="Remote, US",
    )
    assert result.warnings == []

    gitlab_declared = GreenhouseBoard("gitlab", "GitLab", content_mode=DECLARED)
    _, declared = await discover_records(gitlab_declared, [job_record])
    assert greenhouse_posting_inputs(declared.jobs[0]) == mapped
    assert declared.warnings == ["greenhouse content_unconverted=absent count=1"]
    assert declared.source_stats[0].incomplete_results is True


# ---------------------------------------------------------------------------
# Reconstructed corpus envelopes (A15, A16)
# ---------------------------------------------------------------------------


def reconstruct_content(description: str) -> str:
    """The exact reconstruction algorithm: synthetic raw shape, not captured
    Greenhouse HTML."""
    return html.escape("<div>" + html.escape(description, quote=False) + "</div>", quote=False)


def test_corpus_identities() -> None:
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    assert hashlib.sha256(canonical.encode("ascii")).hexdigest() == CORPUS_CANONICAL_JSON_SHA256
    assert canonical_lf_sha256(CORPUS_PATH) == CORPUS_CANONICAL_LF_SHA256


@pytest.fixture(scope="module")
def corpus(taxonomy: TaxonomyIndex) -> list[CorpusRecord]:
    return load_corpus(CORPUS_PATH, known_canonical_ids=taxonomy.canonical_ids())


async def test_reconstructed_corpus_envelopes_reproduce_the_s2_invocation(
    corpus: list[CorpusRecord], taxonomy: TaxonomyIndex
) -> None:
    assert len(corpus) == 30
    by_board: dict[str, list[dict[str, Any]]] = {}
    expected: dict[tuple[str, str], CorpusRecord] = {}
    for record in corpus:
        token, job_id = record.id.split(":")
        description = record.fields["description"]
        assert isinstance(description, str)
        content = reconstruct_content(description)
        assert "<" not in content and ">" not in content
        location_raw = record.fields["location_raw"]
        by_board.setdefault(token, []).append(
            {
                "_synthetic": "RECONSTRUCTED SYNTHETIC raw shape — not captured Greenhouse HTML",
                "id": int(job_id),
                "title": record.fields["title"],
                "absolute_url": f"https://job-boards.greenhouse.io/{token}/jobs/{job_id}",
                "location": None if location_raw is None else {"name": location_raw},
                "content": content,
            }
        )
        expected[(token, job_id)] = record
    assert sorted(by_board) == ["anthropic", "discord", "gitlab"]

    boards = tuple(
        GreenhouseBoard(token, token.title(), content_mode=DECLARED) for token in sorted(by_board)
    )
    routes = {token: json_response(envelope(records)) for token, records in by_board.items()}
    result = await make_provider(routes, boards).discover(GREENHOUSE_QUERY)
    assert result.warnings == []
    assert result.errors == []
    assert result.source_stats[0].incomplete_results is False
    assert len(result.jobs) == 30

    for job in result.jobs:
        assert job.source_tenant_id is not None and job.source_job_id is not None
        record = expected.pop((job.source_tenant_id, job.source_job_id))
        direct_inputs = PostingInputs(
            title=record.fields["title"],
            description=record.fields["description"],
            location=record.fields["location_raw"],
        )
        mapped = greenhouse_posting_inputs(job)
        assert mapped == direct_inputs, record.id
        assert normalize_posting(mapped, taxonomy=taxonomy) == normalize_posting(
            direct_inputs, taxonomy=taxonomy
        ), record.id
    assert expected == {}


# ---------------------------------------------------------------------------
# Import boundaries and reachability (A2, A12, A19)
# ---------------------------------------------------------------------------


def _imports(path: Path) -> set[str]:
    """Module names imported by `path`, including `from pkg import module`
    spellings as `pkg.module`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module is not None, path
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_mapper_import_allow_list() -> None:
    tree = ast.parse(MAPPER_MODULE.read_text(encoding="utf-8"))
    modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    plain = [node for node in ast.walk(tree) if isinstance(node, ast.Import)]
    assert plain == []
    assert modules == {"__future__", "app.normalization.posting", "app.schemas.discovered_job"}


_ALLOWED_JOB_ATTRIBUTES = {"provider", "source", "title", "description", "location"}
_FORBIDDEN_MAPPER_NAMES = {
    "raw",
    "company",
    "source_url",
    "apply_url",
    "canonical_url",
    "source_job_id",
    "source_tenant_id",
    "requisition_id_raw",
    "posted_at",
    "discovered_at",
    "compensation_text",
    "getattr",
    "setattr",
    "vars",
    "__dict__",
    "model_dump",
    "model_dump_json",
    "dict",
    "__import__",
    "importlib",
    "exec",
    "eval",
    "compile",
    "globals",
    "locals",
}


def test_mapper_ast_boundary() -> None:
    tree = ast.parse(MAPPER_MODULE.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not (names | attributes) & _FORBIDDEN_MAPPER_NAMES
    job_reads = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        if node.value.id == "job"
    }
    assert job_reads == _ALLOWED_JOB_ATTRIBUTES
    banned_nodes = (
        ast.IfExp,
        ast.Try,
        ast.For,
        ast.While,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.Lambda,
        ast.Subscript,
    )
    assert not [node for node in ast.walk(tree) if isinstance(node, banned_nodes)]
    (function,) = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    returned = function.body[-1]
    assert isinstance(returned, ast.Return) and isinstance(returned.value, ast.Call)
    call = returned.value
    assert isinstance(call.func, ast.Name) and call.func.id == "PostingInputs"
    assert call.args == []
    wiring = {}
    for keyword in call.keywords:
        value = keyword.value
        assert isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name)
        assert value.value.id == "job"
        wiring[keyword.arg] = value.attr
    assert wiring == {"title": "title", "description": "description", "location": "location"}


def _app_modules() -> list[Path]:
    return sorted(path for path in APP_DIR.rglob("*.py") if "__pycache__" not in path.parts)


def _importers(module: str) -> list[str]:
    return sorted(
        path.relative_to(BACKEND_DIR).as_posix()
        for path in _app_modules()
        if module in _imports(path)
    )


def test_new_modules_are_reachable_only_as_allowed() -> None:
    assert _importers("app.providers.greenhouse_content") == ["app/providers/greenhouse.py"]
    assert _importers("app.providers.greenhouse_posting_inputs") == []
    assert _importers("app.providers.greenhouse") == []


def test_greenhouse_adapter_imports_no_normalization_or_mapper() -> None:
    imported = _imports(GREENHOUSE_MODULE)
    assert not [name for name in imported if name.startswith("app.normalization")]
    assert "app.providers.greenhouse_posting_inputs" not in imported
    tree = ast.parse(GREENHOUSE_MODULE.read_text(encoding="utf-8"))
    from_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert {name for name in from_modules if name.startswith("app.")} == {
        "app.providers.greenhouse_content",
        "app.schemas.discovered_job",
        "app.schemas.provider",
    }


def test_greenhouse_adapter_imports_are_the_s1_set_plus_the_content_module() -> None:
    """No new network primitive, logging, persistence, or normalization import:
    the adapter's module imports are exactly S1's plus `greenhouse_content`."""
    tree = ast.parse(GREENHOUSE_MODULE.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    assert modules == {
        "__future__",
        "asyncio",
        "copy",
        "json",
        "math",
        "re",
        "time",
        "collections",
        "collections.abc",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "urllib.parse",
        "httpx",
        "app.providers.greenhouse_content",
        "app.schemas.discovered_job",
        "app.schemas.provider",
    }


@pytest.mark.parametrize("path", [CONTENT_MODULE, MAPPER_MODULE])
def test_no_logging_persistence_database_or_network_primitive(path: Path) -> None:
    imported = _imports(path)
    forbidden = (
        "logging",
        "app.db",
        "app.ingestion",
        "app.services",
        "app.api",
        "sqlalchemy",
        "alembic",
        "socket",
        "urllib",
        "requests",
        "aiohttp",
        "asyncpg",
        "psycopg",
        "ats_scrapers",
        "httpx",
    )
    assert not [name for name in imported if name.startswith(forbidden)]
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert "print" not in names and "open" not in names
