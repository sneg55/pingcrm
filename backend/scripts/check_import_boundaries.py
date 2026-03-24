#!/usr/bin/env python3
"""Advisory check: API routes should not import directly from integrations."""
import ast
import os
import sys

violations = []
for root, dirs, files in os.walk("app/api"):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        filepath = os.path.join(root, fn)
        with open(filepath) as f:
            tree = ast.parse(f.read(), filepath)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                if "app.integrations" in module:
                    violations.append(f"  {filepath}:{node.lineno} imports {module}")

if violations:
    print(f"Advisory: {len(violations)} direct api->integrations import(s):")
    for v in violations:
        print(v)
else:
    print("OK: no direct api->integrations imports found.")

# Always exit 0 — this is advisory only
sys.exit(0)
