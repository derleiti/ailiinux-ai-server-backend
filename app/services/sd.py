from __future__ import annotations

from typing import Dict, List

import httpx

from ..utils.http import extract_http_error

from ..config import get_settings
from ..utils.errors import api_error


async def generate_image(payload: Dict[str, object]) -> List[str]:
    required_fields = {"prompt", "width", "height", "steps", "model"}
    missing = [field for field in required_fields if field not in payload]
    if missing:
        raise api_error(
            f"Missing fields: {', '.join(missing)}",
            status_code=422,
            code="missing_fields",
        )

    settings = get_settings()
    url = httpx.URL(str(settings.stable_diffusion_url)).join("/sdapi/v1/txt2img")

    body = {
        "prompt": payload.get("prompt"),
        "negative_prompt": payload.get("negative_prompt", ""),
        "width": payload.get("width"),
        "height": payload.get("height"),
        "steps": payload.get("steps"),
        "seed": payload.get("seed", -1),
        "override_settings": {
            "sd_model_checkpoint": payload.get("model"),
        },
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout)) as client:
            response = await client.post(url, json=body)
    except httpx.RequestError as exc:
        raise api_error(
            f"Failed to reach Stable Diffusion backend: {exc}",
            status_code=502,
            code="stable_diffusion_unreachable",
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message, code = extract_http_error(exc.response, default_code="stable_diffusion_error")
        raise api_error(message, status_code=exc.response.status_code, code=code) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise api_error("Stable Diffusion returned malformed JSON", status_code=502, code="invalid_response") from exc

    images = data.get("images") or []
    if not images:
        raise api_error("Stable Diffusion returned no images", status_code=502, code="empty_response")
    return images
