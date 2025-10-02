from __future__ import annotations
from typing import AsyncGenerator, List, Literal, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fastapi_limiter.depends import RateLimiter

from ..services import chat as chat_service
from ..services.model_registry import registry
from ..utils.errors import api_error
from ..utils.throttle import request_slot

router = APIRouter(tags=["chat"])

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(..., min_length=1)

class ChatRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = True
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)

async def _chat_generator(payload: ChatRequest) -> AsyncGenerator[str, None]:
    model = await registry.get_model(payload.model)
    if not model or "chat" not in model.capabilities:
        raise api_error("Requested model does not support chat", status_code=404, code="model_not_found")

    async with request_slot():
        async for chunk in chat_service.stream_chat(
            model,
            payload.model,
            (m.model_dump() for m in payload.messages),
            stream=payload.stream,
            temperature=payload.temperature,
        ):
            if chunk:
                yield chunk

@router.post("/chat/completions", dependencies=[Depends(RateLimiter(times=5, seconds=10))])
async def chat_completions(payload: ChatRequest):
    if not payload.messages:
        raise api_error("At least one message is required", status_code=422, code="missing_messages")

    if payload.stream:
        return StreamingResponse(_chat_generator(payload), media_type="text/plain")

    collected: List[str] = []
    async for chunk in _chat_generator(payload):
        collected.append(chunk)
    return {"text": "".join(collected)}