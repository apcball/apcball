# 🎨 Visual Flowchart: Cost Allocation Logic

## 📊 Diagram 1: Inter-Warehouse Transfer Flow

```
┌─────────────────────────────────────────────────────────────────┐
│           INTER-WAREHOUSE TRANSFER PROCESS                      │
│           (Transfer 50 units from WH-A to WH-B)                 │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ BEFORE TRANSFER                                                  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ WH-A (Source)                 WH-B (Destination)                │
│ ┌──────────────┐               ┌──────────────┐                │
│ │ 100 units    │               │ 100 units    │                │
│ │ @ 10/unit    │               │ @ 12/unit    │                │
│ │ Value: 1000  │               │ Value: 1200  │                │
│ │ LC: 100      │               │ LC: 50       │                │
│ │ Total: 1100  │               │ Total: 1250  │                │
│ └──────────────┘               └──────────────┘                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                    TRANSFER REQUEST
                         50 units
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: Calculate FIFO Cost from WH-A                           │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Get FIFO queue at WH-A:                                        │
│  ┌─────────────────────────┐                                   │
│  │ Layer 1: 100 @ 10/unit  │ ← Oldest (First-In)             │
│  │ Layer 2: (none)         │                                   │
│  └─────────────────────────┘                                   │
│                                                                  │
│  Consume 50 units from Layer 1:                                 │
│  50 × 10 = 500 (base cost)                                     │
│                                                                  │
│  Get landed cost at WH-A:                                       │
│  Total LC: 100                                                  │
│  Proportion: 50 / 100 = 50%                                    │
│  LC per unit: 100 / 100 = 1/unit                              │
│  50 units × 1 = 50 (landed cost)                              │
│                                                                  │
│  ✅ Total cost from WH-A: 500 + 50 = 550                      │
│  ✅ Unit cost: 550 / 50 = 11/unit                             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2: Create Valuation Layers                                 │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Negative Layer (WH-A outgoing):                                 │
│ ┌────────────────────────┐                                     │
│ │ qty: -50               │                                     │
│ │ unit_cost: 11          │                                     │
│ │ value: -550            │                                     │
│ │ warehouse_id: WH-A     │                                     │
│ └────────────────────────┘                                     │
│                                                                  │
│ Positive Layer (WH-B incoming):                                 │
│ ┌────────────────────────┐                                     │
│ │ qty: +50               │                                     │
│ │ unit_cost: 11          │ ← Same cost as WH-A!              │
│ │ value: +550            │                                     │
│ │ warehouse_id: WH-B     │                                     │
│ └────────────────────────┘                                     │
│                                                                  │
│ These two layers represent the transfer:                         │
│ ✅ Outgoing: WH-A loses 50 units                               │
│ ✅ Incoming: WH-B gains 50 units (same cost)                   │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ STEP 3: Transfer Landed Costs                                   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ WH-A Landed Cost Distribution:                                  │
│ └─ Layer 1: 100 LC for 100 units                               │
│    Allocation: 100 × 50% = 50 LC transferred                   │
│    Remaining: 100 - 50 = 50 LC                                 │
│                                                                  │
│ Transfer Operation:                                             │
│ ┌──────────────────┐         ┌──────────────────┐             │
│ │ WH-A LC: 100     │────→    │ WH-B LC: 50      │             │
│ │    ↓             │  50 LC  │    ↓             │             │
│ │ WH-A LC: 50      │  moved  │ WH-B LC: 100     │             │
│ └──────────────────┘         └──────────────────┘             │
│                                                                  │
│ ✅ Total LC unchanged: 100 + 50 = 50 + 100 = 150             │
│ ✅ Just redistributed between warehouses                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ AFTER TRANSFER                                                   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ WH-A (Source)                 WH-B (Destination)                │
│ ┌──────────────┐               ┌──────────────┐                │
│ │ 50 units     │               │ 150 units    │                │
│ │ @ 10/unit    │               │ Mixed:       │                │
│ │ Value: 500   │               │ • 100@12     │                │
│ │ LC: 50       │               │ • 50@11      │                │
│ │ Total: 550   │               │ Value: 1750  │                │
│ │              │               │ LC: 100      │                │
│ │ Unit Cost:   │               │ Total: 1850  │                │
│ │ 11/unit      │               │              │                │
│ │ (50+50)/50   │               │ Unit Cost:   │                │
│ │              │               │ (1750+100)/150│               │
│ │              │               │ ≈ 12.33/unit │               │
│ └──────────────┘               └──────────────┘                │
│                                                                  │
│ Total Inventory Value: 550 + 1850 = 2400 ✅                   │
│ (Same as before: 1100 + 1250 + transfer neutral)              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Legend:
┌─────┐ = Process box
  ✅  = Correct behavior
  ⚠️  = Warning / Attention needed
  ❌  = Error / Problem
```

