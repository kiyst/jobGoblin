"""Offline tests for `fetch_greenhouse_evaluation_postings.py` -- every
network-shaped test uses `httpx.MockTransport` (an in-process transport,
never a real socket), mirroring `test_canary_greenhouse_mapping.py`'s own
established pattern exactly. No test in this file may cause a real HTTP
request."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import httpx
import pytest

import scripts.fetch_greenhouse_evaluation_postings as fetcher
from scripts.fetch_greenhouse_evaluation_postings import (
    BoardAcquisitionSpec,
    EvaluationFetchError,
    FatalBudgetExhaustedError,
    SanitizedCandidate,
    _build_detail_url,
    _has_meaningful_text,
    _is_usable_detail_candidate,
    _parse_board_arg,
    _redact_contact_patterns,
    _RunBudget,
    _sanitize_job_detail,
    _select_job_ids,
    _stream_get,
    _validate_detail_response,
    _write_json_atomic_create_only,
    run_acquisition,
)


def _mock_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _spec(
    board_token: str,
    employer: str,
    *,
    content_mode: str = "standard",
    mode_basis_ref: str | None = None,
) -> BoardAcquisitionSpec:
    return BoardAcquisitionSpec(
        board_token=board_token,
        employer=employer,
        content_mode=content_mode,  # type: ignore[arg-type]
        mode_basis_ref=mode_basis_ref,
    )


# ---------------------------------------------------------------------------
# _build_detail_url
# ---------------------------------------------------------------------------
def test_build_detail_url_uses_fixed_origin_and_validated_token() -> None:
    url = _build_detail_url("acme", "123")
    assert url == "https://boards-api.greenhouse.io/v1/boards/acme/jobs/123"


def test_build_detail_url_rejects_non_numeric_job_id() -> None:
    with pytest.raises(EvaluationFetchError, match="not a conservative numeric id"):
        _build_detail_url("acme", "123; DROP TABLE")


def test_build_detail_url_rejects_unsafe_board_token() -> None:
    with pytest.raises(ValueError, match="conservative ASCII slug"):
        _build_detail_url("../../etc", "123")


# ---------------------------------------------------------------------------
# _redact_contact_patterns
# ---------------------------------------------------------------------------
def test_redact_contact_patterns_redacts_email() -> None:
    result = _redact_contact_patterns("Contact jane.doe@example.com for details.")
    assert "jane.doe@example.com" not in result
    assert "[REDACTED_EMAIL]" in result


def test_redact_contact_patterns_redacts_phone() -> None:
    result = _redact_contact_patterns("Call us at 555-123-4567 today.")
    assert "555-123-4567" not in result
    assert "[REDACTED_PHONE]" in result


def test_redact_contact_patterns_leaves_ordinary_text_unchanged() -> None:
    text = "We are looking for a Python engineer."
    assert _redact_contact_patterns(text) == text


# ---------------------------------------------------------------------------
# _select_job_ids
# ---------------------------------------------------------------------------
def test_select_job_ids_is_deterministic_and_order_independent() -> None:
    jobs = [{"id": 30}, {"id": 10}, {"id": 20}]
    assert _select_job_ids(jobs, limit=10) == ["10", "20", "30"]


def test_select_job_ids_ignores_jobs_missing_a_usable_id() -> None:
    jobs: list[dict[str, Any]] = [{"id": 1}, {"title": "no id"}, {"id": ""}, {"id": 2}]
    assert _select_job_ids(jobs, limit=10) == ["1", "2"]


def test_select_job_ids_respects_the_limit() -> None:
    """Sorting is by *stringified* id, lexicographic, matching
    `canary_greenhouse.select_representative_job`'s own established
    rule exactly -- so among ids 1-20 as strings, "10".."18" sort before
    "2", not after it."""
    jobs = [{"id": n} for n in range(1, 21)]
    selected = _select_job_ids(jobs, limit=10)
    assert selected == ["1", "10", "11", "12", "13", "14", "15", "16", "17", "18"]
    assert len(selected) == 10


def test_select_job_ids_deduplicates_repeated_ids() -> None:
    """A list response with duplicate ids must never waste part of the
    detail-request budget re-fetching the same job twice."""
    jobs = [{"id": 1}, {"id": 1}, {"id": 2}, {"id": 2}, {"id": 3}]
    assert _select_job_ids(jobs, limit=10) == ["1", "2", "3"]


# ---------------------------------------------------------------------------
# _RunBudget
# ---------------------------------------------------------------------------
def test_run_budget_accepts_consumption_under_the_cap() -> None:
    budget = _RunBudget(max_total_bytes=1_000)
    budget.consume(500)
    budget.consume(400)
    assert budget.consumed_bytes == 900


def test_run_budget_raises_once_the_cap_is_exceeded() -> None:
    """The total-run budget's exhaustion exception must be
    `FatalBudgetExhaustedError`, never plain `EvaluationFetchError` --
    `run_acquisition`'s per-board handling must not be able to catch it
    as an ordinary single-board failure."""
    budget = _RunBudget(max_total_bytes=1_000)
    budget.consume(600)
    with pytest.raises(FatalBudgetExhaustedError, match="total-run byte cap exceeded"):
        budget.consume(500)


def test_fatal_budget_exhausted_error_is_not_an_evaluation_fetch_error() -> None:
    assert not issubclass(FatalBudgetExhaustedError, EvaluationFetchError)


# ---------------------------------------------------------------------------
# _stream_get -- every chunk must be charged to the run budget before its
# effect on the per-response cap is evaluated.
# ---------------------------------------------------------------------------
async def test_stream_get_charges_run_budget_even_when_per_response_cap_rejects_the_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A chunk that overflows the (tiny, here) per-response cap must
    still be charged to the cumulative run budget before that rejection
    is decided -- the cumulative cap measures bytes actually received,
    never only bytes a well-behaved response happened to stay under."""
    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 5)
    body = b'{"id": 1, "title": "Engineer", "content": "<p>Hi</p>"}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    run_budget = fetcher._RunBudget(max_total_bytes=10**9)
    async with _mock_client(handler) as client:
        with pytest.raises(EvaluationFetchError, match="per-response byte cap exceeded"):
            await _stream_get(
                "https://boards-api.greenhouse.io/v1/boards/acme/jobs/1",
                client=client,
                run_budget=run_budget,
            )

    assert run_budget.consumed_bytes > fetcher.MAX_RESPONSE_BYTES


