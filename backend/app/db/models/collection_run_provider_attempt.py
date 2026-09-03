import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import Uuid

from app.db.base import Base

STATUSES = ("running", "completed", "partial", "failed")
_TERMINAL_STATUSES = ("completed", "partial", "failed")

# Reused verbatim from ARCHITECTURE.md §6.3's `ProviderErrorCategory` Python
# enum. Phase 2+ must keep this list synchronized with that enum by hand;
# adding a category requires a migration here, not just a Python release —
# see the class docstring.
ERROR_CATEGORIES = (
    "timeout",
    "rate_limited",
    "auth_error",
    "blocked",
    "parse_error",
    "not_found",
    "upstream_error",
    "unknown",
)

# Same four-character whitespace set as every other trim-only column in this
# project: space, tab, line feed, carriage return. Public (no leading
# underscore) and imported directly by `ingestion/pipeline.py`, which must
# normalize a Core-update `error_message` value identically to this model's
# own ORM validator and the database's `error_message_normalized`/
# `error_message_not_empty` CHECKs below — a private, module-local constant
# would invite a second, independently-drifting literal at that call site.
COVERED_WHITESPACE = " \t\n\r"


class CollectionRunProviderAttempt(Base):
    """One aggregate row per `(collection_run, provider, source)` — request-
    level telemetry for that source's execution within that run
    (docs/DATA_MODEL.md's `collection_run_provider_attempts` section;
    ARCHITECTURE.md §9; ADR 0005). Not one row per individual HTTP request
    or retry — `retry_count` *summarizes* retries within this one source's
    execution for this run. `CollectionRun` remains the parent aggregate
    over these rows: its own counters/`failures` are denormalized run-level
    rollups, this table holds the authoritative per-source detail. Phase
    2's offline fixture pipeline is the first writer; Phase 9 (the real
    scheduler) extends how this table is used rather than introducing it;
    Phase 12 reads its accumulated history for volume-trend/anomaly
    analysis. This Phase 1 slice only migrates the schema.

    `collection_run_id` is NOT NULL with `ON DELETE CASCADE` — unlike this
    schema's audit-trail FKs (`raw_job_ingestions`, `identity_conflicts` x2,
    `collection_runs.saved_search_id`, all `SET NULL`), an attempt row has
    no independent meaning without its parent run, so it is deleted
    alongside it. (`ON DELETE CASCADE` is not new to this schema — it is
    already used by `job_occurrences.job_id`, `candidate_skills.
    candidate_profile_id`, and the `saved_search_*` child tables; only the
    parent-table identity differs here.)

    `provider`/`source` are the same canonical identifiers as
    `job_occurrences`/`raw_job_ingestions`: lowercased/trimmed by the ORM,
    `CHECK`-restricted to an already-canonical, non-empty ASCII-slug value
    (`^[a-z0-9][a-z0-9._-]*$`) — they are join keys correlated across
    tables (Phase 12 reads this table per-`(provider, source)` alongside
    `raw_job_ingestions`/`job_occurrences`), not external raw data.

    `started_at` is NOT NULL with **no** server default — supplied
    explicitly by the attempt-recording code, matching `collection_runs.
    started_at`/`raw_job_ingestions.fetched_at`'s treatment. `completed_at`
    is nullable only while `status = 'running'`; every terminal status
    requires it non-null (a `CHECK`, the same bidirectional lifecycle
    pattern already established on `collection_runs.status`/`.completed_at`
    — this table's own version of it was already documented in
    DATA_MODEL.md before `collection_runs` was implemented). A second
    `CHECK` requires `completed_at >= started_at` when both are set,
    extending the ordering-`CHECK` convention already established on
    `job_occurrences`/`identity_conflicts`/`collection_runs`. `status` has
    no server default: fresh creation must explicitly supply `'running'`.

    `jobs_discovered`/`jobs_inserted`/`jobs_updated`/`retry_count` are NOT
    NULL, `server_default 0`, each with a non-negative `CHECK` — the same
    counter convention already established on `collection_runs`, now with
    a fourth counter (`retry_count`, summarizing retries within this one
    source's execution — see the cardinality note above).
    `rate_limited`/`incomplete_results` are NOT NULL booleans,
    `server_default false`, fully independent of each other and of
    `status` — a `status = 'partial'` row does not require
    `incomplete_results = true` at the database level (nor the reverse):
    ARCHITECTURE.md §9's own "Required Phase 1 database tests" for this
    table never mandates that pairing, and inventing one now would repeat
    the "don't enforce narrative/soft expectations with `CHECK`" mistake
    this table's docs already warn against for `error_category`/
    `error_message` below. Phase 2's application logic is responsible for
    the normal `incomplete_results = true` <-> `status = 'partial'`
    mapping in practice; the database does not require it.

    `error_category` is nullable text, nowhere case-folded or trimmed by
    the ORM (it is a plain closed-enum column like `status`, not free
    text) — `CHECK`-restricted to exactly the 8 values ARCHITECTURE.md
    §6.3's `ProviderErrorCategory` Python enum currently defines: `timeout`,
    `rate_limited`, `auth_error`, `blocked`, `parse_error`, `not_found`,
    `upstream_error`, `unknown`. **Phase 2+ must keep this list
    synchronized with that Python enum by hand** — adding a 9th category
    (e.g. if a future Phase 4/7 provider surfaces a genuinely new failure
    mode) requires a coordinated migration here, not merely a Python-side
    change. No `CHECK` ties `error_category` to `status`: a `status =
    'partial'` row does not require an error (a clean, truncated-but-
    successful pagination result is not an error condition); a `status =
    'failed'` row is expected, by application convention only, to populate
    it. `error_message` is nullable, case-preserving free text: trimmed by
    the ORM with a covered-whitespace-only value collapsed to `None` (the
    same `_NULLABLE_TEXT_COLUMNS` treatment as `raw_job_ingestions.
    error_message`), with a matching NULL-safe trim/non-empty `CHECK` pair.
    Sanitizing it against secrets/tokens/stack traces remains an
    application-level responsibility (per the cross-cutting non-negotiable
    in PHASE_RISK_CHECKLIST.md) — neither this trim `CHECK` nor any other
    database constraint proves sanitization occurred.

    `created_at`/`updated_at` follow the established global convention.
    """

    __tablename__ = "collection_run_provider_attempts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collection_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "collection_runs.id",
            ondelete="CASCADE",
            # Explicit, shortened name: the naming convention's full
            # template ("fk_collection_run_provider_attempts_collection_
            # run_id_collection_runs", 69 bytes) exceeds Postgres's 63-byte
            # identifier limit and would otherwise be silently truncated
            # with an auto-appended hash suffix.
            name="fk_collection_run_provider_attempts_collection_run",
        ),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    jobs_discovered: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    jobs_inserted: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    jobs_updated: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    rate_limited: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    error_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    incomplete_results: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
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
        UniqueConstraint("collection_run_id", "provider", "source"),
        CheckConstraint(
            f"status IN {STATUSES}",
            name="status_valid",
        ),
        CheckConstraint(
            "(status = 'running' AND completed_at IS NULL) "
            f"OR (status IN {_TERMINAL_STATUSES} AND completed_at IS NOT NULL)",
            # Shortened: the full "status_completed_at_consistency" suffix
            # would push the final name to 67 bytes.
            name="status_completed_at",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            # Shortened: the full "completed_at_after_started_at" suffix
            # would push the final name to 65 bytes.
            name="completed_after_started",
        ),
        CheckConstraint(
            "jobs_discovered >= 0",
            # Shortened: the full "jobs_discovered_non_negative" suffix
            # would push the final name to 64 bytes.
            name="jobs_discovered_nonneg",
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
            "retry_count >= 0",
            name="retry_count_non_negative",
        ),
        CheckConstraint(
            r"provider = lower(trim(both E'\t\n\r ' from provider))",
            name="provider_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from provider) <> ''",
            name="provider_not_empty",
        ),
        CheckConstraint(
            r"provider ~ '^[a-z0-9][a-z0-9._-]*$'",
            name="provider_slug_format",
        ),
        CheckConstraint(
            r"source = lower(trim(both E'\t\n\r ' from source))",
            name="source_normalized",
        ),
        CheckConstraint(
            r"trim(both E'\t\n\r ' from source) <> ''",
            name="source_not_empty",
        ),
        CheckConstraint(
            r"source ~ '^[a-z0-9][a-z0-9._-]*$'",
            name="source_slug_format",
        ),
        CheckConstraint(
            f"error_category IS NULL OR error_category IN {ERROR_CATEGORIES}",
            name="error_category_valid",
        ),
        CheckConstraint(
            r"error_message IS NULL OR error_message = trim(both E'\t\n\r ' from error_message)",
            name="error_message_normalized",
        ),
        CheckConstraint(
            r"error_message IS NULL OR trim(both E'\t\n\r ' from error_message) <> ''",
            name="error_message_not_empty",
        ),
    )

    @validates("provider", "source")
    def _normalize_canonical_identifier(self, _key: str, value: str) -> str:
        """Trims `COVERED_WHITESPACE` and lowercases — same canonical-
        identifier treatment as `job_occurrences`/`raw_job_ingestions`."""
        return value.strip(COVERED_WHITESPACE).lower()

    @validates("error_message")
    def _normalize_nullable_text(self, _key: str, value: str | None) -> str | None:
        """Trims `COVERED_WHITESPACE` and converts a covered-whitespace-
        only value to `None` rather than failing ingestion. Case preserved
        — sanitization against secrets/tokens is a separate, application-
        level responsibility, not performed here."""
        if value is None:
            return None
        trimmed = value.strip(COVERED_WHITESPACE)
        return trimmed or None


# Phase 12's volume-trend query — "give me this source's jobs_discovered
# over time."
Index(
    "ix_collection_run_provider_attempts_provider_source_started_at",
    CollectionRunProviderAttempt.provider,
    CollectionRunProviderAttempt.source,
    CollectionRunProviderAttempt.started_at.desc(),
)
# PostgreSQL does not automatically index a referencing foreign-key
# column, so this index is added explicitly to support "all attempts for
# this run" lookups (and efficient parent-side FK-maintenance lookups on
# `collection_runs` deletes).
Index(
    "ix_collection_run_provider_attempts_collection_run_id",
    CollectionRunProviderAttempt.collection_run_id,
)