---

## 📊 Diagram 2: Return Move Logic (CRITICAL FIX)

```
┌─────────────────────────────────────────────────────────────────┐
│           RETURN MOVE PROCESS (v17.0.1.1.2 FIX)                 │
│           Delivered 100 units, then Return 100 units            │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ ORIGINAL DELIVERY                                                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ WH-A FIFO Queue: [100 @ 10]                                    │
│ Landed Cost: 100 (freight cost)                                │
│ Unit Cost: 10 + (100/100) = 11/unit ✅ With LC!               │
│                                                                  │
│ Delivery Move: -100 @ 11 = -1100                               │
│                                                                  │
│ After Delivery:                                                 │
│ ┌────────────────────────────┐                                 │
│ │ NEGATIVE Layer             │                                 │
│ │ qty: -100                  │                                 │
│ │ unit_cost: 11 ✅ With LC   │                                 │
│ │ value: -1100               │                                 │
│ │ warehouse_id: WH-A         │                                 │
│ │ remaining_qty: 0           │ ← Fully consumed               │
│ │ remaining_value: 0         │                                 │
│ └────────────────────────────┘                                 │
│                                                                  │
│ WH-A Balance: 0 (fully delivered)                              │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
                        CUSTOMER RETURNS
                           ALL 100 UNITS
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ RETURN MOVE CREATION                                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Origin Move Link:                                               │
│ return_move.origin_returned_move_id = original_delivery_move   │
│                                                                  │
│ Return Move Properties:                                         │
│ ┌─────────────────────────────┐                                │
│ │ location_id: Customer       │ ← Returning FROM               │
│ │ location_dest_id: WH-A      │ ← Returning TO original WH     │
│ │ quantity: 100               │                                │
│ │ reason: Return due to...    │                                │
│ └─────────────────────────────┘                                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ STEP 1: Warehouse Validation                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ CHECK: Can return go back to original warehouse?                │
│                                                                  │
│ original_wh = original_delivery_move.warehouse_id = WH-A ✅    │
│ return_wh = determined from return_move locations = WH-A ✅    │
│                                                                  │
│ IF original_wh != return_wh:                                    │
│    RAISE ERROR: ❌ Return must go to original warehouse!        │
│ ELSE:                                                           │
│    CONTINUE ✅                                                  │
│                                                                  │
│ ⚠️  This prevents negative balance issues                       │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ STEP 2: Calculate Return Unit Cost                              │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ ❌ OLD WRONG LOGIC (pre v17.0.1.1.2):                           │
│    return_unit_cost = product.standard_price = 10               │
│    return_value = 100 × 10 = 1000 ❌ No LC!                   │
│    Result: balance ≠ 0 (WRONG!)                               │
│                                                                  │
│ ✅ NEW CORRECT LOGIC (v17.0.1.1.2):                             │
│                                                                  │
│    Step 2a: Find original NEGATIVE layer                       │
│    ┌───────────────────────────┐                               │
│    │ Negative Layer            │                               │
│    │ qty: -100                 │                               │
│    │ unit_cost: 11             │ ← This is the key! ✅         │
│    │ warehouse_id: WH-A        │                               │
│    │ remaining_qty: 0          │                               │
│    └───────────────────────────┘                               │
│                                                                  │
│    Step 2b: Get landed cost from this layer                    │
│    landed_cost_value = 100 (from landed cost allocation)       │
│    quantity = 100                                               │
│    unit_lc = 100 / 100 = 1                                    │
│                                                                  │
│    Step 2c: Calculate total return unit cost                   │
│    return_unit_cost = 11 + 1 = 12 ❌ Wait...                   │
│                                                                  │
│    Actually: return_unit_cost = base_unit_cost + unit_lc       │
│             = 10 + 1 = 11 ✅ Correct!                         │
│             = 11 per unit (same as delivery)                   │
│                                                                  │
│    return_value = 100 × 11 = 1100 ✅ With LC!                │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ STEP 3: Create Return Valuation Layers                          │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ Return layers created (automatically by Odoo):                 │
│                                                                  │
│ Return Positive Layer:                                         │
│ ┌──────────────────────┐                                      │
│ │ qty: +100            │ ← Adding back                        │
│ │ unit_cost: 11 ✅ LC  │ ← Same as delivery layer!            │
│ │ value: +1100         │                                      │
│ │ warehouse_id: WH-A   │ ← Back to original                   │
│ │ remaining_qty: 100   │ ← Still in inventory                 │
│ └──────────────────────┘                                      │
│                                                                  │
│ These are updated by _update_created_layers_warehouse():        │
│ - Set unit_cost to 11 (from delivery layer)                   │
│ - Set warehouse_id to WH-A                                    │
│ - Set value to +1100                                          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────────┐
│ FINAL STATE: BALANCE ZERO ✅                                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│ WH-A FIFO Queue After Return:                                  │
│ ┌────────────────────────────┐                                 │
│ │ Negative Layer (Delivery)  │                                 │
│ │ qty: -100                  │                                 │
│ │ remaining_qty: 0 ← consumed │                               │
│ │ value: -1100               │                                 │
│ │                            │                                 │
│ │ Positive Layer (Return)    │                                 │
│ │ qty: +100                  │                                 │
│ │ remaining_qty: 100 ← back  │                                 │
│ │ value: +1100               │                                 │
│ │                            │                                 │
│ │ TOTAL:                     │                                 │
│ │ qty: 0 ✅                  │                                 │
│ │ value: 0 ✅                │                                 │
│ │ balance: ZERO ✅           │                                 │
│ └────────────────────────────┘                                 │
│                                                                  │
│ ✅ Full return results in balance = 0                          │
│ ✅ Landed costs properly included                              │
│ ✅ No orphaned stock or incorrect valuations                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Key Differences (pre vs post v17.0.1.1.2):
═════════════════════════════════════════════════════════════════

BEFORE (WRONG):
  Delivery Layer: -100 @ 10.00 = -1000
  Return Layer:   +100 @ 10.00 = +1000
  Balance: 0 ✓ (looks right)
  
  BUT: Landed cost (100) is orphaned! 
  Revenue: 1100 (was charged)
  COGS: 1000 (not charged) 
  Landed Cost: 100 (on balance sheet) ❌
  Result: WRONG profit calculation

AFTER (CORRECT v17.0.1.1.2):
  Delivery Layer: -100 @ 11.00 = -1100 (includes LC)
  Return Layer:   +100 @ 11.00 = +1100 (includes LC)
  Balance: 0 ✓
  
  Revenue: 1100
  COGS: 1100 (matches revenue) ✓
  Landed Cost: 0 (properly allocated) ✓
  Result: CORRECT profit = 0 ✓
```

