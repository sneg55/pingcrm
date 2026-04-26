---
sidebar_position: 99
---

# Contributing

Thanks for your interest in contributing to PingCRM! See the full [CONTRIBUTING.md](https://github.com/sneg55/pingcrm/blob/main/CONTRIBUTING.md) for detailed instructions.

## Quick Start

The full Docker Compose stack is the fastest way to a working dev environment — see the [Setup Guide](./setup) for the recommended path. For pure-host development:

```bash
# Bring up just the supporting services
docker compose up -d postgres redis

# Backend
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install && npm run dev

# Tests
cd backend && pytest
cd frontend && npm test
```

## Pre-push hook

`.githooks/pre-push` runs the test suite (and the API-doc / response-model guards) before any push. It uses `backend/.venv`'s Python, so any new test dependency added to `requirements-test.txt` must also be installed in that venv:

```bash
cd backend && source .venv/bin/activate && pip install -r requirements-test.txt
```

Never push with `--no-verify` unless explicitly asked to.

## Pull Request Process

1. Fork the repo and create a branch from `main`
2. Make your changes with tests
3. Ensure `pytest` and `npm test` both pass
4. Run the API-doc guard if you touched any FastAPI route: `PYTHONPATH=. python3 scripts/check_api_doc.py`
5. Submit a PR with a clear description

## Code Style

- **Python:** snake_case, type hints, async where appropriate
- **TypeScript:** camelCase for variables/functions, PascalCase for components

See [CLAUDE.md](https://github.com/sneg55/pingcrm/blob/main/CLAUDE.md) for the full conventions guide.
