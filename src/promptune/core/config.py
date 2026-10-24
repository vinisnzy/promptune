from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str
    jwt_secret: SecretStr
    jwt_algorithm: str
    access_token_expires_in_minutes: int = 15
    refresh_token_expires_in_days: int = 7
    llm_model: str
    llm_provider: str
    groq_api_key: SecretStr
    agent_run_max_attempts: int = Field(default=3, gt=0)
    agent_run_retry_delay_seconds: int = Field(default=15, gt=0)
    agent_run_timeout_seconds: int = Field(default=90, gt=0)
    rabbitmq_url: str = "amqp://app:app@localhost:5672/"
    worker_prefetch: int = Field(default=1, gt=0)

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
