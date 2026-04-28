# BarrelBoss

Professional bar and pub management web app for stock control, supplier ordering, breakage logs, and shift checklists.

## Current Status

Day 1 and Day 2 foundations are in place:
- Django project scaffold with app modules (`accounts`, `dashboard`, `stock`, `orders`, `suppliers`, `breakages`, `checklists`)
- Responsive premium dashboard shell and login UI
- Role model via `StaffProfile` (`Landlord`, `Manager`, `Staff`)
- Role-based login redirect flow
- Role-based access control for management sections
- Baseline tests for profile creation, role redirects, and permissions
- Day 3 dashboard with richer role-based KPI and task panels
- Day 4 real stock data model + stock page backed by database queries
- Day 5 stock CRUD flows (add, edit, remove from active inventory) for management roles
- Day 6 suppliers CRUD flows with search/filter and management-only access
- Day 7 real orders model with line items, status workflow, and management-only CRUD
- Day 8 breakage model with live logging/history and role-based delete controls
- Day 9 checklist model with assignment workflow, completion toggle, filters, and role-based task controls
- Day 10 shifts polish with weekly chart + staff/management portal split
- Web push notifications for shift allocation/update events (staff opt-in per device)
- CI pipeline for migration integrity, test suite, deploy security checks, and browser smoke tests
- Playwright browser E2E smoke suite for login/role routing and core CRUD workflows
- Production-safe demo account bootstrap guard (`ALLOW_DEMO_ACCOUNT_BOOTSTRAP`)

## Stack

- Python 3.9+
- Django 4.2
- PostgreSQL (optional; SQLite fallback for local dev)

## Setup

1. Create and activate a virtual environment.
2. Install dependencies.
3. Run migrations.
4. Start the server.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open: `http://127.0.0.1:8000/accounts/login/`

### Optional Dev Dependencies (Browser E2E)

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
```

## Demo Login Accounts (Local Testing)

Run this once to create/reset role-based demo users:

```bash
python manage.py bootstrap_demo_accounts
```

Note: this command is blocked when `ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false` (recommended in production).

Default demo credentials:
- `landlord` / `strong-pass-123` (Landlord portal + Django admin access)
- `manager` / `strong-pass-123` (Management portal)
- `staff` / `strong-pass-123` (Staff portal)

Optional custom password for all demo users:

```bash
python manage.py bootstrap_demo_accounts --password "YourStrongPassword-123!"
```

### Demo Business Data (Client Preview)

Populate the app with realistic suppliers, stock, orders, checklists, shifts, and breakages:

```bash
python manage.py bootstrap_demo_data
```

Re-run to refresh deterministic preview data (old preview-tagged records are replaced).
Append mode is also available:

```bash
python manage.py bootstrap_demo_data --append
```

## Environment Variables

Copy `.env.example` values into your environment (or `.env` with your preferred loader):
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_TIME_ZONE`
- `DATABASE_URL`
- `DATABASE_SSL_REQUIRE`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `WEB_PUSH_PUBLIC_KEY`
- `WEB_PUSH_PRIVATE_KEY`
- `WEB_PUSH_SUBJECT`
- `ALLOW_DEMO_ACCOUNT_BOOTSTRAP`
- `E2E_REQUIRE_BROWSER`
- `E2E_HEADLESS`

If PostgreSQL variables are not all set, the project defaults to SQLite.

### Web Push Setup

To enable real browser push notifications, set VAPID keys:

```bash
WEB_PUSH_PUBLIC_KEY=<your-public-vapid-key>
WEB_PUSH_PRIVATE_KEY=<your-private-vapid-key>
WEB_PUSH_SUBJECT=mailto:alerts@yourdomain.com
```

Staff then enable alerts from `Settings` on their own device/browser.

## Role Flow

- `Landlord` / `Manager`:
- redirected to dashboard after login
- access to orders, suppliers, staff, reports, settings

- `Staff`:
- redirected to checklists after login
- access to dashboard, stock, breakages, checklists, shifts, settings (personal push opt-in)

## Tests

```bash
python manage.py test
```

Browser E2E smoke tests:

```bash
python manage.py test e2e.smoke_tests
```

Release preflight (local or CI quality gates):

```bash
./scripts/release_preflight.sh
```

With browser smoke tests included:

```bash
./scripts/release_preflight.sh --with-e2e
```

## CI

GitHub Actions workflow: `.github/workflows/ci.yml`
- migration drift check
- unapplied migration check
- Django test suite
- deploy hardening checks (`check --deploy` + custom production checks)
- Playwright browser smoke tests

## Deployment (Render + Railway)

### 1. Railway database

1. Create a PostgreSQL service in Railway.
2. Copy the provided connection string.
3. Use it as `DATABASE_URL` in Render.

### 2. Render web service

1. Connect this GitHub repo in Render.
2. Render can auto-detect `render.yaml`, or configure manually with:
- Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- Start command: `gunicorn taptrack.wsgi:application --log-file -`
3. Add environment variables:
- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY=<strong-random-value>`
- `DJANGO_ALLOWED_HOSTS=<your-render-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<your-render-domain>`
- `DATABASE_URL=<railway-postgres-url>`
- `DATABASE_SSL_REQUIRE=true`
- `ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false`

### 3. First production release

After first deploy, run migrations once:

```bash
python manage.py migrate
```

Then create an admin user:

```bash
python manage.py createsuperuser
```

### Render Staging One-Click Seed + Verify

In Render Shell (staging), run:

```bash
./scripts/render_staging_seed_and_verify.sh
```

This command:
- runs migrations
- seeds demo preview data with a temporary `ALLOW_DEMO_ACCOUNT_BOOTSTRAP=true` for that command only
- runs critical smoke test classes for role routing + stock/order/checklist/shift flows

Optional non-interactive superuser creation in Render shell:

```bash
export DJANGO_SUPERUSER_USERNAME=admin
export DJANGO_SUPERUSER_EMAIL=admin@example.com
export DJANGO_SUPERUSER_PASSWORD='Strong-Admin-Pass-123!'
./scripts/render_staging_seed_and_verify.sh
```

Troubleshooting:
- If you see `Invalid DATABASE_URL` / `No support for ''`, your `DATABASE_URL` env var is empty or malformed.
- Set it to a full connection URL (for example `postgresql://USER:PASSWORD@HOST:5432/DBNAME`) in Render Environment, then re-run the script.

### 4. Notes

- `DATABASE_URL` is preferred and fully supported.
- If `DATABASE_URL` is missing, project can still use `POSTGRES_*` fallback or local SQLite.
- Static files are served via WhiteNoise in production.

## 14-Day Launch Plan

Use this rollout checklist to get to business-ready in 2 weeks:
- [Docs Index](docs/README.md)
- [Launch Readiness Plan](docs/planning/launch-readiness-14-days.md)
- [Staged UAT Script](docs/uat/staging-script.md)
- [UAT Results Template](docs/uat/results-template.md)
- [UAT Runs Archive](docs/uat/runs/README.md)
- [Production Ops Runbook](docs/operations/production-ops-runbook.md)

## Next Build Step

Day 11-12: run staged UAT on mobile + desktop, log findings, and complete backup/monitoring setup using the production ops runbook.