async def test_run_acquisition_repeated_per_response_overflows_still_hit_the_cumulative_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every response in this test individually overflows the tiny
    per-response cap and is treated as an ordinary per-board failure --
    but each overflowing chunk must still be charged to the cumulative
    run budget before that per-response rejection is decided, so enough
    repeated overflow cannot evade the total-run cap."""
    body = b'{"jobs": [{"id": 1}]}'
    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 5)
    monkeypatch.setattr(fetcher, "MAX_TOTAL_RUN_BYTES", len(body) + 10)

    requested_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_tokens.append(request.url.path.split("/")[3])
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    async with _mock_client(handler) as client:
        with pytest.raises(FatalBudgetExhaustedError):
            await run_acquisition(
                [_spec("board_a", "A"), _spec("board_b", "B"), _spec("board_c", "C")],
                client=client,
            )

    assert requested_tokens == ["board_a", "board_b"]


async def test_run_acquisition_simultaneous_overflow_raises_fatal_error_and_stops_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a single chunk simultaneously exceeds both the per-response
    cap and the cumulative run budget, `FatalBudgetExhaustedError` must
    take precedence over the ordinary per-response
    `EvaluationFetchError` and abort the entire run -- not merely this
    one board."""
    body = b'{"jobs": [{"id": 1}]}'
    monkeypatch.setattr(fetcher, "MAX_RESPONSE_BYTES", 5)
    monkeypatch.setattr(fetcher, "MAX_TOTAL_RUN_BYTES", 5)

    requested_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_tokens.append(request.url.path.split("/")[3])
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    async with _mock_client(handler) as client:
        with pytest.raises(FatalBudgetExhaustedError):
            await run_acquisition([_spec("board_a", "A"), _spec("board_b", "B")], client=client)

    assert requested_tokens == ["board_a"]


