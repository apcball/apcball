# BOQ Material Requisition Wizard - Validation Error Fix

## Problem Description

Users encountered a validation error when trying to use the BOQ Material Requisition Wizard:

```
Validation Error
The operation cannot be completed:
- Create/update: a mandatory field is not set.
- Delete: another model requires the record being deleted. If possible, archive it instead.

Model: BOQ Material Requisition Wizard Line (boq.material.requisition.wizard.line)
Field: Product (product_id)
```

## Root Cause

The validation error occurred because:

1. **Mandatory Field Constraint**: The `product_id` field in the wizard line model was set as `required=True`
2. **Missing Data Validation**: BOQ lines without products were being included in wizard creation
3. **Insufficient Pre-validation**: No checks were performed to ensure BOQ readiness before wizard creation
4. **Edge Case Handling**: The system didn't handle scenarios where BOQ lines lacked essential data

## Solution Implemented

### 1. Relaxed Field Requirements

**Before:**
```python
product_id = fields.Many2one('product.product', string='Product', required=True)
uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
```

**After:**
```python
product_id = fields.Many2one('product.product', string='Product', required=False)
uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=False)
```

### 2. Enhanced Validation in `default_get()`

Added comprehensive validation before wizard creation:

```python
@api.model
def default_get(self, fields_list):
    # Check if BOQ has any lines
    if not boq.line_ids:
        raise ValidationError(_('The selected BOQ has no lines...'))
    
    # Check if BOQ lines have products
    lines_with_products = boq.line_ids.filtered(lambda l: l.product_id)
    if not lines_with_products:
        raise ValidationError(_('The selected BOQ has no lines with products...'))
    
    # Check if lines have remaining quantities
    lines_with_remaining = lines_with_products.filtered(lambda l: l.remaining_qty > 0)
    if not lines_with_remaining:
        raise ValidationError(_('All BOQ lines with products have been fully requisitioned...'))
```

### 3. Added Runtime Validation

Implemented `@api.constrains` and `@api.onchange` methods:

```python
@api.constrains('product_id', 'selected')
def _check_selected_line_data(self):
    """Ensure selected lines have required data"""
    for record in self:
        if record.selected:
            if not record.product_id:
                raise ValidationError(_('Selected line must have a product assigned.'))
            if not record.uom_id:
                raise ValidationError(_('Selected line must have a unit of measure.'))

@api.onchange('boq_line_id')
def _onchange_boq_line_id(self):
    """Update fields when BOQ line changes"""
    if self.boq_line_id:
        self.product_id = self.boq_line_id.product_id
        self.uom_id = self.boq_line_id.uom_id or self.boq_line_id.product_id.uom_id
        # ... other field updates
```

### 4. Enhanced User Interface

**Before:**
```xml
<field name="product_id" readonly="1"/>
<field name="uom_id" readonly="1"/>
```

**After:**
```xml
<field name="product_id" options="{'no_create': True}" required="1"/>
<field name="uom_id" options="{'no_create': True}" required="1"/>
```

### 5. Improved Error Handling

Added detailed validation in `action_create_requisition()`:

```python
# Validate selected lines have required data
lines_missing_product = selected_lines.filtered(lambda l: not l.product_id)
if lines_missing_product:
    raise ValidationError(_('The following lines are missing products...'))

lines_missing_uom = selected_lines.filtered(lambda l: not l.uom_id)
if lines_missing_uom:
    raise ValidationError(_('The following lines are missing unit of measure...'))
```

### 6. Added BOQ Readiness Check

New method to validate BOQ before requisition creation:

```python
def check_requisition_readiness(self):
    """Check if BOQ is ready for material requisition creation"""
    issues = []
    
    if self.state not in ('approved', 'locked'):
        issues.append(f'BOQ state must be approved or locked')
    
    if not self.line_ids:
        issues.append('BOQ has no lines')
    
    # ... additional checks
    
    return {
        'ready': len(issues) == 0,
        'issues': issues,
        'lines_total': len(self.line_ids),
        'lines_with_products': len(lines_with_products),
        'lines_with_remaining': len(lines_with_remaining),
    }
```

