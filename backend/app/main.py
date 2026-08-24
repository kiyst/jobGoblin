from fastapi import FastAPI

from app.api.health import router as health_router


def create_app() -> FastAPI:
    """Application factory.

    Phase 0 registers only the health/readiness router — no domain routers
    exist yet (see docs/ROADMAP.md; API routes for jobs/searches/etc. arrive
    in Phase 8).
    """
    app = FastAPI(title="JobGoblin", version="0.1.0")
    app.include_router(health_router)
    return app


app = create_app()
