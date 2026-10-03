"""Offline tests for `app.providers.greenhouse.GreenhouseJobBoardProvider`
(Phase 4 S1; ADR 0013).

Zero-network enforcement (Sol A10): the autouse `network_guard` fixture
replaces `httpx.AsyncHTTPTransport.handle_async_request` with a hook that
raises one fixed `httpx.ConnectError`, and turns `socket.socket.connect`/
`connect_ex`, `socket.create_connection`, and `socket.getaddrinfo` into
hard-fail backups that record any call. It is an async fixture so the event
loop (whose Windows self-pipe uses a Python-level `socketpair`/`connect`)
already exists before the socket backups are installed. Every test other
than T00 supplies a fresh `httpx.MockTransport` through `transport_factory`,
and every retry waits through an injected no-wait recording `sleep`.

Fixtures (Sol A13):

- `greenhouse_live_canary.json` is a sanitized, allowlisted, derived sample
  based on one real job entry. It is not raw, structure-complete, envelope
  evidence, or `content=true` evidence; it is read here, never modified.
- Every other record and envelope below is SYNTHETIC — not captured from
  Greenhouse — with fictional boards, IDs, titles, URLs and placeholder HTML,
  and no real person, contact detail, or secret.
"""

from __future__ import annotations

import ast
import json
import logging
import socket
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ingestion.hashing import canonical_json_hash
from app.providers.base import DiscoveryProvider
from app.providers.greenhouse import (
    GreenhouseBoard,
    GreenhouseClientSettings,
    GreenhouseConfigurationError,
    GreenhouseJobBoardProvider,
    UnsupportedSourceQueryError,
)
from app.providers.registry import ProviderRegistry
from app.schemas.discovered_job import DiscoveryResult, ProviderErrorCategory
from app.schemas.provider import SourceQuery

BACKEND_DIR = Path(__file__).resolve().parent.parent
CANARY_FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "discovery" / "greenhouse_live_canary.json"

SYNTHETIC = "SYNTHETIC — not captured from Greenhouse"
SENTINEL = "SENTINEL-7f3c-greenhouse-payload-must-not-leak"
FIXED_NOW = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
GREENHOUSE_QUERY = SourceQuery(sources=["greenhouse"])

ACME = GreenhouseBoard(board_token="acme-synthetic", company="Acme Synthetic Co")
BETA = GreenhouseBoard(board_token="beta-synthetic", company="Beta Synthetic Co")


# ---------------------------------------------------------------------------
# Network guard (A10)
# ---------------------------------------------------------------------------


@dataclass
class SocketGuard:
    calls: list[str] = field(default_factory=list)


FIXED_CONNECT_ERROR_MESSAGE = "network disabled in tests"


@pytest.fixture(autouse=True)
async def network_guard(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[SocketGuard]:
    """Installed and removed inside this async fixture's own lifetime:
    pytest-asyncio builds a replacement event loop during its teardown
    (before function-scoped `monkeypatch` is undone), and on Windows that
    loop's self-pipe connects a loopback `socketpair` — which must not trip
    the hard-fail backups."""
    guard = SocketGuard()

    async def blocked_transport(self: Any, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(FIXED_CONNECT_ERROR_MESSAGE)

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
        # Built from the trimmed ID so whitespace-bearing IDs used by the
        # duplicate-identity tests still carry a valid URL.
        "absolute_url": f"https://job-boards.greenhouse.io/{board}/jobs/{str(job_id).strip()}",
        "location": {"name": "Remote, Synthetic Region"},
        "requisition_id": "SYN-REQ-1",
        "first_published": "2026-09-01T09:30:00-04:00",
        "updated_at": "2026-09-15T10:00:00-04:00",
        "company_name": "Payload Company Name (must be ignored)",
        "content": "&lt;p&gt;Placeholder synthetic description.&lt;/p&gt;",
        "metadata": [{"id": 1, "name": "Synthetic Tag", "value": ["a", {"nested": True}]}],
        "unknown_future_field": {"kept": [1, 2.5, None, "x"]},
    }
    record.update(overrides)
    return record


def envelope(records: list[Any], *, total: Any = "default") -> dict[str, Any]:
    payload: dict[str, Any] = {"jobs": records}
    if total == "default":
        payload["meta"] = {"total": len(records)}
    elif total != "absent":
        payload["meta"] = {"total": total}
    return payload


def json_response(
    payload: Any, *, status: int = 200, content_type: str = "application/json", **headers: str
) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(payload).encode("utf-8"),
        headers={"content-type": content_type, **headers},
    )


ResponseSpec = httpx.Response | Callable[[httpx.Request], httpx.Response] | BaseException


@dataclass
class FakeGreenhouse:
    """Routes each board token to a queue of responses (one per attempt);
    the last entry repeats once the queue is exhausted."""

    routes: dict[str, list[ResponseSpec]]
    requests: list[httpx.Request] = field(default_factory=list)
    factory_calls: int = 0
    closed: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        token = request.url.path.split("/")[3]
        queue = self.routes[token]
        spec = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(spec, BaseException):
            raise spec
        if callable(spec) and not isinstance(spec, httpx.Response):
            return spec(request)
        return spec

    def transport_factory(self) -> httpx.AsyncBaseTransport:
        self.factory_calls += 1
        fake = self

        class _TrackingTransport(httpx.MockTransport):
            async def aclose(self) -> None:
                fake.closed += 1

        return _TrackingTransport(self.handler)


@dataclass
class Sleeps:
    calls: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_provider(
    fake: FakeGreenhouse | None = None,
    *,
    boards: tuple[GreenhouseBoard, ...] = (ACME,),
    settings: GreenhouseClientSettings | None = None,
    sleeps: Sleeps | None = None,
    monotonic: Callable[[], float] | None = None,
    now: Callable[[], datetime] | None = None,
) -> GreenhouseJobBoardProvider:
    return GreenhouseJobBoardProvider(
        boards,
        settings=settings,
        transport_factory=fake.transport_factory if fake is not None else None,
        sleep=sleeps if sleeps is not None else Sleeps(),
        monotonic=monotonic if monotonic is not None else (lambda: 0.0),
        now=now if now is not None else (lambda: FIXED_NOW),
    )


