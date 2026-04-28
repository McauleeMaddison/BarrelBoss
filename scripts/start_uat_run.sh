#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

ROUND_LABEL="${1:-round-1}"
SANITIZED_ROUND="$(echo "$ROUND_LABEL" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9._-' '-')"
RUN_DATE="$(date -u +"%Y-%m-%d")"
RUN_TIMESTAMP="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"
RUN_SLUG_DATE="$(date -u +"%Y%m%d")"

RESULTS_DIR="$ROOT_DIR/docs/uat-runs"
TEMPLATE_PATH="$ROOT_DIR/docs/uat-results-template.md"
mkdir -p "$RESULTS_DIR"

if [[ ! -f "$TEMPLATE_PATH" ]]; then
  echo "Template not found: $TEMPLATE_PATH" >&2
  exit 1
fi

GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
STAGING_URL="${UAT_BASE_URL:-set-UAT_BASE_URL}"

OUTPUT_PATH="$RESULTS_DIR/${RUN_SLUG_DATE}-${SANITIZED_ROUND}.md"
if [[ -f "$OUTPUT_PATH" ]]; then
  OUTPUT_PATH="$RESULTS_DIR/${RUN_SLUG_DATE}-${SANITIZED_ROUND}-$(date -u +"%H%M%S").md"
fi

cat > "$OUTPUT_PATH" <<EOF
# BarrelBoss UAT Run - ${ROUND_LABEL}

- Run Date (UTC): ${RUN_TIMESTAMP}
- Build Commit: \`${GIT_SHA}\`
- Staging URL: ${STAGING_URL}
- Test Leads: _fill in_
- Device Matrix: Desktop Chrome / Desktop Safari or Edge / iPhone Safari / Android Chrome

---

EOF

cat "$TEMPLATE_PATH" >> "$OUTPUT_PATH"

echo "Created UAT run file:"
echo "$OUTPUT_PATH"
echo
echo "Next steps:"
echo "1) Fill scenario pass/fail and severity in the generated file."
echo "2) Attach screenshots and bug links."
echo "3) Commit the UAT result file for audit traceability."
