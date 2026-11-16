"""Concurrent fan-out, independent failures and safe structured logging."""
import asyncio
import logging
from datetime import datetime, timezone
import httpx
from app.config import Settings
from app.errors import error_detail
from app.platforms.base import Platform
from app.platforms.facebook import Facebook
from app.platforms.linkedin import LinkedIn
from app.platforms.x import X
from app.platforms.mastodon import Mastodon
from app.platforms.bluesky import Bluesky
from app.platforms.mock import MockAdapter
from app.schemas import PLATFORM_NAMES, PlatformName, PlatformResult, PostingResponse

logger = logging.getLogger("publisher")
ADAPTERS = {"facebook": Facebook, "linkedin": LinkedIn, "x": X, "mastodon": Mastodon, "bluesky": Bluesky}


def successful_result(platform, published):
    now = datetime.now(timezone.utc)
    return PlatformResult(platform=platform.name, status="success", mode="real",
                          post_id=published.post_id, posted_url=published.url,
                          url_source=published.url_source, warnings=list(published.warnings),
                          date=now.date().isoformat(), time=now.strftime("%H:%M:%SZ"),
                          timestamp_source="api_acknowledged_at")


async def post_one(platform: Platform, client: httpx.AsyncClient, message: str,
                   settings: Settings, request_id: str) -> PlatformResult:
    try:
        async with asyncio.timeout(settings.platform_timeout_seconds):
            published = await platform.publish(client, message)
        result = successful_result(platform, published)
    except Exception as exc:
        acknowledged = getattr(platform, "acknowledged", None)
        result = (successful_result(platform, acknowledged) if acknowledged is not None else
                  PlatformResult(platform=platform.name, status="failed", mode="real", error=error_detail(exc)))
    logger.info("request_id=%s platform=%s mode=real status=%s error_code=%s",
                request_id, result.platform, result.status, result.error.code if result.error else "none")
    return result


async def publish_all(settings: Settings, client: httpx.AsyncClient, message: str,
                      selected: list[PlatformName] | None, request_id: str) -> PostingResponse:
    names = selected if selected is not None else PLATFORM_NAMES
    if settings.publish_mode == "mock":
        results = await asyncio.gather(*(MockAdapter(name).simulate() for name in names))
        logger.info("request_id=%s mode=mock simulated_count=%d published_count=0", request_id, len(results))
    else:
        results = await asyncio.gather(*(post_one(ADAPTERS[name](settings), client, message, settings, request_id)
                                         for name in names))
    successes = sum(result.status == "success" for result in results)
    failures = sum(result.status == "failed" for result in results)
    simulations = sum(result.status == "simulated" for result in results)
    return PostingResponse(request_id=request_id, mode=settings.publish_mode,
                           success=successes == len(results), success_count=successes,
                           failure_count=failures, simulated_count=simulations, total_count=len(results),
                           results=results)
