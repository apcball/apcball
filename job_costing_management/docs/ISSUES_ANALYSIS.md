# Job Costing Management Module - Issues Analysis

**Analysis Date:** 2026-02-04  
**Module:** job_costing_management  
**Files Analyzed:**
- `models/material_requisition.py` (workflow states)
- `models/boq.py` (quantity management)
- `wizard/boq_material_requisition_wizard.py` (wizard with search/filter)
- `wizard/boq_material_requisition_wizard_view.xml`
- `views/material_requisition_views.xml`

---

## 1. Material Requisition Workflow Issue: Cannot Cancel/Rollback from "Ordered" State

### 1.1 Current State Workflow Analysis

The Material Requisition (MR) model defines the following states in `material_requisition.py`:

```python
state = fields.Selection([
    ('draft', 'Draft'),
    ('submitted', 'Submitted'),
    ('dept_approved', 'Department Approved'),
    ('approved', 'Approved'),
    ('ordered', 'Ordered'),
    ('received', 'Received'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled')
], string='Status', default='draft', tracking=True)
```

### 1.2 Current Cancel Button Logic (in XML View)

```xml
<button name="action_cancel" string="Cancel" type="object" 
        invisible="state not in ('draft', 'submitted', 'dept_approved', 'approved')"/>
```

**PROBLEM:** The "ordered" state is **NOT** included in the cancel button visibility conditions. Users cannot cancel an MR once it reaches the "ordered" state.

### 1.3 Current Reset-to-Draft Logic

```xml
<button name="action_reset_to_draft" string="Reset to Draft" type="object" 
        invisible="state not in ('rejected', 'cancelled')"/>
```

**PROBLEM:** The "ordered" state is **NOT** included in the reset-to-draft button visibility. Once ordered, there's no way to rollback.

### 1.4 The Business Impact

When an MR reaches "ordered" status:
1. A Purchase Order (PO) has been created via `action_create_purchase_order()`
2. The BOQ quantities have been "consumed" (tracked in `total_requisitioned_qty`)
3. If the PO has delivery issues, users **CANNOT**:
   - Cancel the MR to return quantities to BOQ
   - Create a new MR with corrected quantities
   - Rollback to a previous state to modify the requisition

### 1.5 Why Rollback is Blocked

1. **UI Constraint:** The cancel/reset buttons are hidden for "ordered" state
2. **No Business Logic for Reversal:** The `action_cancel()` method only changes state, it does NOT:
   - Check if related POs can be cancelled
   - Return quantities back to BOQ (reverse the consumption)
   - Handle partial deliveries

3. **BOQ Quantity Consumption Logic:** In `boq.py`, the `_compute_purchase_tracking()` method calculates:
   ```python
   active_req_lines = req_lines.filtered(lambda l: l.requisition_state not in ['cancelled', 'rejected'])
   record.total_requisitioned_qty = sum(active_req_lines.mapped('quantity'))
   ```
   This means cancelled lines are excluded from the total - but the MR itself cannot be cancelled from "ordered" state.

### 1.6 Recommended Fix

**Option A: Allow Cancel from Ordered State (with validation)**
```python
def action_cancel(self):
    for record in self:
        if record.state == 'ordered':
            # Check if any POs are in a cancellable state
            purchase_orders = self.env['purchase.order'].search([('origin', '=', record.name)])
            non_cancellable_pos = purchase_orders.filtered(lambda po: po.state not in ['draft', 'cancel'])
            if non_cancellable_pos:
                raise ValidationError(_(
                    'Cannot cancel this requisition because the following purchase orders are already confirmed:\n%s'
                ) % '\n'.join(non_cancellable_pos.mapped('name')))
            # Cancel related draft POs
            purchase_orders.filtered(lambda po: po.state == 'draft').action_cancel()
        
        record.write({'state': 'cancelled'})
        # Note: BOQ quantities are automatically returned because 
        # _compute_purchase_tracking excludes cancelled/rejected states
```