# ---------------------------------------------------------------------------
# _validate_detail_response -- offline, synthetic bytes only
# ---------------------------------------------------------------------------
def test_validate_detail_response_accepts_a_well_formed_payload() -> None:
    body = b'{"id": 42, "title": "Engineer", "content": "<p>Hi</p>"}'
    payload = _validate_detail_response(
        body, content_type="application/json", status_code=200, board_token="acme", job_id="42"
    )
    assert payload["id"] == 42


def test_validate_detail_response_rejects_non_2xx_status() -> None:
    with pytest.raises(EvaluationFetchError, match="non-2xx status"):
        _validate_detail_response(
            b"{}", content_type="application/json", status_code=404, board_token="acme", job_id="1"
        )


def test_validate_detail_response_rejects_unexpected_content_type() -> None:
    with pytest.raises(EvaluationFetchError, match="unexpected content-type"):
        _validate_detail_response(
            b"{}", content_type="text/html", status_code=200, board_token="acme", job_id="1"
        )


def test_validate_detail_response_rejects_invalid_json() -> None:
    with pytest.raises(EvaluationFetchError, match="invalid JSON"):
        _validate_detail_response(
            b"not json",
            content_type="application/json",
            status_code=200,
            board_token="acme",
            job_id="1",
        )


def test_validate_detail_response_rejects_non_dict_payload() -> None:
    with pytest.raises(EvaluationFetchError, match="malformed detail schema"):
        _validate_detail_response(
            b"[1, 2]",
            content_type="application/json",
            status_code=200,
            board_token="acme",
            job_id="1",
        )


def test_validate_detail_response_rejects_id_mismatch() -> None:
    with pytest.raises(EvaluationFetchError, match="id mismatch"):
        _validate_detail_response(
            b'{"id": 999}',
            content_type="application/json",
            status_code=200,
            board_token="acme",
            job_id="1",
        )


def test_validate_detail_response_error_never_contains_response_body() -> None:
    body = b'{"id": 999, "content": "SECRET DESCRIPTION TEXT"}'
    with pytest.raises(EvaluationFetchError) as exc_info:
        _validate_detail_response(
            body, content_type="application/json", status_code=200, board_token="acme", job_id="1"
        )
    assert "SECRET DESCRIPTION TEXT" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# _sanitize_job_detail -- only id/title/location.name/content are ever read
# ---------------------------------------------------------------------------
def _sanitize(payload: dict[str, Any], **overrides: Any) -> SanitizedCandidate:
    kwargs: dict[str, Any] = {
        "board_token": "acme",
        "employer": "Acme",
        "accessed_at": "t",
        "content_mode": "standard",
        "mode_basis_ref": None,
    }
    kwargs.update(overrides)
    return _sanitize_job_detail(payload, **kwargs)


def test_sanitize_job_detail_extracts_only_the_allowed_fields() -> None:
    payload = {
        "id": 1,
        "title": "Engineer",
        "location": {"name": "Remote"},
        "content": "<p>Skills: Python</p>",
        "metadata": ["should never be read"],
        "internal_job_id": "should never be read",
        "departments": [{"name": "should never be read"}],
    }
    candidate = _sanitize(payload)
    assert candidate.title == "Engineer"
    assert candidate.location_raw == "Remote"
    assert candidate.description == "Skills: Python"


def test_sanitize_job_detail_handles_missing_content() -> None:
    payload = {"id": 1, "title": "Engineer"}
    candidate = _sanitize(payload)
    assert candidate.description is None


def test_sanitize_job_detail_raises_on_unclosed_script_content() -> None:
    payload = {"id": 1, "title": "Engineer", "content": "<script>oops"}
    with pytest.raises(EvaluationFetchError, match="HTML conversion failed"):
        _sanitize(payload)


