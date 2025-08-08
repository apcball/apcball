# Critical Fixes for WHT Tax Issues - Apply these if WHT is not working

## Fix 1: Ensure WHT Tax fields are visible in Invoice Lines

Add this to your invoice line views if WHT fields are not showing:

```xml
<!-- Add to invoice line tree view -->
<field name="wht_tax_id" optional="hide"/>

<!-- Add to invoice line form view -->
<group name="withholding_tax" string="Withholding Tax">
    <field name="wht_tax_id"/>
</group>
```

## Fix 2: Currency Conversion Issues

If you get currency conversion errors, check this method in account_move.py:

```python
def _get_wht_base_amount(self, currency, currency_date):
    # Make sure this method handles different currency conversion approaches
    # The module already has fallbacks for this
```

## Fix 3: Payment Register Not Showing WHT Options

If payment register doesn't show WHT fields:

1. Ensure invoices have WHT tax assigned to products/lines
2. Check that Group Payment is enabled 
3. Verify WHT tax has proper account configured

## Fix 4: Missing WHT Account Configuration

Run this SQL to check WHT account setup:

```sql
-- Check if any accounts are marked as WHT accounts
SELECT code, name, wht_account FROM account_account WHERE wht_account = true;

-- If empty, manually mark an account:
UPDATE account_account SET wht_account = true WHERE code = '2131';
```

## Fix 5: Module Installation Issues

If module won't install:

```bash
# Clear cache and restart
sudo systemctl restart odoo
# or
sudo service odoo restart

# Reinstall module
odoo-bin -d your_database -i l10n_th_account_tax --log-level=debug
```

## Fix 6: WHT Tax Not Calculating

Check these in order:

1. **Product Configuration**: Products must have WHT tax assigned
2. **Account Configuration**: WHT account must exist and be marked as "WHT Account"
3. **Tax Configuration**: WHT tax types must be created with proper account
4. **User Permissions**: User must have accounting access rights

## Fix 7: Payment Integration Issues

If payments don't deduct WHT:

1. Ensure "Group Payment" is checked in payment register
2. Verify invoice lines have `wht_tax_id` populated
3. Check that payment wizard can access `_get_wht_amount` method

## Quick Verification Script

Run this in Odoo shell to verify basic setup:

```python
# Check WHT accounts
wht_accounts = env['account.account'].search([('wht_account', '=', True)])
print(f"WHT Accounts: {wht_accounts.mapped('code')}")

# Check WHT tax types  
wht_taxes = env['account.withholding.tax'].search([])
print(f"WHT Tax Types: {wht_taxes.mapped('name')}")

# Check products with WHT
products_wht = env['product.template'].search([('wht_tax_id', '!=', False)])
print(f"Products with WHT: {len(products_wht)}")
```

## Emergency WHT Setup (Manual)

If automated setup fails, create manually:

```python
# 1. Create WHT Account
wht_account = env['account.account'].create({
    'name': 'Withholding Tax Payable',
    'code': '2131',
    'account_type': 'liability_current', 
    'wht_account': True,
})

# 2. Create Service WHT 3%
service_wht = env['account.withholding.tax'].create({
    'name': 'Service WHT 3%',
    'account_id': wht_account.id,
    'amount': 3.0,
    'income_tax_form': 'pnd3',
    'wht_cert_income_type': '2',
})

# 3. Assign to Product
product = env['product.template'].search([('name', 'ilike', 'service')], limit=1)
if product:
    product.supplier_wht_tax_id = service_wht.id
```

## Common Error Messages and Solutions

### "Record does not exist or has been deleted"
- **Cause**: Module trying to access deleted records
- **Solution**: Already fixed in latest version with `.exists()` checks

### "AttributeError: 'NoneType' object has no attribute 'get'"
- **Cause**: Reconciliation returning None
- **Solution**: Already fixed in latest version with None checks

### "No effective PIT rate for date"
- **Cause**: Missing Personal Income Tax rates
- **Solution**: Go to Accounting > Configuration > PIT Rate and create rates

### "Selected account is not for withholding tax"
- **Cause**: Account not marked as WHT account
- **Solution**: Edit account and check "WHT Account" field

### "Please check Group Payments when dealing with multiple invoices"
- **Cause**: Trying to pay multiple invoices with WHT without grouping
- **Solution**: Check "Group Payment" in payment register wizard

## Testing Workflow

1. **Create Vendor Bill**:
   - Add product with WHT tax
   - Confirm bill
   - Check WHT amount is calculated

2. **Register Payment**:
   - Click "Register Payment"
   - Verify WHT amount auto-deducts
   - Check writeoff account is WHT account
   - Confirm payment

3. **Verify Results**:
   - Check journal entries created
   - Verify WHT certificate generated
   - Confirm amounts are correct

If any step fails, check the specific error message against the solutions above.