def single_board(*responses: ResponseSpec) -> FakeGreenhouse:
    return FakeGreenhouse(routes={"acme-synthetic": list(responses)})


async def discover(provider: GreenhouseJobBoardProvider) -> DiscoveryResult:
    return await provider.discover(GREENHOUSE_QUERY)


def load_canary_sample() -> dict[str, Any]:
    data = json.loads(CANARY_FIXTURE.read_text(encoding="utf-8"))
    job = data["job"]
    assert isinstance(job, dict)
    return job


# ---------------------------------------------------------------------------
# T00 — network guard
# ---------------------------------------------------------------------------


async def test_t00_default_transport_hits_fixed_connect_error_without_socket_contact(
    network_guard: SocketGuard,
) -> None:
    sleeps = Sleeps()
    provider = make_provider(None, sleeps=sleeps)
    result = await discover(provider)

    stats = result.source_stats[0]
    assert stats.completed is False
    assert stats.jobs_found == 0
    assert stats.incomplete_results is False
    assert stats.retry_count == 2
    assert sleeps.calls == [0.5, 1.0]
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.UPSTREAM_ERROR
    assert error.retryable is True
    assert error.detail == (
        "greenhouse board=acme-synthetic failure=connect_error status=none attempts=3"
    )
    assert FIXED_CONNECT_ERROR_MESSAGE not in (error.detail or "")
    assert network_guard.calls == []


# ---------------------------------------------------------------------------
# T01 — protocol, registry, capabilities
# ---------------------------------------------------------------------------


def test_t01_conforms_to_protocol_and_registers() -> None:
    provider: DiscoveryProvider = make_provider(single_board(json_response(envelope([]))))
    registry = ProviderRegistry([provider])
    assert registry.names() == ["greenhouse"]
    resolved = registry.get("greenhouse")
    assert resolved.provider is provider
    capabilities = provider.capabilities()
    assert capabilities.provider == "greenhouse"
    assert list(capabilities.sources) == ["greenhouse"]
    source = capabilities.sources["greenhouse"]
    assert source.supported_query_fields == set()
    assert source.max_concurrency == 1
    assert source.requests_per_second is None
    assert not (
        source.supports_salary_filter
        or source.supports_location_filter
        or source.supports_remote_filter
        or source.supports_posted_within_filter
    )


# ---------------------------------------------------------------------------
# T02 — configuration
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token", ["", "Acme", "acme/../x", "acme board", "-acme", "a" * 101, "acmé", "acme\n"]
)
def test_t02_rejects_invalid_board_tokens(token: str) -> None:
    with pytest.raises(GreenhouseConfigurationError):
        GreenhouseBoard(board_token=token, company="Acme")


@pytest.mark.parametrize("company", ["", "   ", " \t\n\r", 123, None])
def test_t02_rejects_invalid_company(company: Any) -> None:
    with pytest.raises(GreenhouseConfigurationError):
        GreenhouseBoard(board_token="acme-synthetic", company=company)


def test_t02_rejects_empty_duplicate_and_foreign_boards() -> None:
    with pytest.raises(GreenhouseConfigurationError):
        GreenhouseJobBoardProvider([])
    with pytest.raises(GreenhouseConfigurationError):
        GreenhouseJobBoardProvider([ACME, GreenhouseBoard("acme-synthetic", "Other")])
    with pytest.raises(GreenhouseConfigurationError):
        GreenhouseJobBoardProvider(["acme-synthetic"])  # type: ignore[list-item]


@pytest.mark.parametrize(
    "overrides",
    [
        {"connect_timeout": 0},
        {"read_timeout": -1.0},
        {"write_timeout": float("inf")},
        {"pool_timeout": float("nan")},
        {"attempt_deadline": True},
        {"max_response_bytes": 0},
        {"max_response_bytes": 1.5},
        {"max_attempts": 0},
        {"max_attempts": 6},
        {"max_attempts": True},
        {"backoff_base": 2.0, "backoff_cap": 1.0},
        {"max_retry_after": 0},
    ],
)
def test_t02_rejects_invalid_settings(overrides: dict[str, Any]) -> None:
    with pytest.raises(GreenhouseConfigurationError):
        GreenhouseClientSettings(**overrides)


def test_t02_default_settings_match_the_frozen_bound() -> None:
    s = GreenhouseClientSettings()
    per_attempt = s.pool_timeout + s.connect_timeout + s.write_timeout + s.read_timeout
    bound = s.max_attempts * (per_attempt + s.attempt_deadline) + (s.max_attempts - 1) * max(
        s.backoff_cap, s.max_retry_after
    )
    assert bound == 225


# ---------------------------------------------------------------------------
# T03 — source-query validation
# ---------------------------------------------------------------------------


async def test_t03_empty_sources_returns_empty_result_without_transport() -> None:
    fake = single_board(json_response(envelope([synthetic_record()])))
    provider = make_provider(fake)
    result = await provider.discover(SourceQuery(sources=[]))
    assert result.source_stats == []
    assert result.jobs == []
    assert result.errors == []
    assert fake.factory_calls == 0
    assert fake.requests == []
    assert (await provider.health()).sources[0].detail == "no discovery observed"


@pytest.mark.parametrize(
    "sources", [["linkedin"], ["greenhouse", "greenhouse"], ["greenhouse", "lever"], ["Greenhouse"]]
)
async def test_t03_unsupported_sources_raise_before_transport(sources: list[str]) -> None:
    fake = single_board(json_response(envelope([synthetic_record()])))
    provider = make_provider(fake)
    with pytest.raises(UnsupportedSourceQueryError):
        await provider.discover(SourceQuery(sources=sources))
    assert fake.factory_calls == 0
    assert fake.requests == []


