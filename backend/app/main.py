from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.jobs import router as jobs_router


def create_app() -> FastAPI:
    """Application factory.

    Registers the health/readiness router and Phase 4 S4's local, read-only
    jobs router (docs/DECISIONS/0019-local-read-only-jobs-api.md). The Phase 8
    feed, searches, and user workspace routes do not exist yet.
    """
    app = FastAPI(title="JobGoblin", version="0.1.0")
    app.include_router(health_router)
    app.include_router(jobs_router)
    return app


app = create_app()
