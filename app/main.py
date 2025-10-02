from __future__ import annotations
import asyncio, logging, time
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
import redis.asyncio as redis

from app.config import get_settings
from app.utils.logging_middleware import LoggingMiddleware

# Routers
from app.routes import health, admin, mcp, orchestration
from app.routes import models, agents, chat, vision, sd, crawler, posts


def create_app() -> FastAPI:
    settings = get_settings() # Moved inside create_app
    app = FastAPI(title="AILinux AI Server Backend", description="AI-powered services for AILinux", version="0.1.0")

    # Middlewares
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins.split(","), # Split the string into a list
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exceptions → einheitliche Fehlerform
    @app.exception_handler(HTTPException)
    async def handle_http_exception(_: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "error" in detail:
            payload = detail
        else:
            message = detail if isinstance(detail, str) else "Unexpected error"
            payload = {"error": {"message": message, "code": "http_error"}}
        return JSONResponse(status_code=exc.status_code, content=payload)

    # Startup/Shutdown
    @app.on_event("startup")
    async def on_startup():
        redis_connection = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True) # Changed to lowercase
        await FastAPILimiter.init(redis_connection)

    @app.on_event("shutdown")
    async def on_shutdown():
        # Falls du Background-Tasks/Crawler stoppst → hier sauber schließen
        pass

    # Routers (prefix /v1, wo sinnvoll)
    app.include_router(health.router)  # /health
    app.include_router(admin.router)
    app.include_router(mcp.router)  # /mcp
    app.include_router(orchestration.router)

    app.include_router(models.router, prefix="/v1")
    app.include_router(agents.router, prefix="/v1")
    app.include_router(chat.router, prefix="/v1")
    app.include_router(vision.router, prefix="/v1")
    app.include_router(sd.router, prefix="/v1")
    app.include_router(crawler.router, prefix="/v1")
    app.include_router(posts.router, prefix="/v1")

    return app

# Export für Uvicorn & für from .main import create_app/app:
app = create_app()
