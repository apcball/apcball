# Implementation prompt — `buz_production_planning`: Buy → Blanket Order, plan ↔ document links, friendlier UI

You are implementing a change to the Odoo 17 addon `buz_production_planning`
(repo root: `/Users/apichartball/work/apcball`, one addon per top-level directory).
Read `CLAUDE.md` at the repo root first. Everything below was checked against the
current code and against the live production database on 2026-11-17.

## 0. What the user wants

Today the **Create Documents** wizard turns approved plan suggestions into draft
manufacturing orders (Make) and draft RFQs (Buy). The planner wants:

1. **Buy suggestions create a Blanket Order** (`purchase.requisition`) instead of an RFQ.
   The wizard lets the planner choose Blanket Order or RFQ each time; Blanket Order is the default.
2. **The plan is linked to the documents it opened** (Blanket Orders, MOs, and the POs
   later issued from those Blanket Orders), navigable in both directions.
3. **The screens are easier to use.** The users are production planners and purchasing
   staff, not technical people. They should be able to learn the flow from the screen itself.

## 1. Guardrails

- Odoo 17 API only: `fields.Command`, `invisible=`/`readonly=` expressions (no `attrs`),
  `<tree>` not `<list>`. Odoo 17 has no `env._`; use `from odoo import _`.
- Multi-company: `company_id`, `check_company=True`, `_check_company_auto` as the module already does.
- Source strings in English. Every new or changed string gets a Thai translation in `i18n/th.po`.
- The module's core promise stays: **it never confirms, reserves or moves stock.** It creates
  draft documents only. Do not call `action_in_progress`, `button_confirm`, `action_confirm`.
- Do **not** commit or push. Do **not** touch production (`mog-prod`, `MOG_LIVE`).
- Do **not** change `version` in `__manifest__.py`; ask the user (proposed: `17.0.1.1.0`).
- Do not edit the Gantt assets (`static/src/gantt/*`), `engine/scheduler.py` or `engine/gantt.py`.
- Deploy to DEV only: `bash scripts/deploy.sh dev buz_production_planning`.
- Tests run through the Odoo test runner against the real DEV database (side effects are permanent):
  `ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_production_planning --test-enable --stop-after-init --no-http"`
- Keep the existing code style: batch SQL for history lookups, pylint-odoo disables already at the top of files.

Read these before changing anything:

| File | Why |
|---|---|
| `wizard/plan_create_documents.py` | `_classify`, `_compute_summary`, `_create_documents`, `_po_line_vals`, `_latest_mo_analytics`, `_result_body`, `action_create` |
| `models/plan_suggestion.py` | `production_id`, `purchase_line_id`, states |
| `models/plan_run.py` | state machine, `_compute_counts`, `action_open_*` |
| `models/mrp_production.py` + `views/plan_create_documents_views.xml` | the existing MO → plan smart button; copy this pattern |
| `engine/mrp_netting.py` | `PlanGatherer._receipts`, `_other_plan_drafts`, `_kept` |
| `tests/common.py`, `tests/test_documents.py`, `tests/test_netting.py` | fixtures and existing coverage |
| `manual.md` | Thai user manual to update |

## 2. Facts from production (MOG_LIVE, read-only queries, 2026-11-17)

Design against these, not against a stock Odoo database.

- `purchase_requisition` (17.0.0.1) and `purchase_requisition_stock` are installed. Custom addons
  already extend it: `buz_bo_report_excel`, `buz_po_portal`. `buz_production_planning` is **not**
  installed on prod yet.
- There is exactly one requisition type: id 1 **"Blanket Order"**, `exclusive='multiple'`,
  `quantity_copy='none'`, `line_copy='copy'`. Do not hardcode the id or an XML id; find it by `quantity_copy = 'none'`.
- 239 blanket orders: 193 ongoing, 37 done, 2 draft, 7 cancelled. The number (`BO-YYMMNNNN`,
  sequence `purchase.requisition.blanket.order`) is assigned **on confirmation**; a draft is named `New`.
- 6 vendors in total, 5 of them foreign. Currency: 226 USD, 6 THB.
- 960 lines: 959 have a price, 759 have `analytic_distribution`, 812 have a line `schedule_date`.
  Median 3 lines per order (max 17). Median validity 51 days (ordering date → agreement deadline).
