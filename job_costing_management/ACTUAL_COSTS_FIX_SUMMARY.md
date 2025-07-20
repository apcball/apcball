# Actual Costs Fix Summary - Job Costing Management

## ปัญหาที่พบ

**Labour Costs มี actual cost ไม่เกิดขึ้น** แม้ว่าจะมี timesheet entries แล้ว

## สาเหตุของปัญหา

### 1. การคำนวณ Actual Unit Cost สำหรับ Labour
- ใน method `_compute_actual_unit_cost()` สำหรับ labour costs
- การใช้ `abs(line.amount)` อาจไม่ถูกต้องในบางกรณี
- ขาด debug logging เพื่อตรวจสอบการทำงาน

### 2. การเชื่อมต่อ Timesheet กับ Job Cost Line
- Timesheet อาจไม่ได้เชื่อมต่อกับ job cost line อัตโนมัติ
- ขาดการ auto-linking เมื่อสร้าง timesheet ใหม่

### 3. การ Refresh Actual Costs
- ไม่มีวิธีการ manual refresh actual costs ที่มีประสิทธิภาพ
- ขาด debug information เพื่อตรวจสอบปัญหา

## การแก้ไขที่ทำ

### 1. ปรับปรุงการคำนวณ Actual Unit Cost

**ไฟล์**: `models/job_cost_sheet.py`

```python
@api.depends('purchase_order_line_ids.price_unit', 'purchase_order_line_ids.product_qty', 
             'timesheet_ids.amount', 'invoice_line_ids.price_unit', 'invoice_line_ids.quantity')
def _compute_actual_unit_cost(self):
    for record in self:
        total_cost = 0
        total_qty = 0
        
        if record.cost_type == 'labour':
            # Use timesheets - amount is negative in Odoo, so use abs()
            for line in record.timesheet_ids:
                # In Odoo, timesheet amount is negative (cost), so we use abs()
                cost_amount = abs(line.amount) if line.amount else 0
                total_cost += cost_amount
                total_qty += line.unit_amount
                
                # Debug logging
                import logging
                _logger = logging.getLogger(__name__)
                _logger.info(f"Timesheet line: unit_amount={line.unit_amount}, amount={line.amount}, abs_amount={cost_amount}")
```

### 2. เพิ่ม Debug Logging

**เพิ่มใน**:
- `_compute_actual_qty()` - ตรวจสอบการคำนวณ actual quantity
- `_compute_actual_unit_cost()` - ตรวจสอบการคำนวณ unit cost
- `_compute_actual_cost()` - ตรวจสอบการคำนวณ total actual cost
- `_compute_actual_costs()` - ตรวจสอบการรวม actual costs ในระดับ job cost sheet

### 3. ปรับปรุงการเชื่อมต่อ Timesheet

**ไฟล์**: `models/hr_timesheet.py`

```python
@api.model
def create(self, vals):
    result = super(AccountAnalyticLine, self).create(vals)
    
    # Auto-link to job cost line if not already linked
    if not result.job_cost_line_id and result.account_id:
        result._auto_link_to_job_cost_line()
        
    return result

def _auto_link_to_job_cost_line(self):
    """Auto-link timesheet to appropriate job cost line"""
    if not self.account_id:
        return
        
    # Find related job cost sheet
    cost_sheet = self.env['job.cost.sheet'].search([
        ('analytic_account_id', '=', self.account_id.id),
        ('state', 'in', ['approved', 'done'])
    ], limit=1)
    
    if cost_sheet:
        # Find matching labour cost line
        labour_lines = cost_sheet.labour_cost_ids
        
        if len(labour_lines) == 1:
            # If only one labour line, auto-link
            self.job_cost_line_id = labour_lines[0].id
```

### 4. ปรับปรุงฟังก์ชัน Sync Actual Costs

```python
def action_sync_actual_costs(self):
    """Manually sync actual costs from all linked POs and Invoices"""
    import logging
    _logger = logging.getLogger(__name__)
    
    _logger.info(f"=== Syncing actual costs for Job Cost Sheet: {self.name} ===")
    
    for cost_line in self.material_cost_ids + self.labour_cost_ids + self.overhead_cost_ids:
        _logger.info(f"Processing cost line: {cost_line.name} (type: {cost_line.cost_type})")
        
        if cost_line.cost_type == 'labour':
            # Force recomputation for labour costs
            cost_line._compute_actual_qty()
            cost_line._compute_actual_unit_cost()
            cost_line._compute_actual_cost()
            _logger.info(f"  Labour line after sync: actual_qty={cost_line.actual_qty}, actual_cost={cost_line.actual_cost}")
        else:
            cost_line.update_actual_costs_from_purchases()
            
    # Force recomputation of job cost sheet totals
    self._compute_actual_costs()
```

