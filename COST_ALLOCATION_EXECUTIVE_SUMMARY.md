# 📌 Executive Summary: Cost Allocation & Warehouse Sharing

## TL;DR (Too Long; Didn't Read)

**ก:** แต่ละ warehouse มี FIFO queue แยกเป็นอิสระ ❌ **ไม่แชร์กันโดยตรง**

**ส:** Landed cost ถูกตัดจ่ายตามสัดส่วนเมื่อโอนสินค้า ✅ **มีการแชร์แต่ถูกต้อง**

**ล:** Return move ใช้ cost จากการขายครั้งแรก + landed cost ✅ **ถูกต้องแล้ว**

---

## 🎯 หลักการ 3 ข้อ

### 1️⃣ Warehouse Isolation (แต่ละ warehouse อิสระ)

```
คิดเหมือน: ร้านค้า 3 สาขา แต่ละสาขามีสินค้าเป็นของตัวเอง

WH-A: 100 units @ 10/unit
WH-B: 100 units @ 12/unit
WH-C: 100 units @ 9/unit

→ FIFO Queue WH-A: [100@10] (ไม่เห็น WH-B, WH-C)
→ FIFO Queue WH-B: [100@12] (ไม่เห็น WH-A, WH-C)
→ FIFO Queue WH-C: [100@9]  (ไม่เห็น WH-A, WH-B)

ข้อดี:
✅ แต่ละ warehouse คำนวณ COGS ให้ของตัวเองได้แม่นยำ
✅ ถ้าสาขา A ของแพงกว่า ไม่มีผล COGS ของสาขา B
```

### 2️⃣ Cost Transfer (เมื่อโอนระหว่าง warehouse)

```
การโอน 50 units จาก WH-A ไป WH-B:

WH-A FIFO Queue: [100@10]
           ↓ Consume 50 from queue
Cost/unit: 10 + 1 (freight) = 11

Transfer creates:
  WH-A: -50 @ 11 = -550 (outgoing)
  WH-B: +50 @ 11 = +550 (incoming)

ข้อดี:
✅ Cost ที่จากมาจากการคำนวณ FIFO จริง ของ WH-A
✅ WH-B ได้ inventory ด้วย cost เดียวกับ source
✅ No double-counting
```

### 3️⃣ Landed Cost Sharing (ตัดจ่ายตามสัดส่วน)

```
Transfer scenario:
WH-A: 100 units, Freight Cost: 100

Transfer 50 units to WH-B:
  Proportion: 50/100 = 50%
  LC to transfer: 100 × 50% = 50
  
Result:
  WH-A: Remaining LC = 50
  WH-B: Additional LC = +50
  Total LC: Still 100 ✅ (not duplicated)

ข้อดี:
✅ Freight cost ตามไป (fair allocation)
✅ ไม่มี double-count
✅ Audit trail บันทึกไว้ (transparency)
```

---

## 📊 Visual: Cost Flow

```
┌─────────────────────────────────────────────────────┐
│          INTER-WAREHOUSE TRANSFER                   │
└─────────────────────────────────────────────────────┘

Before:
  WH-A: 100 @ 10 (cost queue isolated) ← Independent
  WH-B: 100 @ 12 (cost queue isolated) ← Independent

Transfer 50 units from A→B:
  
  Step 1: Consume from WH-A FIFO
          50 units @ 11/unit (includes LC)
  
  Step 2: Create layers
          WH-A: -50 @ 11 (outgoing)
          WH-B: +50 @ 11 (incoming, same cost)
  
  Step 3: Transfer LC
          50/100 = 50% of WH-A's LC → WH-B

After:
  WH-A: 50 @ 10 (cost queue still independent)
  WH-B: [Original: 100@12] + [Transferred: 50@11]
  
Total inventory value: UNCHANGED ✅
```

---

## ❓ Common Questions

### Q1: แล้ว warehouse ต่างได้ cost คนละเดือนได้ไหม?

**A:** ได้! และนั่นคือจุดประสงค์:

```
ตัวอย่าง:
Jan: Buy 100 units @ 10/unit → WH-A
Feb: Buy 100 units @ 15/unit → WH-B

Deliver 50 units from WH-A:
  COGS = 50 × 10 = 500 (ราคาสดของ WH-A)
  
Deliver 50 units from WH-B:
  COGS = 50 × 15 = 750 (ราคาสดของ WH-B)

✅ Correct! Each warehouse tracks own cost
```

### Q2: ถ้าต่ละ warehouse เป็นอิสระ ค่า freight ไม่ซ้ำกันไหม?

**A:** ไม่ซ้ำ เพราะมี logic ลด source warehouse:

```
Before transfer:
  WH-A freight: 100
  WH-B freight: 50
  Total: 150

Transfer 50 units (50% ของ WH-A):
  WH-A freight: 100 - 50 = 50 ← REDUCED
  WH-B freight: 50 + 50 = 100 ← ADDED

After:
  WH-A: 50
  WH-B: 100
  Total: 150 ✅ (unchanged, not duplicated)
```

### Q3: Return สินค้า ต้องไปที่ warehouse เดิมไหม?

**A:** ใช่! นี่คือ critical fix (v17.0.1.1.1+):

