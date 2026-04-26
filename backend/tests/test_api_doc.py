"""Pre-push guard: docs/docs/api-reference.md stays in sync with OpenAPI."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_api_doc.py"


def test_api_reference_matches_openapi() -> None:
    """Every FastAPI route appears in the public API reference table.

    Run the standalone script as a subprocess so the assertion mirrors what
    contributors invoke from the command line.
    """
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=backend,
        env={"PYTHONPATH": str(backend), **__import__("os").environ},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "API reference is out of sync with OpenAPI:\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
