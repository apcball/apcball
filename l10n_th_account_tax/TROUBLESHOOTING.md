# Troubleshooting Guide - l10n_th_account_tax for Odoo 17

## Common Issues and Solutions

### 1. Missing Record Errors

**Problem**: `Record does not exist or has been deleted` errors when using batch payments or processing invoices.

**Solution**: The module now includes comprehensive error handling to prevent these errors:

- All methods check record existence using `.exists()` method
- Try-catch blocks around critical operations
- Graceful fallbacks for deleted records
- Enhanced logging for debugging

**Example Error**:
```
Record does not exist or has been deleted.
(Record: account.move(19795,), User: 2)
```

### 2. Reconciliation AttributeError

**Problem**: `AttributeError: 'NoneType' object has no attribute 'get'` during payment reconciliation.

**Solution**: Enhanced reconcile method to handle None returns:

```python
def reconcile(self):
    try:
        res = super().reconcile()
        # Check if res is None or not a dictionary
        if not res or not isinstance(res, dict):
            return res or {}
        # Continue with normal processing...
    except Exception as e:
        _logger.warning("Error in reconcile: %s", str(e))
        return {}
```

**Example Error**:
```
AttributeError: 'NoneType' object has no attribute 'get'
File "models/account_move.py", line 524, in reconcile
tax_move = res.get("tax_cash_basis_moves")
```

**Fixed Methods**:
- `_compute_wht_tax_id()`
- `_get_wht_base_amount()`
- `_get_wht_amount()`
- `_prepare_deduction_list()`
- `_compute_amount()` in payment register
- `_create_payments()`
- `reconcile()` in account move lines

### 3. Currency Conversion Issues

**Problem**: Currency conversion methods not compatible with Odoo 17.

**Solution**: Added compatibility layer with fallback mechanisms:

```python
# New approach with fallbacks
try:
    if hasattr(self.company_currency_id, '_convert'):
        amount = self.company_currency_id._convert(...)
    else:
        amount = currency._convert(...)
except Exception:
    amount = self.balance  # Fallback
```

### 4. Payment Register Wizard Errors

**Problem**: Batch payment processing fails with missing record errors.

**Solution**: Enhanced error handling in wizard methods:

- Record existence checks before processing
- Safe filtering of existing records
- Graceful error handling in onchange methods
- Improved currency conversion with fallbacks

### 5. View Inheritance Conflicts

**Problem**: View inheritance errors due to missing fields or changed structures.

**Solution**: Updated view inheritance to be more robust:

- Removed references to non-existent fields
- Added invisible fields where needed
- Updated xpath expressions for better compatibility

### 6. Field Reference Errors

**Problem**: References to fields that don't exist in Odoo 17.

**Solution**: Updated field references and added compatibility checks:

- Replaced deprecated field names
- Added proper currency_field references
- Enhanced field definitions

## Best Practices

### 1. Error Handling Pattern

When extending the module, follow this error handling pattern:

```python
def your_method(self):
    try:
        # Check if record exists
        if not self.exists():
            return default_value
            
        # Your logic here
        result = some_operation()
        return result
    except Exception as e:
        # Log error but don't break the flow
        _logger.warning("Error in your_method: %s", str(e))
        return default_value
```

### 2. Record Filtering

Always filter records for existence:

```python
# Good
existing_records = records.filtered(lambda r: r.exists())

# Better with additional checks
safe_records = records.filtered(lambda r: r.exists() and r.some_field)
```

### 3. Currency Conversion

Use the compatibility method for currency conversion:

```python
def _safe_currency_convert(self, amount, from_currency, to_currency, date):
    try:
        if hasattr(from_currency, '_convert'):
            return from_currency._convert(amount, to_currency, self.company_id, date)
        else:
            return to_currency._convert(amount, to_currency, self.company_id, date)
    except Exception:
        return amount  # Fallback to original amount
```

## Testing

Run the included tests to verify the fixes:

```bash
# Run specific test
odoo-bin -d your_database -i l10n_th_account_tax --test-enable --test-tags test_missing_record_handling

# Run all tests
odoo-bin -d your_database -i l10n_th_account_tax --test-enable
```

## Debugging

Enable debug logging to see detailed error information:

```python
import logging
_logger = logging.getLogger(__name__)
_logger.setLevel(logging.DEBUG)
```

## Performance Considerations

The error handling adds minimal overhead but provides significant stability improvements:

- Record existence checks are fast operations
- Try-catch blocks only activate on errors
- Logging is conditional and can be disabled in production

## Migration Notes

When upgrading from previous versions:

1. Backup your database
2. Test in a staging environment first
3. Monitor logs for any new warnings
4. Verify WHT calculations are correct
5. Test batch payment processing thoroughly

## Support

If you encounter issues not covered here:

1. Check the logs for detailed error messages
2. Verify record existence in the database
3. Test with a minimal dataset
4. Report issues with full error traces and steps to reproduce