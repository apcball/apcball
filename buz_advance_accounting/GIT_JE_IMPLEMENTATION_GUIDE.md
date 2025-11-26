# Goods-in-Transit (GIT) and FX Difference Journal Entry Logic
## Implementation Documentation for buz_advance_accounting Module

---

## Overview

This document describes the implementation of Journal Entry (JE) posting logic for foreign purchase goods-in-transit with FX difference calculations in Odoo 17. The implementation handles two main accounting events:

1. **Prepayment/Vendor Bill Posting (Goods-in-Transit Recognition)** - On document date
2. **Goods Arrival Reclassification JE (GIT to Inventory + FX Difference)** - On arrival date

---

## Business Scenario

### Company Setup
- **Company Currency:** THB (Thai Baht)
- **Vendor Currency:** USD (US Dollar)
- **Purchase Model:** Sea freight purchase with goods-in-transit period

### Accounting Events

#### Event 1: Goods-in-Transit Recognition (Bill Date)
**When:** On Document Date (e.g., 2025-01-01)
- Company receives vendor bill in USD
- Goods not yet received (still in transit)

**Accounting Entry:**
```
DR Goods in Transit (asset)           = USD amount × FX rate on bill date
CR Foreign AP Trade (liability)        = USD amount × FX rate on bill date
```

#### Event 2: Goods Arrival Reclassification (Arrival Date)
**When:** Goods physically arrive (e.g., 2025-01-15)
- Reclassify from GIT to Inventory using new FX rate
- Book exchange difference

**Accounting Entry:**
```
DR Inventory/Purchases                = USD amount × FX rate on arrival date
CR Goods in Transit                   = USD amount × FX rate on bill date (historical)
DR/CR Exchange Difference              = difference if positive/negative
```

---

## Implementation Details

### 1. Data Model Extensions

#### New Fields in `purchase.advance.accrual`

**FX Tracking Fields:**
```python
# Foreign exchange tracking
source_currency_amount                 # Amount in original currency (USD)
exchange_rate_on_bill_date            # FX rate on bill date (THB per unit)
amount_in_company_currency_on_bill    # THB amount on bill date
company_currency_id                   # Related company currency

# Goods arrival tracking
is_git_entry                          # Flag to identify GIT entries
stock_picking_id                      # Link to receiving stock picking
arrival_date                          # Date goods arrived
exchange_rate_on_arrival_date         # FX rate on arrival date
amount_in_company_currency_on_arrival # THB amount on arrival date
fx_difference_amount                  # FX gain/loss amount
arrival_move_id                       # Link to arrival JE
```

**State Extension:**
```python
state = [
    ('posted', 'Posted'),              # GIT JE posted on bill date
    ('reversed', 'Reversed'),           # Original JE reversed
    ('arrived', 'Goods Arrived'),       # Arrival JE posted
]
```

---

### 2. Core Methods

#### Method: `_post_goods_in_transit_entry()`

**Purpose:** Post GIT recognition JE on bill date

**Signature:**
```python
def _post_goods_in_transit_entry(
    self, 
    journal_id, 
    git_account_id, 
    foreign_ap_account_id, 
    date=None
)
```

**Logic Flow:**
1. Retrieve FX rate on bill date using `_get_conversion_rate()`
2. Calculate THB amount: `USD amount × FX rate`
3. Create 2-line JE:
   - Line 1: Debit Goods in Transit
   - Line 2: Credit Foreign AP Trade
4. Post and store FX tracking data
5. Update accrual state to 'posted'

**Example:**
```
Bill Date: 2025-01-01
USD Amount: 10,000
FX Rate: 1 USD = 35 THB

JE:
  DR Goods in Transit           350,000 THB
    CR Foreign AP Trade                   350,000 THB
```

---

#### Method: `_post_goods_arrival_entry()`

**Purpose:** Post goods arrival reclassification JE with FX calculation

**Signature:**
```python
def _post_goods_arrival_entry(
    self, 
    journal_id, 
    inventory_account_id, 
    git_account_id, 
    arrival_date=None
)
```

**Logic Flow:**
1. Validate entry is GIT entry and in 'posted' state
2. Retrieve historical data:
   - Source currency amount (USD)
   - Bill date FX rate (35 THB/USD)
   - THB amount on bill date (350,000 THB)
3. Get FX rate on arrival date
4. Calculate:
   - `THB debit inventory = USD amount × FX rate on arrival date`
   - `THB credit GIT = USD amount × FX rate on bill date` (from stored data)
   - `FX difference = THB debit - THB credit`
5. Create JE lines:
   - Line 1: Debit Inventory
   - Line 2: Credit Goods in Transit
   - Line 3: Debit/Credit FX Difference (if non-zero)
6. Post and update state to 'arrived'

