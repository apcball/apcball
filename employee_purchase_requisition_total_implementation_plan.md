# Implementation Plan: Adding Total Amount to Employee Purchase Requisition

## Overview
This plan outlines the steps to add total amount functionality to the Employee Purchase Requisition module. The implementation will include:
1. Subtotal calculation for each line item
2. Total amount calculation for the entire requisition
3. Display of these values in form, tree, and kanban views

## Changes Required

### 1. Model Changes

#### requisition.order Model (requisition_order.py)
- Add `price_subtotal` field to calculate line total (quantity × unit_price)
- Add compute method `_compute_price_subtotal`

#### employee.purchase.requisition Model (employee_purchase_requisition.py)
- Add `total_amount` field to sum all line subtotals
- Add compute method `_compute_total_amount`

### 2. View Changes

#### requisition_order_views.xml
- Add subtotal column to the tree view
- Make the subtotal readonly and formatted as currency

#### employee_purchase_requisition_views.xml
- **Form View**: Add total_amount field in a prominent position
- **Tree View**: Add total_amount column
- **Kanban View**: Display total_amount in the card

## Technical Implementation Details

### Field Definitions
```python
# In requisition.order
price_subtotal = fields.Float(
    string="Subtotal", 
    compute="_compute_price_subtotal", 
    store=True
)

# In employee.purchase.requisition
total_amount = fields.Float(
    string="Total Amount", 
    compute="_compute_total_amount", 
    store=True
)
```

### Compute Methods
```python
# In requisition.order
@api.depends('quantity', 'unit_price')
def _compute_price_subtotal(self):
    for line in self:
        line.price_subtotal = line.quantity * line.unit_price

# In employee.purchase.requisition
@api.depends('requisition_order_ids.price_subtotal')
def _compute_total_amount(self):
    for requisition in self:
        requisition.total_amount = sum(line.price_subtotal for line in requisition.requisition_order_ids)
```

### View Modifications
The views will be updated to display these fields with proper formatting and positioning for optimal user experience.

## Implementation Steps
1. Update the requisition.order model
2. Update the employee.purchase.requisition model
3. Update the requisition order tree view
4. Update the employee purchase requisition form view
5. Update the employee purchase requisition tree view
6. Update the employee purchase requisition kanban view
7. Test the implementation

## Benefits
- Users can immediately see the total value of each purchase requisition
- Better financial control and visibility
- Improved decision-making for approvals
- More professional and informative interface