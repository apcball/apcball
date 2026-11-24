# Prompt: สร้าง module `buz_production_planning` (Odoo 17 Community, Mogen Co.)

> ผู้รัน: Claude Code ใน repo `apcball` (addon วางแบนที่ root, 1 โฟลเดอร์ = 1 addon)
> ข้อมูลอ้างอิง: snapshot จาก MOG_LIVE (prod) วันที่ 2026-11-16
> อ่าน `CLAUDE.md` และ `SERVER.md` ก่อนเริ่ม

## 1. บทบาทและเป้าหมาย

คุณคือ senior Odoo 17 developer. สร้าง addon ใหม่ชื่อ **`buz_production_planning`** ที่ทำ flow นี้ให้ครบ:

```
Demand (ใบส่งค้าง + safety stock + forecast)
   → คำนวณความต้องการสุทธิ (MRP หลายชั้น)
   → ข้อเสนอ ผลิต/ซื้อ (suggestion)
   → planner อนุมัติ → สร้าง MO draft / PO draft
   → จัดคิว workorder ลง workcenter (finite capacity)
   → Gantt ให้ planner ลากแก้ → Apply ลง workorder จริง
```

ทำไมต้องมี: ปัจจุบันโรงงานผลิต 500–670 MO ต่อเดือน แต่ MO ทุกใบสร้างด้วยมือ ไม่ผูกกับ demand,
workorder ค้าง 1,234 ใบมีวันแผนแค่ 165 ใบ, lead time ในระบบเป็น 0 ทั้งหมด. ฝ่ายวางแผนไม่มีเครื่องมือดูว่า
ต้องผลิตอะไร เมื่อไหร่ และ workcenter ไหนงานล้น.

ผู้ใช้หลัก: ฝ่ายวางแผนการผลิต (5 คนที่สร้าง MO อยู่ทุกวัน) และผู้จัดการโรงงาน.

## 2. กติกาที่ห้ามละเมิด

1. **Prod อ่านอย่างเดียว.** ใช้ได้เฉพาะ `SELECT` ผ่าน psql. ห้าม `UPDATE/DELETE/INSERT`, ห้าม odoo shell ที่เขียนข้อมูล,
   ห้าม deploy prod, ห้าม upgrade module บน prod.
2. **ห้าม commit / push** จนกว่าผู้ใช้สั่ง. ห้าม bump version เอง.
3. **สร้างใหม่ทั้งหมด.** ห้ามแก้ ห้าม depend ห้าม copy จาก `buz_planning`, `buz_mps`, `mogen_sop_*`
   (อยู่ใน repo แต่ไม่ได้ติดตั้งบน prod). ชื่อ model ห้ามชน: ห้ามใช้ `planning.slot`, `mps.plan`, `mps.plan.line`.
4. Module นี้ **ไม่แตะ stock**: ไม่สร้าง/validate stock move, ไม่ reserve, ไม่เขียน quant, ไม่เขียน `stock.valuation.layer`.
   เอกสารที่สร้างได้มีแค่ `mrp.production` สถานะ draft และ `purchase.order` สถานะ draft.
5. Convention ตาม `CLAUDE.md`: Odoo 17 API, `fields.Command`, model namespace `buz.plan.*`, XML ID มี prefix module,
   `company_id` + `_check_company_auto`, `mail.thread` สำหรับ model ที่ต้องมี chatter,
   `security/ir.model.access.csv` + `security/security.xml`.
6. ทดสอบบน DEV เท่านั้น (`bash scripts/deploy.sh dev buz_production_planning`).
   `--test-enable` รันบน DB จริงของ DEV และย้อนไม่ได้: **ขออนุญาตผู้ใช้ก่อนรันทุกครั้ง**.
7. จบแต่ละ phase (ข้อ 7) ให้หยุด รายงานสิ่งที่ทำ สิ่งที่ตรวจแล้ว สิ่งที่ยังไม่ได้ตรวจ แล้วรอผู้ใช้.

## 3. Phase 0: ยืนยันข้อมูล prod ก่อนเขียนโค้ด (read-only)

รันชุด query นี้แล้วเทียบกับ snapshot ในข้อ 4. ถ้าตัวเลขต่างจนกระทบ design
(เช่น มี calendar เพิ่ม, workcenter capacity ไม่ใช่ 1, MO เริ่มมี `origin`) ให้หยุดและรายงานก่อน.

