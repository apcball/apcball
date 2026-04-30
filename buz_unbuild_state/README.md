# Buz Unbuild State Module for Odoo 17

**เพิ่ม state "Picking" สำหรับ Unbuild Orders**

## 📋 Overview

โมดูลนี้ขยายฟีเจอร์ Unbuild Orders ของ Odoo Manufacturing โดยเพิ่ม state "Picking" ระหว่าง Draft กับ Done เพื่อเป็นขั้นตอนรอเบิกของที่จะ unbuild

## 🎯 ปัญหาที่แก้ไข

### ปัญหาเดิม
- Unbuild Orders ใน Odoo มาตรฐานมีแค่ 2 states: `draft` และ `done`
- กด Done ผิดพลาดได้ง่าย เพราะไม่มีขั้นตอนตรวจสอบก่อน
- ไม่มีการบันทึกว่าได้เบิกของแล้วหรือยัง

### วิธีแก้ไข
- เพิ่ม state `picking` ระหว่าง `draft` กับ `done`
- ให้ User สร้าง Picking เพื่อเบิกของก่อน unbuild
- ถ้ามี Picking ต้อง Validate ก่อนจึง Mark Done ได้

## 🔄 Workflow ใหม่

```
┌─────────┐    Create     ┌─────────┐    Validate    ┌─────────┐
│  Draft  │ ──Picking──→ │ Picking │ ───Picking───→ │  Done   │
└─────────┘               └─────────┘                 └─────────┘
     │                                               ↑
     └────────────── Mark Done (ข้าม picking) ────────┘
```

### สถานะทั้งหมด
1. **Draft** — สถานะเริ่มต้น สร้าง unbuild order
2. **Picking** — รอเบิกของ (สร้าง picking แล้ว)
3. **Done** — เสร็จสิ้น unbuild

## 🎯 ฟีเจอร์

### 1. Create Picking
- สร้าง Internal Transfer อัตโนมัติ
- Link picking กับ unbuild order
- เปลี่ยน state เป็น `picking`

### 2. Mark Done
- ตรวจสอบว่ามี picking หรือไม่
- ถ้ามี picking ต้อง Validate ก่อน
- ถ้าไม่มี picking ทำได้เลย

### 3. Open Picking
- เปิด picking ที่เชื่อมไว้
- ดูสถานะการเบิกของ

## 🏗️ Module Structure

```
buz_unbuild_state/
├── __init__.py
├── __manifest__.py
├── README.md
├── security/
│   └── security.xml           # User groups & record rules
├── models/
│   ├── __init__.py
│   ├── mrp_unbuild.py         # ขยาย unbuild model
│   └── stock_picking.py       # ขยาย picking model
└── views/
    └── mrp_unbuild_views.xml  # Tree, Form, Search views
```

## 📊 Data Models

### `mrp.unbuild` (Extended)
Fields ใหม่ที่เพิ่มเข้ามา:

| Field | Type | Description |
|-------|------|-------------|
| picking_id | Many2one → stock.picking | เชื่อมกับ picking |
| picking_count | Integer | จำนวน picking (computed) |
| state | Selection | เพิ่ม `picking` state |

### `stock.picking` (Extended)
Fields ใหม่ที่เพิ่มเข้ามา:

| Field | Type | Description |
|-------|------|-------------|
| unbuild_id | Many2one → mrp.unbuild | เชื่อมกับ unbuild |

## 🔘 ปุ่มใหม่

### บน Unbuild Order Form

| ปุ่ม | สถานะ | คำอธิบาย |
|------|-------|----------|
| **Create Picking** | state = draft, ไม่มี picking | สร้าง picking |
| **Mark Done** | state = draft หรือ picking | ปิด unbuild |
| **Open Picking** | มี picking | เปิด picking |

## 🛡️ Security

### User Groups

- **Buz Unbuild User** (`group_buz_unbuild_user`):
  - สร้าง/แก้ไข unbuild orders
  - สร้าง/validate picking
  - Inherits: Manufacturing User

- **Buz Unbuild Manager** (`group_buz_unbuild_manager`):
  - Full access ทุกอย่าง
  - Inherits: Buz Unbuild User

### Record Rules (Multi-company)

- Unbuild Orders: `[('company_id', 'in', company_ids)]`

## 📦 Dependencies

```python
'depends': [
    'mrp',      # Manufacturing
    'stock',    # Inventory/Picking
]
```

## 🚀 Installation

1. Copy `buz_unbuild_state` folder to your Odoo addons path
2. Update module list in Odoo
3. Install "Buz Unbuild State" module

## ⚙️ Configuration

ไม่ต้องตั้งค่าเพิ่มเติม ใช้ได้ทันทีหลังติดตั้ง

## 📝 Usage Guide

### สร้าง Unbuild Order

1. ไปที่ **Manufacturing → Operations → Unbuild Orders**
2. คลิก **New**
3. เลือก **Product** และ **Bill of Material**
4. ใส่ **Quantity**
5. คลิก **Save**

### สร้าง Picking (Optional)

1. เปิด Unbuild Order
2. คลิก **Create Picking**
3. System สร้าง Internal Transfer อัตโนมัติ
4. ตรวจสอบ picking แล้วคลิก **Validate**

### ปิด Unbuild Order

**วิธีที่ 1: ผ่าน Picking**
1. Validate picking
2. Unbuild เป็น Done อัตโนมัติ

**วิธีที่ 2: Mark Done โดยตรง**
1. คลิก **Mark Done** (เฉพาะเมื่อไม่มี picking)

## 🔧 Technical Notes

### State Transitions

```python
# อนุญาตให้เปลี่ยน state เฉพาะ:
'draft' → 'picking'     # สร้าง picking
'draft' → 'done'        # ข้าม picking
'picking' → 'done'      # validate picking แล้ว
```

### Picking Creation Logic

1. ค้นหา Internal Picking Type
2. กำหนด Source Location (Stock)
3. กำหนด Destination Location (Production)
4. สร้าง Stock Move
5. Link กับ Unbuild Order

### Auto Done on Picking Validate

เมื่อ Validate picking ที่ link กับ unbuild:
```python
def button_validate(self):
    res = super().button_validate()
    # อัปเดต unbuild เป็น done
    done_pickings = self.filtered(
        lambda p: p.state == 'done' and p.unbuild_id
    )
    done_pickings.mapped('unbuild_id').write({'state': 'done'})
    return res
```

## 📄 License

LGPL-3

## 👥 Authors

- AI-DEV-Module-Odoo17
- Website: https://github.com/apcball/AI-DEV-Module-Odoo17

---

*Last updated: 2026-04-29*
