from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from pathlib import Path
from typing import Optional, Tuple

import httpx

from ..config import get_settings
from ..services.model_registry import ModelInfo
from ..utils.errors import api_error
from ..utils.http import extract_http_error

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10MB
TEMP_RETENTION_SECONDS = 120


async def analyze(
    model: ModelInfo,
    request_model: str,
    prompt: str,
    image_url: Optional[str] = None,
    image_bytes: Optional[bytes] = None,
    content_type: Optional[str] = None,
    filename: Optional[str] = None,
) -> str:
    if not prompt.strip():
        raise api_error("Prompt is required", status_code=422, code="missing_prompt")

    if image_bytes is None and not image_url:
        raise api_error("Either image_url or image data is required", status_code=422, code="missing_image")

    if image_bytes is not None and len(image_bytes) > MAX_IMAGE_BYTES:
        raise api_error("Image exceeds 10MB limit", status_code=413, code="image_too_large")

    if image_bytes is not None and content_type is None:
        content_type = "image/png"

    if model.provider == "ollama":
        resolved_bytes = image_bytes
        resolved_name = filename

        if resolved_bytes is None:
            assert image_url is not None
            _, resolved_bytes = await _download_image(image_url)
            if not resolved_name and image_url:
                resolved_name = image_url.split("/")[-1]

        if resolved_bytes is None:
            raise api_error("Image bytes missing", status_code=422, code="missing_image")

        _persist_temp_file(resolved_bytes, resolved_name)
        return await _analyze_with_ollama_data(
            request_model,
            prompt,
            resolved_bytes,
        )

    if model.provider == "gemini":
        settings = get_settings()
        if not settings.gemini_api_key:
            raise api_error("Gemini support is not configured", status_code=503, code="gemini_unavailable")
        if image_bytes is not None:
            encoded = base64.b64encode(image_bytes).decode("ascii")
            _persist_temp_file(image_bytes, filename)
            return await _analyze_with_gemini_data(
                request_model,
                prompt,
                content_type or "image/png",
                encoded,
                api_key=settings.gemini_api_key,
            )
        assert image_url is not None
        return await _analyze_with_gemini_url(
            request_model,
            prompt,
            image_url,
            api_key=settings.gemini_api_key,
        )

    raise api_error("Selected model does not support vision analysis", status_code=400, code="unsupported_provider")


async def analyze_from_url(model: ModelInfo, request_model: str, image_url: str, prompt: str) -> str:
    return await analyze(model, request_model, prompt, image_url=image_url)


async def analyze_from_upload(
    model: ModelInfo,
    request_model: str,
    prompt: str,
    image_bytes: bytes,
    content_type: Optional[str],
    filename: Optional[str],
) -> str:
    return await analyze(
        model,
        request_model,
        prompt,
        image_bytes=image_bytes,
        content_type=content_type,
        filename=filename,
    )


def _persist_temp_file(data: bytes, filename: Optional[str]) -> None:
    suffix = ""
    if filename and "." in filename:
        suffix = filename[filename.rfind("."):]
    fd, temp_path = tempfile.mkstemp(prefix="novaai_upload_", suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    path = Path(temp_path)

    loop = asyncio.get_event_loop()
    loop.call_later(
        TEMP_RETENTION_SECONDS,
        lambda: path.exists() and path.unlink(missing_ok=True),
    )


async def _analyze_with_ollama_data(
    model: str,
    prompt: str,
    image_bytes: bytes,
) -> str:
    settings = get_settings()
    url = httpx.URL(str(settings.ollama_base)).join("/api/chat")
    encoded = base64.b64encode(image_bytes).decode("ascii")
    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [encoded],
            }
        ],
        "stream": False,
    }
    return await _dispatch_ollama(url, body)


async def _dispatch_ollama(url: httpx.URL, payload: dict) -> str:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.request_timeout)) as client:
            response = await client.post(url, json=payload)
    except httpx.RequestError as exc:
        raise api_error(
            f"Failed to reach Ollama backend: {exc}",
            status_code=502,
            code="ollama_unreachable",
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message, code = extract_http_error(
            exc.response,
            default_message="Ollama returned an error",
            default_code="ollama_error",
        )
        raise api_error(message, status_code=exc.response.status_code, code=code) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise api_error(
            "Ollama returned malformed JSON",
            status_code=502,
            code="ollama_invalid_response",
        ) from exc

    message = data.get("message") or {}
    text = _extract_ollama_text(message.get("content"))
    if not text:
        text = _extract_ollama_text(data.get("response"))
    if not text:
        raise api_error("Vision model returned no response", status_code=502, code="empty_response")
    return text


def _extract_ollama_text(content: Optional[object]) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item and item["text"]:
                    fragments.append(str(item["text"]))
                elif "content" in item and item["content"]:
                    fragments.append(str(item["content"]))
            elif isinstance(item, str):
                fragments.append(item)
        return "".join(fragments)
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        if isinstance(text_value, str):
            return text_value
    return str(content)


async def _analyze_with_gemini_data(
    model: str,
    prompt: str,
    content_type: str,
    encoded_data: str,
    *,
    api_key: str,
) -> str:
    target_model = model.split("/", 1)[1] if "/" in model else model

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": content_type,
                            "data": encoded_data,
                        }
                    },
                ],
            }
        ]
    }

    return await _dispatch_gemini(url, body, api_key)


async def _analyze_with_gemini_url(
    model: str,
    prompt: str,
    image_url: str,
    *,
    api_key: str,
) -> str:
    content_type, image_data = await _download_image(image_url)
    encoded = base64.b64encode(image_data).decode("ascii")
    return await _analyze_with_gemini_data(model, prompt, content_type, encoded, api_key=api_key)


async def _dispatch_gemini(url: str, payload: dict, api_key: str) -> str:
    params = {"key": api_key}
    timeout = httpx.Timeout(get_settings().request_timeout)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, params=params, json=payload)
    except httpx.RequestError as exc:
        raise api_error(
            f"Failed to reach Gemini API: {exc}",
            status_code=502,
            code="gemini_unreachable",
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message, code = extract_http_error(
            exc.response,
            default_message="Gemini API responded with an error",
            default_code="gemini_error",
        )
        raise api_error(message, status_code=exc.response.status_code, code=code) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise api_error(
            "Gemini API returned malformed JSON",
            status_code=502,
            code="gemini_invalid_response",
        ) from exc
        candidates = data.get("candidates") or []
        if not candidates:
            raise api_error("Gemini returned no candidates", status_code=502, code="empty_response")
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [part.get("text", "") for part in parts if part.get("text")]
        text = "".join(texts)
        if not text:
            raise api_error("Gemini response was empty", status_code=502, code="empty_response")
        return text


async def _download_image(url: str) -> Tuple[str, bytes]:
    settings = get_settings()
    timeout = httpx.Timeout(settings.request_timeout)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
    except httpx.RequestError as exc:
        raise api_error(
            f"Failed to download image: {exc}",
            status_code=502,
            code="image_download_failed",
        ) from exc

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        message, code = extract_http_error(
            exc.response,
            default_message="Image download failed",
            default_code="image_download_failed",
        )
        raise api_error(message, status_code=exc.response.status_code, code=code) from exc
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_IMAGE_BYTES:
            raise api_error("Image exceeds 10MB limit", status_code=413, code="image_too_large")
        data = response.content
        if len(data) > MAX_IMAGE_BYTES:
            raise api_error("Image exceeds 10MB limit", status_code=413, code="image_too_large")
        content_type = response.headers.get("Content-Type") or "image/png"
        return content_type, data
