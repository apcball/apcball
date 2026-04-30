# Cross-User Allocation Validation - Task #9

## Date: 2025-06-17

## Overview
Added validation to prevent cross-user allocations in forecast_allocation model.

---

## Problem Statement

### Original Issue (from security analysis)
**File**: `models/forecast_allocation.py`
**Method**: `_create_or_update_sale_order_line()`

**Problem**: No validation for cross-user allocations
```python
# _create_or_update_sale_order_line() does NOT validate:
if self.sale_order_id.user_id != self.plan_id.user_id:
    raise ValidationError(...)
```

**Vulnerability**:
- User could allocate sale order to another user's forecast plan
- Bypasses record rules if sudo() is used
- Violates business logic and accountability

**Example Scenario**:
```
User A (Salesperson) creates SO
User B (Salesperson) has forecast plan
User A could allocate SO to User B's plan (if no validation)
Result: User B gets allocation for User A's sales
```

**Security Implications**:
- Unauthorized access to other users' forecasts
- Misallocation of forecast quantities
- Loss of accountability and audit trail

---

## Solution Implemented

### Added Constraint: `_check_cross_user_allocation()`

```python
@api.constrains("plan_id", "sale_order_id")
def _check_cross_user_allocation(self):
    """
    Prevent cross-user allocations.

    Ensure that sale order and forecast plan belong to the same user.
    This prevents users from allocating to other users' forecast plans.

    Business Logic:
    - Salesperson should allocate to their own forecast plan
    - Prevents unauthorized access to other users' forecasts
    - Ensures proper accountability and tracking
    """
    for rec in self:
        if rec.plan_id and rec.sale_order_id:
            so_user = rec.sale_order_id.user_id
            plan_user = rec.plan_id.user_id

            if so_user and plan_user and so_user != plan_user:
                raise ValidationError(
                    _(
                        "Cannot allocate sale order '%s' (salesperson: %s) "
                        "to forecast plan '%s' (user: %s). "
                        "\n\n"
                        "Sales orders can only be allocated to forecast plans "
                        "that belong to the same user. "
                        "Please select a forecast plan belonging to '%s'."
                    )
                    % (
                        rec.sale_order_id.name,
                        so_user.name,
                        rec.plan_id.name,
                        plan_user.name,
                        so_user.name,
                    )
                )
```

---

## Implementation Details

### Trigger Points

The constraint is triggered when:
1. **Creating allocation** (`create()`)
2. **Updating plan_id** (`write()`)
3. **Updating sale_order_id** (`write()`)

### Validation Logic

1. Check if both `plan_id` and `sale_order_id` are set
2. Get user IDs from both records
3. Compare user IDs
4. If different, raise `ValidationError`

### Error Message

```
Cannot allocate sale order 'SO001' (salesperson: John Doe)
to forecast plan 'FP-2024-001' (user: Jane Smith).

Sales orders can only be allocated to forecast plans
that belong to the same user.
Please select a forecast plan belonging to 'John Doe'.
```

---

## Business Logic Rationale

### Why Prevent Cross-User Allocation?

1. **Accountability**:
   - Each user is responsible for their own forecast
   - Cross-user allocation blurs responsibility
   - Difficult to track performance

2. **Fairness**:
   - Users compete for forecast quantities
   - Cross-user allocation could bypass limits
   - Unfair advantage

3. **Data Integrity**:
   - Forecast plans tied to individual users
   - Cross-user allocation breaks this model
   - KPI calculations become inaccurate

4. **Audit Trail**:
   - Need clear ownership for audit purposes
   - Cross-user allocation complicates audits
   - Regulatory compliance issues

---

## Impact Analysis

### Scenario 1: Valid Allocation (Same User)

**Setup**:
```
SO: SO001, user_id = John Doe
Plan: FP-2024-001, user_id = John Doe
```

**Action**:
```python
allocation = env["forecast.allocation"].create({
    "sale_order_id": so.id,
    "plan_id": plan.id,
    "allocated_qty": 50,
})
```

**Result**: ✅ Success
- Validation passes (same user)
- Allocation created
- Business logic satisfied

---

### Scenario 2: Invalid Allocation (Different User)

**Setup**:
```
SO: SO001, user_id = John Doe
Plan: FP-2024-002, user_id = Jane Smith
```

**Action**:
```python
allocation = env["forecast.allocation"].create({
    "sale_order_id": so.id,
    "plan_id": plan.id,
    "allocated_qty": 50,
})
```

**Result**: ❌ ValidationError
```
Cannot allocate sale order 'SO001' (salesperson: John Doe)
to forecast plan 'FP-2024-002' (user: Jane Smith).
...
```

---

### Scenario 3: Allocation Without User

**Setup**:
```
SO: SO001, user_id = None
Plan: FP-2024-001, user_id = John Doe
```

**Action**:
```python
allocation = env["forecast.allocation"].create({
    "sale_order_id": so.id,
    "plan_id": plan.id,
    "allocated_qty": 50,
})
```

**Result**: ✅ Success
- Validation allows (no user to compare)
- Allocation created
- This is intentional for flexibility

---

### Scenario 4: Manager Override

