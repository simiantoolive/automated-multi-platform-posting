"""Original assignment route plus the separately documented convenience API."""
from uuid import uuid4
from fastapi import APIRouter, Request
from app.schemas import PostingRequest, PostingResponse, PublishRequest
from app.services.posting_service import publish_all

router = APIRouter()


@router.get("/health", tags=["Operations"])
async def health(request: Request):
    return {"status": "ok", "mode": request.app.state.settings.publish_mode}


@router.post("/posting", response_model=PostingResponse, tags=["Assignment"])
async def posting(body: PostingRequest, request: Request):
    """Original contract: single message with one embedded CTA, all five platforms."""
    return await publish_all(request.app.state.settings, request.app.state.http,
                             body.message, None, str(uuid4()))


@router.post("/api/v1/publish", response_model=PostingResponse, tags=["Publishing"])
async def publish(body: PublishRequest, request: Request):
    """Combined message + space + CTA URL must be at most 200 characters."""
    return await publish_all(request.app.state.settings, request.app.state.http,
                             body.content, body.platforms, str(uuid4()))
