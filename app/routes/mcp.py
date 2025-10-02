from __future__ import annotations

import base64
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ..services.crawler.user_crawler import user_crawler
from ..services.crawler.manager import crawler_manager
from ..services.wordpress import wordpress_service
from ..services import chat as chat_service
from ..services.model_registry import registry
from ..utils.throttle import request_slot
from ..routes.admin_crawler import (
    CrawlerConfigUpdate,
    CrawlerConfigUpdateResponse,
    CrawlerControlRequest,
    control_crawler,
    get_crawler_config,
    update_crawler_config,
)

router = APIRouter()


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text.split()))


def _serialize_job(job) -> Dict[str, Any]:
    payload = job.to_dict()
    payload["allowed_domains"] = list(job.allowed_domains)
    return payload


async def handle_crawl_url(params: Dict[str, Any]) -> Dict[str, Any]:
    url = params.get("url")
    if not url:
        raise ValueError("'url' parameter is required for crawl.url")

    keywords = params.get("keywords")
    if keywords is not None and not isinstance(keywords, Iterable):
        raise ValueError("'keywords' must be an iterable of strings")

    job = await user_crawler.crawl_url(
        url=url,
        keywords=list(keywords) if keywords else None,
        max_pages=int(params.get("max_pages", 10)),
        idempotency_key=params.get("idempotency_key"),
    )
    return {"job": _serialize_job(job)}


async def handle_crawl_site(params: Dict[str, Any]) -> Dict[str, Any]:
    site_url = params.get("site_url")
    if not site_url:
        raise ValueError("'site_url' parameter is required for crawl.site")

    seeds = params.get("seeds") or [site_url]
    if not isinstance(seeds, Iterable):
        raise ValueError("'seeds' must be an iterable of URLs")

    keywords = params.get("keywords") or []
    if keywords and not isinstance(keywords, Iterable):
        raise ValueError("'keywords' must be iterable when provided")

    job = await crawler_manager.create_job(
        keywords=list(keywords) if keywords else [site_url],
        seeds=[str(seed) for seed in seeds],
        max_depth=int(params.get("max_depth", 2)),
        max_pages=int(params.get("max_pages", 40)),
        allow_external=bool(params.get("allow_external", False)),
        relevance_threshold=float(params.get("relevance_threshold", 0.35)),
        requested_by="mcp",
        priority=params.get("priority", "low"),
        idempotency_key=params.get("idempotency_key"),
    )
    return {"job": _serialize_job(job)}


async def handle_crawl_status(params: Dict[str, Any]) -> Dict[str, Any]:
    job_id = params.get("job_id")
    if not job_id:
        raise ValueError("'job_id' parameter is required for crawl.status")

    job = await user_crawler.get_job(job_id)
    source = "user"
    manager = user_crawler
    if not job:
        job = await crawler_manager.get_job(job_id)
        source = "manager"
        manager = crawler_manager
    if not job:
        raise ValueError(f"Crawler job '{job_id}' not found")

    include_results = params.get("include_results", False)
    include_content = params.get("include_content", False)
    results: List[Dict[str, Any]] = []
    if include_results:
        for result_id in job.results:
            result = await manager.get_result(result_id)  # type: ignore[attr-defined]
            if result:
                results.append(result.to_dict(include_content=include_content))

    payload = _serialize_job(job)
    payload["source"] = source
    payload["results"] = results
    return payload


async def handle_posts_create(params: Dict[str, Any]) -> Dict[str, Any]:
    title = params.get("title")
    content = params.get("content")
    status_value = params.get("status", "publish")
    categories = params.get("categories")
    featured_media = params.get("featured_media")

    if not title or not content:
        raise ValueError("'title' and 'content' are required for posts.create")

    result = await wordpress_service.create_post(
        title=title,
        content=content,
        status=status_value,
        categories=categories,
        featured_media=featured_media,
    )
    return result


async def handle_media_upload(params: Dict[str, Any]) -> Dict[str, Any]:
    file_data = params.get("file_data")
    filename = params.get("filename")
    content_type = params.get("content_type", "application/octet-stream")

    if not file_data or not filename:
        raise ValueError("'file_data' and 'filename' are required for media.upload")

    try:
        binary = base64.b64decode(file_data)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid base64 payload: {exc}") from exc

    result = await wordpress_service.upload_media(
        filename=filename,
        file_content=binary,
        content_type=content_type,
    )
    return result


