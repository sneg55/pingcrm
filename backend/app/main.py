import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.api.auth import router as auth_router
from app.api.contacts import router as contacts_router
from app.api.identity import router as identity_router
from app.api.interactions import router as interactions_router
from app.api.suggestions import router as suggestions_router
from app.api.telegram import router as telegram_router
from app.api.notifications import router as notifications_router
from app.api.twitter import router as twitter_router
from app.api.organizations import router as organizations_router
from app.api.settings import router as settings_router
from app.api.linkedin import router as linkedin_router
from app.api.activity import router as activity_router
from app.api.extension import router as extension_router

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    if (
        not settings.SECRET_KEY
        or settings.SECRET_KEY == "change-me-in-production"
        or len(settings.SECRET_KEY) < 32
    ):
        raise RuntimeError(
            "SECRET_KEY is not set or uses the insecure default. "
            "Set a strong random value in your .env file."
        )
    if not settings.ENCRYPTION_KEY:
        env = getattr(settings, "ENVIRONMENT", "production")
        if env == "production":
            raise RuntimeError(
                "ENCRYPTION_KEY is not set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        else:
            logger.warning(
                "ENCRYPTION_KEY is not set. Encrypted fields will not work. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
    logger.info("PingCRM API starting up...")
    yield
    logger.info("PingCRM API shutting down.")


app = FastAPI(
    title="PingCRM API",
    description="AI-powered networking assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

cors_origins = list(settings.CORS_ORIGINS)
if settings.CHROME_EXTENSION_ID:
    cors_origins.append(f"chrome-extension://{settings.CHROME_EXTENSION_ID}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestCorrelationMiddleware)

app.include_router(contacts_router)
app.include_router(interactions_router)
app.include_router(auth_router)
app.include_router(suggestions_router)
app.include_router(telegram_router)
app.include_router(identity_router)
app.include_router(twitter_router)
app.include_router(notifications_router)
app.include_router(organizations_router)
app.include_router(settings_router)
app.include_router(linkedin_router)
app.include_router(activity_router)
app.include_router(extension_router)

# Serve uploaded avatars
_static_dir = Path(__file__).resolve().parent.parent / "static"
_avatars_dir = _static_dir / "avatars"
_avatars_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Log HTTP exceptions with structured context."""
    if exc.status_code >= 500:
        logger.error(
            "http_error %s %s %d",
            request.method,
            request.url.path,
            exc.status_code,
            extra={
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": exc.status_code,
                "error_detail": str(exc.detail),
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — log full traceback."""
    logger.exception(
        "unhandled_error %s %s: %s",
        request.method,
        request.url.path,
        exc,
        extra={
            "http_method": request.method,
            "http_path": request.url.path,
            "http_status": 500,
            "exception_type": type(exc).__name__,
        },
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


class FrontendErrorReport(BaseModel):
    message: str
    source: str | None = None
    lineno: int | None = None
    colno: int | None = None
    stack: str | None = None
    url: str | None = None
    component: str | None = None

_frontend_logger = logging.getLogger("app.frontend")


@app.post("/api/v1/errors", tags=["errors"])
async def report_frontend_error(report: FrontendErrorReport) -> dict:
    """Receive client-side errors and log them in the structured backend log."""
    _frontend_logger.error(
        "frontend_error: %s",
        report.message,
        extra={
            "error_source": report.source,
            "error_lineno": report.lineno,
            "error_colno": report.colno,
            "error_stack": report.stack,
            "error_url": report.url,
            "error_component": report.component,
            "origin": "frontend",
        },
    )
    return {"data": {"received": True}, "error": None}


@app.get("/api/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "service": "pingcrm-api"}
