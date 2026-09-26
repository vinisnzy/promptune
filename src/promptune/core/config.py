from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    database_url: str
    jwt_secret: SecretStr
    jwt_algorithm: str
    access_token_expires_in_minutes: int = 15
    refresh_token_expires_in_days: int = 7
    groq_api_key: SecretStr

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
