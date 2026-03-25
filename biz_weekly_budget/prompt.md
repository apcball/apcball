แนวคิดใหม่ของ Budget

จากเดิม

PR / MR / RFQ → Reserved
PO Confirm → Used

เปลี่ยนเป็น

PR / MR / RFQ → Reserved
PO Confirm → Reserved
Vendor Bill Created → Used

และ

Used Budget Date = Bill Due Date

นี่คือ Accrual / Cashflow Budget Hybrid

Flow ใหม่ของ Budget
1️⃣ PR Approve
Budget Type = Reserved
date = expected_payment_date
2️⃣ PO Confirm

ยังเป็น

Reserved

เพราะเงินจริงยังไม่เกิด

3️⃣ Create Vendor Bill

ตอน create bill

Reserved → Used

และ

Used Date = invoice_date_due
Budget Lifecycle ใหม่
PR Approve
     │
     ▼
Reserved Budget

PO Confirm
     │
     ▼
Still Reserved

Vendor Bill
     │
     ▼
Used Budget
Example จริง
Weekly Budget
Week 1 Budget = 1,000,000
PR
PR = 200,000
Expected Payment = Week 1

Budget

Reserved = 200,000
Used = 0
Available = 800,000
PO Confirm
PO = 200,000

Budget

Reserved = 200,000
Used = 0
Available = 800,000

ไม่เปลี่ยน

Create Bill
Bill Amount = 200,000
Due Date = Week 3

Budget จะกลายเป็น

Week 1
Reserved = 0

Week 3
Used = 200,000

นี่คือ Cashflow Forecast จริง

Architecture ที่ต้องเพิ่ม

ต้อง extend model

account.move
(type = in_invoice)
field ที่ต้องใช้
invoice_date_due
amount_total
invoice_origin
purchase_id
Hook ที่ต้องเขียน

ใน

account.move

override

action_post()

pseudo code

def action_post(self):

    res = super().action_post()

    for bill in self:
        if bill.move_type == 'in_invoice':
            self._update_budget_usage()

    return res
Function update budget

logic

def _update_budget_usage(self):

    payment_date = self.invoice_date_due

    budget_line = self.env['weekly.budget.line'].find(payment_date)

    amount = self.amount_total

    create transaction:

        type = used
        date = payment_date
        amount = amount

    release reserved from PO
ต้องแก้ Reserved Calculation

Reserved ต้องรวม

PR
MR
RFQ
PO Confirmed (no bill yet)
Query Logic
Reserved
PR Approved
MR Submitted
RFQ Draft
PO Confirmed (bill not created)
Used
Vendor Bills Posted
Dashboard จะดีขึ้นมาก

ตอนนี้ dashboard เป็น

Budget vs Used

ใหม่จะเป็น

Budget vs Forecast Cashflow
Dashboard Example
Week 1

Limit     1,000,000
Reserved  600,000
Used      100,000
Available 300,000
ข้อดีของแนวคิดนี้
Feature	Result
Budget ใกล้เงินจริง	⭐⭐⭐⭐⭐
Cashflow Forecast	⭐⭐⭐⭐⭐
PO Overcommit ลด	⭐⭐⭐⭐
Management decision	⭐⭐⭐⭐⭐
Edge Case ที่ต้องคิด
1️⃣ Bill Partial

PO

100,000

Bill

50,000

Budget

Used = 50,000
Reserved = 50,000
2️⃣ Multiple Bills

PO

100,000

Bill

30,000
30,000
40,000

Budget

Used = 100,000
Reserved = 0
3️⃣ Cancel Bill
release used
back to reserved
สิ่งที่ผมแนะนำเพิ่ม (สำคัญ)

เพิ่ม field ใน PO

billed_amount
remaining_to_bill

Odoo มีอยู่แล้ว

invoice_status

ใช้ได้เลย

ผมแนะนำ architecture แบบนี้
Budget Reserved
    │
    ├─ PR
    ├─ MR
    ├─ RFQ
    └─ PO

Budget Used
    │
    └─ Vendor Bill
Feature ที่จะเทพมากถ้าทำเพิ่ม
Budget Cashflow Projection

ระบบจะรู้

Future Cash Outflow

จาก

Bill Due Date

สามารถทำ chart

Cash Outflow Forecast
สรุป

Design ใหม่คือ

Commitment Budget + Cashflow Budget

ระดับ

Enterprise ERP

