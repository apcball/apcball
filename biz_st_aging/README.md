# biz_st_aging — อายุสินค้าคงเหลือ (Stock Aging)

รายงาน **คงเหลือ ณ วันที่ แยกตามช่วงอายุ** (0-30 / 31-60 / 61-90 / 91-180 / 181-365 / >365 วัน —
ตั้งค่าขอบช่วงได้ต่อบริษัท) ทั้งจำนวนและมูลค่า พร้อม **อายุเฉลี่ย / วันไม่เคลื่อนไหว / ใช้เฉลี่ยต่อเดือน /
MOS / สถานะ** กางเป็นต้นไม้ คลัง → สินค้า → (ที่เก็บ / ล็อต) หรือ สินค้า → คลัง ออกได้ทั้งหน้าจอ PDF และ Excel

Odoo Community ไม่มีรายงานลักษณะนี้ — **Stock / Valuation** ให้มูลค่าปัจจุบันอย่างเดียว ไม่บอกว่าของ
แต่ละก้อนอยู่มานานเท่าไร และ `stock.quant.in_date` เก็บ **วันเก่าสุด** ของ quant (ไม่ใช่ชั้น FIFO)
ทั้งยังไม่มีประวัติย้อนหลัง จึงตอบ "ณ วันที่" ไม่ได้

โมดูลนี้ **standalone** (depends แค่ `stock`, `stock_account`) แต่ลอกหลักการทั้งหมดจาก
`biz_st_stock_card` — ถ้าติดตั้งคู่กัน การกดชื่อสินค้าจะเปิด **การ์ดสินค้ารายวัน** ของ stock card ให้อัตโนมัติ

## เครื่องยนต์เดียว สามช่องทาง

```
biz.stock.aging.report.get_report_data(options)    ← แหล่งความจริงเดียว
   ├── OWL client action  biz_st_aging.stock_aging
   ├── QWeb PDF           report.biz_st_aging.report_stock_aging_doc
   └── XLSX               biz.stock.aging.xlsx.generate(options)
biz.stock.aging.config                             ← ตั้งค่าต่อบริษัท (ปุ่ม "ตั้งค่า Aging" บนจอ)
```

**ห้ามเพิ่มเส้นทางคำนวณเส้นที่สอง** สเปกคอลัมน์ (`report_columns()`) ก็ส่งลงมาใน payload
(`data.columns`) หน้าจอจึงไม่ต้อง mirror เอง การคำนวณใช้ ORM `_read_group` เป็นหลัก คิวรีเดียวที่เป็น
SQL (FIFO walk) สร้าง FROM/WHERE จาก `_where_calc` + `_apply_ir_rules` ของ ORM จึงได้ domain, record rule
และ multi-company ชุดเดียวกับ `_read_group` ทุกประการ

รายงานหนึ่งครั้งยิงคิวรีจำนวนคงที่ (แผนที่มิติ 4 + บัญชีคุม 3 + ชั้นอายุ 1 + SVL 1)
**ไม่ขึ้นกับจำนวนสินค้า**

### แคชระดับโหนด (17.0.1.1.0)

ทุกอย่างที่ต้องกวาด `stock.move.line`/SVL อยู่ใน `_computed_nodes()` และถูกแคชต่อ worker
(`NODES_CACHE`, LRU 16 ชุด) คีย์ = (db, uid, core options, **ลายนิ้วมือข้อมูล**) — ลายนิ้วมือคือ
`count / max(id) / max(write_date)` ของ move line (done) และ SVL ในขอบเขตบริษัท จึงหมดอายุเอง
ทันทีที่มีรายการใหม่หรือถูกแก้ ส่วน TTL 10 นาทีเป็นแค่เพดานกันแผนที่ชื่อสินค้า/ที่เก็บค้าง

ผลคือ **กาง/หุบแถว, เปลี่ยน พ.ศ./ค.ศ., สลับ "แสดงสินค้า"** (`RENDER_ONLY_KEYS`) ทำแค่ pivot ใน Python
ไม่แตะ DB (`checks.from_cache`) ปุ่ม "ปรับปรุงข้อมูล" ส่ง `nocache: true` เพื่อข้ามแคชแน่ ๆ
(`nocache` ไม่ถูก echo กลับใน `data.options`) — **ห้ามแก้ `nodes`/`maps` หลัง `_computed_nodes()`**
เพราะเป็นของที่แชร์กับการเรียกครั้งถัดไป

