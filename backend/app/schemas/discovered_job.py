from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DiscoveredJob(BaseModel):
    """Universal per-posting output every `DiscoveryProvider` must produce
    (docs/ARCHITECTURE.md §6.2). `raw` is the provider-specific payload,
    preserved for `RawJobIngestion.raw_payload` — see
    `app/ingestion/hashing.py` for why this is a value/structure-preserving
    representation, not a byte-preserving one, once it round-trips through
    JSONB.
    """

    provider: str
    source: str
    source_tenant_id: str | None
    source_job_id: str | None
    requisition_id_raw: str | None

    title: str | None
    company: str | None
    location: str | None

    source_url: str
    apply_url: str | None
    canonical_url: str | None

    description: str | None
    compensation_text: str | None

    posted_at: datetime | None
    discovered_at: datetime

    raw: dict[str, Any] = Field(default_factory=dict)


class ProviderErrorCategory(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    BLOCKED = "blocked"
    PARSE_ERROR = "parse_error"
    NOT_FOUND = "not_found"
    UPSTREAM_ERROR = "upstream_error"
    UNKNOWN = "unknown"


class ProviderError(BaseModel):
    source: str
    category: ProviderErrorCategory
    retryable: bool
    detail: str | None
    occurred_at: datetime


class SourceRunStats(BaseModel):
    source: str
    completed: bool
    jobs_found: int
    incomplete_results: bool = False
    duration_ms: int | None = None
    rate_limited: bool = False
    retry_count: int = 0


class DiscoveryResult(BaseModel):
    """What a provider call actually returns (docs/ARCHITECTURE.md §6.3).
    `source_stats` is the single source of truth; `requested_sources`/
    `completed_sources`/`possibly_incomplete` are derived so they cannot
    drift out of sync with it by construction. Every `SourceQuery.sources`
    entry appearing exactly once in `source_stats` is enforced by the
    caller (`ingestion/pipeline.py`), not by this model — a single
    `DiscoveryResult` has no access to the originating `SourceQuery`.
    """

    provider: str
    jobs: list[DiscoveredJob] = Field(default_factory=list)
    source_stats: list[SourceRunStats] = Field(default_factory=list)
    errors: list[ProviderError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    started_at: datetime
    completed_at: datetime

    @property
    def requested_sources(self) -> list[str]:
        return [s.source for s in self.source_stats]

    @property
    def completed_sources(self) -> list[str]:
        return [s.source for s in self.source_stats if s.completed]

    @property
    def possibly_incomplete(self) -> bool:
        return (
            bool(self.errors)
            or any(not s.completed for s in self.source_stats)
            or any(s.incomplete_results for s in self.source_stats)
        )

    @model_validator(mode="after")
    def _check_consistency(self) -> "DiscoveryResult":
        sources = [s.source for s in self.source_stats]
        if len(sources) != len(set(sources)):
            raise ValueError("duplicate source names in source_stats")
        error_sources = {e.source for e in self.errors}
        if not error_sources <= set(sources):
            raise ValueError("ProviderError.source with no matching source_stats entry")
        job_sources = {j.source for j in self.jobs}
        if not job_sources <= set(sources):
            raise ValueError("DiscoveredJob.source with no matching source_stats entry")
        for s in self.source_stats:
            if not s.completed and s.jobs_found != 0:
                raise ValueError(
                    f"{s.source}: completed=False must have jobs_found=0 — a source "
                    "that returned any jobs is completed=True, incomplete_results=True"
                )
        return self
