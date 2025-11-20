# Exchange Rate Module - Quick Reference Guide

## 🎯 What Was Changed

The exchange rate module now displays and accepts exchange rates in **THB per Unit** format instead of the decimal format.

### Format Examples

| Format | Example | Meaning |
|--------|---------|---------|
| **Decimal (Old)** | 0.030861 | 1 USD = 0.030861 THB ❌ (confusing) |
| **THB per Unit (New)** | 32.45 | 1 USD = 32.45 THB ✅ (intuitive) |

## 📋 UI Changes

### Before
```
Auto Exchange Rate: 0.030861
Manual Exchange Rate: [input field]
Exchange Rate Difference: 0.00
```

### After
```
From Currency: USD
To Currency: THB

Auto Rate (THB per Unit): 32.45 ← Read-only, auto-calculated
☐ Use Manual Exchange Rate
  [When checked:]
  Manual Rate (THB per Unit): 32.10 ← User enters here
  Difference Amount: 119.92 ← Auto-calculated
```

## 🔧 Technical Changes

### Python Model (`advance_bill_wizard.py`)

**New Fields:**
- `auto_exchange_rate_thb` - Auto rate in THB per Unit format (computed)
- `source_currency_name` - Source currency code (computed)
- `company_currency_name` - Company currency code (computed)

**Updated Methods:**
- `_compute_exchange_rates()` - Now converts decimal to THB format
- Added `_compute_exchange_rate_thb()` - New conversion method
- Added `_compute_currency_names()` - New display method

### XML View (`advance_bill_wizard_views.xml`)

**Exchange Rate Section:**
```xml
<group string="Exchange Rate Information" 
       attrs="{'invisible': 'not show_exchange_rate_section'}">
  <!-- Currency Labels -->
  <field name="source_currency_name" string="From Currency"/>
  <field name="company_currency_name" string="To Currency"/>
  
  <!-- Auto Rate -->
  <field name="auto_exchange_rate_thb" string="Auto Rate (THB per Unit)"/>
  
  <!-- Manual Override (Optional) -->
  <field name="use_manual_exchange_rate"/>
  <field name="manual_exchange_rate" string="Manual Rate (THB per Unit)"/>
  <field name="exchange_rate_diff_amount" string="Difference Amount"/>
</group>
```

## 📝 How to Use

### Scenario 1: USD Purchase Order with Auto Rate
1. Open "Create Advance Accrual" wizard
2. Select USD Purchase Order
3. Exchange Rate Information appears automatically
4. See "Auto Rate (THB per Unit): 32.45"
5. Amount converts using this rate

### Scenario 2: Manual Rate Override
1. Open wizard with USD PO
2. Check "Use Manual Exchange Rate"
3. Enter "Manual Rate (THB per Unit): 32.10"
4. See calculated "Difference Amount: 119.92"
5. Journal entry created with adjusted amount

### Scenario 3: Same Currency (No Exchange Rate)
1. Open wizard with THB PO
2. Exchange Rate Information section hidden
3. No rate needed, amount used as-is

## 🧮 Calculation Examples

### Example 1: Convert USD to THB
```
Amount (USD): 386.13
Manual Rate: 32.10 THB per USD

Amount (THB) = 386.13 ÷ 32.10 = 12,026.65 THB
```

### Example 2: Exchange Rate Difference
```
Auto Rate: 32.45 THB per USD
Manual Rate: 32.10 THB per USD

Using Auto Rate:    386.13 ÷ 32.45 = 11,906.73 THB
Using Manual Rate:  386.13 ÷ 32.10 = 12,026.65 THB
Difference:         12,026.65 - 11,906.73 = 119.92 THB
```

## ✅ Verification Checklist

After deployment, verify:

- [ ] Exchange Rate Information appears for USD PO
- [ ] Shows "From Currency: USD" and "To Currency: THB"
- [ ] Auto Rate displays in format like "32.45" (not "0.030861")
- [ ] Can check "Use Manual Exchange Rate"
- [ ] Can enter manual rate like "32.10"
- [ ] Difference Amount calculates automatically
- [ ] Journal entry preview shows correct amounts
- [ ] Same-currency PO hides Exchange Rate section
- [ ] Amounts convert correctly in journal lines

## 🔄 Backward Compatibility

✅ Fully compatible with existing data:
- No database structure changes
- Only display formatting changed
- Existing records remain valid
- New computed fields don't affect old data

## 📚 Additional Resources

- `EXCHANGE_RATE_IMPLEMENTATION.md` - Detailed documentation
- `test_exchange_rate_implementation.py` - Test calculations
- `EXCHANGE_RATE_CHANGES_SUMMARY.md` - Complete change summary

## 🚀 Deployment

```bash
# Restart Odoo
sudo systemctl restart instance1

# In Odoo UI:
# 1. Go to Apps
# 2. Search "buz_advance_accounting"
# 3. Click Upgrade
# 4. Test with USD Purchase Order
```

## 🐛 Troubleshooting

### Exchange Rate Section Not Showing
- ✅ Verify PO currency ≠ Company currency
- ✅ Check both currencies are configured

### Auto Rate Shows as 1.0
- ✅ Usually means same currency
- ✅ Or exchange rate not configured in Odoo

### Manual Rate Not Applied
- ✅ Check "Use Manual Exchange Rate" checkbox
- ✅ Verify manual rate > 0
- ✅ Rate must be in THB per Unit format

---

**Version:** 17.0.1.0.19  
**Module:** buz_advance_accounting  
**Format:** THB per Unit (YYYY-MM-DD: 2025-11-20)