### 5. เพิ่มปุ่ม Refresh Actual Costs

**ไฟล์**: `views/job_cost_sheet_views.xml`

```xml
<button name="action_sync_actual_costs" string="Refresh Actual Costs" type="object" 
        class="btn-secondary" invisible="state not in ['approved', 'done']"
        help="Manually refresh actual costs from purchase orders, invoices, and timesheets"/>
```

## การทดสอบ

### 1. ไฟล์ทดสอบ Debug

**ไฟล์**: `test_actual_costs_debug.py`
- ทดสอบการคำนวณ labour actual costs
- ทดสอบการเชื่อมต่อ timesheet
- ทดสอบการ sync actual costs

### 2. ไฟล์ทดสอบการแก้ไข

**ไฟล์**: `test_actual_costs_fix.py`
- ทดสอบการทำงานหลังการแก้ไข
- ทดสอบ auto-linking timesheet
- ทดสอบ manual sync function

## วิธีการทดสอบ

### 1. ใน Odoo Shell:

```bash
python odoo-bin shell -d your_database
```

```python
# Load test script
exec(open('/path/to/job_costing_management/test_actual_costs_fix.py').read())

# Run tests
test_data = test_labour_actual_costs()
test_timesheet_auto_linking()
```

### 2. ใน Odoo Interface:

1. **สร้าง Job Cost Sheet**:
   - เลือก Project และ Analytic Account
   - Approve job cost sheet

2. **เพิ่ม Labour Cost Line**:
   - เลือก Service Product
   - กำหนด Planned Quantity และ Unit Cost

3. **สร้าง Timesheet**:
   - เลือก Employee
   - กำหนด Analytic Account เดียวกับ Job Cost Sheet
   - บันทึก Unit Amount และ Amount

4. **ตรวจสอบ Actual Costs**:
   - ดู Actual Quantity, Actual Unit Cost, Actual Cost
   - กดปุ่ม "Refresh Actual Costs" หากจำเป็น

## ผลลัพธ์ที่คาดหวัง

### หลังการแก้ไข:

1. **Labour Actual Costs จะแสดงผลถูกต้อง**:
   - `actual_qty` = ผลรวม timesheet unit_amount
   - `actual_unit_cost` = ผลรวม abs(timesheet.amount) / ผลรวม unit_amount
   - `actual_cost` = actual_qty × actual_unit_cost

2. **Timesheet Auto-linking**:
   - Timesheet ใหม่จะเชื่อมต่อกับ job cost line อัตโนมัติ
   - หาก labour cost line มีเพียงหนึ่งรายการ

3. **Manual Refresh**:
   - ปุ่ม "Refresh Actual Costs" ทำงานได้
   - แสดง notification พร้อมผลลัพธ์

4. **Debug Information**:
   - Log ข้อมูลการคำนวณใน server log
   - ช่วยในการ troubleshoot ปัญหา

## การตรวจสอบปัญหาเพิ่มเติม

### 1. ตรวจสอบ Timesheet Linking:
```python
# ใน Odoo shell
timesheet = env['account.analytic.line'].browse(timesheet_id)
print(f"Job Cost Line: {timesheet.job_cost_line_id.name if timesheet.job_cost_line_id else 'Not linked'}")
```

### 2. ตรวจสอบ Computed Fields:
```python
# Force recomputation
cost_line = env['job.cost.line'].browse(cost_line_id)
cost_line.invalidate_recordset()
cost_line._compute_actual_qty()
cost_line._compute_actual_unit_cost()
cost_line._compute_actual_cost()
```

### 3. ตรวจสอบ Dependencies:
```python
# Check field dependencies
print(cost_line._fields['actual_qty'].depends)
print(cost_line._fields['actual_unit_cost'].depends)
print(cost_line._fields['actual_cost'].depends)
```

## สรุป

การแก้ไขนี้ครอบคลุม:
- ✅ แก้ไขการคำนวณ labour actual costs
- ✅ เพิ่ม debug logging สำหรับ troubleshooting
- ✅ ปรับปรุงการ auto-link timesheet
- ✅ เพิ่มฟังก์ชัน manual refresh
- ✅ เพิ่มปุ่ม UI สำหรับ refresh
- ✅ สร้างไฟล์ทดสอบสำหรับ verification

หลังการแก้ไขนี้ Labour Actual Costs ควรทำงานได้อย่างถูกต้องและแสดงผลตามที่คาดหวัง