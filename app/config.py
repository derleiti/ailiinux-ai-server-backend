from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, Field

DEFAULT_ALLOWED_ORIGINS = ["http://localhost:5173", "http://localhost:3000", "https://ailinux.me"]

class Settings(BaseSettings):
    # --- Core timeouts ---
    request_timeout: float = Field(default=30.0, validation_alias="REQUEST_TIMEOUT")
    ollama_timeout_ms: int = Field(default=15000, validation_alias="OLLAMA_TIMEOUT_MS")
    max_concurrent_requests: int = Field(default=8, validation_alias="MAX_CONCURRENT_REQUESTS")
    request_queue_timeout: float = Field(default=15.0, validation_alias="REQUEST_QUEUE_TIMEOUT")

    # --- CORS ---
    cors_allowed_origins: str = Field(default=",".join(DEFAULT_ALLOWED_ORIGINS), validation_alias="CORS_ALLOWED_ORIGINS")

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # --- Providers / Backends ---
    ollama_base: AnyHttpUrl = Field(default="http://localhost:11434", validation_alias="OLLAMA_BASE")
    stable_diffusion_url: AnyHttpUrl = Field(default="http://localhost:7860", validation_alias="STABLE_DIFFUSION_URL")

    # GPT-OSS
    gpt_oss_api_key: str | None = Field(default=None, validation_alias="GPT_OSS_API_KEY")
    gpt_oss_base_url: AnyHttpUrl | None = Field(default=None, validation_alias="GPT_OSS_BASE_URL")

    # Gemini
    gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    # Mistral / Mixtral
    mixtral_api_key: str | None = Field(default=None, validation_alias="MIXTRAL_API_KEY")
    ailinux_mixtral_organisation_id: str | None = Field(default=None, validation_alias="AILINUX_MIXTRAL_ORG_ID")

    # WordPress / bbPress
    wordpress_url: AnyHttpUrl | None = Field(default=None, validation_alias="WORDPRESS_URL")
    wordpress_user: str | None = Field(default=None, validation_alias="WORDPRESS_USER")
    wordpress_password: str | None = Field(default=None, validation_alias="WORDPRESS_PASSWORD")

    # Crawler
    crawler_enabled: bool = Field(default=True, validation_alias="CRAWLER_ENABLED")
    crawler_max_memory_bytes: int = Field(default=256*1024*1024, validation_alias="CRAWLER_MAX_MEMORY_BYTES")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache
def get_settings() -> Settings:
    return Settings()