## วิธีคำนวณ

### คงเหลือ ณ วันที่ (บัญชีคุม)

`_read_group` บน `stock.move.line` (done) ต่อ (บริษัท, สินค้า, ที่มา, ที่ไป[, ล็อต]) สองช่วง:
ก่อนช่วงใช้งาน / ในช่วงใช้งาน แล้วปล่อย fact ตามกฎเดียวกับ stock card:

> ที่มาเป็นของคงคลัง → OUT ที่โหนดต้นทาง · ที่ไปเป็นของคงคลัง → IN ที่โหนดปลายทาง ·
> ทั้งคู่ตกโหนดเดียวกัน → ไม่ปล่อย

`closing_qty = opening + in − out` คือคงเหลือ ณ วันที่ของโหนด (ตรงกับ `qty_available` ของ core)
การปรับปรุงยอด/ของเสีย **รวมเสมอ** (ไม่มีตัวเลือกตัดออก) ไม่งั้นยอดคงเหลือไม่จริง

### ชั้นอายุแบบ FIFO (`age_basis = node_in`)

หลัก: **ของที่เหลืออยู่คือของที่รับเข้าล่าสุด** — คิวรีเดียว (`_read_layers_sql`) รวม IN fact ระดับ *วัน*
(ตามเขตเวลาผู้ใช้) ต่อโหนด แล้วใช้ window function หายอดสะสมจากวันใหม่สุดไปเก่า
ส่งกลับเฉพาะชั้นที่ยอดสะสมก่อนหน้ายังไม่ถึงคงเหลือ (`before < closing`) ประวัติแสนบรรทัดจึงข้าม DB มา
แค่ไม่กี่แถวต่อโหนด `age = ณ วันที่ − วันรับเข้า` กฎ fact ทั้งหมด (ปลายทางต้อง on-hand, ย้ายในโหนดเดียวกัน
ไม่ปล่อย, ก้อน (ที่มา, ที่ไป, วัน) ที่รวมแล้ว ≤ 0 ทิ้ง) อยู่ใน SQL ตัวเดียวกับ `_emit_layer`
`_walk_layers_windowed` คือเวอร์ชัน ORM รายหน้าต่างเดิม เก็บไว้ให้เทส `test_sql_walk_matches_windowed_orm_walk_bit_for_bit`
เทียบผลทุกโหนดทุกระดับ — **แก้กฎ fact ต้องแก้ทั้งสองที่แล้วให้เทสนี้ผ่าน**

| กรณี | ผล |
|---|---|
| รับ-จ่ายวันเดียวกัน | ไม่ต้องทำอะไรพิเศษ — OUT หักคงเหลือแล้ว IN วันนั้นคือชั้นใหม่สุด |
| โอนข้ามคลัง (A → B) | B ได้ชั้นใหม่วันที่โอน (อายุรีเซ็ต) A ถูกกินตาม FIFO |
| ย้ายภายในโหนดเดียวกัน | ไม่ปล่อย fact → อายุคงเดิม |
| เปิดระดับ ที่เก็บ/ล็อต | อายุนับที่ระดับที่แสดง — ย้ายชั้นวางนับเป็นรับเข้าใหม่ของชั้นนั้น (`checks.age_granularity`) |
| ปรับปรุงยอด / รับคืนลูกค้า | เป็นชั้นตามวันนั้น (ไม่รู้อายุจริง) |
| คงเหลือ > IN ทั้งประวัติ | เศษลงช่วงเก่าสุด อายุ = ขอบสุดท้าย + 1, flag `unlayered`, `checks.unlayered_qty` |
| คงเหลือติดลบ | ไม่จัดชั้น, flag `negative`, `checks.bucket_qty_difference` |

`age_qty_sum = Σ(อายุ × จำนวน)` บวกกันได้ทุกระดับ → **อายุเฉลี่ยของแถวใด ๆ = age_qty_sum ÷ bucketed_qty**

