# Exchange Rate Decimal Precision Enhancement

## Overview
This document describes the changes made to support 4 decimal places for exchange rate fields in the Manual Currency Exchange Rate module.

## Changes Made

### 1. Model Changes

#### Sale Order Model (`models/sale_order.py`)
- Modified the `rate` field to include `digits=(12, 4)` parameter
- This allows up to 4 decimal places with a maximum of 12 total digits
- Fixed the `_compute_rate` method to only compute the rate value, not modify other fields
- Changed the dependency from `order_line.product_id` to `is_exchange`

#### Purchase Order Model (`models/purchase_order.py`)
- Modified the `rate` field to include `digits=(12, 4)` parameter
- This allows up to 4 decimal places with a maximum of 12 total digits
- Fixed the `_compute_rate` method to only compute the rate value, not modify other fields
- Changed the dependency from `order_line.product_id` to `is_exchange`

#### Account Move Model (`models/account_move.py`)
- Modified the `rate` field to include `digits=(12, 4)` parameter
- This allows up to 4 decimal places with a maximum of 12 total digits
- Fixed the `_compute_rate` method to only compute the rate value, not modify other fields
- Changed the dependency from `invoice_line_ids.product_id` to `is_exchange`

### 2. View Changes

#### Sale Order View (`views/sale_order_views.xml`)
- Added `widget="float"` to the rate field to ensure proper display of decimal places

#### Purchase Order View (`views/purchase_order_views.xml`)
- Added `widget="float"` to the rate field to ensure proper display of decimal places

#### Account Move View (`views/account_move_views.xml`)
- Added `widget="float"` to the rate field to ensure proper display of decimal places

### 3. Testing

Created a test script (`test_decimal_precision.py`) that can be run in an Odoo shell to verify:
- Exchange rate fields accept values with up to 4 decimal places
- Values are stored correctly in the database
- Values display properly in the UI

## Technical Details

### Field Definition
The `rate` field in all three models now uses:
```python
rate = fields.Float(string='Rate', help='specify the rate',
                    compute='_compute_rate', readonly=False, store=True,
                    default=1, digits=(12, 4))
```

The `digits=(12, 4)` parameter means:
- Total precision: 12 digits
- Scale: 4 decimal places
- This allows values from -99999999.9999 to 99999999.9999

### Compute Method Fix
The original compute methods were incorrectly modifying other fields (price_unit) during computation, which caused errors with other modules. The fixed compute methods now:
- Only compute the value of the rate field itself
- Set a default value of 1.0 if no rate is specified
- Depend only on the `is_exchange` field, not on product fields
```python
@api.depends('is_exchange')
def _compute_rate(self):
    """Compute the default rate value."""
    for rec in self:
        if not rec.rate:
            rec.rate = 1.0
```

### Benefits
1. **More precise currency conversion**: Support for up to 4 decimal places allows for more accurate exchange rates
2. **Consistent behavior**: All three document types (Sales, Purchases, and Invoices) now have the same precision
3. **Backward compatibility**: Existing data with fewer decimal places continues to work correctly
4. **User-friendly**: The UI properly displays all decimal places entered by the user

## Usage

1. Enable "Apply Manual Currency" on any Sales Order, Purchase Order, or Invoice
2. Enter an exchange rate with up to 4 decimal places (e.g., 1.2345)
3. The rate will be stored and displayed with the correct precision
4. The system will use this rate to calculate converted amounts

## Testing

To test the implementation:
1. Install or update the module
2. Create a new Sales Order, Purchase Order, or Invoice
3. Enable the manual exchange rate option
4. Enter rates with various decimal places (1.2, 1.23, 1.234, 1.2345)
5. Verify that the rates are stored and displayed correctly

Alternatively, run the test script in an Odoo shell:
```python
exec(open('exchange_currency_rate/test_decimal_precision.py').read())
test_exchange_rate_precision()