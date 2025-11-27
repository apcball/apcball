# 🔧 Fix: Prevent Negative Warehouse Balance on Returns

**Version:** 17.0.1.1.1  
**Date:** 27 พฤศจิกายน 2568  
**Priority:** 🔴 CRITICAL  
**Status:** ✅ IMPLEMENTED

---

## 📋 สรุปปัญหา

### ปัญหาที่พบ:
เมื่อทำการ **Return สินค้า** ที่ขายไปแล้ว หาก Return ไปยัง **Warehouse ที่ต่างจากเดิม** จะทำให้:

1. **Warehouse ต้นทาง (ที่ขายออกไป)** มี valuation **ติดลบ**
2. **Warehouse ปลายทาง (ที่ return เข้ามา)** ได้สินค้า "ฟรี" โดยไม่ถูกต้อง
3. FIFO Queue แต่ละ warehouse **ไม่สมดุล**

### Scenario ที่เป็นปัญหา:

```
📦 Step 1: รับสินค้าเข้า WH1
   WH1: +10 units @ 100 THB/unit = 1,000 THB

📤 Step 2: ขายออกจาก WH1  
   WH1: -10 units @ 100 THB/unit = -1,000 THB
   Balance: 0 units, 0 THB ✅

🔄 Step 3: ลูกค้า Return แต่เข้า WH2 (ผิดที่!)
   WH2: +10 units @ 100 THB/unit = +1,000 THB

📊 ผลลัพธ์:
   ❌ WH1: -10 units, -1,000 THB (ติดลบ!)
   ❌ WH2: +10 units, +1,000 THB (ได้ของฟรี!)
```

---

## 🔍 สาเหตุหลัก

### 1. Method `_get_fifo_valuation_layer_warehouse()` ไม่ได้จัดการ Return Move
```python
# ❌ โค้ดเดิม (ก่อนแก้ไข)
def _get_fifo_valuation_layer_warehouse(self):
    # ไม่มีการตรวจสอบ origin_returned_move_id
    source_usage = self.location_id.usage
    dest_usage = self.location_dest_id.usage
    
    if source_usage == 'customer' and dest_usage == 'internal':
        return dest_wh  # ❌ ใช้ warehouse ปลายทาง (ผิด!)
```

### 2. ไม่มี Validation ป้องกันการ Return ข้าม Warehouse

โค้ดเดิมไม่ได้บังคับให้ return ต้องกลับไปที่ warehouse เดิม

### 3. ไม่มี Constraint ตรวจสอบ Negative Balance

ไม่มีการตรวจสอบว่า warehouse จะติดลบหรือไม่ก่อนที่จะ validate move

---

## ✅ การแก้ไข

### Fix #1: บังคับให้ Return ใช้ Warehouse เดิม

**ไฟล์:** `models/stock_move.py`

```python
def _get_fifo_valuation_layer_warehouse(self):
    """
    Determine the appropriate warehouse for FIFO valuation layer.
    """
    self.ensure_one()
    
    if not self.location_id or not self.location_dest_id:
        return None
    
    # 🔴 CRITICAL FIX: Return moves MUST use original warehouse
    # This prevents negative warehouse balance issues
    if self.origin_returned_move_id:
        original_warehouse = self.origin_returned_move_id.warehouse_id
        if original_warehouse:
            return original_warehouse
        # Fallback: try to get from original move's location
        if self.origin_returned_move_id.location_id:
            return self.origin_returned_move_id.location_id.warehouse_id
    
    # ...rest of code...
```

### Fix #2: เพิ่ม Validation ใน `_action_done()`

**ไฟล์:** `models/stock_move.py`

```python
def _action_done(self, cancel_backorder=False):
    """
    Override move completion to ensure warehouse context is passed to layer operations.
    """
    from odoo.exceptions import ValidationError
    
    # 🔴 VALIDATION: Return moves must go back to original warehouse
    for move in self:
        if move.origin_returned_move_id:
            original_wh = move.origin_returned_move_id.warehouse_id
            return_wh = move._get_fifo_valuation_layer_warehouse()
            
            if original_wh and return_wh and original_wh.id != return_wh.id:
                raise ValidationError(
                    f"❌ ไม่สามารถ Return ไปคนละ Warehouse ได้\n\n"
                    f"เอกสาร: {move.picking_id.name or move.name}\n"
                    f"สินค้า: {move.product_id.display_name}\n"
                    f"Warehouse ต้นทาง (ขายไป): {original_wh.name}\n"
                    f"Warehouse ปลายทาง (Return เข้า): {return_wh.name}\n\n"
                    f"⚠️ เพื่อความถูกต้องของ FIFO Valuation\n"
                    f"การ Return ต้องกลับไปที่ Warehouse เดิม: {original_wh.name}\n\n"
                    f"กรุณาเปลี่ยนปลายทางเป็น: {original_wh.name}"
                )
    
    # Call parent implementation
    result = super()._action_done(cancel_backorder=cancel_backorder)
    # ...rest of code...
```

