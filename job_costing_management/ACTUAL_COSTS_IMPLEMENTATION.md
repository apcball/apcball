# Job Costing Management - Actual Costs Implementation Guide

## Overview
The Job Costing Management module implements a comprehensive actual cost tracking system that automatically captures real costs from various sources and compares them with planned costs.

## When Actual Costs Occur

### 1. Material Costs (ค่าวัสดุ)

#### Triggers for Actual Cost Updates:
- **Purchase Order Confirmation**: When PO state changes to 'purchase' or 'done'
- **Goods Receipt**: When `qty_received` is updated in purchase order lines
- **Vendor Bill/Invoice Posting**: When supplier invoices are posted

#### Calculation Logic:
```python
# From job_cost_sheet.py lines 354-372
@api.depends('purchase_order_line_ids.product_qty', 'purchase_order_line_ids.qty_received',
             'timesheet_ids.unit_amount', 'invoice_line_ids.quantity')
def _compute_actual_qty(self):
    for record in self:
        if record.cost_type == 'material':
            # Use received quantity from confirmed purchase orders
            po_lines = record.purchase_order_line_ids.filtered(lambda l: l.order_id.state in ['purchase', 'done'])
            record.actual_qty = sum(po_lines.mapped('qty_received'))
```

#### Data Sources:
- **Quantity**: `purchase_order_line_ids.qty_received`
- **Unit Cost**: Calculated from `price_subtotal / product_qty`
- **Total Cost**: `actual_qty * actual_unit_cost`

### 2. Labour Costs (ค่าแรงงาน)

#### Triggers for Actual Cost Updates:
- **Timesheet Entry**: When employees log time against job cost lines
- **Timesheet Approval**: When timesheet entries are validated

#### Calculation Logic:
```python
# From job_cost_sheet.py lines 362-363
elif record.cost_type == 'labour':
    record.actual_qty = sum(record.timesheet_ids.mapped('unit_amount'))
```

#### Data Sources:
- **Quantity**: `timesheet_ids.unit_amount` (hours worked)
- **Unit Cost**: Calculated from `timesheet_ids.amount / unit_amount`
- **Total Cost**: Sum of `timesheet_ids.amount`

### 3. Overhead Costs (ค่าใช้จ่ายทั่วไป)

#### Triggers for Actual Cost Updates:
- **Invoice Posting**: When overhead invoices are posted (primary source)
- **Purchase Order Receipt**: Fallback when no invoices exist

#### Calculation Logic:
```python
# From job_cost_sheet.py lines 364-371
else:  # overhead
    # Use invoice lines first, fallback to purchase orders
    if record.invoice_line_ids:
        record.actual_qty = sum(record.invoice_line_ids.filtered(
            lambda l: l.move_id.state == 'posted').mapped('quantity'))
    else:
        po_lines = record.purchase_order_line_ids.filtered(lambda l: l.order_id.state in ['purchase', 'done'])
        record.actual_qty = sum(po_lines.mapped('qty_received'))
```

## Automatic Integration Points

### 1. Purchase Order Integration

#### File: `models/purchase_order.py`

**Key Features:**
- Auto-linking PO to job cost sheet via material requisition
- Automatic actual cost updates on PO confirmation
- Analytic account propagation to PO lines

**Workflow:**
1. Material Requisition → BOQ → Job Cost Sheet
2. Create RFQ from Job Cost Sheet
3. PO Confirmation triggers actual cost update
4. Receipt updates actual quantities

### 2. Invoice Integration

#### File: `models/account_move.py`

**Key Features:**
- Auto-linking invoices to job cost sheet via PO origin
- Invoice line linking to specific job cost lines
- Analytic account-based matching

**Workflow:**
1. Vendor Bill created from PO
2. Auto-link to job cost sheet via PO reference
3. Invoice posting triggers actual cost update
4. Real-time variance calculation

### 3. Timesheet Integration

#### File: `models/hr_timesheet.py`

**Key Features:**
- Direct linking of timesheet entries to job cost lines
- Project/task-based cost allocation
- Real-time labor cost tracking