def test_sanitize_job_detail_redacts_title_and_description() -> None:
    payload = {
        "id": 1,
        "title": "Contact jane@example.com",
        "content": "<p>Call 555-123-4567</p>",
    }
    candidate = _sanitize(payload)
    assert candidate.title is not None and "jane@example.com" not in candidate.title
    assert candidate.description is not None and "555-123-4567" not in candidate.description


def test_sanitize_job_detail_propagates_content_mode_and_basis_ref() -> None:
    payload = {"id": 1, "title": "Engineer", "content": "<p>Hi</p>"}
    candidate = _sanitize(
        payload, content_mode="declared-double-escaped", mode_basis_ref="prior-capture:abc123"
    )
    assert candidate.content_mode == "declared-double-escaped"
    assert candidate.mode_basis_ref == "prior-capture:abc123"


def test_sanitize_job_detail_raises_html_double_encoding_error_as_evaluation_fetch_error() -> None:
    """A rejection under `declared-double-escaped` mode is still a
    sanitization failure isolated to this one job -- caught the same way
    as any other `HtmlConversionError` subclass."""
    payload = {"id": 1, "title": "Engineer", "content": "<p>&lt;b&gt;mixed&lt;/b&gt;</p>"}
    with pytest.raises(EvaluationFetchError, match="HTML conversion failed"):
        _sanitize(payload, content_mode="declared-double-escaped")


# ---------------------------------------------------------------------------
# _has_meaningful_text / _is_usable_detail_candidate
# ---------------------------------------------------------------------------
def _candidate(**overrides: Any) -> SanitizedCandidate:
    base: dict[str, Any] = {
        "board_token": "acme",
        "employer": "Acme",
        "job_id": "1",
        "title": "Engineer",
        "description": "Some description",
        "location_raw": None,
        "accessed_at": "t",
        "content_mode": "standard",
        "mode_basis_ref": None,
    }
    base.update(overrides)
    return SanitizedCandidate(**base)


def test_has_meaningful_text_accepts_ordinary_text() -> None:
    assert _has_meaningful_text("Engineer")


def test_has_meaningful_text_rejects_none() -> None:
    assert not _has_meaningful_text(None)


def test_has_meaningful_text_rejects_empty_string() -> None:
    assert not _has_meaningful_text("")


def test_has_meaningful_text_rejects_ascii_whitespace_only() -> None:
    assert not _has_meaningful_text("   \t\n  ")


def test_has_meaningful_text_rejects_nbsp_only() -> None:
    """The exact sanitized-description shape a `<p>&nbsp;</p>` source
    would produce after HTML conversion (NBSP is Unicode whitespace by
    `str.isspace()`, so it must be rejected the same as ASCII
    whitespace)."""
    assert not _has_meaningful_text(" ")


def test_has_meaningful_text_rejects_format_character_only() -> None:
    """A zero-width space (category `Cf`) is not `str.isspace()`, so the
    helper must reject it via the explicit Unicode-category check, not
    `str.isspace()` alone."""
    assert not _has_meaningful_text("​")


def test_has_meaningful_text_rejects_mixed_whitespace_and_format_characters() -> None:
    assert not _has_meaningful_text(" ​ ﻿ \t")


def test_has_meaningful_text_accepts_text_mixed_with_whitespace_and_format_characters() -> None:
    assert _has_meaningful_text(" ​Engineer  ")


def test_is_usable_detail_candidate_accepts_title_and_content() -> None:
    assert _is_usable_detail_candidate(_candidate())


def test_is_usable_detail_candidate_rejects_missing_title() -> None:
    assert not _is_usable_detail_candidate(_candidate(title=None))


def test_is_usable_detail_candidate_rejects_empty_title() -> None:
    assert not _is_usable_detail_candidate(_candidate(title=""))


def test_is_usable_detail_candidate_rejects_ascii_whitespace_only_title() -> None:
    assert not _is_usable_detail_candidate(_candidate(title="   \t  "))


def test_is_usable_detail_candidate_rejects_nbsp_only_description() -> None:
    """Exercised through the real HTML conversion path: `<p>&nbsp;</p>`
    sanitizes to a single NBSP character, which must not count as
    meaningful content."""
    from scripts.greenhouse_html_convert import convert_html_to_text

    description = convert_html_to_text("<p>&nbsp;</p>")
    assert not _is_usable_detail_candidate(_candidate(description=description))