```bash
ssh mog-prod "PW=\$(grep -E '^db_password' /etc/instance1.conf | cut -d= -f2 | tr -d ' '); export PGPASSWORD=\$PW
q(){ echo \"## \$1\"; psql -h localhost -U odoo MOG_LIVE -At -F' | ' -c \"\$2\" | head -\${3:-40}; }
q 'MO by state' \"select state,count(*) from mrp_production group by 1 order by 2 desc\"
q 'MO picking types' \"select pt.id,pt.name->>'en_US',w.code,count(*) from mrp_production p join stock_picking_type pt on pt.id=p.picking_type_id left join stock_warehouse w on w.id=pt.warehouse_id group by 1,2,3 order by 4 desc\"
q 'workcenters' \"select id,name,code,default_capacity,time_efficiency,time_start,time_stop,resource_calendar_id from mrp_workcenter where active order by id\" 60
q 'open WO planned' \"select state,count(*),count(date_start) from mrp_workorder where state in ('pending','waiting','ready','progress') group by 1\"
q 'WO time expected vs actual' \"select wc.name,count(*),round(avg(wo.duration_expected)),round(avg(wo.duration)) from mrp_workorder wo join mrp_workcenter wc on wc.id=wo.workcenter_id where wo.state='done' group by 1 order by 2 desc\" 45
q 'bom' \"select type,count(*) from mrp_bom where active group by 1\"
q 'bom with operations' \"select count(distinct bom_id) from mrp_routing_workcenter where active\"
q 'open delivery demand' \"select to_char(m.date,'YYYY-MM'),m.state,count(*),count(distinct m.product_id),round(sum(m.product_uom_qty)) from stock_move m join stock_picking_type pt on pt.id=m.picking_type_id where pt.code='outgoing' and m.state in ('confirmed','assigned','waiting','partially_available') group by 1,2 order by 1 desc,2\"
q 'lead times' \"select 'supplier delay',delay::text,count(*) from product_supplierinfo group by 2 union all select 'produce_delay',produce_delay::text,count(*) from mrp_bom where active group by 2\"
q 'calendars' \"select id,name,hours_per_day,tz from resource_calendar\"
q 'global leaves' \"select count(*) from resource_calendar_leaves where resource_id is null\"
q 'warehouses' \"select id,code,name from stock_warehouse order by id\"
q 'open PO' \"select state,count(*) from purchase_order where state in ('draft','sent','purchase') group by 1\"
q 'MO origin filled' \"select count(*) filter (where origin is not null), count(*) from mrp_production\"
"
```

อ่าน source ของ Odoo บน prod เพื่อยืนยันพฤติกรรมที่ design นี้พึ่ง (อย่าเดาจากความจำ):
`/opt/instance1/odoo17/addons/mrp/models/mrp_workorder.py` (การเขียน `date_start/date_finished`, `leave_id`, `_plan_workorders`)
และ `mrp_production.py` (`button_plan`, `_plan_workorders`, การ sync วันที่ MO กับ WO).

## 4. Snapshot ข้อมูลจริง MOG_LIVE (2026-11-16)

### องค์กรและปฏิทิน
- บริษัทเดียว (id 1). ยังต้องใส่ `company_id` ตาม convention.
- Calendar เดียว: id 1 "Standard 40 hours/week", 8 ชม./วัน, tz Asia/Bangkok.
- ไม่มีวันหยุดกลาง (`resource_calendar_leaves` ที่ `resource_id is null` = 0 แถว).
- พนักงาน active 110 คน, ไม่มีการผูกพนักงานกับ workcenter. การวางแผนคน/กะอยู่นอกขอบเขต.

### การผลิต
| รายการ | ค่า |
|---|---|
| MO ทั้งหมด | done 3,887 / cancel 507 / confirmed 166 / progress 33 / draft 13 / to_close 4 |
| MO ต่อเดือน (เม.ย.–ต.ค. 2026) | 238, 427, 399, 521, 672, 617, 546 |
| ขนาด MO (qty) | median 5, p90 40, p99 144 |
| MO `origin` | ว่างทุกใบ (ไม่มี link SO→MO, ผลิตเข้า stock) |
| MO เปิดที่ `date_start` เลยมาแล้ว | ทุกใบ (216/216). `date_deadline` กรอกน้อย (MO done ปี 2026: 735 จาก 3,595) → ห้ามพึ่ง deadline อย่างเดียวในการเรียงคิว |
| MO `reservation_state` (confirmed+progress) | confirmed 164 / assigned 35 |

สายผลิตแยกด้วย picking type:

| id | ชื่อ | คลัง | จำนวน MO |
|---|---|---|---|
| 245 | Manufacturing Ceramic | FG10 | 2,419 |
| 246 | Manufacturing La-fur | PD01 | 1,523 |
| 108 | Manufacturing | PD01 | 510 |
| 247 | Manufacturing Stair | PD01 | 112 |
| 248 | Manufacturing PJ | PJ01 | 45 |
| 244 | Manufacturing Bathtub | FG10 | 1 |

