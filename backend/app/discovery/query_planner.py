import math
from collections.abc import Sequence

from app.db.models.saved_search import SavedSearch
from app.schemas.identifiers import is_canonical_slug
from app.schemas.provider import ProviderCapabilities, SourceQuery

# Canonical-identifier grammar validation (lowercase ASCII slug, same
# grammar already enforced by every `provider`/`source` database CHECK in
# this schema) is shared with `app/providers/registry.py` via
# `app.schemas.identifiers.is_canonical_slug()` — see that module for why
# it is a predicate function rather than an exported regex.

# Every `QueryPlanValidationError` message below is a fixed, categorical
# string — never an f-string interpolating a provider name, source name,
# capabilities-mapping key, embedded `SourceCapabilities.source`, or any
# `enabled_sources` JSON value. All of that is `SavedSearch`-owned,
# effectively user-controlled data; none of it is "trusted" merely because
# it originates from a `ProviderCapabilities` object rather than raw JSON —
# a provider adapter can be buggy, and `enabled_sources` is written through
# ordinary application code, not hand-audited. These messages are written to
# be safe to log or persist verbatim (docs/PHASE_RISK_CHECKLIST.md's
# "logs... never expose... raw stack traces" non-negotiable, applied here to
# a validation error that may itself be logged or persisted later).
_ERROR_PROVIDER_SLUG_INVALID = (
    "provider_capabilities.provider does not match the canonical source-slug grammar"
)
_ERROR_CAPABILITY_SOURCE_SLUG_INVALID = (
    "a ProviderCapabilities.sources mapping key or its embedded "
    "SourceCapabilities.source does not match the canonical source-slug grammar"
)
_ERROR_CAPABILITY_KEY_MISMATCH = (
    "a ProviderCapabilities.sources mapping key does not match its own "
    "embedded SourceCapabilities.source"
)
_ERROR_TITLES_BARE_STRING = "titles must be a sequence of strings, not a bare str/bytes value"
_ERROR_LOCATIONS_BARE_STRING = "locations must be a sequence of strings, not a bare str/bytes value"
_ERROR_TITLES_NON_STRING = "titles must contain only strings"
_ERROR_LOCATIONS_NON_STRING = "locations must contain only strings"
_ERROR_ENABLED_SOURCES_NOT_LIST = "enabled_sources value for the selected provider must be a list"
_ERROR_ENABLED_SOURCES_NON_STRING = (
    "enabled_sources value for the selected provider must contain only strings"
)
_ERROR_ENABLED_SOURCES_DUPLICATE = (
    "enabled_sources value for the selected provider contains duplicate source names"
)
_ERROR_UNKNOWN_SOURCE = "a requested source is not present in provider capabilities"
_ERROR_RADIUS_MILES_NOT_FINITE = (
    "saved_search.radius_miles could not be converted to a finite radius"
)

# Fields checked against one of `SourceCapabilities`' 4 dedicated booleans,
# never against the generic `supported_query_fields` set — authoritative
# for these fields regardless of what `supported_query_fields` also happens
# to contain (see `QueryPlanner.plan`'s own docstring for why no
# contradiction is possible). `locations`/`radius_miles` share one boolean:
# one location-filtering capability, not two independent ones.
_DEDICATED_CAPABILITY_FIELDS: dict[str, str] = {
    "salary_floor": "supports_salary_filter",
    "locations": "supports_location_filter",
    "radius_miles": "supports_location_filter",
    "remote_ok": "supports_remote_filter",
    "posted_within_hours": "supports_posted_within_filter",
}

# Every remaining mapped `SourceQuery` filter field — checked against
# `SourceCapabilities.supported_query_fields` by exact field-name string.
_GENERIC_CAPABILITY_FIELDS = frozenset(
    {
        "titles",
        "excluded_titles",
        "employment_types",
        "seniority",
        "company_filter",
        "excluded_companies",
    }
)

# Fields whose "populated" test is list-emptiness rather than `is not None`.
_LIST_VALUED_FIELDS = frozenset(
    {
        "titles",
        "excluded_titles",
        "locations",
        "employment_types",
        "seniority",
        "company_filter",
        "excluded_companies",
    }
)