**Setup**:
```
User: Manager (with sudo access)
SO: SO001, user_id = John Doe
Plan: FP-2024-002, user_id = Jane Smith
```

**Action**:
```python
# Manager tries to bypass
allocation = env["forecast.allocation"].sudo().create({
    "sale_order_id": so.id,
    "plan_id": plan.id,
    "allocated_qty": 50,
})
```

**Result**: ❌ ValidationError
- **Still blocked!**
- Constraint runs regardless of sudo
- Even managers cannot bypass

---

## Benefits

### Security ✅
- Prevents unauthorized access to other users' forecasts
- No cross-user allocation even with sudo
- Maintains clear ownership boundaries

### Business Logic ✅
- Enforces accountability
- Fair competition for forecast quantities
- Accurate performance tracking

### Data Integrity ✅
- Prevents misallocation
- Accurate KPI calculations
- Clear audit trail

### User Experience ✅
- Clear error messages
- Guidance on correct action
- Prevents accidental errors

---

## Testing

### Test Cases

#### Test 1: Same User Allocation
```python
def test_cross_user_validation_same_user(self):
    """Allow allocation when SO and plan belong to same user."""
    plan = self.create_forecast_plan(user=self.user_sales)
    so = self.create_sale_order(user=self.user_sales)

    # Should succeed
    allocation = self.create_allocation(plan, so)
    self.assertTrue(allocation)
```

#### Test 2: Different User Allocation
```python
def test_cross_user_validation_different_user(self):
    """Block allocation when SO and plan belong to different users."""
    plan = self.create_forecast_plan(user=self.user_sales)
    so = self.create_sale_order(user=self.user_planner)

    # Should fail
    with self.assertRaises(ValidationError):
        self.create_allocation(plan, so)
```

#### Test 3: Allocation Without User
```python
def test_cross_user_validation_no_user(self):
    """Allow allocation when SO has no user_id."""
    plan = self.create_forecast_plan(user=self.user_sales)
    so = self.create_sale_order(user=None)

    # Should succeed
    allocation = self.create_allocation(plan, so)
    self.assertTrue(allocation)
```

#### Test 4: Update to Different User
```python
def test_cross_user_validation_update_plan(self):
    """Block update when changing plan to different user."""
    plan1 = self.create_forecast_plan(user=self.user_sales)
    plan2 = self.create_forecast_plan(user=self.user_planner)
    so = self.create_sale_order(user=self.user_sales)

    allocation = self.create_allocation(plan1, so)

    # Should fail
    with self.assertRaises(ValidationError):
        allocation.write({"plan_id": plan2.id})
```

#### Test 5: Sudo Bypass Attempt
```python
def test_cross_user_validation_sudo_blocked(self):
    """Constraint should block even with sudo."""
    plan = self.create_forecast_plan(user=self.user_sales)
    so = self.create_sale_order(user=self.user_planner)

    # Should still fail with sudo
    with self.assertRaises(ValidationError):
        self.env["forecast.allocation"].sudo().create({
            "plan_id": plan.id,
            "sale_order_id": so.id,
            "allocated_qty": 50,
        })
```

---

## Integration with Other Security Measures

### Layer 1: Model Access Rights
```python
# security/ir.model.access.csv
# Users have read/write access to their own allocations
```

### Layer 2: Record Rules
```python
# security/forecast_record_rules.xml
# Users can only access allocations for their own plans or SOs
```

### Layer 3: Business Logic Constraints (NEW)
```python
# _check_cross_user_allocation()
# Validates SO and plan belong to same user
# Runs regardless of sudo
```

### Layer 4: Auto-Allocation Filtering
```python
# models/sale_order.py
# Auto-allocation only matches user's own plans
```

**Defense in Depth**:
- Even if one layer is bypassed, others still protect
- Multiple layers ensure comprehensive security
- Redundant protection is intentional

---

## Rollback Considerations

### If Issues Occur

**Option 1**: Comment out constraint temporarily
```python
# @api.constrains("plan_id", "sale_order_id")
# def _check_cross_user_allocation(self):
#     ...
```

**Option 2**: Add bypass flag (NOT RECOMMENDED)
```python
@api.model
def _allow_cross_user(self):
    """Override for testing/migration."""
    return False

def _check_cross_user_allocation(self):
    if self._allow_cross_user():
        return
    # ... validation logic
```

**Option 3**: Make it optional per plan
```python
plan_id = fields.Many2one(
    "forecast.plan",
    required=True,
    ondelete="cascade",
    help="Forecast plan. Plan user must match sale order user."
)
```

---

## Files Modified

| File | Changes |
|------|---------|
| `models/forecast_allocation.py` | Added `_check_cross_user_allocation()` constraint |

---

## Related Tasks

- Task #1: Security improvements (record rules)
- Task #3: Exception handling (tested here)
- Task #8: Test suite expansion (tests for this)

---

## References

- Odoo Constraints: https://www.odoo.com/documentation/17.0/developer/reference/addons/orm.html#constraints
- Odoo Exceptions: https://www.odoo.com/documentation/17.0/developer/reference/addons/exceptions.html
- Defense in Depth: https://en.wikipedia.org/wiki/Defense_in_depth_(computing)
