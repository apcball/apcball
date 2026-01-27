# Validation Error Fix: Analytic Account Access

## Problem
Users reported a "Validation Error" (Read Access Error) when creating Purchase Orders:
`Uh-oh! Looks like you have stumbled upon some top-secret records. ... doesn't have 'read' access to: - Analytic Account`

This occurs because the `job_costing_management` module attempts to automatically link the Purchase Order to an Analytic Account derived from the Job Cost Sheet (linked via Material Requisition/BOQ). Since standard Purchase Users might have restricted access to Analytic Accounts (especially in multi-company setups) or just restricted visibility due to record rules, accessing the `analytic_account_id` properties (like `.name` for logging) triggers a security violation.

## Solution
Modified `models/purchase_order.py` to use `sudo()` when traversing the relationship chain from Purchase Order -> Material Requisition -> BOQ -> Job Cost Sheet -> Analytic Account.

This allows the system to read the necessary configuration values (like the Analytic Account ID) to set up the Purchase Order correctly, without failing due to the user's restricted read permissions on the underlying configuration records.

### Specific Changes
1. **In `PurchaseOrder.create`**:
   Used `result.material_requisition_id.sudo().boq_id` to enter superuser mode when traversing to BOQ and Job Cost Sheet. This ensures that checks for `job_cost_sheet_id` and `analytic_account_id` (and subsequent logging) do not trigger access errors.

2. **In `PurchaseOrderLine.create`**:
   Used `result.material_requisition_line_id.sudo()` when accessing the linked requisition line. This ensures retrieving `job_cost_line_id` and `analytic_account_id` from the requisition line is successful.

## Verification
1. Restart the Odoo service.
2. Attempt to create a Purchase Order as the user who previously encountered the error.
3. The Purchase Order should be created successfully, with the correct links to Job Cost Sheet and Analytic Account populated (since writing the ID to the PO field is usually allowed if the user has write access to the PO).