### Workcenter และ workorder
- Workcenter 40 ตัว (id 57–96, รหัส PD1-xx = QC/ประกอบสุขภัณฑ์, PD2-xx = เฟอร์นิเจอร์/บันได).
  ทุกตัว: `default_capacity` 1, `time_efficiency` 100, `time_start`/`time_stop` 0, calendar id 1.
- Workorder: done 9,859 / cancel 1,785 / pending 1,035 / waiting 164 / ready 29 / progress 6.
  WO เปิด 1,234 ใบ มี `date_start` แค่ 165.
- จำนวน WO ต่อ MO: 1 ใบ = 1,640 MO, 7–8 ใบ = 1,198 MO (สายเฟอร์นิเจอร์), 3 ใบ = 200 MO.
  MO ประมาณ 30% **ไม่มี WO เลย** (BOM ไม่มี operations).
- Operation (`mrp.routing.workcenter`): 3,468 แถว, `time_mode` = manual ทั้งหมด, เฉลี่ย 13 นาที/รอบ.
- เวลาจริงต่ำกว่า expected มากในสายเฟอร์นิเจอร์ (นาที, expected → จริง):
  ตัด 1: 151 → 71, ปิดขอบตรง 1: 144 → 86, เจาะ CNC: 102 → 56, ประกอบเฟอร์: 183 → 103, Pack: 46 → 25.
  สาย QC ใกล้เคียงกัน (QC ประกอบโถ: 83 → 84). มีตัวที่จริงมากกว่า expected (ประกอบ บันได: 327 → 458).
- `mrp_workcenter_productivity`: 16,410 แถว ตั้งแต่ 2026-02-23.

### BOM และ route
- BOM active: normal 2,685 (2,526 template) / phantom 1,660 / unbuild-type 174. มี operations 1,074 BOM.
- Route บนสินค้า: Buy 16,246 / Manufacture 577. อย่าเชื่อ route อย่างเดียวในการตัดสิน make/buy.
- Lead time ในระบบใช้ไม่ได้: `mrp_bom.produce_delay` = 0 ทุกใบ, `product_supplierinfo.delay` = 0 (1,585) หรือ 1 (780),
  `sale_delay` = 0 ทุกสินค้า.
- Orderpoint: 184 ตัว, `trigger` = manual ทั้งหมด. ไม่ใช้เป็นแหล่ง safety stock อัตโนมัติ (ให้ปุ่ม import ค่า min เป็นค่าเริ่มต้นได้).

### Demand
- **แหล่ง demand ที่เชื่อได้ = `stock.move` ของ picking type `code = 'outgoing'`** ที่ state อยู่ใน
  `confirmed / waiting / partially_available / assigned`: ประมาณ 1,600 แถว.
  พ.ย. 2026: 693 แถว, ต.ค.: 356, ย้อนหลังไปถึง ธ.ค. 2025 (ค้างเกินกำหนด).
- **ห้ามใช้ `sale.order.line` เป็น demand**: บรรทัดค้างส่ง 16,493 แต่ 15,142 ไม่มี stock move เปิด
  (มัดจำ `9Deposit+`, บริการ, SO เก่าก่อน go-live). ยอดรวมเพี้ยนเป็นล้านหน่วย.
- สินค้าที่มี BOM normal และมีการส่งออกจริงใน 90 วัน: 700 ตัว.
- ข้อมูลก่อน **2026-04-01** ไม่น่าเชื่อถือ (cut-off 31/03/2026, มีการ reset FIFO). ประวัติทุกอย่างใช้ตั้งแต่ 2026-04-01.

### Supply
- คลัง 27 แห่ง. ไม่ใช่ทุกคลังที่เป็นของพร้อมใช้:
  FG10/FG20 (สำเร็จรูป), RM01/RM02 (วัตถุดิบ), SM01 (กึ่งสำเร็จรูป), PD01 (ผลิต), PJ01 (โครงการ) เป็นกลุ่มใช้งานหลัก.
  FG40 (NC), FG50 (ชำรุด), DS01 (dead stock), RM11/RM12 (รอเคลม), FG30 (โชว์), FG60 (เคลมต่างรุ่น), SP01 (ตัวอย่าง),
  OT01 (outlet), AS01 (ทรัพย์สิน), ST0x (สิ้นเปลือง) ไม่ควรนับเป็น supply.
  → ให้ planner เลือกชุดคลังต่อแผน, ค่าเริ่มต้นเก็บใน settings.
