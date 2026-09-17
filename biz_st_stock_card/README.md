# biz_st_stock_card — สต๊อกการ์ด (Stock Card)

รายงานบัญชีคุมสินค้าแบบ **ยอดยกมา / รับ / จ่าย / คงเหลือ** ทั้งจำนวนและมูลค่า
แยกตามคลังสินค้า กางดูรายการเคลื่อนไหวรายบรรทัดพร้อมยอดคงเหลือสะสมได้
ออกได้ทั้งหน้าจอ PDF และ Excel

Odoo Community ไม่มีรายงานลักษณะนี้ — **Moves History** ให้รายการดิบแต่ไม่มียอดยกมา
ไม่มียอดคงเหลือสะสมและไม่มีมูลค่า ส่วน **Valuation** ให้มูลค่าอย่างเดียวและแยกคลังไม่ได้

## เครื่องยนต์เดียว สามช่องทาง

```
biz.stock.card.report.get_report_data(options)     ← แหล่งความจริงเดียว
   ├── OWL client action  biz_st_stock_card.stock_card
   ├── QWeb PDF           report.biz_st_stock_card.report_stock_card_doc
   └── XLSX               biz.stock.card.xlsx.generate(options)

biz.stock.card.report.get_product_card(options, product_id)   ← การ์ดสินค้ารายวัน
   └── OWL client action  biz_st_stock_card.product_card
```

**ห้ามเพิ่มเส้นทางคำนวณเส้นที่สอง** ไม่งั้นตัวเลขบนจอกับตัวเลขในไฟล์ที่ส่งผู้ตรวจสอบ
จะเพี้ยนจากกันโดยไม่มีใครรู้ การคำนวณใช้ ORM `_read_group` **ไม่ใช่ raw SQL** เพื่อให้
record rule และ multi-company ทำงานตามปกติ

รายงานหนึ่งครั้งยิง **7 `_read_group` + 4 คิวรีแผนที่มิติ + คิวรีรายละเอียดตามที่กาง**
จำนวนคิวรีไม่ขึ้นกับจำนวนสินค้าหรือจำนวนคลัง

## สถาปัตยกรรม: แตกที่ระดับ fact แล้วค่อย pivot

`group_mode` (คลัง→สินค้า / สินค้า→คลัง) **เป็นเพียงการนำเสนอ** ไม่ใช่โค้ดคนละเส้น
เครื่องยนต์สร้าง fact table เดียว key = `(บริษัท, คลัง, สินค้า, ที่เก็บ, ล็อต)` โดยการโอน
ข้ามคลังถูกแตกเป็น **OUT ของคลังต้นทาง + IN ของคลังปลายทาง ตั้งแต่ตอนสร้าง fact**
(core ทำแบบเดียวกันใน `stock/report/report_stock_quantity.py`) แล้วจึง pivot ตาม
ลำดับระดับที่ผู้ใช้เลือก การสลับแกนจึงได้ตัวเลขเท่ากันเสมอ — มีเทสยืนยันข้อนี้

กฎการปล่อย fact (generalise มาจาก `stock_account/_compute_warehouse_id`):

> ที่มาเป็นของคงคลัง → ปล่อย OUT ที่โหนดต้นทาง
> ที่ไปเป็นของคงคลัง → ปล่อย IN ที่โหนดปลายทาง
> ทั้งคู่เป็นของคงคลังและตกโหนดเดียวกัน → ไม่ปล่อยอะไรเลย

| การเคลื่อนไหว | ไม่กางที่เก็บ | กางที่เก็บ |
|---|---|---|
| ผู้ขาย → คลัง A | IN ที่คลัง A | IN ที่ A/Stock |
| คลัง A → ลูกค้า | OUT ที่คลัง A | OUT ที่ A/Stock |
| คลัง A → คลัง B | OUT A + IN B | เหมือนกัน (รายที่เก็บ) |
| A/Stock → A/Shelf2 | **ไม่ปรากฏ** | OUT + IN หักล้างกันที่คลัง A |

