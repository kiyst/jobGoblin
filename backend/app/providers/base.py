from typing import Protocol

from app.schemas.discovered_job import DiscoveryResult
from app.schemas.provider import ProviderCapabilities, ProviderHealth, SourceQuery


class DiscoveryProvider(Protocol):
    """The one interface every provider adapter implements
    (docs/ARCHITECTURE.md §6.4). `discover()` is only allowed to raise for
    genuine programmer errors (e.g. a malformed `SourceQuery`) — any
    anticipated-but-uncontrollable failure is reported *in* the returned
    `DiscoveryResult` (`errors`/`source_stats`), never by raising past this
    boundary.

    Provider-independent value objects (`DiscoveredJob`, `DiscoveryResult`,
    `SourceQuery`, `SourceCapabilities`, etc.) live in `app/schemas/`, not
    here — this module holds only the provider-facing contract itself.
    """

    name: str

    async def discover(self, query: SourceQuery) -> DiscoveryResult: ...
    def capabilities(self) -> ProviderCapabilities: ...
    async def health(self) -> ProviderHealth: ...