- PO เปิด: draft 70 / sent 1 / purchase 41. MO เปิดเป็น supply ของสินค้าสำเร็จรูป/กึ่งสำเร็จรูป.
- Component ที่ MO เปิดยังต้องใช้ (raw move ไม่ done): confirmed 1,673 / assigned 1,214 / partially_available 137.

### Module บน prod ที่ต้องอยู่ร่วมกันได้
`buz_mrp_stock_request` (flow เบิกวัตถุดิบเข้า MO: อย่า reserve แทนมัน), `buz_stock_reservation_guard`,
`stock_fifo_by_location` (negative balance = strict, บล็อก move ที่ทำให้ติดลบ), `buz_mrp_backdate`,
`buz_mrp_cost_share_guard`, `mrp_import_engine` (เพิ่ม field `external_ref`, `batch_id`, `import_session_id` บน MO).
อ่าน override ของ `mrp.production.create/write` ใน module เหล่านี้ก่อนเขียน wizard สร้าง MO.

## 5. Design

### 5.1 Manifest
- name: `buz_production_planning`, version `17.0.1.0.0`, category Manufacturing, license LGPL-3, `application: True`
- depends: `mrp`, `purchase_stock`, `sale_stock`, `stock`, `mail`
- ไม่มี external python dependency

### 5.2 Models

**`buz.plan.product.param`** — พารามิเตอร์วางแผนต่อสินค้า (unique ต่อ product + company)
- `product_id`, `company_id`
- `safety_stock` (qty), `min_batch_qty`, `batch_multiple`
- `lead_time_make_days`, `lead_time_buy_days`
- `supply_method`: `auto` / `make` / `buy` / `none` (none = ไม่วางแผนสินค้านี้)
- `picking_type_id` (สายผลิต, domain code = mrp_operation)
- `vendor_id` (override vendor หลัก)
- `forecast_method`: `avg` / `manual` / `none`
- Action "คำนวณค่าเริ่มต้นจากประวัติ" (ทำงานกับ selection):
  lead time ผลิต = median ของ (`date_finished − date_start`) ของ MO done ตั้งแต่ 2026-04-01 (ตัดค่าติดลบและ outlier);
  lead time ซื้อ = median ของ (วันรับจริง − `date_approve`) จาก PO → incoming move done;
  `picking_type_id` = ของ MO ล่าสุดของสินค้านั้น; `min_batch_qty` = median ขนาด MO.
  สินค้าที่ไม่มีประวัติใช้ค่า default จาก settings.

**`buz.plan.run`** — หัวแผน (`mail.thread`, sequence `PLAN/2026/0001`)
- `name`, `company_id`, `user_id`, `date_from` (default วันนี้), `horizon_weeks` (default 8), bucket = สัปดาห์ (จันทร์–อาทิตย์)
- `warehouse_ids` (m2m, คลังที่นับเป็น supply), `picking_type_ids` (m2m, จำกัดสายผลิต; ว่าง = ทั้งหมด)
- `forecast_lookback_weeks` (default 12, แต่ไม่ย้อนก่อน 2026-04-01; วันที่ cut-off เก็บเป็น config parameter)
- `state`: `draft → computed → confirmed → done`, มี `cancel`
- one2many ไป demand line, suggestion, schedule line
- ปุ่ม: Compute Demand & Suggestions, Create Documents (เปิด wizard), Schedule, Open Gantt, Apply Schedule
- Compute ซ้ำได้ขณะ draft/computed: ลบ suggestion ที่ยัง `proposed` แล้วคำนวณใหม่, เก็บตัวที่ `approved/done` ไว้และหักออกจากความต้องการ

**`buz.plan.demand.line`** — demand ต่อสินค้าต่อ bucket
- `run_id`, `product_id`, `bucket_start` (date), `source`: `delivery` / `forecast` / `safety` / `dependent`
- `qty`, `qty_manual` (planner แก้ forecast ได้, ถ้ามีค่าใช้แทน `qty`), `origin_ref` (เลข picking / suggestion แม่)
- Stored, ไม่ใช่ computed ล้วน เพื่อให้ pivot/กราฟได้

**`buz.plan.suggestion`** — ข้อเสนอผลิต/ซื้อ
- `run_id`, `product_id`, `action`: `make` / `buy`, `qty`, `uom_id`
- `date_need` (วันที่ของต้องพร้อม), `date_release` (= `date_need − lead time`; ถ้าอยู่ในอดีต ตั้งเป็นวันนี้และ `is_late = True`)
- `bom_id`, `picking_type_id`, `vendor_id`, `level` (low-level code)
- ตัวเลขอธิบาย: `onhand_qty`, `incoming_qty`, `demand_qty`, `projected_qty`, `shortage_qty`
- `parent_suggestion_id` (pegging: component นี้มาจาก make suggestion ไหน)
- `state`: `proposed / approved / rejected / done`
- `production_id`, `purchase_line_id` (เอกสารที่สร้าง)

