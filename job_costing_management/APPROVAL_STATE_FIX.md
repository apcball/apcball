# Approval State Error Fix

## Problem
The job costing management module was encountering errors when trying to display purchase orders due to a missing `approval_state` field. This field is added by custom modules like `custom_purchase_approval` or `buz_custom_po`, but when these modules are not installed or when their views are referenced, it causes errors.

## Error Message
```
OwlError: "purchase.order"."approval_state" field is undefined.
```

## Root Cause
The issue occurred because:
1. Smart buttons in material requisitions and job cost sheets were opening purchase order views
2. These views were trying to use the default purchase order form/tree views
3. Other custom modules in the system add `approval_state` fields to purchase order views
4. When those modules' views are inherited or referenced, but the field doesn't exist in the context, it causes the error

## Solution Implemented

### 1. Created Custom Purchase Order Views
- **File**: `views/purchase_order_views.xml`
- **Tree View**: `view_purchase_order_tree_job_costing` - Simple tree view with only essential fields
- **Action**: `action_purchase_order_job_costing` - Uses only the tree view to avoid form view issues

### 2. Updated Model Methods
- **File**: `models/material_requisition.py`
  - `action_view_purchase_orders()` - Now uses custom tree view
  - `action_create_purchase_order()` - Now uses custom tree view
- **File**: `models/job_cost_sheet.py`
  - `action_view_purchase_orders()` - Now uses custom tree view

### 3. View Strategy
- **Tree View Only**: The action only opens purchase orders in tree view mode
- **No Form View**: Avoided creating a custom form view to prevent domain field issues
- **Essential Fields Only**: Only includes fields that are guaranteed to exist in standard Odoo

### 4. Benefits
- **Isolation**: Our module is now isolated from other custom purchase order modules
- **Stability**: No dependency on `approval_state` or other custom fields
- **Compatibility**: Works regardless of which other purchase-related modules are installed
- **Functionality**: Users can still view purchase orders, just in a simplified interface

## Files Modified
1. `/views/purchase_order_views.xml` - Created custom views
2. `/models/material_requisition.py` - Updated action methods
3. `/models/job_cost_sheet.py` - Updated action methods

## Testing
After implementing these changes:
1. Material requisition smart buttons should work without errors
2. Job cost sheet smart buttons should work without errors  
3. Purchase order creation from material requisitions should work
4. All views should load without `approval_state` errors

## Future Considerations
If a full-featured purchase order form is needed in the future, we could:
1. Create a complete custom form view with all necessary fields
2. Use view inheritance to selectively remove problematic fields
3. Add conditional logic to handle missing fields gracefully
