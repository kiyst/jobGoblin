"""Offline unit tests for `scripts/canary_greenhouse.py`'s pure logic —
response validation, deterministic job selection, and Greenhouse-job-dict
to `DiscoveredJob` mapping.

**No test in this file ever calls `fetch_greenhouse_jobs_raw` or performs
any network I/O.** Every test exercises `validate_and_parse_response`,
`select_representative_job`, `map_job_to_discovered_job`, or
`build_sanitized_fixture` directly, against either synthetic dicts or the
committed sanitized fixture (`tests/fixtures/discovery/
greenhouse_live_canary.json`) — never a real Greenhouse request. This
mirrors `test_verify.py`'s own pattern for keeping default test runs
network-free (`docs/PHASE_RISK_CHECKLIST.md`'s cross-cutting non-negotiable
"default tests never contact public job sources"); `scripts/verify.py
--level routine` never imports this module's network-touching function
either.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.schemas.discovered_job import DiscoveredJob
from scripts import canary_greenhouse as canary

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "discovery" / "greenhouse_live_canary.json"
)


def _load_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data


def _fixture_job() -> dict[str, Any]:
    return dict(_load_fixture()["job"])


# --------------------------------------------------------------------------
# validate_board_token / _build_url
# --------------------------------------------------------------------------


@pytest.mark.parametrize("token", ["gitlab", "acme-corp", "acme_corp", "A1", "a" * 100])
def test_validate_board_token_accepts_conservative_ascii_slugs(token: str) -> None:
    assert canary.validate_board_token(token) == token


@pytest.mark.parametrize(
    "token",
    [
        "../etc/passwd",
        "acme/corp",
        "acme corp",
        "acme.corp",
        "acmé",
        "",
        "a" * 101,
    ],
)
def test_validate_board_token_rejects_anything_else(token: str) -> None:
    with pytest.raises(ValueError, match="conservative ASCII slug"):
        canary.validate_board_token(token)


def test_build_url_uses_the_fixed_origin_and_validated_token() -> None:
    url = canary._build_url("gitlab")
    assert url == "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs"


def test_build_url_rejects_an_unsafe_token_before_constructing_anything() -> None:
    with pytest.raises(ValueError, match="conservative ASCII slug"):
        canary._build_url("../../evil")


# --------------------------------------------------------------------------
# validate_and_parse_response — offline, synthetic RawResponse only
# --------------------------------------------------------------------------


def _raw(
    status_code: int = 200,
    content_type: str | None = "application/json",
    body: bytes = b'{"jobs": [{"id": 1, "absolute_url": "https://x/1"}]}',
) -> canary.RawResponse:
    return canary.RawResponse(status_code=status_code, content_type=content_type, body=body)


def test_validate_and_parse_response_accepts_a_well_formed_payload() -> None:
    payload, metadata = canary.validate_and_parse_response(
        _raw(), board_token="acme", elapsed_seconds=0.1
    )
    assert payload["jobs"] == [{"id": 1, "absolute_url": "https://x/1"}]
    assert metadata.board_token == "acme"
    assert metadata.status_code == 200


def test_validate_and_parse_response_rejects_non_2xx_status() -> None:
    with pytest.raises(canary.CanaryFetchError, match="non-2xx status"):
        canary.validate_and_parse_response(
            _raw(status_code=404), board_token="acme", elapsed_seconds=0.1
        )


def test_validate_and_parse_response_rejects_an_oversized_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(canary, "MAX_RESPONSE_BYTES", 10)
    with pytest.raises(canary.CanaryFetchError, match="response too large"):
        canary.validate_and_parse_response(_raw(), board_token="acme", elapsed_seconds=0.1)


def test_validate_and_parse_response_rejects_unexpected_content_type() -> None:
    with pytest.raises(canary.CanaryFetchError, match="unexpected content-type"):
        canary.validate_and_parse_response(
            _raw(content_type="text/html"), board_token="acme", elapsed_seconds=0.1
        )


def test_validate_and_parse_response_rejects_a_missing_content_type() -> None:
    with pytest.raises(canary.CanaryFetchError, match="unexpected content-type"):
        canary.validate_and_parse_response(
            _raw(content_type=None), board_token="acme", elapsed_seconds=0.1
        )


def test_validate_and_parse_response_rejects_invalid_json() -> None:
    with pytest.raises(canary.CanaryFetchError, match="invalid JSON"):
        canary.validate_and_parse_response(
            _raw(body=b"not json at all"), board_token="acme", elapsed_seconds=0.1
        )


@pytest.mark.parametrize(
    "body",
    [
        b"[]",  # top level is a list, not a dict
        b"{}",  # missing 'jobs' entirely
        b'{"jobs": "not-a-list"}',
        b'{"jobs": null}',
    ],
)
def test_validate_and_parse_response_rejects_malformed_schema(body: bytes) -> None:
    with pytest.raises(canary.CanaryFetchError, match="malformed schema"):
        canary.validate_and_parse_response(_raw(body=body), board_token="acme", elapsed_seconds=0.1)


def test_validate_and_parse_response_rejects_an_empty_job_list() -> None:
    with pytest.raises(canary.CanaryFetchError, match="empty job list"):
        canary.validate_and_parse_response(
            _raw(body=b'{"jobs": []}'), board_token="acme", elapsed_seconds=0.1
        )


def test_validate_and_parse_response_error_never_contains_the_response_body() -> None:
    secret_shaped_body = b'{"jobs": "TOTALLY_NOT_A_LIST_BUT_LOOKS_SECRETY_abc123"}'
    with pytest.raises(canary.CanaryFetchError) as exc_info:
        canary.validate_and_parse_response(
            _raw(body=secret_shaped_body), board_token="acme", elapsed_seconds=0.1
        )
    assert "TOTALLY_NOT_A_LIST_BUT_LOOKS_SECRETY_abc123" not in str(exc_info.value)


# --------------------------------------------------------------------------
# select_representative_job — deterministic, order-independent
# --------------------------------------------------------------------------


def test_select_representative_job_is_independent_of_input_order() -> None:
    jobs = [{"id": 300}, {"id": 100}, {"id": 200}]
    forward = canary.select_representative_job(jobs)
    backward = canary.select_representative_job(list(reversed(jobs)))
    shuffled = canary.select_representative_job([jobs[1], jobs[2], jobs[0]])
    assert forward == backward == shuffled
    assert forward["id"] == 100


def test_select_representative_job_ignores_jobs_missing_an_id() -> None:
    jobs: list[dict[str, Any]] = [{"title": "no id here"}, {"id": 42, "title": "has an id"}]
    selected = canary.select_representative_job(jobs)
    assert selected["id"] == 42


def test_select_representative_job_raises_when_no_job_has_a_usable_id() -> None:
    with pytest.raises(canary.CanaryFetchError, match="no job.*usable 'id'"):
        canary.select_representative_job([{"title": "no id"}, {"id": None}])


def test_select_representative_job_raises_on_an_empty_list() -> None:
    with pytest.raises(canary.CanaryFetchError):
        canary.select_representative_job([])


# --------------------------------------------------------------------------
# map_job_to_discovered_job — the mapping contract, against the real fixture
# --------------------------------------------------------------------------

_DISCOVERED_AT = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


def test_mapping_succeeds_against_the_real_sanitized_fixture() -> None:
    job = _fixture_job()
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert isinstance(discovered, DiscoveredJob)
    assert discovered.provider == "ats_scrapers"
    assert discovered.source == "greenhouse"
    assert discovered.source_tenant_id == "gitlab"
    assert discovered.source_job_id == str(job["id"])
    assert discovered.requisition_id_raw == str(job["requisition_id"])


def test_mapping_uses_established_identity_labels_even_though_greenhouse_is_called_directly() -> (
    None
):
    """Binding requirement: provider/source stay `ats_scrapers`/`greenhouse`
    — the project's established identity domain — even though this canary
    never imports or calls the `ats-scrapers` library."""
    job = _fixture_job()
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.provider == canary.DISCOVERED_JOB_PROVIDER == "ats_scrapers"
    assert discovered.source == canary.DISCOVERED_JOB_SOURCE == "greenhouse"


def test_mapping_url_fields_come_from_absolute_url_and_apply_url_is_never_invented() -> None:
    job = _fixture_job()
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.source_url == job["absolute_url"]
    assert discovered.canonical_url == job["absolute_url"]
    assert discovered.apply_url is None


def test_mapping_company_is_the_externally_supplied_value_never_the_payloads_own_company_name() -> (
    None
):
    """The real fixture's own job dict *does* contain `company_name`
    ("GitLab") — proves it is genuinely ignored, not merely absent."""
    job = _fixture_job()
    assert job.get("company_name") == "GitLab"  # sanity: the field really is present

    discovered = canary.map_job_to_discovered_job(
        job,
        board_token="gitlab",
        company="A Totally Different Caller-Supplied Name",
        discovered_at=_DISCOVERED_AT,
    )
    assert discovered.company == "A Totally Different Caller-Supplied Name"


def test_mapping_posted_at_comes_from_first_published_never_updated_at() -> None:
    job = _fixture_job()
    assert "updated_at" in job  # sanity: both fields are present in the real fixture
    assert "first_published" in job
    assert job["updated_at"] != job["first_published"]

    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.posted_at is not None
    assert (
        discovered.posted_at.isoformat()
        == datetime.fromisoformat(job["first_published"]).isoformat()
    )


def test_mapping_posted_at_is_none_when_first_published_is_absent() -> None:
    job = _fixture_job()
    del job["first_published"]
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.posted_at is None


def test_mapping_never_infers_posted_at_from_updated_at_even_when_first_published_is_absent() -> (
    None
):
    job = _fixture_job()
    del job["first_published"]
    assert "updated_at" in job
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.posted_at is None  # never falls back to updated_at


def test_mapping_description_and_compensation_stay_none_content_was_never_fetched() -> None:
    """Confirms omitted content does not prevent construction — this
    canary never requests `content=true`, so there is nothing to map."""
    job = _fixture_job()
    assert "content" not in job
    assert "description" not in job
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.description is None
    assert discovered.compensation_text is None


def test_mapping_raises_on_missing_id() -> None:
    job = _fixture_job()
    del job["id"]
    with pytest.raises(ValueError, match="'id'"):
        canary.map_job_to_discovered_job(
            job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
        )


def test_mapping_raises_on_missing_absolute_url() -> None:
    job = _fixture_job()
    del job["absolute_url"]
    with pytest.raises(ValueError, match="'absolute_url'"):
        canary.map_job_to_discovered_job(
            job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
        )


def test_mapping_tolerates_a_missing_requisition_id() -> None:
    job = _fixture_job()
    del job["requisition_id"]
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.requisition_id_raw is None


def test_mapping_tolerates_a_missing_location() -> None:
    job = _fixture_job()
    del job["location"]
    discovered = canary.map_job_to_discovered_job(
        job, board_token="gitlab", company="GitLab", discovered_at=_DISCOVERED_AT
    )
    assert discovered.location is None


# --------------------------------------------------------------------------
# build_sanitized_fixture — the allowlist is real, not decorative
# --------------------------------------------------------------------------


def test_build_sanitized_fixture_only_ever_includes_allowlisted_fields() -> None:
    job = {
        "id": 1,
        "absolute_url": "https://x/1",
        "content": "<p>SENSITIVE HTML SHOULD NEVER APPEAR</p>",
        "metadata": [{"name": "internal-tag", "value": "SHOULD NOT APPEAR EITHER"}],
        "internal_job_id": 999,
    }
    fixture = canary.build_sanitized_fixture(
        job, board_token="acme", company="Acme", accessed_at="2026-01-01T00:00:00+00:00"
    )
    assert set(fixture["job"].keys()) <= set(canary.FIXTURE_ALLOWED_JOB_FIELDS)
    assert "content" not in fixture["job"]
    assert "metadata" not in fixture["job"]
    assert "internal_job_id" not in fixture["job"]
    dumped = json.dumps(fixture)
    assert "SENSITIVE HTML" not in dumped
    assert "SHOULD NOT APPEAR" not in dumped


def test_build_sanitized_fixture_is_labeled_as_a_derived_sample() -> None:
    fixture = canary.build_sanitized_fixture(
        {"id": 1, "absolute_url": "https://x/1"},
        board_token="acme",
        company="Acme",
        accessed_at="2026-01-01T00:00:00+00:00",
    )
    assert fixture["_fixture_kind"] == "sanitized_derived_sample"
    assert "NOT a byte- or structure-preserved raw payload" in fixture["_note"]


def test_committed_fixture_file_itself_is_labeled_and_allowlisted() -> None:
    """The actual committed fixture (not a synthetic one) must satisfy the
    same allowlist/labeling guarantees the builder enforces."""
    fixture = _load_fixture()
    assert fixture["_fixture_kind"] == "sanitized_derived_sample"
    assert set(fixture["job"].keys()) <= set(canary.FIXTURE_ALLOWED_JOB_FIELDS)
    assert "content" not in fixture["job"]
    assert "description" not in fixture["job"]
