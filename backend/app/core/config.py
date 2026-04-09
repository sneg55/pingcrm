from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/pingcrm"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ENVIRONMENT: str = "development"  # Set to "production" in production deployments
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

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

    ENCRYPTION_KEY: str = ""

    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    CHROME_EXTENSION_ID: str = ""

    WHATSAPP_SIDECAR_URL: str = "http://localhost:3001"
    WHATSAPP_WEBHOOK_SECRET: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