class QueryPlanValidationError(RuntimeError):
    """A `SavedSearch`/`ProviderCapabilities` pair cannot be planned as
    given — a whole-provider failure, raised before any `SourceQuery` is
    constructed and before any provider call could occur. Never raised for
    a legitimate, well-formed empty selection (see `QueryPlanner.plan`'s own
    docstring for the two paths that legitimately return `None` instead).

    Every raise site in this module is one of:
    - `provider_capabilities.provider`, a `ProviderCapabilities.sources`
      mapping key, or an embedded `SourceCapabilities.source` failing the
      canonical lowercase-ASCII-slug grammar, or a mapping key disagreeing
      with its own embedded `SourceCapabilities.source`;
    - `titles`/`locations` being a bare `str`/`bytes` value (which `list()`
      would otherwise silently iterate character-by-character) or containing
      a non-string element;
    - `SavedSearch.enabled_sources`'s selected-provider value being present
      but not a list, containing a non-string element, or containing
      duplicate source names — its own `CHECK` only guarantees a top-level
      JSON object, nothing about a given key's value;
    - a requested source name absent from `provider_capabilities.sources`;
    - `saved_search.radius_miles` (an unconstrained-precision PostgreSQL
      `numeric`) converting to a non-finite `float` (e.g. `Decimal("1e10000")`
      overflows to infinity) — a non-finite radius is neither the stored
      value nor a usable one, and `SourceQuery.radius_miles`'s own type
      currently accepts it silently if not checked here.

    Every message above is a fixed, categorical string — see the module-level
    `_ERROR_*` constants for why no raise site ever interpolates the actual
    offending value.
    """


def _is_populated(field_name: str, value: object) -> bool:
    if field_name in _LIST_VALUED_FIELDS:
        return bool(value)
    return value is not None


