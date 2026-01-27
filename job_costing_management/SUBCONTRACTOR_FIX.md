# แก้ไขปัญหา Subcontractor ไม่แสดงในหน้า Subcontractor

## ปัญหา
เมื่อเพิ่ม subcontractor แล้วไม่แสดงในหน้า subcontractor เพราะ action มี domain ที่กรองเฉพาะ partner ที่มี `is_subcontractor = True`

## สาเหตุ
1. การสร้าง partner ใหม่ อาจจะไม่ได้เซ็ต `is_subcontractor = True`
2. Context ของ action อาจจะไม่ทำงานถูกต้อง
3. Default values ไม่ถูกนำไปใช้

## วิธีแก้ไขที่ทำ

### 1. เพิ่ม default_get method ใน ResPartner
```python
@api.model
def default_get(self, fields_list):
    defaults = super(ResPartner, self).default_get(fields_list)
    
    if self.env.context.get('default_is_subcontractor'):
        defaults.update({
            'is_subcontractor': True,
            'supplier_rank': 1,
            'is_company': True,
            'subcontractor_type': 'company'
        })
    
    return defaults
```

### 2. เพิ่ม create และ write methods
```python
@api.model
def create(self, vals):
    if self.env.context.get('default_is_subcontractor') and 'is_subcontractor' not in vals:
        vals['is_subcontractor'] = True
    
    if vals.get('is_subcontractor') and 'supplier_rank' not in vals:
        vals['supplier_rank'] = 1
        
    return super(ResPartner, self).create(vals)

def write(self, vals):
    if vals.get('is_subcontractor') and self.supplier_rank == 0:
        vals['supplier_rank'] = 1
        
    return super(ResPartner, self).write(vals)
```

### 3. อัปเดต action context
```xml
<field name="context">{
    'default_is_subcontractor': True, 
    'default_supplier_rank': 1,
    'default_is_company': True,
    'res_model': 'res.partner'
}</field>
```

### 4. สร้าง views เฉพาะสำหรับ subcontractor
- สร้าง `view_subcontractor_tree` และ `view_subcontractor_form`
- แสดง fields ที่เกี่ยวข้องกับ subcontractor
- เพิ่ม button สำหรับเซ็ตเป็น subcontractor

### 5. เพิ่ม helper methods
```python
def action_set_as_subcontractor(self):
    """Manual action to set partner as subcontractor."""
    self.write({
        'is_subcontractor': True,
        'supplier_rank': 1
    })

@api.model
def action_debug_subcontractors(self):
    """Debug method to check existing subcontractors."""
    subcontractors = self.search([('is_subcontractor', '=', True)])
    # ...
```

## วิธีการทดสอบ

1. **ไปที่หน้า Subcontractors**
2. **กดปุ่ม Create** - ควรเห็นว่า `is_subcontractor` ถูกเซ็ตเป็น True
3. **กรอกข้อมูล** (ชื่อ, ประเภท, เบอร์โทร, etc.)
4. **Save** 
5. **กลับไปดูที่ list** - ควรเห็น record ใหม่

## การแก้ไขเพิ่มเติม (หากยังมีปัญหา)

หากยังไม่แสดง ให้ลองทำดังนี้:

1. **ตรวจสอบ existing partners**:
   ```python
   # ใน Odoo shell หรือ debug mode
   partners = self.env['res.partner'].search([])
   for p in partners:
       if 'subcontractor' in p.name.lower():
           p.is_subcontractor = True
   ```

2. **Force update existing records**:
   ```xml
   <button name="action_set_as_subcontractor" type="object" 
           string="Set as Subcontractor"/>
   ```

3. **ตรวจสอบ domain**:
   - Domain: `[('is_subcontractor', '=', True)]`
   - Context: `{'default_is_subcontractor': True}`

## Files ที่แก้ไข
1. `models/subcontractor.py` - เพิ่ม methods
2. `views/subcontractor_views.xml` - สร้าง custom views
3. `views/job_order_views.xml` - อัปเดต action