async def test_t03_filter_fields_do_not_change_request_or_output() -> None:
    plain = single_board(json_response(envelope([synthetic_record()])))
    filtered = single_board(json_response(envelope([synthetic_record()])))
    plain_result = await discover(make_provider(plain))
    filtered_result = await make_provider(filtered).discover(
        SourceQuery(
            sources=["greenhouse"],
            titles=["nothing matches"],
            locations=["Nowhere"],
            remote_ok=False,
            salary_floor=10**9,
            max_results=0,
        )
    )
    assert str(plain.requests[0].url) == str(filtered.requests[0].url)
    assert plain_result.jobs == filtered_result.jobs


# ---------------------------------------------------------------------------
# T04 — request shape and client ownership
# ---------------------------------------------------------------------------


async def test_t04_request_shape() -> None:
    fake = single_board(json_response(envelope([synthetic_record()])))
    await discover(make_provider(fake))
    (request,) = fake.requests
    assert request.method == "GET"
    assert str(request.url) == (
        "https://boards-api.greenhouse.io/v1/boards/acme-synthetic/jobs?content=true"
    )
    assert "pay_transparency" not in str(request.url)
    assert "authorization" not in request.headers
    assert "cookie" not in request.headers


async def test_t04_one_fresh_transport_per_discover_and_closed() -> None:
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [json_response(envelope([synthetic_record()]))],
            "beta-synthetic": [
                json_response(envelope([synthetic_record(2000001, "beta-synthetic")]))
            ],
        }
    )
    provider = make_provider(fake, boards=(ACME, BETA))
    await discover(provider)
    assert fake.factory_calls == 1
    assert fake.closed >= 1
    await discover(provider)
    assert fake.factory_calls == 2
    assert fake.closed >= 2
    assert [r.url.path for r in fake.requests] == [
        "/v1/boards/acme-synthetic/jobs",
        "/v1/boards/beta-synthetic/jobs",
    ] * 2


async def test_t04_transport_closed_when_a_programmer_error_propagates() -> None:
    fake = single_board(RuntimeError("bug inside transport"))
    with pytest.raises(RuntimeError):
        await discover(make_provider(fake))
    assert fake.factory_calls == 1
    assert fake.closed >= 1


async def test_t04_redirect_is_not_followed() -> None:
    def other_host(request: httpx.Request) -> httpx.Response:
        if request.url.host == "boards-api.greenhouse.io":
            return httpx.Response(301, headers={"location": "https://elsewhere.example/jobs"})
        return json_response(envelope([synthetic_record()]))

    fake = single_board(other_host)
    result = await discover(make_provider(fake))
    assert len(fake.requests) == 1
    assert result.source_stats[0].completed is False
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.UPSTREAM_ERROR
    assert error.retryable is False
    assert "failure=redirect status=301" in (error.detail or "")


async def test_t04_environment_proxies_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, "http://proxy.invalid:9")
    fake = single_board(json_response(envelope([synthetic_record()])))
    result = await discover(make_provider(fake))
    assert result.source_stats[0].completed is True
    assert len(fake.requests) == 1


# ---------------------------------------------------------------------------
# T05 — mapping
# ---------------------------------------------------------------------------


async def test_t05_maps_the_sanitized_canary_sample() -> None:
    job = load_canary_sample()
    fake = FakeGreenhouse(routes={"gitlab": [json_response(envelope([job]))]})
    provider = make_provider(fake, boards=(GreenhouseBoard("gitlab", "GitLab"),))
    (mapped,) = (await discover(provider)).jobs
    assert mapped.provider == "greenhouse"
    assert mapped.source == "greenhouse"
    assert mapped.source_tenant_id == "gitlab"
    assert mapped.source_job_id == "8396674002"
    assert mapped.requisition_id_raw == "5899"
    assert mapped.title == "Manager, Solutions Architects - San Francisco "
    assert mapped.location == "Remote, US"
    assert mapped.company == "GitLab"
    assert mapped.source_url == mapped.canonical_url == job["absolute_url"]
    assert mapped.posted_at == datetime.fromisoformat("2026-03-06T14:25:31-05:00")
    assert mapped.discovered_at == FIXED_NOW
    assert mapped.raw == job


async def test_t05_maps_synthetic_record_and_takes_company_from_configuration() -> None:
    record = synthetic_record(requisition_id=4242)
    fake = single_board(json_response(envelope([record])))
    (mapped,) = (await discover(make_provider(fake))).jobs
    assert mapped.company == "Acme Synthetic Co"
    assert mapped.company != record["company_name"]
    assert mapped.source_job_id == "1000001"
    assert mapped.requisition_id_raw == "4242"
    assert mapped.title == "Synthetic Platform Engineer"
    assert mapped.location == "Remote, Synthetic Region"
    assert mapped.apply_url is None
    assert mapped.description is None
    assert mapped.compensation_text is None


@pytest.mark.parametrize(
    ("overrides", "title", "location", "requisition"),
    [
        ({"title": None, "location": None, "requisition_id": None}, None, None, None),
        (
            {"title": " \t\n\r", "location": {"name": "  "}, "requisition_id": "  "},
            None,
            None,
            None,
        ),
        ({"location": {}}, "Synthetic Platform Engineer", None, "SYN-REQ-1"),
        (
            {"title": "  Padded Title  "},
            "  Padded Title  ",
            "Remote, Synthetic Region",
            "SYN-REQ-1",
        ),
    ],
)
async def test_t05_absent_null_and_whitespace_optional_text_mean_absent(
    overrides: dict[str, Any], title: str | None, location: str | None, requisition: str | None
) -> None:
    record = synthetic_record(**overrides)
    for key in ("title", "location", "requisition_id"):
        if key in overrides and overrides[key] is None:
            del record[key]
    fake = single_board(json_response(envelope([record])))
    (mapped,) = (await discover(make_provider(fake))).jobs
    assert (mapped.title, mapped.location, mapped.requisition_id_raw) == (
        title,
        location,
        requisition,
    )