class QueryPlanner:
    """Stateless — no instance state, no database access, no network access,
    no call to any provider's `discover()` (docs/ARCHITECTURE.md §5's
    dependency-boundary table: `discovery/` may depend on `schemas/` and
    `db/models` read access only, never `ingestion/` or a network client).
    Called as `QueryPlanner.plan(...)` — never instantiated; `plan` is a
    `@staticmethod` so that documented call form is exact, not merely
    conventional.
    """

    @staticmethod
    def plan(
        saved_search: SavedSearch,
        provider_capabilities: ProviderCapabilities,
        *,
        titles: Sequence[str],
        locations: Sequence[str],
    ) -> SourceQuery | None:
        """Translates one `SavedSearch` plus one provider's
        `ProviderCapabilities` into a `SourceQuery` for that provider
        (docs/ARCHITECTURE.md §6.5–6.6). Returns `None` — never raises —
        for a *legitimate* empty selection: an explicit
        `enabled_sources[provider] == []`, or an absent provider key
        expanding against a `provider_capabilities.sources` that itself
        advertises zero sources. Every *unknown* requested source name
        raises `QueryPlanValidationError` instead — it is never silently
        dropped, so "every listed source failed validation" can never be
        the reason an empty selection is reached; that path does not exist.

        `titles`/`locations` are supplied by the caller (the future
        orchestration layer, which loads `saved_search_titles`/
        `saved_search_locations`) as already-ordered, already-normalized
        plain string sequences — `QueryPlanner` performs no database I/O of
        its own and cannot load them itself. Neither table has an ordering
        column today (no `position`/`sort_order` on either
        `SavedSearchTitle` or `SavedSearchLocation`), so "deterministic
        order" is not this function's concept to define — it treats both
        sequences as opaque and preserves whatever order it is given,
        verbatim, never sorting, deduplicating, or reordering either one.
        Defining what deterministic order means is the future loader's own
        responsibility, not `QueryPlanner`'s.

        Multi-provider concerns are deliberately absent: this function is
        called once per already-selected provider (per its documented
        signature, which takes one `ProviderCapabilities`, not a registry
        or a mapping of them). It does not consult
        `saved_search.enabled_providers` at all — trusting the caller to
        invoke it only for providers actually enabled is a documented
        boundary of this slice, not an oversight; deciding *which*
        providers to plan for is the ProviderRegistry/orchestration slice's
        job.

        `local_enforcement` is computed per resolved source. Two disjoint
        mechanisms decide whether a populated field is added to a given
        source's set: 4 fields (`salary_floor`, `locations`/`radius_miles`
        together, `remote_ok`, `posted_within_hours`) are governed
        exclusively by their own dedicated `SourceCapabilities` boolean;
        every other mapped field is governed by exact-name membership in
        `SourceCapabilities.supported_query_fields`. No contradiction
        between the two is possible *by construction* — they are checked
        over disjoint field-name sets, so if a caller's
        `supported_query_fields` happens to also contain a dedicated
        field's name (e.g. `"salary_floor"`), it is simply never consulted
        for that field; the dedicated boolean alone decides it, silently,
        every time.
        """
        if not is_canonical_slug(provider_capabilities.provider):
            raise QueryPlanValidationError(_ERROR_PROVIDER_SLUG_INVALID)
        for key, source_capabilities in provider_capabilities.sources.items():
            if not is_canonical_slug(key) or not is_canonical_slug(source_capabilities.source):
                raise QueryPlanValidationError(_ERROR_CAPABILITY_SOURCE_SLUG_INVALID)
            if key != source_capabilities.source:
                raise QueryPlanValidationError(_ERROR_CAPABILITY_KEY_MISMATCH)

        if isinstance(titles, str | bytes):
            raise QueryPlanValidationError(_ERROR_TITLES_BARE_STRING)
        if isinstance(locations, str | bytes):
            raise QueryPlanValidationError(_ERROR_LOCATIONS_BARE_STRING)
        titles_out = list(titles)
        locations_out = list(locations)
        if not all(isinstance(item, str) for item in titles_out):
            raise QueryPlanValidationError(_ERROR_TITLES_NON_STRING)
        if not all(isinstance(item, str) for item in locations_out):
            raise QueryPlanValidationError(_ERROR_LOCATIONS_NON_STRING)

        provider = provider_capabilities.provider
        enabled_sources = saved_search.enabled_sources or {}
        if provider not in enabled_sources:
            resolved_sources = sorted(provider_capabilities.sources.keys())
        else:
            raw_value = enabled_sources[provider]
            if not isinstance(raw_value, list):
                raise QueryPlanValidationError(_ERROR_ENABLED_SOURCES_NOT_LIST)
            if not all(isinstance(name, str) for name in raw_value):
                raise QueryPlanValidationError(_ERROR_ENABLED_SOURCES_NON_STRING)
            if len(set(raw_value)) != len(raw_value):
                raise QueryPlanValidationError(_ERROR_ENABLED_SOURCES_DUPLICATE)
            if not raw_value:
                return None
            for name in raw_value:
                if name not in provider_capabilities.sources:
                    raise QueryPlanValidationError(_ERROR_UNKNOWN_SOURCE)
            resolved_sources = list(raw_value)

        if not resolved_sources:
            return None

        excluded_titles = list(saved_search.excluded_titles or [])
        radius_miles: float | None = None
        if saved_search.radius_miles is not None:
            radius_miles = float(saved_search.radius_miles)
            if not math.isfinite(radius_miles):
                raise QueryPlanValidationError(_ERROR_RADIUS_MILES_NOT_FINITE)
        salary_floor = saved_search.salary_floor
        employment_types = list(saved_search.employment_types or [])
        seniority = list(saved_search.seniority or [])
        posted_within_hours = saved_search.recency_limit_hours
        company_filter = list(saved_search.preferred_companies or [])
        excluded_companies = list(saved_search.excluded_companies or [])
        remote_ok = True if saved_search.remote_rules == "remote_only" else None

        field_values: dict[str, object] = {
            "titles": titles_out,
            "excluded_titles": excluded_titles,
            "locations": locations_out,
            "radius_miles": radius_miles,
            "salary_floor": salary_floor,
            "employment_types": employment_types,
            "seniority": seniority,
            "posted_within_hours": posted_within_hours,
            "company_filter": company_filter,
            "excluded_companies": excluded_companies,
            "remote_ok": remote_ok,
        }

        local_enforcement: dict[str, set[str]] = {}
        for source in resolved_sources:
            capabilities = provider_capabilities.sources[source]
            enforcement: set[str] = set()
            for field_name, value in field_values.items():
                if not _is_populated(field_name, value):
                    continue
                dedicated_attr = _DEDICATED_CAPABILITY_FIELDS.get(field_name)
                supported = (
                    getattr(capabilities, dedicated_attr)
                    if dedicated_attr is not None
                    else field_name in capabilities.supported_query_fields
                )
                if not supported:
                    enforcement.add(field_name)
            local_enforcement[source] = enforcement

        return SourceQuery(
            sources=resolved_sources,
            titles=titles_out,
            excluded_titles=excluded_titles,
            locations=locations_out,
            remote_ok=remote_ok,
            radius_miles=radius_miles,
            salary_floor=salary_floor,
            employment_types=employment_types,
            seniority=seniority,
            posted_within_hours=posted_within_hours,
            company_filter=company_filter,
            excluded_companies=excluded_companies,
            local_enforcement=local_enforcement,
        )
