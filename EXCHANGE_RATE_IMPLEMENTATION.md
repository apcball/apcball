# Exchange Rate Module Implementation - THB per Unit Format

## Overview
This document describes the exchange rate module implementation for the `buz_advance_accounting` module. The exchange rate is now displayed and input in "THB per Unit" format, which is more intuitive for users working with Thai Baht (THB).

## Format Explanation

### Exchange Rate Formats

1. **Auto Exchange Rate (Decimal)** - Internal format used by Odoo
   - Format: `0.030861` (example)
   - This is stored internally but NOT shown to users
   - Meaning: 1 unit of source currency = 0.030861 THB
   - **Note:** This decimal format is counterintuitive for Thai users

2. **Auto Exchange Rate (THB per Unit)** - Display format
   - Format: `32.45` (example)
   - Calculated as: `1 / auto_exchange_rate_decimal`
   - Meaning: 1 unit of source currency = 32.45 THB
   - **Status:** Read-only, automatically calculated

3. **Manual Exchange Rate (THB per Unit)** - User input format
   - Format: `32.10` (example)
   - Meaning: 1 unit of source currency = 32.10 THB
   - **Status:** Editable when "Use Manual Exchange Rate" is checked
   - **Purpose:** Allows users to override the automatic rate

## Implementation Details

### Python Model Changes

#### New Fields
```python
auto_exchange_rate = fields.Float(string='Auto Exchange Rate (Decimal)', readonly=True)
auto_exchange_rate_thb = fields.Float(string='Auto Rate (THB per Unit)', readonly=True, compute='_compute_exchange_rate_thb')
manual_exchange_rate = fields.Float(string='Manual Rate (THB per Unit)', digits=(12, 6))
source_currency_name = fields.Char(compute='_compute_currency_names')
company_currency_name = fields.Char(compute='_compute_currency_names')
```

#### New Compute Methods

**`_compute_exchange_rate_thb()`**
- Converts `auto_exchange_rate` (decimal) to `auto_exchange_rate_thb` (THB per Unit)
- Calculation: `auto_exchange_rate_thb = 1.0 / auto_exchange_rate`
- Executes when `auto_exchange_rate` changes

**`_compute_currency_names()`**
- Extracts and displays currency codes
- Shows "From Currency" and "To Currency" labels
- Makes the UI more informative

#### Updated Methods

**`_compute_exchange_rates()`**
- Enhanced to handle both decimal and THB formats
- When setting manual rate from auto rate:
  ```python
  manual_exchange_rate = 1.0 / auto_exchange_rate
  ```
- Conversion calculation for exchange rate difference:
  ```python
  # manual_exchange_rate is THB per Unit (e.g., 32.10)
  # To convert from foreign currency to company currency, divide by the rate
  amount_company_manual = self.amount / self.manual_exchange_rate
  ```

### XML View Changes

#### Exchange Rate Section
The section now displays:

1. **Currency Information** (Read-only)
   - From Currency: Source currency code (e.g., USD)
   - To Currency: Company currency code (e.g., THB)

2. **Automatic Rate** (Read-only)
   - Auto Rate (THB per Unit): Displays rate in user-friendly format
   - Example: 32.45 (means 32.45 THB = 1 USD)

3. **Manual Override** (Optional)
   - Checkbox: "Use Manual Exchange Rate"
   - When checked, shows:
     - Manual Rate (THB per Unit): Input field for user
     - Difference Amount: Calculated automatically

#### Visibility Logic
```xml
attrs="{'invisible': 'not show_exchange_rate_section'}"
```
Exchange rate section only shows when:
- Purchase order exists
- Source currency ≠ Company currency

## Usage Examples

### Example 1: USD to THB with Auto Rate
1. Create Advance Accrual from a USD Purchase Order
2. The wizard automatically:
   - Detects USD ≠ THB currencies
   - Shows Exchange Rate Information section
   - Displays Auto Rate (THB per Unit): 32.45
   - Uses this rate for conversion

### Example 2: USD to THB with Manual Override
1. Open the wizard with USD Purchase Order
2. Check "Use Manual Exchange Rate"
3. Enter Manual Rate (THB per Unit): 32.10
4. The wizard calculates:
   - Exchange rate difference
   - Adjusted journal entry lines
   - Difference amount: THB value difference

### Example 3: USD Amount Conversion
Given:
- Amount (USD): 386.13
- Manual Rate: 32.10 THB per USD

Calculation:
- Amount (THB) = 386.13 / 32.10 = 12,026.65 THB

## Journal Entry Preview

The preview shows how amounts are split:

| Account | Description | Debit (THB) | Credit (THB) |
|---------|-------------|------------|-------------|
| Expense Account | Advance Accrual | 11,223.64 | - |
| Tax Input Account | Input Tax | 803.01 | - |
| Accrual Account | Advance Accrual | - | 12,026.65 |
| Exchange Rate Diff | Exchange Difference | (if applicable) | - |

## Database Impact

### Fields Stored
- `manual_exchange_rate`: Stored as user input in THB per Unit format
- `exchange_rate_diff_amount`: Stored as calculated difference
- `auto_exchange_rate`: Stored for reference in decimal format

### Computed Fields (Not Stored)
- `auto_exchange_rate_thb`: Computed from `auto_exchange_rate`
- `source_currency_name`: Computed from `currency_id`
- `company_currency_name`: Computed from company currency

## Validation & Error Handling

1. **Zero Rate Check**: Prevents division by zero
   ```python
   if self.manual_exchange_rate != 0:
       amount_company_manual = self.amount / self.manual_exchange_rate
   ```

2. **Currency Matching**: Only shows exchange rate section when currencies differ

3. **Negative Amount Check**: Preview only shows when amount > 0

## Troubleshooting

### Issue: Exchange Rate Section Not Showing
**Solution:** Verify that:
- Purchase order currency ≠ Company currency
- Both currencies are set

### Issue: Auto Rate Shows as 1.0
**Solution:** 
- Check if source and company currencies are the same
- If different, verify exchange rates are configured in Odoo

### Issue: Manual Rate Not Applied
**Solution:**
- Ensure "Use Manual Exchange Rate" checkbox is checked
- Verify the manual rate is greater than 0
- Check that the rate is in THB per Unit format (not decimal)

## Related Files
- `/wizards/advance_bill_wizard.py` - Main model
- `/wizards/advance_bill_wizard_views.xml` - UI form
- `/tests/test_exchange_rate_feature.py` - Unit tests

## Future Enhancements
1. Add rate history tracking
2. Implement exchange rate validation against market rates
3. Add bulk exchange rate updates
4. Support for additional currency formats
5. Rate rounding policy configuration
