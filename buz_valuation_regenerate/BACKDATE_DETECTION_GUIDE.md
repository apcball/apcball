# Back-date Detection Guide - คู่มือการตรวจจับปัญหาจาก Back-dating

## ภาพรวม

การ **back-date** คือการบันทึกธุรกรรมย้อนหลัง ซึ่งอาจทำให้เกิดปัญหากับ Stock Valuation โดยเฉพาะใน FIFO และ AVCO costing methods

## ปัญหาที่เกิดจาก Back-dating

### 1. Cost Calculation ผิดพลาด
- FIFO ใช้ cost จาก lot ที่ผิด
- AVCO คำนวณ average cost ผิด
- Valuation ไม่ตรงกับความเป็นจริง

### 2. วันที่ไม่สอดคล้อง
- SVL create_date ≠ Stock Move date
- Journal Entry date ไม่ตรงกับ move date
- Accounting period ไม่ตรงกัน

### 3. ลำดับการประมวลผลผิด
- Outgoing ก่อน Incoming (แต่ date ตรงกันข้าม)
- Stock negative ชั่วคราว
- Valuation layer sequence ผิด

## กลไกการตรวจจับ (Detection Mechanisms)

### Case 1: Date Mismatch Detection

**เงื่อนไข:**
```python
abs((svl.create_date.date() - stock_move.date).days) > 1
```

**ตัวอย่าง:**
```
Stock Move: Date = 2024-01-01
SVL: Created = 2024-01-15 10:00
Difference: 14 days → ⚠️ Detected!
```

**สาเหตุที่พบบ่อย:**
- แก้ไข date ของ move หลังจากสร้าง SVL แล้ว
- Back-date picking/delivery order
- Import data โดยไม่ระบุ date

**ผลกระทบ:**
- Journal entry date ไม่ตรง
- Report แสดงข้อมูลผิด period
- Reconciliation ทำยาก

---

### Case 2: Order Mismatch Detection

**เงื่อนไข:**
```python
abs(svl_position - move_position) > 3
```

**ตัวอย่าง:**
```
Stock Moves (sorted by date):
1. Move A - 2024-01-01
2. Move B - 2024-01-02
3. Move C - 2024-01-03
4. Move D - 2024-01-04
5. Move E - 2024-01-05

SVLs (sorted by create_date):
1. SVL for Move A
2. SVL for Move B
3. SVL for Move E  ← position 3 but move is at position 5
4. SVL for Move C  ← position 4 but move is at position 3
5. SVL for Move D

Position difference for Move E: |3 - 5| = 2 → OK
Position difference for Move C: |4 - 3| = 1 → OK

But if:
SVL position 1 → Move position 5: |1 - 5| = 4 → ⚠️ Detected!
```

**สาเหตุที่พบบ่อย:**
- Back-date multiple moves
- Batch processing ไม่เรียงลำดับ
- Manual correction of dates

**ผลกระทบ:**
- FIFO/AVCO cost calculation ผิด
- Valuation layer sequence ไม่ถูกต้อง
- Report ไม่สะท้อนความเป็นจริง

---

### Case 3: FIFO Sequence Violation

**เงื่อนไข:**
```python
# For outgoing SVL:
- Find incoming SVLs where:
  - incoming.create_date > outgoing.create_date
  - incoming.move_date < outgoing.move_date
```

**ตัวอย่างที่ผิด:**

```
Timeline:
2024-01-01: Incoming X (100 units @ 100 THB) - created 2024-01-01 10:00
2024-01-05: Outgoing A (50 units) - created 2024-01-05 10:00
            → Uses cost from Incoming X (100 THB)
2024-01-03: Incoming Y (200 units @ 80 THB) - created 2024-01-06 14:00 (back-dated!)

Problem:
- Outgoing A should use cost from Incoming Y (80 THB) first
- But it used cost from Incoming X (100 THB)
- Because Incoming Y was created AFTER Outgoing A processed
```

**ตัวอย่างที่ถูกต้อง:**

