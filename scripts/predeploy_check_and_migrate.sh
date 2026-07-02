#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No Python interpreter found in PATH." >&2
  exit 1
fi

echo "==> Predeploy diagnostics"
"$PYTHON_BIN" -u - <<'PY'
import os
import sys

sys.path.insert(0, os.getcwd())

import django
from taptrack.database_config import (
    FALLBACK_DATABASE_ENV_KEYS,
    is_render_private_postgres_hostname,
    resolve_hostname,
    select_database_url,
    trim_env,
)

primary_url = trim_env("DATABASE_URL")
selection = select_database_url()

print(f"DATABASE_URL_SET={bool(primary_url)}", flush=True)
for env_key in FALLBACK_DATABASE_ENV_KEYS:
    print(f"{env_key}_SET={bool(trim_env(env_key))}", flush=True)

if selection:
    print(f"SELECTED_DATABASE_SOURCE={selection.source}", flush=True)
    print(f"SELECTED_DATABASE_REASON={selection.reason}", flush=True)
    if selection.reason == "render_private_hostname":
        print(
            "Using the external database fallback because DATABASE_URL points at a "
            "Render private hostname.",
            flush=True,
        )
else:
    print("SELECTED_DATABASE_SOURCE=POSTGRES_* or sqlite fallback", flush=True)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "taptrack.settings")
django.setup()

from django.db import connection

config = connection.settings_dict
engine = config.get("ENGINE", "")
host = config.get("HOST", "")
port = config.get("PORT", "")
name = config.get("NAME", "")
user = config.get("USER", "")
options = config.get("OPTIONS", {})

print(f"ENGINE={engine}", flush=True)
print(f"HOST={host} PORT={port} NAME={name} USER={user}", flush=True)
print(f"OPTIONS={options}", flush=True)

host_resolves, resolution_error = resolve_hostname(host)
print(f"HOST_RESOLVES={host_resolves}", flush=True)
if not host_resolves:
    print(f"HOST_RESOLUTION_ERROR={resolution_error}", flush=True)
    if is_render_private_postgres_hostname(host):
        print(
            "Detected a Render private Postgres hostname. These internal database "
            "URLs only resolve when the web service and database are in the same "
            "Render workspace and region.",
            flush=True,
        )
        print(
            "If that is not true for this deploy, set DATABASE_FALLBACK_URL or "
            "RENDER_EXTERNAL_DATABASE_URL to the database's external connection "
            "string and redeploy.",
            flush=True,
        )
    raise SystemExit(1)

print("Attempting database connection...", flush=True)

connection.ensure_connection()

print("Database connection OK", flush=True)
PY

echo "==> Applying migrations"
"$PYTHON_BIN" manage.py migrate --noinput --verbosity 2
