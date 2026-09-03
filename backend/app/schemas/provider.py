from datetime import datetime

from pydantic import BaseModel, Field


class SourceQuery(BaseModel):
    """What a provider is asked to do (docs/ARCHITECTURE.md §6.1). An empty
    `sources` list means "run this provider with zero sources" (don't call
    it), not "all sources" — that expansion is `QueryPlanner.plan()`'s job
    (`app/discovery/query_planner.py` — implemented). What remains deferred
    is wiring it into `ingestion/pipeline.py`'s own call sites: nothing in
    this codebase yet calls `plan()` automatically, so a caller may still
    construct a `SourceQuery` directly instead, exactly as every current
    test does.
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

    # Set by `QueryPlanner.plan()` (implemented) when a caller uses it; a
    # caller constructing `SourceQuery` directly instead must populate this
    # itself if it wants enforcement tracked — nothing does so automatically
    # yet, since `plan()` is not wired into `ingestion/pipeline.py`.
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
