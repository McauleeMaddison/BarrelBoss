# BarrelBoss Production Ops Runbook

This runbook covers launch hardening, backup/monitoring operations, and incident handling.

## 1. Production Configuration Baseline
Set these environment variables in production:
- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY=<long-random-secret>`
- `DJANGO_ALLOWED_HOSTS=<production-domain>`
- `DJANGO_CSRF_TRUSTED_ORIGINS=https://<production-domain>`
- `DATABASE_URL=<production-postgres-url>`
- `DATABASE_SSL_REQUIRE=true`
- `DJANGO_SECURE_SSL_REDIRECT=true`
- `DJANGO_SECURE_HSTS_SECONDS=31536000`
- `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=true`
- `DJANGO_SECURE_HSTS_PRELOAD=true`
- `ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false`

Validation command:
```bash
DJANGO_DEBUG=false DJANGO_SECRET_KEY='<strong-secret>' DJANGO_ALLOWED_HOSTS='example.com' DJANGO_CSRF_TRUSTED_ORIGINS='https://example.com' python manage.py check --deploy
```

## 2. Account and Access Hardening
- Ensure demo credentials are not used in production.
- Disable demo bootstrap command in production (`ALLOW_DEMO_ACCOUNT_BOOTSTRAP=false`).
- Enforce unique named accounts for real staff.
- Keep landlord accounts minimal and auditable.

## 3. Deployment Procedure
1. Deploy release candidate to staging.
2. Run UAT and collect sign-off.
3. Deploy to production.
4. Run migrations:
```bash
python manage.py migrate
```
5. Run quick smoke checks:
- login/logout
- manager dashboard
- staff dashboard
- stock/order/checklist/shift create actions

## 4. Backup Policy
- Configure automatic daily PostgreSQL backups (Railway managed backups or external backup job).
- Retain at least 14 days of backups.
- Perform a monthly restore drill into a non-production environment.

## 5. Monitoring and Alerting
Minimum monitoring stack:
- Platform uptime alerts (Render/Railway service checks).
- Application error tracking (Sentry or equivalent).
- DB health checks (connection errors, storage growth, failed backups).

Alert priorities:
- P1: app down, login failure for all users, migration failure.
- P2: core workflow degradation (stock/order/checklist/shift save errors).
- P3: non-blocking UI issues.

## 6. Incident Response
1. Acknowledge incident and assign incident owner.
2. Capture scope: affected routes, user roles, start time, latest deploy SHA.
3. Mitigate:
- rollback deployment if release-related.
- disable problematic action paths if needed.
4. Validate recovery with smoke checks.
5. Publish incident summary and corrective actions.

## 7. Rollback Procedure
- Re-deploy previous known-good build.
- If schema changed, apply safe backward plan (or data hotfix) before rollback when needed.
- Re-run smoke checks and monitor for 30 minutes.

## 8. Release Checklist
- `./scripts/release_preflight.sh` (includes migration drift, unapplied migration, tests, deploy checks)
- `./scripts/release_preflight.sh --with-e2e` (run when browser stack is available)
- UAT sign-off complete
- Backup status confirmed
