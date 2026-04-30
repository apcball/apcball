# sale_forecast (Odoo 17)

Sales Forecast module for demand planning, auto-allocation to sale orders, and forecast-vs-actual performance tracking.

## Features

### Forecast Planning
- Create **Forecast Plans** (`forecast.plan`) — **1 plan per salesperson per month**
- Each plan is linked to a `user_id` (salesperson)
- Add **Forecast Lines** (`forecast.line`) by product, qty, and arrival month/week
- Weekly delivery balancing: split monthly forecast qty evenly into week buckets (W1..W5)
- Optional manual reference to blanket PO (`blanket_reference`)

### Auto Allocation
- **Auto-allocate on SO Confirm** — when a salesperson confirms a Sale Order, the system automatically:
  - Finds their forecast plan for the current month
  - Matches products and allocates available forecast qty
  - Creates `forecast.allocation` records automatically
- **Non-forecast sales allowed** — products not in forecast are flagged as `is_non_forecast` but still processed
- **Partial allocation** — if forecast qty is insufficient, allocates what's available and flags the remainder
- **Over-allocation prevention** — cannot allocate beyond forecast availability
- Manual allocation still available via Forecast Allocations menu

### OWL JavaScript Dashboard
- Real-time KPI cards (Forecast, Allocated, Actual Sold, Allocation %, Accuracy %)
- Bar chart: Forecast vs Allocated vs Actual by month (Chart.js)
- Doughnut chart: Allocation by product
- Recent plans and allocations tables
- Weekly distribution view (W1-W5 per month)
- Navigate to Plans and Allocations from dashboard

## Business Rules

1. **1 plan per salesperson per month** (SQL constraint)
2. Forecast horizon: current month + next 2 months
3. Auto allocation triggers on **SO confirm** (not on SO create)
4. Non-forecast products are allowed (flagged as `is_non_forecast`)
5. Allocation cannot exceed forecast remaining quantity
6. Weekly schedule distribution balances arrivals across weeks

## Flow

```
1. Salesperson creates Forecast Plan (of their own, 1 per month)
   └── Linked to user_id

2. Salesperson creates Sale Order normally

3. On SO Confirm → System auto-allocates:
   ├── Product in forecast → Deduct qty automatically
   └── Product NOT in forecast → Allow sale, flag as "non-forecast"

4. Dashboard updates in real-time
```

## Security / Roles

- **Forecast Planner** — Create/Edit own Forecast Plans and Lines, read allocations
- **Forecast Sales Allocator** — Read plans/lines, create/edit allocations
- **Forecast Manager** — Full access + dashboard

## Installation

```bash
cp -r modules/sale_forecast /path/to/odoo/addons/
```

Restart Odoo and update apps list. Install **Sales Forecast Planning**.

```bash
./odoo-bin -c odoo.conf -u sale_forecast --stop-after-init
```

## Usage

### Creating a Forecast Plan
1. Go to **Sales ▸ Sales Forecast ▸ Forecast Plans**
2. Click Create — plan auto-assigns to current user
3. Add forecast lines: product, qty, arrival month, expected week
4. Click **Distribute All Lines Weekly** to auto-balance weekly buckets
5. Confirm the plan

### Auto Allocation (Automatic)
1. Salesperson creates a Sale Order normally
2. Adds products and quantities
3. Clicks **Confirm**
4. System automatically allocates from their forecast plan
5. View allocations via smart button on Sale Order

### Dashboard
1. Go to **Sales ▸ Sales Forecast ▸ Dashboard**
2. View KPIs, charts, recent activity, weekly distribution

## Technical Details

### Models
| Model | Description |
|---|---|
| `forecast.plan` | Forecast plan per salesperson per month |
| `forecast.line` | Forecast lines (product, qty, week breakdown) |
| `forecast.allocation` | Allocation records (auto or manual) |
| `sale.order` | Extended with allocation fields |
| `sale.order.line` | Extended with allocation + non-forecast flags |
| `sale.forecast.dashboard` | Dashboard data provider |

### OWL Frontend
- `static/src/dashboard/dashboard.js` — OWL Component
- `static/src/dashboard/dashboard.xml` — QWeb Template
- `static/src/dashboard/dashboard.scss` — Styling
- `static/src/dashboard_action.js` — Action registry

### Key Constraints
- `unique(user_id, start_date, company_id)` on `forecast.plan`
- Over-allocation prevention on `forecast.allocation`
- Forecast qty > 0 validation

## Out of Scope (Phase 2)
- Budget module integration
- Auto-import from blanket purchase orders

## Changelog

### v17.0.1.0.0
- Initial release with manual allocation

### v17.0.2.0.0
- Added auto-allocation on SO confirm
- Added user_id to forecast plan (1 plan per user per month)
- Added non-forecast sales flagging
- Added OWL JavaScript dashboard
- Added SQL constraint for unique plan per user per month
