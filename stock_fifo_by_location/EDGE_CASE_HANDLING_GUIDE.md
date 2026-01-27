# Edge Case Handling Guide - v17.0.1.1.9

## 🎯 Overview

Version 17.0.1.1.9 introduces comprehensive edge case handling for stock shortage and negative balance scenarios, making the system more user-friendly and production-ready.

## 🚨 Edge Cases Handled

### 1. **Stock Shortage**

#### Problem
User tries to sell/transfer more stock than available at a warehouse.

#### Solution
**Enhanced Error Messages with Suggestions:**
```
❌ สินค้าไม่เพียงพอในคลัง!

สินค้า: [Product Name]
คลัง: WH-A
มีอยู่: 50.00 Unit
ต้องการ: 100.00 Unit
ขาด: 50.00 Unit

💡 คลังอื่นที่มีสินค้า:
   • WH-B: 80.00 Unit
   • WH-C: 30.00 Unit

✅ มีสินค้าเพียงพอในคลังอื่น (รวม 110.00)

🔧 แนะนำ: สร้าง Internal Transfer เพื่อโอนสินค้ามายังคลังนี้
```

**Shortage Resolution Wizard:**
- Interactive wizard แสดง available stock ในคลังอื่น
- เลือกคลังต้นทาง และจำนวนที่จะโอน
- สร้าง internal transfer อัตโนมัติ (one-click)
- รองรับการโอนจากหลายคลังพร้อมกัน

### 2. **Negative Balance**

#### Problem
Operation would cause warehouse stock to go negative.

#### Solution
**Configurable Validation Modes:**

1. **Strict Mode** (Production Recommended)
   - Block operation completely
   - Show detailed error with alternatives
   - Suggest warehouses with stock

2. **Warning Mode** (Development/Troubleshooting)
   - Allow operation but log warning
   - Show notification to user
   - Useful for debugging

3. **Disabled Mode** (Use with Caution)
   - No validation
   - Allow negative balance
   - Not recommended for production

**Enhanced Error Message:**
```
❌ คลัง WH-A จะติดลบ!

สินค้า: [Product Name]
จำนวนคงเหลือปัจจุบัน: 30.00 Unit
พยายามตัดออก: 50.00 Unit
จะเหลือ: -20.00 Unit (ติดลบ!)

⚠️ ไม่สามารถขายหรือโอนสินค้าได้มากกว่าที่มีในคลังนี้

🏭 คลังอื่นที่มีสินค้า:
   • WH-B: 40.00 Unit
   • WH-C: 25.00 Unit

➡️ แนะนำ: โอนสินค้าจากคลังอื่นมายังคลังนี้ก่อน

🔧 วิธีแก้ไข:
   1. ถ้าเป็นการ Return: ตรวจสอบว่า Return ไปคลังที่ถูกต้อง
   2. ถ้าเป็นการขาย: โอนสินค้าจากคลังอื่นมาก่อน
   3. ตรวจสอบว่ามีการรับสินค้าเข้า WH-A ถูกต้อง
   4. ตรวจสอบ Inventory Adjustment ที่อาจทำให้ Stock ลดลง
```

## ⚙️ Configuration

### System Parameters

Go to: **Settings > Technical > Parameters > System Parameters**

Search for: `stock_fifo_by_location`

#### 1. Negative Balance Mode
**Key:** `stock_fifo_by_location.negative_balance_mode`

**Values:**
- `strict` - Block operations (Production recommended) ✅
- `warning` - Allow with warning (Development) ⚠️
- `disabled` - No validation (Not recommended) ❌

**Default:** `warning`

#### 2. Negative Balance Tolerance
**Key:** `stock_fifo_by_location.negative_balance_tolerance`

**Value:** Float (in units)

**Purpose:** Allow small negative values due to rounding errors

**Default:** `0.01` (1/100th of a unit)

**Examples:**
- `0.01` - Allow -0.01 units (recommended)
- `0.001` - Very strict (0.001 units)
- `1.0` - Allow up to -1 unit

#### 3. Auto-Suggest Transfers
**Key:** `stock_fifo_by_location.auto_suggest_transfers`

**Values:** `True` / `False`

**Purpose:** Automatically show transfer suggestions in error messages

**Default:** `True`

#### 4. Max Fallback Warehouses
**Key:** `stock_fifo_by_location.max_fallback_warehouses`

**Value:** Integer

**Purpose:** Maximum number of alternative warehouses to show

**Default:** `5`

## 🧙 Using the Shortage Resolution Wizard

### Manual Launch

1. Go to **Inventory > Products > Products**
2. Select a product
3. Click **Action > Resolve Stock Shortage**
4. Fill in:
   - Destination Warehouse
   - Quantity Needed
5. Wizard shows available stock in other warehouses
6. Select source warehouses and transfer quantities
7. Click **Create Transfer(s)**

### Automatic Launch (Planned Feature)

When shortage is detected during sale/transfer, system can automatically show wizard.

### Programmatic Usage

