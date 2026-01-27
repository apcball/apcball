# Validation Error Fix: Job Cost Line Access

## Problem
Users reported a "Validation Error" when creating Purchase Orders:
`You are not allowed to access 'Job Cost Line' (job.cost.line) records.`

This occurs because standard users (e.g., Purchase Users) do not have read access to Job Costing models, but the `purchase.order` and `purchase.order.line` models are extended to link to `job.cost.line`, `job.cost.sheet`, and `job.order`.

## Solution
Added read-only access rights for `base.group_user` (Internal User) to the following models in `security/ir.model.access.csv`:
- `job.cost.line`
- `job.cost.sheet`
- `job.order`

This ensures that any internal user can view Purchase Orders that reference these objects without triggering access errors.

## Verification
1. Upgrade the `job_costing_management` module.
2. Attempt to create a Purchase Order as a standard user (non-Job Costing Manager).
3. The error should no longer appear.
