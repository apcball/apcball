# Stock Layer Usage Compatibility Fix

## สรุปปัญหา

มีปัญหาความเข้ากันได้ระหว่าง 2 modules:

1. **buz_valuation_regenerate** - ลบและสร้าง Stock Valuation Layers (SVL) ใหม่
2. **stock_valuation_layer_usage** - ติดตามการใช้งาน SVL ผ่าน usage records

### ปัญหาที่เกิดขึ้น

- เมื่อ `buz_valuation_regenerate` สร้าง SVL ใหม่ มันไม่มี `taken_data` ใน context
- `stock_valuation_layer_usage` พยายามประมวลผล `taken_data` และอาจเกิด error
- เมื่อลบ SVL, usage records ที่เกี่ยวข้องไม่ถูกลบตาม ทำให้เกิด orphaned records

## การแก้ไข

### 1. สร้าง Model Override ใน buz_valuation_regenerate

**ไฟล์:** `/opt/instance1/odoo17/custom-addons/buz_valuation_regenerate/models/stock_valuation_layer.py`

เพิ่มการ override `stock.valuation.layer` เพื่อ:

- ใส่ context `valuation_regeneration=True` และ `skip_usage_tracking=True` เมื่อสร้าง SVL ระหว่าง regeneration
- ให้ `taken_data` ที่เป็น default เพื่อป้องกัน error
- ลบ usage records ที่เกี่ยวข้องเมื่อลบ SVL

```python
class StockValuationLayer(models.Model):
    _inherit = 'stock.valuation.layer'

    @api.model_create_multi
    def create(self, vals_list):
        # ตรวจสอบว่าอยู่ใน regeneration context หรือไม่
        regeneration_context = self.env.context.get('valuation_regeneration', False)
        
        if regeneration_context:
            # ใส่ context เพื่อข้ามการประมวลผล usage tracking
            new_context = dict(self.env.context)
            if 'taken_data' not in new_context:
                new_context['taken_data'] = [{}]
            new_context['skip_usage_tracking'] = True
            
            return super(StockValuationLayer, self.with_context(new_context)).create(vals_list)
        
        return super(StockValuationLayer, self).create(vals_list)

    def unlink(self):
        # ลบ usage records ที่เกี่ยวข้องเมื่อลบ SVL ในช่วง regeneration
        regeneration_context = self.env.context.get('valuation_regeneration', False)
        
        if regeneration_context:
            if 'stock.valuation.layer.usage' in self.env:
                usage_records = self.env['stock.valuation.layer.usage'].search([
                    '|',
                    ('stock_valuation_layer_id', 'in', self.ids),
                    ('dest_stock_valuation_layer_id', 'in', self.ids),
                ])
                
                if usage_records:
                    usage_records.sudo().unlink()
        
        return super(StockValuationLayer, self).unlink()
```

### 2. อัพเดท Wizard ใน buz_valuation_regenerate

**ไฟล์:** `/opt/instance1/odoo17/custom-addons/buz_valuation_regenerate/models/valuation_regenerate_wizard.py`

เปลี่ยนการสร้าง SVL ทั้งหมดให้ใช้ context:

```python
# ใน _recompute_fifo_valuation() และ _recompute_avco_valuation()
new_svl = svl_obj.with_context(valuation_regeneration=True).create(svl_vals)

# ใน action_apply_regeneration() เมื่อลบ SVL
svls_to_delete.with_context(
    no_recompute=True,
    valuation_regeneration=True
).unlink()
```

### 3. แก้ไข stock_valuation_layer_usage

**ไฟล์:** `/opt/instance1/odoo17/custom-addons/stock_valuation_layer_usage/models/stock_valuation_layer.py`

เพิ่มการตรวจสอบ context เพื่อข้ามการประมวลผลในช่วง regeneration:

```python
@api.model_create_multi
def create(self, values):
    recs = self.browse()
    for val in values:
        rec = super().create([val])
        
        # ข้ามการ track usage ถ้าอยู่ใน regeneration context
        if self.env.context.get('skip_usage_tracking', False):
            recs |= rec
            continue
        
        # ... ประมวลผลปกติ
        taken_data = rec.env.context.get('taken_data', [{}])[0]
        # ...

def write(self, values):
    res = super().write(values)
    
    # ข้ามการ track usage ถ้าอยู่ใน regeneration context
    if self.env.context.get('skip_usage_tracking', False):
        return res
    
    # ... ประมวลผลปกติ
```