---

## 📊 Diagram 3: Cost Flow Matrix

```
┌─────────────────────────────────────────────────────────────────┐
│          COST ALLOCATION SCENARIOS                              │
└─────────────────────────────────────────────────────────────────┘

SCENARIO 1: Same Warehouse (Intra-warehouse move)
═══════════════════════════════════════════════════════════════════

Location A → Location A within WH-A
┌────────────────────┐       ┌────────────────────┐
│ Before: 100 @ 10   │  ───→ │ After: 100 @ 10    │
│ LC: 100            │       │ LC: 100            │
│ Warehouse: WH-A    │       │ Warehouse: WH-A    │
└────────────────────┘       └────────────────────┘

Result:
✅ Same FIFO queue (no new layers needed for bookkeeping)
✅ Same landed costs
❌ NO cost transfer (same warehouse)
💡 Use: Intra-warehouse transfers, inter-location moves


SCENARIO 2: Inter-Warehouse Transfer (Different warehouse)
═══════════════════════════════════════════════════════════════════

WH-A (100 @ 10, LC 100) → Transfer 50 → WH-B (100 @ 12, LC 50)

┌─────────────────┐                 ┌─────────────────┐
│ WH-A: 100 @ 10  │                 │ WH-B: 100 @ 12  │
│ LC: 100         │  Transfer 50 ───→ │ LC: 50          │
└─────────────────┘      @ 11        └─────────────────┘

Result after transfer:
┌──────────────────┐                 ┌──────────────────┐
│ WH-A: 50 @ 10    │                 │ WH-B:            │
│ LC: 50           │                 │ Layer 1: 100@12  │
│ (NEW) Layer: 50@11 (transferred) │ │ Layer 2: 50@11   │
│       Value transferred: 550     │ │ LC: 100          │
│       LC transferred: 50         │ │ (50 from WH-A)   │
└──────────────────┘                 └──────────────────┘

✅ Different FIFO queues maintained
✅ Cost transferred at FIFO price (11 = 10 + 1 LC)
✅ Landed cost proportionally transferred
✅ Audit trail in stock.landed.cost.allocation
💡 Use: Inter-warehouse transfers, branch-to-branch moves


SCENARIO 3: Return Move (Full return)
═══════════════════════════════════════════════════════════════════

Delivery: 100 units @ 11/unit (10 + 1 LC) → Return 100 units

┌──────────────────┐                 ┌──────────────────┐
│ Delivery Layer:  │                 │ Return Layer:    │
│ qty: -100        │  RETURN MOVE ───→ │ qty: +100        │
│ @: 11/unit ✅ LC │                 │ @: 11/unit ✅ LC │
│ Value: -1100     │                 │ Value: +1100     │
└──────────────────┘                 └──────────────────┘

Result:
Net Balance = -100 + 100 = 0 ✅
Net Value = -1100 + 1100 = 0 ✅

✅ Landed cost included in return
✅ Balance equals zero
✅ No orphaned stock or costs
💡 Use: Customer returns, quality issues, reverse deliveries


SCENARIO 4: Shortage with Fallback Policy
═══════════════════════════════════════════════════════════════════

WH-A: 30 units          WH-B: 50 units          WH-C: 20 units
Demand: 100 units from WH-A

Option 1: ERROR mode (block)
❌ Raise error: Insufficient inventory at WH-A

Option 2: FALLBACK mode (allow)
✅ Use 30 from WH-A (FIFO @ 10)
✅ Fallback to 50 from WH-B (FIFO @ 12)
✅ Fallback to 20 from WH-C (FIFO @ 9)
Cost: 30×10 + 50×12 + 20×9 = 300 + 600 + 180 = 1080

Result:
✅ Fulfills order (100 units)
✅ Uses other warehouse inventory
✅ Respects FIFO within each warehouse
⚠️  Manual review recommended for fallback


COST TRANSFER DIRECTION
═══════════════════════════════════════════════════════════════════

Scenario              | Base Cost | Landed Cost | Unit Cost
───────────────────────────────────────────────────────────────
Intra-warehouse       | —         | —           | —
Inter-warehouse       | Transfers | Transfers   | = WH source
Return (full)         | Reverses  | Reverses    | = Delivery
Return (partial)      | Reverses  | Proportional| = Avg delivery
Shortage (fallback)   | From WH   | From WH     | = WH source
```