**`buz.plan.schedule.line`** — คิวที่เสนอ (ยังไม่ใช่ของจริงจนกว่า Apply)
- `run_id`, `workorder_id`, `production_id`, `workcenter_id`, `product_id`, `sequence`
- `date_start`, `date_end`, `duration_minutes`, `duration_source`: `history` / `expected`
- `is_locked` (WO state progress หรือ planner ล็อก), `is_late` (จบหลัง `date_deadline`/`date_need`), `is_manual` (ลากแก้มือ)
- `state`: `proposed / applied`

**`buz.plan.operation.time`** — SQL view (`_auto = False`)
- ต่อ `operation_id` + `workcenter_id`: จำนวน WO done, นาทีจริงต่อหน่วยผลิต (median ของ `duration / qty_produced`),
  นาที expected ต่อหน่วย, อัตราส่วนจริง/expected. ใช้ WO done ตั้งแต่ 2026-04-01 ที่ `duration > 0` และ `qty_produced > 0`.

**Settings** (`res.config.settings` → `ir.config_parameter`)
- คลัง supply เริ่มต้น, lead time default ผลิต/ซื้อ, horizon, lookback, history cut-off date (default 2026-04-01),
  จำนวน WO ขั้นต่ำที่ถือว่า history เชื่อได้ (default 5), factor คูณ expected เมื่อไม่มี history (default 1.0)

### 5.3 Engine คำนวณความต้องการ (MRP)

เขียนเป็น method บน `buz.plan.run`, แยกฟังก์ชันย่อยที่ test ได้โดยไม่ต้องผ่าน UI. ดึงข้อมูลด้วย `_read_group` หรือ SQL
แบบ batch; ห้าม loop query ต่อสินค้า (สินค้าที่เกี่ยวข้องหลักพันตัว).

1. **Delivery demand**: stock.move ของ picking type outgoing ใน state เปิด, แปลงเป็น UoM หลักของสินค้า,
   จัดลง bucket ตาม `date`. วันที่ในอดีต → bucket แรก. เลยปลาย horizon → ไม่นับ.
2. **Forecast**: ค่าเฉลี่ยต่อสัปดาห์ของ outgoing move ที่ done ในช่วง lookback (ไม่ย้อนก่อน cut-off),
   เฉพาะสินค้าที่ `forecast_method = avg`. สินค้าที่ไม่มี param: ใช้ avg ถ้ามีการส่งออกใน lookback.
3. **Demand ต่อ bucket = max(delivery, forecast)** (forecast กินใบสั่งที่มีอยู่แล้ว ไม่บวกซ้อน).
   บันทึกเป็น demand line แยก source: delivery เต็มจำนวน + forecast เฉพาะส่วนเกิน.
4. **Supply**: on-hand = ผลรวม quant ใน location ภายใต้ `lot_stock_id` ของคลังที่เลือก (ไม่ใช้ `qty_available` แบบไม่ระบุคลัง).
   Scheduled receipts = incoming move เปิดของ PO + finished move เปิดของ MO, ลง bucket ตามวันที่ (อดีต → bucket แรก).
5. **Component ของ MO เปิด**: raw move ที่ยังไม่ done ของ MO state confirmed/progress = dependent demand ลง bucket ตาม `date`.
6. **Netting ทีละ level** (low-level code จากโครงสร้าง BOM, level 0 = สินค้าขายก่อน):
   `projected[b] = projected[b-1] + receipts[b] − demand[b]`.
   ถ้า `projected[b] < safety_stock` → สร้าง suggestion qty = `safety_stock − projected[b]`,
   ปัดขึ้นเป็น `min_batch_qty` แล้วปัดขึ้นตาม `batch_multiple`, `date_need` = วันแรกของ bucket, แล้วบวกกลับเข้า projected.
7. **make หรือ buy**: `supply_method` ถ้าไม่ใช่ auto ใช้ตามนั้น. auto: มี BOM `type = normal` active → make, ไม่มี → buy.
   เลือก BOM ด้วย `mrp.bom._bom_find`.
8. **ระเบิด BOM** ของ make suggestion ด้วย `bom.explode()` (phantom ระเบิดทะลุให้อัตโนมัติ) → dependent demand
   ของ component ที่ bucket ของ `date_release`, ผูก `parent_suggestion_id`. แล้ว net level ถัดไป.
9. กัน BOM วนลูป: จำกัดความลึก (เช่น 10 ชั้น) และ raise `UserError` ที่บอกชื่อสินค้าที่วน.
10. สินค้า `detailed_type != 'product'` ไม่วางแผน.

