"""Offline unit tests for `scripts/db_safety.py` — no database connection,
no network. `assert_is_disposable_test_database` is already exercised
indirectly through `tests/conftest.py`'s fixtures and `tests/test_users.py`;
this file adds direct, isolated coverage for that function's newer sibling,
`assert_safe_for_local_destructive_lifecycle`, which only
`scripts/live_proof_greenhouse_ingestion.py` ever calls.
"""

import pytest

from scripts.db_safety import assert_safe_for_local_destructive_lifecycle

_DEV_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin"


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]"])
def test_accepts_a_genuinely_local_test_database(host: str) -> None:
    """IPv6 literals require bracket syntax in a URL authority
    (`[::1]`) — `URL.host` itself still reports the unbracketed `::1`."""
    candidate = (
        f"postgresql+asyncpg://jobgoblin:jobgoblin@{host}:5432/jobgoblin_test_live_proof_abc123"
    )
    assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")


def test_accepts_local_host_case_insensitively() -> None:
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@LOCALHOST:5432/jobgoblin_test_x"
    assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")


def test_rejects_a_remote_host() -> None:
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@db.example.com:5432/jobgoblin_test_x"
    with pytest.raises(RuntimeError, match="host must be one of"):
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")


def test_rejects_a_missing_host() -> None:
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@/jobgoblin_test_x"
    with pytest.raises(RuntimeError, match="host must be one of"):
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")


def test_rejects_production_app_env_even_with_a_local_disposable_name() -> None:
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test_x"
    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="production")


def test_production_check_runs_even_when_host_is_also_unsafe() -> None:
    """Order doesn't matter for correctness here — both conditions
    independently fail closed — but the production message must still be
    the one surfaced when both are true, since it is checked first."""
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@remote.example.com:5432/jobgoblin_test_x"
    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="production")


def test_still_delegates_to_the_disposable_name_guard_first() -> None:
    """A candidate matching the development database's own name must still
    be rejected by the underlying `assert_is_disposable_test_database`
    check, even though its host is genuinely local."""
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin"
    with pytest.raises(RuntimeError, match="matches the configured development database"):
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")


def test_still_delegates_to_the_missing_test_marker_guard_too() -> None:
    candidate = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/some_other_db"
    with pytest.raises(RuntimeError, match="does not contain 'test'"):
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")


def test_error_messages_never_contain_credentials() -> None:
    candidate = (
        "postgresql+asyncpg://secretuser:secretpass@remote.example.com:5432/jobgoblin_test_x"
    )
    with pytest.raises(RuntimeError) as exc_info:
        assert_safe_for_local_destructive_lifecycle(candidate, _DEV_URL, app_env="development")
    message = str(exc_info.value)
    assert "secretuser" not in message
    assert "secretpass" not in message
