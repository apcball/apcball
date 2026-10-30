# Budget & Payment Control Dashboard (`biz_dashboard_ap_payment`)

Dashboard ควบคุมงบประมาณและยอดจ่าย สำหรับ Odoo 17 Community
เมนู: **Purchase > Budget Control > Budget & Payment Control** และ **Accounting > Reporting > Budget & Payment Control**

สิทธิ์: ผู้ใช้ในกลุ่ม *Monthly Budget User* (`biz_monthly_analytic_budget`) หรือ *Accounting / Invoicing* (`account.group_account_invoice`)

## ตัวกรอง
เดือน / ปี / บริษัท / โครงการ (`project.project`) / ร้านค้า-ผู้ขาย — กดปุ่ม **กรองข้อมูล** จึงจะโหลดใหม่

## นิยามข้อมูล

| ส่วน | แหล่งข้อมูล | สูตร |
|---|---|---|
| 1. ยอดจ่ายประจำเดือน | ใบแจ้งหนี้ผู้ขาย (`account.move` ประเภท in_invoice / in_refund, สถานะ posted) ที่ **วันครบกำหนด** (`invoice_date_due` หรือ `invoice_date`) อยู่ในเดือนที่เลือก | รวม = ยอดรวมบิล (ใบลดหนี้ติดลบ), ชำระแล้ว = รวม − คงค้าง, ค้างชำระ = `amount_residual` |
| เงินสด / เครดิต | Payment term ของบิล | **เงินสด** = ทุกบรรทัดของ term เป็น 0 วัน (ทันที), หรือวันครบกำหนด ≤ วันที่ใบแจ้งหนี้; ที่เหลือ = **เครดิต**. บิลที่ไม่มี payment term ตัดสินจากวันครบกำหนดอย่างเดียว (ครบกำหนดหลังวันที่บิล = เครดิต); PO ที่ไม่มี term ถือเป็นเงินสด |
| รายสัปดาห์ | วันครบกำหนดของบิล | สัปดาห์ 1 = วันที่ 1-7, 2 = 8-14, 3 = 15-21, 4 = 22-สิ้นเดือน |
| 2. ยอดการใช้งบประมาณ | บรรทัดงบ `monthly.budget.line` ของแผน `monthly.budget.plan` ที่ confirmed ในเดือนนั้น (`biz_monthly_analytic_budget`) | อนุมัติ = Σ amount, ผูกพัน PO = Σ amount_reserved, ใช้จริง = Σ amount_used, คงเหลือ = อนุมัติ − ผูกพัน − ใช้จริง, % = (ผูกพัน + ใช้จริง) / อนุมัติ. กรองตามโครงการได้ (ผ่าน `line.project_id`), ไม่กรองตามร้านค้า; ตารางโครงการใช้งบจากบรรทัดงบ และตารางหมวดมีแถว CapEx/OpEx |
| 3. ขออนุมัติงบเพิ่มเติม | `buz.monthly.budget.approval.request` ที่สร้าง (`create_date`) ในเดือนนั้น สถานะ pending / approved / rejected | ยอด = `amount_requested` (ยอดเอกสารที่ขอ) — ไม่ใช้ `amount_overage` เพราะเป็นส่วนเกินสะสมของบรรทัดงบ ณ ตอนที่ขอ รวมแล้วนับซ้ำ; ร้านค้า/โครงการจาก PO ที่อ้างอิง |
| 4. ประมาณการเดือนถัดไป | (ก) บิลที่ posted และยังไม่จ่าย (`payment_state` not_paid / partial) ครบกำหนดเดือนหน้า → ยอดคงค้าง, (ข) PO ที่ยืนยันแล้ว `payment_date` อยู่เดือนหน้า และยังตั้งบิลไม่ครบ → ยอดที่เหลือตั้งบิล | เงินสด / เครดิตตาม payment term ของบิล / PO |
| คอลัมน์งบอนุมัติ / ใช้แล้ว / คงเหลือ (ต่อร้านค้า, โครงการ, หมวด) | PO ที่ยืนยันแล้ว (purchase / done) ที่ `payment_date` อยู่ในเดือนที่เลือก | งบอนุมัติ = ยอดรวม PO, ใช้แล้ว = ตั้งบิลแล้ว, คงเหลือ = ยังไม่ตั้งบิล |
| หมวดค่าใช้จ่าย | หมวดสินค้า (`product.category`) ของบรรทัดบิล / PO; ไม่มีสินค้า → ผังบัญชีของบรรทัด | ภาษีและเศษปัดจากยอดบิลแสดงในแถว "ภาษี / ปัดเศษ" เพื่อให้ยอดรวมของแท็บเท่ากับการ์ด |

หมายเหตุ
- ยอด PO (ตั้งบิลแล้ว / ยังไม่ตั้งบิล) คำนวณจากบรรทัด PO (ก่อนภาษี, หักจำนวนที่ตั้งบิลแล้วที่ไม่ยกเลิก) จึงถูกคูณสัดส่วนภาษีของ PO เพื่อให้เทียบกับยอดรวมบิลได้ (ปิดได้ที่ค่าคงที่ `GROSS_UP_PO` ใน `models/ap_dashboard.py`)
- ตัวเลขทั้งหมดแปลงเป็นสกุลเงินของบริษัทที่เลือก (หรือบริษัทหลักของผู้ใช้เมื่อเลือก "ทั้งหมด")
- ปีแสดงเป็น ค.ศ.

## ความเร็ว / Cache
- ผลลัพธ์ถูก cache ฝั่ง server ต่อชุดตัวกรอง (ต่อ worker) เป็นเวลา 120 วินาที — ปรับได้ที่ System Parameter `biz_dashboard_ap_payment.cache_ttl` (วินาที, `0` = ปิด cache)
- ปุ่ม **รีเฟรช** (ลูกศรวน มุมขวาบน) โหลดข้อมูลสดโดยไม่ใช้ cache; เวลาข้าง "ข้อมูล ณ วันที่" คือเวลาที่คำนวณข้อมูลชุดนั้น
- ตรวจสิทธิ์และขอบเขตบริษัททุกครั้งก่อนอ่าน cache; Export ใช้ข้อมูลชุดเดียวกับที่แสดงบนจอ
- รายการตัวกรอง (โครงการ / ร้านค้า) cache แยก นานสูงสุด 10 นาที

## Export Excel
ปุ่ม **Export** (มุมขวาบน) หรือ **ดาวน์โหลดรายละเอียด** (เหนือตาราง) — ชีต "สรุป" + ชีตตามแท็บที่เลือก หรือทุกชีต

## โครงสร้าง
- `models/ap_dashboard.py` — engine (`biz.ap.dashboard`, AbstractModel): กรอง, รวมยอด, สร้างไฟล์ xlsx
- `controllers/ap_dashboard_api.py` — `/ap_dashboard/api/data` (JSON), `/ap_dashboard/api/export` (xlsx)
- `static/src/` — OWL component + Chart.js (จาก `web`)
- `tests/test_ap_dashboard.py` — baseline-delta tests

```
docker exec odoo_kyld odoo -c /etc/odoo/odoo.conf -d KYLD-DEV -u biz_dashboard_ap_payment \
    --test-enable --test-tags /biz_dashboard_ap_payment --stop-after-init --max-cron-threads=0
```

> หมายเหตุ: ไม่พึ่ง `biz_weekly_budget` (ใช้ `payment_date` จาก `biz_monthly_analytic_budget`; ยอดค้างตั้งบิลคำนวณในตัว dashboard)
