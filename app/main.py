"""Application factory with one pooled async HTTP client per process."""
from contextlib import asynccontextmanager
import logging
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.accounts import router as accounts_router, SessionStore, HideCallbackQuery
from app.api.routes import router
from app.config import Settings


def create_app(settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        # Do not emit raw request URLs, auth headers, payloads or exception strings.
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        access_logger = logging.getLogger("uvicorn.access")
        query_filter = HideCallbackQuery()
        access_logger.addFilter(query_filter)
        async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, follow_redirects=False,
                                     transport=transport, limits=httpx.Limits(max_connections=20)) as client:
            application.state.http = client
            yield
        access_logger.removeFilter(query_filter)

    application = FastAPI(title="Automated Multi-Platform Posting", version="2.0.0",
                          description="Real adapters and explicitly labelled offline simulation.",
                          lifespan=lifespan)
    application.state.settings = settings
    application.state.sessions = SessionStore()
    application.include_router(router)
    application.include_router(accounts_router)
    static = Path(__file__).resolve().parent / "static"
    application.mount("/static", StaticFiles(directory=static), name="static")

    @application.get("/", include_in_schema=False)
    async def account_page():
        return FileResponse(static / "index.html", headers={"Cache-Control": "no-store"})

    @application.middleware("http")
    async def privacy_headers(request, call_next):
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path == "/" or request.url.path.startswith("/ui/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    return application


app = create_app()