def test_is_usable_detail_candidate_rejects_format_character_only_content() -> None:
    assert not _is_usable_detail_candidate(_candidate(description="​​"))


def test_is_usable_detail_candidate_rejects_missing_content() -> None:
    assert not _is_usable_detail_candidate(_candidate(description=None))


def test_is_usable_detail_candidate_rejects_empty_content() -> None:
    assert not _is_usable_detail_candidate(_candidate(description=""))


def test_is_usable_detail_candidate_accepts_ordinary_non_empty_title_and_content() -> None:
    assert _is_usable_detail_candidate(_candidate(title="Engineer", description="A real job."))


# ---------------------------------------------------------------------------
# run_acquisition -- httpx.MockTransport, never a real socket
# ---------------------------------------------------------------------------
def _list_response(job_ids: list[int]) -> httpx.Response:
    jobs = [{"id": job_id} for job_id in job_ids]
    return httpx.Response(200, headers={"content-type": "application/json"}, json={"jobs": jobs})


def _detail_response(job_id: int, *, title: str = "Engineer") -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "application/json"},
        json={"id": job_id, "title": title, "content": "<p>Hi</p>"},
    )


async def test_run_acquisition_succeeds_with_two_boards() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response([1, 2])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        candidates = await run_acquisition(
            [_spec("board_a", "Employer A"), _spec("board_b", "Employer B")], client=client
        )

    assert len({c.board_token for c in candidates}) == 2
    assert len(candidates) == 4  # 2 jobs per board * 2 boards