```
Timeline:
2024-01-01: Incoming X (100 units @ 100 THB) - created 2024-01-01 10:00
2024-01-03: Incoming Y (200 units @ 80 THB) - created 2024-01-03 10:00
2024-01-05: Outgoing A (50 units) - created 2024-01-05 10:00
            → Uses cost from Incoming X (100 THB) correctly

FIFO Queue before Outgoing A:
1. Incoming X: 100 units @ 100 THB
2. Incoming Y: 200 units @ 80 THB

Outgoing A consumes: 50 units from Incoming X @ 100 THB ✓
```

**สาเหตุที่พบบ่อย:**
- Forgot to record incoming, then back-date it later
- Supplier invoice arrives late, back-date receiving
- Correction of receiving date after sales

**ผลกระทบ:**
- **FIFO cost ผิดพลาดมาก**
- Gross profit calculation ผิด
- Inventory valuation ไม่ถูกต้อง
- Possible negative valuation

---

## ตัวอย่างการใช้งาน

### Scenario 1: Back-dated Purchase

**สถานการณ์:**
1. วันที่ 1 ม.ค.: ขาย Product A 10 units
2. วันที่ 5 ม.ค.: นึกขึ้นได้ว่าลืมบันทึกการรับสินค้า
3. Back-date ใบรับสินค้า เป็นวันที่ 31 ธ.ค.

**ผลกระทบ:**
```
Before back-date:
- Sale on 1 Jan: -10 units @ 0 THB (no stock) → Valuation = 0
  
After back-date:
- Receive on 31 Dec: +10 units @ 100 THB → Valuation = 1,000
- Sale on 1 Jan: -10 units @ ??? THB
  
Problem:
- SVL for Sale was created before SVL for Receive
- Sale used cost = 0 or wrong cost
- Need regeneration!
```

**วิธีแก้:**
1. เปิด Valuation Regenerate Wizard
2. เลือก Location ที่มีปัญหา
3. เปิด "Auto-detect Products with Valuation Issues"
4. กด "Compute Plan"
5. ระบบจะตรวจพบ Product A (FIFO sequence violation)
6. กด "Apply Regeneration" เพื่อแก้ไข

---

### Scenario 2: Multiple Back-dates

**สถานการณ์:**
```
Original:
- 1 Jan: IN-001 (date: 1 Jan, created: 1 Jan)
- 3 Jan: OUT-001 (date: 3 Jan, created: 3 Jan)
- 5 Jan: IN-002 (date: 5 Jan, created: 5 Jan)

Then back-date:
- 7 Jan: IN-003 (date: 2 Jan, created: 7 Jan) ← back-dated!
- 8 Jan: OUT-002 (date: 4 Jan, created: 8 Jan) ← back-dated!

Final sequence by date:
1. IN-001 (1 Jan)
2. IN-003 (2 Jan) ← but created last
3. OUT-001 (3 Jan)
4. OUT-002 (4 Jan) ← but created last
5. IN-002 (5 Jan)

SVL sequence by create_date:
1. IN-001 (created: 1 Jan)
2. OUT-001 (created: 3 Jan)
3. IN-002 (created: 5 Jan)
4. IN-003 (created: 7 Jan) ← position 4 but should be 2
5. OUT-002 (created: 8 Jan) ← position 5 but should be 4
```

**Detection:**
- Position mismatch: |4 - 2| = 2 → OK for IN-003
- Position mismatch: |5 - 4| = 1 → OK for OUT-002
- But cumulative effect may cause cost errors
- FIFO sequence check will catch this!

---

## Best Practices

### 1. ป้องกันการ Back-date
- ✅ บันทึกธุรกรรมตามวันที่จริง
- ✅ ใช้ Accounting Lock Date
- ✅ ตั้ง User Rights ให้เข้มงวด
- ❌ อย่า back-date เว้นแต่จำเป็นจริงๆ

### 2. เมื่อต้อง Back-date
- ✅ Back-date ก่อนมี transactions อื่นเกิดขึ้น
- ✅ Regenerate valuation ทันทีหลัง back-date
- ✅ ตรวจสอบ impact กับ moves อื่นๆ
- ✅ ทำ backup log ก่อนแก้ไข

