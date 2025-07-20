# Auto Cost Type Adjustment Feature

## Overview

เพิ่มฟีเจอร์การปรับ Cost Type อัตโนมัติตาม Product Type เพื่อให้การทำงานเป็นไปอย่างราบรื่นและลดข้อผิดพลาดจากผู้ใช้

## การทำงานของระบบ

### 🔄 **Auto-Adjustment Rules**

เมื่อผู้ใช้เลือก Product ในฟิลด์ `product_id` ระบบจะปรับ `cost_type` อัตโนมัติตามกฎดังนี้:

| Product Type | Auto Cost Type | UOM Adjustment |
|--------------|----------------|----------------|
| **Service** | **Labour** | Hours (ชั่วโมง) |
| **Storable** | **Material** | Product's default UOM |
| **Consumable** | **Material** | Product's default UOM |

### 📋 **Implementation Details**

#### 1. Enhanced `_onchange_product_id` Method ✅

```python
@api.onchange('product_id')
def _onchange_product_id(self):
    if self.product_id:
        # Set basic product information
        self.name = self.product_id.name
        self.unit_cost = self.product_id.standard_price
        self.uom_id = self.product_id.uom_id
        
        # Store original cost type to detect changes
        original_cost_type = self.cost_type
        
        # Auto-adjust cost type based on product type
        if self.product_id.detailed_type == 'service':
            self.cost_type = 'labour'
            # Set Hours UOM for labour
            hours_uom = self.env['uom.uom'].search([('name', 'ilike', 'hour')], limit=1)
            if hours_uom:
                self.uom_id = hours_uom
                
        elif self.product_id.detailed_type in ['product', 'consu']:
            self.cost_type = 'material'
            # Keep product's default UOM
            self.uom_id = self.product_id.uom_id
        
        # Show notification if cost type changed
        if original_cost_type and original_cost_type != self.cost_type:
            return {
                'warning': {
                    'title': 'Cost Type Auto-Adjusted',
                    'message': f'Cost type changed to "{self.cost_type}" based on product type'
                }
            }
```

#### 2. Enhanced RFQ Creation ✅

**Updated Domain**: รวม Labour cost lines ที่สามารถซื้อได้
```python
domain="[('cost_sheet_id', '=', job_cost_sheet_id), ('cost_type', 'in', ['material', 'overhead', 'labour'])]"
```

**Smart Selection**: เลือกเฉพาะ Labour lines ที่มี `purchase_ok = True`
```python
cost_lines = (self.job_cost_sheet_id.material_cost_ids + 
             self.job_cost_sheet_id.overhead_cost_ids + 
             self.job_cost_sheet_id.labour_cost_ids.filtered(lambda l: l.product_id.purchase_ok))
```

#### 3. Improved Validation Messages ✅

ปรับปรุงข้อความแจ้งเตือนให้ชัดเจนและให้คำแนะนำที่เป็นประโยชน์:

```python
# Material + Service Product
"Material cost line uses service product. Consider changing cost type to 'Labour' or use a storable/consumable product."

# Labour + Non-Service Product  
"Labour cost line uses non-service product. Consider changing cost type to 'Material' or use a service product."
```

## Benefits

### ✅ **User Experience**
- **ลดข้อผิดพลาด**: ระบบปรับ cost type อัตโนมัติ
- **ประหยัดเวลา**: ไม่ต้องปรับ cost type ด้วยตนเอง
- **คำแนะนำชัดเจน**: แจ้งเตือนเมื่อมีการเปลี่ยนแปลง

### ✅ **Business Logic**
- **สอดคล้องกับธุรกิจ**: Service = Labour, Physical Products = Material
- **ยืดหยุ่น**: ยังคงสามารถปรับแต่งด้วยตนเองได้
- **RFQ Integration**: รองรับการสร้าง PO จาก Labour cost lines

### ✅ **Data Integrity**
- **Validation ที่ดีขึ้น**: ข้อความแจ้งเตือนที่เป็นประโยชน์
- **Flexible Context**: รองรับการทำงานในสถานการณ์ต่างๆ
- **Backward Compatible**: ไม่กระทบข้อมูลเดิม

## Use Cases

### 🎯 **Scenario 1: Service Product Selection**
1. ผู้ใช้สร้าง cost line ใหม่
2. เลือก cost type = "Material" 
3. เลือก product ที่เป็น "Service"
4. **ระบบปรับเป็น "Labour" อัตโนมัติ**
5. แสดงข้อความแจ้งเตือน
6. ปรับ UOM เป็น "Hours"