### มูลค่า (`cost_basis = average`)

`stock.valuation.layer` ไม่มีมิติคลัง/ที่เก็บ/ล็อต และไม่มีฟิลด์วันที่ (ใช้ `stock_move_id.date` fallback
`create_date`) เครื่องยนต์อ่านมูลค่าสะสม ณ วันที่ต่อ (บริษัท, สินค้า) แล้ว:

* กระจายลงโหนดตามสัดส่วนคงเหลือ — **ตัวหารมาจากชุดเงาที่ไม่ผ่านตัวกรองคลัง** (กรองคลังเดียวแล้ว
  คลังนั้นจึงไม่ได้มูลค่าทั้งสินค้า); กรองล็อตใช้จำนวน SVL ทั้งบริษัทเป็นตัวหาร
* สินค้าที่ SVL มีมูลค่าแต่ไม่มีจำนวน (landed cost หลังของหมด) → โหนด "ไม่ระบุคลัง" ไม่หายเงียบ
* ซอยลงช่วงอายุตามสัดส่วนจำนวนของช่วง เศษยัดช่วงสุดท้ายที่มีจำนวน → **Σ ช่วง = มูลค่าโหนด เป๊ะ**

`checks.svl_value / report_value / svl_difference / svl_reconciled` พิสูจน์ทุกครั้ง (ชิปเขียว/แดงบนจอ,
กล่องใน PDF, ชีตใน Excel) — รายงานที่กรองคลัง/ที่เก็บ/ล็อตกระทบยอดทั้งบริษัทไม่ได้
(`checks.svl_scope_limited` แจ้งเป็นข้อมูล ไม่ใช่ error)

### ตัวชี้วัด (แสดงตั้งแต่ระดับสินค้าลงไป; แถวคลัง/หมวด/บริษัทเหนือสินค้าแสดงแค่อายุเฉลี่ย)

| ตัวชี้วัด | นิยาม |
|---|---|
| วันไม่เคลื่อนไหว | ณ วันที่ − วันจ่ายออกจากโหนดล่าสุด (ทุกประเภทรวมโอนภายใน); ไม่เคยจ่าย → นับจากวันรับเข้าเก่าสุด (`*`, `no_move_is_estimate`) |
| ใช้เฉลี่ย/เดือน | จำนวนที่ออกจากขอบเขตมูลค่าบริษัท (ขาย/ผลิต) ในช่วง `usage_months` ÷ เดือน — **ไม่นับ** โอนภายใน / ปรับปรุงยอด / ของเสีย |
| MOS | คงเหลือ ÷ ใช้เฉลี่ย/เดือน (ว่างเมื่อไม่มีการใช้) |
| สถานะ | ตามลำดับ: **ตาย** (ไม่จ่าย ≥ `obsolete_days`) → **ไม่เคลื่อนไหว** (≥ `non_moving_days`) → **ช้า** (MOS > `slow_mos_months` หรือไม่มีการใช้เลย) → **ปกติ** |

KPI "จำนวนรายการเสี่ยง" นับที่ระดับ **(บริษัท, สินค้า)** — รวมทุกคลัง/ล็อต — จึงเท่ากันทั้งสองแกน
และไม่ขึ้นกับการกาง; KPI "มูลค่า > N วัน" ใช้ขอบช่วงที่ 3/4/5 ของ config

## ตัวกรอง / options

| กลุ่ม | คีย์ |
|---|---|
| วันที่ | `date_to` (ณ วันที่), `tz`, `date_format`; `date_from` = (ณ วันที่ + 1 วัน) − `usage_months` เดือน (30 มิ.ย. ย้อน 6 เดือน = 1 ม.ค.) (ช่วงคำนวณการใช้ และการ์ด 4 ใบมุมขวา) |
| บริษัท | `company_ids`, `company_mode` consolidated / split |
| แกน | `group_mode` wh_product / product_wh, `group_categ`, `group_location`, `group_lot` |
| ขอบเขต | `warehouse_ids`, `location_ids`, `categ_ids`, `product_ids`, `product_search` (ilike รหัส/ชื่อ), `lot_ids`, `include_consignment` |
| วิธีคิด | `age_basis` (`node_in`), `cost_basis` (`average`), `show_value` |
| การแสดง | `unfold_level`, `unfolded`, `display_product` on_hand / all |
| จาก config | `bucket_edges`, `usage_months`, `slow_mos_months`, `non_moving_days`, `obsolete_days` (echo กลับให้ client) |

