# JobGoblin

Job aggregation and market-intelligence platform. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/DATA_MODEL.md](docs/DATA_MODEL.md), and [docs/ROADMAP.md](docs/ROADMAP.md) for the
full design. Before planning or reviewing a phase, use
[docs/PHASE_RISK_CHECKLIST.md](docs/PHASE_RISK_CHECKLIST.md) as its engineering preflight.
This repo has completed **Phase 0** (repository scaffolding only) — no domain models,
providers, or ingestion logic exist yet.

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

## Run tests

From `backend/`:

```bash
pytest
```

The database-unavailable test cases run unconditionally (no external
dependency). The database-*available* `/ready` test skips cleanly if no
PostgreSQL is reachable at `DATABASE_URL` — run `docker compose up -d
postgres` first to exercise it. No test contacts the public internet.

## Verification

One command that runs everything (formatting check, lint, type-check, tests) from `backend/`:

```bash
ruff format --check . && ruff check . && mypy app tests && pytest
```

PowerShell 7 (stops at the first failed check):

```powershell
ruff format --check . && ruff check . && mypy app tests && pytest
```

To also prove the full migration cycle against a real database:

```bash
docker compose up -d postgres
alembic upgrade head
alembic downgrade base
alembic upgrade head
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
