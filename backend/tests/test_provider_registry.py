import uuid

import pytest

from app.db.models.saved_search import SavedSearch
from app.discovery.query_planner import QueryPlanner
from app.providers.registry import (
    ProviderRegistrationError,
    ProviderRegistry,
    UnknownProviderError,
)
from app.schemas.discovered_job import DiscoveryResult
from app.schemas.provider import (
    ProviderCapabilities,
    ProviderHealth,
    SourceCapabilities,
    SourceQuery,
)

_UNSET = object()


class _FakeProvider:
    """Minimal `DiscoveryProvider` test double. Registry tests only exercise
    `.name`/`.capabilities()`; `discover()`/`health()` are never called here
    and exist only to satisfy the structural protocol."""

    def __init__(
        self,
        name: str,
        *,
        source: str = "fixture_ats",
        capabilities_provider: str | None = None,
        capabilities_error: Exception | None = None,
        capabilities_return_override: object = _UNSET,
    ) -> None:
        self.name = name
        self._source = source
        self._capabilities_provider = (
            capabilities_provider if capabilities_provider is not None else name
        )
        self._capabilities_error = capabilities_error
        self._capabilities_return_override = capabilities_return_override
        self.capabilities_call_count = 0

    def capabilities(self) -> ProviderCapabilities:
        self.capabilities_call_count += 1
        if self._capabilities_error is not None:
            raise self._capabilities_error
        if self._capabilities_return_override is not _UNSET:
            return self._capabilities_return_override  # type: ignore[return-value]
        return ProviderCapabilities(
            provider=self._capabilities_provider,
            sources={self._source: SourceCapabilities(source=self._source, max_concurrency=1)},
        )

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        raise NotImplementedError

    async def health(self) -> ProviderHealth:
        raise NotImplementedError


def _saved_search(**overrides: object) -> SavedSearch:
    """An in-memory-only `SavedSearch` — never persisted, never queried.
    Mirrors `tests/test_query_planner.py`'s own helper of the same shape."""
    defaults: dict[str, object] = {
        "user_id": uuid.uuid4(),
        "name": "Backend roles",
        "remote_rules": "any",
        "polling_schedule": "manual",
    }
    defaults.update(overrides)
    return SavedSearch(**defaults)


# ---------------------------------------------------------------------------
# Empty registry, ordering, successful lookup.
# ---------------------------------------------------------------------------


def test_empty_registry_has_no_names_and_rejects_any_lookup() -> None:
    registry = ProviderRegistry([])
    assert registry.names() == []
    with pytest.raises(UnknownProviderError):
        registry.get("anything")


def test_names_are_alphabetically_sorted_independent_of_registration_order() -> None:
    registry = ProviderRegistry(
        [_FakeProvider("zeta"), _FakeProvider("alpha"), _FakeProvider("mid")]
    )
    assert registry.names() == ["alpha", "mid", "zeta"]


def test_successful_lookup_returns_the_same_provider_instance() -> None:
    provider = _FakeProvider("fixture_provider")
    registry = ProviderRegistry([provider])
    resolved = registry.get("fixture_provider")
    assert resolved.provider is provider
    assert resolved.capabilities.provider == "fixture_provider"


# ---------------------------------------------------------------------------
# Fail-closed construction: duplicates, invalid slugs, capabilities mismatch,
# capabilities() exceptions.
# ---------------------------------------------------------------------------


def test_duplicate_provider_name_is_rejected() -> None:
    with pytest.raises(ProviderRegistrationError):
        ProviderRegistry([_FakeProvider("fixture_provider"), _FakeProvider("fixture_provider")])


@pytest.mark.parametrize(
    "invalid_name",
    [
        "Invalid_Name",
        "fixture_provider\n",
        "fixture_provider\r\n",
    ],
)
def test_invalid_provider_slug_is_rejected(invalid_name: str) -> None:
    with pytest.raises(ProviderRegistrationError):
        ProviderRegistry([_FakeProvider(invalid_name)])


def test_capabilities_provider_mismatch_is_rejected() -> None:
    with pytest.raises(ProviderRegistrationError):
        ProviderRegistry([_FakeProvider("alpha", capabilities_provider="beta")])


def test_capabilities_exception_is_sanitized() -> None:
    provider = _FakeProvider("alpha", capabilities_error=RuntimeError("leak-me secret-token-xyz"))
    with pytest.raises(ProviderRegistrationError) as excinfo:
        ProviderRegistry([provider])
    message = str(excinfo.value)
    assert "leak-me" not in message
    assert "secret-token-xyz" not in message


def test_capabilities_returning_a_malformed_value_is_rejected_not_a_raw_attribute_error() -> None:
    """`capabilities()`'s declared return type isn't runtime-enforced — a
    buggy adapter returning `None` (or anything else with no `.provider`
    attribute) must still fail closed with the same sanitized
    `ProviderRegistrationError`, never a raw `AttributeError` escaping the
    registry."""
    provider = _FakeProvider("alpha", capabilities_return_override=None)
    with pytest.raises(ProviderRegistrationError):
        ProviderRegistry([provider])


# ---------------------------------------------------------------------------
# Capabilities snapshot: called once, read-isolated.
# ---------------------------------------------------------------------------


def test_capabilities_is_called_exactly_once_on_successful_registration() -> None:
    provider = _FakeProvider("alpha")
    registry = ProviderRegistry([provider])
    assert provider.capabilities_call_count == 1
    registry.get("alpha")
    registry.get("alpha")
    assert provider.capabilities_call_count == 1


def test_mutating_a_resolved_capabilities_snapshot_does_not_mutate_the_registry() -> None:
    registry = ProviderRegistry([_FakeProvider("alpha", source="fixture_ats")])
    first = registry.get("alpha")
    first.capabilities.sources["fixture_ats"].max_concurrency = 999
    first.capabilities.sources["new_source"] = SourceCapabilities(
        source="new_source", max_concurrency=1
    )

    second = registry.get("alpha")
    assert second.capabilities.sources["fixture_ats"].max_concurrency == 1
    assert "new_source" not in second.capabilities.sources


# ---------------------------------------------------------------------------
# Name drift, detected only at resolution.
# ---------------------------------------------------------------------------


def test_provider_name_drift_after_registration_is_detected_on_resolution() -> None:
    provider = _FakeProvider("alpha")
    registry = ProviderRegistry([provider])
    provider.name = "beta"  # a real DiscoveryProvider is not assumed immutable
    with pytest.raises(ProviderRegistrationError):
        registry.get("alpha")


# ---------------------------------------------------------------------------
# Unknown-name errors never leak the requested name.
# ---------------------------------------------------------------------------


def test_unknown_provider_error_does_not_contain_the_requested_name() -> None:
    registry = ProviderRegistry([_FakeProvider("alpha")])
    distinctive_name = "distinctive-unregistered-name-xyz"
    with pytest.raises(UnknownProviderError) as excinfo:
        registry.get(distinctive_name)
    assert distinctive_name not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Compatibility: a resolved snapshot is directly consumable by QueryPlanner,
# offline, with no database or network access — the real current consumer.
# ---------------------------------------------------------------------------


def test_resolved_capabilities_snapshot_feeds_query_planner() -> None:
    registry = ProviderRegistry([_FakeProvider("fixture_provider", source="fixture_ats")])
    resolved = registry.get("fixture_provider")

    saved_search = _saved_search(enabled_sources=None)
    result = QueryPlanner.plan(
        saved_search, resolved.capabilities, titles=["Engineer"], locations=[]
    )

    assert result is not None
    assert result.sources == ["fixture_ats"]
