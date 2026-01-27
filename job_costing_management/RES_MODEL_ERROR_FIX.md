# Res Model Error Fix

## Problem
A new error appeared during form operations:
```
EvalError: Can not evaluate python expression: (['|', ('res_model', '=', False), ('res_model', '=', res_model)])
Error: Name 'res_model' is not defined
```

## Root Cause
This error occurs because:
1. Our models inherit from `mail.thread` and `mail.activity.mixin`
2. These mixins add fields that have domains referencing the `res_model` variable
3. The `res_model` variable is typically passed in the context when opening forms/views
4. When the context doesn't include `res_model`, the domain evaluation fails

## Solution Implemented

### 1. Added Context to Action Methods
Updated all methods that return purchase order actions to include `res_model` in the context:

**File**: `models/material_requisition.py`
- `action_view_purchase_orders()` - Added `'context': {'res_model': 'purchase.order'}`
- `action_create_purchase_order()` - Added `'context': {'res_model': 'purchase.order'}`

**File**: `models/job_cost_sheet.py`
- `action_view_purchase_orders()` - Added `'context': {'res_model': 'purchase.order'}`

### 2. Added Context to XML Actions
**File**: `views/purchase_order_views.xml`
- `action_purchase_order_job_costing` - Added `<field name="context">{'res_model': 'purchase.order'}</field>`

### 3. Why This Works
- The `res_model` variable is now available in the context when forms are opened
- Domain expressions can evaluate `res_model` correctly
- Activity and mail-related fields can properly filter their results
- The error is prevented at the source

## Benefits
1. **Proper Context**: All purchase order actions now have the correct model context
2. **Domain Evaluation**: Fields with `res_model` domains can evaluate correctly
3. **Mail Integration**: Mail and activity features work properly
4. **Error Prevention**: Prevents the EvalError from occurring

## Files Modified
1. `/models/material_requisition.py` - Added context to purchase order actions
2. `/models/job_cost_sheet.py` - Added context to purchase order actions  
3. `/views/purchase_order_views.xml` - Added context to XML action definition

## Testing
After implementing these changes:
1. Opening purchase orders from material requisitions should work without `res_model` errors
2. Opening purchase orders from job cost sheets should work without `res_model` errors
3. Creating purchase orders should work without `res_model` errors
4. All domain evaluations should work correctly

## Related Issues
This fix addresses the `res_model` undefined error that was occurring after fixing the `approval_state` error. Both issues were related to context and domain evaluation problems when opening purchase order views from our job costing module.
