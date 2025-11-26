# Quick Reference: GIT & FX Difference JE Logic

## Core Methods

### 1. Post Goods-in-Transit Entry

```python
accrual._post_goods_in_transit_entry(
    journal_id=123,                    # General journal
    git_account_id=456,                # Goods in Transit account
    foreign_ap_account_id=789,         # Foreign AP account
    date=date(2025, 1, 1)              # Bill date
)
```

**Result:** 2-line JE on bill date
- DR Goods in Transit = USD × Rate(bill_date)
- CR Foreign AP = USD × Rate(bill_date)

---

### 2. Post Goods Arrival Entry

```python
accrual._post_goods_arrival_entry(
    journal_id=123,                    # General journal
    inventory_account_id=456,          # Inventory account
    git_account_id=789,                # Goods in Transit account (must match GIT entry)
    arrival_date=date(2025, 1, 15)     # Arrival date
)
```

**Result:** 3-line JE on arrival date
- DR Inventory = USD × Rate(arrival_date)
- CR Goods in Transit = USD × Rate(bill_date)
- DR/CR FX Difference = difference (loss=DR, gain=CR)

---

## Wizard Usage

### Open from Stock Picking
```
Stock Picking → Action → Goods Arrival Reclassification
```

### Or from Code
```python
wizard = env['purchase.goods.arrival.wizard'].create({
    'stock_picking_id': picking.id,
    'purchase_order_id': po.id,
    'accrual_id': accrual.id,
    'journal_id': journal.id,
    'inventory_account_id': inv_account.id,
    'git_account_id': git_account.id,
    'arrival_date': date(2025, 1, 15),
})
wizard.action_create()
```

---

## Data Model Fields

### In `purchase.advance.accrual`

**FX Tracking:**
- `source_currency_amount` - Amount in USD
- `exchange_rate_on_bill_date` - Rate on bill date (35.0 THB/USD)
- `amount_in_company_currency_on_bill` - THB amount on bill date
- `is_git_entry` - True if this is GIT entry

**Arrival Tracking:**
- `arrival_date` - When goods arrived
- `exchange_rate_on_arrival_date` - Rate on arrival date
- `amount_in_company_currency_on_arrival` - THB amount on arrival
- `fx_difference_amount` - FX gain/loss (positive=loss, negative=gain)
- `arrival_move_id` - Link to arrival JE
- `stock_picking_id` - Link to picking

---

## Examples

### Example 1: 10,000 USD Purchase with FX Loss

**Setup:**
- Bill Date: Jan 1, Rate: 1 USD = 35 THB
- Arrival Date: Jan 15, Rate: 1 USD = 36 THB

**Step 1: Post GIT Entry**
```
Jan 1 Journal Entry:
  DR Goods in Transit     350,000 THB
    CR Foreign AP Trade           350,000 THB
```

**Step 2: Post Arrival Entry**
```
Jan 15 Journal Entry:
  DR Inventory           360,000 THB
  DR FX Loss              10,000 THB
    CR Goods in Transit           350,000 THB
    CR Exchange Difference        20,000 THB
```

**Calculation:**
- Bill: 10,000 × 35 = 350,000
- Arrival: 10,000 × 36 = 360,000
- Loss: 360,000 - 350,000 = 10,000

---

### Example 2: 10,000 USD Purchase with FX Gain

**Setup:**
- Bill Date: Jan 1, Rate: 1 USD = 35 THB
- Arrival Date: Jan 15, Rate: 1 USD = 34 THB

**Step 1: Post GIT Entry** (same as above)
```
Jan 1 Journal Entry:
  DR Goods in Transit     350,000 THB
    CR Foreign AP Trade           350,000 THB
```

**Step 2: Post Arrival Entry**
```
Jan 15 Journal Entry:
  DR Inventory           340,000 THB
    CR Goods in Transit           350,000 THB
    CR Exchange Rate Gain          10,000 THB
```

**Calculation:**
- Bill: 10,000 × 35 = 350,000
- Arrival: 10,000 × 34 = 340,000
- Gain: 340,000 - 350,000 = -10,000 (credit)

---

## Configuration Checklist

```
Company Setup:
  □ Company currency: THB
  □ FX rates set for bill date and arrival date

Account Setup:
  □ Goods in Transit (Asset account)
  □ Foreign AP Trade (Liability account)
  □ Inventory/Purchases (Asset account)
  □ Exchange Rate Difference (P&L account)

System Setup:
  □ advance.accounting.config.exchange_rate_diff_account_id set
  □ General journal available
  □ User has access rights
```

---

## State Transitions

```
Accrual States:
  'posted'  ──GIT Entry──>  State updates to 'posted'
                            ↓
                   'arrived' ──Arrival Entry──> State updates to 'arrived'
                            
  'posted'  ──Reverse──>     State updates to 'reversed'
```

---

## Common Errors & Solutions

| Error | Solution |
|-------|----------|
| "This is not a Goods-in-Transit entry" | Ensure `is_git_entry = True` |
| "Exchange Rate Difference Account is not configured" | Set account in advance.accounting.config |
| "Source currency amount not found" | Ensure GIT entry was posted with method |
| "Exchange rate on bill date not found" | Verify FX rate exists for bill date |
| "Selected accrual entry must be in posted state" | Only 'posted' state accruals can move to arrival |

---

## Testing

Run full test suite:
```bash
pytest tests/test_goods_in_transit_je.py -v
```

Run specific test:
```bash
pytest tests/test_goods_in_transit_je.py::TestGoodsInTransitJELogic::test_01_post_git_entry -v
```

---

## Key Points to Remember

1. ✅ **Store the Bill Date Rate** - Captured automatically in `_post_goods_in_transit_entry()`
2. ✅ **Use Historical Rate for GIT Credit** - Always 350,000 THB in example
3. ✅ **Calculate Inventory Debit with New Rate** - Always 360,000 or 340,000 in example
4. ✅ **FX Difference Logic:**
   - Debit = Loss (rate worsened, company pays more)
   - Credit = Gain (rate improved, company pays less)
5. ✅ **Link Everything** - GIT entry links to arrival entry and stock picking

---

## Architecture Overview

```
Purchase Order (USD)
    ↓
Create Accrual Entry
    ↓
POST GIT ENTRY (Bill Date)
  └─ Store: USD amount, Rate, THB amount
    ↓
Stock Picking Received
    ↓
Open Goods Arrival Wizard
    ↓
POST ARRIVAL ENTRY (Arrival Date)
  └─ Use: Stored USD amount, stored bill rate
  └─ Calculate: New rate, new THB amount, FX difference
    ↓
Complete - State = 'arrived'
```

---

## Related Documentation

- **Full Guide:** GIT_JE_IMPLEMENTATION_GUIDE.md
- **Tests:** tests/test_goods_in_transit_je.py
- **Summary:** IMPLEMENTATION_SUMMARY.md
- **Code:** models/advance_accrual.py, wizards/goods_arrival_wizard.py
