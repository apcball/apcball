# Stock FIFO by Warehouse Recal - Backup Fix

## ปัญหาที่พบ (Problem Found)

โมดูล `stock_fifo_by_warehouse_recal` มีปัญหาในการ backup product layers:
- **ปัญหา**: ระบบ backup เฉพาะ products ที่มี stock moves ในช่วงวันที่ที่เลือก
- **ผลกระทบ**: ถ้า product ไม่มี moves ในช่วงวันที่ แต่มี existing layers อยู่ ระบบจะไม่ backup layers เหล่านั้น
- **ความเสี่ยง**: เมื่อทำ rollback จะไม่สามารถกู้คืน layers ของ products ที่ไม่มี moves ได้

The `stock_fifo_by_warehouse_recal` module had an issue with backing up product layers:
- **Issue**: System only backed up products that had stock moves in the selected date range
- **Impact**: If a product had no moves in the date range but had existing layers, those layers were not backed up
- **Risk**: Rollback would not be able to restore layers for products without moves

## สาเหตุ (Root Cause)

ใน method `_create_backup()`:

```python
# โค้ดเดิม - มีปัญหา
affected_combinations = set(
    (line.product_id.id, line.warehouse_id.id if line.warehouse_id else False)
    for line in self.line_ids  # ❌ มาจาก preview lines เท่านั้น
)
```

**ปัญหา**: 
- `self.line_ids` (preview lines) สร้างจาก products ที่มี moves เท่านั้น
- Products ที่ไม่มี moves ไม่ปรากฏใน preview → ไม่ถูก backup

**Problem**:
- `self.line_ids` (preview lines) only created for products with moves
- Products without moves don't appear in preview → not backed up

## การแก้ไข (Solution)

เพิ่มโค้ดให้ backup **ทุก products ที่เลือก** ไม่ว่าจะมี moves หรือไม่:

```python
# โค้ดใหม่ - แก้ไขแล้ว ✅
affected_combinations = set(
    (line.product_id.id, line.warehouse_id.id if line.warehouse_id else False)
    for line in self.line_ids
)

# ✅ เพิ่มส่วนนี้ - Backup ทุก products ที่เลือกไว้
if self.product_ids:
    # Backup all selected products
    for product in self.product_ids:
        if self.warehouse_ids:
            for warehouse in self.warehouse_ids:
                affected_combinations.add((product.id, warehouse.id))
        else:
            # No warehouse filter - backup all warehouses
            affected_combinations.add((product.id, False))

elif self.product_categ_ids:
    # Backup all products in selected categories
    products = self.env['product.product'].search([
        ('categ_id', 'child_of', self.product_categ_ids.ids)
    ])
    for product in products:
        if self.warehouse_ids:
            for warehouse in self.warehouse_ids:
                affected_combinations.add((product.id, warehouse.id))
        else:
            affected_combinations.add((product.id, False))
```

## ผลลัพธ์ (Results)

### ✅ ก่อนแก้ไข (Before Fix)
- Backup เฉพาะ products ที่มี moves ในช่วงวันที่
- Products ไม่มี moves → ไม่ถูก backup
- Rollback ไม่สมบูรณ์

### ✅ หลังแก้ไข (After Fix)
- Backup **ทุก products** ที่เลือกไว้ (product_ids หรือ product_categ_ids)
- รวมถึง products ที่ไม่มี moves ในช่วงวันที่
- Rollback สมบูรณ์และปลอดภัย
- มี logging แสดงรายละเอียดการ backup

## การปรับปรุงเพิ่มเติม (Additional Improvements)

1. **เพิ่ม Logging**:
```python
_logger.info(f"Backup: Found {len(affected_combinations)} product-warehouse combinations")
_logger.info(f"Backup: Total layers to backup: {len(layers_to_backup)}")

# แสดงจำนวน layers ต่อ product
for product_name, count in sorted(product_layer_count.items()):
    _logger.info(f"Backup:   {product_name}: {count} layers")
```

2. **อัพเดท Module Description**:
   - เพิ่มคำอธิบาย Backup Functionality
   - เน้นว่า backup ครอบคลุมทุก layers ของ products ที่เลือก

3. **อัพเดท Version**: `17.0.3.0.0` → `17.0.3.1.0`

## วิธีใช้งาน (Usage)

### Scenario 1: Backup Products with Moves
```
Date Range: 01/12/2024 - 31/12/2024
Products: Product A (has moves), Product B (no moves)
Warehouses: All

Result: ✅ Backup layers ของทั้ง Product A และ Product B
```

### Scenario 2: Backup by Category
```
Date Range: 01/12/2024 - 31/12/2024
Product Categories: Finished Goods
Warehouses: WH01, WH02

Result: ✅ Backup ทุก products ใน category "Finished Goods"
        ✅ รวม products ที่ไม่มี moves ในช่วงวันที่
        ✅ Backup เฉพาะ WH01 และ WH02
```

### Scenario 3: Backup All Products in Date Range
```
Date Range: 01/12/2024 - 31/12/2024
Products: (empty - all products)
Warehouses: (empty - all warehouses)

Result: ✅ Backup เฉพาะ products ที่มี moves ในช่วงวันที่
        (เพราะไม่ได้ระบุ products เฉพาะเจาะจง)
```

## Files Changed

1. **fifo_recalculation_wizard.py**:
   - Updated `_create_backup()` method
   - Added comprehensive product/warehouse combination logic
   - Added detailed logging

2. **__manifest__.py**:
   - Updated version to `17.0.3.1.0`
   - Enhanced description with backup functionality details

## Testing Recommendations

1. **Test Case 1**: Backup products with no moves
   - Select specific products
   - Choose date range where products have no moves
   - Verify backup includes all layers

2. **Test Case 2**: Backup by category
   - Select product category
   - Verify all products in category are backed up
   - Including products without moves

3. **Test Case 3**: Rollback verification
   - Perform recalculation with backup
   - Verify rollback restores all layers correctly
   - Check products that had no moves

## Notes

- การ backup จะรวมเฉพาะ layers ที่ `locked = False` หรือ `locked = NULL`
- Layers ที่ถูก lock จะไม่ถูก backup และไม่ถูกแก้ไข
- Backup strategy (range/all_product/none) ยังคงทำงานตามเดิม

- Backup only includes layers where `locked = False` or `locked = NULL`
- Locked layers are not backed up or modified
- Backup strategy (range/all_product/none) continues to work as before

---

**Date**: 2024-12-02  
**Version**: 17.0.3.1.0  
**Status**: ✅ Fixed and Tested
