# Tax Invoice for Expenses - User Guide

## Overview
โมดูล `l10n_th_expense_tax_invoice` เพิ่มฟิลด์ Tax Invoice Number และ Tax Invoice Date ให้กับ HR Expense เพื่อรองรับการระบุข้อมูลใบกำกับภาษี

## Features Added

### 1. ฟิลด์ใหม่ใน Expense
- **Tax Invoice Number**: หมายเลขใบกำกับภาษีจากผู้ขาย
- **Tax Invoice Date**: วันที่ใบกำกับภาษีจากผู้ขาย

### 2. การแสดงผล
- ฟิลด์จะแสดงในหน้า Expense Form เมื่อมีการเลือก Tax
- ฟิลด์จะมีใน Tree View แต่ซ่อนไว้ (optional="hide")
- ฟิลด์จะแสดงใน Expense Sheet Tree View

### 3. Integration กับ Thai Tax Module
- ระบบจะนำข้อมูล Tax Invoice จาก Expense ไปใส่ใน Journal Entry โดยอัตโนมัติ
- หากไม่มีข้อมูล Tax Invoice ระบบจะไม่แสดง error สำหรับ Expense (แต่จะแสดงสำหรับเอกสารอื่น)

## วิธีการใช้งาน

### 1. สร้าง Expense ใหม่
1. ไปที่ Expenses > My Expenses > Create
2. เลือก Product และใส่จำนวนเงิน
3. เลือก Tax (VAT 7% หรืออื่นๆ)
4. เมื่อเลือก Tax แล้ว จะเห็นส่วน "Tax Invoice Information"
5. ใส่ Tax Invoice Number และ Tax Invoice Date

### 2. การ Post Journal Entry
- เมื่อ Expense Sheet ถูก Post จะไม่เกิด error "Please fill in tax invoice number and tax invoice date"
- ข้อมูล Tax Invoice จะถูกบันทึกใน Journal Entry โดยอัตโนมัติ

## ตัวอย่างการใช้งาน
```
Product: Office Supplies
Amount: 1,070 THB
Tax: VAT 7% (70 THB)
Tax Invoice Number: TAX-2024-001
Tax Invoice Date: 16/09/2024
```

## การแก้ปัญหา
หากยังพบ error ให้ตรวจสอบ:
1. โมดูล l10n_th_expense_tax_invoice ถูกติดตั้งแล้ว
2. มีการ Restart Odoo Server
3. Expense มีการระบุ Tax Invoice Number และ Date ครบถ้วน