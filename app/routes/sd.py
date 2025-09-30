from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services import sd as sd_service
from ..services.model_registry import registry
from ..utils.errors import api_error
from ..utils.throttle import request_slot

router = APIRouter(tags=["image_generation"])


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    negative_prompt: str = ""
    width: int = Field(512, ge=64, le=2048)
    height: int = Field(512, ge=64, le=2048)
    steps: int = Field(30, ge=1, le=150)
    seed: int = -1
    model: str


@router.post("/images/generate")
async def generate_image(payload: ImageGenerationRequest) -> dict[str, list[str]]:
    model = await registry.get_model(payload.model)
    if not model or "image_gen" not in model.capabilities:
        raise api_error("Requested model does not support image generation", status_code=404, code="model_not_found")

    async with request_slot():
        images = await sd_service.generate_image(payload.model_dump())
    return {"images": images}