```python
# Using FIFO Service API
fifo_service = env['fifo.service']

# Check shortage
result = fifo_service.validate_warehouse_availability(
    product, warehouse, quantity, allow_fallback=True
)

if not result['available']:
    print(f"Shortage: {result['shortage']} units")
    print(f"Can fulfill from other warehouses: {result['can_fulfill']}")
    
    for fb in result['fallback_warehouses']:
        wh = env['stock.warehouse'].browse(fb['warehouse_id'])
        print(f"  {wh.name}: {fb['available_qty']} units")

# Auto-create suggested transfer
transfer_result = fifo_service.create_suggested_transfer(
    product, dest_warehouse, quantity
)

if transfer_result['transfer_id']:
    picking = env['stock.picking'].browse(transfer_result['transfer_id'])
    print(f"Created transfer: {picking.name}")
    print(transfer_result['message'])
```

## 📊 Real-World Scenarios

### Scenario 1: Sale Order - Insufficient Stock

**Problem:**
- Customer orders 100 units
- WH-A (sales warehouse) has only 40 units
- WH-B has 80 units

**Flow:**
1. User validates sale order
2. System detects shortage at WH-A
3. Error shown with suggestion: Transfer from WH-B
4. User opens Shortage Wizard
5. Selects WH-B → WH-A, 60 units
6. System creates internal transfer
7. After transfer validated, sale order can proceed

### Scenario 2: Inter-Warehouse Transfer - Negative Balance

**Problem:**
- User tries to transfer 50 units from WH-A to WH-B
- WH-A only has 30 units

**Flow (Strict Mode):**
1. User creates transfer WH-A → WH-B (50 units)
2. System blocks operation
3. Error shows:
   - WH-A has 30 units
   - Need 50 units
   - Shortage: 20 units
4. Suggests: Check other warehouses or purchase

**Flow (Warning Mode):**
1. Same as above but operation allowed
2. Warning logged and shown to user
3. Developer can investigate

### Scenario 3: Return with Negative Balance Risk

**Problem:**
- Product sold from WH-A (30 units)
- Customer returns 50 units (more than sold!)
- This would create accounting issues

**Flow:**
1. System detects return quantity > original sale
2. Warning shown to user
3. User can:
   - Adjust return quantity
   - Create separate receipt for extra units
   - Contact customer about discrepancy

## 🔍 Troubleshooting

### Issue: Too Many "Negative Balance" Warnings

**Cause:** Rounding errors in unit conversions

**Solution:**
Increase tolerance:
```
stock_fifo_by_location.negative_balance_tolerance = 0.1
```

### Issue: Wizard Shows No Alternative Warehouses

**Cause:** Product not available in any other warehouse

**Solution:**
1. Check if product exists in other warehouses
2. Check stock.quant records
3. Consider purchasing or adjusting inventory

### Issue: Auto-Suggest Not Working

**Cause:** Config parameter disabled

**Solution:**
```
stock_fifo_by_location.auto_suggest_transfers = True
```

### Issue: Transfer Creation Fails

**Cause:** Missing picking type for internal transfers

**Solution:**
Check that internal picking type exists for destination warehouse:
```python
env['stock.picking.type'].search([
    ('code', '=', 'internal'),
    ('warehouse_id', '=', warehouse.id)
])
```

## 🎓 Best Practices

### 1. Use Strict Mode in Production
```
negative_balance_mode = strict
```
Prevents data inconsistencies.

### 2. Set Appropriate Tolerance
```
negative_balance_tolerance = 0.01
```
Account for rounding but catch real issues.

### 3. Enable Auto-Suggestions
```
auto_suggest_transfers = True
```
Helps users resolve issues quickly.

### 4. Train Users on Wizard
- Show users how to use Shortage Resolution Wizard
- Document common scenarios
- Create internal procedures

### 5. Monitor Warnings
Even in warning mode, review logs regularly:
```bash
grep "Negative balance warning" odoo.log
```

## 🔒 Security Considerations

### Access Rights
- Shortage wizard: Available to stock users
- Config parameters: Accessible to system admins only
- Transfer creation: Respects normal stock access rules

### Audit Trail
All operations logged:
- Shortage detections
- Transfer suggestions
- Wizard usage
- Config changes

## 📈 Monitoring

### Key Metrics to Track

1. **Shortage Frequency**
   ```sql
   SELECT COUNT(*) FROM ir_logging 
   WHERE name LIKE '%shortage%' 
   AND create_date > NOW() - INTERVAL '7 days';
   ```

2. **Negative Balance Warnings**
   ```sql
   SELECT COUNT(*) FROM ir_logging 
   WHERE message LIKE '%Negative balance warning%'
   AND create_date > NOW() - INTERVAL '7 days';
   ```

3. **Auto-Created Transfers**
   ```sql
   SELECT COUNT(*) FROM stock_picking 
   WHERE origin LIKE '%Shortage Resolution%'
   AND create_date > NOW() - INTERVAL '7 days';
   ```

## 🚀 Future Enhancements

- [ ] Auto-create transfers without wizard (one-click)
- [ ] ML-based warehouse suggestion (predict best source)
- [ ] Batch shortage resolution (multiple products)
- [ ] Integration with purchase planning
- [ ] Email notifications for shortages
- [ ] Dashboard for shortage analytics

---

**Version:** 17.0.1.1.9  
**Last Updated:** 30 พฤศจิกายน 2568  
**Author:** APC Ball