### 3. การตรวจสอบเป็นระยะ
- ✅ รัน auto-detect ทุกสัปดาห์
- ✅ ตรวจสอบ log messages
- ✅ Review products ที่ถูกตรวจพบ
- ✅ แก้ไขทันทีที่พบปัญหา

### 4. หลังทำ Regeneration
- ✅ ตรวจสอบ valuation ว่าถูกต้อง
- ✅ Reconcile journal entries
- ✅ Compare กับ physical inventory
- ✅ เก็บ backup log ไว้อ้างอิง

---

## Technical Details

### Date Tolerance
```python
# Date mismatch tolerance: 1 day
# เพราะ move อาจถูกสร้างใน day+1 แต่ date = day
# ตัวอย่าง: Move date = 1 Jan, created = 1 Jan 23:59
#          SVL created = 2 Jan 00:01 → diff = 1 day → OK

TOLERANCE_DAYS = 1
```

### Order Position Tolerance
```python
# Position tolerance: 3
# เพราะอาจมี moves หลายตัวในวันเดียวกัน
# ลำดับอาจต่างกันเล็กน้อยแต่ไม่ impact cost

TOLERANCE_POSITIONS = 3
```

### FIFO Sequence Check
```python
# ตรวจทุก outgoing SVL
# เปรียบเทียบกับ incoming SVLs ทั้งหมด
# หา incoming ที่:
#   - created หลัง outgoing
#   - แต่ dated ก่อน outgoing
# → แสดงว่า back-dated หลัง outgoing ประมวลผล
```

---

## Troubleshooting

### Q: ระบบ detect product แต่เมื่อ regenerate แล้วยัง detect อีก
**A:** กรณีนี้อาจเป็น:
1. Product มีปัญหาอื่นที่ regenerate ไม่ได้แก้
2. มีการ back-date ใหม่หลัง regenerate
3. ตรวจสอบ log ว่ามี error อะไร

### Q: Position mismatch แต่ไม่ detect
**A:** เช็คว่า:
1. Difference < 3 positions → ยังไม่ถึง threshold
2. Product ไม่ใช่ FIFO/AVCO → ข้าม check นี้
3. ไม่มี location filter → อาจไม่เจอ moves

### Q: FIFO sequence OK แต่ valuation ยังผิด
**A:** อาจเป็น:
1. Landed cost ยังไม่ apply
2. Manual valuation adjustment
3. Price change ที่ไม่ผ่าน SVL
4. ตรวจสอบ account moves

---

## สรุป

การตรวจจับ back-date issues มี **3 levels**:

1. **Level 1: Date Mismatch** (ง่าย, แจ้งเตือนเร็ว)
   - ตรวจ simple date difference
   - จับได้ส่วนใหญ่

2. **Level 2: Order Mismatch** (ปานกลาง, ละเอียดขึ้น)
   - ตรวจ sequence position
   - จับได้เกือบทั้งหมด

3. **Level 3: FIFO Sequence** (ยาก, ลึกที่สุด)
   - ตรวจ cost flow logic
   - จับได้ทุกกรณีที่มี impact

**Module ตรวจทั้ง 3 levels พร้อมกัน** เพื่อให้มั่นใจว่าไม่มี back-date issue หลุดไป! 🎯

---

## ตัวอย่าง Log Output

```
INFO: Auto-detecting products with valuation issues in 2 location(s)...
INFO: Found 45 products with moves in selected locations

INFO: Product [ABC-001] Widget A: Found 3 SVLs with date mismatch (back-date issue)
INFO: Product [ABC-002] Widget B: Found SVL order mismatch (position 8 vs 2) - possible back-date issue
INFO: Product [ABC-003] Widget C: Found FIFO sequence issue - 2 incoming SVL(s) created later but dated earlier (back-date issue)
INFO: Product [ABC-004] Widget D: Found negative valuation - Qty: 10.0, Value: -5000.0
INFO: Product [ABC-005] Widget E: Skipping - recently processed

INFO: Auto-detection complete: Found 4 products with issues
INFO: Compute Plan: Plan computed: Found 156 SVL(s) and 312 Journal Entry(ies) for 4 product(s).
```

---

**Version:** 1.4.0  
**Date:** October 25, 2024  
**Module:** buz_valuation_regenerate