### 4. อัพเดท Manifests

**buz_valuation_regenerate:**
- Version: 17.0.1.2.0 → 17.0.1.3.0
- เพิ่มข้อมูลว่า compatible กับ stock_valuation_layer_usage

**stock_valuation_layer_usage:**
- Version: 17.0.1.1.0 → 17.0.1.2.0
- เพิ่มข้อมูลว่า compatible กับ buz_valuation_regenerate

## การทดสอบ

### ขั้นตอนการทดสอบ:

1. **อัพเกรด modules:**
   ```bash
   cd /opt/instance1/odoo17
   ./odoo-bin -c odoo.conf -d your_database -u buz_valuation_regenerate,stock_valuation_layer_usage --stop-after-init
   ```

2. **ทดสอบ Regeneration:**
   - ไปที่ Inventory → Valuation → Re-Generate Valuation
   - เลือก product ที่มี stock moves
   - Run Compute Plan (dry run)
   - ตรวจสอบว่าไม่มี error
   - ปิด Dry Run และ Apply Regeneration
   - ตรวจสอบว่า SVL ถูกสร้างใหม่สำเร็จ

3. **ตรวจสอบ Usage Records:**
   - ไปที่ Inventory → Valuation Layers
   - เปิด SVL ที่ถูกสร้างในช่วง normal operations (ไม่ใช่ regeneration)
   - ตรวจสอบว่า Usage records ยังทำงานปกติ
   - ตรวจสอบ incoming_usage_ids และ usage_ids

4. **ทดสอบ Cleanup:**
   - Run regeneration อีกครั้ง
   - ตรวจสอบว่า orphaned usage records ไม่เหลืออยู่ใน database
   - Query: `SELECT COUNT(*) FROM stock_valuation_layer_usage WHERE stock_valuation_layer_id NOT IN (SELECT id FROM stock_valuation_layer)`

## คุณสมบัติหลังการแก้ไข

✅ **buz_valuation_regenerate:**
- สามารถลบและสร้าง SVL ใหม่ได้โดยไม่เกิด error
- ลบ usage records ที่เกี่ยวข้องอัตโนมัติ
- ป้องกัน orphaned records

✅ **stock_valuation_layer_usage:**
- ทำงานปกติสำหรับ stock moves ทั่วไป
- ข้ามการประมวลผลในช่วง regeneration
- ไม่สร้าง usage records สำหรับ regenerated SVLs

✅ **ความเข้ากันได้:**
- ทั้ง 2 modules ทำงานร่วมกันได้โดยไม่มีปัญหา
- สามารถติดตั้งทั้งคู่พร้อมกันได้
- Regeneration ไม่กระทบการทำงานของ usage tracking

## หมายเหตุสำคัญ

1. **Context Keys:**
   - `valuation_regeneration=True` - บอกว่าอยู่ในช่วง regeneration
   - `skip_usage_tracking=True` - สั่งให้ข้าม usage tracking

2. **Backward Compatibility:**
   - การเปลี่ยนแปลงนี้ไม่กระทบการทำงานปกติของ modules
   - ถ้าใช้แค่ module เดียว ก็ยังทำงานได้ปกติ

3. **Performance:**
   - การข้าม usage tracking ในช่วง regeneration ช่วยเพิ่มความเร็ว
   - ไม่มีการสร้าง usage records ที่ไม่จำเป็นใน regenerated SVLs

## ผู้พัฒนา

- **Modified by:** apcball
- **Date:** 25 ตุลาคม 2568
- **Purpose:** Fix compatibility between buz_valuation_regenerate and stock_valuation_layer_usage modules

## การติดตามผล

หลังจากอัพเกรด ให้ติดตาม:
- Error logs ที่เกี่ยวกับ stock.valuation.layer
- Orphaned usage records
- Performance ของการ regenerate
- ความถูกต้องของ usage tracking ใน normal operations
