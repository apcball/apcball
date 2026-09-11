# Customer Refund PV - Workflow Plan

เอกสารนี้สรุป workflow ปัจจุบันของ Customer Refund PV ใน `buz_accounting_addon` รวมถึงการเปลี่ยนแปลงล่าสุดและผลการส่งขึ้น DEV

## 1. Workflow หลัก

```text
Posted Customer Credit Note
        |
Create Customer Refund PV (Draft)
        |
เลือก Source Invoice ตามที่ฝ่ายบัญชีกำหนด
        |
Confirm Refund PV (Posted)
        |
Register Refund Payment
        |
Post Payment และ Reconcile กับ Credit Note
```

## 2. กติกาหลัก

- Refund PV ต้องอ้างอิง Customer Credit Note (`out_refund`) ที่อยู่ในสถานะ `Posted`
- `Refund Amount` ต้องมากกว่า 0 และไม่เกินยอดคงเหลือของ Credit Note
- Payment ใช้ยอดจาก `Refund Amount` บน Refund PV และผู้ใช้แก้ Amount ใน Register Payment ไม่ได้
- Refund PV ใช้ standard Odoo Payment Register และสร้าง, Post และ Reconcile Payment ตาม flow มาตรฐาน
- เมื่อมี Payment ที่ยัง Active แล้ว จะไม่สามารถ Register Payment ซ้ำสำหรับ Refund PV เดิมได้
- Refund PV แยกจาก Vendor PV, Payment Voucher และ Receipt Voucher
- Bank Fee และ WHT ยังไม่อยู่ใน flow นี้จนกว่าจะมี accounting logic รองรับครบถ้วน

## 3. Payment Difference และ Write-off

หน้าต่าง Register Refund Payment จาก Refund PV แสดงตัวเลือกทั้งสองแบบ แม้ Difference จะเป็น `0.00`:

| ตัวเลือก | ผลลัพธ์ | Difference Account |
|---|---|---|
| Keep open / จ่ายเต็ม | คงส่วนต่างไว้ใน Credit Note | ไม่บังคับ |
| Mark invoice as fully paid / Write-off | ตัดส่วนต่างและปิด Credit Note | ต้องเลือก |

กติกาของ Difference Account:

- แสดงให้เลือกได้ในหน้าต่าง Refund PV ทั้งสองตัวเลือก
- บังคับเลือกเฉพาะเมื่อเลือก `Mark invoice as fully paid`
- กรองบัญชีที่ยัง Active (`deprecated = False`)
- Odoo ใช้ `check_company=True` เพื่อป้องกันบัญชีต่างบริษัท
- ระบบไม่กำหนดบัญชี Other Income ให้ตายตัวจาก context อีกต่อไป

## 4. Source Invoice

Source Invoice เป็นข้อมูลที่ฝ่ายบัญชีเลือกในช่วง Draft โดยระบบตรวจสอบว่า:

- เชื่อมโยงกับ Source Sales Order ผ่าน `sale_line_ids`
- เป็น Customer Invoice (`out_invoice`)
- อยู่ในสถานะ `Posted`
- มีสถานะการชำระเงินเป็น `Paid` และยอดคงเหลือเป็นศูนย์
- เป็นลูกค้าและบริษัทเดียวกับ Refund PV

หลัง Confirm แล้ว Source Invoice จะถูกล็อก และระบบตรวจสอบซ้ำก่อน Register Payment

## 5. การควบคุมข้อมูล

- Posted หรือ Cancelled Refund PV แก้ข้อมูลหลักและ Invoice ต้นทางไม่ได้
- Reset to Draft and Cancel are available to Accounting Users and Accounting Managers through the Reason Wizard.
- ไม่ทำ mass update หรือ backfill ข้อมูลธุรกรรมเดิม
- การ deploy ตามแผนนี้จำกัดเฉพาะ DEV (`MOG_DEV`) ไม่รวม PROD

## 6. การเปลี่ยนแปลงล่าสุด: Payment Difference UI

ไฟล์ที่แก้:

- `buz_accounting_addon/models/customer_refund_pv.py`
  - ยกเลิก default `payment_difference_handling = 'reconcile'`
  - ยกเลิกการส่งบัญชี Other Income เป็นค่าเริ่มต้นแบบบังคับ
- `buz_accounting_addon/views/account_payment_register_inherit_views.xml`
  - แสดง Payment Difference Handling เมื่อเปิดจาก Refund PV แม้ Difference เป็นศูนย์
  - แสดง Difference Account ใน Refund PV
  - บังคับบัญชีเฉพาะเมื่อเลือก Write-off
  - จำกัดบัญชีที่ deprecated แล้วออก

หมายเหตุ: `account_payment_batch_process` ไม่ถูกแก้ เพราะ Refund PV เปิด standard flow ด้วย `batch = False`; behavior ของ Vendor PV และ Receipt Voucher จึงไม่ถูกเปลี่ยนจากงานนี้