- `picking_type_id` is required on the header. In use: `ST01 -Receipts` (id 287) 106, TS01 `Receipts` (211) 59,
  ST01 `Receipts` (1) 41, RM01 receipts 19. The right one depends on the vendor.
- 176 vendor + product pairs sit in more than one *ongoing* blanket order: old orders are never closed.
  **Hand-made blanket orders must never be counted as supply.**
- Last 90 days: 237 of 923 done POs were issued from a blanket order.
- Analytic is **mandatory on purchase orders** (analytic plans 1 and 2). A PO issued from a blanket
  order copies each line's `analytic_distribution`, so the blanket order line should carry it.
- Of 4,730 active BoM components only 899 have a vendor pricelist and 299 have ever been on a
  blanket order. Many Buy suggestions will have no vendor or no price: report these clearly, never crash.

## 3. Part A — Buy creates a Blanket Order

### Manifest
Add `purchase_requisition` to `depends`.

### Wizard `buz.plan.create.documents.wizard`
- New field `buy_document = Selection([('bo', "Blanket Order"), ('rfq', "Purchase Order (RFQ)")], default='bo', required=True)`,
  shown as a radio.
- `rfq` keeps today's behaviour exactly (existing tests must still pass when they select `rfq`).
- Split the Buy branch of `_create_documents()` into `_create_blanket_orders(buy)` and `_create_rfqs(buy)`.
  Both group by vendor: **one document per vendor per wizard run, always a new document** (never append to an existing one).

### Blanket order header values
| Field | Value |
|---|---|
| `vendor_id` | the suggestion vendor |
| `company_id` | `run.company_id` |
| `type_id` | the type with `quantity_copy = 'none'` (limit 1). None found → `UserError` explaining what to configure |
| `currency_id` | currency of the vendor's latest non-cancelled blanket order → `vendor.property_purchase_currency_id` → company currency |
| `picking_type_id` | from the vendor's latest non-cancelled blanket order → incoming type of `run.warehouse_ids[:1]` → the model default |
| `origin` | `run.name` |
| `user_id` | current user |
| `ordering_date` | today |
| `schedule_date` | earliest `date_need` of its suggestions |
| `date_end` | `run.date_to` at end of day local time, converted to UTC (extend `_local_to_utc` to accept minutes or add a sibling helper) |
| `buz_plan_run_id` | `run.id` (new field, Part B) |

### Blanket order line values (one line per suggestion)
| Field | Value |
|---|---|
| `product_id` | suggestion product |
| `product_uom_id` | `product.uom_po_id or product.uom_id` |
| `product_qty` | suggestion qty converted to that unit (same conversion as `_po_line_vals`) |
| `schedule_date` | `date_need` |
| `price_unit` | 1) `product._select_seller(partner_id=vendor, quantity=qty, date=today, uom_id=uom)` price, 2) latest blanket order line of this vendor + product, 3) latest confirmed PO line of this vendor + product, 4) `0.0` and report "no price". Convert to the blanket order currency when the source currency differs |
| `analytic_distribution` | latest blanket order line of this product that has one → latest PO line of this product that has one → empty and report it. One batch SQL per source, like `_latest_mo_analytics` |

### Behaviour
- The blanket order stays in `draft`. Purchasing reviews, fixes price/analytic and confirms it themselves.
- Create each vendor's order inside `self.env.cr.savepoint()`; a `UserError`/`ValidationError` goes to the
  `blocked` list (same pattern as the MO loop) and the other vendors still get their documents.
- After creation write `requisition_line_id` and `state = 'done'` on each suggestion. Match suggestion ↔ line
  explicitly (create lines with `Command.create` in suggestion order and zip, as the RFQ branch does).
- `_classify()`: a suggestion with `requisition_line_id` counts as "document already created".
  `default_get` must also exclude suggestions that already have a `requisition_line_id`.
- `_compute_summary`, `_result_body` and the notification count blanket orders or RFQs according to `buy_document`.
  A draft blanket order is named `New`, so in the chatter message use record links
  (`record._get_html_link()`), not plain names.
- Access: a **Planning / User** who is not an administrator must be able to create the draft blanket order.
  Check the ACLs of `purchase.requisition` / `purchase.requisition.line` for `purchase.group_purchase_user`
  (already implied by `group_plan_user`); add what is missing in `security/`. Do not use `sudo()` to create documents.

## 4. Part B — Plan ↔ document links