`counts_to_total` เป็นจริง **เฉพาะแถวระดับบนสุด** ซึ่งเป็น partition ของ fact table
โดยโครงสร้าง ทั้งสองโหมด ทุกความลึกการพับ — ยอดรวมจึงพิสูจน์ได้ว่าไม่นับซ้ำ และ
สูตร `SUMPRODUCT` ใน Excel ให้ตัวเลขตรงกับหน้าจอเป๊ะ

## การกระทบยอดมูลค่า

`stock.valuation.layer` (SVL) ไม่มีมิติคลัง/ที่เก็บ/ล็อต และ**ไม่มีฟิลด์วันที่**
เครื่องยนต์จึง:

* ใช้ `stock_move_id.date` เป็นวันที่ของชั้นมูลค่า fallback เป็น `create_date`
  (โมดูล `biz_mrp_backdate` ใช้กฎเดียวกันในชื่อ `x_effective_date`)
* แยก SVL เป็น 4 ก้อนต่อ (บริษัท, สินค้า): ยกมา / รับ (qty>0) / จ่าย (qty<0) /
  **ปรับมูลค่า (qty=0)** ซึ่งมีคอลัมน์ของตัวเอง ไม่แอบยัดเข้ายอดรับ
* กระจายลงต้นไม้ตามสัดส่วนจำนวน โดย**ตัวหารมาจากชุดที่ไม่ผ่านตัวกรองคลัง** —
  กรองคลังเดียวแล้วคลังนั้นจึงไม่ได้รับมูลค่าของทั้งสินค้าไปทั้งก้อน
* ตีมูลค่าการโอนภายในเป็น**คู่ด้วยต้นทุนเดียวกัน** (`value_mode="imputed"`) ทั้งสองขา
  จึงหักล้างกันที่ระดับบริษัท

`closing_value = opening_value + in_value − out_value + adj_value`

รายงานแสดงผลการกระทบยอดให้เห็นทุกครั้ง ไม่ใช่คำแก้ตัวแต่เป็น**ข้อพิสูจน์**:

```
checks.svl_period_value      Σ SVL.value ทั้งงวด จาก _read_group ตรง ๆ
checks.report_period_value   Σ (in_value_ext − out_value_ext + adj_value) ของแถวระดับบนสุด
checks.svl_difference        ต้องเป็น 0.00
checks.svl_reconciled        → ชิปเขียว/แดงบนจอ, กล่องใน PDF, ชีตใน Excel
checks.svl_scope_limited     กรองคลังไว้ → กระทบยอดทั้งบริษัทไม่ได้ (แจ้งเป็นข้อมูล ไม่ใช่ error)
checks.imputed_internal      มูลค่าประมาณของการโอนภายใน + ยอดสุทธิ (ควรเป็น 0)
checks.interwarehouse        จำนวนบรรทัด/ปริมาณที่ถูกนับสองครั้งโดยตั้งใจ
```

## ตัวกรอง

| กลุ่ม | ตัวเลือก |
|---|---|
| ช่วงเวลา | `date_from` / `date_to` (เขตเวลาผู้ใช้), `date_format` พ.ศ./ค.ศ. |
| บริษัท | `company_ids`, `company_mode` = `consolidated` / `split` |
| แกน | `group_mode` = `wh_product` / `product_wh` |
| ระดับเสริม | `group_categ`, `group_location`, `group_lot` |
| ขอบเขต | `warehouse_ids`, `location_ids`, `product_ids`, `categ_ids`, `lot_ids`, `picking_type_ids` |
| ชนิดรายการ | `include_inventory`, `include_scrap`, `include_consignment` |
| มูลค่า | `show_value`, `value_mode`, `value_date_basis`, `opening_basis` |
| การแสดง | `display_product`, `unfold_level`, `unfolded`, `detail_mode`, `detail_limit` |

`_normalize_options()` clamp/whitelist ทุกคีย์ที่ข้ามเขต RPC และ **client รับค่าที่
server normalize แล้วไปใช้แทนของเดิม** (`this.state.options = data.options`) จอกับ
เซิร์ฟเวอร์จึงไม่มีวันเข้าใจตัวกรองไม่ตรงกัน — `_normalize_options` เป็น idempotent

