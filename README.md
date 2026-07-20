# BarrelBoss

BarrelBoss is a role-based operations app for bar and pub teams.

## Stack

- Python 3.9+
- Django 4.2
- PostgreSQL in production
- SQLite fallback for local work

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/accounts/login/`.

## Optional Local Seed

Create demo accounts:

```bash
python manage.py bootstrap_demo_accounts
```

Create demo data:

```bash
python manage.py bootstrap_demo_data
```

Default local users:

- `landlord` / `strong-pass-123`
- `manager` / `strong-pass-123`
- `staff` / `strong-pass-123`

## Environment

Use [.env.example](.env.example) as the baseline.

Core production values:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY=<strong-secret>`
- `DJANGO_ALLOWED_HOSTS=<production-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<production-domain>`
- `DATABASE_URL=<postgres-url>`
- `ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false`

## Roles

- `Landlord` and `Manager` use the management portal.
- `Staff` use the staff portal.
- Django admin is for superusers only.

## Verification

Run tests:

```bash
python manage.py test
```

Run browser smoke locally:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
python manage.py test e2e.smoke_tests
```

Run release preflight:

```bash
./scripts/release_preflight.sh
```

Run deployed smoke:

```bash
SMOKE_BASE_URL=https://<deployment-url> \
SMOKE_MANAGER_USERNAME='<manager-username>' \
SMOKE_MANAGER_PASSWORD='<manager-password>' \
SMOKE_STAFF_USERNAME='<staff-username>' \
SMOKE_STAFF_PASSWORD='<staff-password>' \
SMOKE_LANDLORD_USERNAME='<landlord-username>' \
SMOKE_LANDLORD_PASSWORD='<landlord-password>' \
./.venv/bin/python scripts/hosted_smoke.py
```

## Health

- `GET /health/live/`
- `GET /health/ready/`

## Docs

- [Docs Index](docs/README.md)
- [Production Ops Runbook](docs/operations/production-ops-runbook.md)
- [Staged UAT Script](docs/uat/staging-script.md)
