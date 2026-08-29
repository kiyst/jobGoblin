from app.ingestion.natural_key import NaturalKey, resolve_natural_key
from app.normalization.url import normalize_url
from app.schemas.discovered_job import DiscoveredJob


class UnresolvableIdentityError(ValueError):
    """Raised when a `DiscoveredJob` carries no `source_job_id` and its
    `source_url` fails to normalize into a usable fallback key (ADR 0004's
    third natural-key form). Deliberately narrow: this is the *only*
    exception `ingestion/pipeline.py` catches and reroutes to
    `processing_status='parse_error'` — every other exception must
    propagate (docs binding decision, point 4/7 of the approved proposal).

    Persisting a `job_occurrences` row with neither `source_job_id` nor a
    usable `source_url_normalized` would be silently unenforceable: none of
    the three partial unique indexes can meaningfully key it (the two
    `source_job_id IS NOT NULL` indexes don't apply, and the URL-fallback
    index's own key column would itself be `NULL` — NULL is never distinct
    from NULL for uniqueness purposes, exactly the bug class ADR 0004's
    NULL-safety fix already exists to prevent). Raising here, before any
    insert is attempted, avoids ever relying on a database constraint that
    would not actually catch this case.
    """


def resolve_identity(job: DiscoveredJob) -> NaturalKey:
    """Canonicalizes and selects the natural-key form for `job`, per ADR
    0004's precedence order. Raises `UnresolvableIdentityError` if none of
    the three forms can be established."""
    source_url_normalized = normalize_url(job.source_url, provider=job.provider, source=job.source)
    natural_key = resolve_natural_key(
        job.provider,
        job.source,
        source_tenant_id=job.source_tenant_id,
        source_job_id=job.source_job_id,
        source_url_normalized=source_url_normalized,
    )
    if natural_key is None:
        raise UnresolvableIdentityError(
            f"no source_job_id and source_url {job.source_url!r} did not normalize into a "
            "usable fallback key — cannot derive any of the three ADR-0004 natural-key forms"
        )
    return natural_key