### 5.4 Wizard สร้างเอกสาร (`buz.plan.create.documents.wizard`)

- เลือก suggestion ที่ `approved` (หรืออนุมัติใน wizard), แสดงสรุปก่อนสร้าง: กี่ MO, กี่ PO, vendor ไหน.
- **make** → `mrp.production` สถานะ **draft**: `product_id`, `product_qty`, `bom_id`, `picking_type_id`,
  `date_start` = `date_release`, `date_deadline` = `date_need`, `origin` = เลขแผน.
  ไม่เรียก `action_confirm`. ถ้าไม่มี `picking_type_id` ให้ error ชี้ไปที่ param ของสินค้า.
- **buy** → `purchase.order` สถานะ **draft** รวมบรรทัดตาม vendor, `origin` = เลขแผน, `date_planned` = `date_need`.
  ไม่มี vendor → ข้ามและรายงานในสรุป (ไม่ raise ทั้งชุด).
- เขียน link กลับที่ suggestion, state → `done`. โพสต์สรุปใน chatter ของแผน.
- ห้ามสร้างซ้ำ: suggestion ที่มี `production_id`/`purchase_line_id` แล้วถูกข้าม.
- สร้างผ่าน ORM ปกติ ไม่ใช้ `sudo()`; ถ้า module guard ตัวไหนบล็อกการสร้าง draft ให้หยุดและรายงาน อย่า bypass.

### 5.5 Engine จัดคิว (finite capacity, forward)

ขอบเขต: WO state `pending / waiting / ready / progress` ของ MO state `confirmed / progress`
(กรองตาม `picking_type_ids` ของแผนถ้ามี). MO draft ไม่มี WO จึงไม่เข้าคิว: แสดงใน load table ระดับวันเท่านั้น.

1. **Duration**: นาทีจริงต่อหน่วยจาก `buz.plan.operation.time` × qty คงเหลือ ถ้ามี history ถึงเกณฑ์;
   ไม่ถึง → `duration_expected` × factor. WO ที่ progress: หักเวลาที่ทำไปแล้ว (`duration`) ขั้นต่ำ 1 นาที.
2. **ลำดับ MO**: `date_deadline` (null ไว้ท้าย) → `priority` desc → `date_start` → id.
3. **วาง WO**: ตามลำดับ operation ใน MO (ถ้า `allow_workorder_dependencies` ใช้ `blocked_by_workorder_ids`, ไม่งั้นใช้ sequence).
   เวลาเริ่ม = max(เวลาว่างถัดไปของ workcenter, เวลาจบของ WO ก่อนหน้าใน MO เดียวกัน, ตอนนี้).
   Workcenter capacity 1 = ทีละงาน ห้ามซ้อน.
4. **เวลาทำงาน**: ใช้ calendar ของ workcenter (`resource_calendar_id._attendance_intervals_batch` หรือ `plan_hours`)
   ข้ามช่วงพัก/นอกเวลา/วันหยุด. เวลาเก็บเป็น UTC, คำนวณตาม tz ของ calendar.
5. **ล็อก**: WO progress และ schedule line ที่ `is_locked` ไม่ถูกย้าย; งานอื่นวางรอบมัน.
6. **Re-schedule**: ลบ line ที่ `proposed` และไม่ `is_locked`/`is_manual` แล้ววางใหม่.
7. ผลเขียนลง `buz.plan.schedule.line` เท่านั้น. ตั้ง `is_late` เมื่อจบหลัง deadline.
8. **Apply Schedule** (ปุ่มแยก, ถามยืนยัน): เขียน `date_start` + `date_finished` ลง `mrp.workorder`, state line → `applied`.
   ตรวจจาก source (Phase 0) ว่าการเขียนสองฟิลด์นี้สร้าง/ย้าย `leave_id` และ sync วันที่ MO อย่างไร แล้วเขียน test ครอบ.
   ไม่เปลี่ยน state ของ WO/MO.

### 5.6 Gantt (OWL client action)

ทำเป็น **client action** (`ir.actions.client`, tag `buz_production_planning.gantt`) ไม่ลงทะเบียน view type ใหม่
(ไม่ต้อง patch `ir.ui.view.type` / `ir.actions.act_window.view`).

