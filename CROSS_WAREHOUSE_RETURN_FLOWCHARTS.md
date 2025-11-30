# Cross-Warehouse Return Flow Diagrams
## Version 17.0.1.1.6

## Scenario Overview

```
Timeline: ขายจาก WH-A แต่ลูกค้าคืนของเข้าคลัง WH-B

    Supplier          WH-A (Bangkok)        Customer         WH-B (Chiang Mai)
       │                    │                    │                    │
       │    [1] Receipt     │                    │                    │
       ├───────────────────>│                    │                    │
       │   10 units @ 100   │                    │                    │
       │                    │                    │                    │
       │                    │   [2] Delivery     │                    │
       │                    ├───────────────────>│                    │
       │                    │   10 units @ 100   │                    │
       │                    │                    │                    │
       │                    │                    │   [3] Return       │
       │                    │                    ├───────────────────>│
       │                    │                    │  10 units @ 100    │
       │                    │                    │  (cross-warehouse) │
       │                    │                    │                    │
```

## Detailed Flow

### [1] Receipt to WH-A

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Receive 10 units @ 100 THB/unit to Bangkok WH      │
└─────────────────────────────────────────────────────────────┘

Stock Move:
  location_id: Supplier
  location_dest_id: WH-A/Stock
  quantity: 10
  price_unit: 100

Valuation Layer Created:
┌──────────────────────────────────────┐
│ Layer ID: 1001                       │
│ warehouse_id: WH-A (Bangkok)         │
│ quantity: +10                        │
│ unit_cost: 100                       │
│ value: 1000                          │
│ remaining_qty: 10                    │
└──────────────────────────────────────┘

Result: WH-A มีสต็อก 10 ชิ้น @ 100 บาท
```

### [2] Delivery from WH-A

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 2: Deliver 10 units from Bangkok WH to Customer       │
└─────────────────────────────────────────────────────────────┘

Stock Move:
  location_id: WH-A/Stock
  location_dest_id: Customer
  quantity: 10

FIFO Consumption Process:
┌──────────────────────────────────────┐
│ Find FIFO candidates at WH-A:       │
│ → Layer 1001: 10 units @ 100        │
│                                      │
│ Consume from Layer 1001:             │
│   Take: 10 units @ 100               │
│   Cost: 1000 THB                     │
│                                      │
│ Update Layer 1001:                   │
│   remaining_qty: 10 → 0              │
└──────────────────────────────────────┘

Valuation Layer Created:
┌──────────────────────────────────────┐
│ Layer ID: 1002                       │
│ warehouse_id: WH-A (Bangkok)         │
│ quantity: -10                        │
│ unit_cost: 100 (from FIFO)           │
│ value: -1000                         │
└──────────────────────────────────────┘

Result: WH-A มีสต็อก 0 ชิ้น (ขายหมดแล้ว)
```

### [3] Cross-Warehouse Return to WH-B

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 3: Return 10 units to Chiang Mai WH (Different!)      │
└─────────────────────────────────────────────────────────────┘

Stock Move:
  location_id: Customer
  location_dest_id: WH-B/Stock
  quantity: 10
  origin_returned_move_id: [Move from Step 2]  ← Link to original

┌─────────────────────────────────────────────────────────────┐
│ Cost Calculation Logic (NEW!)                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ 1. Find Original Move (from origin_returned_move_id)       │
│    → Step 2 delivery move                                  │
│                                                             │
│ 2. Get Original Warehouse (where it was sold from)         │
│    → WH-A (Bangkok)                                         │
│                                                             │
│ 3. Find Original Delivery Layer at WH-A                    │
│    → Layer 1002: -10 units @ 100 THB                       │
│                                                             │
│ 4. Extract Unit Cost from Original Layer                   │
│    → unit_cost = 100 THB (includes landed costs if any)    │
│                                                             │
│ 5. Determine Destination Warehouse (where stock returns)   │
│    → WH-B (Chiang Mai)                                      │
│                                                             │
│ 6. Create Return Layers at WH-B with cost from WH-A        │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Valuation Layers Created:

