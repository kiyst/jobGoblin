import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models import Company
from app.normalization.company import normalize_domain
from tests.conftest import real_committed_company, real_committed_duplicate_company_pair

# --------------------------------------------------------------------------
# normalize_domain() — pure function, no database involved
# --------------------------------------------------------------------------


def test_normalize_domain_lowercases_and_trims() -> None:
    assert normalize_domain("  ACME.com  ") == "acme.com"


def test_normalize_domain_bare_host_accepted() -> None:
    assert normalize_domain("acme.com") == "acme.com"


def test_normalize_domain_arbitrary_scheme_url_accepted() -> None:
    assert normalize_domain("ftp://acme.com/") == "acme.com"


def test_normalize_domain_strips_userinfo_port_path_query_fragment() -> None:
    assert normalize_domain("http://user:pass@acme.com:8080/careers?x=1#frag") == "acme.com"


def test_normalize_domain_strips_one_leading_www() -> None:
    assert normalize_domain("https://www.acme.com") == "acme.com"


def test_normalize_domain_strips_one_trailing_dot() -> None:
    assert normalize_domain("acme.com.") == "acme.com"


def test_normalize_domain_casing_collision() -> None:
    assert normalize_domain("Acme.com") == normalize_domain("acme.com")


def test_normalize_domain_www_collision() -> None:
    assert normalize_domain("www.acme.com") == normalize_domain("acme.com")


def test_normalize_domain_unicode_punycode_equivalence() -> None:
    assert normalize_domain("café.com") == normalize_domain("xn--caf-dma.com")
    assert normalize_domain("café.com") == "xn--caf-dma.com"


def test_normalize_domain_distinct_domains_remain_distinct() -> None:
    assert normalize_domain("acme.com") != normalize_domain("acme.io")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_normalize_domain_empty_or_missing_input_returns_none(value: str | None) -> None:
    assert normalize_domain(value) is None


def test_normalize_domain_single_label_host_returns_none() -> None:
    assert normalize_domain("acme") is None


@pytest.mark.parametrize(
    "value",
    ["192.168.1.1", "[::1]", "[::1]:8080", "::1"],
    ids=["ipv4", "bracketed-ipv6", "bracketed-ipv6-with-port", "bare-ipv6"],
)
def test_normalize_domain_ip_literal_returns_none(value: str) -> None:
    assert normalize_domain(value) is None


def test_normalize_domain_empty_label_returns_none() -> None:
    assert normalize_domain("a..b.com") is None


@pytest.mark.parametrize(
    "value", ["acme.com:99999", "acme.com:abc"], ids=["out-of-range", "non-numeric"]
)
def test_normalize_domain_invalid_port_returns_none(value: str) -> None:
    assert normalize_domain(value) is None


@pytest.mark.parametrize(
    "value", ["/careers", "?x=1", "https://"], ids=["bare-path", "bare-query", "empty-authority"]
)
def test_normalize_domain_missing_host_returns_none(value: str) -> None:
    assert normalize_domain(value) is None


def test_normalize_domain_oversized_domain_returns_none() -> None:
    assert normalize_domain("a" * 300 + ".com") is None


@pytest.mark.parametrize(
    "value",
    ["a b.com", "acme_corp.com", "-bad.com", "xn--zzzzzz.com"],
    ids=["whitespace", "underscore", "leading-hyphen", "bad-punycode"],
)
def test_normalize_domain_invalid_idna_returns_none(value: str) -> None:
    assert normalize_domain(value) is None


# --------------------------------------------------------------------------
# Regression: structural checks (www./trailing-dot/IP-literal/multi-label)
# must run on the canonical, post-UTS-#46-mapping form, not the raw input —
# UTS #46 mapping can itself turn a Unicode look-alike into the exact ASCII
# form those checks watch for, letting it bypass a pre-mapping check.
# Reproduced against the pre-fix implementation at commit 7bd27a7.
# --------------------------------------------------------------------------


def test_normalize_domain_doubled_ascii_trailing_dot_returns_none() -> None:
    """Two trailing dots must not survive as one — the pre-fix
    implementation stripped exactly one trailing dot before IDNA ever saw
    the input, silently discarding evidence of the second (empty) label."""
    assert normalize_domain("acme.com..") is None


def test_normalize_domain_ideographic_full_stop_leading_www_collides() -> None:
    """U+3002 (IDEOGRAPHIC FULL STOP) maps to ASCII "." under UTS #46, so
    "www。acme.com" is the same www-prefixed domain as "www.acme.com",
    not a distinct one."""
    assert normalize_domain("www。acme.com") == normalize_domain("www.acme.com")
    assert normalize_domain("www。acme.com") == "acme.com"


