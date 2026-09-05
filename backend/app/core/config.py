from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Workspace Manager API"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://ai_workspace:ai_workspace@localhost:5433/ai_workspace"
    )
    frontend_url: str = "http://localhost:5173"
    gemini_api_key: str | None = None
    gemini_chat_model: str = "gemini-3.6-flash"
    gemini_request_timeout_seconds: float = 60
    guest_session_secret: str = "local-development-guest-session-secret"

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def select_psycopg_driver(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_url]
        if self.environment == "development":
            origins.extend(["http://localhost:5173", "http://127.0.0.1:5173"])
        return list(dict.fromkeys(origins))


@lru_cache
def get_settings() -> Settings:
    return Settings()