# ---------------------------------------------------------------------------
# T06 — record validation (A5, A7)
# ---------------------------------------------------------------------------


GOOD = synthetic_record(1000001)


async def assert_record_skipped(bad: Any) -> None:
    fake = single_board(json_response(envelope([bad, GOOD])))
    result = await discover(make_provider(fake))
    assert [job.source_job_id for job in result.jobs] == ["1000001"]
    stats = result.source_stats[0]
    assert stats.completed is True
    assert stats.incomplete_results is True
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.PARSE_ERROR
    assert error.detail == "greenhouse board=acme-synthetic skipped_records=1"


@pytest.mark.parametrize("job_id", [None, "", "   ", True, False, 1.5, [1], {"id": 1}])
async def test_t06_unusable_ids_skip_the_record(job_id: Any) -> None:
    await assert_record_skipped(synthetic_record(job_id, absolute_url="https://x.example/1"))


@pytest.mark.parametrize(
    "url",
    [
        None,
        42,
        "",
        "/acme-synthetic/jobs/5",
        "http://job-boards.greenhouse.io/acme-synthetic/jobs/5",
        "javascript:alert(1)",
        "https://user:pass@job-boards.greenhouse.io/jobs/5",
        "https://user@job-boards.greenhouse.io/jobs/5",
        "https:///jobs/5",
        "https://job boards.greenhouse.io/jobs/5",
        "https://job-boards.greenhouse.io/jobs/5 ",
        "https://job-boards.greenhouse.io/jobs/\t5",
        "https://job-boards.greenhouse.io:0/jobs/5",
        "https://job-boards.greenhouse.io:99999/jobs/5",
        "https://job-boards.greenhouse.io:abc/jobs/5",
        "https://-bad-.greenhouse.io/jobs/5",
        "https://bad..greenhouse.io/jobs/5",
        "https://exämple.com/jobs/5",
    ],
)
async def test_t06_url_boundary_rejections_skip_the_record(url: Any) -> None:
    await assert_record_skipped(synthetic_record(5, absolute_url=url))


@pytest.mark.parametrize(
    "url",
    [
        "https://job-boards.greenhouse.io/acme-synthetic/jobs/5",
        "HTTPS://Careers.Acme-Synthetic.example:8443/jobs?gh_jid=5",
        "https://careers.acme-synthetic.example/jobs/5#apply",
    ],
)
async def test_t06_valid_https_urls_are_kept(url: str) -> None:
    fake = single_board(json_response(envelope([synthetic_record(5, absolute_url=url)])))
    (mapped,) = (await discover(make_provider(fake))).jobs
    assert mapped.source_url == url


@pytest.mark.parametrize(
    "first_published",
    ["2026-09-01T09:30:00", "not a date", "   ", "", 1725000000, ["2026-09-01T09:30:00Z"]],
)
async def test_t06_invalid_timestamps_skip_the_record(first_published: Any) -> None:
    await assert_record_skipped(synthetic_record(5, first_published=first_published))


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": 123},
        {"title": ["Synthetic"]},
        {"location": "Remote"},
        {"location": ["Remote"]},
        {"location": {"name": 7}},
        {"requisition_id": True},
        {"requisition_id": 1.5},
        {"requisition_id": {"id": 1}},
    ],
)
async def test_t06_wrong_type_optional_fields_skip_the_record(overrides: dict[str, Any]) -> None:
    await assert_record_skipped(synthetic_record(5, **overrides))


@pytest.mark.parametrize("bad", ["a string", 5, None, ["list"]])
async def test_t06_non_object_records_skip(bad: Any) -> None:
    await assert_record_skipped(bad)


# ---------------------------------------------------------------------------
# T07 — raw preservation
# ---------------------------------------------------------------------------


async def test_t07_raw_is_the_whole_record_structurally() -> None:
    record = synthetic_record()
    fake = single_board(json_response(envelope([record])))
    (mapped,) = (await discover(make_provider(fake))).jobs
    assert mapped.raw == record
    assert canonical_json_hash(mapped.raw) == canonical_json_hash(record)
    assert mapped.raw["unknown_future_field"] == {"kept": [1, 2.5, None, "x"]}
    assert mapped.raw["content"] == record["content"]
    assert mapped.raw["metadata"] == record["metadata"]


async def test_t07_raw_is_deep_copied_without_aliasing() -> None:
    first = synthetic_record(1000001)
    second = synthetic_record(1000002)
    fake = single_board(json_response(envelope([first, second])))
    jobs = (await discover(make_provider(fake))).jobs
    jobs[0].raw["metadata"][0]["value"][1]["nested"] = "mutated"
    jobs[0].raw["unknown_future_field"]["kept"].append("mutated")
    assert jobs[1].raw["metadata"][0]["value"][1]["nested"] is True
    assert jobs[1].raw["unknown_future_field"]["kept"] == [1, 2.5, None, "x"]
    assert jobs[0].raw is not jobs[1].raw


# ---------------------------------------------------------------------------
# T08–T11 — outcomes (A1–A3)
# ---------------------------------------------------------------------------


async def test_t08_empty_jobs_is_completed_successful_empty() -> None:
    result = await discover(make_provider(single_board(json_response(envelope([])))))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 0, False)
    assert result.errors == []
    assert result.possibly_incomplete is False


async def test_t09_multiple_jobs_across_two_boards() -> None:
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [json_response(envelope([synthetic_record(1), synthetic_record(2)]))],
            "beta-synthetic": [json_response(envelope([synthetic_record(3, "beta-synthetic")]))],
        }
    )
    result = await discover(make_provider(fake, boards=(ACME, BETA)))
    assert [(j.source_tenant_id, j.source_job_id, j.company) for j in result.jobs] == [
        ("acme-synthetic", "1", "Acme Synthetic Co"),
        ("acme-synthetic", "2", "Acme Synthetic Co"),
        ("beta-synthetic", "3", "Beta Synthetic Co"),
    ]
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 3, False)
    assert result.possibly_incomplete is False


