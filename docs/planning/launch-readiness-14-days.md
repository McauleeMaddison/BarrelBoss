# BarrelBoss Launch Readiness Plan (14 Days)

Goal: ship a business-ready release in 2 weeks with clear quality gates.

## Supporting Assets
- [Staged UAT Script](../uat/staging-script.md)
- [UAT Results Template](../uat/results-template.md)
- [Production Ops Runbook](../operations/production-ops-runbook.md)

## Week 1: Product and Operational Hardening

### Day 1: Access and Accounts
- Confirm landlord/manager/staff permissions across every page.
- Verify staff can only access staff portal actions.
- Lock role editing rules (manager cannot escalate to landlord).

### Day 2: Inventory and Ordering Workflows
- Validate stock create/edit/delete flows on desktop and mobile.
- Validate urgency bands against real sample inventory data.
- Validate order request/approval cycle from staff to management.

### Day 3: Team and Shift Operations
- Validate shift planning and worked-hours update flow.
- Validate staff hours visibility in staff portal.
- Validate push notification opt-in and role-specific behavior.

### Day 4: UX Consistency Sweep
- Verify spacing, headings, button states, and empty states.
- Verify success/error/warning message consistency across forms.
- Verify mobile nav, slide-out behavior, and click targets.

### Day 5: Data Integrity and Edge Cases
- Add test coverage for key edge cases (empty filters, invalid IDs, role restrictions).
- Validate CSV exports for stock, staff, and reports.
- Validate soft-delete behavior and list refresh states.

### Day 6: Security and Settings
- Confirm production settings (`DEBUG=false`, secure cookies, SSL redirect, HSTS).
- Confirm `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` for Render URL.
- Rotate to strong production credentials and disable demo credentials in live.

### Day 7: UAT Round 1
- Run scripted end-to-end flows with real-world scenarios.
- Capture UI/flow issues from landlord + staff perspectives.
- Prioritize and schedule fixes for Week 2.

## Week 2: Stabilization and Release

### Day 8: Resolve UAT Findings
- Fix high/medium priority defects from UAT.
- Re-run impacted tests and smoke checks.

### Day 9: Performance and Device Testing
- Test on iPhone/Android + desktop browsers.
- Improve slow pages (query optimization, pagination where needed).
- Verify PWA install behavior and offline fallback quality.

### Day 10: Content and Reporting Polish
- Finalize clear labels, helper text, and action language.
- Validate reports for management decision-making clarity.

### Day 11: Deployment Dry Run
- Deploy staging on Render with Railway PostgreSQL.
- Run migrations and collectstatic in staging.
- Verify login/logout, data save, uploads, and notifications in staging.

### Day 12: Backups, Monitoring, and Runbook
- Configure DB backup policy in Railway.
- Add error tracking/alerts (basic logging + platform alerts).
- Document incident runbook (downtime, rollback, user lockout).

### Day 13: Release Candidate Sign-Off
- Freeze scope.
- Execute full regression checklist.
- Confirm business owner acceptance.

### Day 14: Production Go-Live
- Deploy approved commit/tag.
- Run migrations.
- Smoke-test key workflows with real accounts.
- Announce release and monitor first 24 hours.

## Release Gate Checklist (Must Pass)
- Authentication and role routing pass.
- Stock/order/checklist/shift core workflows pass.
- Logout/login role switching works cleanly.
- Mobile navigation and key action buttons are fully usable.
- No high-severity bugs open.
- Production environment variables verified.
- Backups and rollback steps documented.
