# TapTrack (BarrelBoss)

Professional bar and pub management web app for stock control, supplier ordering, breakage logs, and shift checklists.

## Current Status

Day 1 and Day 2 foundations are in place:
- Django project scaffold with app modules (`accounts`, `dashboard`, `stock`, `orders`, `suppliers`, `breakages`, `checklists`)
- Responsive premium dashboard shell and login UI
- Role model via `StaffProfile` (`Landlord`, `Manager`, `Staff`)
- Role-based login redirect flow
- Role-based access control for management sections
- Baseline tests for profile creation, role redirects, and permissions

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

## Environment Variables

Copy `.env.example` values into your environment (or `.env` with your preferred loader):
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_TIME_ZONE`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_HOST`
- `POSTGRES_PORT`

If PostgreSQL variables are not all set, the project defaults to SQLite.

## Role Flow

- `Landlord` / `Manager`:
- redirected to dashboard after login
- access to orders, suppliers, staff, reports, settings

- `Staff`:
- redirected to checklists after login
- access to dashboard, stock, breakages, checklists

## Tests

```bash
python manage.py test
```

## Next Build Step

Day 3: Implement real dashboard data wiring and role-specific KPI queries from database models.