async def test_t10_valid_empty_board_plus_404_board_is_completed_incomplete() -> None:
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [json_response(envelope([]))],
            "beta-synthetic": [httpx.Response(404)],
        }
    )
    result = await discover(make_provider(fake, boards=(ACME, BETA)))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 0, True)
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.NOT_FOUND


async def test_t10_valid_job_plus_failed_board_is_completed_incomplete() -> None:
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [json_response(envelope([synthetic_record()]))],
            "beta-synthetic": [httpx.Response(500)],
        }
    )
    result = await discover(make_provider(fake, boards=(ACME, BETA)))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 1, True)
    assert result.errors[0].category is ProviderErrorCategory.UPSTREAM_ERROR


async def test_t11_all_boards_failed_is_not_completed() -> None:
    fake = FakeGreenhouse(
        routes={"acme-synthetic": [httpx.Response(404)], "beta-synthetic": [httpx.Response(500)]}
    )
    result = await discover(make_provider(fake, boards=(ACME, BETA)))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (False, 0, False)
    assert result.jobs == []
    assert len(result.errors) == 2


async def test_t11_all_invalid_nonempty_response_is_failure_not_successful_empty() -> None:
    bad = [synthetic_record(None), synthetic_record(2, absolute_url="http://x.example/2")]
    result = await discover(make_provider(single_board(json_response(envelope(bad)))))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (False, 0, False)
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.PARSE_ERROR
    assert error.detail == (
        "greenhouse board=acme-synthetic failure=no_usable_records status=200 attempts=1"
    )


async def test_t11_all_invalid_board_plus_usable_board_is_completed_incomplete() -> None:
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [json_response(envelope([synthetic_record(None)]))],
            "beta-synthetic": [json_response(envelope([synthetic_record(3, "beta-synthetic")]))],
        }
    )
    result = await discover(make_provider(fake, boards=(ACME, BETA)))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 1, True)


