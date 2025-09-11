# Account WHT Installment (TH) — Odoo 17

**Purpose:** จ่ายเจ้าหนี้แบบทยอยจ่าย (Installments) พร้อมหักภาษี ณ ที่จ่าย (WHT) ได้ในคลิกเดียว
โดยโมดูลจะสร้างรายการบัญชี 3 เส้นอัตโนมัติใน Bank Journal:
- Dr Accounts Payable (ยอดที่จะตัดออกจากบิล) — *ลดหนี้*
- Cr Bank/Cash (ยอดที่จ่ายสุทธิ)
- Cr WHT Payable (ยอดภาษีหัก ณ ที่จ่ายที่ต้องนำส่งกรมสรรพากร)

จากนั้นระบบจะ reconcile เส้น AP (debit) กับบิล (credit) ให้แบบ partial

## การติดตั้ง
1. คัดลอกโฟลเดอร์ `account_wht_installment` ไปไว้ใน `custom-addons/`
2. Update Apps list แล้วติดตั้งโมดูล
3. ไปที่ Accounting Settings ตั้งค่า:
   - **WHT Payable Account (TH)** = บัญชีเจ้าหนี้ภาษีหัก ณ ที่จ่าย
   - **Default WHT %** = ค่ามาตรฐาน เช่น 3%

## การใช้งาน
- เปิด Vendor Bill (ต้องโพสต์แล้ว และยังไม่จ่ายครบ)
- กดปุ่ม **Installment Payment (WHT)** บน header
- เลือก Bank/Cash Journal, ใส่ยอดที่ต้องการตัด (gross), อัตรา WHT, วันที่, memo
- กด Confirm → ระบบจะสร้าง Bank JE + Reconcile ให้ทันที

## หมายเหตุ
- เวอร์ชันแรกนี้ถือว่าสกุลเงินของบริษัทและบิลตรงกัน (ไม่มี FX) — สามารถต่อยอดเพิ่ม multi-currency ได้
- ถ้าต้องการพิมพ์หนังสือรับรองฯ แนะนำใช้ร่วมกับชุดโมดูล OCA Thailand (l10n_th_*)
