from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MOGUL_", env_file=".env", extra="ignore")

    # SQLite keeps local dev zero-setup; docker-compose points this at Postgres.
    database_url: str = "sqlite:///./mogul.db"
    cors_origins: list[str] = ["http://localhost:3000"]
    # Every downloaded source file is kept here before parsing, so history can be
    # re-parsed later. A local path for now; object storage in production.
    raw_data_dir: str = "./data/raw"
    # How many of the largest metros to ingest from Zillow (by Zillow's SizeRank).
    zillow_max_metros: int = 150
    # Listings: RentCast API key and the areas to sweep, e.g. ["Memphis, TN"].
    rentcast_api_key: str = ""
    listing_areas: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
