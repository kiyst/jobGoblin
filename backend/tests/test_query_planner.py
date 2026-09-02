import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.db.models.collection_run import CollectionRun
from app.db.models.job_occurrence import JobOccurrence
from app.db.models.raw_job_ingestion import RawJobIngestion
from app.db.models.saved_search import SavedSearch
from app.discovery.query_planner import QueryPlanner, QueryPlanValidationError
from app.ingestion import pipeline
from app.ingestion.clock import FixedClock
from app.providers.fixture import FixtureProvider
from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult
from app.schemas.provider import ProviderCapabilities, SourceCapabilities, SourceQuery
from tests.test_ingestion_pipeline import _cleanup, _load_fixture

_DEFAULT_PROVIDER = "fixture_provider"


def _saved_search(**overrides: object) -> SavedSearch:
    """An in-memory-only `SavedSearch` — never persisted, never queried.
    `QueryPlanner.plan()` only reads user-set attributes, none of which are
    server-generated, so no database session is needed to construct one."""
    defaults: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "name": "Backend roles",
        "remote_rules": "any",
        "polling_schedule": "manual",
    }
    defaults.update(overrides)
    return SavedSearch(**defaults)


def _capabilities(
    sources: dict[str, SourceCapabilities], *, provider: str = _DEFAULT_PROVIDER
) -> ProviderCapabilities:
    return ProviderCapabilities(provider=provider, sources=sources)


def _source_capabilities(source: str, **overrides: object) -> SourceCapabilities:
    defaults: dict[str, object] = {"source": source, "max_concurrency": 1}
    defaults.update(overrides)
    return SourceCapabilities(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Source selection: absent key, explicit empty, explicit non-empty, unknown.
# ---------------------------------------------------------------------------


def test_absent_provider_key_expands_to_every_advertised_source_sorted() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities(
        {
            "zeta": _source_capabilities("zeta"),
            "alpha": _source_capabilities("alpha"),
        }
    )
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.sources == ["alpha", "zeta"]  # sorted, not insertion order


def test_absent_provider_key_with_zero_advertised_sources_returns_none() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({})
    assert QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[]) is None


def test_explicit_empty_source_list_returns_none() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: []})
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    assert QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[]) is None


def test_explicit_non_empty_list_preserves_requested_order() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: ["b_source", "a_source"]})
    capabilities = _capabilities(
        {
            "a_source": _source_capabilities("a_source"),
            "b_source": _source_capabilities("b_source"),
        }
    )
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.sources == ["b_source", "a_source"]  # caller's order, never re-sorted


def test_unknown_requested_source_raises_before_any_source_query_built() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: ["ghost_source"]})
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])


def test_unknown_source_error_message_never_contains_the_offending_name() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: ["ghost_source_xyz"]})
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError) as excinfo:
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert "ghost_source_xyz" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# enabled_sources runtime shape validation (its own CHECK only guarantees a
# top-level JSON object, nothing about a given key's value).
# ---------------------------------------------------------------------------


def test_malformed_enabled_sources_value_not_a_list_raises() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: "not-a-list"})
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError) as excinfo:
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert "not-a-list" not in str(excinfo.value)


def test_enabled_sources_value_with_non_string_element_raises() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: ["fixture_ats", 123]})
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])


def test_enabled_sources_value_with_duplicate_source_names_raises() -> None:
    saved_search = _saved_search(
        enabled_sources={_DEFAULT_PROVIDER: ["fixture_ats", "fixture_ats"]}
    )
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])


# ---------------------------------------------------------------------------
# Canonical-slug and capability-consistency validation, fails closed before
# any selection logic runs.
# ---------------------------------------------------------------------------


def test_invalid_provider_slug_raises() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities(
        {"fixture_ats": _source_capabilities("fixture_ats")}, provider="Not A Slug!"
    )
    with pytest.raises(QueryPlanValidationError) as excinfo:
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert "Not A Slug!" not in str(excinfo.value)


def test_invalid_capability_map_source_slug_raises() -> None:
    """The mapping *key* itself is not a canonical slug (equal to its own
    embedded `.source` so the mismatch check is never what fires here —
    this isolates the slug-grammar check on the key specifically)."""
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"Bad Key!": _source_capabilities("Bad Key!")})
    with pytest.raises(QueryPlanValidationError) as excinfo:
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert "Bad Key!" not in str(excinfo.value)


