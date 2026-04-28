#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_E2E=false

usage() {
  cat <<'EOF'
Usage: scripts/release_preflight.sh [--with-e2e]

Runs launch-readiness quality gates:
  - migration drift check
  - unapplied migration check
  - Django test suite
  - deploy hardening checks
  - optional browser E2E smoke tests
EOF
}

while (($# > 0)); do
  case "$1" in
    --with-e2e)
      RUN_E2E=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

log_step() {
  printf "\n==> %s\n" "$1"
}

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No Python interpreter found. Install Python or create .venv first." >&2
  exit 1
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  PRECHECK_DB="$(mktemp "${TMPDIR:-/tmp}/barrelboss-preflight-XXXXXX.sqlite3")"
  export DATABASE_URL="sqlite:///$PRECHECK_DB"
  export DATABASE_SSL_REQUIRE="false"
  trap 'rm -f "$PRECHECK_DB"' EXIT
fi

log_step "Checking migration drift"
"$PYTHON_BIN" manage.py makemigrations --check --dry-run

log_step "Applying migrations to preflight database"
"$PYTHON_BIN" manage.py migrate --noinput

log_step "Checking unapplied migrations"
"$PYTHON_BIN" manage.py migrate --check

log_step "Running Django tests"
"$PYTHON_BIN" manage.py test

log_step "Running deploy hardening checks"
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-preflight-secret-key-this-must-be-very-long-and-random-1234567890}" \
DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-example.com}" \
DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS:-https://example.com}" \
ALLOW_DEMO_ACCOUNT_BOOTSTRAP="${ALLOW_DEMO_ACCOUNT_BOOTSTRAP:-false}" \
"$PYTHON_BIN" manage.py check --deploy

if [[ "$RUN_E2E" == "true" ]]; then
  log_step "Running browser E2E smoke tests"
  export E2E_REQUIRE_BROWSER="${E2E_REQUIRE_BROWSER:-true}"
  export E2E_HEADLESS="${E2E_HEADLESS:-true}"
  "$PYTHON_BIN" manage.py test e2e.smoke_tests
fi

printf "\nRelease preflight completed successfully.\n"