## How to Apply the Fix

### Step 1: Update the Module
```bash
# In Odoo interface: Apps > Job Costing Management > Update
# Or via command line:
./odoo-bin -u job_costing_management -d your_database
```

### Step 2: Prepare Your BOQ
1. Ensure BOQ is in **'approved'** or **'locked'** state
2. Assign **products** to all BOQ lines that need requisitions
3. Verify BOQ lines have **unit of measure** assigned
4. Check that at least one line has **remaining quantity > 0**

### Step 3: Test the Wizard
1. Open the prepared BOQ
2. Click **"Create Material Requisition"** button
3. Wizard should open without validation errors
4. Review and adjust data as needed
5. Click **"Create Requisition"**

## Validation Scenarios

### Scenario 1: BOQ with No Lines
**Error Message:** "The selected BOQ has no lines. Please add BOQ lines before creating a material requisition."

**Solution:** Add BOQ lines with products and quantities.

### Scenario 2: BOQ Lines Without Products
**Error Message:** "The selected BOQ has no lines with products assigned. Please assign products to BOQ lines before creating a material requisition."

**Solution:** Assign products to BOQ lines in the BOQ form.

### Scenario 3: All Lines Fully Requisitioned
**Error Message:** "All BOQ lines with products have been fully requisitioned. No remaining quantities available for requisition."

**Solution:** This is expected behavior when all materials have been requisitioned.

### Scenario 4: Missing Product in Wizard
**Error Message:** "Selected line must have a product assigned."

**Solution:** Select a product in the wizard line or uncheck the line.

### Scenario 5: Missing Unit of Measure
**Error Message:** "Selected line must have a unit of measure."

**Solution:** Select a unit of measure in the wizard line.

## Benefits of the Fix

### For Users
- **Clear Error Messages**: Understand exactly what needs to be fixed
- **Flexible Interface**: Can edit products and UOMs in the wizard if needed
- **Guided Workflow**: Step-by-step validation prevents common mistakes
- **No More Cryptic Errors**: Meaningful messages instead of database constraints

### For Administrators
- **Robust Validation**: Prevents data inconsistencies
- **Better Diagnostics**: Clear information about what's wrong
- **Flexible Configuration**: Can handle various BOQ setups
- **Reduced Support**: Users can self-diagnose and fix issues

### For Developers
- **Maintainable Code**: Clear separation of validation logic
- **Extensible Design**: Easy to add new validation rules
- **Error Handling**: Comprehensive exception handling
- **Documentation**: Well-documented validation scenarios

## Testing Checklist

- [ ] BOQ with no lines shows appropriate error
- [ ] BOQ with lines but no products shows appropriate error
- [ ] BOQ with fully requisitioned lines shows appropriate error
- [ ] Wizard opens successfully for valid BOQ
- [ ] Can edit products and UOMs in wizard
- [ ] Validation prevents creation with missing data
- [ ] Successful requisition creation updates BOQ tracking
- [ ] Error messages are clear and actionable

## Files Modified

1. **`wizard/boq_material_requisition_wizard.py`**
   - Relaxed field requirements
   - Enhanced validation logic
   - Added constrains and onchange methods

2. **`wizard/boq_material_requisition_wizard_view.xml`**
   - Made fields editable
   - Added required attributes
   - Added no_create options

3. **`models/boq.py`**
   - Added BOQ readiness check method
   - Enhanced debug capabilities

4. **`test_validation_fix.py`**
   - Comprehensive test documentation
   - Troubleshooting guide

## Support

If you continue to experience validation errors:

1. **Check Odoo Logs**: Look for detailed error messages
2. **Verify Module Update**: Ensure the module was properly updated
3. **Test with Simple BOQ**: Create a test BOQ with one line and one product
4. **Check User Permissions**: Ensure user has required access rights
5. **Contact Support**: Provide specific error messages and BOQ configuration

The validation error fix ensures a smooth user experience while maintaining data integrity and providing clear guidance for resolving any issues.