def test_invalid_embedded_source_slug_raises() -> None:
    """The mapping key is a valid slug; only the embedded `.source` value
    fails the grammar — isolates the slug check on the embedded value,
    proven reachable independently of the key's own half of the check."""
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"good_key": _source_capabilities("Bad Source!")})
    with pytest.raises(QueryPlanValidationError) as excinfo:
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert "Bad Source!" not in str(excinfo.value)


def test_capability_key_source_mismatch_raises() -> None:
    """Key and embedded `.source` are each individually valid slugs, but
    disagree with each other."""
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"source_a": _source_capabilities("source_b")})
    with pytest.raises(QueryPlanValidationError) as excinfo:
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert "source_a" not in str(excinfo.value)
    assert "source_b" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Defensive titles/locations validation.
# ---------------------------------------------------------------------------


def test_bare_string_titles_rejected() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        # `str` structurally satisfies `Sequence[str]` (each character is a
        # `str`), so mypy accepts this call — the runtime isinstance guard
        # exists precisely because the type system cannot catch this.
        QueryPlanner.plan(saved_search, capabilities, titles="engineer", locations=[])


def test_bare_string_locations_rejected() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(saved_search, capabilities, titles=[], locations="remote")


def test_non_string_title_element_rejected() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(
            saved_search,
            capabilities,
            titles=["Engineer", 123],  # type: ignore[list-item]
            locations=[],
        )


def test_non_string_location_element_rejected() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(
            saved_search,
            capabilities,
            titles=[],
            locations=["Remote", None],  # type: ignore[list-item]
        )


def test_deterministic_supplied_title_location_ordering_is_preserved() -> None:
    saved_search = _saved_search(enabled_sources=None)
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    result = QueryPlanner.plan(
        saved_search,
        capabilities,
        titles=["Zeta Engineer", "Alpha Engineer"],
        locations=["Zeta City", "Alpha City"],
    )
    assert result is not None
    assert result.titles == ["Zeta Engineer", "Alpha Engineer"]
    assert result.locations == ["Zeta City", "Alpha City"]


# ---------------------------------------------------------------------------
# Field mapping.
# ---------------------------------------------------------------------------


def test_preferred_companies_maps_to_company_filter() -> None:
    saved_search = _saved_search(enabled_sources=None, preferred_companies=["Acme", "Widgets Inc"])
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.company_filter == ["Acme", "Widgets Inc"]


@pytest.mark.parametrize(
    ("remote_rules", "expected_remote_ok"),
    [
        ("remote_only", True),
        ("hybrid_ok", None),
        ("onsite_ok", None),
        ("any", None),
    ],
)
def test_remote_rules_mapping(remote_rules: str, expected_remote_ok: bool | None) -> None:
    saved_search = _saved_search(enabled_sources=None, remote_rules=remote_rules)
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.remote_ok is expected_remote_ok


def test_radius_miles_mapped_independently_of_locations_population() -> None:
    """`radius_miles` is copied whenever `saved_search.radius_miles` is set —
    never gated on whether `locations` is also populated. No new
    "radius requires location" invariant is invented here."""
    saved_search = _saved_search(enabled_sources=None, radius_miles=25)
    capabilities = _capabilities(
        {"fixture_ats": _source_capabilities("fixture_ats", supports_location_filter=True)}
    )
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.radius_miles == 25.0
    assert result.locations == []
    assert result.local_enforcement["fixture_ats"] == set()  # radius alone, remotely supported


def test_every_representable_field_maps_correctly() -> None:
    saved_search = _saved_search(
        enabled_sources=None,
        excluded_titles=["Intern"],
        radius_miles=10,
        salary_floor=90000,
        employment_types=["full_time"],
        seniority=["senior"],
        recency_limit_hours=48,
        preferred_companies=["Acme"],
        excluded_companies=["Globex"],
        remote_rules="any",
    )
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    result = QueryPlanner.plan(
        saved_search, capabilities, titles=["Engineer"], locations=["Remote"]
    )
    assert result is not None
    assert result.titles == ["Engineer"]
    assert result.excluded_titles == ["Intern"]
    assert result.locations == ["Remote"]
    assert result.radius_miles == 10.0
    assert result.salary_floor == 90000
    assert result.employment_types == ["full_time"]
    assert result.seniority == ["senior"]
    assert result.posted_within_hours == 48
    assert result.company_filter == ["Acme"]
    assert result.excluded_companies == ["Globex"]
    assert result.max_results is None  # no SavedSearch counterpart exists


