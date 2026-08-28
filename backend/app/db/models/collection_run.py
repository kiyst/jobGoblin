import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base

STATUSES = ("running", "completed", "completed_with_errors", "failed")
_TERMINAL_STATUSES = ("completed", "completed_with_errors", "failed")


class CollectionRun(Base):
    """Scheduler execution record, one row per saved-search execution
    (docs/DATA_MODEL.md's `collection_runs` section, §38).
    The parent aggregate over the future `collection_run_provider_attempts`
    table, which holds the authoritative per-`(provider, source)` detail —
    this table's own counters/`failures` are denormalized run-level
    rollups/summaries only, never the source of truth. Phase 2's offline
    fixture pipeline is the first writer; this Phase 1 slice only migrates
    the schema.

    `saved_search_id` is nullable with `ON DELETE SET NULL` — a run's
    history is a historical fact independent of whether the saved search
    that triggered it still exists, the same "audit trail must outlive its
    optional parent" reasoning already used for `raw_job_ingestions` and
    `identity_conflicts`. No other column's `CHECK` references this one's
    nullness, so unlike those two tables there is no FK-vs-CHECK asymmetric
    design tension here.

    `started_at` is NOT NULL with **no** server default: it represents the
    actual start of this run, supplied explicitly by the scheduler/pipeline
    code, not silently substituted — matching `raw_job_ingestions.
    fetched_at`'s treatment. `completed_at` is nullable only while
    `status = 'running'`; every terminal status requires it non-null (a
    `CHECK`, mirroring `collection_run_provider_attempts`' own already-
    documented status/`completed_at` consistency pattern). A second `CHECK`
    requires `completed_at >= started_at` when both are set, extending the
    ordering-`CHECK` convention already established on `job_occurrences`/
    `identity_conflicts`. `status` has no server default: fresh creation
    must explicitly supply `'running'` — there is no queued/pending state.

    `providers_attempted` (text[]) records providers whose execution
    actually began — **not** every provider merely planned. A provider
    rejected during `QueryPlanner` validation, with no `discover()` call
    ever made, is not "attempted" and must not appear here (see
    ARCHITECTURE.md §6.6's planning-time-failure case, recorded in
    `failures` below instead). Application code appends a provider name
    when its execution begins and is responsible for avoiding duplicates —
    no database uniqueness is enforced on array elements. NOT NULL,
    `server_default '{}'`, `MutableList`-wrapped so an in-place append to
    an already-loaded row is tracked by the unit of work.

    `providers_enforced_locally` (jsonb, shape `{provider: {source:
    [field, ...]}}` — ARCHITECTURE.md §6.6 step 6) is assembled in memory
    by `QueryPlanner` during planning and assigned as a complete value
    once planning finishes — **not** built up by repeated in-place
    mutation over the run's lifetime. NOT NULL, `server_default '{}'`,
    a `CHECK` requires a top-level JSON object. Deliberately **not**
    `MutableDict`-wrapped: nested in-place mutation (e.g.
    `run.providers_enforced_locally[provider][source].append(...)`) is
    not tracked and is silently lost on commit — callers must always
    assign a new complete value, the same limitation already documented
    for `jobs.field_provenance`.

    `failures` (jsonb array of `{provider, source, error}`) can
    legitimately accumulate at two different times within one run: a
    planning-time validation failure (before any provider call, per
    ARCHITECTURE.md §6.6 step 2) and an execution-time attempt failure —
    potentially across more than one write to the same row. NOT NULL,
    `server_default '[]'`, a `CHECK` requires a top-level JSON array,
    `MutableList`-wrapped so a top-level append is tracked. Each entry is
    treated as immutable once appended: nested dictionary mutation
    *within* an already-appended entry is not tracked (the same
    `MutableList`/`MutableDict` limitation as elsewhere in this schema) —
    correcting an entry requires replacing the whole list, not editing one
    entry in place. No `CHECK` ties `failures`' contents, or the three job
    counters below, to `status` — a `completed_with_errors` run may
    legitimately show accurate non-zero rollups from its successful
    sources alongside a non-empty `failures` array from its failed ones,
    mirroring `collection_run_provider_attempts`' own already-documented
    "no `CHECK` ties `error_category`/status" reasoning.

    `jobs_discovered`/`jobs_inserted`/`jobs_updated` are NOT NULL,
    `server_default 0`, each with a non-negative `CHECK` — the same
    counter convention already established on `collection_run_provider_
    attempts`. `duration_ms` stays freely nullable with a NULL-safe
    non-negative `CHECK`, independent of `status`.

    `created_at`/`updated_at` follow the established global convention —
    the same as `collection_run_provider_attempts`' own sibling columns,
    even though this table's own initial design note omitted them.
    """

    __tablename__ = "collection_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    saved_search_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("saved_searches.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    providers_attempted: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(ARRAY(Text)),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    providers_enforced_locally: Mapped[dict[str, object]] = mapped_column(
        JSONB(), nullable=False, server_default=text("'{}'::jsonb")
    )
    jobs_discovered: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    jobs_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failures: Mapped[list[object]] = mapped_column(
        MutableList.as_mutable(JSONB()),
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            f"status IN {STATUSES}",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) "
            f"OR (status IN {_TERMINAL_STATUSES} AND completed_at IS NOT NULL)",
            name="status_completed_at_consistency",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="completed_at_after_started_at",
        ),
        CheckConstraint(
            "jobs_discovered >= 0",
            name="jobs_discovered_non_negative",
        ),
        CheckConstraint(
            "jobs_inserted >= 0",
            name="jobs_inserted_non_negative",
        ),
        CheckConstraint(
            "jobs_updated >= 0",
            name="jobs_updated_non_negative",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="duration_ms_non_negative",
        ),
        CheckConstraint(
            "jsonb_typeof(providers_enforced_locally) = 'object'",
            name="providers_enforced_locally_is_object",
        ),
        CheckConstraint(
            "jsonb_typeof(failures) = 'array'",
            name="failures_is_array",
        ),
    )


Index(
    "ix_collection_runs_saved_search_id_started_at",
    CollectionRun.saved_search_id,
    CollectionRun.started_at.desc(),
)
Index("ix_collection_runs_status", CollectionRun.status)