async def test_fetch_board_enforces_max_requests_per_board_as_a_real_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`MAX_REQUESTS_PER_BOARD` must be an actually-enforced ceiling, not
    merely an emergent consequence of `_select_job_ids`'s own limit --
    proven by independently loosening the selection limit and confirming
    this check, not that one, is what catches the overrun."""
    monkeypatch.setattr(fetcher, "MAX_DETAIL_REQUESTS_PER_BOARD", 20)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response(list(range(1, 26)))
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        with pytest.raises(EvaluationFetchError, match="MAX_REQUESTS_PER_BOARD"):
            await fetcher._fetch_board(
                _spec("board_a", "A"),
                client=client,
                run_budget=fetcher._RunBudget(max_total_bytes=10**9),
            )


async def test_run_acquisition_caps_detail_requests_at_ten_per_board() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response(list(range(1, 26)))  # 25 jobs offered
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        candidates = await run_acquisition(
            [_spec("board_a", "Employer A"), _spec("board_b", "Employer B")], client=client
        )

    # 1 list + 10 detail per board, 2 boards
    assert request_count == 22
    assert len(candidates) == 20


async def test_run_acquisition_never_sends_content_true_on_list_request() -> None:
    seen_query_strings: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            seen_query_strings.append(request.url.query)
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        await run_acquisition([_spec("board_a", "A"), _spec("board_b", "B")], client=client)

    assert all(b"content" not in q for q in seen_query_strings)


async def test_run_acquisition_never_sends_questions_or_pay_transparency_on_detail_request() -> (
    None
):
    seen_detail_query_strings: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response([1])
        seen_detail_query_strings.append(request.url.query)
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        await run_acquisition([_spec("board_a", "A"), _spec("board_b", "B")], client=client)

    assert all(
        b"questions" not in q and b"pay_transparency" not in q for q in seen_detail_query_strings
    )


async def test_run_acquisition_logs_a_reachable_but_empty_board(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A board that responds successfully but yields zero usable
    candidates (no exception raised) must still be logged as
    unavailable -- not silently absorbed with no operator-visible signal
    of which board contributed nothing."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            if "empty_board" in path:
                # Non-empty jobs list, but no job has a usable id -- a
                # well-formed, reachable response that still yields
                # nothing selectable, distinct from an outright failure.
                return httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json={"jobs": [{"title": "no id field"}]},
                )
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        with pytest.raises(EvaluationFetchError):
            await run_acquisition(
                [_spec("empty_board", "Empty"), _spec("board_a", "A")],
                client=client,
            )

    captured = capsys.readouterr()
    assert "empty_board" in captured.err


async def test_fetch_board_skips_unsanitizable_record_without_discarding_earlier_candidates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A sanitization failure on one job (e.g. an unclosed <script>/
    <style> tag, raised by `_sanitize_job_detail` as
    `EvaluationFetchError`) must not discard already-collected valid
    candidates from earlier job ids on the same board, and must not
    abort the board -- it is this one record's problem, never the whole
    board's, matching the same skip-not-abort contract as a missing
    title/content record."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response([1, 2])
        job_id = int(path.rsplit("/", 1)[-1])
        if job_id == 2:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"id": 2, "title": "Broken", "content": "<script>oops"},
            )
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        candidates = await fetcher._fetch_board(
            _spec("board_a", "A"),
            client=client,
            run_budget=fetcher._RunBudget(max_total_bytes=10**9),
        )

    assert [c.job_id for c in candidates] == ["1"]
    captured = capsys.readouterr()
    assert "sanitization failed" in captured.err


async def test_run_acquisition_does_not_count_missing_title_or_content_as_board_success(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A board whose every detail record is missing a usable title or
    content must not count toward `MIN_SUCCESSFUL_BOARDS`, even though
    the board itself was perfectly reachable."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        token = path.split("/")[3]
        if path.endswith("/jobs"):
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        if token == "board_no_title":
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"id": job_id, "content": "<p>Hi</p>"},  # no title
            )
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        with pytest.raises(EvaluationFetchError, match="only 1 board"):
            await run_acquisition(
                [_spec("board_no_title", "NoTitle"), _spec("board_good", "Good")], client=client
            )

    captured = capsys.readouterr()
    assert "skipped unusable detail record" in captured.err
    assert "board_no_title" in captured.err


async def test_run_acquisition_fatal_budget_exhaustion_prevents_later_board_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exhausting the total-run budget during board A's very first
    request must raise `FatalBudgetExhaustedError` -- not an ordinary
    per-board `EvaluationFetchError` -- and must prevent every later
    request to boards B and C, proven by asserting no board beyond the
    first was ever contacted."""
    monkeypatch.setattr(fetcher, "MAX_TOTAL_RUN_BYTES", 10)
    requested_tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.path.split("/")[3]
        requested_tokens.append(token)
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        with pytest.raises(FatalBudgetExhaustedError):
            await run_acquisition(
                [_spec("board_a", "A"), _spec("board_b", "B"), _spec("board_c", "C")],
                client=client,
            )

    assert requested_tokens == ["board_a"]


async def test_run_acquisition_skips_a_failing_board_without_retry() -> None:
    request_count_by_board: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        token = path.split("/")[3]  # /v1/boards/{token}/jobs...
        request_count_by_board[token] = request_count_by_board.get(token, 0) + 1
        if token == "broken_board":
            return httpx.Response(500, headers={"content-type": "application/json"}, json={})
        if path.endswith("/jobs"):
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        candidates = await run_acquisition(
            [
                _spec("broken_board", "Broken"),
                _spec("board_a", "A"),
                _spec("board_b", "B"),
            ],
            client=client,
        )

    assert request_count_by_board["broken_board"] == 1  # no retry
    assert len({c.board_token for c in candidates}) == 2
    assert "broken_board" not in {c.board_token for c in candidates}


async def test_run_acquisition_raises_and_stages_nothing_with_too_few_boards() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        with pytest.raises(EvaluationFetchError, match="only 1 board"):
            await run_acquisition([_spec("board_a", "A")], client=client)


