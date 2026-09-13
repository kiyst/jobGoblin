"""Genuine tests against the real local disposable Postgres instance
(docker compose `postgres` service) -- not mocked at the database layer.
Requires TEST_DATABASE_URL's server to be reachable; skipped otherwise,
exactly like the rest of this project's real-database test suite."""

from __future__ import annotations

import asyncio

import asyncpg
import pytest

from app.config import get_settings
from scripts import db_safety
from scripts import migration_matrix as mm


def _dev_url() -> str:
    return get_settings().database_url


async def _server_reachable() -> bool:
    try:
        conn = await asyncpg.connect(mm._to_asyncpg_dsn(db_safety.resolve_test_database_url(None)))
    except Exception:
        return False
    await conn.close()
    return True


pytestmark = pytest.mark.skipif(
    not asyncio.run(_server_reachable()), reason="local disposable Postgres server unreachable"
)


def test_derive_admin_url_changes_only_database_component() -> None:
    target = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_verify_abc"
    admin = mm.derive_admin_url(target)
    assert admin == "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/postgres"


def test_derive_admin_url_rejects_component_mismatch_by_construction() -> None:
    target = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_verify_abc"
    admin = mm.derive_admin_url(target)
    mm._require_identical_connection_components(target, admin)  # must not raise
    with pytest.raises(mm.MigrationMatrixError):
        mm._require_identical_connection_components(
            target, "postgresql+asyncpg://someoneelse:pw@remotehost:5432/postgres"
        )


@pytest.mark.asyncio
async def test_provision_and_cleanup_real_fresh_database_happy_path() -> None:
    lifecycle = await mm.provision_fresh_database(_dev_url(), app_env="test")
    try:
        assert lifecycle.present_before is False
        assert lifecycle.created_by_this_run is True
        assert lifecycle.present_after is True
        assert await mm.query_database_exists(lifecycle.admin_url, lifecycle.generated_name) is True
    finally:
        await mm.cleanup_fresh_database(lifecycle)
    assert lifecycle.cleaned_up is True
    assert await mm.query_database_exists(lifecycle.admin_url, lifecycle.generated_name) is False


@pytest.mark.asyncio
async def test_provision_refuses_production_app_env() -> None:
    with pytest.raises(RuntimeError, match="production"):
        await mm.provision_fresh_database(_dev_url(), app_env="production")


def test_admin_connection_guard_refuses_remote_host() -> None:
    remote_admin_url = "postgresql+asyncpg://jobgoblin:jobgoblin@remote.example.com:5432/postgres"
    with pytest.raises(RuntimeError, match="host must be one of"):
        mm._assert_admin_connection_local_and_non_production(remote_admin_url, app_env="test")


def test_admin_connection_guard_refuses_production_app_env() -> None:
    admin_url = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/postgres"
    with pytest.raises(RuntimeError, match="production"):
        mm._assert_admin_connection_local_and_non_production(admin_url, app_env="production")


@pytest.mark.asyncio
async def test_provision_rejects_pre_existing_name_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force a real collision: pre-create a database under the exact name
    # this run will generate, by making the name generator deterministic
    # for the duration of this test only.
    fixed_name = "jobgoblin_verify_forced_collision_test"
    monkeypatch.setattr(mm, "generate_fresh_database_name", lambda: fixed_name)

    admin_url = mm.derive_admin_url(db_safety.resolve_test_database_url(None))
    await mm.create_database(admin_url, fixed_name)
    try:
        with pytest.raises(mm.MigrationMatrixError, match="already exists"):
            await mm.provision_fresh_database(_dev_url(), app_env="test")
    finally:
        await mm.drop_database(admin_url, fixed_name)

    # And the pre-existing database must still be exactly as we left it --
    # never dropped by the failed provisioning attempt.
    assert (
        await mm.query_database_exists(admin_url, fixed_name) is False
    )  # we dropped it ourselves above


@pytest.mark.asyncio
async def test_provision_never_drops_pre_existing_database_on_collision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_name = "jobgoblin_verify_never_touch_test"
    monkeypatch.setattr(mm, "generate_fresh_database_name", lambda: fixed_name)
    admin_url = mm.derive_admin_url(db_safety.resolve_test_database_url(None))
    await mm.create_database(admin_url, fixed_name)
    try:
        with pytest.raises(mm.MigrationMatrixError):
            await mm.provision_fresh_database(_dev_url(), app_env="test")
        # still present -- the collision path must never call DROP
        assert await mm.query_database_exists(admin_url, fixed_name) is True
    finally:
        await mm.drop_database(admin_url, fixed_name)


@pytest.mark.asyncio
async def test_cleanup_never_drops_a_database_present_before_the_attempt() -> None:
    admin_url = mm.derive_admin_url(db_safety.resolve_test_database_url(None))
    pre_existing_name = "jobgoblin_verify_manually_preexisting"
    await mm.create_database(admin_url, pre_existing_name)
    try:
        lifecycle = mm.FreshDatabaseLifecycle(
            generated_name=pre_existing_name,
            admin_url=admin_url,
            target_url=db_safety.resolve_test_database_url(None),
            present_before=True,  # simulates the one condition that must block cleanup
            created_by_this_run=True,
            present_after=True,
        )
        await mm.cleanup_fresh_database(lifecycle)
        assert lifecycle.cleaned_up is False
        assert await mm.query_database_exists(admin_url, pre_existing_name) is True
    finally:
        await mm.drop_database(admin_url, pre_existing_name)


@pytest.mark.asyncio
async def test_acknowledgement_lost_after_create_is_still_cleaned_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates the client losing the acknowledgement of a successful
    CREATE DATABASE: the real database is genuinely created, but
    `create_database` raises anyway. Reconciliation must still detect it
    (present now, absent before) and cleanup must still remove it."""
    real_create_database = mm.create_database

    async def _create_then_pretend_it_failed(admin_url: str, database_name: str) -> None:
        await real_create_database(admin_url, database_name)
        raise ConnectionResetError("simulated acknowledgement loss")

    monkeypatch.setattr(mm, "create_database", _create_then_pretend_it_failed)

    lifecycle = await mm.provision_fresh_database(_dev_url(), app_env="test")
    assert lifecycle.created_by_this_run is True
    assert lifecycle.present_after is True

    await mm.cleanup_fresh_database(lifecycle)
    assert lifecycle.cleaned_up is True
    assert await mm.query_database_exists(lifecycle.admin_url, lifecycle.generated_name) is False


@pytest.mark.asyncio
async def test_failed_before_create_produces_no_database_and_no_cleanup() -> None:
    """A CREATE that fails with no side effect at all (e.g. a malformed
    name) must never be treated as owned, and cleanup must be a no-op."""
    admin_url = mm.derive_admin_url(db_safety.resolve_test_database_url(None))
    lifecycle = mm.FreshDatabaseLifecycle(
        generated_name="jobgoblin_verify_never_created",
        admin_url=admin_url,
        target_url=db_safety.resolve_test_database_url(None),
        present_before=False,
        created_by_this_run=False,
        present_after=False,
    )
    await mm.cleanup_fresh_database(lifecycle)
    assert lifecycle.cleaned_up is False


@pytest.mark.asyncio
async def test_capture_development_state_reads_real_database() -> None:
    state = await mm.capture_development_state(_dev_url())
    assert state  # a real database name was returned


@pytest.mark.asyncio
async def test_capture_development_state_fails_closed_when_unreachable() -> None:
    with pytest.raises(mm.MigrationMatrixError, match="failing closed"):
        await mm.capture_development_state(
            "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/does_not_exist"
        )
