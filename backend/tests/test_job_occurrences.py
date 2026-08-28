import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Job, JobOccurrence
from app.normalization.url import normalize_url
from tests.conftest import real_committed_job, real_committed_job_occurrence

_SEEN_AT = datetime(2026, 1, 1, tzinfo=UTC)
_LATER_SEEN_AT = datetime(2026, 1, 2, tzinfo=UTC)


async def _insert_job(db_session: AsyncSession, make_job: Callable[..., Job]) -> uuid.UUID:
    """Returns the new job's id, captured immediately after its own
    commit — `session.commit()` expires every attribute of every object in
    the session, so a later commit (e.g. adding an occurrence) would
    otherwise expire this id before it's read."""
    job = make_job(first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job.id


_DIRECT_SQL_BASE_COLUMNS = {
    "provider": "'ats_scrapers'",
    "source": "'greenhouse'",
    "source_url": "'https://boards.greenhouse.io/acme/jobs/1'",
}


async def _assert_direct_sql_insert_rejected(
    db_session: AsyncSession, job_id: uuid.UUID, overrides: dict[str, str]
) -> None:
    """Shared helper: attempt a raw SQL insert bypassing the ORM entirely.
    `id`/`job_id`/`first_seen_at`/`last_seen_at` are always supplied;
    `provider`/`source`/`source_url` default to a valid row and are
    replaced (not duplicated) by any of the same keys in `overrides`;
    anything else in `overrides` is an additional column. Asserts
    PostgreSQL itself rejects the insert, and that the session recovers."""
    columns = dict(_DIRECT_SQL_BASE_COLUMNS)
    columns.update(overrides)
    column_names = ["id", "job_id", "first_seen_at", "last_seen_at", *columns.keys()]
    column_values = ["gen_random_uuid()", ":job_id", "now()", "now()", *columns.values()]
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO job_occurrences ({', '.join(column_names)}) "
                f"VALUES ({', '.join(column_values)})"
            ).bindparams(job_id=job_id)
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# normalize_url() — pure function, no database involved
# --------------------------------------------------------------------------


def test_normalize_url_lowercases_scheme_and_host() -> None:
    assert normalize_url("HTTP://Acme.COM/x") == "http://acme.com/x"


def test_normalize_url_retains_www() -> None:
    """Unlike `normalize_domain()`, a URL host must keep `www.` — it's a
    click-through target, not a company-identity signal."""
    assert normalize_url("http://www.acme.com/x") == "http://www.acme.com/x"


def test_normalize_url_unicode_punycode_host_equivalence() -> None:
    assert normalize_url("http://café.com/x") == normalize_url("http://xn--caf-dma.com/x")
    assert normalize_url("http://café.com/x") == "http://xn--caf-dma.com/x"


def test_normalize_url_unicode_separator_variant_host_equivalence() -> None:
    """U+3002/U+FF0E map to ASCII "." under UTS #46, same rationale as
    `normalize_domain()`'s equivalent regression coverage."""
    assert normalize_url("http://www。acme.com/x") == normalize_url("http://www.acme.com/x")
    assert normalize_url("http://acme．com/x") == normalize_url("http://acme.com/x")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://acme.com:80/x", "http://acme.com/x"),
        ("https://acme.com:443/x", "https://acme.com/x"),
        ("http://acme.com:8080/x", "http://acme.com:8080/x"),
        ("https://acme.com:8443/x", "https://acme.com:8443/x"),
    ],
    ids=["http-default", "https-default", "http-nondefault", "https-nondefault"],
)
def test_normalize_url_port_handling(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_normalize_url_preserves_ipv4_host() -> None:
    assert normalize_url("https://192.168.1.1/x") == "https://192.168.1.1/x"


def test_normalize_url_reconstructs_bracketed_ipv6_host() -> None:
    assert normalize_url("http://[::1]:8080/x") == "http://[::1]:8080/x"
    assert normalize_url("http://[::1]/x") == "http://[::1]/x"


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@acme.com/",
        "http://user@acme.com/",
        "//acme.com/x",
        "/careers",
        "ftp://acme.com/x",
        "http://acme.com:99999/",
        "http://acme.com:abc/",
        "http://",
        "http:///x",
        "not a url at all",
        "",
    ],
    ids=[
        "userinfo",
        "username-only",
        "protocol-relative",
        "relative",
        "non-http-scheme",
        "port-out-of-range",
        "port-non-numeric",
        "empty-authority",
        "empty-host-with-path",
        "garbage",
        "empty-string",
    ],
)
def test_normalize_url_rejects_invalid_input_returns_none(url: str) -> None:
    assert normalize_url(url) is None