**Option B: Add "Request Cancel" Workflow**
- Add a new state "cancel_requested"
- Require approval for cancellation of ordered MRs
- Track cancellation reason

---

## 2. BOQ Quantity Management Analysis

### 2.1 How BOQ Quantities are Tracked

The `boq.line` model tracks quantities through these computed fields in `boq.py`:

```python
# Purchase tracking fields
total_requisitioned_qty = fields.Float(string='Total Requisitioned Qty', compute='_compute_purchase_tracking', store=True)
total_ordered_qty = fields.Float(string='Total Ordered Qty', compute='_compute_purchase_tracking', store=True)
total_received_qty = fields.Float(string='Total Received Qty', compute='_compute_purchase_tracking', store=True)
remaining_qty = fields.Float(string='Remaining Qty', compute='_compute_purchase_tracking', store=True)
```

### 2.2 Quantity Computation Logic

```python
@api.depends('requisition_line_ids', 'requisition_line_ids.quantity', 'requisition_line_ids.requisition_state')
def _compute_purchase_tracking(self):
    for record in self:
        req_lines = record.requisition_line_ids
        
        # Calculate total requisitioned quantity (all states EXCEPT cancelled/rejected)
        active_req_lines = req_lines.filtered(lambda l: l.requisition_state not in ['cancelled', 'rejected'])
        record.total_requisitioned_qty = sum(active_req_lines.mapped('quantity'))
        
        # Calculate total ordered quantity (approved and above states)
        ordered_req_lines = req_lines.filtered(lambda l: l.requisition_state in ['approved', 'ordered', 'received'])
        record.total_ordered_qty = sum(ordered_req_lines.mapped('quantity'))
        
        # Calculate total received quantity
        received_req_lines = req_lines.filtered(lambda l: l.requisition_state == 'received')
        record.total_received_qty = sum(received_req_lines.mapped('quantity'))
        
        # Calculate remaining quantity
        record.remaining_qty = record.adjusted_quantity - record.total_requisitioned_qty
```

### 2.3 Key Observations

**Good Design:**
- The system correctly excludes `cancelled` and `rejected` MR lines from quantity calculations
- This means if an MR line is cancelled, its quantity is automatically returned to BOQ
- The `remaining_qty` field will increase accordingly

**Potential Issue:**
- The computation depends on `requisition_state` being correctly set
- If an MR is cancelled but the related MR lines don't update their state, quantities won't be returned

### 2.4 MR Line State Synchronization

In `material_requisition.py`, when an MR changes state, the lines don't automatically update a local state field. The `requisition_state` field on `material.requisition.line` is:

```python
requisition_state = fields.Selection(related='requisition_id.state', string='Requisition State', readonly=True)
```

This is a **related field**, meaning it automatically reflects the parent MR's state. This is good - no synchronization issues.

### 2.5 Quantity Return on Cancel - How it Works

When an MR is cancelled:
1. `action_cancel()` sets MR state to `'cancelled'`
2. The related `requisition_state` on MR lines automatically updates (related field)
3. `_compute_purchase_tracking()` on BOQ line is triggered (depends on `requisition_line_ids.requisition_state`)
4. The cancelled lines are filtered out of `total_requisitioned_qty`
5. `remaining_qty` is recalculated as `adjusted_quantity - total_requisitioned_qty`
6. Quantity is effectively "returned" to BOQ

**This mechanism works correctly - the issue is that users cannot cancel from "ordered" state.**

---

## 3. Material Requisition Wizard - Search & Filter Not Working

### 3.1 Current Filter Implementation

In `wizard/boq_material_requisition_wizard.py`:

