from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore") # 'extra="ignore"' erlaubt unbekannte Variablen im .env

    APP_ENV: str = "development"
    DEBUG: bool = True
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000,http://localhost:8080"
    REDIS_URL: str = "redis://localhost:6379/0"

    # LLM Provider
    LLM_DEFAULT: str = "gpt-oss:120b-cloud"
    LLM_HEAVY: str = "deepseek-670b-cloud"

    OPENROUTER_API_BASE: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL_ID: Optional[str] = None
    OPENROUTER_TIMEOUT_MS: int = 20000

    DEEPSEEK_API_BASE: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_MODEL_ID: Optional[str] = None
    DEEPSEEK_TIMEOUT_MS: int = 60000

    ZJ_API_BASE: Optional[str] = None
    ZJ_API_KEY: Optional[str] = None
    ZJ_MODEL_ID: Optional[str] = None
    ZJ_TIMEOUT_MS: int = 30000

    OLLAMA_API_BASE: Optional[str] = None
    OLLAMA_MODEL: Optional[str] = None
    OLLAMA_TIMEOUT_MS: int = 120000

    GPT_OSS_API_BASE: Optional[str] = None
    GPT_OSS_API_KEY: Optional[str] = None
    GPT_OSS_MODEL_ID: Optional[str] = None
    GPT_OSS_TIMEOUT_MS: int = 30000

    # WordPress MCP
    WP_MCP_ENDPOINT: Optional[str] = None
    WP_MCP_TOKEN: Optional[str] = None
    WP_MCP_TIMEOUT_MS: int = 15000

    CRAWLER_MCP_ENDPOINT: str = "http://localhost:7777/mcp"
    WORDPRESS_MCP_ENDPOINT: str = "https://ailinux.me/wp-json/mcp/v1" # Schon oben definiert
    OLLAMA_MCP_ENDPOINT: str = "http://127.0.0.1:11434/api" # Ollama API ist direkt, kein MCP-Adapter nötig
    OPENROUTER_BRIDGE_ENDPOINT: str = "https://openrouter.ai/api/v1" # OpenRouter API ist direkt
    ZJ_ADAPTER_ENDPOINT: str = "https://api.zukijourney.com/v1" # ZukiJourney API ist direkt

settings = Settings()