┌──────────────────────────────────────┐
│ Layer ID: 1003 (Negative)            │
│ warehouse_id: WH-B (Chiang Mai) ✅   │
│ quantity: -10                        │
│ unit_cost: 100 (from WH-A!) ✅       │
│ value: -1000                         │
│                                      │
│ Purpose: FIFO accounting entry       │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ Layer ID: 1004 (Positive)            │
│ warehouse_id: WH-B (Chiang Mai) ✅   │
│ quantity: +10                        │
│ unit_cost: 100 (from WH-A!) ✅       │
│ value: 1000                          │
│ remaining_qty: 10                    │
│                                      │
│ Purpose: New FIFO source at WH-B     │
└──────────────────────────────────────┘

Result: WH-B มีสต็อก 10 ชิ้น @ 100 บาท (cost จาก WH-A)
```

## Key Differences: OLD vs NEW

### OLD Behavior (v17.0.1.1.5 and earlier)

```
Return to Different Warehouse:

Customer → WH-B
  ↓
Check origin_returned_move_id
  ↓
Original move was from WH-A
  ↓
Compare: WH-A ≠ WH-B
  ↓
❌ VALIDATION ERROR
  ❌ "Cannot return to different warehouse"
  ❌ Return blocked
```

### NEW Behavior (v17.0.1.1.6)

```
Return to Different Warehouse:

Customer → WH-B
  ↓
Check origin_returned_move_id
  ↓
Original move was from WH-A
  ↓
Get cost from WH-A: 100 THB ←─────────┐
  ↓                                    │
Create layers at WH-B ────────────────┘
  ↓                     (cost from WH-A,
✅ SUCCESS              layer at WH-B)
  ✅ Return processed
  ✅ Correct cost
  ✅ Correct location
```

## Data Structure Comparison

### Warehouse A Status

```
After Receipt (Step 1):
┌─────────────────────────────────────┐
│ WH-A Valuation Layers               │
├─────────────────────────────────────┤
│ Layer 1001: +10 @ 100 (remain: 10) │
└─────────────────────────────────────┘
Stock: 10 units
Value: 1000 THB

After Delivery (Step 2):
┌─────────────────────────────────────┐
│ WH-A Valuation Layers               │
├─────────────────────────────────────┤
│ Layer 1001: +10 @ 100 (remain: 0)  │ ← Consumed
│ Layer 1002: -10 @ 100               │
└─────────────────────────────────────┘
Stock: 0 units
Value: 0 THB

After Return to WH-B (Step 3):
┌─────────────────────────────────────┐
│ WH-A Valuation Layers               │
├─────────────────────────────────────┤
│ Layer 1001: +10 @ 100 (remain: 0)  │
│ Layer 1002: -10 @ 100               │
│                                     │
│ NO NEW LAYERS (return went to WH-B)│
└─────────────────────────────────────┘
Stock: 0 units ← Still 0
Value: 0 THB
```

### Warehouse B Status

```
After Receipt (Step 1):
┌─────────────────────────────────────┐
│ WH-B Valuation Layers               │
├─────────────────────────────────────┤
│ (empty)                             │
└─────────────────────────────────────┘
Stock: 0 units
Value: 0 THB

After Delivery (Step 2):
┌─────────────────────────────────────┐
│ WH-B Valuation Layers               │
├─────────────────────────────────────┤
│ (empty)                             │
└─────────────────────────────────────┘
Stock: 0 units
Value: 0 THB

