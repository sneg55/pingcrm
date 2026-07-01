import asyncio
from logging.config import fileConfig

# app.models is imported for its side effect: registering every model on
# Base.metadata so Alembic autogenerate can detect them.
import app.models  # noqa: F401
from alembic import context
from app.core.config import settings
from app.core.database import Base
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

# Source the database URL from the application settings so migrations use the
# exact same configuration as the app. pydantic-settings resolves real
# environment variables first (e.g. the DATABASE_URL injected by docker compose),
# then falls back to the .env file, then to the default. This keeps a single
# source of truth and also applies the +asyncpg driver normalisation defined on
# Settings.DATABASE_URL.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