## 7. ผลตรวจสอบก่อนส่งขึ้น DEV

วันที่: 2026-09-09 (เวลาไทย)

- Python syntax: ผ่าน
- XML parse: ผ่าน
- `git diff --check`: ผ่าน
- ไม่ได้ทำ live database test ก่อน deploy

## 8. ผลการส่งขึ้น DEV

Target: `root@217.216.32.33`
Database: `MOG_DEV`
Module: `buz_accounting_addon`

- Upload ด้วย `scp` เฉพาะโฟลเดอร์ `buz_accounting_addon`: สำเร็จ
- Upgrade ด้วย `-u buz_accounting_addon --stop-after-init --no-http`: สำเร็จ
- Upgrade log พบ `Modules loaded`, `Registry loaded` และ `Stopping gracefully`
- Restart container `odoo`: สำเร็จ
- Container status: `running`
- HTTP `http://127.0.0.1:8069/web?db=MOG_DEV`: `302`
- HTTP `http://127.0.0.1:8069/web/database/selector`: `200`

ระหว่าง deploy มี validation failure ครั้งแรกเนื่องจาก custom domain อ้าง `company_id` ใน view แต่ field ไม่ผ่าน view validation จึงปรับกลับไปใช้ domain Active มาตรฐานร่วมกับ `check_company=True` แล้ว upgrade สำเร็จ


### 9.1 Customer Refund PV permission for Accounting User

Local-only verification on 2026-09-09:

- Permission checks for Reset to Draft, Cancel, and the Reason Wizard now accept account.group_account_invoice while retaining Accounting Manager.
- Reason, active Payment, and Credit Note reconciliation validations remain unchanged.
- Form buttons and CRUD ACL for the state wizard were updated for Accounting User.
- No deploy, upgrade, or server restart was performed.
- Odoo/database UAT remains pending until deployment is separately authorized.
## 9. UAT ที่ยังค้าง

- เปิด Register Refund Payment จาก Customer Refund PV และตรวจว่าตัวเลือกทั้งสองแบบแสดงจริง
- Credit Note ยอดเต็ม: เลือก Keep open และสร้าง Payment โดยไม่เลือก Difference Account
- ยอดไม่เต็ม: เลือก Write-off และยืนยันว่าต้องเลือก Difference Account
- ตรวจบัญชีต่างบริษัทและบัญชีที่ Archive/Deprecated แล้วว่าเลือกไม่ได้
- ตรวจ Vendor PV และ Receipt Voucher ว่ายังทำงานเหมือนเดิม
- ตรวจผล Payment, Reconciliation และ Journal Entry บนหน้าจอจริง

เอกสารนี้อัปเดตเพื่อบันทึกผลการแก้ไขและการส่งมอบ DEV โดยไม่รวมการ deploy ไป PROD

## 6. POS Lite ที่ไม่มี Source SO หรือ Source Invoice

- หากผู้ใช้เลือก Invoice อ้างอิงเอง ระบบตรวจเฉพาะบริษัท ลูกค้า ประเภท out_invoice และสถานะ Posted โดยไม่บังคับ Paid หรือยอดคงเหลือเป็นศูนย์ และไม่สร้างความสัมพันธ์กับ SO ขึ้นมาเอง
- การตรวจ Invoice อ้างอิงก่อน Confirm/Register Payment ไม่บังคับให้เลือก และการจ่ายเงินจริงยังใช้ Credit Note กับ Refund Amount เป็นหลัก
- Dropdown Invoice อ้างอิงแสดงเฉพาะ Invoice Posted ของบริษัทและลูกค้าเดียวกัน โดยไม่เดาความสัมพันธ์จาก POS Lite, SO หรือ invoice_origin
- การตรวจ Source Invoice ก่อน Register Payment ยังคงทำงานตามเดิม จึงต้องเลือก Invoice ที่ผ่านเงื่อนไขเมื่อจะรับชำระเงิน

## 7. POS Lite Refund PV: Optional Invoice Reference

- Confirm และ Register Refund Payment ไม่บังคับเลือก Source Invoice
- Invoice ที่เลือกเองเป็นข้อมูลอ้างอิงเท่านั้น ระบบตรวจบริษัท ลูกค้า ประเภท out_invoice และสถานะ Posted
- Dropdown แสดง Invoice Posted ของบริษัทและลูกค้าเดียวกัน โดยไม่เดาความสัมพันธ์จาก POS Lite, SO หรือ invoice_origin
- การ Register Payment ใช้ Credit Note และ Refund Amount เป็นเอกสารและยอดหลักตาม standard Odoo Payment Register
- ผลการตรวจ local: ยังไม่ได้ deploy, upgrade หรือ restart server และยังต้องทดสอบด้วย Odoo isolated/local database และ UAT จริง
