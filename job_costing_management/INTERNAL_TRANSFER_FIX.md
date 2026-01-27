# Material Requisition - Internal Transfer Fix

## ปัญหา
หลังจากสร้าง Internal Transfer แล้ว ไม่สามารถดูรายการ Pickings ได้ เนื่องจากไม่มีการเชื่อมโยงระหว่าง Material Requisition Lines กับ Stock Picking ที่สร้างขึ้น

## การแก้ไข

### 1. ปรับปรุงฟังก์ชัน `action_create_picking`
เพิ่มการเชื่อมโยง picking กับ requisition lines:

```python
# หลังจากสร้าง picking แล้ว
picking = self.env['stock.picking'].create(picking_vals)

# เชื่อมโยง picking กับ requisition lines
for line in internal_lines:
    line.picking_ids = [(4, picking.id)]
```

### 2. ปรับปรุงฟังก์ชัน `_compute_picking_count`
เพิ่มการค้นหา picking ทั้งจากการเชื่อมโยงและจาก origin:

```python
def _compute_picking_count(self):
    for record in self:
        # Get all picking IDs from requisition lines
        picking_ids = record.line_ids.mapped('picking_ids.id')
        # Also search for pickings by origin
        pickings_by_origin = self.env['stock.picking'].search([('origin', '=', record.name)])
        picking_ids.extend(pickings_by_origin.ids)
        # Remove duplicates
        picking_ids = list(set(picking_ids))
        record.picking_count = len(picking_ids)
```

### 3. ปรับปรุงฟังก์ชัน `action_view_pickings`
เพิ่มการค้นหา picking ที่ครอบคลุมทั้งสองวิธี:

```python
def action_view_pickings(self):
    # Get all picking IDs from requisition lines
    picking_ids = self.line_ids.mapped('picking_ids.id')
    # Also search for pickings by origin
    pickings_by_origin = self.env['stock.picking'].search([('origin', '=', self.name)])
    picking_ids.extend(pickings_by_origin.ids)
    # Remove duplicates
    picking_ids = list(set(picking_ids))
    
    return {
        'name': 'Internal Transfers',
        'type': 'ir.actions.act_window',
        'res_model': 'stock.picking',
        'view_mode': 'tree,form',
        'domain': [('id', 'in', picking_ids)],
        'context': {'default_picking_type_code': 'internal'},
    }
```

### 4. เพิ่มการ Debug และ Logging
เพิ่มการ log เพื่อติดตามการทำงาน:

```python
import logging
_logger = logging.getLogger(__name__)
_logger.info(f"Material Requisition {self.name}: Found {len(picking_ids)} pickings: {picking_ids}")
```

## วิธีทดสอบ

1. **สร้าง Material Requisition**:
   - เพิ่ม requisition lines ที่มี `requisition_action = 'internal'`
   - กดปุ่ม "Create Internal Transfer"

2. **ตรวจสอบการเชื่อมโยง**:
   - ดูที่ smart button "Pickings" ว่าแสดงจำนวนถูกต้องหรือไม่
   - กดปุ่ม "Pickings" เพื่อดูรายการ internal transfers

3. **ตรวจสอบ Logs**:
   - ดู server logs เพื่อดูข้อมูล debug
   - ตรวจสอบว่า picking IDs ถูกต้องหรือไม่

## ผลลัพธ์ที่คาดหวัง

- Smart button "Pickings" จะแสดงจำนวน picking ที่ถูกต้อง
- เมื่อกดปุ่ม "Pickings" จะเปิดรายการ internal transfers ที่เกี่ยวข้อง
- สามารถเข้าไปดูรายละเอียด picking ได้
- การเชื่อมโยงทำงานได้ทั้งการค้นหาด้วย origin และการเชื่อมโยงโดยตรง

## หมายเหตุ

การแก้ไขนี้ใช้วิธีการค้นหา picking ทั้งสองวิธี:
1. **Direct Link**: ผ่าน `picking_ids` field ใน requisition lines
2. **Origin Search**: ค้นหาจาก `origin` field ใน stock.picking

วิธีนี้ช่วยให้มั่นใจว่า picking ที่สร้างขึ้นจะถูกแสดงใน smart button ได้อย่างถูกต้อง
