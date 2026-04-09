#!/usr/bin/env python3
"""CI guard: ensure all API endpoints have response_model declared.

Usage: python scripts/check_response_models.py
Exit code 0 if all endpoints have response_model, 1 otherwise.
"""
import sys
from app.main import fastapi_app as app


def main() -> int:
    missing = []
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "endpoint"):
            continue
        path = getattr(route, "path", "")
        if not path.startswith("/api/v1/"):
            continue
        # Skip health check
        if path == "/api/health":
            continue
        response_model = getattr(route, "response_model", None)
        if response_model is None:
            methods = sorted(route.methods - {"HEAD", "OPTIONS"})
            for method in methods:
                missing.append(f"  {method:6s} {path}")

    if missing:
        print(f"ERROR: {len(missing)} endpoint(s) missing response_model:")
        for m in missing:
            print(m)
        print("\nAdd response_model=Envelope[...] to each endpoint decorator.")
        return 1
    else:
        print(f"OK: all API endpoints have response_model declared.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
