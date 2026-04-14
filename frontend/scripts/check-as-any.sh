#!/bin/bash
# CI guard: count "as any" usage in frontend source code.
# Reports the current count and fails if it increases above the baseline.
#
# Usage: bash scripts/check-as-any.sh
# Update BASELINE when intentionally adding/removing as-any casts.

BASELINE=101  # Updated 2026-04-14: +2 for TwitterBirdRow (cookies endpoints not yet in generated API types)

COUNT=$(grep -rn "as any" src/ --include="*.ts" --include="*.tsx" \
  | grep -v "node_modules" \
  | grep -v ".test." \
  | grep -v "__mocks__" \
  | wc -l | tr -d ' ')

echo "as any count: $COUNT (baseline: $BASELINE)"

if [ "$COUNT" -gt "$BASELINE" ]; then
  echo "ERROR: as any count increased from $BASELINE to $COUNT."
  echo "New as-any casts found:"
  grep -rn "as any" src/ --include="*.ts" --include="*.tsx" \
    | grep -v "node_modules" \
    | grep -v ".test." \
    | grep -v "__mocks__"
  echo ""
  echo "Either remove the new as-any casts or update BASELINE in this script."
  exit 1
else
  echo "OK: as any count ($COUNT) is at or below baseline ($BASELINE)."
  exit 0
fi
