# Exchange Rate Module - UI Comparison

## Visual Layout Comparison

### BEFORE: Exchange Rate Information Section

```
┌─────────────────────────────────────────────────────┐
│ EXCHANGE RATE INFORMATION                           │
├─────────────────────────────────────────────────────┤
│                                                     │
│ Auto Exchange Rate          0.030861                │
│ Use Manual Exchange Rate    [checkbox]              │
│                                                     │
│ Manual Exchange Rate        [text input field]      │
│ Exchange Rate Difference    0.00                    │
│                                                     │
└─────────────────────────────────────────────────────┘

⚠️ Issues:
  • Decimal format (0.030861) is not intuitive
  • No context about which currencies are converting
  • Auto rate doesn't indicate it's a display format
  • Manual rate field always visible (even when unchecked)
```

---

### AFTER: Exchange Rate Information Section

```
┌──────────────────────────────────────────────────────────┐
│ EXCHANGE RATE INFORMATION                                │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ From Currency              USD                           │
│ To Currency                THB                           │
│                                                          │
│ Auto Rate (THB per Unit)   32.45         ← Intuitive!   │
│ Use Manual Exchange Rate   ☐ [checkbox]                  │
│                                                          │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ When "Use Manual Exchange Rate" is checked:         │  │
│ │                                                     │  │
│ │ Manual Rate (THB per Unit)    32.10                │  │
│ │ Difference Amount             119.92               │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                          │
└──────────────────────────────────────────────────────────┘

✅ Improvements:
  • Clear currency conversion context
  • THB per Unit format (32.45) is intuitive
  • Manual fields only show when needed
  • Currency labels reduce confusion
```

---

## State Flow Diagram

### Same Currency (THB to THB)

```
User selects THB Purchase Order
        ↓
Check: purchase_id.currency_id == company.currency_id
        ↓
show_exchange_rate_section = FALSE
        ↓
Exchange Rate Information Section is HIDDEN
        ↓
No rate conversion needed
```

### Different Currencies (USD to THB)

```
User selects USD Purchase Order
        ↓
Check: purchase_id.currency_id != company.currency_id
        ↓
show_exchange_rate_section = TRUE
        ↓
┌─────────────────────────────────────┐
│ Exchange Rate Information is SHOWN  │
├─────────────────────────────────────┤
│ From Currency: USD                  │
│ To Currency: THB                    │
│ Auto Rate (THB per Unit): 32.45     │
│ Use Manual Exchange Rate: ☐         │
└─────────────────────────────────────┘
        ↓
User checks "Use Manual Exchange Rate"
        ↓
┌─────────────────────────────────────┐
│ Manual fields now VISIBLE           │
├─────────────────────────────────────┤
│ Manual Rate (THB per Unit): 32.10   │
│ Difference Amount: 119.92           │
└─────────────────────────────────────┘
        ↓
Manual rate applied to journal entry
```

---

## Calculation Flow Diagram

### Exchange Rate Conversion Process

```
PO Currency & Company Currency
        ↓
    Are they different?
    ├─ NO → Use 1.0 rate, skip exchange section
    └─ YES ↓
        Get auto_exchange_rate (decimal format from Odoo)
        Example: 0.030861
        ↓
        Convert to THB per Unit format
        auto_exchange_rate_thb = 1 / auto_exchange_rate
        Example: 1 / 0.030861 = 32.45
        ↓
        Display to user: "Auto Rate (THB per Unit): 32.45"
        ↓
        User can override with manual_exchange_rate
        Example: 32.10 (user enters THB per Unit)
        ↓
        Calculate difference:
        - Using auto: amount / 32.45
        - Using manual: amount / 32.10
        - Difference: manual_amount - auto_amount
        ↓
        Apply to journal entry amounts
```

---

## Data Flow Diagram

### From User Input to Journal Entry

