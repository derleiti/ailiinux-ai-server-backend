from __future__ import annotations

import sys
import os

# Add the virtual environment's site-packages directory to the sys.path
# This is a workaround for an environment issue where the uvicorn process
# is not correctly using the virtual environment.
venv_path = '/root/ailinux-ai-server-backend/.venv/lib/python3.12/site-packages'
if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

import time
import asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routes import agents, chat, crawler, models, sd, vision, posts
from .config import get_settings
from .services.crawler import crawler_manager
from .services.auto_publisher import auto_publisher
from .services.auto_crawler import auto_crawler


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AILinux AI Service", version="1.0.0")

    import logging
    main_logger = logging.getLogger("ailinux.main") # Define a logger for main.py
    main_logger.setLevel(logging.INFO) # Set its level to INFO

    crawler_logger = logging.getLogger("ailinux.crawler")
    crawler_logger.setLevel(logging.DEBUG)
    main_logger.info(f"Crawler logger level set to: {crawler_logger.level} (DEBUG={logging.DEBUG})") # Use main_logger

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
    app.include_router(posts.router, prefix="/v1")
    # app.include_router(gemini.router, prefix="/v1")

    if settings.crawler_enabled:
        @app.on_event("startup")
        async def _start_crawler() -> None:  # pragma: no cover - integration behaviour
            try:
                main_logger.info("Crawler startup event triggered.") # New INFO message
                await crawler_manager.start()
                asyncio.create_task(crawler_manager.flush_hourly())
                asyncio.create_task(crawler_manager.compact_spool())

                # Start auto-publisher für WordPress
                main_logger.info("Starting auto-publisher for WordPress...")
                await auto_publisher.start()

                # Start 24/7 auto-crawler für AI/Tech/Media/Games/Linux/Coding/Windows
                main_logger.info("Starting 24/7 auto-crawler for all categories...")
                await auto_crawler.start()
            except Exception as exc:
                main_logger.error("Error during crawler startup: %s", exc, exc_info=True)
                # Optionally re-raise or set an app-level flag to indicate startup failure

    @app.on_event("shutdown")
    async def _stop_crawler() -> None:  # pragma: no cover
        await crawler_manager.stop()
        await crawler_manager.shutdown_flush()
        await auto_publisher.stop()
        await auto_crawler.stop()

    @app.get("/health")
    async def health_check() -> dict[str, object]:
        return {"ok": True, "ts": int(time.time())}

    @app.post("/v1/auto-publisher/trigger")
    async def trigger_auto_publisher() -> dict[str, str]:
        """Manually trigger auto-publisher to process crawl results immediately."""
        if not settings.crawler_enabled:
            return {"status": "error", "message": "Crawler/Auto-Publisher nicht aktiviert"}

        try:
            main_logger.info("Manual auto-publisher trigger via API")
            await auto_publisher._process_hourly()
            return {"status": "success", "message": "Auto-Publisher manuell ausgeführt"}
        except Exception as exc:
            main_logger.error("Error during manual auto-publisher trigger: %s", exc)
            return {"status": "error", "message": f"Fehler: {str(exc)}"}

    @app.get("/v1/auto-crawler/status")
    async def get_auto_crawler_status() -> dict[str, object]:
        """Get status of 24/7 auto-crawler for all categories."""
        if not settings.crawler_enabled:
            return {"status": "disabled", "message": "Crawler nicht aktiviert"}

        try:
            status = await auto_crawler.get_status()
            return {"status": "running", "categories": status}
        except Exception as exc:
            main_logger.error("Error getting auto-crawler status: %s", exc)
            return {"status": "error", "message": str(exc)}

    @app.get("/dummy")
    async def dummy_route() -> dict[str, object]:
        return {"dummy": "route"}

    return app


app = create_app()