async def handle_llm_invoke(params: Dict[str, Any]) -> Dict[str, Any]:
    model_id = params.get("model") or params.get("provider_id")
    messages = params.get("messages")
    options = params.get("options") or {}

    if not model_id or not messages:
        raise ValueError("'model' (or provider_id) and 'messages' are required for llm.invoke")
    if not isinstance(messages, list):
        raise ValueError("'messages' must be a list of role/content dictionaries")

    model = await registry.get_model(model_id)
    if not model or "chat" not in model.capabilities:
        raise ValueError(f"Model '{model_id}' does not support chat capability")

    formatted_messages: List[Dict[str, str]] = []
    for entry in messages:
        role = entry.get("role") if isinstance(entry, dict) else None
        content = entry.get("content") if isinstance(entry, dict) else None
        if not role or content is None:
            raise ValueError("Each message must include 'role' and 'content'")
        formatted_messages.append({"role": role, "content": content})

    temperature = options.get("temperature")
    stream = bool(options.get("stream", False))

    chunks: List[str] = []
    async with request_slot():
        async for chunk in chat_service.stream_chat(
            model,
            model_id,
            (message for message in formatted_messages),
            stream=stream,
            temperature=temperature,
        ):
            if chunk:
                chunks.append(chunk)

    completion = "".join(chunks)
    prompt_tokens = sum(_estimate_tokens(item["content"]) for item in formatted_messages)
    completion_tokens = _estimate_tokens(completion)

    return {
        "model": model_id,
        "provider": model.provider,
        "output": completion,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


async def handle_admin_control(params: Dict[str, Any]) -> Dict[str, Any]:
    action = params.get("action")
    instance = params.get("instance")
    if not action or not instance:
        raise ValueError("'action' and 'instance' parameters are required")
    request = CrawlerControlRequest(action=action, instance=instance)
    result = await control_crawler(request)
    return result


async def handle_admin_config_get(_: Dict[str, Any]) -> Dict[str, Any]:
    return await get_crawler_config()


async def handle_admin_config_set(params: Dict[str, Any]) -> Dict[str, Any]:
    allowed_fields = {"user_crawler_workers", "user_crawler_max_concurrent", "auto_crawler_enabled"}
    updates = {key: value for key, value in (params or {}).items() if key in allowed_fields}
    if not updates:
        raise ValueError("No allowed configuration fields provided")
    update_request = CrawlerConfigUpdate(**updates)
    response: CrawlerConfigUpdateResponse = await update_crawler_config(update_request)
    return {"updated": response.updated, "config": response.config.dict()}


Handler = Callable[[Dict[str, Any]], Awaitable[Any]]
MCP_HANDLERS: Dict[str, Handler] = {
    "crawl.url": handle_crawl_url,
    "crawl.site": handle_crawl_site,
    "crawl.status": handle_crawl_status,
    "posts.create": handle_posts_create,
    "media.upload": handle_media_upload,
    "llm.invoke": handle_llm_invoke,
    "admin.crawler.control": handle_admin_control,
    "admin.crawler.config.get": handle_admin_config_get,
    "admin.crawler.config.set": handle_admin_config_set,
}


@router.post("/mcp", tags=["MCP"], summary="JSON-RPC 2.0 endpoint for MCP communication")
async def mcp_endpoint(request: Request):
    try:
        body = await request.json()
        jsonrpc_version = body.get("jsonrpc")
        method = body.get("method")
        params = body.get("params", {})
        req_id = body.get("id")

        if jsonrpc_version != "2.0":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request", "data": "jsonrpc field must be '2.0'"}},
            )
        if not method:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request", "data": "method field is required"}},
            )

        handler = MCP_HANDLERS.get(method)
        if not handler:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"jsonrpc": "2.0", "error": {"code": -32601, "message": "Method not found", "data": f"Method '{method}' not supported"}},
            )

        result = await handler(params)
        return JSONResponse(content={"jsonrpc": "2.0", "result": result, "id": req_id})

    except ValueError as exc:
        return JSONResponse(
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": str(exc)}, "id": None},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except HTTPException as exc:
        return JSONResponse(content=exc.detail, status_code=exc.status_code)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        return JSONResponse(
            content={"jsonrpc": "2.0", "error": {"code": -32000, "message": "Internal Server Error", "data": str(exc)}, "id": None},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