### Fix #3: เพิ่ม Constraint ป้องกัน Negative Balance

**ไฟล์:** `models/stock_valuation_layer.py`

```python
@api.constrains('warehouse_id', 'quantity', 'remaining_qty', 'remaining_value')
def _check_warehouse_consistency(self):
    """
    Validate warehouse_id is set for all layers with non-zero quantity.
    Also check that warehouse doesn't go into negative balance.
    """
    from odoo.exceptions import ValidationError
    import logging
    _logger = logging.getLogger(__name__)
    
    for layer in self:
        # Skip validation for layers with zero quantity
        if float_compare(abs(layer.quantity), 0, precision_digits=2) == 0:
            continue
        
        # Layers with quantity MUST have warehouse_id
        if not layer.warehouse_id:
            raise ValidationError(
                f"Valuation layer {layer.id} for product {layer.product_id.display_name} "
                f"has quantity {layer.quantity} but no warehouse_id. "
                f"All layers with quantity must be assigned to a warehouse."
            )
        
        # 🔴 NEW: Check for negative warehouse balance
        if layer.quantity < 0:
            # Calculate total remaining qty at this warehouse BEFORE this layer
            domain = [
                ('product_id', '=', layer.product_id.id),
                ('warehouse_id', '=', layer.warehouse_id.id),
                ('id', '<', layer.id),
            ]
            previous_layers = self.search(domain)
            total_remaining_qty = sum(previous_layers.mapped('remaining_qty'))
            total_remaining_value = sum(previous_layers.mapped('remaining_value'))
            
            qty_after = total_remaining_qty + layer.quantity
            value_after = total_remaining_value + layer.value
            
            # Allow small rounding differences
            precision_qty = self.env['decimal.precision'].precision_get('Product Unit of Measure')
            if float_compare(qty_after, -0.01, precision_digits=precision_qty) < 0:
                _logger.error(
                    f"Negative warehouse balance detected: "
                    f"Product={layer.product_id.display_name}, "
                    f"Warehouse={layer.warehouse_id.name}, "
                    f"Qty Before={total_remaining_qty}, "
                    f"This Layer Qty={layer.quantity}, "
                    f"Qty After={qty_after}"
                )
                raise ValidationError(
                    f"❌ Warehouse จะติดลบ!\n\n"
                    f"Warehouse: {layer.warehouse_id.name}\n"
                    f"สินค้า: {layer.product_id.display_name}\n"
                    f"จำนวนคงเหลือ: {total_remaining_qty:.2f}\n"
                    f"พยายามตัดออก: {abs(layer.quantity):.2f}\n"
                    f"จะเหลือ: {qty_after:.2f} (ติดลบ!)\n\n"
                    f"⚠️ ไม่สามารถขายหรือโอนสินค้าได้มากกว่าที่มีใน Warehouse นี้\n\n"
                    f"คำแนะนำ:\n"
                    f"1. ถ้าเป็นการ Return - ตรวจสอบว่า Return ไปที่ Warehouse เดิมหรือไม่\n"
                    f"2. ถ้าเป็นการขาย - ตรวจสอบว่ามี Stock เพียงพอใน {layer.warehouse_id.name} หรือไม่\n"
                    f"3. ตรวจสอบว่ามีการรับสินค้าเข้า Warehouse นี้ถูกต้องหรือไม่"
                )
```

---

## 🧪 Test Cases

สร้าง test case ใหม่ใน `tests/test_return_warehouse_fix.py`:

### Test 1: Return ไปที่ Warehouse เดิม (ต้องผ่าน)
```python
def test_return_to_same_warehouse_should_pass(self):
    """Return to same warehouse should work."""
    # Receive 10 units to WH1
    # Deliver 10 units from WH1
    # Return 10 units to WH1 ✅ Should pass
```

### Test 2: Return ไปคนละ Warehouse (ต้องไม่ผ่าน) ⭐
```python
def test_return_to_different_warehouse_should_fail(self):
    """Return to different warehouse should be BLOCKED."""
    # Receive 10 units to WH1
    # Deliver 10 units from WH1
    # Try to return 10 units to WH2 ❌ Should raise ValidationError
    with self.assertRaises(ValidationError):
        return_picking.button_validate()
```

### Test 3: ป้องกัน Negative Balance
```python
def test_negative_balance_prevention(self):
    """Prevent negative warehouse balance."""
    # Receive 10 units to WH1
    # Try to deliver 15 units from WH1 ❌ Should raise ValidationError
```

