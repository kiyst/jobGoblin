"""Local, read-only jobs API (Phase 4 S4;
`docs/DECISIONS/0019-local-read-only-jobs-api.md`).

`GET /jobs` and `GET /jobs/{job_id}` only. Thin routing and response mapping:
all queries and validation live in `app.services.job_read`.

Non-reflective by construction. Neither route declares a typed query or path
parameter that FastAPI could reject with its input-echoing 422; the raw values
are validated by the service and every failure maps to a fixed JSON error. An
unexpected failure inside a route is logged server-side (exception type only)
and answered with a fixed generic 500 body. A failure outside the route body
(dependency setup or teardown, response serialization) gets Starlette's
plain-text generic 500.

Unauthenticated and intended for localhost only: Docker Compose binds the port
to 127.0.0.1. Not an Internet- or LAN-facing API, with no user isolation.
"""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import JobReaderDep
from app.schemas.job_read import ErrorResponse, JobDetail, JobListPage
from app.services.job_read import (
    InvalidCursorError,
    InvalidQueryError,
    parse_job_id,
    parse_list_query,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["jobs"])


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def _job_not_found() -> JSONResponse:
    return _error(404, "job_not_found", "Job not found")


def _internal_error() -> JSONResponse:
    return _error(500, "internal_error", "Internal server error")


_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}


@router.get("/jobs", response_model=JobListPage, responses=_ERROR_RESPONSES)
async def list_jobs(request: Request, reader: JobReaderDep) -> JobListPage | JSONResponse:
    try:
        query = parse_list_query(request.query_params.multi_items())
    except InvalidQueryError:
        return _error(400, "invalid_query", "Invalid query parameters")
    except InvalidCursorError:
        return _error(400, "invalid_cursor", "Invalid pagination cursor")
    try:
        return await reader.list_jobs(query)
    except Exception as exc:
        # The exception type only: never its message, which could carry SQL,
        # paths, or submitted values.
        logger.error("jobs_list_failed exception_type=%s", type(exc).__name__)
        return _internal_error()


@router.get("/jobs/{job_id}", response_model=JobDetail, responses=_ERROR_RESPONSES)
async def get_job(job_id: str, reader: JobReaderDep) -> JobDetail | JSONResponse:
    parsed = parse_job_id(job_id)
    if parsed is None:
        return _job_not_found()
    try:
        detail = await reader.get_job(parsed)
    except Exception as exc:
        logger.error("jobs_detail_failed exception_type=%s", type(exc).__name__)
        return _internal_error()
    return detail if detail is not None else _job_not_found()
