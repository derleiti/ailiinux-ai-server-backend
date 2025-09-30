from __future__ import annotations

import json
from typing import AsyncGenerator, Iterable, List, Optional

import httpx

from ..config import get_settings
from ..services.model_registry import ModelInfo
from ..utils.errors import api_error
from ..utils.http import extract_http_error
from . import web_search

MISTRAL_MODEL_ALIASES = {
    "mistral/mixtral-8x7b": "open-mixtral-8x7b",
    "mistral/open-mixtral-8x7b": "open-mixtral-8x7b",
}

UNCERTAINTY_PHRASES = [
    "i don't know",
    "i am not sure",
    "i cannot answer",
    "i can't answer",
    "i do not have information",
    "i don't have information",
]


def _format_messages(messages: Iterable[dict[str, str]]) -> List[dict[str, str]]:
    formatted: List[dict[str, str]] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not role or content is None:
            continue
        formatted.append({"role": role, "content": content})
    if not formatted:
        raise api_error("Messages cannot be empty", status_code=422, code="missing_messages")
    return formatted


async def _get_initial_response(
    model: ModelInfo,
    request_model: str,
    messages: List[dict[str, str]],
    temperature: Optional[float],
    settings,
) -> str:
    chunks = []
    if model.provider == "ollama":
        async for chunk in _stream_ollama(
            request_model,
            messages,
            temperature=temperature,
            stream=True,
            timeout=settings.request_timeout,
        ):
            chunks.append(chunk)
    elif model.provider == "mistral":
        if not settings.mixtral_api_key:
            raise api_error("Mistral support is not configured", status_code=503, code="mistral_unavailable")
        async for chunk in _stream_mistral(
            request_model,
            messages,
            api_key=settings.mixtral_api_key,
            organisation_id=settings.ailinux_mixtral_organisation_id,
            temperature=temperature,
            stream=True,
            timeout=settings.request_timeout,
        ):
            chunks.append(chunk)
    elif model.provider == "gemini":
        if not settings.gemini_api_key:
            raise api_error("Gemini support is not configured", status_code=503, code="gemini_unavailable")
        async for chunk in _stream_gemini(
            request_model,
            messages,
            api_key=settings.gemini_api_key,
            temperature=temperature,
            stream=True,
            timeout=settings.request_timeout,
        ):
            chunks.append(chunk)
    else:
        raise api_error("Unsupported provider", status_code=400, code="unsupported_provider")
    return "".join(chunks)


