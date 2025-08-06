# Odoo 17 View Compatibility Fix Summary

## Issue Fixed
The module was failing to install due to deprecated `attrs` attributes in XML views. In Odoo 17, `attrs` and `states` attributes in views have been replaced with direct attributes.

## Root Cause
Odoo 17 deprecated the `attrs` attribute syntax in favor of direct attribute declarations:

### Before (Odoo 16):
```xml
<field name="my_field" attrs="{'invisible': [('condition', '=', True)]}" />
```

### After (Odoo 17):
```xml
<field name="my_field" invisible="condition == True" />
```

## Changes Made

### 1. account_payment_view.xml
**Fixed**: Payment form field visibility
```xml
<!-- Before -->
<field name="advance_id" attrs="{'invisible': [('payment_type', '!=', 'inbound')]}" />

<!-- After -->
<field name="advance_id" invisible="payment_type != 'inbound'" />
```

### 2. hr_employee_views.xml  
**Fixed**: Employee advance button visibility
```xml
<!-- Before -->
<button attrs="{'invisible': [('advance_count', '=', 0)]}" />

<!-- After -->
<button invisible="advance_count == 0" />
```

### 3. hr_expense_views.xml (Multiple Fixes)

#### a) Clearing product field
```xml
<!-- Before -->
<field name="clearing_product_id" attrs="{'invisible': [('advance', '=', False)]}" />

<!-- After -->
<field name="clearing_product_id" invisible="advance == False" />
```

#### b) Clear Advance buttons
```xml
<!-- Before -->
<button attrs="{'invisible': ['|', '|', ('advance', '=', False), ('state', '!=', 'done'), ('clearing_residual', '=', 0.0)]}" />

<!-- After -->  
<button invisible="advance == False or state != 'done' or clearing_residual == 0.0" />
```

#### c) Advance fields visibility
```xml
<!-- Before -->
<field name="advance" attrs="{'invisible': [('advance', '=', False)]}" />
<label for="advance" attrs="{'invisible': [('advance', '=', False)]}" />

<!-- After -->
<field name="advance" invisible="advance == False" />
<label for="advance" invisible="advance == False" />
```

#### d) Sheet fields with multiple conditions
```xml
<!-- Before -->
<field name="advance_sheet_id" attrs="{'invisible': [('advance', '=', True)], 'readonly': [('id', '!=', False)]}" />

<!-- After -->
<field name="advance_sheet_id" invisible="advance == True" readonly="id != False" />
```

#### e) Column visibility in tree views
```xml
<!-- Before -->
<field name="clearing_product_id" attrs="{'column_invisible': [('parent.advance', '=', False)]}" />

<!-- After -->
<field name="clearing_product_id" column_invisible="parent.advance == False" />
```

## Odoo 17 View Attribute Conversion Rules

### 1. Basic Equality/Inequality
```xml
<!-- Old -->
attrs="{'invisible': [('field', '=', value)]}"
<!-- New -->
invisible="field == value"

<!-- Old -->
attrs="{'invisible': [('field', '!=', value)]}"  
<!-- New -->
invisible="field != value"
```

### 2. Multiple Conditions with OR
```xml
<!-- Old -->
attrs="{'invisible': ['|', ('field1', '=', value1), ('field2', '=', value2)]}"
<!-- New -->
invisible="field1 == value1 or field2 == value2"
```

### 3. Multiple Conditions with AND
```xml
<!-- Old -->
attrs="{'invisible': [('field1', '=', value1), ('field2', '=', value2)]}"
<!-- New -->
invisible="field1 == value1 and field2 == value2"
```

### 4. Complex Nested Conditions
```xml
<!-- Old -->
attrs="{'invisible': ['|', '|', ('advance', '=', False), ('state', '!=', 'done'), ('clearing_residual', '=', 0.0)]}"
<!-- New -->
invisible="advance == False or state != 'done' or clearing_residual == 0.0"
```

### 5. Multiple Attribute Types
```xml
<!-- Old -->
attrs="{'invisible': [('advance', '=', True)], 'readonly': [('id', '!=', False)]}"
<!-- New -->
invisible="advance == True" readonly="id != False"
```

### 6. Column Visibility in Tree Views
```xml
<!-- Old -->
attrs="{'column_invisible': [('parent.advance', '=', False)]}"
<!-- New -->
column_invisible="parent.advance == False"
```

## Files Updated
1. `views/account_payment_view.xml` - 1 attrs conversion
2. `views/hr_employee_views.xml` - 1 attrs conversion  
3. `views/hr_expense_views.xml` - 9 attrs conversions

## Key Notes

### Valid Attributes in Odoo 17
- `invisible` - Hide/show field
- `readonly` - Make field read-only
- `required` - Make field required
- `column_invisible` - Hide column in tree view

### Operator Conversion
- `('field', '=', value)` → `field == value`
- `('field', '!=', value)` → `field != value`  
- `('field', '>', value)` → `field > value`
- `('field', '<', value)` → `field < value`

### Boolean Values
- `False` remains `False`
- `True` remains `True`
- Numeric `0` becomes `0.0` for float fields

## Installation Status
✅ **View compatibility issues resolved** - All deprecated `attrs` attributes converted to Odoo 17 syntax

The module now uses proper Odoo 17 view syntax and should install without view-related errors.
