from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import AnyHttpUrl, validator
from pydantic_settings import BaseSettings


DEFAULT_ALLOWED_ORIGINS = [
    "https://ailinux.me",
    "https://api.ailinux.me:9000",
]


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 9100
    ollama_base: AnyHttpUrl = "http://localhost:11434"
    stable_diffusion_url: AnyHttpUrl = "http://127.0.0.1:7860"
    request_timeout: int = 120
    request_queue_timeout: int = 15
    max_concurrent_requests: int = 8

    chat_backend: str | None = None
    gpt_oss_model: str | None = None

    manage_ollama: int = 0
    ollama_port: int = 11434
    ollama_host: str | None = None

    mixtral_api_key: Optional[str] = None
    ailinux_mixtral_organisation_id: Optional[str] = None
    gemini_api_key: Optional[str] = None
    voidai_api_key: Optional[str] = None
    open_skywork_ai_api_key: Optional[str] = None
    open_skywork_secret_id: Optional[str] = None
    gpt_oss_api_key: Optional[str] = None
    gpt_oss_base_url: Optional[AnyHttpUrl] = None
    groq_api_key: Optional[str] = None
    wordpress_url: Optional[AnyHttpUrl] = None
    wordpress_username: Optional[str] = None
    wordpress_password: Optional[str] = None
    bbpress_forum_id: int = 1
    wordpress_category_id: int = 0

    crawler_enabled: bool = True
    crawler_spool_dir: str = "data/crawler_spool"
    crawler_max_memory_bytes: int = 48 * 1024 ** 3
    crawler_summary_model: Optional[str] = "gpt-oss:cloud/120b"
    crawler_ollama_model: Optional[str] = "gpt-oss:cloud/120b"
    crawler_flush_interval: int = 3600
    crawler_retention_days: int = 30
    crawler_train_dir: str = "data/crawler_spool/train"

    ssl_enabled: int = 0
    ssl_cert_file: Optional[str] = None
    ssl_key_file: Optional[str] = None
    allowed_origins: list[str] = DEFAULT_ALLOWED_ORIGINS.copy()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @validator("ollama_host", pre=True, always=True)
    def _derive_ollama_host(cls, value: str | None, values):
        if value:
            return value
        port = values.get("ollama_port", 11434)
        return f"0.0.0.0:{port}"

    @validator("allowed_origins", pre=True)
    def _normalize_allowed_origins(cls, value):
        if value is None:
            return DEFAULT_ALLOWED_ORIGINS.copy()
        if isinstance(value, str):
            items = [origin.strip() for origin in value.split(",") if origin.strip()]
            return items or DEFAULT_ALLOWED_ORIGINS.copy()
        if isinstance(value, (list, tuple, set)):
            items = [str(origin).strip() for origin in value if str(origin).strip()]
            return items or DEFAULT_ALLOWED_ORIGINS.copy()
        raise ValueError("allowed_origins must be a comma-separated string or list of origins")


@lru_cache()
def get_settings() -> Settings:
    return Settings()