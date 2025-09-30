from __future__ import annotations

import time
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes import agents, chat, crawler, models, sd, vision, gemini
from .config import get_settings
from .services.crawler import crawler_manager


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AILinux AI Service", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-AILinux-Client"],
        allow_credentials=False,
    )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            payload = detail
        else:
            message = detail if isinstance(detail, str) else "Unexpected error"
            payload = {"error": {"message": message, "code": "http_error"}}
        return JSONResponse(status_code=exc.status_code, content=payload)

    app.include_router(models.router, prefix="/v1")
    app.include_router(agents.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    app.include_router(vision.router, prefix="/v1")
    app.include_router(sd.router, prefix="/v1")
    app.include_router(crawler.router, prefix="/v1")
    app.include_router(gemini.router, prefix="/v1")

    if settings.crawler_enabled:
        @app.on_event("startup")
        async def _start_crawler() -> None:  # pragma: no cover - integration behaviour
            await crawler_manager.start()
            asyncio.create_task(crawler_manager.flush_hourly())
            asyncio.create_task(crawler_manager.compact_spool())

        @app.on_event("shutdown")
        async def _stop_crawler() -> None:  # pragma: no cover
            await crawler_manager.stop()
            await crawler_manager.shutdown_flush()

    @app.get("/health")
    async def health_check() -> dict[str, object]:
        return {"ok": True, "ts": int(time.time())}

    return app


app = create_app()