```
User Action: Enter USD Amount 386.13
        ↓
Field: amount = 386.13
        ↓
Trigger: @api.onchange('amount', ..., 'manual_exchange_rate')
        ↓
_onchange_recompute_preview()
        ├─ Call _compute_exchange_rates()
        │  ├─ Get auto_exchange_rate (decimal: 0.030861)
        │  ├─ Convert to THB format (32.45)
        │  ├─ If use_manual_exchange_rate:
        │  │  └─ Calculate exchange_rate_diff_amount
        │  └─ Set manual_exchange_rate to 1/auto if needed
        │
        └─ Call _recompute_preview()
           ├─ Split amount by tax ratio
           ├─ Convert using appropriate rate:
           │  ├─ If manual: use manual_exchange_rate
           │  └─ If auto: use auto (decimal format)
           │
           └─ Generate preview_line_ids
              ├─ Expense account: 11,223.64 THB
              ├─ Tax account: 803.01 THB
              ├─ Accrual account: 12,026.65 THB
              └─ Exchange diff (if applicable)
```

---

## Exchange Rate Conversion Examples

### Example 1: Auto Rate Display

```
Odoo Internal → User Display
    ↓
0.030861 (decimal format)
    ↓
Computation: 1 / 0.030861 = 32.45
    ↓
Display to User: "32.45 THB per Unit"
    ✓ User understands: 32.45 THB = 1 USD
```

### Example 2: Amount Conversion

```
Amount (USD): 386.13
Manual Rate: 32.10 THB per USD
    ↓
Calculation: 386.13 ÷ 32.10 = 12,026.65 THB
    ↓
Preview shows:
  • Debit Expense: 11,223.64 THB (before tax)
  • Debit Tax: 803.01 THB
  • Credit Accrual: 12,026.65 THB
```

### Example 3: Exchange Rate Difference

```
Auto Rate (THB per Unit): 32.45
Manual Rate (THB per Unit): 32.10
Difference: 32.45 - 32.10 = 0.35 per unit

Amount: 386.13 USD
    ↓
Auto conversion: 386.13 ÷ 32.45 = 11,906.73 THB
Manual conversion: 386.13 ÷ 32.10 = 12,026.65 THB
    ↓
Difference Amount: 12,026.65 - 11,906.73 = 119.92 THB
    ↓
Adds to journal entry:
  • Debit: Exchange Rate Difference Account 119.92
  • Credit: Accrual Account 119.92
```

---

## Component Interaction Diagram

