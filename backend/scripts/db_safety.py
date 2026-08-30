"""Shared database-safety guard for tooling only — never imported by the
shipped application package (`app/`).

`assert_is_disposable_test_database()` and its supporting helpers originated
in `tests/conftest.py`. They now live here, unchanged in behavior, so both
`tests/conftest.py` (real pytest fixtures) and `scripts/verify.py` (the
Workflow v3 routine verifier) import the *same* implementation rather than
maintaining two independently-driftable copies of a safety-critical check —
see `docs/DECISIONS` for why this class of duplication is treated as a real
risk, not a style preference. Deliberately placed under `scripts/`, not
`app/db/`: this is dev/test tooling, not runtime application code, and
`pyproject.toml`'s `[tool.hatch.build.targets.wheel]` only ships `app/` —
this module is never packaged.
"""

from __future__ import annotations

from sqlalchemy.engine import URL, make_url

# Disposable database for automated tests only (backend/tests/) — never the
# same database as the configured development target. `None` (an unset
# `Settings.test_database_url`) falls back to this default — see
# .env.example and README.md's "Dedicated test database" section.
DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin_test"


def redact_database_url(url: str | URL) -> str:
    """A safe-to-print form of a database URL: driver/host/port/database
    only — never username or password. Used anywhere a misconfigured URL
    might otherwise end up in a raised exception or test/tooling output."""
    parsed = url if isinstance(url, URL) else make_url(url)
    return f"{parsed.drivername}://{parsed.host}:{parsed.port}/{parsed.database}"


def assert_is_disposable_test_database(test_url: str, development_url: str) -> None:
    """Fail closed: refuse to run destructive database tests against
    anything that doesn't clearly look like a disposable test database,
    *distinct from the actually-configured development database*.

    Raises `RuntimeError` (a hard test failure, not a skip) if either:
    - `test_url`'s database name equals `development_url`'s database name
      (case-insensitive) — compared by **name alone**, deliberately ignoring
      host, port, credentials, or driver spelling. A first version of this
      guard compared `(host, port, database)` tuples, which let a
      `localhost` test URL and a `127.0.0.1` development URL — or an
      explicit `:5432` versus an omitted default port — pass as "different"
      even when they resolve to the exact same server. Two different
      connection strings can reach the same database in more ways than can
      be reliably enumerated, so this guard doesn't try: it's deliberately
      conservative and rejects on name match alone, accepting that a
      same-named database on a genuinely separate server will also be
      rejected. For a fail-closed guard protecting against irreversible
      schema/data loss, an occasional false rejection is the correct
      trade-off against a false acceptance.
    - `test_url`'s database name doesn't contain "test" at all.

    Database tests create and drop schema/data; running them against
    whatever `DATABASE_URL` actually points at — the real check, not a
    hardcoded name — would corrupt real development state. Never includes a
    raw, credential-bearing URL in the raised message; see
    `redact_database_url` above.
    """
    test_parsed = make_url(test_url)
    dev_parsed = make_url(development_url)

    test_name = (test_parsed.database or "").lower()
    dev_name = (dev_parsed.database or "").lower()

    same_name_as_development = test_name == dev_name
    missing_test_marker = "test" not in test_name

    if same_name_as_development or missing_test_marker:
        reasons = []
        if same_name_as_development:
            reasons.append(
                "its database name matches the configured development database's "
                f"name ({redact_database_url(dev_parsed)})"
            )
        if missing_test_marker:
            reasons.append("its database name does not contain 'test'")
        raise RuntimeError(
            f"Refusing to run database tests against {redact_database_url(test_parsed)}: "
            + " and ".join(reasons)
            + ". Set TEST_DATABASE_URL to a distinct, clearly-named disposable "
            "test database — see README.md's 'Dedicated test database' section."
        )


def resolve_test_database_url(test_database_url: str | None) -> str:
    """The test database URL this project actually uses: the configured
    `Settings.test_database_url` if set, otherwise `DEFAULT_TEST_DATABASE_URL`.
    Takes the already-resolved setting value (not a `Settings` object) so
    this module never needs to import `app.config` — callers (both
    `tests/conftest.py` and `scripts/verify.py`) already have their own
    `Settings` instance and pass its one relevant field through, keeping
    this module's only dependency the already-required `sqlalchemy`.
    """
    return test_database_url or DEFAULT_TEST_DATABASE_URL
