from __future__ import annotations

import json
import re
import asyncio
from typing import AsyncGenerator, Iterable, List, Optional

import httpx
from pydantic import AnyHttpUrl
import google.generativeai as genai

from ..config import get_settings
from ..services.model_registry import ModelInfo
from ..utils.errors import api_error
from ..utils.http import extract_http_error
from . import web_search
from .crawler.manager import crawler_manager

logger = __import__("logging").getLogger("ailinux.chat")

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

CRAWLER_PHRASES = [
    "crawl",
    "website",
    "link",
    "discover",
    "explore",
    "search website",
    "analyze website",
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
    elif model.provider == "gpt-oss":
        if not settings.gpt_oss_api_key or not settings.gpt_oss_base_url:
            raise api_error("GPT-OSS support is not configured (missing API key or base URL)", status_code=503, code="gpt_oss_unavailable")
        async for chunk in _stream_gpt_oss(
            request_model,
            messages,
            api_key=settings.gpt_oss_api_key,
            base_url=settings.gpt_oss_base_url,
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
    user_query = formatted_messages[-1]["content"]

    # Get initial response
    initial_response = await _get_initial_response(model, request_model, formatted_messages, temperature, settings)

    # Check for uncertainty (web search)
    if any(phrase in initial_response.lower() for phrase in UNCERTAINTY_PHRASES):
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
        logger.debug("Web search augmented messages length: %d", len(json.dumps(augmented_messages)))

        try:
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
            elif model.provider == "gpt-oss":
                if not settings.gpt_oss_api_key:
                    raise api_error("GPT-OSS support is not configured", status_code=503, code="gpt_oss_unavailable")
                async for chunk in _stream_gpt_oss(
                    request_model,
                    augmented_messages,
                    api_key=settings.gpt_oss_api_key,
                    base_url=settings.gpt_oss_base_url,
                    temperature=temperature,
                    stream=stream,
                    timeout=settings.request_timeout,
                ):
                    yield chunk
        except Exception as exc:
            logger.error("Error during web search augmented chat streaming: %s", exc)
            raise
    # Check for crawler phrases
    elif any(phrase in user_query.lower() for phrase in CRAWLER_PHRASES):
        yield "Okay, ich werde versuchen, die angeforderten Informationen zu crawlen...\n\n"
        
        # Extract potential URLs from the user query
        urls = re.findall(r"(https?://[^\s]+)", user_query)
        if not urls:
            yield "Ich konnte keine Links in Ihrer Anfrage finden, die ich crawlen könnte."
            return

        # Extract keywords from the user query (excluding URLs and crawler phrases)
        keywords = [word for word in user_query.lower().split() if word not in CRAWLER_PHRASES and not word.startswith("http")]
        if not keywords:
            keywords = ["information"] # Default keyword if none provided

        try:
            job = await crawler_manager.create_job(
                keywords=keywords,
                seeds=urls,
                max_depth=5,
                max_pages=50,
                allow_external=True,
                requested_by="chat_tool",
                user_context=user_query,
                ollama_assisted=True, # Enable Ollama assistance
                ollama_query=user_query, # Pass user query for Ollama analysis
            )
            yield f"Crawl job {job.id} gestartet. Status: {job.status}. Bitte warten Sie, während ich die Ergebnisse sammle.\n\n"

            # Poll job status until completed or failed
            job_status = job.status
            while job_status in ["queued", "running"]:
                await asyncio.sleep(5) # Poll every 5 seconds
                updated_job = await crawler_manager.get_job(job.id)
                if updated_job:
                    job_status = updated_job.status
                    yield f"Crawl job {job.id} Status: {job_status}. Seiten gecrawlt: {updated_job.pages_crawled}.\n"
                else:
                    yield f"Fehler: Crawl job {job.id} nicht gefunden.\n"
                    break
            
            if job_status == "completed" and updated_job and updated_job.results:
                yield "Crawling abgeschlossen. Ich analysiere die Ergebnisse...\n\n"
                
                crawl_results_context = "Gecrawlte Ergebnisse:\n"
                for result_id in updated_job.results[:3]: # Limit context to top 3 results
                    result = await crawler_manager.get_result(result_id)
                    if result:
                        title = result.title or "Kein Titel"
                        url = result.url or "Keine URL"
                        content_snippet = ""
                        if result.extracted_content_ollama: # Prioritize Ollama extracted content
                            content_snippet = result.extracted_content_ollama[:500] + "..." if len(result.extracted_content_ollama) > 500 else result.extracted_content_ollama
                            crawl_results_context += f"- Titel: {title}\n"
                            crawl_results_context += f"  URL: {url}\n"
                            crawl_results_context += f"  Extrahierter Inhalt (Ollama): {content_snippet}\n\n"
                        elif result.summary:
                            content_snippet = result.summary[:500] + "..." if len(result.summary) > 500 else result.summary
                            crawl_results_context += f"- Titel: {title}\n"
                            crawl_results_context += f"  URL: {url}\n"
                            crawl_results_context += f"  Zusammenfassung: {content_snippet}\n\n"
                        elif result.excerpt:
                            content_snippet = result.excerpt[:500] + "..." if len(result.excerpt) > 500 else result.excerpt
                            crawl_results_context += f"- Titel: {title}\n"
                            crawl_results_context += f"  URL: {url}\n"
                            crawl_results_context += f"  Auszug: {content_snippet}\n\n"

                augmented_messages = formatted_messages + [
                    {"role": "system", "content": "Hier ist Kontext aus einem Crawl-Job:"},
                    {"role": "system", "content": crawl_results_context},
                    {"role": "user", "content": f"Basierend auf den gecrawlten Ergebnissen, beantworten Sie bitte meine ursprüngliche Frage: {user_query}"}
                ]
                logger.debug("Crawler augmented messages length: %d", len(json.dumps(augmented_messages)))

                try:
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
                    elif model.provider == "gpt-oss":
                        if not settings.gpt_oss_api_key:
                            raise api_error("GPT-OSS support is not configured", status_code=503, code="gpt_oss_unavailable")
                        async for chunk in _stream_gpt_oss(
                            request_model,
                            augmented_messages,
                            api_key=settings.gpt_oss_api_key,
                            base_url=settings.gpt_oss_base_url,
                            temperature=temperature,
                            stream=stream,
                            timeout=settings.request_timeout,
                        ):
                            yield chunk
                except Exception as exc:
                    logger.error("Error during crawler augmented chat streaming: %s", exc)
                    raise
                # Successfully streamed augmented response, exit early
                return
            elif job_status == "failed":
                yield f"Crawl job {job.id} fehlgeschlagen: {updated_job.error or 'Unbekannter Fehler'}.\n"
                return
            else:
                # Provide more context when no relevant results are found
                if updated_job and updated_job.pages_crawled > 0:
                    yield f"Crawl job {job.id} abgeschlossen. Es wurden {updated_job.pages_crawled} Seiten gecrawlt, aber keine Ergebnisse, die direkt auf Ihre Anfrage passen, wurden gefunden. Versuchen Sie, Ihre Suchanfrage zu präzisieren oder andere Keywords zu verwenden.\n"
                else:
                    yield f"Crawl job {job.id} abgeschlossen, aber es wurden keine Seiten gecrawlt oder relevante Ergebnisse gefunden. Die angegebenen URLs waren möglicherweise nicht erreichbar oder enthielten keine durchsuchbaren Inhalte. Versuchen Sie, Ihre Anfrage zu überprüfen oder andere Links anzugeben.\n"
                return
        except Exception as exc:
            logger.error("Crawler tool failed: %s", exc)
            yield f"Entschuldigung, beim Starten des Crawl-Tools ist ein Fehler aufgetreten: {exc}.\n"
            return

    # Only yield initial response if crawler wasn't triggered
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
                        if payload in ( "", "[DONE]"):
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
    genai.configure(api_key=api_key)
    target_model = model.split("/", 1)[1] if "/" in model else model
    
    generation_config = None
    if temperature is not None:
        generation_config = genai.types.GenerationConfig(temperature=temperature)

    model = genai.GenerativeModel(target_model)
    
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

    if stream:
        response = await model.generate_content_async(contents, generation_config=generation_config, stream=True)
        async for chunk in response:
            if chunk.text:
                yield chunk.text
    else:
        response = await model.generate_content_async(contents, generation_config=generation_config, stream=False)
        if response.text:
            yield response.text


async def _stream_gpt_oss(
    model: str,
    messages: List[dict[str, str]],
    *,
    api_key: str,
    base_url: Optional[AnyHttpUrl],
    temperature: Optional[float],
    stream: bool,
    timeout: int,
) -> AsyncGenerator[str, None]:
    url = str(base_url.join("v1/chat/completions")) if base_url else "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    body: dict[str, object] = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        body["temperature"] = max(0.0, min(temperature, 2.0))

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
                        if payload in ( "", "[DONE]"):
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
                    default_message="GPT-OSS API responded with an error",
                    default_code="gpt_oss_error",
                )
                raise api_error(message, status_code=exc.response.status_code, code=code) from exc
            except httpx.RequestError as exc:
                raise api_error(
                    f"Failed to reach GPT-OSS API: {exc}",
                    status_code=502,
                    code="gpt_oss_unreachable",
                ) from exc
        else:
            try:
                response = await client.post(url, headers=headers, json=body)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                message, code = extract_http_error(
                    exc.response,
                    default_message="GPT-OSS API responded with an error",
                    default_code="gpt_oss_error",
                )
                raise api_error(message, status_code=exc.response.status_code, code=code) from exc
            except httpx.RequestError as exc:
                raise api_error(
                    f"Failed to reach GPT-OSS API: {exc}",
                    status_code=502,
                    code="gpt_oss_unreachable",
                ) from exc

            data = response.json()
            choices = data.get("choices") or []
            if choices:
                message = choices[0].get("message") or {}
                content = message.get("content")
                if content:
                    yield content


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