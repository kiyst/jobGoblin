"""Response models for the local, read-only jobs API (Phase 4 S4;
`docs/DECISIONS/0019-local-read-only-jobs-api.md`).

Each model exposes exactly the fields ADR 0019 allows and forbids any other
(`extra="forbid"`), so adding a field is a deliberate contract change. An absent
value is JSON `null`; clients render it as "not listed". `null` does not say
whether a parser abstained or the field was never normalized.

Imports only the standard library and Pydantic (ARCHITECTURE.md §5).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CompanyRef(_Strict):
    id: uuid.UUID
    name: str


class JobListItem(_Strict):
    id: uuid.UUID
    title: str | None
    company: CompanyRef | None
    location_raw: str | None
    country: str | None
    employment_type: str | None
    seniority: str | None
    canonical_url: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    active: bool


class OccurrenceOut(_Strict):
    provider: str
    source: str
    source_url: str
    apply_url: str | None
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime


class JobDetail(JobListItem):
    description_clean: str | None
    occurrences: list[OccurrenceOut]


class JobListPage(_Strict):
    items: list[JobListItem]
    next_cursor: str | None


class ErrorDetail(_Strict):
    code: str
    message: str


class ErrorResponse(_Strict):
    error: ErrorDetail