### `buz.plan.suggestion`
- `requisition_line_id`: Many2one `purchase.requisition.line`, readonly, `copy=False`, `check_company=True`, indexed.
- `requisition_id`: related `requisition_line_id.requisition_id`, stored, indexed.
- `purchase_order_id`: related `purchase_line_id.order_id` (RFQ path).
- `document_ref` (Char, computed): what the planner reads in the list, e.g. `WH/MO/00123`, `BO-26110013`,
  `Blanket Order (draft)` while the name is still `New`, `P00456`.
- `document_state` (Selection, computed): `none` / `draft` / `open` / `done` / `cancel`, mapped from the linked document's state.
- `action_open_document()`: opens the linked MO, blanket order or PO form.

### `purchase.requisition` (new `models/purchase_requisition.py`)
- `buz_plan_run_id`: Many2one `buz.plan.run`, stored, indexed, readonly, `copy=False`, `ondelete='set null'`.
- `action_open_buz_plan()` and a stat button "Production Plan" on the blanket order form, visible only when set,
  `groups="buz_production_planning.group_plan_user"` (copy `view_mrp_production_form_buz_plan`).
- Find the correct form view XML id and button box by reading the `purchase_requisition` addon in the Odoo 17 source; do not guess.

### `purchase.order`
- Computed `buz_plan_run_id`: `requisition_id.buz_plan_run_id`, or the run of a suggestion linked through `purchase_line_id`.
- Same stat button on the PO form.

### `buz.plan.run`
- `production_count`, `requisition_count`, `purchase_count` (computed, extend `_compute_counts`).
  Purchase orders = RFQs created directly by the plan **plus** POs whose `requisition_id` is one of the plan's blanket orders.
- `action_open_productions()`, `action_open_requisitions()`, `action_open_purchases()` and stat buttons,
  each hidden when its count is 0.
- Run state rule is unchanged: `confirmed` while open suggestions remain, else `done`.

### Netting: a plan's blanket orders are supply (`engine/mrp_netting.py`)
A blanket order creates no stock move until a PO is issued and confirmed, so without this the next
Compute proposes the same purchase again.

- Supply of a suggestion linked to a blanket order line =
  `max(line.product_qty − line.qty_ordered, 0)` converted to the product's stock unit, while the requisition
  state is not `done`/`cancel` and `date_end` is empty or not in the past. Bucket it by the suggestion's `date_need`.
- `_kept()` (same plan): treat such a suggestion as an open document with that remaining quantity instead of `s.qty`.
- `_other_plan_drafts()` (other plans): add the same rule next to the draft MO / draft RFQ cases.
- **No double counting.** `qty_ordered` counts only confirmed POs, and those already arrive through `_receipts`
  as stock moves with `purchase_line_id`. A draft PO issued from the blanket order is not in `qty_ordered`, so it
  stays inside the blanket order's remaining quantity: count it once, there.
- Blanket orders without `buz_plan_run_id` (made by hand) are **not** counted. See section 2.
- Before coding, confirm in the Odoo 17 source how `qty_ordered` is computed and the exact state keys of `purchase.requisition`.

## 5. Part C — Friendlier UI

Principle: a new user opens a plan and the screen tells them what to do next, in plain words.

### Plan form (`views/plan_run_views.xml`)
- A "next step" banner at the top of the sheet (`alert alert-info`), fed by a computed, translated field
  `next_step_hint`. One sentence per situation, with real numbers, for example:
  - draft: "Step 1 of 4: check the dates and warehouses, then click Compute Plan."
  - computed, suggestions to review: "Step 2 of 4: review 34 suggestions (5 late), then click Create Documents."
  - documents created, nothing scheduled: "Step 3 of 4: 12 manufacturing orders and 3 blanket orders were created. Click Schedule to plan the workorders."
  - scheduled: "Step 4 of 4: check the Gantt, then Apply Schedule."
- Header buttons in flow order with short labels (Compute Plan, Create Documents, Schedule, Open Gantt, Apply Schedule).
  Only the button of the next step is `btn-primary`; the others are secondary.
- Stat buttons: Suggestions, Manufacturing Orders, Blanket Orders, Purchase Orders, Schedule.
- Suggestions tab: add `vendor_id`, `document_ref`, `document_state` (badge); keep it readonly.
- Each technical field (`horizon_weeks`, `forecast_lookback_weeks`, `warehouse_ids`, `picking_type_ids`) gets a short `help`.

### Plan list
- Columns: suggestions waiting for review, late suggestions, documents created. Colour by state.
- Action `help` (empty state): the four steps in short lines.

