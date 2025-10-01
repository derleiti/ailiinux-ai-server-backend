from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import httpx

from ..config import get_settings
from ..utils.http_client import robust_client

logger = logging.getLogger("ailinux.model_registry")


VISION_PATTERN = re.compile(r"(llava|vision|moondream|llama-vision|bakllava|pixtral|minicpm)", re.IGNORECASE)
IMAGE_GEN_PATTERN = re.compile(r"(flux|stable-diffusion|sd-|sdxl|dalle)", re.IGNORECASE)


@dataclass(slots=True)
class ModelInfo:
    id: str
    provider: str
    capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "provider": self.provider,
            "capabilities": self.capabilities,
        }


class ModelRegistry:
    def __init__(self) -> None:
        self._settings = get_settings()
        self._lock = asyncio.Lock()
        self._cache: List[ModelInfo] | None = None
        self._cache_expiry: float = 0.0
        self._ttl_seconds: float = 30.0

    async def list_models(self, force_refresh: bool = False) -> List[ModelInfo]:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if (
                not force_refresh
                and self._cache
                and self._cache_expiry > now
            ):
                return list(self._cache)

            models: List[ModelInfo] = []
            models.extend(await self._discover_ollama())
            models.extend(await self._discover_stable_diffusion())
            models.extend(self._discover_hosted())

            self._cache = models
            self._cache_expiry = now + self._ttl_seconds
            return list(models)

    async def get_model(self, model_id: str) -> Optional[ModelInfo]:
        models = await self.list_models()
        for entry in models:
            if entry.id == model_id:
                return entry
        return None

    async def _discover_ollama(self) -> List[ModelInfo]:
        settings = self._settings
        ollama_url = httpx.URL(str(settings.ollama_base)).join("/api/tags") # Re-insert url definition
        try:
            response = await robust_client.get(str(ollama_url))
            response.raise_for_status()
        except httpx.RequestError as exc:
            logger.warning("Failed to connect to Ollama at %s: %s", ollama_url, exc) # Use ollama_url
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("Ollama returned HTTP error %s for %s: %s", exc.response.status_code, ollama_url, exc)

        payload = response.json()
        items = payload.get("models") or payload.get("data") or []
        models: List[ModelInfo] = []
        for item in items:
            name = item.get("name") or item.get("model")
            if not name:
                continue

            # Bestimme Capabilities basierend auf Modellnamen
            capabilities = []

            # Bild-Generierung (FLUX, Stable Diffusion, etc.)
            if IMAGE_GEN_PATTERN.search(name):
                capabilities.append("image_gen")
            # Vision (kann Bilder analysieren)
            elif VISION_PATTERN.search(name):
                capabilities.extend(["chat", "vision"])
            # Standard Chat-Modell
            else:
                capabilities.append("chat")

            models.append(ModelInfo(id=name, provider="ollama", capabilities=capabilities))
        return models

    async def _discover_stable_diffusion(self) -> List[ModelInfo]:
        settings = self._settings
        sd_url = httpx.URL(str(settings.stable_diffusion_url)).join("/sdapi/v1/sd-models") # Re-insert url definition
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
                response = await client.get(sd_url) # Use sd_url
                response.raise_for_status()
        except httpx.RequestError as exc:
            logger.warning("Failed to connect to Stable Diffusion at %s: %s", sd_url, exc) # Use sd_url
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning("Stable Diffusion returned HTTP error %s for %s: %s", exc.response.status_code, sd_url, exc)
            return []

        try:
            data = response.json()
        except json.JSONDecodeError:
            return []

        results: List[ModelInfo] = []
        for item in data or []:
            name = item.get("title") or item.get("model_name") or item.get("name")
            if not name:
                continue
            results.append(ModelInfo(id=name, provider="sd", capabilities=["image_gen"]))
        return results

    def _discover_hosted(self) -> Iterable[ModelInfo]:
        settings = self._settings
        hosted: List[ModelInfo] = []
        if settings.mixtral_api_key:
            hosted.extend([
                ModelInfo(id="mistral/mixtral-8x7b", provider="mistral", capabilities=["chat"]),
                ModelInfo(id="mistral/large", provider="mistral", capabilities=["chat"]),
                ModelInfo(id="mistral/medium", provider="mistral", capabilities=["chat"]),
                ModelInfo(id="mistral/small", provider="mistral", capabilities=["chat"]),
                ModelInfo(id="mistral/tiny", provider="mistral", capabilities=["chat"]),
            ])
        if settings.gemini_api_key:
            hosted.extend([
                # Gemini 2.0 Models (Latest)
                ModelInfo(id="gemini/gemini-2.0-flash-exp", provider="gemini", capabilities=["chat", "vision"]),
                ModelInfo(id="gemini/gemini-2.0-flash-thinking-exp", provider="gemini", capabilities=["chat", "vision"]),

                # Gemini 1.5 Models (Stable)
                ModelInfo(id="gemini/gemini-1.5-flash", provider="gemini", capabilities=["chat", "vision"]),
                ModelInfo(id="gemini/gemini-1.5-flash-8b", provider="gemini", capabilities=["chat", "vision"]),
                ModelInfo(id="gemini/gemini-1.5-pro", provider="gemini", capabilities=["chat", "vision"]),

                # Gemini 1.0 Models (Legacy)
                ModelInfo(id="gemini/gemini-pro", provider="gemini", capabilities=["chat"]),
                ModelInfo(id="gemini/gemini-pro-vision", provider="gemini", capabilities=["chat", "vision"]),

                # Text Embedding
                ModelInfo(id="gemini/text-embedding-004", provider="gemini", capabilities=["embedding"]),
            ])
        if settings.gpt_oss_api_key:
            hosted.append(ModelInfo(id="gpt-oss:cloud/120b", provider="gpt-oss", capabilities=["chat"]))
        return hosted


registry = ModelRegistry()