`_normalize_options()` clamp/whitelist ทุกคีย์ และ client รับค่าที่ normalize แล้วไปใช้แทน
(`state.options = data.options`) — idempotent

Config อ่านจาก **บริษัทหลัก** ของรายงาน (`company_id`) เสมอ รายงานรวมหลายบริษัทจึงใช้เกณฑ์ชุดเดียว
(`checks.config_company`)

## Roadmap (ตัดออกจากรุ่นแรกโดยตั้งใจ)

* `cost_basis = fifo` — ตีมูลค่าชั้นด้วยราคารับเข้าของวันนั้น (ต้องอ่าน SVL รายวันทุกสินค้า)
* `age_basis = external_in` — ไม่รีเซ็ตอายุเมื่อโอนภายใน (จัดชั้นระดับสินค้าแล้วกระจายลงคลัง)
* ตัวกรอง แบรนด์ / กลุ่มสินค้า — ไม่มีฟิลด์เหล่านี้ใน product

select "หลักการอายุ" และ "วิธีคิดมูลค่า" บนจอมีตัวเลือกเดียวในรุ่นนี้ เพิ่มค่าใหม่ใน `AGE_BASIS` /
`COST_BASIS` ได้โดยไม่ต้องเปลี่ยน payload

## สิทธิ์

* เปิดรายงานได้: `stock.group_stock_user` (ไม่มีสิทธิ์ → `AccessError`)
* เห็นมูลค่า: `account.group_account_readonly` **หรือ** `stock.group_stock_manager` (`_can_see_value()`)
  ผู้ใช้บัญชีอ่าน SVL ผ่าน `sudo()` เฉพาะหลังผ่านด่านนี้และ `_resolve_company_ids()`
* ไม่มีสิทธิ์มูลค่า → ได้รายงานเฉพาะจำนวน (`checks.value_hidden_reason`) ไม่ error
* ทุกคิวรีผ่าน `_scoped()` (`allowed_company_ids`) — ir.rule ของ stock อิง env.companies
* config: stock user อ่าน, stock manager แก้; ir.rule ตามบริษัท

## ข้อจำกัดที่ทราบ

1. **มูลค่าแม่นที่ (บริษัท, สินค้า) — ต่ำกว่านั้นเป็นการเฉลี่ย** (SVL ไม่มีมิติคลัง) และเป็นต้นทุนเฉลี่ย
   ณ วันที่ ไม่ใช่ราคาของชั้นรับเข้าจริง
2. **อายุนับที่ระดับที่แสดง** เปิด/ปิด ล็อต หรือ ที่เก็บ ทำให้ช่วงอายุระดับสินค้าต่างกันได้ เมื่อการหยิบจริง
   ไม่ใช่ FIFO ระบุตรง ๆ (ผลรวมจำนวนเท่ากันเสมอ)
3. **โอนข้ามคลังรีเซ็ตอายุ** ที่คลังปลายทาง — เป็นความจงใจของ `node_in`
4. **ปรับปรุงยอด/รับคืน** ได้อายุตามวันที่ทำรายการ ไม่ใช่อายุจริงของของ
5. **สินค้าฝากขายไม่นับโดยตั้งต้น** (`include_consignment`); เปิดแล้วมีจำนวนแต่ไม่มีมูลค่า (core ไม่สร้าง SVL)
6. **คิวรีกวาดประวัติทั้งหมดก่อน ณ วันที่** — ใช้ดัชนี partial สองตัว `WHERE state='done'`:
   `(company_id, product_id, date)` (ของ `biz_st_stock_card` ถ้ามี ไม่งั้นสร้าง `stock_move_line_stock_aging_idx`)
   สำหรับคิวรีที่กรองสินค้า และ `(company_id, date)` (`stock_move_line_stock_aging_date_idx`) สำหรับบัญชีคุม
   ที่กรองแค่บริษัท + ช่วงวันที่; FIFO walk **กรอง `product_id in` เฉพาะสินค้าที่ยังจัดชั้นไม่ครบเสมอ**
   เพราะหน้าต่างสุดท้าย (>365) ไม่มีขอบล่าง