**Workflow:**
1. Employee logs time on project task
2. Timesheet linked to job order/cost line
3. Actual labor costs updated immediately
4. Variance calculated against planned hours

## Actual Cost Computation Methods

### 1. Automatic Computation (Real-time)

```python
# From job_cost_sheet.py lines 98-104
@api.depends('material_cost_ids.actual_cost', 'labour_cost_ids.actual_cost', 'overhead_cost_ids.actual_cost')
def _compute_actual_costs(self):
    for record in self:
        record.actual_material_cost = sum(record.material_cost_ids.mapped('actual_cost'))
        record.actual_labour_cost = sum(record.labour_cost_ids.mapped('actual_cost'))
        record.actual_overhead_cost = sum(record.overhead_cost_ids.mapped('actual_cost'))
        record.actual_total_cost = record.actual_material_cost + record.actual_labour_cost + record.actual_overhead_cost
```

### 2. Manual Synchronization

```python
# From job_cost_sheet.py lines 242-254
def action_sync_actual_costs(self):
    """Manually sync actual costs from all linked POs and Invoices"""
    for cost_line in self.material_cost_ids + self.labour_cost_ids + self.overhead_cost_ids:
        cost_line.update_actual_costs_from_purchases()
    return {
        'type': 'ir.actions.client',
        'tag': 'display_notification',
        'params': {
            'title': 'Success',
            'message': 'Actual costs have been synchronized with purchase orders and invoices.',
            'type': 'success',
        }
    }
```

## Variance Analysis

### Real-time Variance Calculation

```python
# From job_cost_sheet.py lines 106-113
@api.depends('total_material_cost', 'actual_material_cost', 'total_labour_cost', 'actual_labour_cost',
             'total_overhead_cost', 'actual_overhead_cost', 'total_cost', 'actual_total_cost')
def _compute_variance(self):
    for record in self:
        record.material_variance = record.actual_material_cost - record.total_material_cost
        record.labour_variance = record.actual_labour_cost - record.total_labour_cost
        record.overhead_variance = record.actual_overhead_cost - record.total_overhead_cost
        record.total_variance = record.actual_total_cost - record.total_cost
```

### Variance Types:
- **Quantity Variance**: `actual_qty - planned_qty`
- **Cost Variance**: `actual_cost - total_cost`
- **Material Variance**: `actual_material_cost - total_material_cost`
- **Labour Variance**: `actual_labour_cost - total_labour_cost`
- **Overhead Variance**: `actual_overhead_cost - total_overhead_cost`

## Smart Buttons and Reporting

### Available Smart Buttons:
1. **Purchase Orders**: View all related POs
2. **Timesheets**: View all timesheet entries
3. **Invoices**: View all related invoices
4. **Cost Lines**: View detailed cost analysis

### Key Reports:
- Job Cost Sheet Report
- Cost Analysis by Type
- Variance Analysis Report
- Project Cost Summary

## Best Practices for Actual Cost Tracking

### 1. Setup Requirements:
- Configure analytic accounts for projects
- Link job cost sheets to analytic accounts
- Ensure proper product categorization (service vs storable)

### 2. Workflow Recommendations:
- Create job cost sheets before starting procurement
- Use material requisitions for systematic purchasing
- Regular timesheet entry for accurate labor tracking
- Prompt invoice processing for overhead costs

### 3. Monitoring:
- Regular variance analysis
- Monthly actual vs planned cost reviews
- Exception reporting for significant variances
- Cost trend analysis

## Technical Implementation Details

### Database Structure:
- **job.cost.sheet**: Main cost sheet entity
- **job.cost.line**: Individual cost line items
- **Integration fields**: Links to PO, invoices, timesheets

### Key Computed Fields:
- `actual_material_cost`, `actual_labour_cost`, `actual_overhead_cost`
- `material_variance`, `labour_variance`, `overhead_variance`
- `actual_qty`, `actual_unit_cost`, `actual_cost`

### Triggers and Dependencies:
- Purchase order confirmation
- Goods receipt processing
- Invoice posting
- Timesheet validation

This implementation provides comprehensive actual cost tracking with real-time updates and variance analysis for effective project cost management.