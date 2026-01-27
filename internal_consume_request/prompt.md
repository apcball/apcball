PROMPT (ต่อยอด) — Auto Reject Stock ไม่พอ + รองรับหลาย Warehouse

คุณคือ Senior Odoo 17 Developer (Enterprise-level)
พัฒนา Custom Module Odoo 17 ชื่อ internal_consume_request
สำหรับระบบ ขอเบิกอุปกรณ์สิ้นเปลืองภายในบริษัท

1) Feature เพิ่มเติม (Mandatory)
A. Auto Reject เมื่อ Stock ไม่พอ

ตรวจ stock ตอนกด Submit และ ก่อน Create Picking

ถ้า qty_requested > available_qty

เปลี่ยน state เป็น rejected

บันทึกเหตุผล: reason = "Stock ไม่เพียงพอ"

ส่ง Mail / Activity แจ้งผู้ขอทันที

ไม่อนุญาตให้ Approve หรือ Create Picking ถ้า stock ไม่พอ

B. รองรับหลาย Warehouse

ผู้ขอเลือก Warehouse ได้เองในเอกสาร

ระบบเปลี่ยน:

location_id = warehouse.lot_stock_id

picking_type_id = Internal Transfer ของ warehouse นั้น

Stock availability คำนวณ ตาม warehouse ที่เลือกเท่านั้น

Delivery สร้างจาก warehouse ที่เลือก

2) Model เพิ่ม / แก้ไข
internal.consume.request

เพิ่ม field:

warehouse_id (required, selectable)

reason (Text)

has_insufficient_stock (Boolean, compute)

allow_submit (Boolean, compute)

ปรับ compute:

available_qty คำนวณจาก

stock.quant

filter location_id child_of warehouse.lot_stock_id

3) Stock Validation Logic
Compute Stock
available_qty = sum(
    quant.quantity - quant.reserved_quantity
    for quant in quants
)


quants:

product_id

location_id child_of warehouse.lot_stock_id

company_id

Auto Reject Logic
action_submit()

loop line:

ถ้า stock ไม่พอ → call action_auto_reject()

ถ้าผ่านทั้งหมด → ส่ง Approve

action_auto_reject(reason)

state = rejected

create message_post

create mail.activity to employee

4) Approval Constraint

ห้าม Approve ถ้า:

has_insufficient_stock = True

Raise UserError

5) Views (UX)

แสดง:

Stock คงเหลือ (per warehouse)

Highlight สีแดง ถ้าไม่พอ

Disable:

ปุ่ม Submit / Approve ถ้า stock ไม่พอ

แสดง reason เมื่อ rejected

6) Picking Creation Logic

Picking ต้อง:

warehouse ตรงกับ request

source = warehouse.lot_stock_id

partner = employee

origin = request.name

ถ้า stock เปลี่ยนก่อนสร้าง picking:

auto reject

7) Security / Record Rule (ไม่เปลี่ยน)
8) Output จาก AI (อัปเดต)

Python models (multi-warehouse + auto reject)

View แสดง stock per warehouse

Constraint & validation

Production-ready code

ใช้ best practice Odoo 17
ห้าม hardcode warehouse / location
หลีกเลี่ยง SQL ตรง ยกเว้นจำเป็นจริง