- แถว = workcenter (จัดกลุ่มตามสายผลิต), แท่ง = schedule line, แกนเวลา zoom วัน / สัปดาห์
- แท่งแสดงเลข MO + รหัสสินค้า; สี: ปกติ / late (แดง) / locked (เทา) / manual (ขอบเข้ม); tooltip: MO, สินค้า, qty, operation, เวลา, deadline
- ลากย้ายในแถวเดิมและยืด/หด → `write` ที่ schedule line (`is_manual = True`); ลากข้ามแถวไม่อนุญาต (workcenter มาจาก operation)
- ซ้อนกันใน workcenter เดียว → เตือนด้วยสี ไม่บล็อก (planner ตัดสินใจเอง แล้วกด Re-schedule ได้)
- แถบ load ต่อวันใต้ชื่อ workcenter: นาทีที่จัดแล้ว / นาที capacity ของวันนั้น
- Filter: สายผลิต, workcenter, เฉพาะ late. ปุ่ม: Re-schedule, Apply, วันนี้, ก่อนหน้า/ถัดไป
- คลิกแท่ง → เปิด form ของ MO
- ข้อมูลโหลดผ่าน method เดียวบน `buz.plan.run` ที่คืน JSON (workcenters, lines, capacity ต่อวัน) ตามช่วงวันที่ที่มองเห็น
- ใช้ OWL component + `useService("orm")` ตามแบบ Odoo 17, CSS อยู่ใน module, ไม่ใช้ library ภายนอก
- ต้องลื่นกับ 40 แถว และแท่งระดับ 1,500

### 5.7 Views, เมนู, รายงาน

- เมนูหลัก "วางแผนการผลิต" (app): แผน, ข้อเสนอ, Demand, ตารางคิว, Load vs Capacity, พารามิเตอร์สินค้า, ตั้งค่า
- `buz.plan.run`: form (statusbar, ปุ่ม, notebook: Demand / ข้อเสนอ / คิว), list
- `buz.plan.suggestion`: list แก้ qty/วันที่ได้ inline, ปุ่ม approve/reject หลายบรรทัด, filter make/buy/late, group by สายผลิต/vendor/level, pivot
- `buz.plan.demand.line`: pivot (สินค้า × สัปดาห์ × source), list แก้ `qty_manual`
- `buz.plan.schedule.line`: list + pivot (workcenter × วัน, measure นาที) = Load vs Capacity
- `buz.plan.product.param`: list editable + form, import ได้
- Smart button บน MO: แผนที่สร้างมัน (ผ่าน suggestion)

### 5.8 Security และภาษา

- Group: "Planning / User" (อ่าน-เขียนแผน, สร้าง draft) และ "Planning / Manager" (ตั้งค่า, Apply Schedule, ลบแผน).
  User ของ MRP ทั่วไปอ่านได้อย่างเดียว.
- Record rule multi-company ทุก model ที่มี `company_id`.
- Source string เป็นอังกฤษ, แปลไทยครบใน `i18n/th.po` (label, selection, ข้อความ error, เมนู). ข้อความ error ต้องบอกสิ่งที่ผู้ใช้ต้องแก้.

## 6. โครงสร้างไฟล์ที่คาดหวัง

```
buz_production_planning/
  __manifest__.py  __init__.py
  models/      plan_product_param.py  plan_run.py  plan_demand_line.py  plan_suggestion.py
               plan_schedule_line.py  plan_operation_time.py  res_config_settings.py  mrp_production.py
  engine/      mrp_netting.py  scheduler.py        # logic ล้วน เรียกจาก model, test ง่าย
  wizard/      plan_create_documents.py  + views
  views/       *_views.xml  menus.xml  res_config_settings_views.xml
  security/    security.xml  ir.model.access.csv
  data/        ir_sequence.xml  ir_config_parameter.xml
  static/src/gantt/   gantt_action.js  gantt_action.xml  gantt.scss
  i18n/th.po
  tests/       __init__.py  common.py  test_netting.py  test_documents.py  test_scheduler.py
```

## 7. ลำดับงาน (หยุดรายงานทุก phase)

| Phase | งาน | ผ่านเมื่อ |
|---|---|---|
| 0 | ยืนยันข้อมูล prod + อ่าน source mrp | รายงานส่วนต่างจาก snapshot |
| 1 | Manifest, models, security, settings, views พื้นฐาน, param + ปุ่มคำนวณค่าเริ่มต้น | ติดตั้งบน DEV ได้ ไม่มี error/warning ใน log |
| 2 | Engine MRP + demand/suggestion views | tests netting ผ่าน |
| 3 | Wizard สร้าง MO/PO draft | tests documents ผ่าน, MO ที่ได้ยัง draft |
| 4 | Scheduler + Apply | tests scheduler ผ่าน |
| 5 | Gantt client action | เปิดบน DEV ลาก/ยืดแล้วค่าถูกบันทึก |
| 6 | i18n ไทย, pylint-odoo, เก็บงาน | lint สะอาด, แปลครบ |

## 8. Tests (Odoo test runner เท่านั้น, `TransactionCase`)