def test_normalize_domain_fullwidth_full_stop_leading_www_collides() -> None:
    """U+FF0E (FULLWIDTH FULL STOP) maps to ASCII "." under UTS #46, same
    rationale as the ideographic full stop above."""
    assert normalize_domain("www．acme.com") == normalize_domain("www.acme.com")
    assert normalize_domain("www．acme.com") == "acme.com"


def test_normalize_domain_ideographic_full_stop_trailing_root_dot_stripped() -> None:
    """A UTS-#46-mapped trailing root-label separator must be stripped just
    like an ASCII trailing dot — it must not survive in the stored value."""
    assert normalize_domain("acme.com。") == "acme.com"


def test_normalize_domain_fullwidth_full_stop_trailing_root_dot_stripped() -> None:
    assert normalize_domain("acme.com．") == "acme.com"


def test_normalize_domain_uts46_mapped_fullwidth_digits_ip_literal_returns_none() -> None:
    """Fullwidth digits (U+FF10-U+FF19) map to their ASCII equivalents under
    UTS #46, so "１２７.０.０.１" maps to the IPv4
    literal "127.0.0.1" — this must be rejected exactly like the plain-ASCII
    IP literal is, not accepted as an ordinary-looking hostname."""
    assert normalize_domain("１２７.０.０.１") is None


# --------------------------------------------------------------------------
# Company model — database-backed
# --------------------------------------------------------------------------


async def _assert_direct_sql_name_insert_rejected(
    db_session: AsyncSession, name_sql_literal: str
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(f"INSERT INTO companies (id, name) VALUES (gen_random_uuid(), {name_sql_literal})")
        )
        await db_session.commit()
    await db_session.rollback()


async def test_table_starts_empty(db_session: AsyncSession) -> None:
    """Proves test isolation: if a prior test's row leaked, this would fail."""
    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 0


