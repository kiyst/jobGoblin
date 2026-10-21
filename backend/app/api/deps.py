"""Shared FastAPI dependencies (ARCHITECTURE.md §5: `api/` imports only
`services/` and `schemas/`).

Session acquisition for the jobs routes is owned by
`app.services.job_read.job_reader`, so no route module imports `app.db`
(`docs/DECISIONS/0019-local-read-only-jobs-api.md`).
"""

from typing import Annotated

from fastapi import Depends

from app.services.job_read import JobReader, job_reader

JobReaderDep = Annotated[JobReader, Depends(job_reader)]
