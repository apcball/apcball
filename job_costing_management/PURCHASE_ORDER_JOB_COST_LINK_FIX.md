# Purchase Order - Job Cost Sheet Link Fix

## Problem
Purchase orders created from material requisitions were not properly linked to job cost sheets, causing issues with cost tracking and reporting.

## Root Cause
1. In `action_create_purchase_order()` method in `material_requisition.py`, the code was not setting the `material_requisition_id` and `material_requisition_line_id` fields due to incorrect comments suggesting these fields didn't exist.
2. The linking logic in purchase order creation was not robust enough to handle different scenarios.

## Solution Applied

### 1. Fixed Material Requisition Purchase Order Creation
**File**: `models/material_requisition.py`

```python
# In action_create_purchase_order method:
po_vals = {
    'partner_id': vendor.id,
    'origin': self.name,
    'material_requisition_id': self.id,  # Now properly set
    'order_line': []
}

for line in lines:
    po_line_vals = {
        'product_id': line.product_id.id,
        'name': line.description,
        'product_qty': line.quantity,
        'product_uom': line.uom_id.id,
        'price_unit': line.estimated_cost,
        'material_requisition_line_id': line.id,  # Now properly set
    }
```

### 2. Enhanced Purchase Order Auto-Linking
**File**: `models/purchase_order.py`

#### Purchase Order Level:
```python
@api.model
def create(self, vals):
    result = super(PurchaseOrder, self).create(vals)
    
    # Auto-link to job cost sheet if material requisition is provided
    if result.material_requisition_id and result.material_requisition_id.boq_id:
        boq = result.material_requisition_id.boq_id
        if boq.job_cost_sheet_id:
            result.job_cost_sheet_id = boq.job_cost_sheet_id.id
            result.project_id = boq.project_id.id
            result.job_order_id = boq.job_order_id.id if boq.job_order_id else False
            
            # Also set analytic account on purchase order lines
            if boq.job_cost_sheet_id.analytic_account_id:
                for line in result.order_line:
                    line.analytic_account_id = boq.job_cost_sheet_id.analytic_account_id.id
```

#### Purchase Order Line Level:
```python
@api.model
def create(self, vals):
    result = super(PurchaseOrderLine, self).create(vals)
    
    # Link to job cost line from material requisition line
    if result.material_requisition_line_id:
        req_line = result.material_requisition_line_id
        
        # First try to link through BOQ line
        if req_line.boq_line_id:
            boq_line = req_line.boq_line_id
            # Find matching job cost line
            if boq_line.cost_line_ids:
                matching_cost_line = boq_line.cost_line_ids.filtered(
                    lambda l: l.product_id == result.product_id
                )
                if matching_cost_line:
                    result.job_cost_line_id = matching_cost_line[0].id
                    # Also set analytic account
                    if matching_cost_line[0].analytic_account_id:
                        result.analytic_account_id = matching_cost_line[0].analytic_account_id.id
        
        # If no job cost line found from BOQ, try material requisition project
        if not result.job_cost_line_id and req_line.material_requisition_id.project_id:
            project = req_line.material_requisition_id.project_id
            # Find job cost sheet for this project
            cost_sheet = self.env['job.cost.sheet'].search([
                ('project_id', '=', project.id),
                ('state', '=', 'approved')
            ], limit=1)
            
            if cost_sheet:
                # Set analytic account
                if cost_sheet.analytic_account_id:
                    result.analytic_account_id = cost_sheet.analytic_account_id.id
                
                # Check if there's an existing cost line for this product
                existing_line = cost_sheet.material_cost_ids.filtered(
                    lambda l: l.product_id == result.product_id
                )
                
                if existing_line:
                    result.job_cost_line_id = existing_line[0].id
                else:
                    # Create new cost line
                    cost_line_vals = {
                        'cost_sheet_id': cost_sheet.id,
                        'cost_type': 'material',
                        'product_id': result.product_id.id,
                        'name': result.product_id.name,
                        'planned_qty': result.product_qty,
                        'unit_cost': result.price_unit,
                        'uom_id': result.product_uom.id,
                        'analytic_account_id': cost_sheet.analytic_account_id.id if cost_sheet.analytic_account_id else False,
                    }
                    new_cost_line = self.env['job.cost.line'].create(cost_line_vals)
                    result.job_cost_line_id = new_cost_line.id
```

### 3. Enhanced Purchase Order Views
**File**: `views/purchase_order_views.xml`

Added job cost sheet fields to purchase order views:
- `job_cost_sheet_id` in tree and form views
- `material_requisition_line_id` and `job_cost_line_id` in purchase order line views
- `analytic_account_id` for proper cost tracking

## How to Test

### 1. Create Full Workflow
1. Create a BOQ with products and quantities
2. Create job cost lines from BOQ
3. Create material requisition from BOQ
4. Create purchase order from material requisition

### 2. Verify Linking
1. Check that purchase order has:
   - `material_requisition_id` set
   - `job_cost_sheet_id` set
   - `project_id` set
2. Check that purchase order lines have:
   - `material_requisition_line_id` set
   - `job_cost_line_id` set
   - `analytic_account_id` set

### 3. Test Scenarios
1. **BOQ with Job Cost Sheet**: Should link directly through BOQ
2. **Project without BOQ**: Should find job cost sheet by project
3. **New Products**: Should create new job cost lines automatically
4. **Multiple Vendors**: Should create separate purchase orders with proper linking

## Expected Results
- Purchase orders are properly linked to job cost sheets
- Purchase order lines are linked to specific job cost lines
- Cost tracking works correctly across the entire workflow
- Analytic accounts are properly set for financial reporting
- Smart buttons show correct counts and relationships

## Files Modified
- `models/material_requisition.py`
- `models/purchase_order.py`
- `views/purchase_order_views.xml`
