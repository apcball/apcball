# BOQ Purchase Control Implementation

## Overview
This implementation adds comprehensive purchase control functionality to the BOQ (Bill of Quantities) system, allowing users to track and control material purchases against BOQ quantities while providing flexibility to exceed quantities when necessary.

## Key Features Implemented

### 1. BOQ Line Purchase Tracking
- **total_requisitioned_qty**: Tracks total quantities requisitioned from all material requisitions
- **total_ordered_qty**: Tracks total quantities that have been ordered (approved requisitions)
- **total_received_qty**: Tracks total quantities that have been received
- **remaining_qty**: Calculates remaining quantities available for requisition
- **purchase_progress**: Shows purchase progress as a percentage

### 2. Enhanced Material Requisition System
- **BOQ Integration**: Material requisition lines now show BOQ tracking information
- **Quantity Validation**: Warns when requisition quantities exceed BOQ remaining quantities
- **Flexible Control**: Allows purchases to exceed BOQ quantities with warnings (not blocking)
- **Real-time Updates**: BOQ quantities update automatically when requisitions are created/modified

### 3. BOQ Material Requisition Wizard
- **Smart Line Selection**: Shows only BOQ lines with remaining quantities
- **Visual Indicators**: Color coding for different quantity statuses
- **Batch Processing**: Create requisitions for multiple BOQ lines at once
- **Quantity Control**: Default to remaining quantities but allow user modifications

### 4. Enhanced User Interface
- **Purchase Tracking Tab**: Dedicated view for monitoring purchase progress
- **Progress Bars**: Visual representation of purchase completion
- **Color Coding**: 
  - Green: Completed items
  - Yellow: Items with orders in progress
  - Blue: Items with requisitions submitted
  - Gray: Items fully requisitioned
- **Summary Statistics**: Overall BOQ purchase progress and amounts

## Technical Implementation

### Database Changes
```python
# New fields added to boq.line model
total_requisitioned_qty = fields.Float(string='Total Requisitioned Qty', compute='_compute_purchase_tracking', store=True)
total_ordered_qty = fields.Float(string='Total Ordered Qty', compute='_compute_purchase_tracking', store=True)
total_received_qty = fields.Float(string='Total Received Qty', compute='_compute_purchase_tracking', store=True)
remaining_qty = fields.Float(string='Remaining Qty', compute='_compute_purchase_tracking', store=True)
purchase_progress = fields.Float(string='Purchase Progress (%)', compute='_compute_purchase_tracking', store=True)

# New fields added to material.requisition.line model
boq_remaining_qty = fields.Float(string='BOQ Remaining Qty', related='boq_line_id.remaining_qty', readonly=True)
boq_total_qty = fields.Float(string='BOQ Total Qty', related='boq_line_id.adjusted_quantity', readonly=True)
boq_requisitioned_qty = fields.Float(string='BOQ Requisitioned Qty', related='boq_line_id.total_requisitioned_qty', readonly=True)
```

### Computation Logic
```python
@api.depends('requisition_line_ids', 'requisition_line_ids.quantity', 'requisition_line_ids.requisition_state')
def _compute_purchase_tracking(self):
    """Compute purchase tracking fields"""
    for record in self:
        # Calculate quantities based on requisition states
        active_req_lines = req_lines.filtered(lambda l: l.requisition_state not in ['cancelled', 'rejected'])
        record.total_requisitioned_qty = sum(active_req_lines.mapped('quantity'))
        
        ordered_req_lines = req_lines.filtered(lambda l: l.requisition_state in ['approved', 'ordered', 'received'])
        record.total_ordered_qty = sum(ordered_req_lines.mapped('quantity'))
        
        received_req_lines = req_lines.filtered(lambda l: l.requisition_state == 'received')
        record.total_received_qty = sum(received_req_lines.mapped('quantity'))
        
        record.remaining_qty = record.adjusted_quantity - record.total_requisitioned_qty
        
        if record.adjusted_quantity > 0:
            record.purchase_progress = (record.total_requisitioned_qty / record.adjusted_quantity) * 100
```

