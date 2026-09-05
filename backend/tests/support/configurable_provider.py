from collections.abc import Callable

from app.schemas.discovered_job import DiscoveryResult
from app.schemas.provider import ProviderCapabilities, ProviderHealth, SourceQuery


class ConfigurableProvider:
    """A purpose-built, fully configurable `DiscoveryProvider` test double
    for multi-provider orchestration tests.

    `FixtureProvider` cannot represent any of the scenarios these tests
    need: its `.name` is a fixed class attribute shared by every instance
    (so two instances can never represent two distinct *providers*), and
    `discover()` always synthesizes exactly one `completed=True`
    `SourceRunStats` regardless of the query (so it can never represent a
    malformed, partial, or failing result). This double exists so
    `FixtureProvider` itself is never distorted to fit scenarios it wasn't
    designed for — it stays exactly as-is, still used wherever a single
    clean, one-outcome success is all a test needs.

    Exactly one of `result`/`raise_on_discover` should be set per instance;
    `discover()` raises if neither is configured, since a test double with
    no configured outcome is a test-authoring mistake, not a legitimate
    default. `raise_on_discover` accepts `BaseException` (not just
    `Exception`) so a test can simulate `asyncio.CancelledError`, which is a
    `BaseException` subclass.
    """

    def __init__(
        self,
        name: str,
        *,
        capabilities: ProviderCapabilities,
        result: DiscoveryResult | None = None,
        raise_on_discover: BaseException | None = None,
        on_discover: Callable[[], None] | None = None,
    ) -> None:
        self.name = name
        self._capabilities = capabilities
        self._result = result
        self._raise_on_discover = raise_on_discover
        self._on_discover = on_discover
        self.discover_call_count = 0

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        self.discover_call_count += 1
        if self._on_discover is not None:
            self._on_discover()
        if self._raise_on_discover is not None:
            raise self._raise_on_discover
        if self._result is None:
            raise AssertionError(
                "ConfigurableProvider.discover() called with neither "
                "result= nor raise_on_discover= configured"
            )
        return self._result

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def health(self) -> ProviderHealth:
        raise NotImplementedError
