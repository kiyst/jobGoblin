from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-driven application configuration.

    All configuration comes from environment variables (or a `.env` file in
    local development) — nothing is hardcoded. See `.env.example` at the repo
    root for the full list of recognized variables.
    """

    model_config = SettingsConfigDict(
        # Resolve from this module rather than the process working directory.
        # Local commands run from backend/, while the shared .env belongs at
        # the repository root beside .env.example.
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"

    # Must use the asyncpg driver — this project standardizes on SQLAlchemy's
    # async engine (see docs/ARCHITECTURE.md §5's dependency boundaries).
    database_url: str = Field(
        default="postgresql+asyncpg://jobgoblin:jobgoblin@localhost:5432/jobgoblin"
    )

    # Short connect timeout (seconds) so /ready fails fast instead of hanging
    # when PostgreSQL is unreachable.
    database_connect_timeout_seconds: float = 3.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
