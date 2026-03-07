import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.contacts import router as contacts_router
from app.api.identity import router as identity_router
from app.api.interactions import router as interactions_router
from app.api.suggestions import router as suggestions_router
from app.api.telegram import router as telegram_router
from app.api.notifications import router as notifications_router
from app.api.twitter import router as twitter_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from app.core.config import settings

    if not settings.SECRET_KEY or settings.SECRET_KEY == "change-me-in-production":
        raise RuntimeError(
            "SECRET_KEY is not set or uses the insecure default. "
            "Set a strong random value in your .env file."
        )
    logger.info("Ping CRM API starting up...")
    yield
    logger.info("Ping CRM API shutting down.")


app = FastAPI(
    title="Ping CRM API",
    description="AI-powered networking assistant backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(contacts_router)
app.include_router(interactions_router)
app.include_router(auth_router)
app.include_router(suggestions_router)
app.include_router(telegram_router)
app.include_router(identity_router)
app.include_router(twitter_router)
app.include_router(notifications_router)

# Serve uploaded avatars
_avatars_dir = Path("static/avatars")
_avatars_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/api/health", tags=["health"])
async def health_check() -> dict:
    return {"status": "ok", "service": "pingcrm-api"}
