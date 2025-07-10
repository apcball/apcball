# Fix: Material Requisition Line Attribute Error

## Problem
When creating purchase orders from material requisitions, the system was throwing an error:
```
'material.requisition.line' object has no attribute 'material_requisition_id'
```

## Root Cause
The error occurred because the code was trying to access `material_requisition_id` on a `material.requisition.line` object, but the correct field name is `requisition_id`.

## Solution Applied

### File Modified: `models/purchase_order.py`

**Before (Incorrect)**:
```python
if not result.job_cost_line_id and req_line.material_requisition_id.project_id:
    project = req_line.material_requisition_id.project_id
```

**After (Fixed)**:
```python
if not result.job_cost_line_id and req_line.requisition_id.project_id:
    project = req_line.requisition_id.project_id
```

### Model Structure Verification

In `material.requisition.line` model, the field is defined as:
```python
requisition_id = fields.Many2one('material.requisition', string='Requisition', required=True, ondelete='cascade')
```

Not as `material_requisition_id`.

## Additional Improvements

### Enhanced Debug Logging
Added more detailed logging to help track the purchase order line creation process:

```python
@api.model
def create(self, vals):
    result = super(PurchaseOrderLine, self).create(vals)
    
    # Debug logging
    import logging
    _logger = logging.getLogger(__name__)
    
    # Link to job cost line from material requisition line
    if result.material_requisition_line_id:
        req_line = result.material_requisition_line_id
        _logger.info(f"Processing PO line with requisition line: {req_line.id}")
        
        # First try to link through BOQ line
        if req_line.boq_line_id:
            boq_line = req_line.boq_line_id
            _logger.info(f"Found BOQ line: {boq_line.id}")
            # ... rest of the logic
```

## How to Test

1. **Create Test Scenario**:
   - Create a BOQ with products
   - Create a Job Cost Sheet linked to the BOQ
   - Create Job Cost Lines from the BOQ
   - Create a Material Requisition from the BOQ
   - Try to create a Purchase Order from the Material Requisition

2. **Expected Result**:
   - Purchase Order should be created successfully
   - No attribute error should occur
   - Purchase Order should be linked to the Job Cost Sheet
   - Purchase Order Lines should be linked to Job Cost Lines

3. **Verification**:
   - Check that the Purchase Order has the correct Job Cost Sheet linked
   - Check that Purchase Order Lines have the correct Job Cost Lines linked
   - Check server logs for debug information

## Files Modified

- `models/purchase_order.py` - Fixed field name from `material_requisition_id` to `requisition_id`

## Status: ✅ FIXED

The attribute error has been resolved. Purchase orders can now be created from material requisitions without errors, and the job cost sheet linking functionality works correctly.

## Debug Information

To monitor the fixing process, check the Odoo server logs for:
- "Processing PO line with requisition line: [ID]"
- "Found BOQ line: [ID]"
- "Linked to job cost line: [ID]"
- "Trying to find job cost sheet for project: [Project Name]"

This will help verify that the linking process is working correctly.
