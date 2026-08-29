from datetime import UTC, datetime

import pytest

from app.schemas.discovered_job import (
    DiscoveredJob,
    DiscoveryResult,
    ProviderError,
    ProviderErrorCategory,
    SourceRunStats,
)
from app.schemas.provider import SourceCapabilities, SourceQuery

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _minimal_job(source: str = "fixture_ats") -> DiscoveredJob:
    return DiscoveredJob(
        provider="fixture_provider",
        source=source,
        source_tenant_id=None,
        source_job_id="1",
        requisition_id_raw=None,
        title=None,
        company=None,
        location=None,
        source_url="https://example.com/1",
        apply_url=None,
        canonical_url=None,
        description=None,
        compensation_text=None,
        posted_at=None,
        discovered_at=_NOW,
    )


def _stats(
    source: str = "fixture_ats", *, completed: bool = True, jobs_found: int = 0
) -> SourceRunStats:
    return SourceRunStats(source=source, completed=completed, jobs_found=jobs_found)


# --------------------------------------------------------------------------
# Mutable-default isolation
# --------------------------------------------------------------------------


def test_source_query_mutable_defaults_are_isolated_between_instances() -> None:
    a = SourceQuery()
    b = SourceQuery()
    a.sources.append("x")
    a.local_enforcement["p"] = {"salary_floor"}
    assert b.sources == []
    assert b.local_enforcement == {}


def test_discovered_job_raw_default_is_isolated_between_instances() -> None:
    a = _minimal_job()
    b = _minimal_job()
    a.raw["leaked"] = True
    assert b.raw == {}


def test_discovery_result_list_defaults_are_isolated_between_instances() -> None:
    a = DiscoveryResult(
        provider="fixture_provider", source_stats=[_stats()], started_at=_NOW, completed_at=_NOW
    )
    b = DiscoveryResult(
        provider="fixture_provider", source_stats=[_stats()], started_at=_NOW, completed_at=_NOW
    )
    a.warnings.append("leaked")
    assert b.warnings == []


def test_source_capabilities_supported_query_fields_set_is_isolated() -> None:
    a = SourceCapabilities(source="fixture_ats", max_concurrency=1)
    b = SourceCapabilities(source="fixture_ats", max_concurrency=1)
    a.supported_query_fields.add("salary_floor")
    assert b.supported_query_fields == set()


# --------------------------------------------------------------------------
# DiscoveryResult validation
# --------------------------------------------------------------------------


def test_duplicate_source_names_in_source_stats_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate source names"):
        DiscoveryResult(
            provider="fixture_provider",
            source_stats=[_stats("a"), _stats("a")],
            started_at=_NOW,
            completed_at=_NOW,
        )


def test_error_source_with_no_matching_source_stats_entry_rejected() -> None:
    with pytest.raises(ValueError, match="ProviderError.source with no matching"):
        DiscoveryResult(
            provider="fixture_provider",
            source_stats=[_stats("a")],
            errors=[
                ProviderError(
                    source="b",
                    category=ProviderErrorCategory.UNKNOWN,
                    retryable=False,
                    detail=None,
                    occurred_at=_NOW,
                )
            ],
            started_at=_NOW,
            completed_at=_NOW,
        )


def test_job_source_with_no_matching_source_stats_entry_rejected() -> None:
    with pytest.raises(ValueError, match="DiscoveredJob.source with no matching"):
        DiscoveryResult(
            provider="fixture_provider",
            jobs=[_minimal_job(source="b")],
            source_stats=[_stats("a", jobs_found=0)],
            started_at=_NOW,
            completed_at=_NOW,
        )


def test_completed_false_with_nonzero_jobs_found_rejected() -> None:
    with pytest.raises(ValueError, match="completed=False must have jobs_found=0"):
        DiscoveryResult(
            provider="fixture_provider",
            source_stats=[_stats("a", completed=False, jobs_found=1)],
            started_at=_NOW,
            completed_at=_NOW,
        )


# --------------------------------------------------------------------------
# Derived properties
# --------------------------------------------------------------------------


def test_requested_and_completed_sources_and_possibly_incomplete() -> None:
    result = DiscoveryResult(
        provider="fixture_provider",
        source_stats=[
            _stats("healthy", completed=True, jobs_found=3),
            _stats("broken", completed=False, jobs_found=0),
        ],
        started_at=_NOW,
        completed_at=_NOW,
    )
    assert result.requested_sources == ["healthy", "broken"]
    assert result.completed_sources == ["healthy"]
    assert result.possibly_incomplete is True


def test_all_completed_no_errors_is_not_possibly_incomplete() -> None:
    result = DiscoveryResult(
        provider="fixture_provider",
        source_stats=[_stats("healthy", completed=True, jobs_found=3)],
        started_at=_NOW,
        completed_at=_NOW,
    )
    assert result.possibly_incomplete is False


def test_incomplete_results_flag_alone_makes_possibly_incomplete_true() -> None:
    stats = SourceRunStats(source="healthy", completed=True, jobs_found=3, incomplete_results=True)
    result = DiscoveryResult(
        provider="fixture_provider", source_stats=[stats], started_at=_NOW, completed_at=_NOW
    )
    assert result.possibly_incomplete is True
