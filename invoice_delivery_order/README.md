# Invoice Delivery Order

## Version
17.0.1.1.0

## Summary
เพิ่ม field **Delivery Order** บน Customer Invoice เพื่อ link เอกสาร DO กับ Invoice และแสดง DO number บน PDF

## Features

### 1. DO Selector บน Invoice Form
- ตำแหน่ง: หน้า Customer Invoice → ล่าง Journal
- Widget: `many2many_tags` dropdown เลือกได้หลาย DO
- **Smart Pick**: กรองเฉพาะ DO ที่เกี่ยวข้องอัตโนมัติ
  - Invoice ผูกกับ SO → แสดงเฉพาะ DO ของ SO นั้น (outgoing + done)
  - Invoice ไม่ผูก SO → fallback แสดง DO ทั้งหมดของ partner ที่ done
- **Draft**: แก้ไข/เพิ่ม/ลบได้
- **Posted/Cancelled**: readonly ล็อกไว้

### 2. DO บน PDF Invoice
- แสดง DO number ใต้ส่วน informations ของ invoice PDF
- แสดงเฉพาะ `out_invoice` (Customer Invoice)

## Dependencies
- `account`
- `stock`
- `sale`

## Technical

### Models
| Model | Field | Type | Description |
|-------|-------|------|-------------|
| `account.move` | `picking_ids` | Many2many → `stock.picking` | DO ที่เลือก |
| `account.move` | `available_picking_ids` | Many2many (compute) | DO ที่เลือกได้ (smart filter) |

### Relation: Invoice → SO → DO
```
account.move.line → sale_line_ids → sale.order.line → order_id → sale.order → picking_ids
```

### Files
```
invoice_delivery_order/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   └── account_move.py
├── views/
│   └── invoice_view.xml
├── report/
│   └── invoice_report.xml
└── security/
    └── ir.model.access.csv
```

## Changelog

### 17.0.1.1.0
- Smart Pick: กรอง DO อัตโนมัติจาก SO ที่ผูกกับ invoice
- เพิ่ม `sale` dependency

### 17.0.1.0.0
- Initial release
- DO selector บน invoice form
- DO number บน PDF invoice
