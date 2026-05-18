#!/usr/bin/env bash
set -euo pipefail

echo "==> Predeploy diagnostics"
python3 -u - <<'PY'
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "taptrack.settings")

import django
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
print("Attempting database connection...", flush=True)

connection.ensure_connection()

print("Database connection OK", flush=True)
PY

echo "==> Applying migrations"
python3 manage.py migrate --noinput --verbosity 2