```python
# Search and Filter Fields
search_term = fields.Char(string='Search Products', placeholder='Search by name or code...')
category_filter = fields.Many2one('boq.category', string='Filter by BOQ Category')
product_category_filter = fields.Many2one('product.category', string='Filter by Product Category')
cost_type_filter = fields.Selection([...], default='material')

# Filtered lines (computed for display)
filtered_line_ids = fields.One2many('boq.material.requisition.wizard.line', 'wizard_id', 
                                    string='Filtered BOQ Lines',
                                    compute='_compute_filtered_lines',
                                    readonly=True)
```

### 3.2 The _compute_filtered_lines Method

```python
@api.depends('line_ids', 'search_term', 'category_filter', 'product_category_filter', 
             'cost_type_filter', 'group_by')
def _compute_filtered_lines(self):
    for record in self:
        lines = record.line_ids
        
        # Apply search term filter
        if record.search_term:
            search_lower = record.search_term.lower()
            lines = lines.filtered(lambda l: 
                search_lower in (l.product_id.name or '').lower() or
                search_lower in (l.product_id.default_code or '').lower() or
                search_lower in (l.description or '').lower()
            )
        
        # Apply BOQ category filter
        if record.category_filter:
            lines = lines.filtered(lambda l: l.boq_line_id.category_id == record.category_filter)
        
        # Apply product category filter
        if record.product_category_filter:
            lines = lines.filtered(lambda l: l.product_id.categ_id == record.product_category_filter)
        
        # Store result
        record.filtered_line_ids = lines
```

### 3.3 Root Cause of Search/Filter Not Working

**CRITICAL ISSUE #1: The View Uses `line_ids` Instead of `filtered_line_ids`**

Looking at the wizard view XML:

```xml
<!-- Lines - All BOQ lines available for selection -->
<field name="line_ids" mode="tree">
```

The view is displaying `line_ids` (all lines), NOT `filtered_line_ids` (filtered lines).

**CRITICAL ISSUE #2: Cannot Filter One2many Fields in Odoo**

```python
# This is a fundamental limitation:
filtered_line_ids = fields.One2many('boq.material.requisition.wizard.line', 'wizard_id', 
                                    compute='_compute_filtered_lines',
                                    readonly=True)
```

Setting a computed value on a One2many field doesn't work as expected in Odoo. The `filtered_line_ids` field is computed but cannot actually be used to filter the display in a form view.

**CRITICAL ISSUE #3: No JavaScript/Client-Side Filtering**

The search/filter fields have no triggers that update the view. When a user types in `search_term`, nothing happens because:
1. The computed field updates on the backend
2. But the view doesn't refresh to show filtered results
3. And the field `filtered_line_ids` isn't even used in the view

### 3.4 Why It Doesn't Work

1. **Architecture Mismatch:** The wizard attempts to use server-side Python filtering for a client-side UI need
2. **View Misconfiguration:** The XML uses `line_ids` instead of `filtered_line_ids`
3. **Missing onchange Handler:** No `@api.onchange` decorator on `_compute_filtered_lines` to trigger view refresh
4. **Transient Model Limitations:** Even if the field computed correctly, assigning to a One2many in a transient model doesn't filter the child records visible in the UI

### 3.5 Recommended Fix

**Option A: Use Domain on the Field Tag (Simplest)**
```xml
<field name="line_ids" mode="tree" 
       domain="[('display_in_wizard', '=', True)]">
```

And add a computed boolean field on the wizard line:
```python
class BOQMaterialRequisitionWizardLine(models.TransientModel):
    display_in_wizard = fields.Boolean(compute='_compute_display_in_wizard')
    
    @api.depends('wizard_id.search_term', 'wizard_id.category_filter')
    def _compute_display_in_wizard(self):
        for record in self:
            wizard = record.wizard_id
            show = True
            
            if wizard.search_term:
                search_lower = wizard.search_term.lower()
                match = (search_lower in (record.product_id.name or '').lower() or
                        search_lower in (record.product_id.default_code or '').lower() or
                        search_lower in (record.description or '').lower())
                show = show and match
            
            if wizard.category_filter:
                show = show and record.category_id == wizard.category_filter
            
            record.display_in_wizard = show
```

