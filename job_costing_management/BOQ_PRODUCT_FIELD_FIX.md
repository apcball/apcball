# BOQ Product Field Fix

## ปัญหา
เมื่อใช้ฟังก์ชัน `action_create_boq` เพื่อสร้าง BOQ จาก template แล้ว product field ใน BOQ lines เป็นค่าว่าง

## สาเหตุ
1. **BOQ Template Line** และ **BOQ Line** ไม่ได้กำหนด `product_id` เป็น `required=True`
2. ผู้ใช้สามารถสร้าง template lines ที่ไม่มี product ได้
3. เมื่อ copy จาก template มา product จึงเป็นค่าว่าง
4. ไม่มีการตรวจสอบความครบถ้วนของข้อมูลก่อนสร้าง BOQ

## การแก้ไข

### 1. กำหนด Product เป็น Required Field

#### BOQ Line Model:
```python
# Item information
item_code = fields.Char(string='Item Code')
product_id = fields.Many2one('product.product', string='Product', required=True)
description = fields.Text(string='Description', required=True)
specification = fields.Text(string='Specification')
```

#### BOQ Template Line Model:
```python
# Item information
item_code = fields.Char(string='Item Code')
product_id = fields.Many2one('product.product', string='Product', required=True)
description = fields.Text(string='Description', required=True)
specification = fields.Text(string='Specification')
```

### 2. เพิ่มการตรวจสอบใน Create Method

```python
# Create BOQ lines from template lines
if template_id:
    template = self.env['boq.template'].browse(template_id)
    if template.exists():
        # Validate template has lines with products
        if not template.line_ids:
            raise ValidationError(_('Template has no lines to copy.'))
        
        lines_without_products = template.line_ids.filtered(lambda l: not l.product_id)
        if lines_without_products:
            raise ValidationError(_('Template has lines without products. Please ensure all template lines have products assigned.'))
        
        result._create_lines_from_template(template)
```

### 3. ปรับปรุงการสร้าง Lines จาก Template

```python
def _create_lines_from_template(self, template):
    """Create BOQ lines from template lines"""
    BOQLine = self.env['boq.line']
    
    # Debug logging
    import logging
    _logger = logging.getLogger(__name__)
    _logger.info(f"Creating BOQ lines from template: {template.name}")
    _logger.info(f"Template has {len(template.line_ids)} lines")
    
    for template_line in template.line_ids:
        _logger.info(f"Processing template line: {template_line.description}, Product: {template_line.product_id.name if template_line.product_id else 'None'}")
        
        line_vals = {
            'boq_id': self.id,
            'sequence': template_line.sequence,
            'item_code': template_line.item_code,
            'product_id': template_line.product_id.id if template_line.product_id else False,
            'description': template_line.description,
            'specification': template_line.specification,
            'quantity': template_line.quantity,
            'uom_id': template_line.uom_id.id if template_line.uom_id else False,
            'unit_cost': template_line.unit_cost,
            'waste_percentage': template_line.waste_percentage,
            'contingency_percentage': template_line.contingency_percentage,
            'notes': template_line.notes,
        }
        
        # Validate that essential fields are present
        if not line_vals['description']:
            _logger.warning(f"Template line {template_line.id} has no description")
            continue
            
        if not line_vals['uom_id']:
            _logger.warning(f"Template line {template_line.id} has no UOM")
            continue
        
        new_line = BOQLine.create(line_vals)
        _logger.info(f"Created BOQ line: {new_line.id}, Product: {new_line.product_id.name if new_line.product_id else 'None'}")
        
        # Additional check: if the created line has no product, log it
        if not new_line.product_id:
            _logger.warning(f"Created BOQ line {new_line.id} has no product assigned")
```

## ผลลัพธ์

1. **ป้องกันการสร้าง Template ที่ไม่มี Product**: ผู้ใช้จะต้องระบุ product ใน template lines
2. **ตรวจสอบข้อมูลครบถ้วน**: ระบบจะตรวจสอบว่า template มี lines และมี product ครบก่อนสร้าง BOQ
3. **Logging เพื่อ Debug**: เพิ่มการ log เพื่อติดตามการทำงานและหาปัญหา
4. **ข้อมูลมีความสมบูรณ์**: BOQ ที่สร้างจาก template จะมี product ครบถ้วนทุก line

## การทดสอบ

1. **สร้าง BOQ Template**:
   - ระบุ product ใน template lines (จำเป็น)
   - ตรวจสอบว่าไม่สามารถบันทึกได้หาก product ว่าง

2. **สร้าง BOQ จาก Template**:
   - ใช้ฟังก์ชัน `action_create_boq`
   - ตรวจสอบว่า BOQ lines มี product ครบถ้วน

3. **ตรวจสอบ Error Handling**:
   - ลองสร้าง BOQ จาก template ที่ไม่มี lines
   - ตรวจสอบว่าระบบแสดง error message ที่เหมาะสม

## หมายเหตุ

การเปลี่ยนแปลงนี้จะส่งผลต่อ:
- **ข้อมูลเก่า**: BOQ Template และ BOQ ที่มีอยู่แล้วอาจมี product ว่าง
- **การใช้งานใหม่**: ผู้ใช้จะต้องระบุ product ใน template และ BOQ lines
- **Data Migration**: อาจต้องมีการ migrate ข้อมูลเก่าให้มี product ครบถ้วน

## ไฟล์ที่แก้ไข

- `models/boq.py` - แก้ไข field definitions และ validation logic
