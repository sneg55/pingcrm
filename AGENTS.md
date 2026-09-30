# AGENTS.md

## Repo map
- PingCRM is split into `backend/` (FastAPI, PostgreSQL, Redis/Celery), `frontend/` (Next.js app), `landing/` (marketing Next.js app), `docs/` (Docusaurus), and `whatsapp-sidecar/` (Node WhatsApp Web service).
- Backend app wiring is in `backend/app/main.py`; Celery app and beat schedule are in `backend/app/core/celery_app.py`.
- Product requirements live in `mvp.md`; public API docs are in `docs/docs/api-reference.md`.

## Setup and services
- Full stack: copy `backend/.env.example` to `backend/.env`, copy `.env.docker.example` to `.env`, then run `docker compose up -d` from repo root.
- Host development normally needs only services from Docker: `docker compose up -d postgres redis`.
- Backend local setup: `cd backend && python3.12 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt -r requirements-test.txt && alembic upgrade head`.
- Frontend uses npm lockfiles, not pnpm/yarn: run `npm install` inside the package you edit.

## Development commands
- Backend dev server: `cd backend && uvicorn app.main:app --reload`.
- Frontend dev server: `cd frontend && npm run dev`.
- Landing dev server: `cd landing && npm run dev` (port 3001).
- Docs dev server: `cd docs && npm start`.
- Celery dev worker with beat: `cd backend && celery -A worker.celery_app worker --beat --loglevel=info`.

## Verification
- Backend tests require a real PostgreSQL database, defaulting to `postgresql+asyncpg://localhost:5432/pingcrm_test`; set `TEST_DATABASE_URL` or create `pingcrm_test`. Pytest runs with `-n auto`; use `pytest -n0` when debugging.
- Run one backend test with: `cd backend && pytest tests/path/test_file.py::test_name -n0`.
- Frontend: `cd frontend && npx tsc --noEmit && npm run lint && npm test`.
- Frontend focused test: `cd frontend && npx vitest run src/path/file.test.tsx`.
- Landing lint/build: `cd landing && npm run lint && npm run build`.
- Docs type/build: `cd docs && npm run typecheck && npm run build`.
- WhatsApp sidecar tests: `cd whatsapp-sidecar && npm test`.

## API and generated files
- Every FastAPI endpoint must declare `response_model=Envelope[...]`; check with `cd backend && PYTHONPATH=. python3 scripts/check_response_models.py`.
- After adding/changing API endpoints, regenerate OpenAPI then TS types:
  ```bash
  cd backend && PYTHONPATH=. python3 -c "import json; from app.main import app; from fastapi.openapi.utils import get_openapi; schema = get_openapi(title=app.title, version=app.version, routes=app.routes); open('openapi.json','w').write(json.dumps(schema, indent=2))"
  cd frontend && npm run generate:api
  ```
- If API routes changed, update `docs/docs/api-reference.md` and run `cd backend && PYTHONPATH=. python3 scripts/check_api_doc.py`.
- Frontend `as any` usage is guarded: run `cd frontend && bash scripts/check-as-any.sh` before/after TypeScript-heavy changes.

## Repo-specific gotchas
- New Celery task modules under `backend/app/services/task_jobs/` are not discovered unless re-exported from `backend/app/services/tasks.py` and included in `__all__`; Celery only includes `app.services.tasks`.
- Adding contact routes requires updating both snapshots in `backend/tests/test_route_inventory.py` (`expected` and `must_be_before_param`). Static routes must be registered before `/{contact_id}` or FastAPI will route them incorrectly.
- `backend/app/models/__init__.py` eagerly imports all models; avoid module-level service imports from files under `backend/app/models/` to prevent partial-init cycles. Lazy-import inside handlers/listeners instead.
- Do not add debug/temporary production endpoints unless explicitly asked.
- Twitter cron polling only checks bios via bird CLI; tweet fetching and LLM classification are on-demand for suggestion generation.
- LinkedIn sync is browser/extension driven; cookies stay client-side.

## Error handling and secrets
- No silent errors: when editing a file, fix bare `except:`, `except: pass`, empty `catch {}`, and catch-with-only-console.log in that file. Handlers must log context and either re-raise or return a sentinel; mark intentional silence with `# silent-ok` or `// silent-ok`.
- Never commit `.env`, OAuth credentials, API keys, cookies, or production SSH details. Production access details, if needed, are in untracked local files, not this repo.

## Git hooks
- `.githooks/pre-push` runs backend pytest for backend changes and frontend `tsc`, lint, and vitest for frontend changes; it uses `backend/.venv` if present.
- If you add backend test dependencies, also install them into `backend/.venv` or the hook may fail: `cd backend && source .venv/bin/activate && pip install -r requirements-test.txt`.
- Never use `--no-verify` unless explicitly instructed.