**Option B: Use a Web Client Action with JavaScript Filtering (Best UX)**
Implement a proper client-side filtered list view.

**Option C: Remove Search/Filter (Quick Fix)**
Remove the non-functional search/filter UI elements until properly implemented.

---

## 4. Code Quality Issues

### 4.1 material_requisition.py

#### Issue 4.1.1: Inconsistent Logging Pattern
```python
def _compute_picking_count(self):
    # ...
    # Debug: Log the picking count
    import logging
    _logger = logging.getLogger(__name__)
    _logger.info(f"Material Requisition {record.name}: Computed {len(picking_ids)} pickings")
```

**Problem:** Logger is imported inside the method, repeatedly. Should be at module level.

**Fix:**
```python
import logging
_logger = logging.getLogger(__name__)

class MaterialRequisition(models.Model):
    # ...
    def _compute_picking_count(self):
        # ... use _logger directly
```

#### Issue 4.1.2: Duplicate Method Logic
The `_compute_picking_count` and `action_view_pickings` share identical search logic:

```python
# In _compute_picking_count:
picking_ids = record.line_ids.mapped('picking_ids.id')
pickings_by_origin = self.env['stock.picking'].search([('origin', '=', record.name)])
picking_ids.extend(pickings_by_origin.ids)
picking_ids = list(set(picking_ids))

# In action_view_pickings:
picking_ids = self.line_ids.mapped('picking_ids.id')
pickings_by_origin = self.env['stock.picking'].search([('origin', '=', self.name)])
picking_ids.extend(pickings_by_origin.ids)
picking_ids = list(set(picking_ids))
```

**Fix:** Extract to a helper method:
```python
def _get_related_picking_ids(self):
    self.ensure_one()
    picking_ids = self.line_ids.mapped('picking_ids.id')
    pickings_by_origin = self.env['stock.picking'].search([('origin', '=', self.name)])
    picking_ids.extend(pickings_by_origin.ids)
    return list(set(picking_ids))
```

#### Issue 4.1.3: Missing Error Handling in action_create_picking
The method attempts to get locations without proper fallback:
```python
try:
    source_location = self.env.ref('stock.stock_location_stock').id
except ValueError:
    locations = self.env['stock.location'].search([('usage', '=', 'internal')], limit=1)
    if locations:
        source_location = locations[0].id
    else:
        raise ValidationError(_('No source location found.'))
```
This pattern is repeated twice for source and dest locations.

#### Issue 4.1.4: Inconsistent Return Types
`action_create_picking` returns a dict action for internal transfers, but raises ValidationError if no internal lines found. This is inconsistent with `action_create_purchase_order` which handles empty lines before calling the method.

#### Issue 4.1.5: No Validation on Cancel/Reset Actions
```python
def action_cancel(self):
    self.write({'state': 'cancelled'})

def action_reset_to_draft(self):
    self.write({'state': 'draft'})
```
These methods have no validation. They should check for related documents (POs, pickings) before allowing state change.

### 4.2 boq.py

#### Issue 4.2.1: Duplicate `company_id` Definition
```python
class BOQ(models.Model):
    company_id = fields.Many2one('res.company', string='Company', required=True, 
                                 default=lambda self: self.env.company, index=True)
    # ... later in the file ...
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company)
```

**This is a critical bug - the field is defined twice with different parameters.**

#### Issue 4.2.2: Excessive Debug Logging in Production Code
Multiple methods have debug logging that should be removed or converted to proper log levels:
```python
_logger.info(f"Creating BOQ lines from template: {template.name}")
_logger.info(f"Template has {len(template.line_ids)} lines")
```

#### Issue 4.2.3: Complex Copy Method with Potential Issues
The `copy()` method manually unlinks and recreates lines, which is inefficient and error-prone. Better to use Odoo's native copy with proper default overrides.

#### Issue 4.2.4: Missing Constraints
No SQL constraints on critical fields like `quantity`, `unit_cost` that should be non-negative.