# ---------------------------------------------------------------------------
# T12 — status taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "category", "retryable", "attempts"),
    [
        (401, ProviderErrorCategory.AUTH_ERROR, False, 1),
        (403, ProviderErrorCategory.BLOCKED, False, 1),
        (404, ProviderErrorCategory.NOT_FOUND, False, 1),
        (410, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (429, ProviderErrorCategory.RATE_LIMITED, True, 3),
        (500, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (501, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (502, ProviderErrorCategory.UPSTREAM_ERROR, True, 3),
        (503, ProviderErrorCategory.UPSTREAM_ERROR, True, 3),
        (504, ProviderErrorCategory.UPSTREAM_ERROR, True, 3),
        (301, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (302, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (204, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (201, ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
    ],
)
async def test_t12_status_taxonomy(
    status: int, category: ProviderErrorCategory, retryable: bool, attempts: int
) -> None:
    fake = single_board(httpx.Response(status, headers={"content-type": "application/json"}))
    result = await discover(make_provider(fake))
    (error,) = result.errors
    assert error.category is category
    assert error.retryable is retryable
    assert len(fake.requests) == attempts
    assert error.detail is not None and f"status={status} attempts={attempts}" in error.detail


@pytest.mark.parametrize(
    ("exception", "kind", "category", "retryable", "attempts"),
    [
        (httpx.ConnectTimeout("t"), "timeout", ProviderErrorCategory.TIMEOUT, True, 3),
        (httpx.ReadTimeout("t"), "timeout", ProviderErrorCategory.TIMEOUT, True, 3),
        (httpx.WriteTimeout("t"), "timeout", ProviderErrorCategory.TIMEOUT, True, 3),
        (httpx.PoolTimeout("t"), "timeout", ProviderErrorCategory.TIMEOUT, True, 3),
        (httpx.ConnectError("c"), "connect_error", ProviderErrorCategory.UPSTREAM_ERROR, True, 3),
        (httpx.ReadError("r"), "transport_error", ProviderErrorCategory.UPSTREAM_ERROR, False, 1),
        (
            httpx.RemoteProtocolError("p"),
            "transport_error",
            ProviderErrorCategory.UPSTREAM_ERROR,
            False,
            1,
        ),
    ],
)
async def test_t12_transport_exception_taxonomy(
    exception: Exception,
    kind: str,
    category: ProviderErrorCategory,
    retryable: bool,
    attempts: int,
) -> None:
    fake = single_board(exception)
    result = await discover(make_provider(fake))
    (error,) = result.errors
    assert error.category is category
    assert error.retryable is retryable
    assert len(fake.requests) == attempts
    assert error.detail == (
        f"greenhouse board=acme-synthetic failure={kind} status=none attempts={attempts}"
    )


# ---------------------------------------------------------------------------
# T13 — retries
# ---------------------------------------------------------------------------


async def test_t13_eligible_failures_retry_then_succeed() -> None:
    sleeps = Sleeps()
    fake = single_board(
        httpx.Response(503), httpx.Response(502), json_response(envelope([synthetic_record()]))
    )
    result = await discover(make_provider(fake, sleeps=sleeps))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.retry_count) == (True, 1, 2)
    assert result.errors == []
    assert sleeps.calls == [0.5, 1.0]
    assert len(fake.requests) == 3


async def test_t13_eligible_failures_stop_at_max_attempts() -> None:
    sleeps = Sleeps()
    fake = single_board(httpx.Response(503))
    result = await discover(make_provider(fake, sleeps=sleeps))
    assert len(fake.requests) == 3
    assert sleeps.calls == [0.5, 1.0]
    assert result.source_stats[0].retry_count == 2
    assert result.errors[0].detail == (
        "greenhouse board=acme-synthetic failure=http_status status=503 attempts=3"
    )


@pytest.mark.parametrize("status", [500, 404, 401, 403])
async def test_t13_ineligible_failures_make_exactly_one_attempt(status: int) -> None:
    sleeps = Sleeps()
    fake = single_board(httpx.Response(status))
    result = await discover(make_provider(fake, sleeps=sleeps))
    assert len(fake.requests) == 1
    assert sleeps.calls == []
    assert result.source_stats[0].retry_count == 0


async def test_t13_backoff_is_capped() -> None:
    sleeps = Sleeps()
    settings = GreenhouseClientSettings(max_attempts=5, backoff_base=1.0, backoff_cap=2.0)
    fake = single_board(httpx.Response(504))
    await discover(make_provider(fake, settings=settings, sleeps=sleeps))
    assert len(fake.requests) == 5
    assert sleeps.calls == [1.0, 2.0, 2.0, 2.0]


async def test_t13_single_attempt_setting_never_retries() -> None:
    sleeps = Sleeps()
    fake = single_board(httpx.Response(503))
    await discover(
        make_provider(fake, settings=GreenhouseClientSettings(max_attempts=1), sleeps=sleeps)
    )
    assert len(fake.requests) == 1
    assert sleeps.calls == []


# ---------------------------------------------------------------------------
# T14 — Retry-After
# ---------------------------------------------------------------------------


async def test_t14_retry_after_delta_is_honoured() -> None:
    sleeps = Sleeps()
    fake = single_board(
        httpx.Response(429, headers={"retry-after": "7"}),
        json_response(envelope([synthetic_record()])),
    )
    result = await discover(make_provider(fake, sleeps=sleeps))
    assert sleeps.calls == [7.0]
    stats = result.source_stats[0]
    assert stats.rate_limited is True
    assert stats.completed is True


async def test_t14_retry_after_at_cap_is_honoured() -> None:
    sleeps = Sleeps()
    fake = single_board(
        httpx.Response(503, headers={"retry-after": "30"}),
        json_response(envelope([synthetic_record()])),
    )
    await discover(make_provider(fake, sleeps=sleeps))
    assert sleeps.calls == [30.0]


async def test_t14_retry_after_above_cap_stops_retrying() -> None:
    sleeps = Sleeps()
    fake = single_board(httpx.Response(429, headers={"retry-after": "31"}))
    result = await discover(make_provider(fake, sleeps=sleeps))
    assert len(fake.requests) == 1
    assert sleeps.calls == []
    stats = result.source_stats[0]
    assert stats.rate_limited is True
    assert stats.completed is False
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.RATE_LIMITED
    assert error.retryable is True


@pytest.mark.parametrize("value", ["Wed, 21 Oct 2026 07:28:00 GMT", "-5", "1.5", "soon", ""])
async def test_t14_non_delta_retry_after_falls_back_to_backoff(value: str) -> None:
    sleeps = Sleeps()
    fake = single_board(
        httpx.Response(429, headers={"retry-after": value}),
        json_response(envelope([synthetic_record()])),
    )
    await discover(make_provider(fake, sleeps=sleeps))
    assert sleeps.calls == [0.5]


# ---------------------------------------------------------------------------
# T15 — limits, media type, JSON, envelope, completeness (A8)
# ---------------------------------------------------------------------------


async def test_t15_size_cap_stops_reading_the_stream() -> None:
    yielded: list[int] = []

    async def body() -> AsyncIterator[bytes]:
        for index in range(1000):
            yielded.append(index)
            yield b"x" * 8

    fake = single_board(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/json"}, content=body()
        )
    )
    settings = GreenhouseClientSettings(max_response_bytes=20)
    result = await discover(make_provider(fake, settings=settings))
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.PARSE_ERROR
    assert "failure=oversize" in (error.detail or "")
    assert len(yielded) <= 4
    assert len(fake.requests) == 1


async def test_t15_body_at_cap_is_accepted() -> None:
    payload = json.dumps(envelope([synthetic_record()])).encode("utf-8")
    fake = single_board(
        httpx.Response(200, headers={"content-type": "application/json"}, content=payload)
    )
    settings = GreenhouseClientSettings(max_response_bytes=len(payload))
    result = await discover(make_provider(fake, settings=settings))
    assert result.source_stats[0].completed is True


async def test_t15_attempt_deadline_uses_injected_clock() -> None:
    clock = {"t": 0.0}

    async def slow_body() -> AsyncIterator[bytes]:
        yield b'{"jobs": ['
        clock["t"] += 31.0
        yield b"]}"

    fake = single_board(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/json"}, content=slow_body()
        )
    )
    settings = GreenhouseClientSettings(max_attempts=1)
    result = await discover(make_provider(fake, settings=settings, monotonic=lambda: clock["t"]))
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.TIMEOUT
    assert error.retryable is True
    assert error.detail == "greenhouse board=acme-synthetic failure=deadline status=none attempts=1"


async def test_t15_within_deadline_is_accepted() -> None:
    clock = {"t": 0.0}

    async def body() -> AsyncIterator[bytes]:
        yield b'{"jobs": ['
        clock["t"] += 30.0
        yield b"]}"

    fake = single_board(
        lambda request: httpx.Response(
            200, headers={"content-type": "application/json"}, content=body()
        )
    )
    result = await discover(make_provider(fake, monotonic=lambda: clock["t"]))
    assert result.source_stats[0].completed is True


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "Application/JSON; charset=utf-8",
        "application/vnd.greenhouse+json",
        "APPLICATION/PROBLEM+JSON;charset=UTF-8",
    ],
)
async def test_t15_accepted_media_types(content_type: str) -> None:
    fake = single_board(json_response(envelope([synthetic_record()]), content_type=content_type))
    assert (await discover(make_provider(fake))).source_stats[0].completed is True


@pytest.mark.parametrize(
    "content_type",
    [
        "text/json",
        "text/notjson",
        "application/notjson",
        "application/json-seq",
        "application/+json",
        "text/html",
        "application/x+json/extra",
        "",
    ],
)
async def test_t15_rejected_media_types(content_type: str) -> None:
    fake = single_board(json_response(envelope([synthetic_record()]), content_type=content_type))
    result = await discover(make_provider(fake))
    assert result.source_stats[0].completed is False
    assert "failure=media_type" in (result.errors[0].detail or "")


async def test_t15_missing_content_type_is_rejected() -> None:
    fake = single_board(httpx.Response(200, content=json.dumps(envelope([])).encode()))
    result = await discover(make_provider(fake))
    assert "failure=media_type" in (result.errors[0].detail or "")


@pytest.mark.parametrize(
    ("body", "kind"),
    [
        (b"{not json", "invalid_json"),
        (b'{"jobs": [], "meta": {"total": NaN}}', "invalid_json"),
        (b'{"jobs": [{"id": Infinity}]}', "invalid_json"),
        (b'{"jobs": [{"id": -Infinity}]}', "invalid_json"),
        (b'{"jobs": [{"id": 1e999}]}', "invalid_json"),
        (b"\xff\xfe", "invalid_json"),
        pytest.param(b"[" * 100000 + b"]" * 100000, "invalid_json", id="deeply-nested"),
        (b"[]", "envelope"),
        (b"{}", "envelope"),
        (b'{"jobs": {}}', "envelope"),
        (b'{"jobs": null}', "envelope"),
    ],
)
async def test_t15_invalid_bodies_are_failures(body: bytes, kind: str) -> None:
    fake = single_board(
        httpx.Response(200, headers={"content-type": "application/json"}, content=body)
    )
    result = await discover(make_provider(fake))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (False, 0, False)
    (error,) = result.errors
    assert error.category is ProviderErrorCategory.PARSE_ERROR
    assert error.retryable is False
    assert error.detail == f"greenhouse board=acme-synthetic failure={kind} status=200 attempts=1"


@pytest.mark.parametrize(
    "payload",
    [
        {"jobs": [synthetic_record()]},
        {"jobs": [synthetic_record()], "meta": {}},
        {"jobs": [synthetic_record()], "meta": {"total": 1}},
    ],
)
async def test_t15_meta_without_claim_or_matching_total_is_complete(
    payload: dict[str, Any],
) -> None:
    result = await discover(make_provider(single_board(json_response(payload))))
    stats = result.source_stats[0]
    assert (stats.completed, stats.incomplete_results) == (True, False)
    assert result.warnings == []


@pytest.mark.parametrize(
    ("meta", "problem"),
    [
        (None, "malformed"),
        ([], "malformed"),
        ({"total": None}, "malformed"),
        ({"total": True}, "malformed"),
        ({"total": -1}, "malformed"),
        ({"total": "1"}, "malformed"),
        ({"total": 1.0}, "malformed"),
        ({"total": 2}, "mismatch"),
        ({"total": 0}, "mismatch"),
    ],
)
async def test_t15_failed_completeness_evidence_marks_incomplete(meta: Any, problem: str) -> None:
    payload = {"jobs": [synthetic_record()], "meta": meta}
    result = await discover(make_provider(single_board(json_response(payload))))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 1, True)
    assert result.warnings == [f"greenhouse board=acme-synthetic completeness_evidence={problem}"]
    assert result.errors == []