# ---------------------------------------------------------------------------
# local_enforcement.
# ---------------------------------------------------------------------------


def test_local_enforcement_uses_source_query_field_names_not_saved_search_names() -> None:
    saved_search = _saved_search(
        enabled_sources=None, recency_limit_hours=24, preferred_companies=["Acme"]
    )
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    enforcement = result.local_enforcement["fixture_ats"]
    assert "posted_within_hours" in enforcement
    assert "company_filter" in enforcement
    assert "recency_limit_hours" not in enforcement
    assert "preferred_companies" not in enforcement


def test_every_resolved_source_appears_in_local_enforcement_including_empty_set() -> None:
    saved_search = _saved_search(enabled_sources=None)  # nothing populated at all
    capabilities = _capabilities(
        {
            "source_a": _source_capabilities("source_a"),
            "source_b": _source_capabilities("source_b"),
        }
    )
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.local_enforcement == {"source_a": set(), "source_b": set()}


def test_two_sources_with_different_capabilities_receive_different_local_enforcement() -> None:
    """ARCHITECTURE.md §11's own required fixture case."""
    saved_search = _saved_search(enabled_sources=None, salary_floor=100000)
    capabilities = _capabilities(
        {
            "supports_salary": _source_capabilities("supports_salary", supports_salary_filter=True),
            "no_salary_support": _source_capabilities("no_salary_support"),
        }
    )
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.local_enforcement["supports_salary"] == set()
    assert result.local_enforcement["no_salary_support"] == {"salary_floor"}


def test_dedicated_capability_boolean_overrides_contradictory_generic_declaration() -> None:
    """`supported_query_fields` never governs a dedicated field, regardless
    of what it contains — the dedicated boolean alone decides it, in both
    directions."""
    saved_search = _saved_search(enabled_sources=None, salary_floor=100000)
    capabilities = _capabilities(
        {
            # Dedicated True wins even though the generic set redundantly
            # also names the same field.
            "generic_says_yes_dedicated_says_yes": _source_capabilities(
                "generic_says_yes_dedicated_says_yes",
                supports_salary_filter=True,
                supported_query_fields={"salary_floor"},
            ),
            # Dedicated False wins even though the generic set contradicts it.
            "generic_says_yes_dedicated_says_no": _source_capabilities(
                "generic_says_yes_dedicated_says_no",
                supports_salary_filter=False,
                supported_query_fields={"salary_floor"},
            ),
        }
    )
    result = QueryPlanner.plan(saved_search, capabilities, titles=[], locations=[])
    assert result is not None
    assert result.local_enforcement["generic_says_yes_dedicated_says_yes"] == set()
    assert result.local_enforcement["generic_says_yes_dedicated_says_no"] == {"salary_floor"}


def test_every_implemented_populated_field_is_checked_for_local_enforcement() -> None:
    """A source with zero capabilities and every mapped field populated —
    proves none is silently skipped."""
    saved_search = _saved_search(
        enabled_sources=None,
        excluded_titles=["Intern"],
        radius_miles=10,
        salary_floor=90000,
        employment_types=["full_time"],
        seniority=["senior"],
        recency_limit_hours=48,
        preferred_companies=["Acme"],
        excluded_companies=["Globex"],
        remote_rules="remote_only",
    )
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    result = QueryPlanner.plan(
        saved_search, capabilities, titles=["Engineer"], locations=["Remote"]
    )
    assert result is not None
    assert result.local_enforcement["fixture_ats"] == {
        "titles",
        "excluded_titles",
        "locations",
        "radius_miles",
        "salary_floor",
        "employment_types",
        "seniority",
        "posted_within_hours",
        "company_filter",
        "excluded_companies",
        "remote_ok",
    }


# ---------------------------------------------------------------------------
# Purity.
# ---------------------------------------------------------------------------


