#!/bin/sh
set -e

# Only run migrations when starting the API server
if [ "$1" = "uvicorn" ]; then
    echo "Running database migrations..."
    alembic upgrade head
fi

exec "$@"
