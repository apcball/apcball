# Concept: Force Cancel PO & PR

## Overview
The "Force Cancel PO & PR" feature is a custom administrative override designed for the `biz_monthly_analytic_budget` module. It allows authorized users (Monthly Budget Managers) to forcefully cancel a Purchase Order (PO) and its originating Purchase Requisition (PR) in a single click, instantly restoring the reserved budget.

## Business Problem
In standard Odoo, once a Purchase Order receives goods (Pickings are marked as Done), the `button_cancel` is natively blocked to preserve inventory integrity. However, business workflows occasionally require returning the goods to the vendor and completely scrapping the PO and PR to start fresh with the exact same budget. Forcing users to manually untangle the PO, cancel the PR, and manually adjust budget logs is tedious.

This custom button solves this by providing a unified, safe cancellation path that guarantees the budget is released.

## Security & Visibility
- **Group Restriction**: The button is restricted to `biz_monthly_analytic_budget.group_monthly_budget_manager`. Only Budget Managers can see and execute this action.
- **Visibility**: The button is hidden if the PO is already in a `draft` or `cancel` state (`invisible="state in ('cancel', 'draft')"`).

## Validation Rule (Return Check)
Before cancelling, the system enforces a strict check on **received quantities**:
- If any PO line has `qty_received > 0` (meaning goods are currently in the warehouse), the system raises a `UserError`.
- **Resolution**: The user must explicitly perform a **Return** transfer (`stock.picking`) to the vendor. Returning the goods deducts from `qty_received` natively in Odoo. Once `qty_received` equals `0`, the validation passes and the PO can be cancelled.

## Technical Execution Flow (`action_force_cancel_po_with_pr`)
When the Budget Manager clicks the button, the following Python logic executes:

1. **Validation**: Checks `any(line.qty_received > 0)`. Raises an error if true.
2. **Cancel Pending Pickings**: Iterates through `order.picking_ids`. Any picking that is not `done` or `cancel` is forcefully cancelled (`pick.action_cancel()`).
3. **Force Cancel PO**: Bypasses Odoo's native state validation by directly writing `{'state': 'cancel'}` to the `purchase.order`.
4. **Cleanup PO Budget**: Calls `_release_monthly_analytic_budget_on_cancel()` to ensure any specific budget tracking logs associated with the PO are reversed.
5. **Find and Cancel Linked PR**:
   - Searches for the `employee.purchase.requisition` where the `name` matches the PO's `requisition_order`.
   - Directly writes `{'state': 'cancelled'}` to the PR.
   - Calls `_release_monthly_analytic_budget()` on the PR to ensure any PR-level budget tracking logs are cleaned up.

## Budget Restoration Logic
The dynamic budget calculation in the module ensures that the budget is perfectly restored the moment these states change:
- **Python Backend (`monthly_budget_line.py`)**: The `_compute_reserved_amount` method explicitly filters out PRs with `('state', 'not in', ('draft', 'cancel', 'cancelled', 'rejected'))`. By setting the PR state to `cancelled`, it drops out of the total reserved sum.
- **SQL View (`monthly_budget_report.py`)**: The `monthly.budget.report` SQL view queries the database. It explicitly specifies `WHERE pr.state NOT IN ('draft', 'cancel', 'cancelled', 'rejected')` and restricts POs to `('purchase', 'done')`.

Because both the PR and PO are now in cancelled states, their financial values instantly disappear from the "Reserved" column, effectively restoring the budget to "Available" for future use.

## UI Indicators
To make the cancellation state immediately obvious:
- A red `<widget name="web_ribbon" title="Cancelled"/>` was added to both the `purchase.order` and `employee.purchase.requisition` form views. It automatically displays when the document's state achieves `cancel` or `cancelled`.
