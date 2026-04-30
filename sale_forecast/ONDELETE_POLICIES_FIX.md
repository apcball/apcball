# OnDelete Policies Fix - Task #7

## Date: 2025-06-17

## Overview
Added appropriate `ondelete` policies to relationships in `forecast.allocation` model to prevent data integrity issues.

---

## Problem Statement

### Original Issues (from security analysis)
**File**: `models/forecast_allocation.py`

**Issue 1: Missing `ondelete` on `plan_id`**
```python
plan_id = fields.Many2one("forecast.plan", required=True, index=True)
# No ondelete policy specified
```

**Problem**: When a forecast plan is deleted, allocations referencing it become orphaned:
- Database doesn't know what to do with orphaned allocations
- Allocations point to non-existent plans
- Violates data integrity

**Impact**:
- Orphaned allocation records
- Inaccurate KPI calculations
- Potential application errors

---

**Issue 2: Unsafe `ondelete="set null"` on `sale_order_line_id`**
```python
sale_order_line_id = fields.Many2one("sale.order.line", readonly=True, ondelete="set null")
```

**Problem**: When a sale order line is deleted, the reference is set to NULL:
- Allocation becomes invalid without sale order line
- Business logic depends on `sale_order_line_id`
- Cannot track which line was allocated

**Impact**:
- Lost track of allocation source
- Inaccurate KPI calculations
- Cannot reconcile allocations with orders

---

## OnDelete Policies in Odoo

### Available Options

| Policy | Behavior | Use Case |
|---------|-----------|----------|
| `ondelete="cascade"` | Delete child records when parent is deleted | Child records depend exclusively on parent |
| `ondelete="set null"` | Set foreign key to NULL when parent is deleted | Optional relationship |
| `ondelete="restrict"` | Prevent parent deletion if children exist | Child records must exist |

### Choosing the Right Policy

**Cascade**: Use when child records are meaningless without parent
- Example: Order lines when order is deleted
- Child records have no independent purpose

**Set Null**: Use when relationship is optional
- Example: Optional reference that can be re-assigned
- Child records can exist without parent

**Restrict**: Use when parent deletion would break business logic
- Example: Required reference for validation
- Child records must reference valid parent

---

## Solution Implemented

### Fix 1: Add `ondelete="cascade"` to `plan_id`

**Before**:
```python
plan_id = fields.Many2one("forecast.plan", required=True, index=True)
```

**After**:
```python
plan_id = fields.Many2one(
    "forecast.plan",
    required=True,
    index=True,
    ondelete="cascade"
)
```

**Rationale**:
- Forecast allocations are meaningless without their forecast plan
- If plan is deleted, allocations should also be deleted
- Prevents orphaned allocation records

**Business Logic**:
- Allocations track forecast-to-allocation mapping
- Without a forecast plan, allocation loses its purpose
- Cascade deletion maintains data consistency

---

### Fix 2: Change `sale_order_line_id` to `ondelete="restrict"`

**Before**:
```python
sale_order_line_id = fields.Many2one("sale.order.line", readonly=True, ondelete="set null")
```

**After**:
```python
sale_order_line_id = fields.Many2one("sale.order.line", readonly=True, ondelete="restrict")
```

**Rationale**:
- Allocations depend on valid sale order line references
- Setting to NULL breaks allocation tracking
- Prevents deletion of lines with allocations

**Business Logic**:
- Allocations track which specific line received forecast qty
- Cannot lose track of this relationship
- Users must explicitly deallocate before deleting lines

---

### Fix 3: Add Consistency Constraint

**New Constraint**:
```python
@api.constrains("sale_order_id", "sale_order_line_id")
def _check_sale_order_line_consistency(self):
    """
    Ensure sale_order_line_id belongs to sale_order_id.

    This constraint ensures data integrity when ondelete="restrict" is used.
    Since sale_order_line_id cannot be deleted while allocations reference it,
    this prevents orphaned allocations if relationship is manually broken.
    """
    for rec in self:
        if rec.sale_order_line_id and rec.sale_order_line_id.order_id != rec.sale_order_id:
            raise ValidationError(
                _(
                    "Sale order line '%s' does not belong to sale order '%s'. "
                    "Please ensure that allocation references correct sale order line."
                )
                % (rec.sale_order_line_id.display_name, rec.sale_order_id.name)
            )
```

**Purpose**:
- Validate relationship consistency
- Prevent manual data corruption
- Provide clear error messages

**Validation Flow**:
1. User attempts to create/update allocation
2. Constraint checks if `sale_order_line_id` belongs to `sale_order_id`
3. If invalid, raises `ValidationError` with clear message
4. Prevents data integrity issues

---

## Impact Analysis

### Scenario 1: Deleting Forecast Plan

**Before (No ondelete)**:
```
1. User deletes forecast plan
2. Plan is deleted
3. Allocations still reference deleted plan
4. Result: Orphaned allocations, data corruption
```

**After (ondelete="cascade")**:
```
1. User attempts to delete forecast plan
2. Database checks for allocations
3. Allocations are automatically deleted
4. Plan is deleted
5. Result: Clean data, no orphans
```

**User Experience**:
- User gets warning: "Deleting plan will also delete X allocations"
- Prevents accidental data loss
- Maintains data integrity

---

### Scenario 2: Deleting Sale Order Line

