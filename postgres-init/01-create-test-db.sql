-- Creates a disposable database for automated tests, alongside the ordinary
-- `jobgoblin` development database. Database tests (backend/tests/test_users.py)
-- must never run against `jobgoblin` itself — see backend/tests/conftest.py's
-- fail-closed guard and README.md's "Dedicated test database" section.
--
-- PostgreSQL's docker-entrypoint-initdb.d mechanism only runs scripts here on
-- first initialization of an empty data volume. If your `postgres_data` volume
-- already existed before this file was added, run the CREATE DATABASE
-- statement below manually once instead (see README.md).
CREATE DATABASE jobgoblin_test OWNER jobgoblin;
