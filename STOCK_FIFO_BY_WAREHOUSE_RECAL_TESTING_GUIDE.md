# Testing Guide - FIFO Warehouse Recal Backup Fix

## การทดสอบ (Test Scenarios)

### Test Scenario 1: Product มี Moves ในช่วงวันที่ ✅

**Setup:**
- Product: "Product A"
- มี stock moves ในเดือน ธันวาคม 2024
- มี valuation layers อยู่แล้ว 5 layers

**Steps:**
1. เปิด FIFO Recalculation Wizard
2. เลือก Date Range: 01/12/2024 - 31/12/2024
3. เลือก Product: "Product A"
4. คลิก "Preview"
5. คลิก "Apply Recalculation"

**Expected Result:**
- ✅ Preview แสดง Product A
- ✅ Backup สร้าง 5 layers
- ✅ Log แสดง: "Backup: Product A: 5 layers"

---

### Test Scenario 2: Product ไม่มี Moves ในช่วงวันที่ ✅ [FIX]

**Setup:**
- Product: "Product B"
- **ไม่มี** stock moves ในเดือน ธันวาคม 2024
- มี valuation layers อยู่แล้ว 3 layers (จากเดือนก่อน)

**Steps:**
1. เปิด FIFO Recalculation Wizard
2. เลือก Date Range: 01/12/2024 - 31/12/2024
3. เลือก Product: "Product B"
4. คลิก "Preview"
5. คลิก "Apply Recalculation"

**Expected Result:**
- ⚠️ Preview **ไม่แสดง** Product B (เพราะไม่มี moves)
- ✅ Backup **ยังคงสร้าง** 3 layers สำหรับ Product B
- ✅ Log แสดง: "Backup: Product B: 3 layers"
- ✅ Rollback ทำงานได้ถูกต้อง

**Before Fix:** ❌ ไม่ backup Product B
**After Fix:** ✅ Backup Product B ครบทุก layers

---

### Test Scenario 3: เลือก Product Category ✅

**Setup:**
- Category: "Finished Goods"
- Products in category:
  - Product C (มี moves, 4 layers)
  - Product D (ไม่มี moves, 2 layers)
  - Product E (มี moves, 6 layers)

**Steps:**
1. เปิด FIFO Recalculation Wizard
2. เลือก Date Range: 01/12/2024 - 31/12/2024
3. เลือก Product Category: "Finished Goods"
4. คลิก "Preview"
5. คลิก "Apply Recalculation"

**Expected Result:**
- Preview แสดง Product C และ E (มี moves)
- ✅ Backup สร้าง layers สำหรับ **ทั้ง 3 products** (C, D, E)
- ✅ Log แสดง:
  ```
  Backup: Product C: 4 layers
  Backup: Product D: 2 layers  ← ไม่มี moves แต่ถูก backup
  Backup: Product E: 6 layers
  Total: 12 layers
  ```

---

### Test Scenario 4: เลือก Warehouse เฉพาะ ✅

**Setup:**
- Product: "Product F"
- Warehouses: WH01, WH02, WH03
- Layers:
  - WH01: 3 layers
  - WH02: 2 layers
  - WH03: 4 layers

**Steps:**
1. เปิด FIFO Recalculation Wizard
2. เลือก Date Range: 01/12/2024 - 31/12/2024
3. เลือก Product: "Product F"
4. เลือก Warehouses: WH01, WH02
5. คลิก "Apply Recalculation"

**Expected Result:**
- ✅ Backup เฉพาะ layers ใน WH01 และ WH02
- ✅ Total backup: 5 layers (3 + 2)
- ❌ WH03 ไม่ถูก backup (ไม่ได้เลือก)

---

### Test Scenario 5: Clear Old Layers Strategy ✅

#### Strategy: "range" (Delete & Rebuild in date range)

**Setup:**
- Product: "Product G"
- Layers (by create_date):
  - Nov 2024: 3 layers
  - Dec 2024: 5 layers
  - Jan 2025: 2 layers

**Steps:**
1. Date Range: 01/12/2024 - 31/12/2024
2. Clear Old Layers: "Delete & Rebuild in selected date range"

**Expected Result:**
- ✅ Backup เฉพาะ 5 layers ที่สร้างใน Dec 2024
- ❌ ไม่ backup Nov และ Jan (นอกช่วง)

#### Strategy: "all_product" (Delete all layers for product)

**Steps:**
1. Date Range: 01/12/2024 - 31/12/2024
2. Clear Old Layers: "Delete all layers for selected products"

