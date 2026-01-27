# Edge Case Handling - Quick Reference

## 🚀 Version 17.0.1.1.9 - New Features

### 1. Configurable Negative Balance Validation

**Config Parameter:** `stock_fifo_by_location.negative_balance_mode`

```
strict   → Block operations (Production) ✅
warning  → Allow with warning (Dev) ⚠️
disabled → No validation ❌
```

**Default:** `warning`

### 2. Shortage Resolution Wizard

**Access:** Products > Action > Resolve Stock Shortage

**Features:**
- Shows available stock in other warehouses
- One-click create internal transfers
- Multi-warehouse support
- Auto-confirm option

### 3. Enhanced Error Messages

**Before:**
```
Insufficient quantity at warehouse WH-A
Available: 30, Needed: 50
```

**After:**
```
❌ สินค้าไม่เพียงพอในคลัง!

สินค้า: [Product]
คลัง: WH-A
มีอยู่: 30.00
ต้องการ: 50.00
ขาด: 20.00

💡 คลังอื่นที่มีสินค้า:
   • WH-B: 40.00
   • WH-C: 25.00

✅ มีสินค้าเพียงพอในคลังอื่น (รวม 65.00)
🔧 แนะนำ: สร้าง Internal Transfer
```

### 4. Programmatic API

```python
# Check availability with fallback
fifo_service = env['fifo.service']
result = fifo_service.validate_warehouse_availability(
    product, warehouse, quantity, allow_fallback=True
)

# Auto-create transfer
transfer = fifo_service.create_suggested_transfer(
    product, dest_warehouse, quantity
)
```

## ⚙️ Quick Setup

### 1. Enable Strict Mode (Production)
```
Settings > Technical > System Parameters
Key: stock_fifo_by_location.negative_balance_mode
Value: strict
```

### 2. Set Tolerance
```
Key: stock_fifo_by_location.negative_balance_tolerance
Value: 0.01
```

### 3. Enable Auto-Suggestions
```
Key: stock_fifo_by_location.auto_suggest_transfers
Value: True
```

## 🎯 Common Scenarios

### Scenario 1: Sale with Insufficient Stock
1. Error shown with warehouse suggestions
2. Open Shortage Wizard
3. Select source warehouses
4. Create transfers
5. Validate transfers
6. Complete sale

### Scenario 2: Negative Balance Warning
1. Operation blocked (strict mode)
2. Error shows alternatives
3. Transfer from other warehouse OR
4. Adjust quantity OR
5. Cancel operation

### Scenario 3: Cross-Warehouse Return
1. System checks original warehouse
2. Allows return to different warehouse
3. Cost from original, layer at destination
4. No negative balance issues

## 🔧 Troubleshooting

### Too Many Warnings?
→ Increase tolerance to 0.1

### No Alternatives Shown?
→ Check `auto_suggest_transfers = True`

### Wizard Empty?
→ No stock in other warehouses
→ Consider purchasing

## 📊 Monitoring

```sql
-- Check shortage incidents (last 7 days)
SELECT COUNT(*) FROM ir_logging 
WHERE message LIKE '%shortage%' 
AND create_date > NOW() - INTERVAL '7 days';

-- Check negative balance warnings
SELECT COUNT(*) FROM ir_logging 
WHERE message LIKE '%Negative balance%';
```

## 📖 Full Documentation

See: `EDGE_CASE_HANDLING_GUIDE.md`

---

**Version:** 17.0.1.1.9  
**Quick Reference for Production Use**
