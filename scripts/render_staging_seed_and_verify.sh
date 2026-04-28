#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUN_TESTS=true
DEMO_PASSWORD="${DEMO_PASSWORD:-strong-pass-123}"

usage() {
  cat <<'EOF'
Usage: scripts/render_staging_seed_and_verify.sh [--skip-tests] [--demo-password <password>]

Runs staging-safe setup for Render shell:
  1) apply migrations
  2) optionally create/update superuser from env vars
  3) seed demo preview dataset with temporary ALLOW_DEMO_ACCOUNT_BOOTSTRAP=true
  4) run critical smoke test classes (unless --skip-tests)

Optional env vars for superuser bootstrap:
  DJANGO_SUPERUSER_USERNAME
  DJANGO_SUPERUSER_EMAIL
  DJANGO_SUPERUSER_PASSWORD
EOF
}

while (($# > 0)); do
  case "$1" in
    --skip-tests)
      RUN_TESTS=false
      ;;
    --demo-password)
      if (($# < 2)); then
        echo "Missing value for --demo-password" >&2
        exit 2
      fi
      DEMO_PASSWORD="$2"
      shift
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

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No python interpreter found in PATH." >&2
  exit 1
fi

log_step() {
  printf "\n==> %s\n" "$1"
}

db_url_trimmed="$(printf '%s' "${DATABASE_URL:-}" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
if [[ -n "$db_url_trimmed" && "$db_url_trimmed" != *"://"* ]]; then
  echo "Invalid DATABASE_URL detected (missing URL scheme)." >&2
  echo "Set DATABASE_URL to a valid value like postgresql://USER:PASSWORD@HOST:5432/DBNAME" >&2
  exit 1
fi

if [[ "${RENDER:-}" == "true" && -z "$db_url_trimmed" ]]; then
  echo "DATABASE_URL is empty in Render runtime." >&2
  echo "Open Render Dashboard -> Service -> Environment and set DATABASE_URL to your Postgres connection URL." >&2
  exit 1
fi

log_step "Applying database migrations"
"$PYTHON_BIN" manage.py migrate --noinput

if [[ -n "${DJANGO_SUPERUSER_USERNAME:-}" && -n "${DJANGO_SUPERUSER_EMAIL:-}" && -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]]; then
  log_step "Ensuring superuser exists from DJANGO_SUPERUSER_* env vars"
  "$PYTHON_BIN" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
username = '${DJANGO_SUPERUSER_USERNAME}'
email = '${DJANGO_SUPERUSER_EMAIL}'
password = '${DJANGO_SUPERUSER_PASSWORD}'
user, created = User.objects.get_or_create(username=username, defaults={'email': email})
user.email = email
user.is_staff = True
user.is_superuser = True
user.set_password(password)
user.save()
print('Superuser ready:', username, '(created=' + str(created) + ')')
"
else
  log_step "Skipping superuser bootstrap (set DJANGO_SUPERUSER_* env vars to enable)"
fi

log_step "Seeding staging demo preview data"
ALLOW_DEMO_ACCOUNT_BOOTSTRAP=true "$PYTHON_BIN" manage.py bootstrap_demo_data --password "$DEMO_PASSWORD"

if [[ "$RUN_TESTS" == "true" ]]; then
  log_step "Running critical smoke test classes"
  "$PYTHON_BIN" manage.py test \
    apps.accounts.tests.RoleRoutingTests \
    apps.stock.tests.StockCrudViewTests \
    apps.orders.tests.OrderWorkflowTests \
    apps.checklists.tests.ChecklistViewTests \
    apps.shifts.tests.ShiftViewTests
fi

printf "\nRender staging seed + smoke verification completed.\n"
printf "If ALLOW_DEMO_ACCOUNT_BOOTSTRAP was enabled in Render dashboard, set it back to false after seeding.\n"