def test_normalize_url_none_input_returns_none() -> None:
    assert normalize_url(None) is None


def test_normalize_url_removes_fragment() -> None:
    assert normalize_url("http://acme.com/x#section") == "http://acme.com/x"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://acme.com", "http://acme.com/"),
        ("http://acme.com/", "http://acme.com/"),
        ("http://acme.com//", "http://acme.com/"),
    ],
)
def test_normalize_url_root_path_equivalence(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://acme.com/careers/", "http://acme.com/careers"),
        ("http://acme.com/careers//", "http://acme.com/careers"),
        ("http://acme.com/careers", "http://acme.com/careers"),
    ],
)
def test_normalize_url_trailing_slash_removed_from_non_root_path(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_normalize_url_preserves_path_casing() -> None:
    assert normalize_url("http://acme.com/CaReErS") == "http://acme.com/CaReErS"


def test_normalize_url_repeated_and_blank_query_values_retained() -> None:
    assert normalize_url("http://acme.com/?a=1&a=2&b=") == "http://acme.com/?a=1&a=2&b="


def test_normalize_url_retained_params_sorted_deterministically() -> None:
    assert normalize_url("http://acme.com/?b=2&a=1") == normalize_url("http://acme.com/?a=1&b=2")
    assert normalize_url("http://acme.com/?b=2&a=1") == "http://acme.com/?a=1&b=2"


@pytest.mark.parametrize(
    "name",
    ["utm_source", "utm_medium", "UTM_CAMPAIGN", "utm_anything_arbitrary", "Utm_Custom"],
)
def test_normalize_url_strips_arbitrary_utm_prefixed_params_case_insensitively(name: str) -> None:
    assert normalize_url(f"http://acme.com/?{name}=1&keep=2") == "http://acme.com/?keep=2"


@pytest.mark.parametrize(
    "name",
    ["gh_src", "lever-source", "trk", "li_fat_id", "ref", "fbclid", "gclid", "mc_cid", "mc_eid"],
)
def test_normalize_url_strips_exact_tracking_names_case_insensitively(name: str) -> None:
    assert normalize_url(f"http://acme.com/?{name.upper()}=1&keep=2") == "http://acme.com/?keep=2"


def test_normalize_url_empty_query_after_filtering_omits_delimiter() -> None:
    assert normalize_url("http://acme.com/?utm_source=x&gclid=y") == "http://acme.com/"


def test_normalize_url_unlisted_params_retained() -> None:
    assert normalize_url("http://acme.com/?custom=1") == "http://acme.com/?custom=1"


def test_normalize_url_single_label_host_accepted() -> None:
    """A URL host is not asked to prove company identity — unlike
    `normalize_domain()`, a single-label host is a perfectly valid URL
    target (e.g. an internal tool)."""
    assert normalize_url("http://localhost/x") == "http://localhost/x"


# --------------------------------------------------------------------------
# JobOccurrence model — baseline
# --------------------------------------------------------------------------


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_minimal_valid_occurrence(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert isinstance(occurrence.id, uuid.UUID)

    fetched = await db_session.get(JobOccurrence, occurrence.id)
    assert fetched is not None
    assert fetched.job_id == job_id
    assert fetched.provider == "ats_scrapers"
    assert fetched.source == "greenhouse"
    assert fetched.source_tenant_id is None
    assert fetched.source_job_id is None
    assert fetched.requisition_id_raw is None
    assert fetched.source_url == "https://boards.greenhouse.io/acme/jobs/12345"
    assert fetched.source_url_normalized is None
    assert fetched.apply_url is None
    assert fetched.canonical_url is None
    assert fetched.canonical_url_normalized is None
    assert fetched.posted_at is None
    assert fetched.applicant_count is None
    assert fetched.applicant_count_text is None
    assert fetched.is_active is True
    assert fetched.first_seen_at == _SEEN_AT
    assert fetched.last_seen_at == _SEEN_AT
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


# --------------------------------------------------------------------------
# provider / source — required canonical identifiers
# --------------------------------------------------------------------------


async def test_provider_and_source_are_lowercased_and_trimmed_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(
        job_id=job_id,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        provider="\t ATS_Scrapers \n",
        source="\t GreenHouse \n",
    )
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert occurrence.provider == "ats_scrapers"
    assert occurrence.source == "greenhouse"


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_non_lowercase_provider_or_source_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: "'Greenhouse'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_whitespace_wrapped_provider_or_source_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: r"E'\tgreenhouse\n'"})


@pytest.mark.parametrize("column", ["provider", "source"])
async def test_direct_sql_empty_provider_or_source_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: "''"})