async def test_insert_and_retrieve_valid_company(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    company = make_company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert isinstance(company.id, uuid.UUID)

    fetched = await db_session.get(Company, company.id)
    assert fetched is not None
    assert fetched.name == "Acme Corp"
    assert fetched.normalized_name == "acme corp"
    assert fetched.domain is None
    assert fetched.homepage_url is None
    assert fetched.career_page_url is None
    assert fetched.industry is None
    assert fetched.duplicate_of_company_id is None
    assert fetched.created_at is not None
    assert fetched.updated_at is not None
    assert fetched.created_at.tzinfo is not None
    assert fetched.updated_at.tzinfo is not None


async def test_name_is_trimmed_on_input(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    """The ORM validator trims exactly the four covered whitespace
    characters but never touches case."""
    company = make_company(name="\t Acme Corp \n")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert company.name == "Acme Corp"


async def test_direct_sql_empty_name_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_name_insert_rejected(db_session, "''")


async def test_direct_sql_whitespace_only_name_rejected(db_session: AsyncSession) -> None:
    await _assert_direct_sql_name_insert_rejected(db_session, r"E'\t\n\r'")


async def test_direct_sql_non_normalized_name_rejected(db_session: AsyncSession) -> None:
    """An otherwise-valid value that isn't already trimmed is still
    rejected — the database never trims on write, only validates that it
    already is."""
    await _assert_direct_sql_name_insert_rejected(db_session, r"E'\tAcme Corp\n'")


async def test_normalized_name_generated_on_insert(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    """The ORM validator only trims outer whitespace — it does not collapse
    an internal run of spaces; that half of the algorithm is applied
    entirely by PostgreSQL's generated column."""
    company = make_company(name="Acme   Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert company.name == "Acme   Corp"
    assert company.normalized_name == "acme corp"


async def test_normalized_name_regenerated_on_name_update(db_engine: AsyncEngine) -> None:
    async with real_committed_company(db_engine, name="Acme Corp") as (session, company_id):
        company = await session.get(Company, company_id)
        assert company is not None
        assert company.normalized_name == "acme corp"

        company.name = "Globex Corporation"
        await session.commit()
        await session.refresh(company)

        assert company.normalized_name == "globex corporation"


async def test_direct_sql_cannot_set_normalized_name_directly(db_session: AsyncSession) -> None:
    """PostgreSQL itself rejects an INSERT that names a `GENERATED ALWAYS`
    column — this is a database-level guarantee, not merely an ORM
    convention. PostgreSQL raises `GeneratedAlwaysError`, a different
    condition from a `CHECK`/`UNIQUE`/`FOREIGN KEY` violation, so SQLAlchemy
    surfaces it as `ProgrammingError`, not `IntegrityError`."""
    with pytest.raises(ProgrammingError):
        await db_session.execute(
            text(
                "INSERT INTO companies (id, name, normalized_name) "
                "VALUES (gen_random_uuid(), 'Acme Corp', 'whatever')"
            )
        )
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_omitting_normalized_name_is_generated_by_postgres(
    db_session: AsyncSession,
) -> None:
    """A raw INSERT that never mentions `normalized_name` at all — bypassing
    the ORM (and its validator) entirely — still gets a correctly computed
    value, proving PostgreSQL itself generates it. Uses an already-trimmed
    name (with an internal run of spaces) so the insert satisfies the
    `name` normalization `CHECK`s and only `normalized_name`'s own
    collapse-and-lowercase behavior is under test."""
    result = await db_session.execute(
        text(
            "INSERT INTO companies (id, name) VALUES (gen_random_uuid(), "
            r"E'Acme   Corp')"
            " RETURNING normalized_name"
        )
    )
    await db_session.commit()

    assert result.scalar_one() == "acme corp"


async def test_two_companies_with_colliding_normalized_names_accepted(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    db_session.add(make_company(name="Acme Corp"))
    db_session.add(make_company(name="ACME   CORP"))
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 2


async def test_domain_is_normalized_on_orm_assignment(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    company = make_company(name="Acme Corp", domain="HTTPS://WWW.Acme.COM/careers")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert company.domain == "acme.com"


async def test_domain_defaults_to_none(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    company = make_company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert company.domain is None


async def test_unparseable_domain_normalizes_to_none_on_orm_path(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    """`normalize_domain()` never raises — an unparseable domain is stored
    as `NULL`, and ingestion is not failed by it."""
    company = make_company(name="Acme Corp", domain="not a valid host!!")
    db_session.add(company)
    await db_session.commit()  # must not raise
    await db_session.refresh(company)

    assert company.domain is None


async def test_duplicate_domain_rejected(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    db_session.add(make_company(name="Acme Corp", domain="acme.com"))
    await db_session.commit()

    db_session.add(make_company(name="Acme Corporation", domain="acme.com"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 1


async def test_direct_sql_domain_case_insensitive_collision_rejected(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    """Bypasses `normalize_domain()` entirely with a raw INSERT of a
    differently-cased, already-syntactically-normalized value — proving the
    unique index's own `lower(domain)` expression enforces case-insensitive
    uniqueness as a database-level backstop, not merely app-side
    normalization already agreeing on case."""
    db_session.add(make_company(name="Acme Corp", domain="acme.com"))
    await db_session.commit()

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO companies (id, name, domain) "
                "VALUES (gen_random_uuid(), 'Acme Corporation', 'ACME.COM')"
            )
        )
        await db_session.commit()
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 1


async def test_multiple_null_domain_companies_accepted(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    db_session.add(make_company(name="Acme Corp"))
    db_session.add(make_company(name="Beta Corp"))
    db_session.add(make_company(name="Gamma Corp"))
    await db_session.commit()  # must not raise

    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 3


async def test_concurrent_same_domain_insert_one_fails(db_engine: AsyncEngine) -> None:
    """Real concurrency, not two sequential commits in one session: two
    independent connections race to insert the same normalized domain;
    PostgreSQL's unique index must serialize them so exactly one succeeds."""

    async def _attempt(name: str) -> bool:
        async with AsyncSession(bind=db_engine) as session:
            session.add(Company(name=name, domain="Acme.com"))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    try:
        results = await asyncio.gather(_attempt("Racer One"), _attempt("Racer Two"))
        assert sorted(results) == [False, True]

        async with AsyncSession(bind=db_engine) as verify_session:
            count = (
                await verify_session.execute(
                    select(func.count()).select_from(Company).where(Company.domain == "acme.com")
                )
            ).scalar_one()
            assert count == 1
    finally:
        async with AsyncSession(bind=db_engine) as cleanup_session:
            rows = (
                (await cleanup_session.execute(select(Company).where(Company.domain == "acme.com")))
                .scalars()
                .all()
            )
            for row in rows:
                await cleanup_session.delete(row)
            await cleanup_session.commit()


async def test_self_reference_duplicate_of_company_id_rejected(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    company = make_company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    company.duplicate_of_company_id = company.id
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_direct_sql_self_reference_rejected(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    company = make_company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)
    company_id = company.id

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "UPDATE companies SET duplicate_of_company_id = :company_id WHERE id = :company_id"
            ).bindparams(company_id=company_id)
        )
        await db_session.commit()
    await db_session.rollback()


async def test_nonexistent_duplicate_of_company_id_rejected(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    db_session.add(make_company(name="Acme Corp", duplicate_of_company_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    count = (await db_session.execute(select(func.count()).select_from(Company))).scalar_one()
    assert count == 0


async def test_duplicate_of_company_id_valid_reference_accepted(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    original = make_company(name="Acme Corp")
    db_session.add(original)
    await db_session.commit()
    await db_session.refresh(original)
    # Captured now: the second commit below expires every attribute of
    # every object in the session, including `original`.
    original_id = original.id

    duplicate = make_company(name="Acme Corporation", duplicate_of_company_id=original_id)
    db_session.add(duplicate)
    await db_session.commit()  # must not raise
    await db_session.refresh(duplicate)

    assert duplicate.duplicate_of_company_id == original_id


async def test_deleting_original_company_sets_duplicate_of_company_id_null(
    db_engine: AsyncEngine,
) -> None:
    """Uses real, separately-committed transactions so `ON DELETE SET NULL`
    is actually exercised by PostgreSQL — the duplicate row must survive
    with its FK cleared, never be cascade-deleted."""
    async with real_committed_duplicate_company_pair(db_engine) as (
        session,
        original_id,
        duplicate_id,
    ):
        original = await session.get(Company, original_id)
        assert original is not None
        await session.delete(original)
        await session.commit()

        duplicate = await session.get(Company, duplicate_id)
        assert duplicate is not None
        assert duplicate.duplicate_of_company_id is None

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(Company))
        ).scalar_one()
        assert count == 0


@pytest.mark.parametrize("field", ["homepage_url", "career_page_url", "industry"])
async def test_nullable_text_defaults_to_none(
    db_session: AsyncSession, make_company: Callable[..., Company], field: str
) -> None:
    company = make_company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert getattr(company, field) is None


@pytest.mark.parametrize("field", ["homepage_url", "career_page_url", "industry"])
async def test_nullable_text_whitespace_only_becomes_none_on_orm_path(
    db_session: AsyncSession, make_company: Callable[..., Company], field: str
) -> None:
    """These fields are optional — a covered-whitespace-only value is "not
    provided", not invalid input, so ingestion is not failed by it."""
    company = make_company(name="Acme Corp", **{field: "\t \n"})
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert getattr(company, field) is None


@pytest.mark.parametrize("field", ["homepage_url", "career_page_url", "industry"])
async def test_nullable_text_trimmed_case_preserved_on_orm_path(
    db_session: AsyncSession, make_company: Callable[..., Company], field: str
) -> None:
    company = make_company(name="Acme Corp", **{field: "\t Some Value \n"})
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    assert getattr(company, field) == "Some Value"


@pytest.mark.parametrize("column", ["homepage_url", "career_page_url", "industry"])
async def test_direct_sql_nullable_text_empty_string_rejected(
    db_session: AsyncSession, column: str
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO companies (id, name, {column}) "
                "VALUES (gen_random_uuid(), 'Acme Corp', '')"
            )
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.parametrize("column", ["homepage_url", "career_page_url", "industry"])
async def test_direct_sql_nullable_text_wrapped_value_rejected(
    db_session: AsyncSession, column: str
) -> None:
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                f"INSERT INTO companies (id, name, {column}) "
                r"VALUES (gen_random_uuid(), 'Acme Corp', E'\tvalue\n')"
            )
        )
        await db_session.commit()
    await db_session.rollback()


async def test_created_at_and_updated_at_are_utc_aware(
    db_session: AsyncSession, make_company: Callable[..., Company]
) -> None:
    company = make_company(name="Acme Corp")
    db_session.add(company)
    await db_session.commit()
    await db_session.refresh(company)

    now = datetime.now(UTC)
    assert abs((now - company.created_at).total_seconds()) < 60
    assert abs((now - company.updated_at).total_seconds()) < 60


async def test_updated_at_advances_on_orm_update(db_engine: AsyncEngine) -> None:
    """Same rationale as every other table's equivalent test: PostgreSQL's
    `now()` is fixed for the lifetime of one transaction, so this uses real,
    separately-committed transactions."""
    async with real_committed_company(db_engine, name="Acme Corp") as (session, company_id):
        company = await session.get(Company, company_id)
        assert company is not None
        first_updated_at = company.updated_at

        company.name = "Acme Corporation"
        await session.commit()
        await session.refresh(company)

        assert company.updated_at > first_updated_at

    async with AsyncSession(bind=db_engine) as verify_session:
        count = (
            await verify_session.execute(select(func.count()).select_from(Company))
        ).scalar_one()
        assert count == 0