#### Issue 4.2.5: Inconsistent Error Messages
Some errors include debug information, others don't. Not user-friendly.

### 4.3 boq_material_requisition_wizard.py

#### Issue 4.3.1: Method Returns `act_window_close` Incorrectly
```python
def action_select_all(self):
    self.ensure_one()
    for line in self.line_ids:
        line.selected = True
    return {'type': 'ir.actions.act_window_close'}  # WRONG - closes wizard!
```

This closes the wizard! It should return an action to refresh the view:
```python
return {
    'type': 'ir.actions.act_window',
    'res_model': self._name,
    'res_id': self.id,
    'view_mode': 'form',
    'target': 'new',
}
```

#### Issue 4.3.2: No Validation in action_clear_filters
The method clears filters but doesn't handle the case where `line_ids` might need to be refreshed.

#### Issue 4.3.3: Inconsistent Required Fields
```python
class BOQMaterialRequisitionWizardLine(models.TransientModel):
    wizard_id = fields.Many2one('boq.material.requisition.wizard', string='Wizard', required=False, ondelete='cascade')
    # But the parent requires lines...
```

The `required=False` on wizard_id is inconsistent - lines should always have a wizard.

#### Issue 4.3.4: Unused Compute Field
```python
filtered_line_ids = fields.One2many(..., compute='_compute_filtered_lines', readonly=True)
```
This field is computed but never used in the view (which uses `line_ids` directly).

### 4.4 boq_material_requisition_wizard_view.xml

#### Issue 4.4.1: Duplicate View Definitions
There are THREE different form views defined:
1. `view_boq_material_requisition_wizard_form_selection`
2. `view_boq_material_requisition_wizard_form_preview`  
3. `view_boq_material_requisition_wizard_form` (main one with conditional divs)

The main view duplicates the content of the other two. This is confusing and hard to maintain.

#### Issue 4.4.2: Using `invisible="1"` on Warning Section
```xml
<div class="alert alert-warning mt-4" role="alert" invisible="1">
```
The warning section is always invisible - it should use a computed field to show/hide based on actual warnings.

#### Issue 4.4.3: Missing Groups on Sensitive Buttons
Buttons like "Select All" and "Clear Filters" don't have groups, allowing any user to use them.

---

## 5. Summary of Critical Issues

| Issue | Severity | File | Description |
|-------|----------|------|-------------|
| MR cannot cancel from "ordered" | **HIGH** | views/material_requisition_views.xml | Users cannot cancel MR to return quantities to BOQ |
| Duplicate company_id field | **HIGH** | models/boq.py | Field defined twice with different parameters |
| Wizard search/filter not working | **HIGH** | wizard/boq_material_requisition_wizard.py | Filters compute but don't affect display |
| action_select_all closes wizard | **MEDIUM** | wizard/boq_material_requisition_wizard.py | Method returns wrong action type |
| Excessive debug logging | **LOW** | models/boq.py | Production code has debug logs |
| Inconsistent error handling | **MEDIUM** | models/material_requisition.py | Cancel/reset have no validation |
| Duplicate view definitions | **LOW** | wizard/boq_material_requisition_wizard_view.xml | Hard to maintain |

---

## 6. Recommended Action Plan

### Phase 1: Critical Fixes (Immediate)
1. Fix MR workflow - allow cancel from "ordered" with proper validation
2. Remove duplicate `company_id` definition in boq.py
3. Fix wizard search/filter - implement working domain-based filtering

### Phase 2: Quality Improvements (Short-term)
1. Fix action_select_all to not close wizard
2. Move logger imports to module level
3. Add validation to cancel/reset methods
4. Remove or reduce debug logging

### Phase 3: Refactoring (Long-term)
1. Consolidate wizard view definitions
2. Extract duplicate logic to helper methods
3. Add proper constraints to BOQ lines
4. Improve error messages for users
