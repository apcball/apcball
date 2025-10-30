# Prompt Engineering: Implement Module `buz_easy_transfer_plus`

## 🎯 Objective
สร้างโมดูล **`buz_easy_transfer_plus`** สำหรับ **Odoo 17 Community**  
เพื่อเพิ่มความสามารถของระบบ Inventory มาตรฐาน โดยไม่แตะ workflow หรือ core code ของ `stock`  

เน้นเพิ่มฟังก์ชัน 2 ส่วนหลัก:
1. **หน้าใบ Transfer (`stock.picking`)** → ปุ่ม “Select All Products”, “Clear Lines”, “Transfer Now”  
2. **หน้า Batch Transfers (`stock.picking.batch`)** → ปุ่ม “Create Transfer” เพื่อสร้างใบ Internal Transfer อัตโนมัติ โดยใช้ Destination ของ Batch เป็น Source ของใบใหม่

---

## 📦 Module Information
**Module Name:** buz_easy_transfer_plus  
**Version:** 17.0.2.0.0  
**License:** LGPL-3  
**Depends:** `stock`  
**Category:** Inventory / Stock Management  
**Author:** Ball (MOGEN)  

---

## 🧩 Features Summary

### 🧱 A. ส่วนของใบ Transfer (`stock.picking`)
- ปุ่ม **Select All Products**  
  → ดึงสินค้าทั้งหมดจาก Source Location (stock.quant)
- ปุ่ม **Clear Lines**  
  → ล้างรายการสินค้าทั้งหมดในใบ Transfer
- รองรับ multi-company / multi-warehouse
- ไม่แตะ workflow เดิม (`action_confirm`, `button_validate`)

---

### 🧱 B. ส่วนของ Batch Transfers (`stock.picking.batch`)
- ปุ่ม **Create Transfer**  
  → เปิด wizard ให้เลือก “Destination Location”
  → ระบบสร้างใบ Internal Transfer ใหม่ โดย:
    - Source Location = Destination ของ Batch
    - Destination Location = ที่เลือกใน wizard
    - สินค้าในใบใหม่ = รายการสินค้าใน Batch
- ใช้สำหรับ “ย้ายสินค้าที่รับจาก Batch ไปอีก Location หนึ่ง” ได้สะดวก
- สร้างใบ Transfer พร้อมเปิดหน้าฟอร์มทันที

---

## 📂 Directory Structure
buz_easy_transfer_plus/
├── init.py
├── manifest.py
├── models/
│ ├── init.py
│ ├── stock_picking.py
│ └── stock_picking_batch.py
├── wizard/
│ ├── init.py
│ └── transfer_from_batch_wizard.py
└── views/
├── stock_picking_views.xml
├── stock_picking_batch_views.xml
└── wizard_transfer_from_batch_views.xml

🧪 Test Scenarios
หน้าจอ	Action	ผลลัพธ์
Internal Transfer	กด “Select All Products”	ดึงสินค้าทั้งหมดจาก Source Location
Internal Transfer	กด “Clear Lines”	ล้างรายการทั้งหมด
Batch Transfer	กด “Create Transfer”	เปิด wizard
Wizard	เลือก Destination Location แล้วกด “Create Transfer”	สร้างใบ Internal Transfer ใหม่จาก Batch

