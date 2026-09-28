"""Application configuration.

Loads settings from environment variables (and an optional ``.env`` file)
using Pydantic v2 settings management. A single cached :class:`Settings`
instance is exposed via :func:`get_settings` so the rest of the application
never reads ``os.environ`` directly.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    All values are read from the environment. Defaults are supplied only for
    local development; production deployments MUST override secrets.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application -----------------------------------------------------
    app_name: str = "Enterprise Transformation Intelligence Platform"
    app_env: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    reconcile_on_startup: bool = False

    # ---- Database --------------------------------------------------------
    database_url: str = Field(
        default="postgresql+psycopg://etip:etip@localhost:5432/etip",
        description="SQLAlchemy database URL.",
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_echo: bool = False

    # ---- Redis / Cache ---------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    cache_default_ttl_seconds: int = 300

    # ---- Security / JWT --------------------------------------------------
    jwt_secret_key: str = Field(
        default="change-me-in-production-this-is-not-secure",
        description="HMAC signing key for JWTs.",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 14
    password_min_length: int = 12

    # ---- MFA -------------------------------------------------------------
    mfa_issuer: str = "ETIP"

    # ---- Rate limiting ---------------------------------------------------
    rate_limit_per_minute: int = 120

    # ---- AI code generation (AI Delivery "generate" stage) ---------------
    # Provider: "template" (deterministic, no key) | "anthropic" | "openai".
    codegen_provider: str = "template"
    codegen_api_key: str = ""
    codegen_model: str = "claude-sonnet-4-6"
    codegen_base_url: str = "https://api.anthropic.com/v1/messages"
    codegen_max_tokens: int = 8000

    # ---- SSO (OIDC) ------------------------------------------------------
    public_base_url: str = "http://localhost:8000"

    # ---- CORS ------------------------------------------------------------
    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Allow a comma-separated string in the environment variable."""
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_production(self) -> bool:
        """Return ``True`` when running in the production environment."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()