def test_plan_does_not_mutate_saved_search_provider_capabilities_or_supplied_sequences() -> None:
    saved_search = _saved_search(
        enabled_sources={_DEFAULT_PROVIDER: ["fixture_ats"]}, salary_floor=100000
    )
    enabled_sources_before = dict(saved_search.enabled_sources or {})
    capabilities = _capabilities({"fixture_ats": _source_capabilities("fixture_ats")})
    sources_before = dict(capabilities.sources)
    titles_in: list[str] = ["Engineer"]
    locations_in: list[str] = ["Remote"]

    result = QueryPlanner.plan(saved_search, capabilities, titles=titles_in, locations=locations_in)

    assert result is not None
    assert saved_search.enabled_sources == enabled_sources_before
    assert capabilities.sources == sources_before
    assert titles_in == ["Engineer"]
    assert locations_in == ["Remote"]
    # The returned SourceQuery's own lists are independent copies, not the
    # same list objects the caller supplied.
    result.titles.append("mutated")
    assert titles_in == ["Engineer"]


# ---------------------------------------------------------------------------
# Fixture/pipeline integration — single source only (FixtureProvider emits
# exactly one SourceRunStats regardless of query; not modified here). This
# proves only that a valid planned SourceQuery is consumable by the existing,
# unmodified pipeline and persists the supplied fixture without network
# access — NOT that FixtureProvider applies the planned filters remotely, or
# that pipeline.run() applies any local filtering. Neither happens: this
# slice implements no filtering behavior at all, only planning.
# ---------------------------------------------------------------------------


class _CallCountingFixtureProvider(FixtureProvider):
    """Wraps `FixtureProvider` only to prove `discover()` is never reached
    when `QueryPlanner.plan()` raises first — never used to assert anything
    about filtering, since `FixtureProvider` itself never filters."""

    def __init__(self, fixtures: Sequence[DiscoveredJob], *, called_at: datetime) -> None:
        super().__init__(fixtures, called_at=called_at)
        self.discover_call_count = 0

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        self.discover_call_count += 1
        return await super().discover(query)


async def test_unknown_source_raises_before_fixture_provider_discover_is_called() -> None:
    saved_search = _saved_search(enabled_sources={_DEFAULT_PROVIDER: ["ghost_source"]})
    provider = _CallCountingFixtureProvider([], called_at=datetime(2026, 11, 1, tzinfo=UTC))
    with pytest.raises(QueryPlanValidationError):
        QueryPlanner.plan(saved_search, provider.capabilities(), titles=[], locations=[])
    assert provider.discover_call_count == 0


async def test_planned_source_query_feeds_pipeline_run_without_network_access(
    db_engine: AsyncEngine,
) -> None:
    called_at = datetime(2026, 11, 2, tzinfo=UTC)
    job = _load_fixture("clean_tenant_scoped")
    provider = FixtureProvider([job], called_at=called_at, source="fixture_ats")

    saved_search = _saved_search(enabled_sources=None, salary_floor=50000)
    planned_query = QueryPlanner.plan(
        saved_search, provider.capabilities(), titles=["Engineer"], locations=[]
    )
    assert planned_query is not None
    assert planned_query.sources == ["fixture_ats"]  # single source: matches FixtureProvider

    collection_run_ids: list[uuid.UUID] = []
    job_ids: list[uuid.UUID] = []
    raw_ingestion_ids: list[uuid.UUID] = []
    try:
        run_id = await pipeline.run(
            db_engine,
            provider,
            planned_query,
            observed_at=called_at,
            clock=FixedClock(called_at),
        )
        collection_run_ids.append(run_id)

        async with AsyncSession(bind=db_engine) as session:
            run = await session.get(CollectionRun, run_id)
            assert run is not None
            assert run.status == "completed"
            assert run.jobs_inserted == 1

            raw_rows = (await session.execute(select(RawJobIngestion))).scalars().all()
            raw_ingestion_ids.extend(row.id for row in raw_rows)

            occurrences = (
                (
                    await session.execute(
                        select(JobOccurrence).where(
                            JobOccurrence.source_job_id == job.source_job_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            job_ids.extend(occurrence.job_id for occurrence in occurrences)

            assert len(raw_rows) == 1
            assert raw_rows[0].processing_status == "normalized"
            assert len(occurrences) == 1
    finally:
        await _cleanup(
            db_engine,
            user_ids=[],
            job_ids=job_ids,
            collection_run_ids=collection_run_ids,
            raw_ingestion_ids=raw_ingestion_ids,
        )
