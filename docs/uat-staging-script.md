# BarrelBoss Staged UAT Script

Use this script to execute a role-based UAT round against a staging deployment before release.

## Preconditions
- Staging environment is deployed from the release candidate commit.
- Staging uses production-like settings: `DJANGO_DEBUG=false`, HTTPS, and PostgreSQL.
- Test accounts exist for:
  - `landlord`
  - `manager`
  - `staff`
- Browser/device matrix is ready:
  - Desktop: Chrome, Safari/Edge
  - Mobile: iPhone Safari, Android Chrome

## Pass/Fail Rule
- A scenario is **Pass** only if expected behavior completes with no visual blockers and no backend errors.
- Any auth/permission leak, data-loss risk, or failed save is **Fail (Critical)**.

## Execution Order
1. Landlord desktop pass
2. Manager desktop pass
3. Staff desktop pass
4. Mobile repeat for manager and staff
5. Push-notification verification on at least one mobile device

## Scenario Set A: Authentication & Role Routing
1. Open `/accounts/login/` and sign in as `manager`.
2. Confirm redirect to `/dashboard/management/`.
3. Sign out and sign in as `staff`.
4. Confirm redirect to `/dashboard/staff/`.
5. As `staff`, attempt direct access to `/suppliers/`, `/staff/`, `/reports/`, `/audit/`.
6. Confirm each restricted route redirects to staff portal with access denied feedback.

## Scenario Set B: Stock Workflow (Manager)
1. Open `/stock/`.
2. Add a new stock item.
3. Edit the same item.
4. Soft-delete the item.
5. Validate metrics and list refresh behavior after each change.
6. Export CSV and verify columns and values.

## Scenario Set C: Supplier + Order Workflow
1. Open `/suppliers/`; create, edit, and delete a supplier.
2. Open `/orders/`; create order with item lines.
3. Update order status through full lifecycle: Draft -> Ordered -> Pending Delivery -> Delivered.
4. Confirm status badges and counts update correctly.
5. As `staff`, create a request and verify it is forced to Draft.

## Scenario Set D: Checklist + Shift Workflow
1. As manager, assign checklist tasks to a staff user.
2. As staff, mark assigned task complete and then pending.
3. As manager, schedule and edit a shift for staff.
4. Confirm weekly chart and hours metrics update.
5. Verify push-notification behavior when shift is created/updated.

## Scenario Set E: Reports, Settings, and Audit
1. Open `/reports/`; validate 7/30/90 day switches.
2. Export report CSV and verify KPI/header structure.
3. Open `/settings/`; toggle team shift alert preferences.
4. Validate entries appear in `/audit/` for critical actions.

## Mobile Usability Checks
- Sidebar open/close works via hamburger and overlay.
- Topbar actions are tappable and visible.
- Tables are scrollable and actions remain usable.
- Form fields, date/time inputs, and submit buttons are reachable without layout breakage.

## Completion Artifacts
- Fill [UAT Results Template](./uat-results-template.md)
- Capture screenshots for all failed scenarios.
- Log defects by severity (Critical/High/Medium/Low) with reproduction steps.
