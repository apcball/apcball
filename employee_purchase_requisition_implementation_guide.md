# Complete Implementation Guide: Adding Total Amount to Employee Purchase Requisition

## Overview
This guide provides all the code changes needed to add total amount functionality to the Employee Purchase Requisition module.

## 1. Model Changes

### 1.1 Update requisition_order.py
File: `employee_purchase_requisition/models/requisition_order.py`

Add the following field to the RequisitionOrder class (after line 41, after the unit_price field):

```python
price_subtotal = fields.Float(
    string="Subtotal",
    compute="_compute_price_subtotal",
    store=True,
    help="Automatically calculated as quantity × unit price"
)
```

Add the following compute method to the RequisitionOrder class (after the existing onchange method):

```python
@api.depends('quantity', 'unit_price')
def _compute_price_subtotal(self):
    """Calculate subtotal for each line item"""
    for line in self:
        line.price_subtotal = line.quantity * line.unit_price
```

### 1.2 Update employee_purchase_requisition.py
File: `employee_purchase_requisition/models/employee_purchase_requisition.py`

Add the following field to the PurchaseRequisition class (around line 180, after the internal_transfer_count field):

```python
total_amount = fields.Float(
    string="Total Amount",
    compute="_compute_total_amount",
    store=True,
    help="Total value of all items in this requisition"
)
```

Add the following compute method to the PurchaseRequisition class (after the existing compute methods):

```python
@api.depends('requisition_order_ids.price_subtotal')
def _compute_total_amount(self):
    """Calculate total amount for the requisition"""
    for requisition in self:
        requisition.total_amount = sum(line.price_subtotal for line in requisition.requisition_order_ids)
```

## 2. View Changes

### 2.1 Update requisition_order_views.xml
File: `employee_purchase_requisition/views/requisition_order_views.xml`

Modify the tree view to add the subtotal column (after line 16, after the quantity field):

```xml
<field name="unit_price" string="Unit Price"/>       
<field name="quantity"/>
<field name="price_subtotal" string="Subtotal" readonly="1" widget="monetary"/>
<field name="uom"/>
```

The complete tree view should look like this:

```xml
<tree editable="bottom">
    <field name="product_id"/>
    <field name="description"/>
    <field name="analytic_distribution" 
           widget="analytic_distribution" 
           groups="analytic.group_analytic_accounting"
           options="{'product_field': 'product_id'}"/>
    <field name="unit_price" string="Unit Price"/>       
    <field name="quantity"/>
    <field name="price_subtotal" string="Subtotal" readonly="1" widget="monetary"/>
    <field name="uom"/>
    <field name="partner_id" 
           groups="employee_purchase_requisition.employee_requisition_head,employee_purchase_requisition.employee_requisition_manager"/>
</tree>
```

### 2.2 Update employee_purchase_requisition_views.xml - Form View
File: `employee_purchase_requisition/views/employee_purchase_requisition_views.xml`

Add a total amount stat button to the button_box (after line 104, after the internal_transfer_count button):

```xml
<button class="oe_stat_button" 
        type="object"
        name="get_internal_transfer"
        icon="fa-truck"
        invisible="not internal_transfer_count">
    <field string="Internal Transfer"
           name="internal_transfer_count"
           widget="statinfo"/>
</button>
<button class="oe_stat_button" 
        icon="fa-money"
        invisible="not total_amount">
    <field string="Total Amount"
           name="total_amount"
           widget="monetary"
           options="{'currency_field': 'company_currency_id'}"/>
</button>
```

### 2.3 Update employee_purchase_requisition_views.xml - Tree View
File: `employee_purchase_requisition/views/employee_purchase_requisition_views.xml`

Add the total_amount column to the tree view (after line 177, after the requisition_date field):

```xml
<field name="requisition_date"/>
<field name="total_amount" widget="monetary" options="{'currency_field': 'company_currency_id'}"/>
<field name="state" widget="badge"
       decoration-success="state in ('approved','received')"
       decoration-warning="state in ('waiting_head_approval','waiting_purchase_approval')"
       decoration-info="state == 'purchase_order_created'"
       decoration-danger="state == 'cancelled'"/>
```

### 2.4 Update employee_purchase_requisition_views.xml - Kanban View
File: `employee_purchase_requisition/views/employee_purchase_requisition_views.xml`

Add the total amount to the kanban card (after line 210, after the requisition_date field):

```xml
<div>
    <field name="requisition_date"/>
</div>
<div>
    <strong>Total: <field name="total_amount" widget="monetary"/></strong>
</div>
<div>
    <field name="state" widget="badge"
           decoration-success="state in ('approved','received')"
           decoration-warning="state in ('waiting_head_approval','waiting_purchase_approval')"
           decoration-info="state == 'purchase_order_created'"
           decoration-danger="state == 'cancelled'"/>
</div>
```

## 3. Additional Model Field for Currency

### 3.1 Add Currency Field to Main Model
File: `employee_purchase_requisition/models/employee_purchase_requisition.py`

Add the following field to properly handle currency display (around line 98, after the company_id field):

```python
company_currency_id = fields.Many2one(
    related='company_id.currency_id',
    string='Currency',
    readonly=True,
    store=True
)
```

## 4. Implementation Steps

1. **Backup your files** before making any changes
2. **Update the models** first (requisition_order.py and employee_purchase_requisition.py)
3. **Update the views** (requisition_order_views.xml and employee_purchase_requisition_views.xml)
4. **Restart Odoo** and upgrade the module
5. **Test the functionality** by creating a new purchase requisition with multiple line items

## 5. Expected Behavior

After implementation:
- Each line item will show a calculated subtotal (quantity × unit price)
- The main form will display a total amount stat button
- The tree view will show the total amount for each requisition
- The kanban view will display the total amount in each card
- All monetary values will be properly formatted with currency

## 6. Troubleshooting

If totals don't update:
- Check that the compute methods have proper @api.depends decorators
- Ensure the store=True parameter is set for computed fields
- Verify that field names match exactly between models and views
- Restart Odoo server after making changes

If currency doesn't display:
- Ensure the company_currency_id field is properly added
- Check that the widget="monetary" is used with proper options