---

## 🔄 Diagram 4: Landed Cost Allocation Process

```
┌─────────────────────────────────────────────────────────────────┐
│       LANDED COST ALLOCATION DURING TRANSFER                    │
└─────────────────────────────────────────────────────────────────┘

STEP-BY-STEP PROCESS:

1. TRANSFER REQUEST
   ┌─────────────────────┐
   │ Transfer 50 units   │
   │ From: WH-A          │
   │ To: WH-B            │
   │ Cost: Base 10       │
   └─────────────────────┘

2. CALCULATE SOURCE LC
   ┌─────────────────────┐
   │ WH-A:               │
   │ Available: 100 unit │
   │ Total LC: 100       │
   │ Unit LC: 1/unit     │
   └─────────────────────┘

3. DETERMINE PROPORTION
   ┌─────────────────────┐
   │ Proportion:         │
   │ 50 / 100 = 50%      │
   │ LC to transfer:     │
   │ 100 × 50% = 50      │
   └─────────────────────┘

4. REDUCE SOURCE LC
   ┌─────────────────────┐
   │ WH-A LC before: 100 │
   │ LC to remove:   -50 │
   │ WH-A LC after:   50 │
   └─────────────────────┘
   
5. ADD DESTINATION LC
   ┌─────────────────────┐
   │ WH-B LC before: 50  │
   │ LC to add:     +50  │
   │ WH-B LC after: 100  │
   └─────────────────────┘

6. RECORD AUDIT ENTRY
   ┌──────────────────────────────────┐
   │ stock.landed.cost.allocation     │
   ├──────────────────────────────────┤
   │ move_id: Transfer move           │
   │ source_warehouse: WH-A           │
   │ destination_warehouse: WH-B      │
   │ quantity_transferred: 50         │
   │ lc_before_source: 100            │
   │ lc_after_source: 50              │
   │ lc_before_dest: 50               │
   │ lc_after_dest: 100               │
   │ lc_transferred: 50               │
   │ notes: Auto allocation           │
   └──────────────────────────────────┘

VERIFICATION:
═════════════════════════════════════════════════════════════════

Total LC Before Transfer:  100 (WH-A) + 50 (WH-B)  = 150 ✅
Total LC After Transfer:   50 (WH-A)  + 100 (WH-B) = 150 ✅
Total LC Lost:             0 ✅
Total LC Gained:           0 ✅
Net Balance:               ZERO ✅ (Conservation of LC)
```

