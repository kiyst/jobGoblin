# JobGoblin

Job aggregation and market-intelligence platform. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/DATA_MODEL.md](docs/DATA_MODEL.md), and [docs/ROADMAP.md](docs/ROADMAP.md) for the
full design. Before planning or reviewing a phase, use
[docs/PHASE_RISK_CHECKLIST.md](docs/PHASE_RISK_CHECKLIST.md) as its engineering preflight.
**Phase 0** (repository scaffolding) is complete. **Phase 1** is in progress: the `users`
table (model, migration, and database tests) is implemented and verified — see
[docs/ROADMAP.md](docs/ROADMAP.md) for exact status. No providers, ingestion, or other
Phase 1 tables exist yet.

## Requirements

- Python 3.12
- Docker + Docker Compose (for PostgreSQL; see below for running without it)

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"
cp ../.env.example ../.env    # adjust if needed
```

## Start PostgreSQL

```bash
docker compose up -d postgres
```

## Run migrations

From `backend/`, with the virtualenv active:

```bash
alembic upgrade head
```

To verify downgrade/upgrade both work cleanly (recommended after any migration change):

```bash
alembic downgrade base
alembic upgrade head
```

## Run the server

```bash
uvicorn app.main:app --reload
```

- `GET /health` — liveness only; always returns 200, never touches the database.
- `GET /ready` — readiness; returns 200 if PostgreSQL is reachable, 503 otherwise.

Or via Docker Compose (builds and runs the backend against the compose Postgres):

```bash
docker compose up -d
```

## Dedicated test database

Tests that create/drop schema or rows (`backend/tests/test_users.py`) run against a
**separate, disposable** PostgreSQL database — `jobgoblin_test` — never the ordinary
`jobgoblin` development database. This is enforced, not just documented:
`backend/tests/conftest.py::assert_is_disposable_test_database` raises a hard error
(fails the test, does not skip) if `TEST_DATABASE_URL` doesn't resolve to a database name
containing `test` and different from `jobgoblin`.

**One-time setup**, only needed once per `postgres_data` Docker volume:

```bash
docker exec <postgres-container-name> psql -U jobgoblin -d jobgoblin -c "CREATE DATABASE jobgoblin_test OWNER jobgoblin;"
```

The manual command above is what you need for an already-initialized `postgres_data`
volume (the normal case), since PostgreSQL only runs
`docker-entrypoint-initdb.d` scripts — including `postgres-init/01-create-test-db.sql`,
which creates `jobgoblin_test` automatically — on a *brand-new, empty* volume. This is
not something you need to do routinely: it only matters the first time you set up this
repo, or if you're deliberately creating a new environment from scratch.

**Do not run `docker compose down -v` to get a "fresh" volume for this.** That command
destroys the `postgres_data` volume entirely, including the `jobgoblin` **development**
database this whole test-isolation setup exists to protect. It is not a normal or
recommended part of test setup — the one-time manual `CREATE DATABASE` command above is
sufficient and non-destructive for the volume you already have.

Migrate the test database (separately from the development database — `DATABASE_URL` is
left untouched):

```bash
# bash
DATABASE_URL=postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test alembic upgrade head
```
```powershell
# PowerShell
$env:DATABASE_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test"
alembic upgrade head
Remove-Item Env:\DATABASE_URL
```

`TEST_DATABASE_URL` (see `.env.example`) defaults to exactly this database/URL, so no
further configuration is needed once it exists and is migrated.

**Migration round-trip verification** (upgrade/downgrade/upgrade) must only ever target
this test database, the same way:

```bash
DATABASE_URL=postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test alembic downgrade 0001
DATABASE_URL=postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test alembic upgrade head
```

## Run tests

From `backend/`:

```bash
pytest
```

The database-unavailable test cases run unconditionally (no external
dependency). The database-*available* `/ready` test skips cleanly if no
PostgreSQL is reachable at `DATABASE_URL` — run `docker compose up -d
postgres` first to exercise it. The `users`-table database tests
(`test_users.py`) require the dedicated test database above to exist and be
migrated to head — they fail (not skip) if it isn't reachable, and fail
closed with a clear error if pointed at the development database instead.
No test contacts the public internet.

## Verification

One command that runs everything (formatting check, lint, type-check, tests) from `backend/`:

```bash
ruff format --check . && ruff check . && mypy app tests scripts && pytest
```

PowerShell 7 (stops at the first failed check):

```powershell
ruff format --check . && ruff check . && mypy app tests scripts && pytest
```

### Repository consistency checker

A deterministic, offline, database-free check for documentation/migration drift —
broken markdown links and heading anchors, duplicate rows in `docs/DATA_MODEL.md`'s
constraints-summary table, stale Alembic revision references, and migration-chain
integrity. Run from `backend/` after any documentation or migration change:

```bash
python scripts/check_repo.py
```

Prints sorted `path:line: message` findings and exits non-zero if any are found. It is
also run as part of the ordinary `pytest` suite (`tests/test_check_repo.py`), so CI/local
test runs catch this drift without a separate step.

To also prove the full migration cycle against real PostgreSQL, use the **dedicated test
database** (see above) — never run destructive migration verification against the
development database:

```bash
docker compose up -d postgres
DATABASE_URL=postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test alembic upgrade head
DATABASE_URL=postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test alembic downgrade base
DATABASE_URL=postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test alembic upgrade head
```

## Project layout

```text
backend/
├── app/            # FastAPI application (see docs/ARCHITECTURE.md §4 for the full target layout)
├── migrations/      # Alembic
├── tests/
└── pyproject.toml
docs/               # Architecture, data model, roadmap, ADRs
docker-compose.yml
```