## การกางรายละเอียด (lazy)

แถวกลุ่มมาจาก `_read_group` จำนวนคงที่ซึ่งเบา แต่**แถวรายการเคลื่อนไหวดึงเฉพาะกิ่งที่กาง**
ไม่มี RPC `expand_line` แยก — การกดกางแก้ `options.unfolded` แล้วเรียก `get_report_data`
ตัวเดิม (หลัก "เครื่องยนต์เดียว") หน้าจอคงตารางเดิมไว้ระหว่างโหลด การกางจึงไม่กะพริบ

รูปแบบ row id เป็น path: `wh-3/categ-7/prod-45/loc-12/lot-0/mvl-9912`
`parent_id` = path ตัดท้ายหนึ่งช่วง, `level` = ความลึก − 1, PDF/XLSX flatten ด้วย `level`

## การ์ดสินค้ารายวัน (Product Card)

**กดที่ชื่อสินค้า** ในตารางรายงาน → เปิดหน้าใหม่ (มีปุ่มย้อนกลับและ breadcrumb) ที่อ่านสินค้า
ตัวนั้นเป็นไทม์ไลน์รายวัน: **รับเข้า / จ่ายออก / เปลี่ยนแปลง / คงเหลือสะสม** พร้อม
**ราคาต่อหน่วยของวันนั้น** และมูลค่าคงเหลือ — ตอบคำถาม "ของหายไปวันไหน" ได้ในจอเดียว

การ์ดเป็น **ช่องทางที่สี่ของเครื่องยนต์เดิม ไม่ใช่เส้นทางคำนวณเส้นที่สอง**:

* ยอดของสินค้า (ยกมา/รับ/จ่าย/คงเหลือ ทั้งจำนวนและมูลค่า) มาจาก `_ledger_nodes()` +
  `_allocate_value()` ตัวเดิมทั้งดุ้น **การ์ดจึงเท่ากับแถวสินค้าในรายงานหลักเสมอ** (มีเทสคุม)
* แถวรายวันเกิดจาก `_read_group` ตัวเดียวที่เพิ่มมิติ `date:day` แล้วส่งเข้า
  **`_emit_fact_row()` ตัวเดียวกับรายงานหลัก** กฎการปล่อย fact จึงมีที่เดียว
  (การโอนข้ามคลังยังนับสองครั้งเหมือนเดิม และแบนเนอร์ `checks.interwarehouse` ยังอธิบายได้)
* คิวรีรายวันต้อง `with_context(tz=...)` เพราะ `date` เป็น Datetime เก็บ UTC —
  ไม่ตั้งเขตเวลาให้ตรงกับ `_period_bounds()` ของที่รับตอนสี่ทุ่มจะตกไปอยู่วันถัดไป
* **ออกเฉพาะวันที่มีการเคลื่อนไหว** (ไม่ปูแถวศูนย์ทุกวันในช่วง)

**ราคาต่อหน่วย** มาจาก SVL ของวันนั้นจริง ๆ (`Σ value / Σ quantity` ของวัน — `unit_cost`
มี `group_operator=None` รวมยอดไม่ได้) ส่วน **มูลค่าในแถว** ถูกบังคับให้รวมกันเท่ากับยอด
ของสินค้าที่เครื่องยนต์คำนวณไว้เสมอ โดยกระจายตามน้ำหนัก "จำนวน × ราคาของวันนั้น" แล้วยัด
เศษเข้าวันสุดท้าย (`_spread_to_days()` — หลักการเดียวกับ `_spread()` ที่ระดับโหนด)
มูลค่าที่ระบุวันไม่ได้ (landed cost / ปรับราคาต้นทุนที่ไม่ผูกกับ move) ไปลงคอลัมน์
**ปรับมูลค่า** ของวันสุดท้าย ไม่หายเงียบ ๆ — การ์ดพิสูจน์ตัวเองด้วย
`checks.qty_reconciled` และ `checks.value_reconciled` ทุกครั้ง

