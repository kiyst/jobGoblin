from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Supplies run/attempt **lifecycle** timestamps (`CollectionRun`/
    `CollectionRunProviderAttempt` `started_at`/`completed_at`, and duration
    calculations) — deliberately independent of `observed_at`, the
    business timestamp callers supply for `Job`/`JobOccurrence` (docs
    binding decision, point 6). Conflating the two would make a test unable
    to hold "when did this run execute" and "what does this payload claim
    to observe" as independently controllable facts — e.g. a real-time
    backfill replaying a months-old `observed_at` through a pipeline that
    executes right now.
    """

    def now(self) -> datetime: ...


class SystemClock:
    """Real wall-clock time, UTC-aware. Used outside tests."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Deterministic clock for tests: returns a fixed instant, advanceable
    explicitly via `advance()`. Never derives time from the real system
    clock, so run-duration assertions are exact and reproducible."""

    def __init__(self, initial: datetime) -> None:
        self._current = initial

    def now(self) -> datetime:
        return self._current

    def advance(self, delta_seconds: float) -> None:
        self._current = self._current + timedelta(seconds=delta_seconds)