async def stream_chat(
    model: ModelInfo,
    request_model: str,
    messages: Iterable[dict[str, str]],
    *,
    stream: bool,
    temperature: Optional[float] = None,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    formatted_messages = _format_messages(messages)
    
    # Get initial response
    initial_response = await _get_initial_response(model, request_model, formatted_messages, temperature, settings)

    # Check for uncertainty
    if any(phrase in initial_response.lower() for phrase in UNCERTAINTY_PHRASES):
        user_query = formatted_messages[-1]["content"]
        yield "Ich bin mir nicht sicher, aber ich werde im Web danach suchen...\n\n"
        
        search_results = await web_search.search_web(user_query)
        
        if not search_results:
            yield "Ich konnte keine relevanten Informationen online finden."
            return

        context = "Web search results:\n"
        for res in search_results:
            context += f"- Title: {res['title']}\n"
            context += f"  URL: {res['url']}\n"
            context += f"  Snippet: {res['snippet']}\n\n"

        augmented_messages = formatted_messages + [
            {"role": "system", "content": "Here is some context from a web search:"},
            {"role": "system", "content": context},
            {"role": "user", "content": f"Based on the web search results, please answer my original question: {user_query}"}
        ]
        
        if model.provider == "ollama":
            async for chunk in _stream_ollama(
                request_model, augmented_messages, temperature=temperature, stream=stream, timeout=settings.request_timeout
            ):
                yield chunk
        elif model.provider == "mistral":
            async for chunk in _stream_mistral(
                request_model, augmented_messages, api_key=settings.mixtral_api_key, organisation_id=settings.ailinux_mixtral_organisation_id, temperature=temperature, stream=stream, timeout=settings.request_timeout
            ):
                yield chunk
        elif model.provider == "gemini":
            async for chunk in _stream_gemini(
                request_model, augmented_messages, api_key=settings.gemini_api_key, temperature=temperature, stream=stream, timeout=settings.request_timeout
            ):
                yield chunk
    else:
        yield initial_response


async def _stream_ollama(
    model: str,
    messages: List[dict[str, str]],
    *,
    temperature: Optional[float],
    stream: bool,
    timeout: int,
) -> AsyncGenerator[str, None]:
    settings = get_settings()
    url = httpx.URL(str(settings.ollama_base)).join("/api/chat")
    payload: dict[str, object] = {
        "model": model,
        "messages": messages,
        "stream": stream,
    }
    if temperature is not None:
        payload["options"] = {"temperature": max(0.0, min(temperature, 2.0))}

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        if stream:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if data.get("done"):
                            break
                        message = data.get("message") or {}
                        content = _extract_ollama_text(message.get("content"))
                        if not content:
                            content = _extract_ollama_text(data.get("response"))
                        if content:
                            yield content
            except httpx.HTTPStatusError as exc:
                message, code = extract_http_error(
                    exc.response,
                    default_message="Ollama returned an error",
                    default_code="ollama_error",
                )
                raise api_error(message, status_code=exc.response.status_code, code=code) from exc
            except httpx.RequestError as exc:
                raise api_error(
                    f"Failed to reach Ollama backend: {exc}",
                    status_code=502,
                    code="ollama_unreachable",
                ) from exc
        else:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                message, code = extract_http_error(
                    exc.response,
                    default_message="Ollama returned an error",
                    default_code="ollama_error",
                )
                raise api_error(message, status_code=exc.response.status_code, code=code) from exc
            except httpx.RequestError as exc:
                raise api_error(
                    f"Failed to reach Ollama backend: {exc}",
                    status_code=502,
                    code="ollama_unreachable",
                ) from exc

            data = response.json()
            if "message" in data and data["message"].get("content"):
                text = _extract_ollama_text(data["message"]["content"])
                if text:
                    yield text
            elif data.get("response"):
                text = _extract_ollama_text(data.get("response"))
                if text:
                    yield text


async def _stream_mistral(
    model: str,
    messages: List[dict[str, str]],
    *,
    api_key: str,
    organisation_id: Optional[str],
    temperature: Optional[float],
    stream: bool,
    timeout: int,
) -> AsyncGenerator[str, None]:
    target_model = MISTRAL_MODEL_ALIASES.get(model)
    if not target_model:
        target_model = model.split("/", 1)[1] if "/" in model else model
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if organisation_id:
        headers["X-Organization"] = organisation_id

    body: dict[str, object] = {
        "model": target_model,
        "messages": messages,
    }
    if temperature is not None:
        body["temperature"] = max(0.0, min(temperature, 2.0))

    url = "https://api.mistral.ai/v1/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        if stream:
            body["stream"] = True
            try:
                async with client.stream("POST", url, headers=headers, json=body) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line.split("data:", 1)[1].strip()
                        if payload in ("", "[DONE]"):
                            if payload == "[DONE]":
                                break
                            continue
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choices = data.get("choices")
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield content
            except httpx.HTTPStatusError as exc:
                message, code = extract_http_error(
                    exc.response,
                    default_message="Mistral API responded with an error",
                    default_code="mistral_error",
                )
                raise api_error(message, status_code=exc.response.status_code, code=code) from exc
            except httpx.RequestError as exc:
                raise api_error(
                    f"Failed to reach Mistral API: {exc}",
                    status_code=502,
                    code="mistral_unreachable",
                ) from exc
        else:
            try:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                message, code = extract_http_error(
                    exc.response,
                    default_message="Mistral API responded with an error",
                    default_code="mistral_error",
                )
                raise api_error(message, status_code=exc.response.status_code, code=code) from exc
            except httpx.RequestError as exc:
                raise api_error(
                    f"Failed to reach Mistral API: {exc}",
                    status_code=502,
                    code="mistral_unreachable",
                ) from exc

            data = response.json()
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if content:
                    yield content


async def _stream_gemini(
    model: str,
    messages: List[dict[str, str]],
    *,
    api_key: str,
    temperature: Optional[float],
    stream: bool,
    timeout: int,
) -> AsyncGenerator[str, None]:
    target_model = model.split("/", 1)[1] if "/" in model else model
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent"

    contents: List[dict[str, object]] = []
    for message in messages:
        role = message.get("role", "user")
        if role == "assistant":
            mapped_role = "model"
        else:
            mapped_role = "user"
        content_text = message.get("content") or ""
        if not content_text:
            continue
        parts = [{"text": content_text}]
        contents.append({"role": mapped_role, "parts": parts})

    if not contents:
        raise api_error("Messages cannot be empty", status_code=422, code="missing_messages")

    body: dict[str, object] = {
        "contents": contents,
    }
    if temperature is not None:
        body["generationConfig"] = {
            "temperature": max(0.0, min(temperature, 2.0)),
        }

    params = {"key": api_key}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.post(url, params=params, json=body)
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
            return
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [part.get("text", "") for part in parts if part.get("text")]
        text = "".join(texts)
        if text:
            yield text


def _extract_ollama_text(content: Optional[object]) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text") or item.get("content")
                if text_value:
                    fragments.append(str(text_value))
            elif isinstance(item, str):
                fragments.append(item)
        return "".join(fragments)
    if isinstance(content, dict):
        text_value = content.get("text") or content.get("content")
        if isinstance(text_value, str):
            return text_value
    return str(content)
