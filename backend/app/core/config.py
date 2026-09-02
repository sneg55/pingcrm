from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/pingcrm"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _ensure_asyncpg_driver(cls, v: str) -> str:
        # Managed Postgres providers (Render, Railway, DO, Heroku) emit
        # postgres:// or postgresql:// URLs; SQLAlchemy's async engine needs
        # the +asyncpg driver tag.
        if isinstance(v, str):
            if v.startswith("postgres://"):
                v = "postgresql://" + v[len("postgres://"):]
            if v.startswith("postgresql://") and "+asyncpg" not in v:
                v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ENVIRONMENT: str = "development"  # Set to "production" in production deployments
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # PingCRM is single-player: there is no reason for the public internet to be
    # able to create accounts. Defaults to off so a deployment is closed even if
    # nobody remembers to plumb the env var through docker-compose.prod.yml.
    ALLOW_REGISTRATION: bool = False

    # Fixed-window throttles on the unauthenticated auth endpoints, keyed by client IP.
    AUTH_RATE_LIMIT_ENABLED: bool = True
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 10
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900  # 15 minutes
    REGISTER_RATE_LIMIT_ATTEMPTS: int = 5
    REGISTER_RATE_LIMIT_WINDOW_SECONDS: int = 3600  # 1 hour

    # Number of reverse proxies between the internet and this app. Production is
    # a single Caddy container, so 1. Client IPs are read this many hops from the
    # *right* of X-Forwarded-For; anything further left is caller-supplied and
    # must never be trusted for throttling. Raise this only if you add proxies
    # (e.g. Cloudflare in front of Caddy would make it 2).
    TRUSTED_PROXY_HOPS: int = 1

    # Per-user throttle on endpoints that call the Anthropic API, so a stolen
    # token cannot run up an unbounded bill.
    LLM_RATE_LIMIT_ENABLED: bool = True
    LLM_RATE_LIMIT_ATTEMPTS: int = 30
    LLM_RATE_LIMIT_WINDOW_SECONDS: int = 3600  # 1 hour

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/google/callback"

    TWITTER_API_KEY: str = ""
    TWITTER_API_SECRET: str = ""
    TWITTER_CLIENT_ID: str = ""
    TWITTER_CLIENT_SECRET: str = ""
    TWITTER_REDIRECT_URI: str = "http://localhost:3000/auth/twitter/callback"

    ANTHROPIC_API_KEY: str = ""

    TELEGRAM_API_ID: int = 0
    TELEGRAM_API_HASH: str = ""

    TWITTER_BEARER_TOKEN: str = ""

    APOLLO_API_KEY: str = ""

    MAPBOX_SECRET_TOKEN: str = ""  # server-side geocoding
    MAPBOX_PUBLIC_TOKEN: str = ""  # surfaced to browser for map tiles

    ENCRYPTION_KEY: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    CHROME_EXTENSION_ID: str = ""

    WHATSAPP_SIDECAR_URL: str = "http://localhost:3001"
    WHATSAPP_WEBHOOK_SECRET: str = ""

    # env_ignore_empty: an empty environment variable means "not configured",
    # not "the empty value". Docker Compose writes every `VAR: ${VAR:-}` entry as
    # an empty string rather than omitting it, so any optional credential the
    # operator left blank arrives as "". Without this, blank non-string settings
    # (e.g. TELEGRAM_API_ID) fail validation and crash startup instead of falling
    # back to their defaults.
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)


settings = Settings()
