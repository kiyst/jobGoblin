"""Safe, guarded database routing for the migration/schema-change
verification matrix (Workflow v3.2 frozen contract).

Every command this module runs is routed to a validated disposable
target. The development URL is captured once, before any override, and
every target is validated against it via the *existing*
`scripts.db_safety` guards -- never a new, independently-drifting check.
Alembic subprocesses receive the validated target only through their own
process environment (`DATABASE_URL=<validated>`); the parent environment
is never mutated. A fresh database is created only through a derived
admin connection, owned exclusively by this run, and is dropped only when
this run can prove it created it.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

from scripts.db_safety import (
    _LOCAL_DESTRUCTIVE_LIFECYCLE_HOSTS,
    assert_is_disposable_test_database,
    assert_safe_for_local_destructive_lifecycle,
    redact_database_url,
    resolve_test_database_url,
)

_MAINTENANCE_DATABASE = "postgres"
_BACKEND_DIR = Path(__file__).resolve().parent.parent

# Deterministic, conservative repository-root-relative trigger paths (see
# scripts/verification_scope.py's is_migration_trigger, the single source
# of truth for classification -- these constants exist here only to name
# the exact, literal Alembic command argv arrays this matrix runs).
ALEMBIC_UPGRADE_HEAD = ["-m", "alembic", "-c", "alembic.ini", "upgrade", "head"]
ALEMBIC_DOWNGRADE_ONE = ["-m", "alembic", "-c", "alembic.ini", "downgrade", "-1"]
ALEMBIC_CHECK = ["-m", "alembic", "-c", "alembic.ini", "check"]


class MigrationMatrixError(Exception):
    """A migration-matrix safety invariant was violated -- fails closed,
    never silently degrades to a skip or a warning."""


def _to_asyncpg_dsn(sqlalchemy_url: str) -> str:
    """asyncpg's own `connect()` wants a plain `postgresql://` DSN, not the
    SQLAlchemy driver-qualified `postgresql+asyncpg://` form."""
    parsed = make_url(sqlalchemy_url)
    return parsed.set(drivername="postgresql").render_as_string(hide_password=False)


def derive_admin_url(target_url: str) -> str:
    """Same driver/username/password/host/port as `target_url`, with only
    the database component changed to the fixed maintenance database
    (`postgres`) -- never independently constructed."""
    parsed = make_url(target_url)
    return parsed.set(database=_MAINTENANCE_DATABASE).render_as_string(hide_password=False)


def _assert_admin_connection_local_and_non_production(admin_url: str, *, app_env: str) -> None:
    """The admin/maintenance connection's database name is, by Postgres
    convention, always `postgres` -- it correctly never contains a "test"
    marker, so `assert_is_disposable_test_database`'s name check does not
    apply to it. Only the target guard's *local-host/non-production*
    restrictions are required here, checked directly against the same
    closed host allowlist `assert_safe_for_local_destructive_lifecycle`
    itself uses -- never a second, independently-drifting copy."""
    if app_env == "production":
        raise RuntimeError(
            "Refusing to open an admin/maintenance database connection while APP_ENV=production."
        )
    host = (make_url(admin_url).host or "").lower()
    if host not in _LOCAL_DESTRUCTIVE_LIFECYCLE_HOSTS:
        raise RuntimeError(
            f"Refusing an admin/maintenance connection to {redact_database_url(admin_url)}: "
            f"host must be one of {sorted(_LOCAL_DESTRUCTIVE_LIFECYCLE_HOSTS)}, never a missing "
            "or remote host."
        )


def _require_identical_connection_components(target_url: str, admin_url: str) -> None:
    t = make_url(target_url)
    a = make_url(admin_url)
    if (t.drivername, t.username, t.password, t.host, t.port) != (
        a.drivername,
        a.username,
        a.password,
        a.host,
        a.port,
    ):
        raise MigrationMatrixError(
            "admin URL must share driver/username/password/host/port with the target URL"
        )


async def query_current_database(url: str) -> str:
    conn = await asyncpg.connect(_to_asyncpg_dsn(url))
    try:
        value: str = await conn.fetchval("SELECT current_database()")
        return value
    finally:
        await conn.close()


async def query_database_exists(admin_url: str, database_name: str) -> bool:
    conn = await asyncpg.connect(_to_asyncpg_dsn(admin_url))
    try:
        row = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database_name)
        return row is not None
    finally:
        await conn.close()


async def create_database(admin_url: str, database_name: str) -> None:
    conn = await asyncpg.connect(_to_asyncpg_dsn(admin_url))
    try:
        await conn.execute(f'CREATE DATABASE "{database_name}"')
    finally:
        await conn.close()


async def drop_database(admin_url: str, database_name: str) -> None:
    conn = await asyncpg.connect(_to_asyncpg_dsn(admin_url))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{database_name}"')
    finally:
        await conn.close()


async def capture_development_state(development_url: str) -> str:
    """Fail-closed: an unreachable development database, or one whose
    state cannot be read, is never treated as a skip -- it blocks the
    entire migration-matrix run for a schema-changing candidate."""
    try:
        return await query_current_database(development_url)
    except Exception as exc:  # noqa: BLE001 -- re-raised as a hard failure, never swallowed
        raise MigrationMatrixError(
            f"development database state could not be read: {type(exc).__name__} -- "
            "failing closed, no receipt/post-merge evidence may be issued"
        ) from exc


def generate_fresh_database_name() -> str:
    # Must contain "test" -- assert_is_disposable_test_database rejects any
    # database name that doesn't, regardless of how it will actually be used.
    return f"jobgoblin_test_verify_{uuid.uuid4().hex}"


@dataclass
class FreshDatabaseLifecycle:
    generated_name: str
    admin_url: str
    target_url: str
    present_before: bool = False
    created_by_this_run: bool = False
    present_after: bool = False
    cleaned_up: bool = False


async def provision_fresh_database(development_url: str, app_env: str) -> FreshDatabaseLifecycle:
    generated_name = generate_fresh_database_name()
    template = make_url(resolve_test_database_url(None))
    target_url = template.set(database=generated_name).render_as_string(hide_password=False)

    # 1. validate the generated target and admin connection
    assert_safe_for_local_destructive_lifecycle(target_url, development_url, app_env=app_env)
    admin_url = derive_admin_url(target_url)
    _require_identical_connection_components(target_url, admin_url)
    _assert_admin_connection_local_and_non_production(admin_url, app_env=app_env)

    lifecycle = FreshDatabaseLifecycle(
        generated_name=generated_name, admin_url=admin_url, target_url=target_url
    )

    # 2. prove pre-attempt absence
    lifecycle.present_before = await query_database_exists(admin_url, generated_name)
    if lifecycle.present_before:
        raise MigrationMatrixError(
            f"generated database name {generated_name!r} already exists -- refusing to touch it"
        )

    # 3. attempt CREATE DATABASE; 4. reconcile actual presence after any
    # success or exception (the acknowledgement-loss case).
    try:
        await create_database(admin_url, generated_name)
        lifecycle.created_by_this_run = True
    except Exception:
        lifecycle.present_after = await query_database_exists(admin_url, generated_name)
        if lifecycle.present_after and not lifecycle.present_before:
            lifecycle.created_by_this_run = True
        else:
            raise
    else:
        lifecycle.present_after = await query_database_exists(admin_url, generated_name)

    # 5. only now, connect directly to the created target and require
    # SELECT current_database() to equal the generated name, before any
    # Alembic command runs against it.
    if lifecycle.created_by_this_run:
        resolved = await query_current_database(target_url)
        if resolved != generated_name:
            # Unconditional cleanup before raising -- this run already owns
            # the database it just created; a validation failure past this
            # point must never leave it behind.
            await cleanup_fresh_database(lifecycle)
            raise MigrationMatrixError(
                f"direct connection to the created target resolved to {resolved!r}, "
                f"expected {generated_name!r} -- refusing to run migrations against it"
            )

    return lifecycle


async def cleanup_fresh_database(lifecycle: FreshDatabaseLifecycle) -> None:
    """Drops the generated database only when ownership is provable:
    absent before this run, matches this run's own generated identity,
    and found present afterward. A database present in the pre-attempt
    snapshot is never dropped, under any circumstance."""
    if not (
        not lifecycle.present_before and lifecycle.created_by_this_run and lifecycle.present_after
    ):
        return
    await drop_database(lifecycle.admin_url, lifecycle.generated_name)
    lifecycle.cleaned_up = True


def _run_alembic(args: list[str], database_url: str) -> None:
    """Runs one Alembic command with the validated target passed only
    through this one subprocess's own environment -- the parent process's
    environment (`os.environ`) is read from but never mutated."""
    env = {**os.environ, "DATABASE_URL": database_url}
    proc = subprocess.run(
        [sys.executable, *args], cwd=str(_BACKEND_DIR), env=env, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise MigrationMatrixError(
            f"alembic {' '.join(args[3:])} failed against "
            f"{redact_database_url(database_url)}: {proc.stderr.strip()[-2000:]}"
        )


@dataclass
class MatrixResult:
    status: str  # "PASS" | "FAIL"
    detail: str
    dev_state_before: str | None = None
    dev_state_after: str | None = None
    fresh_database_created: bool = False
    fresh_database_cleaned_up: bool = False
    steps: list[str] = field(default_factory=list)


async def run_full_matrix(
    development_url: str, existing_target_url: str, *, app_env: str
) -> MatrixResult:
    """The complete migration/schema-change verification matrix, run only
    when a candidate's diff actually triggers it
    (`verification_scope.is_migration_trigger`): existing-head upgrade,
    downgrade/upgrade round trip, `alembic check`, and a fresh `base ->
    head` run against a guarded, disposable database -- development
    database state is captured before and after and must be identical, or
    this raises (never returns a "FAIL" result silently; a raised
    exception here always means no receipt may be issued). Cleanup of the
    fresh database is unconditional, in `finally`."""
    steps: list[str] = []
    dev_before = await capture_development_state(development_url)
    steps.append("development state captured (before)")

    assert_is_disposable_test_database(existing_target_url, development_url)
    _run_alembic(ALEMBIC_UPGRADE_HEAD, existing_target_url)
    steps.append("existing-head upgrade")
    _run_alembic(ALEMBIC_DOWNGRADE_ONE, existing_target_url)
    steps.append("downgrade -1")
    _run_alembic(ALEMBIC_UPGRADE_HEAD, existing_target_url)
    steps.append("upgrade head (round trip restored)")
    _run_alembic(ALEMBIC_CHECK, existing_target_url)
    steps.append("alembic check")

    lifecycle = await provision_fresh_database(development_url, app_env)
    fresh_created = lifecycle.created_by_this_run
    try:
        _run_alembic(ALEMBIC_UPGRADE_HEAD, lifecycle.target_url)
        steps.append("fresh base -> head upgrade")
    finally:
        await cleanup_fresh_database(lifecycle)

    dev_after = await capture_development_state(development_url)
    steps.append("development state captured (after)")
    if dev_after != dev_before:
        raise MigrationMatrixError(
            "development database state changed during the migration matrix -- "
            f"before={dev_before!r} after={dev_after!r}"
        )

    return MatrixResult(
        status="PASS",
        detail=f"{len(steps)} steps completed",
        dev_state_before=dev_before,
        dev_state_after=dev_after,
        fresh_database_created=fresh_created,
        fresh_database_cleaned_up=lifecycle.cleaned_up,
        steps=steps,
    )
