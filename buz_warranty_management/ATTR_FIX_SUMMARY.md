# Odoo 17 Compatibility Fixes

## Issues Fixed

### 1. Deprecated `attrs` Attribute
**Error**: 
```
Since 17.0, the "attrs" and "states" attributes are no longer used.
```

**Root Cause**: In Odoo 17, `attrs` attribute has been deprecated and replaced with direct attributes.

**Fix Applied** in `warranty_rma_receive_wizard_view.xml`:
- Replaced `attrs="{'invisible': [('claim_id', '=', False)]}"` with `invisible="claim_id == False"`

### 2. Invalid Action Type
**Error**:
```
KeyError: 'ir.actions.do_nothing'
```

**Root Cause**: The `ir.actions.do_nothing` action type doesn't exist in Odoo 17.

**Fix Applied** in `warranty_rma_receive_wizard.py`:
- Replaced `{'type': 'ir.actions.do_nothing'}` with a proper window action that refreshes the wizard

## Changes Made

### XML Changes:
```xml
<!-- Before -->
attrs="{'invisible': [('claim_id', '=', False)]}"

<!-- After -->
invisible="claim_id == False"
```

### Python Changes:
```python
# Before
return {
    'type': 'ir.actions.do_nothing',
}

# After
return {
    'type': 'ir.actions.act_window',
    'res_model': 'warranty.rma.receive.wizard',
    'view_mode': 'form',
    'res_id': self.id,
    'target': 'new',
    'context': self.env.context,
}
```

## Validation
- XML syntax validation: ✅ Passed
- Python syntax validation: ✅ Passed
- Module should now upgrade and run successfully on Odoo 17