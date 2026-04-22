# TapTrack v1 Model Plan

## Role Approach
- Use Django `User` for authentication.
- Add role choices later in an `accounts.StaffProfile` model (`LANDLORD`, `MANAGER`, `STAFF`).
- Permission split for v1:
- `Landlord/Admin`: full CRUD on stock, suppliers, orders, breakages, checklists, staff.
- `Staff`: read stock, create low-stock reports, log breakages, mark checklist tasks complete, confirm deliveries.

## Planned Models

### `accounts.StaffProfile`
- `id`
- `user` (OneToOne to `auth.User`)
- `phone`
- `job_title`
- `role`
- `is_active`
- `notes`

### `suppliers.Supplier`
- `id`
- `name`
- `contact_name`
- `phone`
- `email`
- `category_supplied`
- `notes`

### `stock.StockItem`
- `id`
- `name`
- `category`
- `quantity`
- `unit`
- `minimum_level`
- `cost`
- `supplier` (FK to `Supplier`, nullable)
- `last_restocked`
- `notes`

### `orders.Order`
- `id`
- `supplier` (FK to `Supplier`)
- `created_by` (FK to `auth.User`)
- `order_date`
- `delivery_date`
- `status` (`Draft`, `Ordered`, `Pending Delivery`, `Delivered`, `Cancelled`)
- `notes`

### `orders.OrderItem`
- `id`
- `order` (FK to `Order`)
- `stock_item` (FK to `StockItem`)
- `quantity`

### `breakages.Breakage`
- `id`
- `item_name`
- `quantity`
- `issue_type` (`Broken`, `Missing`, `Damaged`, `Replacement Needed`)
- `reported_by` (FK to `auth.User`)
- `created_at`
- `notes`

### `checklists.Checklist`
- `id`
- `title`
- `checklist_type` (`Opening`, `Closing`, `Delivery`, `Cleaning`)
- `assigned_to` (FK to `auth.User`)
- `due_date`
- `completed`
- `completed_at`

## Phase 2 Implementation Notes
- Build models with clear `choices` for status/type fields.
- Add indexes for commonly filtered fields (`status`, `category`, `completed`).
- Add model-level validation for non-negative quantities.
- Use `DecimalField` for money (`cost`).
