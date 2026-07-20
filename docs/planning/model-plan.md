# BarrelBoss Model Plan

## Roles

- `Landlord`
- `Manager`
- `Staff`

Management roles control stock, suppliers, orders, staffing, reports, and settings. Staff stay within task and floor workflows.

## Core Models

- `accounts.StaffProfile`
  - user, role, phone, job title, notes
- `suppliers.Supplier`
  - name, contact details, category, notes
- `stock.StockItem`
  - name, category, quantity, unit, minimum level, cost, supplier, notes
- `orders.Order`
  - supplier, created by, dates, status, notes
- `orders.OrderItem`
  - order, stock item, quantity
- `breakages.Breakage`
  - item, quantity, issue type, reported by, notes
- `checklists.Checklist`
  - title, type, assignee, due date, completion state

## Rules

- Use explicit choices for role and status fields.
- Index common filters.
- Keep quantities non-negative.
- Use `DecimalField` for money.
