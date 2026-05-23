# Stock FIFO by Warehouse — Transfer ≠ Consumption

**Version:** 17.0.2.0.0  
**Author:** APC Ball  
**License:** LGPL-3  
**Dependencies:** stock, stock_account, stock_landed_costs

---

## Concept: Transfer ≠ Consumption

Internal Transfer ไม่ใช่การใช้สินค้าออกจากบริษัท  
มันเป็นแค่การเปลี่ยน physical location / warehouse เท่านั้น  
ดังนั้น **ต้นทุนแม่ (cost origin) ไม่ถูกปิด** เพียงเพราะย้ายคลัง

---

## Architecture: Dual-Quantity Tracking

แต่ละ SVL (Stock Valuation Layer) track 2 ปริมาณ:

| Field | ลดเมื่อ Transfer | ลดเมื่อ External Out |
|-------|:-:|:-:|
| `remaining_qty` (Odoo valuation) | ✅ ลด | ✅ ลด |
| `origin_remaining_qty` (cost origin) | ❌ ไม่ลด | ✅ ลด |

- **`remaining_qty`** = Odoo standard → ลดทุกกรณี → **ไม่เบิ้ล**
- **`origin_remaining_qty`** = ต้นทุนแม่ → ลดเฉพาะ external out → **Transfer ≠ Consumption**

---

## Layer Types

### Cost Layer (ต้นทุนแม่)
- สร้างจาก Receipt (PO, production)
- `origin_remaining_qty` = จำนวนที่ยังไม่ถูกใช้จริง (external out)
- ใช้สำหรับ: landed cost, valuation adjustment, audit trail

### Position Layer (ตำแหน่งคลัง)
- สร้างจาก internal transfer
- `origin_valuation_layer_id` → link กลับไป cost layer
- `is_position_layer = True`
- `remaining_qty` = จำนวนที่อยู่ในคลังนี้ (ใช้เลือก FIFO ได้)
- ไม่ใช่ต้นทุนใหม่ แต่เป็น "ตำแหน่งปัจจุบันของต้นทุนแม่"

---

## Flow Example

```
1. Receipt PO → WH1
   Layer A: remaining_qty=100, origin_remaining_qty=100, unit_cost=100

2. Transfer WH1 → WH2 (60 units)
   Layer A: remaining_qty=40, origin_remaining_qty=100  ← origin ไม่ลด
   Layer B (position@WH2): remaining_qty=60, origin=A

3. Transfer WH1 → WH3 (40 units)
   Layer A: remaining_qty=0, origin_remaining_qty=100  ← origin ยังไม่ลด
   Layer C (position@WH3): remaining_qty=40, origin=A

4. Sale from WH2 (30 units) — External Out
   Layer B: remaining_qty=30, origin=A
   Layer A: origin_remaining_qty=70  ← ลดเฉพาะตอน external out

5. Landed Cost arrives (1 month later)
   → Find Layer A (cost origin)
   → Apply adjustment to A.origin_remaining_value
   → Distribute to current positions (WH2, WH3)
```

---

## Key Rules

| Event | remaining_qty | origin_remaining_qty |
|-------|:-:|:-:|
| Receipt | +qty | +qty |
| Internal Transfer source | -qty | **ไม่ลด** |
| Internal Transfer dest | +qty (position layer) | 0 (link to origin) |
| Sale / Delivery | -qty (FIFO consume) | -qty (trace to origin) |
| Scrap / Inventory Loss | -qty | -qty |
| Production Consume | -qty | -qty |
| Customer Return | +qty | **ไม่ลด** (adds back) |

---

## Landed Cost Flow

เมื่อภาษี/ค่าขนส่งมาทีหลัง (หลัง transfer แล้ว):

1. Landed Cost → หา Cost Layer แม่ (ผ่าน `origin_valuation_layer_id` chain)
2. ถึงของจะกระจายไป WH2/WH3 แล้ว ก็ยัง apply ได้ เพราะ Cost Layer ยังเป็น origin
3. `origin_remaining_value` เพิ่มขึ้นบน origin layer
4. Adjustment กระจายไปตาม position layers ปัจจุบัน (based on remaining_qty)

---

## Models

### stock.valuation.layer (extended)

| Field | Type | Description |
|-------|------|-------------|
| `warehouse_id` | Many2one | Warehouse ปัจจุบันของ layer |
| `origin_valuation_layer_id` | Many2one | Link ไป cost origin layer |
| `source_warehouse_id` | Many2one | Warehouse ต้นทางก่อน transfer |
| `transfer_move_id` | Many2one | Transfer move ที่สร้าง position layer |
| `is_position_layer` | Boolean | True = position layer, False = cost layer |
| `origin_remaining_qty` | Float | Remaining qty on cost origin (ลดเฉพาะ external out) |
| `origin_remaining_value` | Float | Remaining value on cost origin |
| `position_qty_available` | Float (compute) | Available qty at this position |
| `current_origin_unit_cost` | Float (compute) | Unit cost from origin including landed costs |
| `position_valuation` | Float (compute) | Position qty × origin unit cost |

### stock.valuation.layer.landed.cost

Per-warehouse landed cost tracking for each SVL.

---

## Changelog

### 17.0.2.0.0 — Transfer ≠ Consumption Architecture
- **Dual-quantity tracking**: `remaining_qty` (valuation) vs `origin_remaining_qty` (cost origin)
- Internal transfers reduce `remaining_qty` but NOT `origin_remaining_qty`
- External out reduces BOTH `remaining_qty` and `origin_remaining_qty`
- Position layers link to cost origin via `origin_valuation_layer_id`
- Landed cost resolves through origin chain regardless of current warehouse
- **No valuation doubling**: `sum(remaining_value)` remains correct
- Returns also preserve `origin_remaining_qty` (adding stock back, not consuming)
- FIFO cost calculation traces through origin layer for accurate unit cost
- Updated tests: `test_internal_transfer_preserves_origin_remaining_qty`, `test_valuation_not_doubled_after_transfer`, `test_external_out_reduces_origin_remaining_qty`, `test_partial_transfer_origin_tracking`

### 17.0.1.2.8 — Previous stable version
- Per-warehouse FIFO tracking
- Cross-warehouse transfer support
- Landed cost by warehouse
- Concurrency control
- Shortage handling