ทุก test สร้างข้อมูลเอง (สินค้า, BOM, workcenter, calendar, คลัง) ไม่พึ่งข้อมูลใน DB.
ระวัง: DEV มี guard ด้าน stock (`stock_fifo_by_location`, `buz_stock_reservation_guard`) ถ้า test ต้องมี stock
ให้สร้าง quant ผ่าน `stock.quant._update_available_quantity` ในคลัง test ที่สร้างเอง; ถ้ายังโดนบล็อกให้รายงาน อย่าปิด guard.

- **Netting**: on-hand พอ → ไม่มี suggestion; ขาด → qty ถูกต้อง; ปัด `min_batch_qty` และ `batch_multiple`;
  safety stock; scheduled receipt ลดความต้องการ; demand เลยกำหนดลง bucket แรก; `date_release` ในอดีต → วันนี้ + `is_late`
- **Forecast**: max(delivery, forecast) ไม่บวกซ้อน; `qty_manual` ชนะค่า avg; ไม่ใช้ข้อมูลก่อน cut-off
- **BOM**: 2 ชั้น (FG → semi → RM) ได้ suggestion ครบทุก level พร้อม pegging; phantom ระเบิดทะลุ; BOM วนลูป → `UserError`
- **make/buy**: auto ตาม BOM; override ด้วย `supply_method`
- **Documents**: MO draft มี `origin`, `date_deadline`, ไม่ถูก confirm; PO รวมตาม vendor; ไม่มี vendor ถูกข้ามพร้อมรายงาน; รันซ้ำไม่สร้างซ้ำ
- **Scheduler**: ไม่มี 2 งานซ้อนใน workcenter เดียว; WO ใน MO เดียวกันเรียงตาม operation; ข้ามเวลานอก calendar และข้ามวันหยุด;
  WO progress ไม่ถูกย้าย; line `is_manual` คงอยู่หลัง re-schedule; ใช้ history เมื่อถึงเกณฑ์ ไม่ถึงใช้ expected × factor;
  `is_late` ถูกต้อง; Apply เขียนวันที่ลง WO และไม่เปลี่ยน state

## 9. Definition of Done

1. `pylint --load-plugins=pylint_odoo buz_production_planning/` ไม่มี error
2. `bash scripts/deploy.sh dev buz_production_planning` สำเร็จ, ติดตั้ง/upgrade บน MOG_DEV ไม่มี traceback
3. Tests ผ่านทั้งหมดบน DEV (รันหลังได้รับอนุญาต):
   `ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_production_planning --test-enable --stop-after-init --no-http"`
4. ไล่ flow จริงบน UI ของ DEV ด้วยตา: สร้างแผน → Compute → ตรวจ demand/suggestion → approve → สร้าง MO draft + PO draft →
   Schedule → Gantt ลาก/ยืด → Apply → ตรวจวันที่บน workorder. รายงานผลพร้อมสิ่งที่เห็นจริง ไม่ใช่แค่ test ผ่าน.
5. รายงานสุดท้ายระบุชัด: อะไรตรวจแล้ว, อะไรยังไม่ได้ตรวจ, ข้อจำกัดที่รู้ (เช่น MO ไม่มี WO ไม่เข้าคิว)
6. ไม่มี commit, ไม่มี push, ไม่มีการแตะ prod นอกจาก `SELECT` ใน Phase 0

## 10. นอกขอบเขต (อย่าทำ)

- วางแผนคน/กะ/พนักงานต่อ workcenter
- Auto-confirm MO/PO, cron ที่สร้างเอกสารเอง, การ reserve หรือเบิกวัตถุดิบ (เป็นหน้าที่ `buz_mrp_stock_request`)
- ต้นทุน, valuation, บัญชี
- แก้ข้อมูลเก่า (SO ค้าง, MO ค้าง, lead time ใน master ของ Odoo)
- แก้ `expected duration` ใน operation master (module นี้แค่ใช้เวลาจริงตอนจัดคิว)
- รายงาน PDF, dashboard ผู้บริหาร, integration ภายนอก
- แก้ module อื่นใน repo

## 11. เมื่อไม่แน่ใจ

- พฤติกรรม Odoo core: อ่าน source บน server ก่อน อย่าเดา
- ข้อมูลจริงไม่ตรง snapshot หรือ guard บล็อก: หยุดและรายงานพร้อมหลักฐาน
- การตัดสินใจที่เปลี่ยนสิ่งที่ planner เห็นหรือเอกสารที่ถูกสร้าง: ถามผู้ใช้
- รายละเอียดการ implement ที่ไม่เปลี่ยนผลลัพธ์: ตัดสินใจเองแล้วระบุในรายงาน phase