**FX Difference Logic:**
```
if FX diff > 0:
    # Unfavorable rate change (company pays more)
    # Loss: DR Exchange Difference
    
if FX diff < 0:
    # Favorable rate change (company pays less)
    # Gain: CR Exchange Difference (amount = abs(diff))
    
if FX diff == 0:
    # No exchange difference
```

**Example (Loss Scenario):**
```
Bill Date: 2025-01-01, Rate: 1 USD = 35 THB
Arrival Date: 2025-01-15, Rate: 1 USD = 36 THB
USD Amount: 10,000

Calculations:
  THB on bill date: 10,000 × 35 = 350,000 THB
  THB on arrival: 10,000 × 36 = 360,000 THB
  FX difference: 360,000 - 350,000 = 10,000 THB (LOSS)

JE:
  DR Inventory                  360,000 THB
  DR Exchange Rate Loss          10,000 THB
    CR Goods in Transit                    350,000 THB
    CR Foreign AP (not in this JE)        20,000 THB*
    
*Note: The remaining AP is handled in subsequent invoice posting
```

---

### 3. Wizard Integration

#### Goods Arrival Wizard: `purchase.goods.arrival.wizard`

**Purpose:** User interface for posting goods arrival JE

**Key Features:**
- Selects GIT accrual entries ready for arrival processing
- Displays bill date FX rate and THB amount
- Allows user to specify arrival date
- Shows preview of JE lines before posting
- Validates all required accounts before posting

**Workflow:**
1. User opens wizard from Stock Picking
2. Select GIT accrual entry to process
3. Specify accounts and arrival date
4. Review preview
5. Click "Post Goods Arrival Entry"
6. System creates and posts JE
7. Return to journal entry form

---

## Configuration Requirements

### Accounts Setup

**Required Accounts:**
1. **Goods in Transit** - Asset account (e.g., code 1031)
2. **Foreign AP Trade** - Liability account (e.g., code 2111)
3. **Inventory/Purchases** - Asset account (e.g., code 1110)
4. **Exchange Rate Difference** - P&L account (e.g., code 5100)

### Configuration Model: `advance.accounting.config`

```python
exchange_rate_diff_account_id  # Account for FX gains/losses
```

---

## Usage Example

### Scenario: Import Goods from USA

**Setup:**
- Company: ABC Company (Currency: THB)
- Vendor: Smith Corp (Currency: USD)
- PO: PO/001 for 10,000 USD
- Bill Date: January 1, 2025 (1 USD = 35 THB)
- Arrival Date: January 15, 2025 (1 USD = 36 THB)

### Step 1: Create Purchase Order
```python
po = env['purchase.order'].create({
    'partner_id': vendor_id,
    'currency_id': usd_id,
    'order_line': [(0, 0, {
        'product_id': product_id,
        'product_qty': 100,
        'price_unit': 100,  # Total: 10,000 USD
    })]
})
po.button_confirm()
```

### Step 2: Create Advance Accrual (GIT Entry)
```python
accrual = env['purchase.advance.accrual'].create({
    'purchase_id': po.id,
    'date': datetime(2025, 1, 1).date(),
    'amount': 10000,
    'currency_id': usd_id,
})

# Post GIT entry
move_git = accrual._post_goods_in_transit_entry(
    journal_id=general_journal.id,
    git_account_id=git_account.id,
    foreign_ap_account_id=foreign_ap_account.id,
    date=datetime(2025, 1, 1).date()
)
```

**Result:**
```
JE Date: 2025-01-01
  DR Goods in Transit           350,000 THB
    CR Foreign AP Trade                    350,000 THB
```

### Step 3: Receive Goods (Jan 15)
```python
# Create and validate stock picking
picking.button_validate()

# From picking, open Goods Arrival Wizard
wizard = env['purchase.goods.arrival.wizard'].create({
    'stock_picking_id': picking.id,
    'purchase_order_id': po.id,
    'accrual_id': accrual.id,
    'journal_id': general_journal.id,
    'inventory_account_id': inventory_account.id,
    'git_account_id': git_account.id,
    'arrival_date': datetime(2025, 1, 15).date(),
})

# Post goods arrival entry
move_arrival = wizard.action_create()
```

**Result:**
```
JE Date: 2025-01-15
  DR Inventory                   360,000 THB
  DR Exchange Rate Loss           10,000 THB
    CR Goods in Transit                    350,000 THB
    CR Exchange Rate Difference            20,000 THB
```

---

## Error Handling

### Validations Performed

1. **GIT Entry Validation**
   - Entry must have `is_git_entry = True`
   - Entry must be in 'posted' state

2. **Account Validation**
   - All required accounts must be selected
   - Accounts must not be deprecated

3. **Currency Validation**
   - Source currency must differ from company currency
   - FX rate must be available for both dates

4. **Data Validation**
   - `source_currency_amount` must be stored
   - `exchange_rate_on_bill_date` must be available
   - `amount_in_company_currency_on_bill` must be set