After Return to WH-B (Step 3):
┌─────────────────────────────────────┐
│ WH-B Valuation Layers               │
├─────────────────────────────────────┤
│ Layer 1003: -10 @ 100               │ ← NEW
│ Layer 1004: +10 @ 100 (remain: 10) │ ← NEW
└─────────────────────────────────────┘
Stock: 10 units ← NEW!
Value: 1000 THB (at cost 100 from WH-A)
```

## Future Sales from WH-B

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 4 (Example): Sell 5 units from WH-B                   │
└─────────────────────────────────────────────────────────────┘

Stock Move:
  location_id: WH-B/Stock
  location_dest_id: Customer
  quantity: 5

FIFO Consumption at WH-B:
┌──────────────────────────────────────┐
│ Find FIFO candidates at WH-B:       │
│ → Layer 1004: 10 units @ 100        │ ← From return!
│                                      │
│ Consume from Layer 1004:             │
│   Take: 5 units @ 100                │
│   Cost: 500 THB                      │
│                                      │
│ Update Layer 1004:                   │
│   remaining_qty: 10 → 5              │
└──────────────────────────────────────┘

New Layer Created:
┌──────────────────────────────────────┐
│ Layer ID: 1005                       │
│ warehouse_id: WH-B (Chiang Mai)      │
│ quantity: -5                         │
│ unit_cost: 100 (from Layer 1004)     │
│ value: -500                          │
└──────────────────────────────────────┘

Final WH-B Status:
┌─────────────────────────────────────┐
│ WH-B Valuation Layers               │
├─────────────────────────────────────┤
│ Layer 1003: -10 @ 100               │
│ Layer 1004: +10 @ 100 (remain: 5)  │ ← Updated
│ Layer 1005: -5 @ 100                │ ← New
└─────────────────────────────────────┘
Stock: 5 units
Value: 500 THB

✅ FIFO works correctly at WH-B!
```

## Summary Diagram

```
┌────────────────────────────────────────────────────────────────┐
│                  Cross-Warehouse Return                        │
│                                                                │
│  Original Sale Warehouse          Return Destination Warehouse│
│  (WH-A: Bangkok)                  (WH-B: Chiang Mai)          │
│                                                                │
│  ┌─────────────┐                  ┌─────────────┐            │
│  │   Layer A   │                  │   Layer B   │            │
│  │  -10 @ 100  │──── Cost ───────>│  +10 @ 100  │            │
│  │ (delivery)  │    Source        │  (return)   │            │
│  └─────────────┘                  └─────────────┘            │
│                                           │                   │
│                                           │ FIFO              │
│                                           ↓ Queue             │
│                                   Future sales use            │
│                                   cost 100 from here          │
│                                                                │
│  Key Points:                                                  │
│  ✅ Cost: From original warehouse (WH-A)                      │
│  ✅ Location: At destination warehouse (WH-B)                 │
│  ✅ FIFO: Independent per warehouse                           │
│  ✅ Deterministic: Always traceable to original transaction   │
└────────────────────────────────────────────────────────────────┘
```

## Implementation Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   stock.move._action_done()                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. parent._action_done()        ← Create standard layers      │
│       ↓                                                         │
│  2. _ensure_inter_warehouse_valuation_layers()                 │
│       ↓                           ← Ensure both layers exist   │
│  3. _update_created_layers_warehouse()                         │
│       │                           ← Set warehouse & cost       │
│       ├── For return moves:                                    │
│       │   ├─ Get original_wh from origin_returned_move_id     │
│       │   ├─ Get FIFO cost from original_wh                   │
│       │   ├─ Set warehouse_id = destination_wh                │
│       │   └─ Set unit_cost = cost from original_wh            │
│       │                                                         │
│       └── For normal moves:                                    │
│           └─ Set warehouse_id based on move direction          │
│                                                                 │
│  4. _allocate_landed_cost_for_inter_warehouse()                │
│       ↓                           ← Handle landed costs        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Version

- Module: `stock_fifo_by_location`
- Version: `17.0.1.1.6`
- Feature: Cross-Warehouse Return Support
- Date: 30 พฤศจิกายน 2568
