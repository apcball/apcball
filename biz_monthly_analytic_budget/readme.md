# Biz Monthly Analytic Budget

## Module Overview

The `biz_monthly_analytic_budget` module extends Odoo's purchase and requisition flows to provide **Monthly Budget Control based on Analytic Accounts**. It operates alongside standard Odoo modules and customized ones (like `budget_engine_core` and `employee_purchase_requisition`) to enforce budgetary limits on a per-month, per-analytic-account basis. 

The primary purpose of this module is to ensure that Employee Purchase Requisitions (PR) and Purchase Orders (PO) do not exceed a pre-defined monthly budget that is divided among specific analytic distributions.

## Core Models

### 1. `monthly.budget.plan` (`models/monthly_budget_plan.py`)
- **Purpose**: Defines the total budget for a specific calendar month.
- **Key Fields**:
  - `name`: Reference ID.
  - `date_from`, `date_to`: Date range for the budget plan.
  - `total_budget`: The overarching monetary budget for this plan.
  - `state`: Status (`draft`, `confirmed`, `closed`).
  - `budget_line_ids`: One2many relationship to `monthly.budget.line`.
- **Key Logic**: Computes aggregate metrics (`allocated_amount`, `reserved_amount`, `used_amount`, `available_amount`) from its budget lines. Contains actions to confirm, close, and dynamically recompute the budget state from scratch (`action_recompute_budget`).

### 2. `monthly.budget.line` (`models/monthly_budget_line.py`)
- **Purpose**: Represents an allocated slice of a Monthly Budget Plan for a single `account.analytic.account`.
- **Key Fields**:
  - `analytic_account_id`: The targeted analytic account.
  - `percentage`: Allocation percentage out of `100.0`.
  - `budget_amount`: Computed as `(total_budget * percentage / 100)`.
  - `reserved_amount`: Tracks budget locked by approved Purchase Requisitions.
  - `used_amount`: Tracks budget consumed by confirmed Purchase Orders.
  - `available_amount`: Calculated as `budget_amount - reserved_amount - used_amount`.
- **Key Logic**: Enforces unique constraints (one analytic account per plan). Provides CRUD helper methods `_add_reservation`, `_release_reservation`, and `_consume_reservation`.

### 3. `employee.purchase.requisition` (Extended in `models/purchase_requisition.py`)
- **Interaction**: Validates the PR budget and locks in a **Reservation**.
- **Key Logic**:
  - `payment_date`: Computed date prioritizing vendor payment terms or requisition deadline to map the PR to a specific `monthly.budget.plan`.
  - `_check_monthly_analytic_budget`: Scans each PR line's `analytic_distribution` and verifies against the budget lines of the active monthly plan. Prevents PR submission/approval if limits are exceeded.
  - `_reserve_monthly_analytic_budget`: Adds reserved amounts to `monthly_budget_line` and creates audit records (`budget.commitment`) using `budget.engine` during PR confirmation.

### 4. `purchase.order` (Extended in `models/purchase_order.py`)
- **Interaction**: Consumes the reserved budget (or direct budget) during PO confirmation.
- **Key Logic**:
  - `payment_date`: Similar rules as PR to find the target monthly plan.
  - `_consume_monthly_analytic_budget`: Decreases the `reserved_amount` and moves it to `used_amount` upon PO confirmation. Handles direct POs (not stemming from a PR) by verifying and strictly adding to the `used_amount`.
  - `button_cancel`: Reverses the consumption logic if a PO is canceled.

### 5. `monthly.budget.report` (`models/monthly_budget_report.py`)
- **Purpose**: Drives analytics and the custom OWL Dashboard.
- **Key Logic**: 
  - An auto-maintained SQL `VIEW` (`_auto = False`) that normalizes records from `monthly_budget_line` (as `entry_type='budget'`) and active `purchase_order_line` data (as `entry_type='actual'`).
  - `get_dashboard_data`: A heavily utilized python layer for OWL dashboards, supplying pie chart stats (Used, Reserved, Available) and bar chart comparisons across different analytic accounts.

## Budget Lifecycle & Flow
1. **Planning**: 
   - A Draft `monthly.budget.plan` is created with a `total_budget`.
   - Lines (`monthly.budget.line`) are added, splitting the budget into percentages by `account.analytic.account`.
   - Plan is `confirmed`.
2. **Reservation (PR Level)**:
   - When a PR is created with lines mentioning an analytic account, a preview (`monthly_budget_check_result`) evaluates remaining budget dynamically.
   - Upon PR Confirm/Head Approval, `_check_monthly_analytic_budget` blocks the action if it over-allocates the budget limit.
   - Success triggers `_reserve_monthly_analytic_budget`, increasing the `reserved_amount` in the budget line.
3. **Consumption (PO Level)**:
   - Once the PR spawns a PO and the PO is confirmed (`button_confirm`), the `reserved_amount` is subtracted, and the `used_amount` expands globally by calling `_consume_monthly_analytic_budget`.

## User Interface & Dashboard
- **Web Assets**: Configured through `manifest.js`, Odoo 17 OWL (`js/xml/scss`) fetches Python dictionary data from `monthly_budget_report.get_dashboard_data`. 
- **Key Views**: Provides specialized Tree/Form views and interactive HTML dashboards. Included forms inject custom HTML-based check snippets (such as PR previews showing `Remaining After` dynamically inside a bootstrap card layout).

## Key Interactions for Developers / AI
- The module extracts analytic values directly from `analytic_distribution` JSON field parsing.
- Budget audit trails are delegated heavily to `budget_engine_core` via calls like `self.env['budget.engine'].reserve_budget()`.
- Use the `payment_date` to link any PR or PO transaction to the corresponding active `monthly.budget.plan`.