### Error Messages

```python
# If GIT entry not found
raise UserError(_('This is not a Goods-in-Transit entry.'))

# If entry not posted
raise UserError(_('Selected accrual entry must be in posted state.'))

# If data missing
raise UserError(_('Source currency amount not found in the accrual entry.'))
raise UserError(_('Exchange rate on bill date not found.'))

# If account missing
raise UserError(_('Exchange Rate Difference Account is not configured.'))
```

---

## FX Rate Handling

### Exchange Rate Format in Odoo

Odoo stores exchange rates in **decimal format**:
- Example: 1 USD = 35 THB is stored as `rate = 0.030861` (i.e., 1/35)

### Conversion Methods Used

```python
# Get FX rate on specific date
fx_rate_decimal = source_currency._get_conversion_rate(
    company_currency, 
    source_currency, 
    company, 
    date
)

# Convert amount using FX rate
thb_amount = source_currency._convert(
    usd_amount,
    company_currency,
    company,
    date
)

# Convert from decimal to THB per unit
thb_per_unit = 1.0 / fx_rate_decimal  # 1/0.030861 = 32.45
```

---

## Testing

### Test Cases Implemented

1. **test_01_post_git_entry**
   - Verify GIT JE posted correctly on bill date
   - Check amounts calculated with bill date FX rate
   - Verify accrual record updated with FX data

2. **test_02_post_goods_arrival_entry_with_fx_gain**
   - Test scenario where rate improves (FX gain)
   - Verify gain posted as credit

3. **test_03_post_goods_arrival_entry_with_fx_loss**
   - Test scenario where rate deteriorates (FX loss)
   - Verify loss posted as debit

4. **test_04_complete_workflow**
   - End-to-end workflow: PO → GIT → Arrival
   - Verify state transitions and entry linking

### Running Tests

```bash
# Run specific test
python -m pytest tests/test_goods_in_transit_je.py::TestGoodsInTransitJELogic::test_01_post_git_entry -v

# Run all GIT tests
python -m pytest tests/test_goods_in_transit_je.py -v

# Run with Odoo
odoo -c odoo.conf -d database_name tests/test_goods_in_transit_je.py
```

---

## Files Modified/Created

### Modified Files
1. `models/advance_accrual.py` - Extended with FX fields and JE posting methods
2. `models/stock_picking.py` - Added method to trigger goods arrival wizard
3. `wizards/__init__.py` - Import new wizard module
4. `__manifest__.py` - Added wizard view to data files
5. `security/ir.model.access.csv` - Added ACL for new models

### New Files Created
1. `wizards/goods_arrival_wizard.py` - Wizard for posting goods arrival JE
2. `wizards/goods_arrival_wizard_views.xml` - UI for wizard
3. `tests/test_goods_in_transit_je.py` - Comprehensive test suite

---

## Integration Points

### With Other Modules

1. **account.move** - Posts JEs with multi-line support
2. **res.currency** - Retrieves FX rates for specific dates
3. **stock.picking** - Links to goods receipt
4. **account.account** - Uses various accounts for posting

### API Hooks

```python
# Callable from other modules
accrual._post_goods_in_transit_entry(...)
accrual._post_goods_arrival_entry(...)

# Configuration access
config = env['advance.accounting.config'].get_config()
fx_account = config.get_exchange_rate_diff_account()
```

---

## Appendix: Example Numbers

### Example 1: FX Loss Scenario
```
Date 1 (Bill):      2025-01-01
  Rate: 1 USD = 35 THB
  USD Amount: 10,000
  THB Amount: 350,000

Date 2 (Arrival):   2025-01-15
  Rate: 1 USD = 36 THB (rate worsened)
  USD Amount: 10,000
  THB Amount: 360,000
  
FX Difference: 360,000 - 350,000 = 10,000 THB LOSS

Journal Entry:
  DR Inventory                360,000
  DR Exchange Rate Loss        10,000
    CR Goods in Transit                 350,000
    CR (Remainder handled separately)    20,000
```

### Example 2: FX Gain Scenario
```
Date 1 (Bill):      2025-01-01
  Rate: 1 USD = 35 THB
  USD Amount: 10,000
  THB Amount: 350,000

Date 2 (Arrival):   2025-01-15
  Rate: 1 USD = 34 THB (rate improved)
  USD Amount: 10,000
  THB Amount: 340,000
  
FX Difference: 340,000 - 350,000 = -10,000 THB GAIN

Journal Entry:
  DR Inventory                340,000
    CR Goods in Transit                 350,000
    CR Exchange Rate Gain                10,000
```

---

## Support and Maintenance

For questions or issues:
1. Check test cases for usage examples
2. Review model documentation in code
3. Verify account configuration in system
4. Check FX rates are set for both bill and arrival dates