async def test_t15_empty_list_with_mismatched_total_is_completed_incomplete() -> None:
    payload = {"jobs": [], "meta": {"total": 3}}
    result = await discover(make_provider(single_board(json_response(payload))))
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 0, True)


# ---------------------------------------------------------------------------
# T16 — health (A4)
# ---------------------------------------------------------------------------


class Ticker:
    def __init__(self) -> None:
        self.current = FIXED_NOW

    def __call__(self) -> datetime:
        self.current = self.current + timedelta(seconds=1)
        return self.current


async def test_t16_initial_health() -> None:
    ticker = Ticker()
    provider = make_provider(single_board(json_response(envelope([]))), now=ticker)
    first = await provider.health()
    second = await provider.health()
    assert first.healthy is True
    (source,) = first.sources
    assert (source.healthy, source.last_success_at, source.last_failure_at) == (True, None, None)
    assert source.consecutive_failures == 0
    assert source.detail == "no discovery observed"
    assert second.last_checked_at > first.last_checked_at


async def test_t16_health_transitions() -> None:
    ticker = Ticker()
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [
                httpx.Response(404),
                httpx.Response(404),
                json_response(envelope([synthetic_record()])),
                json_response(envelope([])),
            ],
            "beta-synthetic": [
                httpx.Response(404),
                httpx.Response(404),
                httpx.Response(404),
                json_response(envelope([])),
            ],
        }
    )
    provider = make_provider(fake, boards=(ACME, BETA), now=ticker)

    await discover(provider)
    failed = (await provider.health()).sources[0]
    assert (failed.healthy, failed.consecutive_failures, failed.detail) == (
        False,
        1,
        "discovery failed",
    )
    assert failed.last_success_at is None and failed.last_failure_at is not None

    await discover(provider)
    failed_twice = await provider.health()
    assert failed_twice.healthy is False
    assert failed_twice.sources[0].consecutive_failures == 2

    await discover(provider)
    partial = await provider.health()
    assert partial.healthy is True
    (source,) = partial.sources
    assert (source.consecutive_failures, source.detail) == (0, "partial discovery observed")
    assert source.last_success_at is not None
    assert source.last_failure_at == source.last_success_at

    await discover(provider)
    succeeded = (await provider.health()).sources[0]
    assert (succeeded.healthy, succeeded.consecutive_failures, succeeded.detail) == (
        True,
        0,
        "discovery succeeded",
    )
    assert succeeded.last_success_at is not None
    assert source.last_failure_at is not None
    assert succeeded.last_failure_at == source.last_failure_at
    assert succeeded.last_success_at > source.last_success_at