รายงานที่กรองคลังไว้: **มูลค่า** เป็นส่วนแบ่งของคลังที่เลือกตามสัดส่วนจำนวน (เหมือนรายงานหลัก)
แต่ **ราคาต่อหน่วย** ยังเป็นต้นทุนจริงระดับบริษัทของวันนั้น — แบนเนอร์บนจอบอกข้อนี้ตรง ๆ

การ์ดยังไม่มี PDF/Excel โดยตั้งใจ — wizard เดิมครอบเคสนี้ได้ด้วยการกรองสินค้า

## สิทธิ์

* เปิดรายงานได้: `stock.group_stock_user` (ไม่มีสิทธิ์ → `AccessError`)
* เห็นคอลัมน์มูลค่า: `account.group_account_readonly` **หรือ** `stock.group_stock_manager`
  (override `_can_see_value()` ตัวเดียวถ้าต้องการนโยบายอื่น)
* ACL ของ `stock.valuation.layer` ใน core ให้เฉพาะ stock manager ผู้ใช้ฝ่ายบัญชีจึงอ่าน
  ผ่าน `sudo()` **เฉพาะเมื่อผ่าน `_can_see_value()` แล้ว** และ `company_ids` ผ่าน
  `_resolve_company_ids()` (ตรวจกับ `user.company_ids`) มาก่อนแล้วเสมอ
* ผู้ใช้ที่ไม่มีสิทธิ์มูลค่า **ไม่เจอ error** — ได้สต๊อกการ์ดเฉพาะจำนวนที่ใช้งานได้เต็มที่
  พร้อม `checks.value_hidden_reason`
* ทุกคิวรีผ่าน `_scoped()` ซึ่งตั้ง `allowed_company_ids` — ir.rule ของ stock อิง
  `env.companies` ถ้าไม่ตั้งให้ตรงกับบริษัทที่ผู้ใช้ขอ รายงานจะคืนข้อมูลว่างเปล่าอย่างเงียบ ๆ

## ข้อจำกัดที่ทราบ

1. **มูลค่าแม่นที่ (บริษัท, สินค้า) — ต่ำกว่านั้นเป็นการเฉลี่ย** SVL ไม่มีมิติคลัง/ที่เก็บ/ล็อต
   มูลค่ารายคลังคือการกระจายตามสัดส่วนจำนวน ยอดระดับบริษัทและระดับสินค้าแม่นเสมอ
   และพิสูจน์ได้ทุกครั้งด้วย `checks.svl_reconciled`
2. **การโอนภายในไม่มี SVL** — `value_mode="imputed"` (ตั้งต้น) ตีมูลค่าเป็นคู่ที่หักล้างกัน
   ทั้งบริษัท; `value_mode="svl"` ให้มูลค่า 0 และยอดมูลค่ารายคลังจะไม่สะท้อนการโอน
3. **สินค้า FIFO** — ต้นทุนที่ประมาณเป็นค่าเฉลี่ยถ่วงน้ำหนัก ไม่ใช่การไล่ layer
   (เฉพาะส่วนโอนภายในเท่านั้นที่ประมาณ มูลค่ารับ/จ่ายกับภายนอกเป็นตัวเลข SVL จริง)
4. **SVL ไม่มีฟิลด์วันที่** — landed cost ที่ลงทีหลังหลายเดือนจะตกงวดของ **ใบรับ**
   ไม่ใช่งวดที่ลงบัญชี สลับด้วย `value_date_basis="svl_create"` ถ้าต้องกระทบยอดกับ GL
   ตามงวดที่ลงบัญชี
5. **`in_qty`/`out_qty` นับการโอนข้ามคลังสองครั้งโดยตั้งใจ** เพราะเป็นการจ่ายออกจริงของ
   คลังต้นทางและการรับเข้าจริงของคลังปลายทาง — `opening_qty`/`closing_qty` ไม่กระทบ
   ดู `checks.interwarehouse`
