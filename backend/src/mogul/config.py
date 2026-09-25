from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOGUL_", env_file=".env", extra="ignore")

    # SQLite keeps local dev zero-setup; docker-compose points this at Postgres.
    database_url: str = "sqlite:///./mogul.db"
    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
