"""Application configuration loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str = "sqlite:///./local.db"
    log_level: str = "INFO"

    identity_service_base_url: str = "http://localhost:8101"
    collaboration_service_base_url: str = "http://localhost:8102"
    notification_service_base_url: str = "http://localhost:8103"

    connector_timeout_seconds: float = 5.0

    # Retry policy: total attempts = 1 initial attempt + retry_max_retries.
    retry_max_retries: int = 3
    retry_base_delay_seconds: float = 0.5
    retry_max_delay_seconds: float = 4.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
