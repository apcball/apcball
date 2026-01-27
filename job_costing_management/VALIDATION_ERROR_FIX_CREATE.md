# Validation Error Fix: Job Cost Line Creation

## Problem
Users reported a "Validation Error" when creating Purchase Orders:
`You are not allowed to create 'Job Cost Line' (job.cost.line) records.`

This occurs because the system attempts to automatically create a Job Cost Line (to track costs) when a Purchase Order Line is created for a project that doesn't have a corresponding cost line yet. Standard users (e.g., Purchase Users) do not have create permissions for Job Cost Lines.

## Solution
Modified `models/purchase_order.py` to use `sudo()` when automatically creating `job.cost.line` records.
This allows the system to create the necessary cost tracking records in the background without requiring the user to have explicit "Create" permissions on the Job Costing module.

### Specific Changes
In `PurchaseOrderLine.create`:
```python
# Before
new_cost_line = self.env['job.cost.line'].create(cost_line_vals)

# After
new_cost_line = self.env['job.cost.line'].sudo().create(cost_line_vals)
```

This change was applied in two places within the `create` method where automatic cost line creation occurs.

## Verification
1. Restart the Odoo service to reload the python code (no module upgrade strictly necessary for python code changes if simply restarting, but upgrading is safer to ensure all assets are loaded).
2. Attempt to create a Purchase Order as a standard user.
3. The error should no longer appear, and the Job Cost Line should be created automatically in the background.
