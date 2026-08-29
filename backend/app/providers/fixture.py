from collections.abc import Sequence
from datetime import datetime

from app.schemas.discovered_job import DiscoveredJob, DiscoveryResult, SourceRunStats
from app.schemas.provider import (
    ProviderCapabilities,
    ProviderHealth,
    SourceCapabilities,
    SourceHealth,
    SourceQuery,
)


class FixtureProvider:
    """Offline `DiscoveryProvider` (docs/ARCHITECTURE.md §11) returning a
    fixed, caller-supplied list of `DiscoveredJob`s — never reads a file or
    the network itself. Which fixtures a given call serves is decided at
    **construction** time (`fixtures=`), not by filtering `SourceQuery` —
    keeping "which records does this test exercise" separate from "what a
    real query looks like," per the approved slice's binding decision
    (point 10).

    `called_at` populates `DiscoveryResult.started_at`/`completed_at` only —
    nothing in this slice's pipeline reads either field; `observed_at`
    (Job/JobOccurrence business time) and the pipeline's own injected clock
    (run/attempt lifecycle time) are supplied independently by the caller,
    never derived from this provider.
    """

    name = "fixture_provider"

    def __init__(
        self,
        fixtures: Sequence[DiscoveredJob],
        *,
        called_at: datetime,
        source: str = "fixture_ats",
    ) -> None:
        self._fixtures = list(fixtures)
        self._called_at = called_at
        self._source = source

    async def discover(self, query: SourceQuery) -> DiscoveryResult:
        stats = [
            SourceRunStats(source=self._source, completed=True, jobs_found=len(self._fixtures))
        ]
        return DiscoveryResult(
            provider=self.name,
            jobs=self._fixtures,
            source_stats=stats,
            started_at=self._called_at,
            completed_at=self._called_at,
        )

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            sources={
                self._source: SourceCapabilities(source=self._source, max_concurrency=1),
            },
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name,
            healthy=True,
            sources=[
                SourceHealth(
                    source=self._source,
                    healthy=True,
                    last_success_at=None,
                    last_failure_at=None,
                    consecutive_failures=0,
                    detail=None,
                )
            ],
            last_checked_at=self._called_at,
        )
