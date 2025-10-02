from __future__ import annotations
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl

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

    GPT_OSS_API_BASE: Optional[str] = None
    GPT_OSS_API_KEY: Optional[str] = None
    GPT_OSS_MODEL_ID: Optional[str] = "gpt-oss:cloud/120b"
    GPT_OSS_TIMEOUT_MS: int = 30000

    DEEPSEEK_API_BASE: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL_ID: Optional[str] = "deepseek-670b-cloud"
    DEEPSEEK_TIMEOUT_MS: int = 60000

    OPENROUTER_API_BASE: Optional[str] = "https://openrouter.ai/api/v1"
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL_ID: Optional[str] = "xai/grok-4o-mini"
    OPENROUTER_TIMEOUT_MS: int = 20000

    ZJ_API_BASE: Optional[str] = "https://api.zukijourney.com/v1"
    ZJ_API_KEY: Optional[str] = None
    ZJ_MODEL_ID: Optional[str] = None
    ZJ_TIMEOUT_MS: int = 30000

    # Vision/Image/Ollama
    gemini_api_key: Optional[str] = None
    ollama_base: AnyHttpUrl = "http://127.0.0.1:11434"
    stable_diffusion_url: AnyHttpUrl = "http://127.0.0.1:7860"

    # WordPress / bbPress
    wordpress_url: Optional[AnyHttpUrl] = None
    wordpress_username: Optional[str] = None
    wordpress_password: Optional[str] = None
    wordpress_category_id: int = 0
    bbpress_forum_id: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore"
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()

# Optional: For backward compatibility or convenience, expose a global settings object
# Modules should primarily use get_settings() inside functions/methods.
settings = get_settings()