# --------------------------------------------------------------------------
# Externally assigned identifiers — case-preserving, nullable
# --------------------------------------------------------------------------

_CASE_PRESERVING_NULLABLE_COLUMNS = (
    "source_tenant_id",
    "source_job_id",
    "requisition_id_raw",
    "apply_url",
    "canonical_url",
    "applicant_count_text",
)


@pytest.mark.parametrize("column", _CASE_PRESERVING_NULLABLE_COLUMNS)
async def test_nullable_text_defaults_to_none(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    column: str,
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert getattr(occurrence, column) is None


@pytest.mark.parametrize("column", _CASE_PRESERVING_NULLABLE_COLUMNS)
async def test_nullable_text_whitespace_only_becomes_none_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    column: str,
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(occurrence, column, "\t \n")
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert getattr(occurrence, column) is None


@pytest.mark.parametrize("column", _CASE_PRESERVING_NULLABLE_COLUMNS)
async def test_nullable_text_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    column: str,
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    setattr(occurrence, column, "\t Some-Value_MixedCase \n")
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert getattr(occurrence, column) == "Some-Value_MixedCase"


@pytest.mark.parametrize("column", _CASE_PRESERVING_NULLABLE_COLUMNS)
async def test_direct_sql_empty_nullable_text_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: "''"})


@pytest.mark.parametrize("column", _CASE_PRESERVING_NULLABLE_COLUMNS)
async def test_direct_sql_whitespace_wrapped_nullable_text_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: r"E'\tvalue\n'"})


# --------------------------------------------------------------------------
# source_url — required, trim-only, case-preserving
# --------------------------------------------------------------------------


async def test_source_url_is_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(
        job_id=job_id,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        source_url="\t https://Boards.Greenhouse.io/Acme/Jobs/1 \n",
    )
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert occurrence.source_url == "https://Boards.Greenhouse.io/Acme/Jobs/1"


async def test_direct_sql_empty_source_url_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {"source_url": "''"})


async def test_direct_sql_whitespace_wrapped_source_url_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(
        db_session, job_id, {"source_url": r"E'\thttps://acme.com/1\n'"}
    )


# --------------------------------------------------------------------------
# Normalized URL columns — application-owned, not auto-derived
# --------------------------------------------------------------------------


async def test_normalized_url_columns_are_not_auto_derived_from_raw_urls(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    """The model never calls `normalize_url()` itself — setting the raw URL
    columns must not silently populate the normalized ones."""
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(
        job_id=job_id,
        first_seen_at=_SEEN_AT,
        last_seen_at=_SEEN_AT,
        source_url="https://Boards.Greenhouse.io/Acme/Jobs/1",
    )
    occurrence.canonical_url = "https://acme.com/careers/1"
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert occurrence.source_url_normalized is None
    assert occurrence.canonical_url_normalized is None


async def test_source_url_normalized_stores_explicit_pure_function_result(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    raw = "https://Boards.Greenhouse.io/Acme/Jobs/1?utm_source=x"
    occurrence = make_job_occurrence(
        job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, source_url=raw
    )
    occurrence.source_url_normalized = normalize_url(raw)
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert occurrence.source_url_normalized == "https://boards.greenhouse.io/Acme/Jobs/1"


@pytest.mark.parametrize("column", ["source_url_normalized", "canonical_url_normalized"])
async def test_direct_sql_empty_normalized_url_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: "''"})


@pytest.mark.parametrize("column", ["source_url_normalized", "canonical_url_normalized"])
async def test_direct_sql_whitespace_wrapped_normalized_url_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job], column: str
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(db_session, job_id, {column: r"E'\thttp://x\n'"})


async def test_canonical_url_null_with_normalized_set_rejected_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    """`canonical_url IS NULL` must imply `canonical_url_normalized IS
    NULL` — a normalized value with no raw value behind it is a
    self-contradictory state, not something a bug in `normalize_url()`
    output could legitimately produce."""
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    occurrence.canonical_url_normalized = "http://acme.com/"
    db_session.add(occurrence)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_canonical_url_null_with_normalized_set_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job_id = await _insert_job(db_session, make_job)
    await _assert_direct_sql_insert_rejected(
        db_session, job_id, {"canonical_url_normalized": "'http://acme.com/'"}
    )


