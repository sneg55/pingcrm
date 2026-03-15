#!/bin/bash
# Soft-fail check: warn if `except Exception` (or `except Exception as e`) is found
# without a logger call on the immediately following non-blank line.
#
# Acceptable patterns on the next non-blank line:
#   logger.<level>(...)   log.<level>(...)
#   raise                 (re-raise is fine)
#   pass  # intentional   (explicitly documented bare pass)
#
# Exit code is always 0 (soft-fail) so CI is not blocked.
#
# Uses Python for reliability (bash line-by-line iteration is fragile on large files).

python3 - <<'PYEOF'
import re
import sys
from pathlib import Path

EXCEPT_RE = re.compile(r'^\s*except Exception(\s+as\s+\w+)?\s*:')
ACCEPTABLE_RE = re.compile(
    r'logger\.(exception|warning|error|info|debug)'
    r'|log\.(exception|warning|error|info|debug)'
    r'|raise(\s|$)'
    r'|pass\s*#.*intentional',
    re.IGNORECASE,
)

found = 0
root = Path('backend/app')
for path in sorted(root.rglob('*.py')):
    if '__pycache__' in path.parts:
        continue
    lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    for i, line in enumerate(lines):
        if not EXCEPT_RE.match(line):
            continue
        # Find the next non-blank line (look ahead up to 3 lines)
        next_line = ''
        for j in range(i + 1, min(i + 4, len(lines))):
            candidate = lines[j].strip()
            if candidate:
                next_line = candidate
                break
        if not ACCEPTABLE_RE.search(next_line):
            lineno = i + 1
            preview = next_line[:60]
            print(f'WARNING: {path}:{lineno} — except Exception without logging (next: {preview})')
            print(f'::warning file={path},line={lineno}::except Exception without logging')
            found += 1

if found:
    print()
    print(f'{found} except Exception block(s) are missing logger calls.')
    print('See Exception Handling Policy in CLAUDE.md for guidance.')
PYEOF

exit 0  # soft-fail: advisory only, does not block CI
