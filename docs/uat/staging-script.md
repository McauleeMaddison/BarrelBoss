# BarrelBoss Staged UAT

## Preconditions

- staging is deployed from the release candidate
- staging uses production-like settings
- landlord, manager, and staff test accounts exist
- desktop and mobile browsers are ready

## Automated Gate

Run hosted smoke first:

```bash
SMOKE_BASE_URL=https://<staging-domain> \
SMOKE_MANAGER_USERNAME='<manager-username>' \
SMOKE_MANAGER_PASSWORD='<manager-password>' \
SMOKE_STAFF_USERNAME='<staff-username>' \
SMOKE_STAFF_PASSWORD='<staff-password>' \
SMOKE_LANDLORD_USERNAME='<landlord-username>' \
SMOKE_LANDLORD_PASSWORD='<landlord-password>' \
./.venv/bin/python scripts/hosted_smoke.py
```

## Manual Pass

1. Landlord desktop: sign in, confirm management routing, confirm admin access.
2. Manager desktop: stock create/edit/archive, supplier create/edit, order create/status update, checklist assign, shift schedule/edit, reports and settings load cleanly.
3. Staff desktop: confirm staff routing, verify restricted redirects, complete checklist work, log breakage, review rota and stock views.
4. Mobile repeat: manager and staff, nav open/close, tap targets usable, forms and tables readable.

## Pass Rule

- pass: flow completes cleanly with no blocking UI or backend issue
- fail: auth leak, save failure, broken layout, or incorrect role access

## Output

- fill [results-template.md](results-template.md)
- attach screenshots for failures
- store final run file in [runs/](runs/)