async def test_run_acquisition_never_substitutes_an_unapproved_board() -> None:
    """Only the boards explicitly passed in are ever requested -- proven
    by asserting the mock handler is never invoked with a token outside
    the caller-supplied closed list."""
    requested_tokens: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.path.split("/")[3]
        requested_tokens.add(token)
        if token == "broken_board":
            return httpx.Response(500, headers={"content-type": "application/json"}, json={})
        path = request.url.path
        if path.endswith("/jobs"):
            return _list_response([1])
        job_id = int(path.rsplit("/", 1)[-1])
        return _detail_response(job_id)

    async with _mock_client(handler) as client:
        with pytest.raises(EvaluationFetchError):
            await run_acquisition([_spec("broken_board", "Broken")], client=client)

    assert requested_tokens == {"broken_board"}


# ---------------------------------------------------------------------------
# _write_json_atomic_create_only
# ---------------------------------------------------------------------------
def test_write_json_atomic_create_only_writes_the_file(tmp_path: Path) -> None:
    destination = tmp_path / "staged.json"
    _write_json_atomic_create_only(destination, [{"a": 1}])
    assert destination.exists()
    import json as _json

    assert _json.loads(destination.read_text(encoding="utf-8")) == [{"a": 1}]


def test_write_json_atomic_create_only_refuses_to_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "staged.json"
    _write_json_atomic_create_only(destination, [{"a": 1}])
    with pytest.raises(EvaluationFetchError, match="create-only"):
        _write_json_atomic_create_only(destination, [{"a": 2}])
    import json as _json

    assert _json.loads(destination.read_text(encoding="utf-8")) == [{"a": 1}]


def test_staging_path_is_fixed_not_caller_suppliable() -> None:
    assert fetcher.STAGING_PATH == fetcher.BACKEND_DIR / ".evaluation-staging" / (
        "greenhouse_candidates_staging.json"
    )


def test_sanitized_candidate_compensation_text_is_never_populated_by_this_module() -> None:
    candidate = SanitizedCandidate(
        board_token="acme",
        employer="Acme",
        job_id="1",
        title="Engineer",
        description="Some description",
        location_raw="Remote",
        accessed_at="t",
        content_mode="standard",
        mode_basis_ref=None,
    )
    staged = fetcher._candidate_to_staged_dict(candidate)
    assert staged["fields"]["compensation_text"] is None


def test_candidate_to_staged_dict_records_content_mode_and_basis_ref_in_lineage() -> None:
    candidate = SanitizedCandidate(
        board_token="acme",
        employer="Acme",
        job_id="1",
        title="Engineer",
        description="Some description",
        location_raw="Remote",
        accessed_at="t",
        content_mode="declared-double-escaped",
        mode_basis_ref="prior-capture:abc123",
    )
    staged = fetcher._candidate_to_staged_dict(candidate)
    lineage = staged["provenance"]["sanitization_lineage"]
    assert "content_mode=declared-double-escaped" in lineage
    assert "mode_basis_ref=prior-capture:abc123" in lineage


def test_candidate_to_staged_dict_omits_basis_ref_text_for_standard_mode() -> None:
    candidate = SanitizedCandidate(
        board_token="acme",
        employer="Acme",
        job_id="1",
        title="Engineer",
        description="Some description",
        location_raw="Remote",
        accessed_at="t",
        content_mode="standard",
        mode_basis_ref=None,
    )
    staged = fetcher._candidate_to_staged_dict(candidate)
    lineage = staged["provenance"]["sanitization_lineage"]
    assert "content_mode=standard" in lineage
    assert "mode_basis_ref" not in lineage


# ---------------------------------------------------------------------------
# BoardAcquisitionSpec -- the mode/basis invariant is enforced by the type
# itself, at construction, never solely by the CLI parser.
# ---------------------------------------------------------------------------
def test_board_acquisition_spec_accepts_standard_with_no_basis_ref() -> None:
    BoardAcquisitionSpec(
        board_token="acme", employer="Acme", content_mode="standard", mode_basis_ref=None
    )


def test_board_acquisition_spec_accepts_declared_mode_with_valid_basis_ref() -> None:
    BoardAcquisitionSpec(
        board_token="acme",
        employer="Acme",
        content_mode="declared-double-escaped",
        mode_basis_ref="prior-capture:abc123",
    )