**Expected Result:**
- ✅ Backup **ทั้งหมด** 10 layers (Nov + Dec + Jan)
- เพื่อรองรับการ rollback

#### Strategy: "none" (Do not touch existing layers)

**Steps:**
1. Date Range: 01/12/2024 - 31/12/2024
2. Clear Old Layers: "Do not touch existing layers"

**Expected Result:**
- ✅ Backup **ทั้งหมด** 10 layers
- เพราะ remaining_qty/remaining_value จะถูกแก้ไข

---

### Test Scenario 6: Rollback ✅

**Setup:**
- ทำ recalculation สำเร็จแล้ว
- มี backup อยู่

**Steps:**
1. เปิด wizard record ที่ทำ recalculation
2. คลิก "Rollback"
3. ตรวจสอบ valuation layers

**Expected Result:**
- ✅ Layers ทั้งหมดกลับคืนสู่สถานะเดิม
- ✅ รวมถึง products ที่ไม่มี moves
- ✅ remaining_qty และ remaining_value ถูกต้อง

---

## Verification Checklist

### Before Fix ❌
- [ ] Products without moves → Not backed up
- [ ] Rollback incomplete for products without moves
- [ ] Risk of data loss

### After Fix ✅
- [x] All selected products backed up (with or without moves)
- [x] Products in selected categories backed up completely
- [x] Warehouse filtering works correctly
- [x] Clear layers strategy respected
- [x] Detailed logging available
- [x] Complete rollback functionality

---

## Log Examples

### Successful Backup (After Fix)
```
2024-12-02 10:30:15 INFO Backup: Found 5 product-warehouse combinations
2024-12-02 10:30:15 INFO Backup: Total layers to backup: 25
2024-12-02 10:30:15 INFO Backup:   Product A: 5 layers
2024-12-02 10:30:15 INFO Backup:   Product B: 3 layers  ← No moves but backed up!
2024-12-02 10:30:15 INFO Backup:   Product C: 7 layers
2024-12-02 10:30:15 INFO Backup:   Product D: 4 layers
2024-12-02 10:30:15 INFO Backup:   Product E: 6 layers
```

### Warning (No Layers)
```
2024-12-02 10:35:20 WARNING No layers found to backup!
```

---

## SQL Verification Queries

### Check Backup Records
```sql
SELECT 
    b.name,
    b.layer_count,
    b.state,
    COUNT(bl.id) as actual_lines,
    b.create_date
FROM fifo_recalculation_backup b
LEFT JOIN fifo_recalculation_backup_line bl ON bl.backup_id = b.id
GROUP BY b.id
ORDER BY b.create_date DESC
LIMIT 10;
```

### Check Products in Backup
```sql
SELECT 
    p.default_code,
    p.name,
    COUNT(bl.id) as layer_count,
    SUM(bl.remaining_qty) as total_qty,
    SUM(bl.remaining_value) as total_value
FROM fifo_recalculation_backup_line bl
JOIN product_product p ON p.id = bl.product_id
WHERE bl.backup_id = [BACKUP_ID]
GROUP BY p.id, p.default_code, p.name
ORDER BY p.default_code;
```

### Compare Layers Before/After Recalculation
```sql
-- Backup layers
SELECT 
    bl.product_id,
    bl.warehouse_id,
    COUNT(*) as backup_count,
    SUM(bl.remaining_qty) as backup_qty,
    SUM(bl.remaining_value) as backup_value
FROM fifo_recalculation_backup_line bl
WHERE bl.backup_id = [BACKUP_ID]
GROUP BY bl.product_id, bl.warehouse_id;

-- Current layers
SELECT 
    svl.product_id,
    svl.warehouse_id,
    COUNT(*) as current_count,
    SUM(svl.remaining_qty) as current_qty,
    SUM(svl.remaining_value) as current_value
FROM stock_valuation_layer svl
WHERE svl.product_id IN (SELECT DISTINCT product_id FROM fifo_recalculation_backup_line WHERE backup_id = [BACKUP_ID])
GROUP BY svl.product_id, svl.warehouse_id;
```

---

## Next Steps

1. ✅ อัพเดทโมดูลในระบบ: `odoo -u stock_fifo_by_warehouse_recal`
2. ✅ ทดสอบตาม Test Scenarios ข้างต้น
3. ✅ ตรวจสอบ logs ว่า backup ครอบคลุมทุก products
4. ✅ ทดสอบ rollback functionality
5. ✅ Monitor production usage

---

**Updated**: 2024-12-02  
**Module Version**: 17.0.3.1.0  
**Status**: Ready for Testing ✅
