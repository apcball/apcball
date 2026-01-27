# Job Cost Lines Creation Fix

## ปัญหา
ฟังก์ชัน `action_create_job_cost_lines` ใน BOQ model ไม่ทำงาน ไม่สามารถสร้าง job cost lines จาก BOQ lines ได้

## สาเหตุเดิม
1. **ไม่มีการ Return Action**: ฟังก์ชันไม่ return ผลลัพธ์ให้ผู้ใช้เห็น
2. **ไม่มีการตรวจสอบข้อมูล**: ไม่ตรวจสอบว่ามี BOQ lines หรือไม่
3. **ไม่มีการจัดการ Duplicate**: ไม่ตรวจสอบว่ามี job cost lines อยู่แล้วหรือไม่
4. **ไม่มี Error Handling**: ไม่มีการจัดการ errors อย่างเหมาะสม
5. **ขาด BOQ Line Linking**: ไม่ได้เชื่อมโยง `boq_line_id` ที่มีอยู่แล้ว

## การแก้ไข

### 1. เพิ่มการตรวจสอบข้อมูล
```python
def action_create_job_cost_lines(self):
    """Create job cost lines from BOQ"""
    # Debug logging
    import logging
    _logger = logging.getLogger(__name__)
    _logger.info(f"Creating job cost lines from BOQ: {self.name}")
    
    if not self.job_cost_sheet_id:
        raise ValidationError(_('Please specify a job cost sheet.'))
    
    # Check if there are any BOQ lines with products
    lines_with_products = self.line_ids.filtered(lambda l: l.product_id)
    if not lines_with_products:
        raise ValidationError(_('No BOQ lines with products found to create job cost lines from.'))
```

### 2. เพิ่มการตรวจสอบ Duplicate
```python
# Check if job cost line already exists for this BOQ line
existing_line = self.env['job.cost.line'].search([
    ('cost_sheet_id', '=', self.job_cost_sheet_id.id),
    ('boq_line_id', '=', line.id)
], limit=1)

if existing_line:
    _logger.info(f"Skipping BOQ line {line.id} - job cost line already exists: {existing_line.id}")
    skipped_lines.append(line.description)
    continue  # Skip if already exists
```

### 3. ปรับปรุงการสร้าง Job Cost Lines
```python
cost_line_vals = {
    'cost_sheet_id': self.job_cost_sheet_id.id,
    'cost_type': 'material',
    'product_id': line.product_id.id,
    'name': line.description,
    'planned_qty': line.quantity,
    'uom_id': line.uom_id.id,
    'unit_cost': line.unit_cost,
    'boq_line_id': line.id,  # Link to BOQ line (ที่สำคัญ!)
}
```

### 4. เพิ่ม Error Handling และ Logging
```python
try:
    cost_line = self.env['job.cost.line'].create(cost_line_vals)
    created_lines.append(cost_line.id)
    _logger.info(f"Created job cost line: {cost_line.id}")
except Exception as e:
    _logger.error(f"Error creating job cost line for {line.description}: {str(e)}")
    raise ValidationError(_('Error creating job cost line for %s: %s') % (line.description, str(e)))
```

### 5. เพิ่ม Return Action
```python
# Return action to show the created job cost lines
return {
    'name': _('Job Cost Lines'),
    'type': 'ir.actions.act_window',
    'res_model': 'job.cost.line',
    'view_mode': 'tree,form',
    'domain': [('id', 'in', created_lines)],
    'context': {'res_model': 'job.cost.line'},
}
```

### 6. ปรับปรุงข้อความ Error
```python
if not created_lines:
    if skipped_lines:
        raise ValidationError(_('No new job cost lines were created. The following lines already exist: %s') % ', '.join(skipped_lines))
    else:
        raise ValidationError(_('No new job cost lines were created. They may already exist.'))
```

## ผลลัพธ์

1. **ฟังก์ชันทำงานได้**: สามารถสร้าง job cost lines จาก BOQ lines ได้อย่างถูกต้อง
2. **ป้องกัน Duplicate**: ตรวจสอบและข้าม lines ที่มีอยู่แล้ว
3. **การเชื่อมโยงที่ถูกต้อง**: `boq_line_id` เชื่อมโยงกับ BOQ line อย่างถูกต้อง
4. **Error Handling**: จัดการ errors และแสดงข้อความที่เข้าใจได้
5. **Comprehensive Logging**: ช่วยในการ debug และติดตามการทำงาน
6. **ผลลัพธ์ที่เห็นได้**: แสดงรายการ job cost lines ที่สร้างขึ้น

## การทดสอบ

1. **เตรียมข้อมูล**:
   - สร้าง BOQ ที่มี BOQ lines พร้อม products
   - สร้าง Job Cost Sheet
   - เชื่อมโยง BOQ กับ Job Cost Sheet

2. **ทดสอบการสร้าง**:
   - กดปุ่ม "Create Job Cost Lines" ใน BOQ form
   - ตรวจสอบว่าระบบแสดงรายการ job cost lines ที่สร้างขึ้น

3. **ทดสอบ Duplicate Prevention**:
   - กดปุ่ม "Create Job Cost Lines" อีกครั้ง
   - ตรวจสอบว่าระบบแสดงข้อความว่า lines มีอยู่แล้ว

4. **ตรวจสอบการเชื่อมโยง**:
   - ดูที่ job cost lines ว่ามี `boq_line_id` ถูกต้อง
   - ตรวจสอบข้อมูลอื่น ๆ ว่าถูก copy อย่างถูกต้อง

## หมายเหตุ

- **UI Integration**: ปุ่ม "Create Job Cost Lines" มีอยู่แล้วใน BOQ form header
- **Prerequisites**: BOQ ต้องมี `job_cost_sheet_id` และ BOQ lines ต้องมี `product_id`
- **Logging**: เพิ่ม comprehensive logging เพื่อ troubleshooting
- **Field Mapping**: การ mapping fields ถูกต้องตาม model definition ของ `job.cost.line`

## ไฟล์ที่แก้ไข

- `models/boq.py` - ปรับปรุงฟังก์ชัน `action_create_job_cost_lines`
