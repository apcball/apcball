# Implementation Plan: Stock Request Confirmation Dialog with Location Details

## Overview
Add a confirmation dialog before creating internal transfers that displays Source Location and Destination Location details.

## Files to Create/Modify

### 1. New Wizard Model
**File**: `buz_mrp_stock_request/wizards/mrp_stock_request_confirm_wizard.py`

```python
from odoo import api, fields, models, _

class MrpStockRequestConfirmWizard(models.TransientModel):
    _name = "mrp.stock.request.confirm.wizard"
    _description = "Stock Request Confirmation Wizard"
    
    request_id = fields.Many2one(
        "mrp.stock.request",
        string="Stock Request",
        required=True,
        readonly=True,
    )
    location_id = fields.Many2one(
        related="request_id.location_id",
        string="Source Location",
        readonly=True,
    )
    location_dest_id = fields.Many2one(
        related="request_id.location_dest_id", 
        string="Destination Location",
        readonly=True,
    )
    line_ids = fields.One2many(
        related="request_id.line_ids",
        string="Request Lines",
        readonly=True,
    )
    notes = fields.Text(
        string="Confirmation Notes",
        readonly=True,
        compute="_compute_notes",
    )
    
    @api.depends("request_id", "location_id", "location_dest_id")
    def _compute_notes(self):
        for wizard in self:
            wizard.notes = _(
                "You are about to create an internal transfer from %s to %s.\n\n"
                "This will create stock moves for %d product line(s).\n\n"
                "Please confirm to proceed or cancel to abort."
            ) % (
                wizard.location_id.name if wizard.location_id else _("Not Set"),
                wizard.location_dest_id.name if wizard.location_dest_id else _("Not Set"),
                len(wizard.line_ids),
            )
    
    def action_confirm(self):
        """Confirm the stock request and create internal transfer."""
        self.ensure_one()
        # Call the original confirm method
        return self.request_id.action_confirm()
```

### 2. Wizard View
**File**: `buz_mrp_stock_request/views/mrp_stock_request_confirm_wizard_views.xml`

```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <!-- Confirmation Wizard Form View -->
    <record id="view_mrp_stock_request_confirm_wizard_form" model="ir.ui.view">
        <field name="name">mrp.stock.request.confirm.wizard.form</field>
        <field name="model">mrp.stock.request.confirm.wizard</field>
        <field name="arch" type="xml">
            <form string="Confirm Stock Request">
                <group>
                    <field name="request_id" readonly="1"/>
                </group>
                
                <div class="alert alert-warning" role="alert">
                    <strong>⚠️ Confirmation Required</strong><br/>
                    Please review the transfer details below before confirming.
                </div>
                
                <group string="Transfer Details">
                    <group>
                        <field name="location_id" readonly="1"/>
                    </group>
                    <group>
                        <field name="location_dest_id" readonly="1"/>
                    </group>
                </group>
                
                <notebook>
                    <page string="Materials to Transfer" name="materials">
                        <field name="line_ids">
                            <tree>
                                <field name="product_id"/>
                                <field name="uom_id"/>
                                <field name="qty_requested"/>
                            </tree>
                        </field>
                    </page>
                    <page string="Summary" name="summary">
                        <group>
                            <field name="notes" readonly="1" nolabel="1"/>
                        </group>
                    </page>
                </notebook>
                
                <footer>
                    <button string="Confirm Transfer" name="action_confirm" type="object" class="btn-primary"/>
                    <button string="Cancel" class="btn-secondary" special="cancel"/>
                </footer>
            </form>
        </field>
    </record>
    
    <!-- Confirmation Wizard Action -->
    <record id="action_mrp_stock_request_confirm_wizard" model="ir.actions.act_window">
        <field name="name">Confirm Stock Request</field>
        <field name="res_model">mrp.stock.request.confirm.wizard</field>
        <field name="view_mode">form</field>
        <field name="target">new</field>
    </record>
</odoo>
```

### 3. Modify the Main Model
**File**: `buz_mrp_stock_request/models/mrp_stock_request.py`

Modify the `action_confirm` method (around line 472):

```python
def action_confirm(self):
    """Open confirmation wizard before creating internal transfer(s)."""
    self.ensure_one()
    
    if self.state != "draft":
        raise UserError(_("Only draft requests can be confirmed."))

    # Validate
    if not self.line_ids:
        raise UserError(_("Cannot confirm request without lines."))
    
    if not self.mo_ids:
        raise UserError(_("Please select at least one Manufacturing Order."))

    if not self.location_id or not self.location_dest_id:
        raise UserError(_("Source and destination locations are required."))

    # Open confirmation wizard instead of directly confirming
    return {
        "name": _("Confirm Stock Request"),
        "type": "ir.actions.act_window",
        "view_mode": "form",
        "res_model": "mrp.stock.request.confirm.wizard",
        "target": "new",
        "context": {
            "default_request_id": self.id,
        },
    }
```

### 4. Update Wizard __init__.py
**File**: `buz_mrp_stock_request/wizards/__init__.py`

Add the new wizard import:

```python
from . import mrp_stock_request_allocate_wizard
from . import mrp_stock_request_allocate_multi_wizard
from . import mrp_production_allocate_wizard
from . import mrp_stock_request_confirm_wizard  # Add this line
```

### 5. Update __manifest__.py
**File**: `buz_mrp_stock_request/__manifest__.py`

Add the new view file to the data list:

```python
"data": [
    "security/mrp_stock_request_security.xml",
    "security/ir.model.access.csv",
    "data/sequence_data.xml",
    "views/mrp_stock_request_views.xml",
    "views/mrp_stock_request_wizard_views.xml",
    "views/mrp_stock_request_allocate_multi_wizard_views.xml",
    "views/mrp_production_allocate_wizard_views.xml",
    "views/mrp_production_views.xml",
    "views/stock_picking_views.xml",
    "views/res_config_settings_views.xml",
    "views/mrp_stock_request_confirm_wizard_views.xml",  # Add this line
],
```

## Implementation Steps

1. Create the wizard model file
2. Create the wizard view file  
3. Update the wizards __init__.py file
4. Modify the action_confirm method in the main model
5. Update the __manifest__.py file
6. Test the implementation

## Expected Behavior

1. User clicks "Confirm" button on a draft stock request
2. Instead of directly creating the transfer, a confirmation dialog opens
3. The dialog shows:
   - Source Location details
   - Destination Location details  
   - List of materials to be transferred
   - Summary information
4. User can either:
   - Click "Confirm Transfer" to proceed with creating the internal transfer
   - Click "Cancel" to abort the operation
5. After confirmation, the original confirmation logic executes

## Benefits

- Users can review transfer details before committing
- Reduces errors from incorrect location selections
- Provides clear visibility of what will be transferred
- Follows Odoo best practices for confirmation dialogs