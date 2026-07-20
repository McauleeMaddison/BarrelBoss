# BarrelBoss Launch Readiness (14 Days)

Goal: reach a release candidate that is safe to deploy and easy to verify.

## Week 1

- Day 1: confirm role access and account rules
- Day 2: verify stock and order flows on desktop and mobile
- Day 3: verify shifts, hours, and notifications
- Day 4: clean UX states, spacing, and mobile navigation
- Day 5: cover edge cases, exports, and soft-delete behavior
- Day 6: lock production settings and security defaults
- Day 7: run UAT round 1 and triage findings

## Week 2

- Day 8: fix UAT defects
- Day 9: test performance and device coverage
- Day 10: final wording and reporting polish
- Day 11: deploy staging and verify operational flows
- Day 12: confirm backups, alerts, and rollback docs
- Day 13: freeze scope and collect sign-off
- Day 14: deploy production and monitor closely

## Release Gate

- auth and role routing pass
- core workflows pass
- mobile navigation is stable
- no open high-severity bugs
- production env vars are verified
- backups and rollback are documented

## Supporting Docs

- [Staged UAT Script](../uat/staging-script.md)
- [UAT Results Template](../uat/results-template.md)
- [Production Runbook](../operations/production-ops-runbook.md)