```
┌──────────────────────────────────────────────────────────┐
│ PURCHASE ADVANCE BILL WIZARD                             │
├──────────────────────────────────────────────────────────┤
│                                                          │
│ Fields:                                                  │
│  • purchase_id                                           │
│  • amount (USD)                                          │
│  • currency_id                                           │
│  • auto_exchange_rate (decimal: 0.030861)               │
│  • auto_exchange_rate_thb (computed: 32.45)             │
│  • manual_exchange_rate (user input: 32.10)             │
│  • exchange_rate_diff_amount (computed: 119.92)         │
│  • source_currency_name (computed: USD)                 │
│  • company_currency_name (computed: THB)                │
│                                                          │
│ Compute Methods:                                         │
│  ├─ _compute_exchange_rate_thb()                        │
│  │  └─ auto_exchange_rate_thb = 1 / auto_exchange_rate │
│  ├─ _compute_currency_names()                           │
│  │  ├─ source_currency_name = currency_id.name          │
│  │  └─ company_currency_name = company_currency.name    │
│  └─ _compute_exchange_rates()                           │
│     └─ Updates all exchange rate fields                 │
│                                                          │
│ On Change Handlers:                                      │
│  ├─ @api.onchange('purchase_id')                        │
│  │  └─ Initialize rates and preview                     │
│  └─ @api.onchange('amount', 'manual_exchange_rate', ...) │
│     └─ Recompute preview                                │
│                                                          │
│ Preview Generation:                                      │
│  └─ preview_line_ids                                    │
│     ├─ Account ID, Debit, Credit                        │
│     ├─ Uses manual_exchange_rate if set                 │
│     └─ Shows journal entry before posting                │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## UI State Transitions

### State 1: Initial Load with USD PO
```
┌─────────────────────────┐
│ From Currency: USD      │
│ To Currency: THB        │
│ Auto Rate: 32.45        │
│ ☐ Manual Rate           │
│                         │
│ Manual fields HIDDEN    │
└─────────────────────────┘
```

### State 2: Check "Use Manual Exchange Rate"
```
┌──────────────────────────────────┐
│ From Currency: USD               │
│ To Currency: THB                 │
│ Auto Rate: 32.45                 │
│ ☑ Manual Rate                    │
│   └─ Manual Rate: 32.10          │
│   └─ Difference: 119.92          │
│                                  │
│ Manual fields now VISIBLE        │
└──────────────────────────────────┘
```

### State 3: Change Manual Rate Value
```
┌──────────────────────────────────┐
│ From Currency: USD               │
│ To Currency: THB                 │
│ Auto Rate: 32.45                 │
│ ☑ Manual Rate                    │
│   └─ Manual Rate: 31.50  ← Changed│
│   └─ Difference: 245.78  ← Updated │
│                                  │
│ Difference recalculated          │
└──────────────────────────────────┘
```

---

## Key Features

✅ **User-Friendly:**
- THB per Unit format matches real-world usage
- Currency labels provide context
- Manual rate option for adjustments

✅ **Automatic:**
- Exchange rates calculated from Odoo
- Differences computed automatically
- Preview updated in real-time

✅ **Transparent:**
- Shows both auto and manual rates
- Displays exchange difference clearly
- Journal preview before posting

✅ **Flexible:**
- Override with manual rates when needed
- Configurable per transaction
- Works with any currency pair

---

## Browser Rendering Example

### Normal View (USD Purchase Order)

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Create Advance Accrual              [⊞] [×]┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃                                           ┃
┃ ACCRUAL INFORMATION                       ┃
┃ Journal              Miscellaneous Ops    ┃
┃ Date                 20/11/2025           ┃
┃ Accrual Account      115600 สินค่าระหว่างนาง ┃
┃ Amount               $ 386.13             ┃
┃ Currency             USD                  ┃
┃ Reference            [blank]              ┃
┃                                           ┃
┃ EXCHANGE RATE INFORMATION                 ┃
┃ From Currency        USD                  ┃
┃ To Currency          THB                  ┃
┃ Auto Rate (THB/Unit) 32.45                ┃
┃ ☐ Use Manual Exchange Rate                ┃
┃                                           ┃
┃ JOURNAL ENTRY PREVIEW                     ┃
┃                                           ┃
┃ Account | Description | Debit | Credit  ┃
┃ 512000  | Advance     | 11,2  | -       ┃
┃ 115600  | Accrual     | -     | 12,026 ┃
┃                                           ┃
┃ [Create Accrual Entry] [Cancel]          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### With Manual Rate Enabled

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Create Advance Accrual              [⊞] [×]┃
┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫
┃ ... (previous fields same) ...            ┃
┃                                           ┃
┃ EXCHANGE RATE INFORMATION                 ┃
┃ From Currency        USD                  ┃
┃ To Currency          THB                  ┃
┃ Auto Rate (THB/Unit) 32.45                ┃
┃ ☑ Use Manual Exchange Rate                ┃
┃ Manual Rate (THB/Unit) 32.10              ┃
┃ Difference Amount    119.92               ┃
┃                                           ┃
┃ JOURNAL ENTRY PREVIEW                     ┃
┃                                           ┃
┃ Account | Description | Debit | Credit  ┃
┃ 512000  | Advance     | 11,2  | -       ┃
┃ 115600  | Accrual     | -     | 12,026 ┃
┃ 99XX00  | Exch Diff   | 119.92| -       ┃
┃                                           ┃
┃ [Create Accrual Entry] [Cancel]          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

---

**This visual comparison shows the significant UI improvement in clarity and usability.**