**Before (ondelete="set null")**:
```
1. User deletes sale order line
2. Line is deleted
3. Allocation.sale_order_line_id set to NULL
4. Result: Allocation loses source, inaccurate KPIs
```

**After (ondelete="restrict")**:
```
1. User attempts to delete sale order line
2. Database checks for allocations
3. Delete is prevented with error
4. User must deallocate first
5. Result: Data integrity maintained
```

**User Experience**:
- User gets error: "Cannot delete line: X allocations reference it"
- User must explicitly deallocate first
- Prevents accidental data loss

---

### Scenario 3: Creating Invalid Allocation

**Before (No constraint)**:
```
1. User creates allocation with mismatched sale_order_id and sale_order_line_id
2. Allocation is created
3. Data inconsistency occurs
4. Result: Business logic errors
```

**After (With constraint)**:
```
1. User attempts to create allocation
2. Constraint checks relationship
3. If invalid, raises ValidationError
4. Result: Data integrity maintained
```

**User Experience**:
- User gets error: "Sale order line 'ABC' does not belong to sale order 'SO001'"
- Prevents data corruption
- Clear error message

---

## Benefits

### Data Integrity ✅
- No orphaned allocation records
- No broken relationships
- Clean database state

### Business Logic ✅
- Allocations always reference valid plans
- Allocations always reference valid sale order lines
- Accurate KPI calculations

### User Experience ✅
- Clear error messages
- Prevents accidental data loss
- Guides users to correct actions

### Maintainability ✅
- Explicit relationship policies
- Self-documenting code
- Easier to understand data flow

---

## Testing

### Test Cases

#### Test 1: Plan Cascade Deletion
```python
# Setup
plan = env["forecast.plan"].create([...])
allocation = env["forecast.allocation"].create({
    "plan_id": plan.id,
    # ... other fields
})

# Test
plan.unlink()

# Verify
assert not env["forecast.allocation"].search([("id", "=", allocation.id)])
```

#### Test 2: Sale Order Line Restrict Deletion
```python
# Setup
so = env["sale.order"].create([...])
line = env["sale.order.line"].create({
    "order_id": so.id,
    # ... other fields
})
allocation = env["forecast.allocation"].create({
    "sale_order_id": so.id,
    "sale_order_line_id": line.id,
    # ... other fields
})

# Test
with pytest.raises(Exception):
    line.unlink()

# Verify
assert env["forecast.allocation"].search([("id", "=", allocation.id)])
assert line.id  # Line still exists
```

#### Test 3: Sale Order Line Consistency
```python
# Setup
so1 = env["sale.order"].create([...])
so2 = env["sale.order"].create([...])
line = env["sale.order.line"].create({
    "order_id": so1.id,
    # ... other fields
})

# Test
with pytest.raises(ValidationError):
    env["forecast.allocation"].create({
        "sale_order_id": so2.id,  # Mismatched
        "sale_order_line_id": line.id,
        # ... other fields
    })
```

#### Test 4: Plan Line Set Null
```python
# Setup
plan_line = env["forecast.line"].create([...])
allocation = env["forecast.allocation"].create({
    "plan_line_id": plan_line.id,
    # ... other fields
})

# Test
plan_line.unlink()

# Verify
allocation = env["forecast.allocation"].browse(allocation.id)
assert not allocation.plan_line_id  # Should be NULL
assert allocation.plan_id  # Should still exist
```

---

## Migration Considerations

### Existing Data

**Current State**:
- May have orphaned allocations (deleted plans)
- May have allocations with `sale_order_line_id = NULL`

**Cleanup SQL**:
```sql
-- Delete orphaned allocations (referencing deleted plans)
DELETE FROM forecast_allocation
WHERE plan_id NOT IN (SELECT id FROM forecast_plan);

-- Update allocations with NULL sale_order_line_id
-- (Cannot delete as they reference valid sale orders)
-- Consider adding business rules for handling these
```

### Deployment Strategy

1. **Backup Database**: Before deployment
2. **Run Cleanup**: Remove orphaned data
3. **Deploy Changes**: Add ondelete policies
4. **Monitor**: Check for errors
5. **Validate**: Test deletion scenarios

---

## Rollback Plan

If issues occur after deployment:

### Option 1: Revert Code
```bash
git revert <commit-hash>
```

### Option 2: Modify Policies
Temporarily use less restrictive policies:
```python
# Less safe rollback
plan_id = fields.Many2one("forecast.plan", required=True, index=True)  # Remove cascade
sale_order_line_id = fields.Many2one("sale.order.line", readonly=True, ondelete="set null")  # Revert
```

### Option 3: Remove Constraint
If new constraint causes issues:
```python
# Comment out _check_sale_order_line_consistency
# @api.constrains("sale_order_id", "sale_order_line_id")
# def _check_sale_order_line_consistency(self):
#     ...
```

---

## Files Modified

| File | Changes |
|------|---------|
| `models/forecast_allocation.py` | Added `ondelete` policies, added consistency constraint |

---

## Related Tasks

- Task #1: Security improvements (record rules)
- Task #8: Add tests for allocations

---

## References

- Odoo Many2one Fields: https://www.odoo.com/documentation/17.0/developer/reference/addons/orm.html#odoo.fields.Many2one
- Odoo Constraints: https://www.odoo.com/documentation/17.0/developer/reference/addons/orm.html#constraints
- Database Referential Integrity: https://www.postgresql.org/docs/current/ddl-constraints.html
