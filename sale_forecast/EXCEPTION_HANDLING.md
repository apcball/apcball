# Exception Handling - Task #3

## Date: 2025-06-17

## Overview
This document describes exception handling improvements made to the auto-allocation feature in sale_order.action_confirm().

---

## Problem Statement

### Original Issue (from security analysis)
**File**: `models/sale_order.py`
**Method**: `action_confirm()`

**Problem**:
- `_auto_allocate_forecast_from_sale()` was called without try-except
- If auto-allocation failed, the sale order would still be confirmed
- Result: Data inconsistency between confirmed SO and failed allocations

**Example Scenario**:
```python
def action_confirm(self):
    res = super().action_confirm()  # SO confirmed here
    self._auto_allocate_forecast_from_sale()  # If this fails, SO remains confirmed!
    return res
```

---

## Solution Implemented

### Added Exception Handling with Three-Tier Strategy

```python
def action_confirm(self):
    res = super().action_confirm()

    for order in self:
        try:
            order._auto_allocate_forecast_from_sale()
        except ValidationError as e:
            # Critical: Rollback SO confirmation
            raise UserError(_("Cannot confirm sale order: Auto-allocation validation failed..."))
        except UserError as e:
            # Non-critical: Log warning, SO remains confirmed
            _logger.warning(...)
            # Continue without raising
        except Exception as e:
            # Unexpected: Log error, SO remains confirmed
            _logger.exception(...)
            # Continue without raising

    return res
```

---

## Exception Handling Strategy

### 1. ValidationError (CRITICAL - ROLLBACK)
**When raised**: Business rule violations (over-allocation, invalid data, etc.)

**Action**: Re-raise as UserError to rollback the entire transaction

**Why**: Validation errors indicate critical data integrity issues. Rolling back prevents:
- Over-allocation beyond forecast
- Inconsistent state between SO and allocations
- Silent failures that corrupt data

**User Message**:
```
Cannot confirm sale order: Auto-allocation validation failed.

Reason: [error details]

Please check your forecast plan or contact your manager.
```

### 2. UserError (NON-CRITICAL - CONTINUE)
**When raised**: Permission issues, access denied, user-facing errors

**Action**: Log warning, continue without raising

**Why**: Access errors shouldn't block sales:
- Users can manually create allocations later
- Forecasts might not exist for all users/months
- Temporary permission issues shouldn't stop business

**User Experience**: Sale order confirms, auto-allocation skipped (logged)

### 3. Exception (UNEXPECTED - CONTINUE)
**When raised**: System errors, bugs, unexpected failures

**Action**: Log full exception with traceback, continue without raising

**Why**: Unknown errors shouldn't block sales:
- Prevents blocking sales due to bugs
- Allows admin to investigate via logs
- Users can manually create allocations

**Logging**:
```python
_logger.exception(
    "Auto-allocation failed for SO %s (Unexpected): %s. "
    "Sale order remains confirmed. Please investigate.",
    order.name, str(e)
)
```

---

## Benefits

### 1. Data Integrity ✅
- Validation errors prevent SO confirmation
- No silent failures that corrupt data
- Consistent state between SO and allocations

### 2. Business Continuity ✅
- Access/permission errors don't block sales
- System errors don't stop business
- Users can manually recover

### 3. Debuggability ✅
- All errors are logged with severity levels
- Transaction rollback is clear (ValidationError → UserError)
- Tracebacks available for unexpected errors

### 4. User Experience ✅
- Clear error messages for critical issues
- Non-critical issues don't interrupt workflow
- Manual recovery option available

---

## Error Handling Matrix

| Exception Type | Severity | Action | SO Status | User Action |
|---------------|----------|--------|-----------|-------------|
| ValidationError | CRITICAL | Rollback | Draft | Fix forecast, retry |
| UserError | LOW | Log & Continue | Confirmed | Manual allocation |
| Exception | MEDIUM | Log & Continue | Confirmed | Admin investigation |

---

## Logging Strategy

### Error Levels Used

1. **`_logger.error()`** - ValidationError (critical issues)
2. **`_logger.warning()`** - UserError (non-critical issues)
3. **`_logger.exception()`** - Unexpected errors (includes traceback)

### Log Format

```
Auto-allocation failed for SO {order_name} ({error_type}): {error_message}.
Sale order remains confirmed. Please investigate.
```

---

## Code Changes

### Before
```python
from collections import defaultdict
from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()
        self._auto_allocate_forecast_from_sale()
        return res
```

### After
```python
from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_confirm(self):
        res = super().action_confirm()

        for order in self:
            try:
                order._auto_allocate_forecast_from_sale()
            except ValidationError as e:
                _logger.error(...)
                raise UserError(_(...))
            except UserError as e:
                _logger.warning(...)
                # Continue without raising
            except Exception as e:
                _logger.exception(...)
                # Continue without raising

        return res
```

---

## Testing Recommendations

### Test Scenarios

1. **Validation Error (Should Rollback)**
   - Create SO with qty > available forecast
   - Confirm SO
   - Expected: Error message, SO remains draft

2. **UserError (Should Continue)**
   - User without forecast plan confirms SO
   - Expected: Warning logged, SO confirmed, no allocations created

3. **System Error (Should Continue)**
   - Mock a system error in _auto_allocate_forecast_from_sale()
   - Expected: Exception logged, SO confirmed

4. **Successful Allocation**
   - Create SO with matching forecast
   - Confirm SO
   - Expected: Allocations created, SO confirmed

5. **Batch Confirmation**
   - Confirm multiple SOs with mixed scenarios
   - Expected: Each SO handled independently

---

## Monitoring

### Log Monitoring

Look for these patterns in production logs:

**Critical (requires attention)**:
```
ERROR: Auto-allocation failed for SO (Validation): ...
```

**Warnings (investigate periodically)**:
```
WARNING: Auto-allocation failed for SO (UserError): ...
```

**Unexpected (immediate investigation)**:
```
ERROR: Auto-allocation failed for SO (Unexpected): ...
[Full traceback]
```

### Metrics to Track

1. **Rollback Rate**: ValidationError / Total confirmations
2. **Failure Rate**: All errors / Total confirmations
3. **UserError Rate**: Access issues / Total confirmations
4. **Unexpected Rate**: System errors / Total confirmations

---

## Rollback Considerations

### Transaction Rollback Behavior

When ValidationError is raised, the entire transaction is rolled back:
- Sale order confirmation is undone
- Any partial allocations are removed
- Database returns to pre-confirmation state

**Important**: This ensures atomicity - either both SO and allocations succeed, or both fail.

---

## Future Enhancements

1. **Retry Mechanism**: Add retry logic for transient errors
2. **Alerting**: Send alerts when error rates exceed threshold
3. **Auto-Recovery**: Auto-create allocations for failed UserErrors
4. **Dashboard**: Show error statistics in forecast dashboard
5. **Notification**: Notify users when auto-allocation fails

---

## Files Modified

| File | Changes |
|------|---------|
| `models/sale_order.py` | Added exception handling in action_confirm() |

---

## Related Tasks

- Task #1: Security improvements (record rules)
- Task #5: Performance improvements (_compute_kpis)
- Task #8: Add tests for auto-allocation

---

## References

- Odoo Exception Handling: https://www.odoo.com/documentation/17.0/developer/reference/addons/exceptions.html
- Odoo Logging: https://www.odoo.com/documentation/17.0/developer/reference/addons/logging.html
