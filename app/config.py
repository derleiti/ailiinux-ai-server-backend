from __future__ import annotations
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl, Field

DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "https://ailinux.me"]

class Settings(BaseSettings):
    # App
    host: str = "0.0.0.0"
    port: int = 9100
    debug: bool = True
    app_env: str = "development"

    # CORS & Rate Limiting
    CORS_ALLOWED_ORIGINS: str = ",".join(DEFAULT_ALLOWED_ORIGINS)
    REDIS_URL: str = "redis://localhost:6379/0"
    max_concurrent_requests: int = 8
    request_timeout: int = 120
    request_queue_timeout: int = 15

    # Feature toggles
    crawler_enabled: bool = True

    # Providers – IDs/Endpoints/Keys
    LLM_DEFAULT: str = "gpt-oss:cloud/120b"
    LLM_HEAVY: str = "deepseek-670b-cloud"

    gpt_oss_api_base: Optional[str] = Field(default=None, validation_alias="GPT_OSS_API_BASE")
    gpt_oss_api_key: Optional[str] = Field(default=None, validation_alias="GPT_OSS_API_KEY")
    gpt_oss_model_id: Optional[str] = Field(default="gpt-oss:cloud/120b", validation_alias="GPT_OSS_MODEL_ID")
    gpt_oss_timeout_ms: int = Field(default=30000, validation_alias="GPT_OSS_TIMEOUT_MS")

    deepseek_api_base: Optional[str] = Field(default=None, validation_alias="DEEPSEEK_API_BASE")
    deepseek_api_key: Optional[str] = Field(default=None, validation_alias="DEEPSEEK_API_KEY")
    deepseek_model_id: Optional[str] = Field(default="deepseek-670b-cloud", validation_alias="DEEPSEEK_MODEL_ID")
    deepseek_timeout_ms: int = Field(default=60000, validation_alias="DEEPSEEK_TIMEOUT_MS")

    openrouter_api_base: Optional[str] = Field(default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_API_BASE")
    openrouter_api_key: Optional[str] = Field(default=None, validation_alias="OPENROUTER_API_KEY")
    openrouter_model_id: Optional[str] = Field(default="xai/grok-4o-mini", validation_alias="OPENROUTER_MODEL_ID")
    openrouter_timeout_ms: int = Field(default=20000, validation_alias="OPENROUTER_TIMEOUT_MS")

    zj_api_base: Optional[str] = Field(default="https://api.zukijourney.com/v1", validation_alias="ZJ_API_BASE")
    zj_api_key: Optional[str] = Field(default=None, validation_alias="ZJ_API_KEY")
    zj_model_id: Optional[str] = Field(default=None, validation_alias="ZJ_MODEL_ID")
    zj_timeout_ms: int = Field(default=30000, validation_alias="ZJ_TIMEOUT_MS")

    # Vision/Image/Ollama
    gemini_api_key: Optional[str] = Field(default=None, validation_alias="GEMINI_API_KEY")
    ollama_base: AnyHttpUrl = Field(default="http://127.0.0.1:11434", validation_alias="OLLAMA_BASE")
    ollama_model: Optional[str] = Field(default=None, validation_alias="OLLAMA_MODEL")
    ollama_timeout_ms: int = Field(default=120000, validation_alias="OLLAMA_TIMEOUT_MS")
    stable_diffusion_url: AnyHttpUrl = Field(default="http://127.0.0.1:7860", validation_alias="STABLE_DIFFUSION_URL")

    # WordPress / bbPress
    wordpress_url: Optional[AnyHttpUrl] = Field(default=None, validation_alias="WORDPRESS_URL")
    wordpress_username: Optional[str] = Field(default=None, validation_alias="WORDPRESS_USERNAME")
    wordpress_password: Optional[str] = Field(default=None, validation_alias="WORDPRESS_PASSWORD")
    wordpress_category_id: int = Field(default=0, validation_alias="WORDPRESS_CATEGORY_ID")
    bbpress_forum_id: int = Field(default=0, validation_alias="BBPRESS_FORUM_ID")

    # Mixtral (Mistral API) - added for consistency
    mixtral_api_key: Optional[str] = Field(default=None, validation_alias="MIXTRAL_API_KEY")
    ailinux_mixtral_organisation_id: Optional[str] = Field(default=None, validation_alias="AILINUX_MIXTRAL_ORG_ID")

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        case_sensitive=False # Allow case-insensitive matching for env vars if no alias is provided
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

# Optional: For backward compatibility or convenience, expose a global settings object
# Modules should primarily use get_settings() inside functions/methods.
settings = get_settings()