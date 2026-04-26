"""Diff OpenAPI paths against docs/docs/api-reference.md.

Exits non-zero on drift so it can gate CI / pre-push hooks. Run from the
backend directory:

    PYTHONPATH=. python3 scripts/check_api_doc.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fastapi.openapi.utils import get_openapi

from app.main import fastapi_app


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = REPO_ROOT / "docs" / "docs" / "api-reference.md"

# Endpoints intentionally omitted from public docs (internal / experimental).
SKIP_DOC_PATHS: set[tuple[str, str]] = set()

# Normalize path-parameter names so docs and OpenAPI compare structurally.
_PARAM_RE = re.compile(r"\{[^}]+\}")


def _normalize(path: str) -> str:
    return _PARAM_RE.sub("{}", path)


def _openapi_routes() -> set[tuple[str, str]]:
    schema = get_openapi(
        title=fastapi_app.title,
        version=fastapi_app.version,
        routes=fastapi_app.routes,
    )
    routes: set[tuple[str, str]] = set()
    for path, methods in schema["paths"].items():
        for method in methods:
            method_upper = method.upper()
            if method_upper in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                routes.add((method_upper, _normalize(path)))
    return routes


# Matches markdown rows like:  | GET | `/api/v1/foo/{bar}` | description |
_DOC_ROW_RE = re.compile(
    r"^\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|\s*`([^`]+)`\s*\|",
    re.MULTILINE,
)


def _doc_routes() -> set[tuple[str, str]]:
    text = DOC_PATH.read_text(encoding="utf-8")
    return {
        (method, _normalize(path))
        for method, path in _DOC_ROW_RE.findall(text)
    }


def main() -> int:
    openapi = _openapi_routes() - SKIP_DOC_PATHS
    documented = _doc_routes()

    missing_in_doc = openapi - documented
    extra_in_doc = documented - openapi

    if not missing_in_doc and not extra_in_doc:
        print(f"OK: all {len(openapi)} API routes are documented.")
        return 0

    if missing_in_doc:
        print("❌ Missing from docs/docs/api-reference.md:")
        for method, path in sorted(missing_in_doc):
            print(f"   {method:6s} {path}")
    if extra_in_doc:
        print("❌ Documented but not in OpenAPI (stale entry):")
        for method, path in sorted(extra_in_doc):
            print(f"   {method:6s} {path}")
    print(
        "\nFix by editing docs/docs/api-reference.md, or add the route to "
        "SKIP_DOC_PATHS in this script if it's intentionally undocumented."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