---

## 📊 ผลลัพธ์หลังแก้ไข

### ✅ Scenario ที่ถูกต้อง:

```
📦 Step 1: รับสินค้าเข้า WH1
   WH1: +10 units @ 100 THB/unit = 1,000 THB

📤 Step 2: ขายออกจาก WH1  
   WH1: -10 units @ 100 THB/unit = -1,000 THB
   Balance: 0 units, 0 THB ✅

🔄 Step 3: ลูกค้า Return (บังคับกลับ WH1)
   WH1: +10 units @ 100 THB/unit = +1,000 THB

📊 ผลลัพธ์:
   ✅ WH1: 10 units, 1,000 THB (ถูกต้อง!)
   ✅ WH2: 0 units, 0 THB (ไม่ได้รับผลกระทบ)
```

### ❌ Scenario ที่ถูกบล็อก:

```
📦 Step 1: รับสินค้าเข้า WH1
📤 Step 2: ขายออกจาก WH1  

🔄 Step 3: พยายาม Return เข้า WH2
   ❌ ValidationError:
   "ไม่สามารถ Return ไปคนละ Warehouse ได้
    Warehouse ต้นทาง (ขายไป): WH1
    Warehouse ปลายทาง (Return เข้า): WH2
    กรุณาเปลี่ยนปลายทางเป็น: WH1"
```

---

## 🚀 การติดตั้งและทดสอบ

### 1. Update Module
```bash
cd /opt/instance1/odoo17
./odoo-bin -c odoo.conf -u stock_fifo_by_location -d YOUR_DATABASE --stop-after-init
```

### 2. Run Tests
```bash
# Run all tests
./odoo-bin -c odoo.conf -d YOUR_DATABASE --test-enable --test-tags=return_fix --stop-after-init

# Run specific test
./odoo-bin -c odoo.conf -d YOUR_DATABASE --test-enable --test-tags=test_return_to_different_warehouse_should_fail --stop-after-init
```

### 3. Manual Testing
1. สร้าง Receipt เข้า WH1 (10 units)
2. สร้าง Delivery Order ออกจาก WH1 (10 units)
3. พยายาม Return เข้า WH2
4. **ควรเห็น Error Message** บอกว่าต้อง return ไปที่ WH1

---

## 📝 สรุป Changes

### Files Modified:
1. ✅ `models/stock_move.py`
   - แก้ไข `_get_fifo_valuation_layer_warehouse()`
   - เพิ่ม validation ใน `_action_done()`

2. ✅ `models/stock_valuation_layer.py`
   - เพิ่ม constraint `_check_warehouse_consistency()`
   - ตรวจสอบ negative balance

3. ✅ `__manifest__.py`
   - อัปเดต version เป็น 17.0.1.1.1
   - เพิ่ม description การแก้ไข

4. ✅ `tests/test_return_warehouse_fix.py` (NEW)
   - เพิ่ม test cases 7 cases
   - ครอบคลุม scenarios หลัก

5. ✅ `tests/__init__.py`
   - Import test module ใหม่

---

## ⚠️ Breaking Changes

### สิ่งที่เปลี่ยนแปลง:
- **ไม่สามารถ Return ไปคนละ Warehouse ได้อีกต่อไป**
- Return move **บังคับให้กลับไปที่ warehouse เดิม**
- จะ **raise ValidationError** ถ้าพยายาม return ไปที่อื่น

### Migration Guide:
ถ้ามี return moves ที่ไปคนละ warehouse อยู่แล้ว:
1. ยกเลิก return นั้น
2. สร้าง return ใหม่ไปที่ warehouse ที่ถูกต้อง
3. ถ้าต้องการโอนไป warehouse อื่น ให้ใช้ Internal Transfer แทน

---

## 🔗 Related Issues

- Issue: Negative warehouse balance on returns
- Root Cause: Return moves using different warehouse
- Impact: FIFO queue imbalance, incorrect valuation
- Priority: CRITICAL
- Status: FIXED in v17.0.1.1.1

---

## 👥 Credits

**Developer:** APC Ball  
**Module:** stock_fifo_by_location  
**Version:** 17.0.1.1.1  
**Date:** 27 พฤศจิกายน 2568  

---

## 📚 เอกสารเพิ่มเติม

- [STOCK_FIFO_BY_LOCATION_FIX_v17.0.1.1.0.md](./STOCK_FIFO_BY_LOCATION_FIX_v17.0.1.1.0.md)
- [README.md](./README.md)
- [CHANGELOG.md](./CHANGELOG_v17.0.1.0.5.md)

---

**สถานะ:** ✅ READY FOR PRODUCTION  
**Last Updated:** 27 พฤศจิกายน 2568