### Suggestions list and search (`views/plan_suggestion_views.xml`)
- Columns `document_ref` + `document_state` badge, and a row button that calls `action_open_document`
  (hidden when there is no document).
- `level`, `projected_qty`, `onhand_qty`, `incoming_qty`, `demand_qty` become `optional="hide"`.
- Decorations: late = danger, done = success, rejected = muted.
- New filters: "To Review" (proposed; make it the default on the menu action), "No Document Yet", "No Vendor", "Has Document".
  New group-bys: Document Status, Blanket Order.
- Clearer labels: `date_need` → "Needed By", `date_release` → "Order / Start By".

### Suggestion form
- A computed, translated sentence `explanation` at the top, e.g.
  "On hand 120 + incoming 40 − demand 300 = short 140. Suggested: buy 150 (minimum batch)."
- "Documents" group: links to the MO, blanket order and purchase order, plus an Open Document button.

### Create Documents wizard
- `buy_document` radio with one line of explanation under each option (Blanket Order: agreement with the vendor,
  purchasing issues POs from it later; RFQ: one purchase order now).
- Update the info banner text: it currently says only RFQs are created.
- Summary in two blocks: **Will be created** (MO count; blanket order or RFQ count with vendor names) and
  **Needs attention** (no vendor, no production line, no price, no analytic, already has a document), each with
  one sentence on how to fix it.
- After Create: close the wizard, reload the plan form and show the result notification
  (so the new stat buttons and the banner are visible immediately). Type `warning` when something was blocked.

### Translations and manual
- Every new field has `string` and `help`; add all new terms to `i18n/th.po`.
- Update `manual.md` sections 1, 6, 7 and 12: Blanket Order instead of RFQ, the BO/RFQ choice, the link buttons,
  price and analytic on blanket order lines, blanket orders counted as supply.

## 6. Tests

Extend `tests/test_documents.py` and `tests/test_netting.py` (Odoo `TransactionCase`, fixtures in `tests/common.py`).
Existing RFQ tests must select `buy_document='rfq'` and keep passing unchanged otherwise.

Blanket order creation
- Two vendors → two blanket orders, each `draft`, type has `quantity_copy == 'none'`, `origin == run.name`,
  `buz_plan_run_id == run`, lines match suggestions (product, quantity in purchase unit, `schedule_date`).
- Price fallback order: vendor pricelist → latest blanket order line → latest PO line → 0 with "no price" reported.
- Analytic copied from the latest blanket order line of the product; missing analytic is reported, not an error.
- Currency and `picking_type_id` taken from the vendor's latest blanket order when one exists.
- No stock move, no PO, nothing confirmed.
- Suggestion without vendor is skipped and reported. Running the wizard twice creates no duplicate.
- A Planning / User who is not an administrator can create the blanket order.
- One vendor failing validation does not stop the others (`blocked` is reported).

Links
- suggestion → `requisition_line_id` / `requisition_id` / `document_ref` / `document_state`; `action_open_document` returns the right model and id.
- Blanket order → `action_open_buz_plan`. PO issued from the blanket order → `buz_plan_run_id`.
- `production_count`, `requisition_count`, `purchase_count` on the plan.

Netting
- A plan's open blanket order line counts as supply: recompute does not propose the same purchase again (same plan and a second plan).
- A hand-made blanket order (no `buz_plan_run_id`) is not counted.
- After a PO from the blanket order is confirmed, the quantity is counted once (receipt), not twice.
- A blanket order that is done, cancelled or past `date_end` is not counted.

## 7. Verification on DEV

1. `bash scripts/deploy.sh dev buz_production_planning`, then run the test command from section 1. Report the real result, including failures.
2. In the DEV UI as a non-admin planner: create a plan → Compute Plan → review suggestions → Create Documents with
   Blanket Order → open a blanket order from the suggestion row → go back to the plan from the blanket order's
   stat button → Compute Plan again and confirm the same purchase is not proposed twice.
3. Repeat step 2 with RFQ selected and confirm the old behaviour.
4. Check the Thai interface: no untranslated new strings.

## 8. Definition of done

- All tests pass on DEV (existing and new).
- The four checks in section 7 are done and reported.
- Final report: files changed, anything left open, anything in this prompt that turned out to be wrong in the Odoo 17 source.
- Nothing committed, nothing pushed, production untouched, version not bumped.
