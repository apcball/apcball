# Prompt: สร้าง Odoo 17 Module สำหรับ Export รายงาน DP เป็น Excel

## Objective

สร้าง custom module สำหรับ Odoo 17 เพื่อ export รายงาน DP จากหน้า Sale Order เป็นไฟล์ Excel (.xlsx)

Report ต้องถูกเรียกจากหน้า Sale Order เพราะต้องดึงข้อมูลจาก:
- Sale Order
- Customer / Billing Address / Shipping Address
- Invoice
- Delivery Order / Picking
- Sale Order Lines

## Module Name

`mogen_report_dp_excel`

## Odoo Version

Odoo 17 Community / Enterprise

## Main Model

ใช้ model หลักเป็น:

```python
sale.order
Report Location

เพิ่มปุ่มหรือ action ในหน้า Sale Order:

เมนู Print
ชื่อรายงาน: DP Excel Report
Export เป็น .xlsx
Dependencies
depends = [
    "sale_management",
    "account",
    "stock",
]
Required Feature

เมื่อผู้ใช้เปิด Sale Order แล้วกด Print > DP Excel Report ระบบต้อง generate Excel โดยใช้ข้อมูลจาก Sale Order ปัจจุบัน

Data Mapping
Header Data

ดึงข้อมูลจาก Sale Order:

Field	Odoo Field
เลขที่ SO	sale.order.name
วันที่ SO	sale.order.date_order
ลูกค้า	sale.order.partner_id.name
ที่อยู่ลูกค้า	sale.order.partner_id.contact_address
Billing Address	sale.order.partner_invoice_id.contact_address
Shipping Address	sale.order.partner_shipping_id.contact_address
Salesperson	sale.order.user_id.name
Invoice Data

ดึงจาก:

sale.order.invoice_ids

ข้อมูลที่ต้องใช้:

Field	Odoo Field
Invoice No	invoice.name
Invoice Date	invoice.invoice_date
Invoice Amount	invoice.amount_total
Invoice State	invoice.payment_state

ใช้เฉพาะ invoice ที่ไม่ถูก cancel:

invoice.state != "cancel"
Delivery / DO Data

ดึงจาก:

sale.order.picking_ids

ข้อมูลที่ต้องใช้:

Field	Odoo Field
DO No	picking.name
Scheduled Date	picking.scheduled_date
Delivery Status	picking.state
Product Line Data

ดึงจาก:

sale.order.order_line

ไม่เอา section/note:

not line.display_type

ข้อมูลที่ต้องแสดง:

Column	Odoo Field
ลำดับ	running number
Product Code	line.product_id.default_code
Description	line.name
Quantity	line.product_uom_qty
UoM	line.product_uom.name
Unit Price	line.price_unit
Subtotal	line.price_subtotal
Tax	line.price_tax
Total	line.price_total
Excel Layout

ไฟล์ Excel ต้องเป็นแนวนอน คล้ายรายงานในภาพตัวอย่าง

Sheet Name
DP Report
Page Setup
Paper size: A4
Orientation: Landscape
Fit to width: 1 page
Fit to height: automatic
Font หลัก: TH Sarabun New หรือ fallback เป็น Arial
Header row ต้องมี border
ทุก cell ในตารางต้องมี border
ตัวเลขชิดขวา
วันที่ format เป็น dd/mm/yyyy
จำนวนเงิน format เป็น #,##0.00
Excel Columns

สร้างตาราง columns ตามนี้:

No	Column Name
1	ลำดับ
2	วันที่ SO
3	SO No
4	Invoice No
5	DO No
6	Customer
7	Billing Address
8	Shipping Address
9	Product Code
10	Description
11	Quantity
12	UoM
13	Unit Price
14	Subtotal
15	Tax
16	Total
Technical Requirement

ใช้ xlsxwriter ในการสร้าง Excel

สร้าง report class แบบ abstract model:

class ReportDPExcel(models.AbstractModel):
    _name = "report.mogen_report_dp_excel.report_dp_xlsx"

ใช้ method:

def generate_xlsx_report(self, workbook, data, records):
Expected Files

สร้าง module structure ดังนี้:

mogen_report_dp_excel/
├── __init__.py
├── __manifest__.py
├── report/
│   ├── __init__.py
│   ├── report_dp_xlsx.py
│   └── report_action.xml
└── security/
    └── ir.model.access.csv
Report Action

สร้าง report action ที่ bind กับ sale.order

<field name="model">sale.order</field>
<field name="binding_model_id" ref="sale.model_sale_order"/>
<field name="binding_type">report</field>
Output Filename

ชื่อไฟล์ export:

DP_Report_<SO Number>.xlsx

ตัวอย่าง:

DP_Report_S00045.xlsx
Validation

ต้องรองรับกรณี:

Sale Order ไม่มี invoice
Sale Order ไม่มี delivery order
Sale Order มี invoice หลายใบ
Sale Order มี delivery order หลายใบ
Sale Order มีหลาย product lines
Field บางตัวเป็นค่าว่าง ต้องไม่ error