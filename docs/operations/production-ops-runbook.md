# BarrelBoss Production Runbook

## Baseline

Set these before go-live:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY=<strong-secret>`
- `DJANGO_ALLOWED_HOSTS=<production-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<production-domain>`
- `RENDER_EXTERNAL_HOSTNAME=<production-domain>`
- `DATABASE_URL=<postgres-url>`
- `DATABASE_FALLBACK_URL=<optional-external-postgres-url>`
- `DATABASE_SSL_REQUIRE=true`
- `DJANGO_EMAIL_BACKEND=<smtp-or-transactional-backend>`
- `DJANGO_DEFAULT_FROM_EMAIL=<real-sender@yourdomain.com>`
- `DJANGO_SERVER_EMAIL=<alerts@yourdomain.com>`
- `ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false`

Validate settings:

```bash
DJANGO_DEBUG=false \
DJANGO_SECRET_KEY='<strong-secret>' \
DJANGO_ALLOWED_HOSTS='example.com' \
DJANGO_CSRF_TRUSTED_ORIGINS='https://example.com' \
python manage.py check --deploy
```

## Release Flow

1. Deploy to staging.
2. Run local preflight:

```bash
./scripts/release_preflight.sh
```

3. Run hosted smoke against the deployed URL:

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

4. Run a short manual write pass: login and logout, stock create/edit/archive, order create/status update, checklist assign/complete, shift schedule/edit, password reset request.

5. Deploy production and run post-deploy smoke again.

## Monitoring

Minimum coverage:

- Render health checks
- app error alerts
- database backup status
- uptime alerting

Probe endpoints:

- `GET /health/live/`
- `GET /health/ready/`

Track `X-Request-ID` when investigating incidents.

## Backup

- Enable automatic PostgreSQL backups.
- Keep at least 14 days.
- Test one restore path before launch.

## Rollback

1. Re-deploy the last known-good build.
2. Confirm schema safety before rollback if migrations shipped.
3. Re-run hosted smoke.
4. Monitor for 30 minutes.