def test_board_acquisition_spec_rejects_declared_mode_with_no_basis_ref() -> None:
    with pytest.raises(ValueError, match="mode_basis_ref is required"):
        BoardAcquisitionSpec(
            board_token="acme",
            employer="Acme",
            content_mode="declared-double-escaped",
            mode_basis_ref=None,
        )


def test_board_acquisition_spec_rejects_declared_mode_with_malformed_basis_ref() -> None:
    with pytest.raises(ValueError, match="mode_basis_ref is required"):
        BoardAcquisitionSpec(
            board_token="acme",
            employer="Acme",
            content_mode="declared-double-escaped",
            mode_basis_ref="not-a-valid-ref",
        )


def test_board_acquisition_spec_rejects_standard_mode_with_a_basis_ref() -> None:
    with pytest.raises(ValueError, match="mode_basis_ref must be None"):
        BoardAcquisitionSpec(
            board_token="acme",
            employer="Acme",
            content_mode="standard",
            mode_basis_ref="prior-capture:abc123",
        )


# ---------------------------------------------------------------------------
# _parse_board_arg -- CLI grammar; every malformed input must fail during
# argument parsing, before any network request is possible.
# ---------------------------------------------------------------------------
def test_parse_board_arg_accepts_standard_three_part_form() -> None:
    spec = _parse_board_arg("gitlab:GitLab:standard")
    assert spec == BoardAcquisitionSpec(
        board_token="gitlab", employer="GitLab", content_mode="standard", mode_basis_ref=None
    )


def test_parse_board_arg_accepts_declared_five_part_form_with_prior_capture() -> None:
    spec = _parse_board_arg("gitlab:GitLab:declared-double-escaped:prior-capture:abc123")
    assert spec == BoardAcquisitionSpec(
        board_token="gitlab",
        employer="GitLab",
        content_mode="declared-double-escaped",
        mode_basis_ref="prior-capture:abc123",
    )


def test_parse_board_arg_accepts_declared_five_part_form_with_probe() -> None:
    spec = _parse_board_arg("gitlab:GitLab:declared-double-escaped:probe:run-42")
    assert spec.mode_basis_ref == "probe:run-42"


def test_parse_board_arg_rejects_wrong_part_count() -> None:
    for value in ["gitlab:GitLab", "gitlab:GitLab:standard:extra", "gitlab"]:
        with pytest.raises(argparse.ArgumentTypeError):
            _parse_board_arg(value)


def test_parse_board_arg_rejects_empty_employer() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="employer name must be non-empty"):
        _parse_board_arg("gitlab::standard")


def test_parse_board_arg_rejects_unsafe_board_token() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="conservative ASCII slug"):
        _parse_board_arg("../../etc:Employer:standard")


def test_parse_board_arg_rejects_unknown_content_mode() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="content mode must be one of"):
        _parse_board_arg("gitlab:GitLab:not-a-real-mode")


def test_parse_board_arg_rejects_standard_mode_with_extra_parts() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="'standard' mode takes exactly 3 parts"):
        _parse_board_arg("gitlab:GitLab:standard:prior-capture:abc123")


def test_parse_board_arg_rejects_declared_mode_with_too_few_parts() -> None:
    with pytest.raises(
        argparse.ArgumentTypeError, match="'declared-double-escaped' mode requires exactly 5"
    ):
        _parse_board_arg("gitlab:GitLab:declared-double-escaped")


def test_parse_board_arg_rejects_declared_mode_with_missing_basis_id() -> None:
    """4 parts is rejected by the generic part-count check before the
    mode-specific 5-part check is ever reached."""
    with pytest.raises(argparse.ArgumentTypeError, match=r"\(3 parts\) or"):
        _parse_board_arg("gitlab:GitLab:declared-double-escaped:prior-capture")


def test_parse_board_arg_rejects_unknown_basis_kind() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="basis-kind must be one of"):
        _parse_board_arg("gitlab:GitLab:declared-double-escaped:not-a-real-kind:abc123")


def test_parse_board_arg_rejects_malformed_basis_id() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="basis-id must match"):
        _parse_board_arg("gitlab:GitLab:declared-double-escaped:prior-capture:has a space")
