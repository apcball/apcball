# Odoo 17 Compatibility Fix

## Issue Identified
When installing the module in Odoo 17, the following error occurred:
```
odoo.tools.convert.ParseError: while parsing /opt/instance1/odoo17/custom-addons/buz_warranty_management/views/sale_order_views.xml:5
Since 17.0, "attrs" and "states" attributes are no longer used.
```

## Root Cause
Odoo 17 deprecated the `attrs` attribute in XML views. The `attrs` attribute was used in the sale_order_views.xml file to control button visibility.

## Solution Applied
Replaced `attrs` attributes with direct `invisible` attributes in `views/sale_order_views.xml`:

### Before (Odoo 16 compatible):
```xml
<button name="action_create_warranty_card" 
        string="Create Warranty Card" 
        type="object" 
        class="btn-primary"
        attrs="{'invisible': [('state', 'not in', ['sale', 'done'])]}"/>
```

### After (Odoo 17 compatible):
```xml
<button name="action_create_warranty_card" 
        string="Create Warranty Card" 
        type="object" 
        class="btn-primary"
        invisible="state not in ['sale', 'done']"/>
```

## Files Modified
- `views/sale_order_views.xml` - Updated button visibility attributes

## Validation
- All validation tests pass
- Module is now compatible with Odoo 17
- No functionality changes

## Additional Notes
This is a common migration issue when upgrading from Odoo 16 to 17. The `attrs` attribute has been replaced with direct attributes like `invisible`, `readonly`, and `required` that can use domain expressions directly.