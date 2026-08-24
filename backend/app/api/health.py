import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.config import Settings, get_settings
from app.db.session import check_database_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Process liveness only. Must succeed even if PostgreSQL is unreachable.

    Deliberately does not import or touch anything database-related — a
    liveness probe answers "is the process alive and able to respond," not
    "are its dependencies healthy." Mixing the two would make an orchestrator
    kill and restart a perfectly healthy process just because the database
    happened to be temporarily down, which would not fix anything.
    """
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    response: Response, settings: Annotated[Settings, Depends(get_settings)]
) -> dict[str, str]:
    """Readiness: process is alive AND its database dependency is reachable.

    Returns 503 (not a raised exception surfaced as 500) when the database is
    unavailable — this is an expected, well-defined outcome, not a server
    error. The failure detail is never included in the response body: only a
    generic status, so nothing about the database host, credentials, or
    driver-level error text can leak to a caller.

    `settings` is injected via `Depends` (rather than called directly)
    specifically so tests can override it with `app.dependency_overrides` to
    point at an unreachable database without touching real configuration.
    """
    try:
        await check_database_connection(settings)
    except Exception:
        logger.warning("readiness check failed: database unreachable")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ok"}