```
Why?
  Delivery: WH-A → Customer (COGS uses WH-A FIFO)
  Return:   Customer → ??? 
  
  ถ้า Return → WH-B:
    ❌ WH-A FIFO queue ไม่ consistent
    ❌ Might cause negative balance
    ❌ Accounting wrong
  
  ถ้า Return → WH-A (เดิม):
    ✅ FIFO queue consistent
    ✅ Balance = 0 when full return
    ✅ Accounting correct

System blocks: Return → wrong warehouse ✅
```

### Q4: v17.0.1.1.2 fix คืออะไร?

**A:** Return move now uses FIFO cost WITH landed cost:

```
BEFORE (wrong):
  Delivery: -100 @ 10 (no LC) = -1000
  Return:   +100 @ 10 (no LC) = +1000
  Balance: 0 (looks right)
  
  But: Landed cost orphaned (accounting wrong) ❌

AFTER (correct):
  Delivery: -100 @ 11 (with LC) = -1100
  Return:   +100 @ 11 (with LC) = +1100
  Balance: 0 (really right)
  
  And: Landed cost properly tracked ✅
```

---

## 🧪 How to Test (Simple Scenario)

### Scenario: Two Warehouse FIFO Transfer

```
Step 1: Setup
  Product: "Widget"
  WH-A, WH-B
  Cost method: FIFO

Step 2: Receive to WH-A
  Qty: 100 units
  Price: 10/unit
  Freight: 100
  Expected unit cost: 11 (10 + 1)

Step 3: Receive to WH-B
  Qty: 100 units
  Price: 12/unit
  Freight: 50
  Expected unit cost: 12.5 (12 + 0.5)

Step 4: Transfer 50 from A→B
  Expected:
    ✅ WH-A layer: -50 @ 11 = -550
    ✅ WH-B layer: +50 @ 11 = +550
    ✅ WH-A freight: 50 (was 100)
    ✅ WH-B freight: 100 (was 50)

Step 5: Verify FIFO Queue (WH-A after transfer)
  Queue: [50 @ 10] only
  No contamination from WH-B ✅
```

---

## ⚠️ Important: Version Requirements

Ensure you're on **v17.0.1.1.2 or later**:

```
v17.0.1.0.1: Initial per-warehouse FIFO
v17.0.1.1.0: Added validation, enhanced return handling
v17.0.1.1.1: 🔴 Critical: Fixed negative balance on returns
v17.0.1.1.2: 🔴 Critical: Fixed return unit cost (now includes LC)
```

Check current version:
```bash
grep "version" __manifest__.py
# Should show: 17.0.1.1.2+
```

---

## 🔍 Audit Trail (Transparency)

All cost transfers logged in:

```
Model: stock.landed.cost.allocation
Records:
  - Which transfer (move_id)
  - From warehouse → To warehouse
  - Qty transferred
  - LC before/after at each warehouse
  - Amount transferred
  - Timestamp

Use for: Audit, debugging, reporting
```

---

## 📋 Checklist: Proper Configuration

- [ ] Module version ≥ v17.0.1.1.2
- [ ] All warehouses defined
- [ ] All valuation layers have warehouse_id (no NULLs)
- [ ] Return moves have origin_returned_move_id
- [ ] Config: shortage_policy = 'error' or 'fallback' (as needed)
- [ ] Config: enable_validation = 'True'
- [ ] Test transfer between warehouses
- [ ] Verify FIFO queues are separate
- [ ] Check audit trail for transfers
- [ ] Verify balance = 0 for full returns

---

## 🆘 Quick Troubleshooting

| Problem | Likely Cause | Fix |
|---------|-------------|-----|
| Balance not zero after full return | Old v17.0.1.1.1 | Upgrade to v17.0.1.1.2 |
| Negative warehouse balance | Return to wrong warehouse | Block with validation |
| Double-counted freight | Old code | Check v17.0.1.1.0+ |
| FIFO queue mixed between warehouses | Missing warehouse_id in layer | Run migration script |
| Audit trail empty | New data (no transfers yet) | Check after first transfer |

---

## 📚 Related Documents

1. **COST_ALLOCATION_WAREHOUSE_ANALYSIS.md** - Detailed technical analysis
2. **COST_ALLOCATION_VISUAL_FLOWCHARTS.md** - Visual diagrams and flows
3. **COST_ALLOCATION_ISSUES_SOLUTIONS.md** - Problem-solution reference
4. **__manifest__.py** - Version history and features

---

## ✅ Summary

| Aspect | Status | Explanation |
|--------|--------|-------------|
| **Warehouse Isolation** | ✅ Works | Each warehouse FIFO queue is independent |
| **Cost Transfer** | ✅ Works | Transfer uses source warehouse FIFO cost |
| **Landed Cost Sharing** | ✅ Works | Proportional allocation, not duplicated |
| **Return Accuracy** | ✅ Fixed (v17.0.1.1.2) | Uses FIFO cost with LC included |
| **Negative Balance Prevention** | ✅ Fixed (v17.0.1.1.1) | Return validation enforces same warehouse |
| **Audit Trail** | ✅ Available | stock.landed.cost.allocation records all transfers |
| **Data Integrity** | ✅ Enforced | Migration script + validation constraints |

---

*Version: 17.0.1.1.2*  
*Last Updated: 2024-11-27*  
*Status: ✅ All Issues Fixed & Tested*