6. **รายงานที่กรองคลัง/ที่เก็บกระทบยอดกับ SVL ทั้งบริษัทไม่ได้** (`checks.svl_scope_limited`)
   เพราะ SVL ไม่มีมิติคลัง — รายงานแจ้งเป็นข้อมูล ไม่ใช่ฟ้องว่าตัวเลขผิด
7. **จำนวนทั้งหมดเป็น UoM อ้างอิงของสินค้า** (`quantity_product_uom`) แถวรายละเอียด
   ไม่แสดงจำนวนในหน่วยเดิมของบรรทัด (บรรทัดหน่วยโหลจะแสดงเป็นชิ้น)
8. **ปิดการปรับปรุงยอดหรือของเสียทำให้สมการบัญชีคุมไม่จริง** — ยังแสดงผลแต่ขึ้นแบนเนอร์แดง
   ทุกช่องทาง (`checks.balance_broken_by_filter`) ทั้งจำนวนและมูลค่าถูกตัดพร้อมกัน
   จึงยังไม่ขัดกันเอง
9. **สินค้าฝากขาย (consignment) ไม่นับโดยตั้งต้น** ตาม `_should_exclude_for_valuation()`
   ของ core จำนวนกับมูลค่าจึงไม่ขัดกัน
10. **บรรทัดที่ปริมาณเป็นศูนย์ไม่แสดง** — ไม่มีผลต่อยอดใด ๆ และเป็นแถวขีดกลางทั้งบรรทัด
11. **คิวรียอดยกมาสแกนประวัติทั้งหมดก่อน `date_from`** โมดูลเพิ่ม index
    `stock_move_line_stock_card_idx (company_id, product_id, date) WHERE state='done'`
    ให้แล้ว บน DB ใหญ่มากให้กรองสินค้าหรือใช้ `opening_basis="none"`
12. **แถวรายละเอียดถูกจำกัดจำนวน** (`detail_limit` ต่อกลุ่ม, `detail_total_limit` รวม)
    แถว `more` ถือยอดที่เหลือไว้ ยอดคงเหลือสะสมจึงยังจบที่ยอดจริงของกลุ่ม
13. **`detail_mode="all"` ต้องมีตัวกรองสินค้า/หมวด/ล็อต** ไม่งั้นถูกลดระดับอัตโนมัติ
    พร้อม `checks.detail_downgraded`
14. **หลายสกุลเงินบวกกันโดยไม่แปลงค่า** พร้อมแบนเนอร์ — พฤติกรรมเดียวกับ `biz_ac_trial_balance`
15. **สินค้า `consu`/`service` ไม่รวม** — ไม่มีบัญชีคุม
16. **ขอบงวดเป็นเขตเวลาของผู้ใช้** แปลงเป็น UTC ครั้งเดียวใน `_normalize_options`
    ผู้ใช้คนละเขตเวลารันช่วงวันเดียวกันจะได้ผลต่างกัน (`options.tz` ถูก echo กลับให้เห็น)

## เมนู

Inventory → Reporting → **สต๊อกการ์ด (Stock Card)** (หน้าจอ interactive)
Inventory → Reporting → **พิมพ์สต๊อกการ์ด (PDF / Excel)** (wizard)

**การ์ดสินค้ารายวัน ไม่มีเมนูของตัวเอง** — เปิดด้วยการกดชื่อสินค้าในรายงานเท่านั้น เพราะมันต้อง
สืบทอดตัวกรองของรายงานที่กำลังดูอยู่ ถ้ามีเมนูแยกผู้ใช้จะได้การ์ดที่ตัวกรองไม่ตรงกับจอที่มา

ทั้งสองอยู่ใต้ `stock.menu_warehouse_report` ซึ่ง core กำหนดเป็น `group_stock_manager`
ใส่ `group_stock_user` ที่เมนูจะได้เมนูที่มองไม่เห็น ซึ่งดูเหมือนบั๊ก

## PDF ภาษาไทย

