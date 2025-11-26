# Quick Reference: Inter-Warehouse Transfer Fix v17.0.1.0.5

## 🎯 Problem Fixed
**Inter-warehouse transfers showing 0.00 valuation** - Fixed by removing manual layer creation and using Odoo's standard process with warehouse enhancement.

---

## ✅ What Was Changed

### Files Modified (3)
1. **`models/stock_move.py`** - Removed 97 lines of duplicate layer creation
2. **`models/fifo_service.py`** - Added standard_price fallback logic
3. **`__manifest__.py`** - Version bump and description update

### Files Added (3)
4. **`tests/test_fifo_by_location.py`** - 4 new test cases (~250 lines)
5. **`CHANGELOG_v17.0.1.0.5.md`** - Complete changelog documentation
6. **`verify_fix_v17.0.1.0.5.py`** - Verification script

---

## 🔧 Technical Changes Summary

### Before → After

| Aspect | Before (v17.0.1.0.4) | After (v17.0.1.0.5) |
|--------|---------------------|---------------------|
| Layer Creation | Manual (custom code) | Odoo Standard |
| Inter-WH Transfer Value | Could be 0.00 ❌ | Always has value ✅ |
| Empty Source WH | 0.00 valuation | Uses standard_price |
| Duplicate Layers | Possible (2-4) | Never (exactly 2) |
| Code Size | 487 lines | 390 lines |

### Core Architecture Change
```
OLD: Odoo creates layers → Our code creates layers again → Duplicates/Conflicts
NEW: Odoo creates layers → Our code adds warehouse_id → Clean/Accurate
```

---

## 🧪 How to Test

### Quick Test Commands
```bash
# 1. Check syntax
cd /opt/instance1/odoo17/custom-addons/stock_fifo_by_location
python3 -c "import ast; ast.parse(open('models/stock_move.py').read())"
python3 -c "import ast; ast.parse(open('models/fifo_service.py').read())"
python3 -c "import ast; ast.parse(open('tests/test_fifo_by_location.py').read())"

# 2. Run verification script
cd /opt/instance1/odoo17
python3 odoo-bin shell -d your_database
>>> exec(open('/opt/instance1/odoo17/custom-addons/verify_fix_v17.0.1.0.5.py').read())

# 3. Run unit tests
python3 odoo-bin -d your_database -u stock_fifo_by_location --test-enable --stop-after-init

# 4. Check for 0.00 layers
psql your_database -c "SELECT COUNT(*) FROM stock_valuation_layer WHERE value = 0.0 AND quantity != 0.0;"
```

### Manual Test Scenario
1. Create two warehouses (WH A, WH B)
2. Receive 100 units to WH A at $100/unit
3. Transfer 50 units from WH A to WH B
4. Check valuation layers:
   - Should have exactly 2 layers
   - Negative layer at WH A: -50 @ $100 = -$5,000
   - Positive layer at WH B: +50 @ $100 = +$5,000
   - NO 0.00 values ✅

---

## 🚀 Deployment Steps

### Pre-Deployment
```bash
# 1. Backup database
sudo -u postgres pg_dump your_database > /backup/backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Verify files are updated
cd /opt/instance1/odoo17/custom-addons/stock_fifo_by_location
grep -n "17.0.1.0.5" __manifest__.py  # Should show version
grep -n "_create_inter_warehouse_valuation_layers" models/stock_move.py  # Should return nothing
```

### Deployment
```bash
# Option 1: Via UI (Recommended)
# Apps → stock_fifo_by_location → Upgrade

# Option 2: Via Command Line
sudo systemctl stop odoo17
/opt/odoo17/odoo-bin -c /etc/odoo17.conf -d your_database -u stock_fifo_by_location --stop-after-init
sudo systemctl start odoo17
```

### Post-Deployment Verification
```sql
-- Check for 0.00 layers (should return 0)
SELECT COUNT(*) FROM stock_valuation_layer 
WHERE value = 0.0 AND quantity != 0.0;

-- Check recent transfers
SELECT svl.id, sm.name, svl.warehouse_id, svl.quantity, svl.value
FROM stock_valuation_layer svl
JOIN stock_move sm ON svl.stock_move_id = sm.id
WHERE svl.create_date > NOW() - INTERVAL '1 hour'
ORDER BY svl.create_date DESC;
```

---

## 📊 Expected Results

### Inter-Warehouse Transfer (WH A → WH B: 50 units)

**Before Fix (v17.0.1.0.4):**
```
Layer 1: WH A, -50 units, value: 0.00     ❌ WRONG
Layer 2: WH B, +50 units, value: 0.00     ❌ WRONG
(Possibly Layer 3 & 4 - duplicates)
```

**After Fix (v17.0.1.0.5):**
```
Layer 1: WH A, -50 units, value: -5000.00  ✅ CORRECT
Layer 2: WH B, +50 units, value: +5000.00  ✅ CORRECT
(Exactly 2 layers, no duplicates)
```

---

## 🔍 Troubleshooting

### Issue: Module upgrade fails
```bash
# Check Odoo logs
sudo tail -f /var/log/odoo17/odoo.log

# Retry with fresh restart
sudo systemctl restart odoo17
```

### Issue: Tests fail
```bash
# Run specific test
python3 odoo-bin -d your_database --test-tags=stock_fifo_by_location -i stock_fifo_by_location

# Check test output for details
```

### Issue: Still seeing 0.00 layers
```sql
-- These might be old layers from before the fix
-- Check their creation date
SELECT id, create_date, stock_move_id, quantity, value 
FROM stock_valuation_layer 
WHERE value = 0.0 AND quantity != 0.0
ORDER BY create_date DESC;

-- To fix old layers (BACKUP FIRST!):
UPDATE stock_valuation_layer svl
SET 
  unit_cost = p.standard_price,
  value = svl.quantity * p.standard_price
FROM product_product pp
JOIN product_template p ON pp.product_tmpl_id = p.id
WHERE svl.product_id = pp.id
  AND svl.value = 0.0
  AND svl.quantity != 0.0;
```

---

## 📚 Documentation Files

- **CHANGELOG_v17.0.1.0.5.md** - Complete changelog (this document's parent)
- **WAREHOUSE_0_VALUATION_FIX.md** - Original fix documentation
- **README.md** - Module overview
- **ANALYSIS_STOCK_FIFO_BY_LOCATION.md** - Thai technical analysis

---

## ✅ Success Criteria

After deployment, all should be true:
- ✅ Module version is 17.0.1.0.5
- ✅ No 0.00 valuation layers created (new transfers)
- ✅ Exactly 2 layers per inter-warehouse transfer
- ✅ `warehouse_id` properly set on all layers
- ✅ All unit tests pass
- ✅ No errors in Odoo logs
- ✅ COGS calculations accurate

---

## 🆘 Support

If issues occur:
1. Check logs: `sudo tail -f /var/log/odoo17/odoo.log`
2. Run verification script: `verify_fix_v17.0.1.0.5.py`
3. Review SQL queries above
4. Restore from backup if needed

---

**Version:** 17.0.1.0.5  
**Status:** ✅ Ready for Production  
**Date:** 26 พฤศจิกายน 2568
