implement ฟีเจอร์ Refill Advance Box ในโมดูล Odoo 17 โดยมีรายละเอียดทั้งหมดดังนี้:

🎯 Objective

ต้องการสร้างกระบวนการ “เติมเงินเข้ากล่อง Advance Box” โดยใช้ Payment Transfer จาก Bank Journal ไปยัง Advance Box Journal อย่างถูกต้องตามบัญชี และเชื่อมข้อมูลกับ Advance Box Record โดยอัตโนมัติ

📦 Models to Implement
1) advance.box

ฟิลด์:

name (Char)

journal_id (Many2one → account.journal) ประเภท = cash / petty cash

balance (Monetary, compute)
คำนวณยอดเงินคงเหลือจากข้อมูล JE ในบัญชีของ journal ที่ผูกกับกล่อง

2) advance.box.refill

สำหรับเก็บประวัติการเติมเงินเข้ากล่อง
ฟิลด์:

box_id (Many2one → advance.box)

amount (Float)

payment_id (Many2one → account.payment)

state (Selection: draft / posted)

date

เมื่อ state = posted ต้องหมายถึง:

Payment transfer ถูกสร้างและ posted สำเร็จ

เงินเข้า advance box แล้ว

🪄 Wizard Requirement

สร้าง wizard: wizard.refill.advance.box

ฟิลด์ wizard:

box_id

journal_bank_id (Many2one → account.journal, domain type = bank)

amount

date

ปุ่ม:

Confirm Refill

🔄 Wizard Logic

เมื่อกดปุ่ม Confirm:

1) สร้าง Payment Transfer

ใช้ model account.payment:
{
  'payment_type': 'transfer',
  'journal_id': journal_bank_id.id,
  'destination_journal_id': box_id.journal_id.id,
  'amount': amount,
  'date': date,
  'ref': 'Refill Advance Box: %s' % box_id.name,
}
หลังจากสร้างต้อง:

payment.action_post()

ผลลัพธ์ทางบัญชี:
Dr Advance Box Journal Account
   Cr Bank Account

2) บันทึกประวัติใน advance.box.refill

สร้าง record:
{
    'box_id': box_id.id,
    'amount': amount,
    'payment_id': payment.id,
    'state': 'posted',
    'date': date,
}

3) อัปเดตยอดคงเหลือของกล่อง

ให้ balance บน advance.box คำนวณจาก JE ที่ผูกกับ journal ของกล่อง:

debit - credit สะสมของบัญชีใน journal นั้น
🖼️ XML Requirement
1) Menu

เพิ่มเมนู:
Accounting
 └─ Advance Box
      ├─ Advance Box
      ├─ Refill History
      └─ Refill Box (wizard)

2) View ของ Wizard

ฟอร์ม: box, bank journal, amount, date + ปุ่ม Confirm

🧾 Security

สร้าง access rule:

accountant, manager สามารถ refill ได้

user ธรรมดาอ่านข้อมูลได้อย่างเดียว

✔️ Expected Deliverables

ให้ AI สร้างสิ่งต่อไปนี้ครบ:

Python models

Wizard .py

Wizard XML views

Menu XML

Security rules

Logic การคำนวณ balance

การสร้าง payment transfer อัตโนมัติ

📌 ความสำคัญ

ห้ามใช้ JE โดยตรง ให้ใช้ Payment Transfer เท่านั้น

ต้อง link payment กับ refill record

ต้องออกแบบให้รองรับ multi-company

ต้องรองรับ multi-currency

ต้องรองรับ rounding standard ของ Odoo
