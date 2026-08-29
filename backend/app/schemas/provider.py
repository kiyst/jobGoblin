from datetime import datetime

from pydantic import BaseModel, Field


class SourceQuery(BaseModel):
    """What a provider is asked to do (docs/ARCHITECTURE.md §6.1). An empty
    `sources` list means "run this provider with zero sources" (don't call
    it), not "all sources" — that expansion is `QueryPlanner`'s job
    (deferred; this slice's callers construct `SourceQuery` directly).
    """

    sources: list[str] = Field(default_factory=list)

    titles: list[str] = Field(default_factory=list)
    excluded_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_ok: bool | None = None
    radius_miles: float | None = None
    salary_floor: int | None = None
    employment_types: list[str] = Field(default_factory=list)
    seniority: list[str] = Field(default_factory=list)
    posted_within_hours: int | None = None
    company_filter: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    max_results: int | None = None

    # Set by QueryPlanner (deferred), never by a caller directly in this slice.
    local_enforcement: dict[str, set[str]] = Field(default_factory=dict)


class SourceCapabilities(BaseModel):
    source: str
    supported_query_fields: set[str] = Field(default_factory=set)
    max_concurrency: int = Field(ge=1)
    requests_per_second: float | None = Field(default=None, gt=0)
    supports_salary_filter: bool = False
    supports_location_filter: bool = False
    supports_remote_filter: bool = False
    supports_posted_within_filter: bool = False


class ProviderCapabilities(BaseModel):
    provider: str
    sources: dict[str, SourceCapabilities] = Field(default_factory=dict)


class SourceHealth(BaseModel):
    source: str
    healthy: bool
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    detail: str | None


class ProviderHealth(BaseModel):
    provider: str
    healthy: bool
    sources: list[SourceHealth] = Field(default_factory=list)
    last_checked_at: datetime