async def test_non_null_malformed_canonical_url_may_have_null_normalized_value(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    """A non-null but malformed `canonical_url` legitimately normalizes to
    `None` via `normalize_url()` — this must NOT be rejected by the
    implication CHECK, which only forbids the reverse (normalized set
    while the raw column is NULL)."""
    job_id = await _insert_job(db_session, make_job)
    malformed = "not a url at all"
    assert normalize_url(malformed) is None
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    occurrence.canonical_url = malformed
    occurrence.canonical_url_normalized = normalize_url(malformed)
    db_session.add(occurrence)
    await db_session.commit()  # must not raise
    await db_session.refresh(occurrence)

    assert occurrence.canonical_url == malformed
    assert occurrence.canonical_url_normalized is None


# --------------------------------------------------------------------------
# applicant_count / applicant_count_text / is_active
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", [0, 5])
async def test_applicant_count_non_negative_accepts_zero_and_positive(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
    value: int,
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    occurrence.applicant_count = value
    db_session.add(occurrence)
    await db_session.commit()  # must not raise


async def test_applicant_count_rejects_negative(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    occurrence.applicant_count = -1
    db_session.add(occurrence)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_is_active_defaults_to_true_on_orm_path(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert occurrence.is_active is True


async def test_is_active_explicit_false_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    occurrence.is_active = False
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    assert occurrence.is_active is False


async def test_direct_sql_omitting_is_active_defaults_to_true(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    """Proves the `true` default is enforced by PostgreSQL itself, not
    merely by the ORM — a raw INSERT that never mentions `is_active` at all
    still gets `true`."""
    job_id = await _insert_job(db_session, make_job)
    result = await db_session.execute(
        text(
            "INSERT INTO job_occurrences "
            "(id, job_id, provider, source, source_url, first_seen_at, last_seen_at) "
            "VALUES (gen_random_uuid(), :job_id, 'ats_scrapers', 'greenhouse', "
            "'https://boards.greenhouse.io/acme/jobs/1', now(), now()) "
            "RETURNING is_active"
        ).bindparams(job_id=job_id)
    )
    await db_session.commit()

    assert result.scalar_one() is True


# --------------------------------------------------------------------------
# first_seen_at <= last_seen_at
# --------------------------------------------------------------------------


async def test_first_seen_at_equal_last_seen_at_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(occurrence)
    await db_session.commit()  # must not raise


async def test_first_seen_at_before_last_seen_at_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(
        job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_LATER_SEEN_AT
    )
    db_session.add(occurrence)
    await db_session.commit()  # must not raise


async def test_first_seen_at_after_last_seen_at_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(
        job_id=job_id, first_seen_at=_LATER_SEEN_AT, last_seen_at=_SEEN_AT
    )
    db_session.add(occurrence)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_first_seen_at_after_last_seen_at_rejected(
    db_session: AsyncSession, make_job: Callable[..., Job]
) -> None:
    job_id = await _insert_job(db_session, make_job)
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO job_occurrences "
                "(id, job_id, provider, source, source_url, first_seen_at, last_seen_at) "
                "VALUES (gen_random_uuid(), :job_id, 'ats_scrapers', 'greenhouse', "
                "'https://boards.greenhouse.io/acme/jobs/1', "
                "'2026-01-02T00:00:00+00', '2026-01-01T00:00:00+00')"
            ).bindparams(job_id=job_id)
        )
        await db_session.commit()
    await db_session.rollback()


# --------------------------------------------------------------------------
# job_id FK — required, ON DELETE CASCADE
# --------------------------------------------------------------------------


async def test_job_id_nonexistent_reference_rejected(
    db_session: AsyncSession, make_job_occurrence: Callable[..., JobOccurrence]
) -> None:
    occurrence = make_job_occurrence(
        job_id=uuid.uuid4(), first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT
    )
    db_session.add(occurrence)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_deleting_a_job_cascades_only_to_its_own_occurrences(
    db_engine: AsyncEngine,
) -> None:
    """Deleting one job must remove only its own occurrences, leaving a
    second, unrelated job and its occurrence completely untouched."""
    async with (
        real_committed_job_occurrence(db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT) as (
            session,
            job_id_1,
            occurrence_id_1,
        ),
        real_committed_job_occurrence(
            db_engine,
            first_seen_at=_SEEN_AT,
            last_seen_at=_SEEN_AT,
            source_url="https://boards.greenhouse.io/other/jobs/2",
        ) as (_session_2, job_id_2, occurrence_id_2),
    ):
        job_1 = await session.get(Job, job_id_1)
        assert job_1 is not None
        await session.delete(job_1)
        await session.commit()

        assert await session.get(JobOccurrence, occurrence_id_1) is None

        async with AsyncSession(bind=db_engine) as verify_session:
            remaining_job = await verify_session.get(Job, job_id_2)
            remaining_occurrence = await verify_session.get(JobOccurrence, occurrence_id_2)
            assert remaining_job is not None
            assert remaining_occurrence is not None
            assert remaining_occurrence.job_id == job_id_2


# --------------------------------------------------------------------------
# Unique-index partition matrix (ADR 0004's three scoped natural-key
# indexes) — the core Class H verification for this table.
# --------------------------------------------------------------------------


async def test_same_tenant_scoped_natural_key_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    first.source_tenant_id = "tenant-1"
    first.source_job_id = "job-1"
    db_session.add(first)
    await db_session.commit()

    second = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    second.source_tenant_id = "tenant-1"
    second.source_job_id = "job-1"
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_same_source_job_id_on_different_tenants_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    first.source_tenant_id = "tenant-1"
    first.source_job_id = "job-1"
    db_session.add(first)

    second = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    second.source_tenant_id = "tenant-2"
    second.source_job_id = "job-1"
    db_session.add(second)
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 2


async def test_same_no_tenant_natural_key_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    """The exact NULL loophole ADR 0004 fixes: two occurrences with
    `source_tenant_id IS NULL` and the same `source_job_id` must still
    collide, even though ordinary PostgreSQL unique indexes treat every
    NULL as distinct from every other NULL."""
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    first.source_job_id = "job-1"
    db_session.add(first)
    await db_session.commit()

    second = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    second.source_job_id = "job-1"
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_same_id_under_different_provider_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(
        job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, provider="ats_scrapers"
    )
    first.source_job_id = "job-1"
    db_session.add(first)

    second = make_job_occurrence(
        job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, provider="jobspy"
    )
    second.source_job_id = "job-1"
    db_session.add(second)
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 2


async def test_tenant_null_and_tenant_present_rows_coexist(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    first.source_job_id = "job-1"
    db_session.add(first)

    second = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    second.source_tenant_id = "tenant-1"
    second.source_job_id = "job-1"
    db_session.add(second)
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 2


async def test_same_fallback_url_within_same_provider_source_rejected(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    first.source_url_normalized = "https://acme.com/careers/1"
    db_session.add(first)
    await db_session.commit()

    second = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    second.source_url_normalized = "https://acme.com/careers/1"
    db_session.add(second)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_same_fallback_url_under_different_provider_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(
        job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, provider="ats_scrapers"
    )
    first.source_url_normalized = "https://acme.com/careers/1"
    db_session.add(first)

    second = make_job_occurrence(
        job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT, provider="jobspy"
    )
    second.source_url_normalized = "https://acme.com/careers/1"
    db_session.add(second)
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 2


async def test_duplicate_source_urls_allowed_when_source_job_id_present(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    """The fallback URL index is scoped `WHERE source_job_id IS NULL` — it
    must not apply at all once a stable per-posting ID exists."""
    job_id = await _insert_job(db_session, make_job)
    first = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    first.source_job_id = "job-1"
    first.source_url_normalized = "https://acme.com/careers/1"
    db_session.add(first)

    second = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    second.source_job_id = "job-2"
    second.source_url_normalized = "https://acme.com/careers/1"
    db_session.add(second)
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 2


async def test_multiple_rows_with_null_source_job_id_and_null_normalized_url_accepted(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    """Two malformed-source-URL occurrences (both `source_job_id` and
    `source_url_normalized` NULL) must not be treated as duplicates of each
    other merely because they're both unparseable."""
    job_id = await _insert_job(db_session, make_job)
    for _ in range(3):
        db_session.add(
            make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
        )
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(JobOccurrence))).scalar_one()
    assert count == 3


# --------------------------------------------------------------------------
# Real concurrency — proves the unique indexes serialize a genuine race,
# not just two sequential commits in one session.
# --------------------------------------------------------------------------


async def test_concurrent_insert_same_no_tenant_natural_key_one_fails(
    db_engine: AsyncEngine,
) -> None:
    """The exact NULL loophole from ADR 0004, exercised as a real race
    between two independent connections."""
    async with real_committed_job(db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT) as (
        _job_session,
        job_id,
    ):

        async def _attempt() -> bool:
            async with AsyncSession(bind=db_engine) as session:
                session.add(
                    JobOccurrence(
                        job_id=job_id,
                        provider="ats_scrapers",
                        source="greenhouse",
                        source_job_id="job-race",
                        source_url="https://boards.greenhouse.io/acme/jobs/race",
                        first_seen_at=_SEEN_AT,
                        last_seen_at=_SEEN_AT,
                    )
                )
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return False
                return True

        try:
            results = await asyncio.gather(_attempt(), _attempt())
            assert sorted(results) == [False, True]

            async with AsyncSession(bind=db_engine) as verify_session:
                count = (
                    await verify_session.execute(
                        select(func.count())
                        .select_from(JobOccurrence)
                        .where(JobOccurrence.source_job_id == "job-race")
                    )
                ).scalar_one()
                assert count == 1
        finally:
            async with AsyncSession(bind=db_engine) as cleanup_session:
                rows = (
                    (
                        await cleanup_session.execute(
                            select(JobOccurrence).where(JobOccurrence.source_job_id == "job-race")
                        )
                    )
                    .scalars()
                    .all()
                )
                for row in rows:
                    await cleanup_session.delete(row)
                await cleanup_session.commit()


async def test_concurrent_insert_same_fallback_url_key_one_fails(db_engine: AsyncEngine) -> None:
    async with real_committed_job(db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT) as (
        _job_session,
        job_id,
    ):

        async def _attempt() -> bool:
            async with AsyncSession(bind=db_engine) as session:
                occurrence = JobOccurrence(
                    job_id=job_id,
                    provider="ats_scrapers",
                    source="greenhouse",
                    source_url="https://boards.greenhouse.io/acme/jobs/race",
                    first_seen_at=_SEEN_AT,
                    last_seen_at=_SEEN_AT,
                )
                occurrence.source_url_normalized = "https://acme.com/careers/race"
                session.add(occurrence)
                try:
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return False
                return True

        try:
            results = await asyncio.gather(_attempt(), _attempt())
            assert sorted(results) == [False, True]

            async with AsyncSession(bind=db_engine) as verify_session:
                count = (
                    await verify_session.execute(
                        select(func.count())
                        .select_from(JobOccurrence)
                        .where(
                            JobOccurrence.source_url_normalized == "https://acme.com/careers/race"
                        )
                    )
                ).scalar_one()
                assert count == 1
        finally:
            async with AsyncSession(bind=db_engine) as cleanup_session:
                rows = (
                    (
                        await cleanup_session.execute(
                            select(JobOccurrence).where(
                                JobOccurrence.source_url_normalized
                                == "https://acme.com/careers/race"
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for row in rows:
                    await cleanup_session.delete(row)
                await cleanup_session.commit()


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession,
    make_job: Callable[..., Job],
    make_job_occurrence: Callable[..., JobOccurrence],
) -> None:
    job_id = await _insert_job(db_session, make_job)
    occurrence = make_job_occurrence(job_id=job_id, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT)
    db_session.add(occurrence)
    await db_session.commit()
    await db_session.refresh(occurrence)

    now = datetime.now(UTC)
    assert abs((now - occurrence.created_at).total_seconds()) < 60
    assert abs((now - occurrence.updated_at).total_seconds()) < 60


async def test_updated_at_advances_on_orm_update(db_engine: AsyncEngine) -> None:
    """Same rationale as every other table's equivalent test: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction, so this uses real,
    separately-committed transactions."""
    async with real_committed_job_occurrence(
        db_engine, first_seen_at=_SEEN_AT, last_seen_at=_SEEN_AT
    ) as (session, _job_id, occurrence_id):
        occurrence = await session.get(JobOccurrence, occurrence_id)
        assert occurrence is not None
        first_updated_at = occurrence.updated_at

        occurrence.applicant_count = 5
        await session.commit()
        await session.refresh(occurrence)

        assert occurrence.updated_at > first_updated_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(JobOccurrence))
        ).scalar_one()
        assert count == 0
