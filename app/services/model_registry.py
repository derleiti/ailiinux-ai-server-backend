from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

import httpx

from ..config import get_settings


VISION_PATTERN = re.compile(r"(llava|vision|moondream|llama-vision)", re.IGNORECASE)


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
        url = httpx.URL(str(settings.ollama_base)).join("/api/tags")
        timeout = httpx.Timeout(settings.request_timeout)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError:
            return []

        payload = response.json()
        items = payload.get("models") or payload.get("data") or []
        models: List[ModelInfo] = []
        for item in items:
            name = item.get("name") or item.get("model")
            if not name:
                continue
            capabilities = ["chat"]
            if VISION_PATTERN.search(name) and "vision" not in capabilities:
                capabilities.append("vision")
            models.append(ModelInfo(id=name, provider="ollama", capabilities=capabilities))
        return models

    async def _discover_stable_diffusion(self) -> List[ModelInfo]:
        settings = self._settings
        url = httpx.URL(str(settings.stable_diffusion_url)).join("/sdapi/v1/sd-models")
        timeout = httpx.Timeout(settings.request_timeout)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError:
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
            hosted.append(
                ModelInfo(
                    id="mistral/mixtral-8x7b",
                    provider="mistral",
                    capabilities=["chat"],
                )
            )
        if settings.gemini_api_key:
            hosted.append(
                ModelInfo(
                    id="gemini/gemini-1.5-pro",
                    provider="gemini",
                    capabilities=["chat", "vision"],
                )
            )
        return hosted


registry = ModelRegistry()