### Validation and Warnings
```python
@api.onchange('quantity', 'boq_line_id')
def _onchange_quantity_boq_check(self):
    """Check quantity against BOQ remaining quantity and show warning"""
    if self.boq_line_id and self.quantity:
        remaining_qty = self.boq_line_id.remaining_qty
        
        if self.quantity > remaining_qty:
            # Show warning but don't prevent the action
            warning_msg = _(
                'Warning: Requisition quantity (%s %s) exceeds remaining BOQ quantity (%s %s).\n'
                'You can still proceed with this requisition if needed.'
            ) % (self.quantity, self.uom_id.name, remaining_qty, self.boq_line_id.uom_id.name)
            
            return {
                'warning': {
                    'title': _('BOQ Quantity Exceeded'),
                    'message': warning_msg
                }
            }
```

## User Workflow

### 1. Creating Material Requisitions from BOQ
1. Open an approved BOQ
2. Click "Create Material Requisition" button
3. BOQ Material Requisition Wizard opens
4. Review lines with remaining quantities
5. Adjust quantities as needed (warnings shown if exceeding BOQ)
6. Click "Create Requisition"

### 2. Monitoring Purchase Progress
1. Open BOQ form view
2. Go to "Purchase Tracking" tab
3. View progress bars and status for each line
4. Check overall purchase progress in summary section

### 3. Creating Individual Line Requisitions
1. In BOQ lines, click "Create Requisition" button for specific lines
2. System creates requisition with remaining quantity as default
3. User can modify quantity (warnings shown if exceeding)

## Benefits

### For Project Managers
- **Complete Visibility**: See exactly what has been purchased vs planned
- **Progress Tracking**: Visual progress bars show completion status
- **Budget Control**: Track spending against BOQ budgets
- **Exception Management**: Identify items that exceed planned quantities

### For Procurement Teams
- **Clear Requirements**: See exactly what quantities are still needed
- **Avoid Over-purchasing**: Warnings when exceeding BOQ quantities
- **Flexible Operations**: Can still purchase more than BOQ when justified
- **Audit Trail**: Complete history of purchases vs BOQ

### For Finance Teams
- **Cost Control**: Track actual vs planned material costs
- **Budget Monitoring**: See purchase progress against BOQ budgets
- **Variance Analysis**: Identify cost overruns early
- **Reporting**: Comprehensive purchase tracking data

## Configuration

### Security Groups
- **Department Manager**: Can approve department-level requisitions
- **Material Requisition Manager**: Can approve final requisitions
- **BOQ Manager**: Can create and modify BOQs

### Workflow States
- **Draft**: Initial requisition creation
- **Submitted**: Submitted for department approval
- **Department Approved**: Approved by department manager
- **Approved**: Final approval for purchasing
- **Ordered**: Purchase orders created
- **Received**: Materials received

## Future Enhancements

### Planned Features
1. **Automatic Reorder Points**: Set minimum stock levels for automatic requisition creation
2. **Vendor Integration**: Direct integration with vendor catalogs and pricing
3. **Mobile App**: Mobile interface for field requisitions
4. **Advanced Analytics**: Dashboard with purchase analytics and trends
5. **Integration with Inventory**: Real-time stock level integration

### Reporting Enhancements
1. **BOQ vs Actual Reports**: Detailed variance analysis reports
2. **Purchase Progress Dashboard**: Real-time dashboard for project managers
3. **Cost Analysis Reports**: Material cost analysis and trends
4. **Vendor Performance**: Track vendor delivery and quality metrics

## Troubleshooting

### Common Issues
1. **Quantities not updating**: Check that requisition states are correct
2. **Warnings not showing**: Verify BOQ line has product and quantities set
3. **Progress not calculating**: Ensure adjusted_quantity is greater than zero
4. **Wizard not showing lines**: Check that BOQ lines have products assigned

### Support
For technical support or feature requests, contact the development team or refer to the module documentation.