ฟอนต์ Sarabun ถูกฝังเป็น base64 ตรงใน CSS เพราะคอนเทนเนอร์ `odoo:17.0` ไม่มีฟอนต์ไทย
ติดตั้งเลย ถ้าไม่ฝัง ตัวอักษรไทยจะกลายเป็นกล่องว่างทั้งหน้า

**ห้ามใส่ single-quote ในสตริง `SARABUN_FONT_CSS`** — QWeb จะ escape เป็น `&#39;`
แล้ว wkhtmltopdf อ่าน `@font-face` ไม่ออก ฟอนต์จะไม่ถูกฝังโดยไม่มี error ใด ๆ
มีเทสยืนยันข้อนี้ (`test_pdf_html_embeds_the_thai_font_without_escaped_quotes`)

## Excel

3 ชีต: **สต๊อกการ์ด** (ต้นไม้เยื้องตามระดับ + คอลัมน์ตัวช่วยซ่อน + ยอดรวมเป็น
`=SUMPRODUCT()`), **สรุประดับบนสุด**, **ข้อสังเกต** (`checks` ทั้งหมดเป็นภาษาไทย)

ไม่ใส่ autofilter โดยตั้งใจ — หัวตารางเป็นเซลล์ merge สองแถวซึ่ง Excel มักฟ้องว่าไฟล์เสีย
และการกรองชีตที่มีแถวรวมแทรกอยู่ให้ภาพที่ชวนเข้าใจผิด

## การทดสอบ

91 เทส ใน 5 ไฟล์ — จำนวน / มูลค่า / การจัดกลุ่ม / สิทธิ์และการส่งออก / การ์ดสินค้ารายวัน

```bash
docker stop dev-odoo-1
docker run --rm --network dev_default \
  -e HOST=db -e PORT=5432 -e USER=odoo -e PASSWORD='biz@0709' \
  -v /root/odoo17/dev/addons:/mnt/extra-addons \
  biz-odoo17-dev:17.0 odoo -d odoo-dev \
  --addons-path=/mnt/extra-addons,/usr/lib/python3/dist-packages/odoo/addons \
  --data-dir=/tmp/odoo-data --stop-after-init --max-cron-threads=0 \
  -u biz_st_stock_card --test-enable --test-tags '/biz_st_stock_card'
docker start dev-odoo-1
```

`odoo-dev` มีข้อมูลจริงอยู่แล้ว เทสจึงสร้าง fixture ของตัวเอง (คลัง/สินค้าใหม่) และ
ยืนยันกับ fixture นั้นเท่านั้น **ห้าม assert ค่าสัมบูรณ์ทั้งระบบ**

เทสที่คุ้มค่าจะอ่านก่อนแก้โค้ด:

* `test_closing_matches_qty_available_oracle` — ยืนยันกับ oracle อิสระของ core
* `test_both_group_modes_produce_identical_totals` / `..._leaf_measures`
* `test_counts_to_total_rows_sum_to_grand_total` — ทั้งสองโหมด × สามความลึกการพับ
* `test_period_value_reconciles_to_svl_in_both_modes` — invariant หลักของมูลค่า
* `test_product_with_valuation_but_no_movement_still_reconciles`
* `test_warehouse_filter_does_not_overstate_value`
* `test_period_boundary_respects_user_timezone`
* `test_company_outside_user_access_is_refused` — ต้องถอด auto-link ของ
  `res.company.create()` ออกก่อน ไม่งั้นเทสผ่านเพราะเหตุผลที่ผิด
* `test_requested_company_works_even_when_not_in_the_switcher` — กับดัก ir.rule
* `test_card_totals_match_product_row_in_main_report` — invariant ของการ์ดสินค้า
* `test_unit_cost_is_the_price_of_that_day` — ราคาต้องเป็นของวันนั้น ไม่ใช่ค่าเฉลี่ยงวด
* `test_day_boundary_respects_user_timezone` (การ์ด) — กับดัก tz ของ `date:day`

## Dependencies

`stock`, `stock_account` (hard — มูลค่าเป็นข้อกำหนดหลัก ไม่ใช่ตัวเลือก)
Python: `xlsxwriter`