7. **`max_groups` / `max_layer_rows` / `max_lines`** กันคิวรีและหน้าจอระเบิด → `UserError` บอกให้กรองแคบลง
   (คิวรีชั้นอายุใส่ `LIMIT max_layer_rows+1` จึงไม่ดึงเกินโควตาข้าม DB มาก่อน) `max_lines` = เพดานแถวที่แสดง
   **หลังกาง**: จอ 5,000 / PDF 3,000 (`PDF_MAX_LINES`) / Excel 100,000 (`XLSX_MAX_LINES`) ตั้งค่าเองใน generator
   แต่ละตัว ไม่กระทบตัวเลข (อยู่ใน `RENDER_ONLY_KEYS` จึงใช้แคชร่วมกัน) ฝั่ง OWL `updateOptions` คืน options
   เดิมเมื่อ server ปฏิเสธ ผู้ใช้จึงไม่ติดค้างกับการกางที่ใหญ่เกิน
8. **หลายสกุลเงินบวกกันโดยไม่แปลงค่า** พร้อมแบนเนอร์ (`checks.mixed_currency`)
9. **สินค้า `consu`/`service` ไม่รวม**; **ขอบวันเป็นเขตเวลาผู้ใช้** (`options.tz`)

## เมนู

Inventory → Reporting → **อายุสินค้าคงเหลือ (Stock Aging)** และ **พิมพ์อายุสินค้าคงเหลือ (PDF / Excel)**
(ใต้ `stock.menu_warehouse_report` = `group_stock_manager`) · Inventory → Configuration → **ตั้งค่าอายุสินค้าคงเหลือ**

## PDF / Excel

* PDF A4 แนวนอน ฟอนต์ Sarabun ฝัง base64 (**ห้ามใส่ single-quote ใน `SARABUN_FONT_CSS`** — QWeb escape เป็น
  `&#39;` แล้ว wkhtmltopdf ไม่อ่าน @font-face) หัวตาราง 2 ชั้น (ชั้นกลาง "อายุสินค้าคงเหลือ (วัน)" มีเฉพาะบนจอ)
* Excel 3 ชีต: **อายุสินค้าคงเหลือ** (ต้นไม้ + คอลัมน์ช่วย `counts_to_total` ซ่อน + ยอดรวม `=SUMPRODUCT()`
  เฉพาะคอลัมน์ `additive`; อายุเฉลี่ย/No Move/MOS/สถานะ เขียนค่าจากเครื่องยนต์), **สรุปตามช่วงอายุ**, **ข้อสังเกต**
  ไม่ใส่ autofilter (หัว merge สองแถว)

## การทดสอบ

5 ไฟล์ — ชั้นอายุ / มูลค่า / ตัวชี้วัด / การจัดกลุ่ม / สิทธิ์-ส่งออก-config

```bash
docker stop dev-odoo-1
docker run --rm --network dev_default --volumes-from dev-odoo-1 \
  -e HOST=db -e PORT=5432 -e USER=odoo -e PASSWORD='biz@0709' \
  biz-odoo17-dev:17.0 odoo -c /etc/odoo/odoo.conf -d odoo-dev \
  --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons \
  --stop-after-init --max-cron-threads=0 --http-port=8099 \
  -u biz_st_aging --test-enable --test-tags '/biz_st_aging'
docker start dev-odoo-1
```

`odoo-dev` มีข้อมูลจริงอยู่แล้ว เทสจึงสร้าง fixture ของตัวเอง (คลัง/สินค้าใหม่ ณ วันที่คงที่ 2025-06-30)
และ**รีเซ็ต config ของบริษัทเป็นค่าตั้งต้น**ใน `setUpClass` ห้าม assert ค่าสัมบูรณ์ทั้งระบบ

## Dependencies

`stock`, `stock_account` · Python: `xlsxwriter` · ทำงานร่วมกับ `biz_st_stock_card` ได้ (ไม่บังคับ)
