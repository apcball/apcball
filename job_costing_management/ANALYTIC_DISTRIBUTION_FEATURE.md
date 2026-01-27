# Feature Update: Analytic Distribution in Material Requisitions

## Request
Update the Analytic field on the "Material Requisitions" page to use the "Analytic Distribution" widget (similar to Purchase Order lines in Odoo 17).

## Changes Implemented

### 1. `models/material_requisition.py`
*   Added `analytic_distribution` (Json) field to `material.requisition.line` model.
*   Added `analytic_precision` field (required for the widget).
*   Updated `action_create_purchase_order` to pass the `analytic_distribution` value from the Requisition Line to the created Purchase Order Line.

### 2. `views/material_requisition_views.xml`
*   Updated the Requisition Lines list (tree view) inside the form.
*   Replaced the display of `analytic_account_id` with `analytic_distribution` using the `widget="analytic_distribution"`.
*   Moved `analytic_account_id` to be invisible (kept for backward compatibility).

## How to Test
1.  **Upgrade the module**: `./upgrade_module.sh job_costing_management` (or restart Odoo if you just updated code, but XML changes require upgrade).
2.  **Go to Job Costing > Material Requisitions**.
3.  Open or Create a Material Requisition.
4.  In the "Requisition Lines" tab, you will now see an "Analytic Distribution" column.
5.  Clicking it opens the popup to select Analytic Accounts with percentages (Projects, Departments, etc.).
6.  When you "Create Purchase Order" from an approved requisition, this distribution will carry over to the Purchase Order lines.