async def test_t16_successful_empty_is_healthy_and_health_makes_no_request() -> None:
    fake = single_board(json_response(envelope([])))
    provider = make_provider(fake)
    await discover(provider)
    requests_before = len(fake.requests)
    health = await provider.health()
    assert health.healthy is True
    assert health.sources[0].detail == "discovery succeeded"
    assert len(fake.requests) == requests_before


# ---------------------------------------------------------------------------
# T17 — no payload or exception-text leakage
# ---------------------------------------------------------------------------


async def test_t17_no_payload_reaches_logs_details_or_warnings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    leaky = synthetic_record(1, title=f"{SENTINEL} title", content=f"<p>{SENTINEL}</p>")
    invalid = synthetic_record(2, absolute_url=f"http://{SENTINEL}.example/2")
    bodies: list[ResponseSpec] = [
        json_response({"jobs": [leaky, invalid], "meta": {"total": SENTINEL}}),
    ]
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": bodies,
            "beta-synthetic": [
                httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    content=f'{{"{SENTINEL}": true}}'.encode(),
                )
            ],
        }
    )
    result = await discover(make_provider(fake, boards=(ACME, BETA)))
    texts = [error.detail or "" for error in result.errors] + result.warnings
    assert texts
    assert all(SENTINEL not in text for text in texts)
    assert SENTINEL not in caplog.text


async def test_t17_envelope_failure_detail_never_contains_the_body() -> None:
    body = f"{SENTINEL} is not an envelope".encode()
    fake = single_board(
        httpx.Response(
            200, headers={"content-type": "application/json"}, content=b'"' + body + b'"'
        )
    )
    result = await discover(make_provider(fake))
    (error,) = result.errors
    assert error.detail == "greenhouse board=acme-synthetic failure=envelope status=200 attempts=1"


async def test_t17_exception_text_never_reaches_detail() -> None:
    fake = single_board(httpx.ReadError(SENTINEL))
    result = await discover(make_provider(fake))
    assert SENTINEL not in (result.errors[0].detail or "")


async def test_t17_raised_messages_are_fixed() -> None:
    provider = make_provider(single_board(json_response(envelope([]))))
    with pytest.raises(UnsupportedSourceQueryError) as raised:
        await provider.discover(SourceQuery(sources=[SENTINEL]))
    assert SENTINEL not in str(raised.value)


# ---------------------------------------------------------------------------
# T18 — import boundary
# ---------------------------------------------------------------------------


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            names.add(node.module)
    return names


def test_t18_httpx_is_imported_only_by_the_greenhouse_adapter() -> None:
    app_dir = BACKEND_DIR / "app"
    importers = sorted(
        path.relative_to(BACKEND_DIR).as_posix()
        for path in app_dir.rglob("*.py")
        if any(name == "httpx" or name.startswith("httpx.") for name in _imported_modules(path))
    )
    assert importers == ["app/providers/greenhouse.py"]


def test_t18_adapter_imports_no_forbidden_layer() -> None:
    forbidden = ("app.db", "app.normalization", "app.ingestion", "app.services", "app.api")
    imported = _imported_modules(BACKEND_DIR / "app" / "providers" / "greenhouse.py")
    assert not [name for name in imported if name.startswith(forbidden)]
    assert not [name for name in imported if name in {"logging", "ats_scrapers"}]


# ---------------------------------------------------------------------------
# T19 — labels
# ---------------------------------------------------------------------------


async def test_t19_greenhouse_label_everywhere() -> None:
    fake = FakeGreenhouse(
        routes={
            "acme-synthetic": [json_response(envelope([synthetic_record()]))],
            "beta-synthetic": [httpx.Response(404)],
        }
    )
    provider = make_provider(fake, boards=(ACME, BETA))
    result = await discover(provider)
    assert provider.name == result.provider == "greenhouse"
    assert all(job.provider == job.source == "greenhouse" for job in result.jobs)
    assert [s.source for s in result.source_stats] == ["greenhouse"]
    assert all(error.source == "greenhouse" for error in result.errors)
    assert "ats_scrapers" not in result.model_dump_json()
    assert (await provider.health()).provider == "greenhouse"


# ---------------------------------------------------------------------------
# T20 — canonical duplicate identity (A6)
# ---------------------------------------------------------------------------


async def test_t20_canonical_duplicates_are_all_skipped() -> None:
    records = [
        synthetic_record(1),
        synthetic_record(
            "1", absolute_url="https://job-boards.greenhouse.io/acme-synthetic/jobs/1b"
        ),
        synthetic_record(
            " 1 ", absolute_url="https://job-boards.greenhouse.io/acme-synthetic/jobs/1c"
        ),
        synthetic_record(2),
        synthetic_record(3),
    ]
    result = await discover(make_provider(single_board(json_response(envelope(records)))))
    assert [job.source_job_id for job in result.jobs] == ["2", "3"]
    stats = result.source_stats[0]
    assert (stats.completed, stats.jobs_found, stats.incomplete_results) == (True, 2, True)
    (error,) = result.errors
    assert error.detail == "greenhouse board=acme-synthetic skipped_records=3"


async def test_t20_only_duplicates_is_a_failure() -> None:
    records = [synthetic_record(7), synthetic_record("7\t")]
    result = await discover(make_provider(single_board(json_response(envelope(records)))))
    assert result.source_stats[0].completed is False
    assert "failure=no_usable_records" in (result.errors[0].detail or "")


async def test_t20_distinct_ids_are_stable_positive_controls() -> None:
    records = [synthetic_record(10), synthetic_record("11"), synthetic_record(" 12")]
    result = await discover(make_provider(single_board(json_response(envelope(records)))))
    assert [job.source_job_id for job in result.jobs] == ["10", "11", " 12"]
    assert result.errors == []