### 🎯 **Scenario 2: Physical Product Selection**
1. ผู้ใช้สร้าง cost line ใหม่
2. เลือก cost type = "Labour"
3. เลือก product ที่เป็น "Storable/Consumable"
4. **ระบบปรับเป็น "Material" อัตโนมัติ**
5. แสดงข้อความแจ้งเตือน
6. ใช้ UOM ของ product

### 🎯 **Scenario 3: RFQ Creation with Labour**
1. สร้าง cost lines ที่มี service products (auto-adjusted เป็น labour)
2. เปิด RFQ wizard
3. **ระบบรวม labour lines ที่ purchase_ok = True**
4. สร้าง PO ได้สำเร็จ
5. ไม่มี validation errors

## Configuration

### Optional Strict Mode
หากต้องการ validation แบบเข้มงวด สามารถเพิ่ม setting ใน company:

```python
# In res.company model (optional)
job_costing_strict_product_validation = fields.Boolean(
    string='Strict Job Costing Product Validation',
    default=False,
    help="Enable strict validation for product types in job cost lines"
)
```

### Context Flags
ระบบรองรับ context flags สำหรับการควบคุม validation:

- `skip_product_validation`: ข้าม validation ทั้งหมด
- `flexible_product_validation`: อนุญาต warnings แต่ไม่ error
- `auto_cost_type_adjustment`: ระบุว่าเป็นการปรับอัตโนมัติ

## Files Modified

### 1. **`models/job_cost_sheet.py`** ✅
- Enhanced `_onchange_product_id()` method
- Updated validation messages
- Added auto-adjustment logic
- Improved helper methods

### 2. **`wizard/create_rfq_from_job_cost.py`** ✅
- Updated domain to include labour cost lines
- Smart filtering for purchasable labour lines
- Enhanced onchange logic

### 3. **`test_product_validation_fix.py`** ✅
- Added comprehensive test for auto-adjustment
- Test scenarios for all product types
- RFQ creation testing with labour lines

### 4. **`AUTO_COST_TYPE_ADJUSTMENT.md`** ✅
- Complete documentation
- Usage examples
- Configuration options

## Testing

### Manual Testing Steps

1. **Test Service Product Auto-Adjustment**:
   ```
   1. Create new cost line
   2. Set cost_type = 'material'
   3. Select service product
   4. Verify: cost_type changes to 'labour'
   5. Verify: UOM changes to hours
   6. Verify: Warning message appears
   ```

2. **Test Material Product Auto-Adjustment**:
   ```
   1. Create new cost line
   2. Set cost_type = 'labour'
   3. Select storable/consumable product
   4. Verify: cost_type changes to 'material'
   5. Verify: UOM uses product's UOM
   6. Verify: Warning message appears
   ```

3. **Test RFQ Creation**:
   ```
   1. Create cost sheet with mixed cost types
   2. Include labour lines with service products
   3. Create RFQ wizard
   4. Verify: Labour lines included in selection
   5. Verify: RFQ creates successfully
   6. Verify: No validation errors
   ```

### Automated Testing
Run the test script in Odoo shell:
```python
exec(open('/path/to/test_product_validation_fix.py').read())
test_product_validation_fix()
```

## Migration Notes

### For Existing Data
- ✅ No data migration required
- ✅ Existing cost lines continue to work
- ✅ Auto-adjustment only applies to new selections
- ⚠️ May see warnings in logs for existing mismatched types

### For Users
- 📚 **Training**: Inform users about auto-adjustment behavior
- 📋 **Documentation**: Update user manuals
- 🔧 **Testing**: Test in staging environment first

## Future Enhancements

### Possible Improvements
1. **Company Settings UI**: Add configuration interface
2. **Bulk Adjustment**: Tool to fix existing mismatched cost lines
3. **Product Categories**: More granular control based on categories
4. **Custom Rules**: Allow custom mapping rules per company
5. **Audit Trail**: Track auto-adjustments for reporting

### Integration Opportunities
1. **BOQ Integration**: Auto-adjust based on BOQ line types
2. **Project Templates**: Pre-configured cost type mappings
3. **Vendor Catalogs**: Integration with vendor product types
4. **Cost Analysis**: Enhanced reporting with type consistency metrics

## Support

### Common Issues
- **Auto-adjustment not working**: Check product detailed_type field
- **Wrong UOM selected**: Verify UOM search criteria
- **Validation still strict**: Check context flags and company settings
- **RFQ missing labour lines**: Verify product.purchase_ok = True

### Troubleshooting
1. Check server logs for warning messages
2. Verify product types are correctly set
3. Test with simple scenarios first
4. Check user permissions for cost line editing

### Contact
For issues or questions about this feature:
- Check the test script results
- Review server logs for warnings
- Test in development environment
- Document specific scenarios that don't work as expected