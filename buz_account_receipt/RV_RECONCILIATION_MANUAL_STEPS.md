# คู่มือ: Reconcile Payment ใน RV ให้ Invoice เป็น Paid

## สถานการณ์ปัจจุบัน
- Invoice IV-2507417 มีสถานะ **"IN PAYMENT"** (สีเขียว)
- Payment PBK01/2025/00001 ถูก post แล้ว จำนวน 1,620.00 ฿
- แต่ payment ยังไม่ได้ reconcile กับ invoice

## วิธีแก้ไข (หลังจาก restart service แล้ว)

### วิธีที่ 1: ใช้ RV Confirm (แนะนำ - อัตโนมัติ)

1. **ไปที่ Receipt Voucher (RV/2025/0003)**
2. **กดปุ่ม "Confirm"** หรือ "Register Payments"
3. ระบบจะ:
   - ✅ หา existing payment PBK01/2025/00001
   - ✅ Link payment เข้ากับ voucher lines
   - ✅ **Auto-reconcile payment กับ invoice IV-2507417**
   - ✅ Invoice จะเปลี่ยนเป็น **"PAID"** โดยอัตโนมัติ

### วิธีที่ 2: Reconcile ด้วยตนเอง (Manual)

หากวิธีที่ 1 ไม่ได้ผล ให้ทำตามนี้:

1. **ไปที่ Invoice IV-2507417**
2. คลิก tab **"Journal Items"** (รายการบัญชี)
3. จะเห็น line ที่มี Account = **"111003 Outstanding Receipts"** หรือ **"Accounts Receivable"**
4. เลือก line ทั้ง 2 ที่ต้องการ reconcile:
   - Line จาก Invoice (Debit/Credit)
   - Line จาก Payment (Credit/Debit)
5. คลิกปุ่ม **"Reconcile"** หรือ **"จับคู่"**
6. Invoice จะเปลี่ยนเป็น **"PAID"**

### วิธีที่ 3: จาก Payment (แนบทางนี้ได้)

1. **ไปที่ Payment PBK01/2025/00001**
2. คลิก tab **"Journal Items"**
3. หา line ที่มี Account = **"114200"** หรือ **"111003 Outstanding Receipts"**
4. คลิก link **"Outstanding Receipts"** หรือไปที่ **"Reconcile Items"**
5. เลือก Invoice IV-2507417 เพื่อ reconcile

## สาเหตุที่เกิดปัญหา

### เดิม:
- Payment ถูกสร้างเป็น "outstanding payment" (on-account)
- ไม่ได้ link โดยตรงกับ invoice เฉพาะเจาะจง
- Method `_reconcile_payment_with_invoices` เดิมมีปัญหา:
  - เช็คเฉพาะ `account_type == 'asset_receivable'` 
  - ข้าม line ที่ `reconciled is False`
  - ไม่รองรับ outstanding payment account

### หลังแก้ไข:
- ✅ เช็ค account_type หลายแบบ: `asset_receivable`, `liability_payable`, และ `reconcile = True`
- ✅ รองรับ outstanding payment
- ✅ Reconcile แบบ grouped by account
- ✅ มี error handling ไม่ให้ระบบ crash
- ✅ มี logging เพื่อ debug

## ตรวจสอบผลลัพธ์

### Invoice ควรแสดง:
- ✅ สถานะ: **"PAID"** (ribbon สีเขียว)
- ✅ Amount Due: **0.00 ฿**
- ✅ Payment Status: **"Paid"**
- ✅ Related Payments: เห็น PBK01/2025/00001

### Payment ควรแสดง:
- ✅ สถานะ: **"Posted"**
- ✅ Reconciled: **Yes** (ถ้ามี field นี้)
- ✅ Related Invoices: เห็น IV-2507417

### RV ควรแสดง:
- ✅ สถานะ: **"Confirmed"**
- ✅ Payment State: **"Paid"** หรือ **"Partial"**
- ✅ Existing Payments: เห็น PBK01/2025/00001 linked

## Troubleshooting

### หาก Invoice ยังเป็น "IN PAYMENT" หลัง Confirm RV

1. **ตรวจสอบ Odoo Log:**
```bash
sudo tail -f /var/log/odoo/instance1.log | grep -i reconcile
```

2. **ดู Account Move Lines:**
   - ไปที่ Invoice → Tab "Journal Items"
   - ตรวจสอบว่า line reconciled หรือยัง

3. **ตรวจสอบ Account Settings:**
   - ไปที่ Accounting → Configuration → Accounts
   - ตรวจสอบ Account 111003 และ 114200
   - ต้องมี **"Allow Reconciliation"** เปิดอยู่

4. **Manual Reconcile:**
   - ไปที่ Accounting → Accounting → Reconciliation
   - เลือก Account 111003 (Outstanding Receipts)
   - หา Payment PBK01/2025/00001 และ Invoice IV-2507417
   - Reconcile ด้วยตนเอง

## Code Changes Summary

### ไฟล์: `models/account_receipt_voucher.py`

#### Method: `_reconcile_payment_with_invoices()`
**เปลี่ยน:**
- ✅ รองรับ outstanding payment accounts
- ✅ เช็ค `account.reconcile = True` แทนเฉพาะ account_type
- ✅ Filter เฉพาะ unreconciled lines
- ✅ Group by account ก่อน reconcile
- ✅ มี try-except error handling
- ✅ เพิ่ม logging ทุกขั้นตอน

**ตัวอย่าง Log ที่จะเห็น:**
```
INFO: Attempting to reconcile 2 lines on account 111003
INFO: Successfully reconciled lines on account 111003
```

หรือ

```
WARNING: No reconcilable lines found for payment PBK01/2025/00001
INFO: No unreconciled invoice lines found to reconcile with payment PBK01/2025/00001
```

## การใช้งานต่อไป

### Workflow ที่แนะนำ:
1. สร้าง Receipt จาก Invoices
2. **กด "Register Batch Payment"** จาก Receipt
3. Post Payment
4. สร้าง RV จาก Receipts
5. **กด "Confirm"** RV → **Auto-reconcile ทันที!**
6. ตรวจสอบ Invoice เป็น "PAID"

### หรือ:
1. สร้าง Receipt + Payment
2. สร้าง RV
3. กด "Register Payment" ใน RV line
4. ระบบจะเปิด "Existing Payments"
5. กลับไปกด "Confirm" RV
6. **Auto-reconcile!**

---

**Status**: ✅ Fixed and Deployed  
**Date**: October 7, 2025  
**Version**: 2.0.1  
**Module**: buz_account_receipt
