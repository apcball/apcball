#  Mode — Full Integration Flow
## MPS → MO → Workorder → Planning Slot → Gantt (Odoo 17 Community)

You are  an Odoo 17 architect.

You already have:
- Module A: `buz_planning`
  - model: `planning.slot`
  - OWL native gantt view (`mog_gantt`)
  - supports group mode: employee / workcenter
  - supports linking to mrp.workorder and project.task

Now you must build:
- Module B: `buz_mps`
  - Master Production Schedule (MPS)
  - generates Manufacturing Orders (MO) and Purchase Orders (PO)

And implement the FULL flow:

> MPS → MO → Workorder → Planning Slot → Gantt

---

# 🎯 Final User Experience (Must Achieve)

1) User opens **MPS**
2) User sets forecast for products per period
3) System computes suggested replenishment
4) User clicks **Generate MO**
5) System creates `mrp.production`
6) Odoo creates `mrp.workorder` records (based on BOM routing)
7) System automatically creates `planning.slot` records for those workorders
8) User opens **Planning Gantt**
9) Workorders appear as slots grouped by workcenter
10) User can drag/resize slots to reschedule workorders
11) Slot changes sync back to workorder planned dates

---

# 🧩 Architecture Rules

## Modules
- `buz_planning` MUST remain generic and not depend on `buz_mps`
- `buz_mps` MAY depend on `buz_planning`
- Do NOT modify Odoo core
- Keep logic in clean services

## Integration layer
Implement integration code in `buz_mps`:
- create slots when MO/workorders created
- sync workorder dates when slot updated

---

# 🧱 Data Model (buz_mps)

### `mps.plan`
- name
- company_id
- warehouse_id
- date_start
- date_end
- bucket_type (day/week/month)
- state (draft/confirmed)

### `mps.plan.line`
- plan_id
- product_id
- route_type (manufacture/buy)
- safety_stock
- lead_time_days
- period_forecast_json (Json)
- period_suggested_json (Json computed)
- period_confirmed_json (Json)
- generated_mo_ids (One2many to mrp.production via link table)
- generated_po_ids (One2many to purchase.order via link table)

---

# 🧠 Planning Engine (MPS)

Compute suggested replenishment per period:
Inputs:
- forecast
- stock on hand
- incoming supply (open PO + open MO)
- outgoing demand (confirmed deliveries)
- safety stock
- lead time

Outputs:
- suggested_qty per period
Rules:
- never negative
- apply safety stock
- lead time shifts suggested earlier

---

# 🏭 MO Generation

When user clicks "Generate MO":
- For each line + period:
  - qty = confirmed_qty if set else suggested_qty
  - if qty <= 0: skip
  - create `mrp.production`:
    - product_id
    - product_qty
    - date_start / date_finished (planned)
    - origin = "MPS: <plan.name>"
    - company_id
    - picking_type_id from warehouse
  - confirm MO (action_confirm) so workorders are created

IMPORTANT:
- Only create MO for products that have a BOM
- If no BOM: show user-friendly error

---

# 🔩 Workorder Extraction

After confirming MO:
- read `mrp.production.workorder_ids`
- for each workorder:
  - compute planned start/end
  - ensure workcenter_id exists
  - create a planning slot linked to that workorder

---

# 🟩 Planning Slot Creation (Integration)

Use model from `buz_planning`:
- `planning.slot`

Create one slot per workorder:
- name = workorder.name
- mrp_workorder_id = workorder.id
- workcenter_id = workorder.workcenter_id.id
- start_datetime = computed start
- end_datetime = start + duration
- slot_type must be computed to `workorder`
- state = confirmed

Duration source:
- workorder.duration_expected (minutes) if available
- fallback: 60 minutes

---

# 🧠 Workorder ↔ Slot Sync

## Rule
When user drags/resizes a slot linked to a workorder:
- update workorder planned dates accordingly

Implementation:
- In `buz_planning` update RPC:
  - detect slot has mrp_workorder_id
  - call a hook method if installed

But since `buz_planning` must not depend on `buz_mps`,
use an extension pattern:

### Option A (recommended)
In `buz_planning`, define a method on slot:
- `_after_slot_write_hook(vals)`
Then `buz_mps` inherits and extends it:
- if mrp_workorder_id: write to workorder

### Option B
Override controller update route in `buz_mps` (less clean)

You MUST implement Option A.

---

# 🧩 Planning Gantt Requirements

In `buz_planning` gantt:
- Workorders must appear in Workcenter mode
- Slot bar click opens mrp.workorder form
- Slot shows badge:
  - MO name (production.name)
  - Workcenter name

---

# 🔐 Security
- `buz_mps` groups:
  - MPS User
  - MPS Manager
- `planning.slot` rights remain in `buz_planning`
- Ensure users with MPS rights can create slots

---

# 📦 Deliverables

You MUST output:
1) Module tree for `buz_mps`
2) All file contents
3) A list of minimal required changes in `buz_planning`
4) Installation steps
5) Manual test checklist

---

# 🧭 Phases

## Phase 0 — buz_mps skeleton
- manifest
- models
- security
- menus

## Phase 1 — MPS engine MVP
- compute suggested
- basic views

## Phase 2 — Generate MO
- button + method
- confirm MO
- link to plan/line

## Phase 3 — Create workorder slots
- after MO confirm, create slots for workorders
- ensure no duplicates

## Phase 4 — Sync slot changes back to workorder
- implement hook pattern (Option A)
- update workorder dates when slot updated

## Phase 5 — Polish
- show links on UI
- show counts of generated MO/slots
- add "Open Planning Gantt" smart button

---

# 🛑 Strict Rules
- No Enterprise code
- No external gantt libraries
- No global refactor
- Must run on Odoo 17 Community
- Every phase must be runnable

---

# 🚀 Start Now
Start Phase 0 immediately:
1) Print module tree
2) Implement skeleton + access rights + menus
3) Provide full code for each file
