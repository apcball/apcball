# Odoo 17 View Structure Fix

## Additional Issue Fixed

### Field Name Changes in Tree Views
**Problem**: The field `unit_amount` no longer exists in the expense tree view in Odoo 17
**Solution**: Updated to use `price_unit` which is the equivalent field

```xml
<!-- Before (Odoo 16) -->
<xpath expr="//field[@name='expense_line_ids']/tree/field[@name='unit_amount']" position="attributes">
    <attribute name="force_save">True</attribute>
</xpath>

<!-- After (Odoo 17) -->
<xpath expr="//field[@name='expense_line_ids']/tree/field[@name='price_unit']" position="attributes">
    <attribute name="force_save">True</attribute>
</xpath>
```

## Odoo 17 Expense Tree View Structure

The tree view structure for expense lines has changed in Odoo 17. Key fields available:

### Main Fields:
- `date` - Expense date
- `product_id` - Product/service
- `name` - Description  
- `price_unit` - Unit price (replaces `unit_amount`)
- `quantity` - Quantity
- `total_amount` - Total amount
- `analytic_distribution` - Analytic distribution
- `account_id` - Account
- `tax_ids` - Taxes

### Removed/Changed Fields:
- `unit_amount` → `price_unit`

This ensures the module properly integrates with Odoo 17's updated expense management interface.