---

## 🧪 Diagram 5: Test Case Flow

```
┌─────────────────────────────────────────────────────────────────┐
│    TEST: Return Full Quantity Results in Balance = 0            │
│    (Proves v17.0.1.1.2 fix is working)                          │
└─────────────────────────────────────────────────────────────────┘

Setup Phase:
═════════════════════════════════════════════════════════════════

1. Create Product
   product: "Test Item"
   cost_method: "fifo"
   type: "product"

2. Create Warehouses
   wh_a: "Warehouse A"
   wh_b: "Warehouse B"

3. Receive Inventory to WH-A
   Receipt: 100 units @ 10/unit + LC 100 (freight)
   
   Valuation Layer (Positive):
   ┌────────────────────────────┐
   │ qty: 100                   │
   │ unit_cost: 10 (base)       │
   │ warehouse_id: WH-A         │
   │ landed_cost: 100           │
   │ unit_lc: 1                 │
   │ total_unit_cost: 11 ✅     │
   │ value: 1100                │
   │ remaining_qty: 100         │
   │ remaining_value: 1100      │
   └────────────────────────────┘

Delivery Phase:
═════════════════════════════════════════════════════════════════

4. Deliver 100 units (ALL)
   Delivery Move: 100 units from WH-A to Customer
   
   FIFO Consumption:
   ├─ Layer from step 3: 100 @ 11/unit
   ├─ Qty consumed: 100
   ├─ Cost consumed: 1100
   └─ Remaining: 0
   
   Valuation Layer (Negative):
   ┌────────────────────────────┐
   │ qty: -100                  │
   │ unit_cost: 11 ✅ With LC   │
   │ warehouse_id: WH-A         │
   │ value: -1100               │
   │ remaining_qty: 0 ← Consumed│
   │ remaining_value: 0 ← Gone  │
   └────────────────────────────┘

Return Phase:
═════════════════════════════════════════════════════════════════

5. Customer Returns ALL 100 units
   Return Move: 100 units from Customer back to WH-A
   
   Validation Step:
   ✅ origin_returned_move_id = delivery move
   ✅ original_warehouse = WH-A (where it was delivered from)
   ✅ return_warehouse = WH-A (where it's returning to)
   ✅ Same warehouse → PASS validation
   
   Cost Calculation Step:
   ├─ Find original delivery layer: -100 @ 11 ✅
   ├─ Get unit_cost from delivery layer: 11 ✅
   ├─ Unit cost includes LC: yes ✅
   ├─ Set return unit_cost = 11 ✅
   └─ Return value = 100 × 11 = 1100 ✅
   
   Valuation Layer (Positive Return):
   ┌────────────────────────────┐
   │ qty: +100                  │
   │ unit_cost: 11 ✅ With LC   │
   │ warehouse_id: WH-A         │
   │ value: +1100               │
   │ remaining_qty: 100         │
   │ remaining_value: 1100      │
   └────────────────────────────┘

Assertion Phase:
═════════════════════════════════════════════════════════════════

6. Verify Final Balance = 0

   Negative Layer (Delivery):
   qty: -100
   remaining_qty: 0
   remaining_value: 0
   value: -1100
   
   Positive Layer (Return):
   qty: +100
   remaining_qty: 100
   remaining_value: 1100
   value: +1100
   
   BALANCE CALCULATION:
   ┌─────────────────────────────┐
   │ Total qty: -100 + 100 = 0 ✅ │
   │ Total val: -1100 + 1100 = 0 │
   │ PASS ✅                      │
   └─────────────────────────────┘

7. Verify No Orphaned Costs

   Landed Costs Tracking:
   ├─ Original receipt: LC 100
   ├─ After delivery: LC properly used in COGS
   ├─ After return: LC properly reversed
   └─ Final: LC = 0 (fully accounted) ✅

8. Verify Inventory Accuracy

   WH-A Inventory:
   ├─ Physical: 100 units (returned)
   ├─ FIFO Queue: [100 @ 11]
   ├─ Value: 1100
   ├─ Previous: Same as after receipt
   └─ Status: RESTORED ✅

Test Result: ✅ PASS - Return move correctly handles landed costs
```

---

*Generated: 2024-11-27 - stock_fifo_by_location v17.0.1.1.2*
