from contextlib import asynccontextmanager
import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from kombu import Connection
from sqlalchemy import text

from app.api.routes import router as document_router
from app.core.config import get_settings
from app.db.session import SessionLocal


settings = get_settings()
logger = logging.getLogger("uvicorn.error")
logger.setLevel(logging.INFO)
static_dir = Path(__file__).resolve().parents[1] / "web" / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

app.include_router(document_router)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.middleware("http")
async def add_request_id(
    request: Request,
    call_next,
) -> Response:
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    started_at = perf_counter()

    try:
        response = await call_next(request)
        return response

    finally:
        duration_ms = round((perf_counter() - started_at) * 1000, 2)
        status_code = getattr(locals().get("response"), "status_code", 500)

        logger.info(
            (
                "request completed request_id=%s method=%s path=%s "
                "status_code=%s duration_ms=%s"
            ),
            request_id,
            request.method,
            request.url.path,
            status_code,
            duration_ms,
        )

        if "response" in locals():
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))

    with Connection(
        settings.celery_broker_url,
        connect_timeout=settings.health_broker_timeout_seconds,
    ) as connection:
        connection.ensure_connection(max_retries=1)

    return {"status": "ready"}
