# Internal Consume Request - Feature Documentation

## Overview
Custom Module สำหรับ Odoo 17 Enterprise เพื่อจัดการระบบขอเบิกอุปกรณ์สิ้นเปลืองภายในบริษัท

## Core Features

### 1. Auto Reject เมื่อ Stock ไม่พอ ✅

#### การทำงาน:
- **ตรวจสอบ Stock ทันที**: ระบบจะตรวจสอบ stock ทุกครั้งที่กด Submit
- **ตรวจสอบก่อนสร้าง Picking**: ตรวจสอบอีกครั้งก่อนสร้าง Delivery Order
- **Auto Reject**: ถ้า `qty_requested > available_qty` จะเปลี่ยน state เป็น `rejected` ทันที
- **บันทึกเหตุผล**: เก็บข้อความ "Stock ไม่เพียงพอ" ใน field `reason`
- **แจ้งเตือน**: ส่ง Mail Activity แจ้งผู้ขอทันทีพร้อมรายละเอียด
- **ป้องกัน**: ไม่อนุญาตให้ Approve หรือ Create Picking ถ้า stock ไม่พอ

#### Implementation:
```python
# ตรวจสอบใน action_submit()
for line in self.line_ids:
    if line.qty_requested > line.available_qty:
        self._action_auto_reject(reason)
        raise UserError(...)

# ตรวจสอบใน action_approve()
if self.has_insufficient_stock:
    raise UserError(...)

# ตรวจสอบใน action_create_picking()
# Validate อีกครั้งก่อนสร้าง picking
```

### 2. รองรับหลาย Warehouse ✅

#### การทำงาน:
- **เลือก Warehouse**: ผู้ขอสามารถเลือก Warehouse ได้เองในเอกสาร
- **Auto Update Location**: 
  - `location_id` = `warehouse.lot_stock_id`
  - `picking_type_id` = Delivery Orders ของ warehouse นั้น
- **Stock Availability**: คำนวณตาม warehouse ที่เลือกเท่านั้น (รวม child locations)
- **Delivery Creation**: สร้างจาก warehouse ที่เลือก พร้อม origin = request.name

#### Implementation:
```python
@api.depends('warehouse_id')
def _compute_picking_type_id(self):
    record.picking_type_id = record.warehouse_id.out_type_id

@api.depends('warehouse_id')
def _compute_location_id(self):
    record.location_id = record.warehouse_id.lot_stock_id

# Stock calculation per warehouse
quants = self.env['stock.quant'].search([
    ('product_id', '=', line.product_id.id),
    ('location_id', 'child_of', line.location_id.id),
    ('location_id.usage', '=', 'internal'),
])
```

### 3. Stock Validation Logic ✅

#### Available Quantity Calculation:
```python
available_qty = sum(
    quant.quantity - quant.reserved_quantity
    for quant in quants
    where location_id child_of warehouse.lot_stock_id
    and location_id.usage = 'internal'
)
```

#### Validation Points:
1. **On Submit**: ตรวจสอบทุก line และ auto reject ถ้าไม่พอ
2. **On Approve**: ป้องกันการ approve ถ้า stock ไม่เพียงพอ
3. **Before Picking**: ตรวจสอบอีกครั้งก่อนสร้าง picking (ป้องกัน stock เปลี่ยน)

### 4. Computed Fields ✅

#### `has_insufficient_stock`
- **Type**: Boolean (computed, not stored)
- **Logic**: True ถ้ามี line ใดๆ ที่ qty_requested > available_qty
- **Use**: แสดง warning banner, ปิดปุ่ม Approve

#### `allow_submit`
- **Type**: Boolean (computed, not stored)
- **Logic**: True ถ้ามี lines และ stock เพียงพอทุก line
- **Use**: ควบคุมการแสดงปุ่ม Submit

### 5. User Interface Enhancements ✅

#### Visual Indicators:
- **Red Alert Banner**: แสดงเมื่อ stock ไม่พอ
- **Red Highlight**: แถวที่ stock ไม่เพียงพอจะแสดงสีแดง
- **Available Column**: แสดง stock คงเหลือแบบ real-time
  - สีเขียว: stock เพียงพอ
  - สีแดง: stock ไม่พอ

#### Button Controls:
- **Submit**: ปิดการใช้งานถ้า `allow_submit = False`
- **Approve**: ปิดการใช้งานถ้า `has_insufficient_stock = True`
- **Reject**: แสดงเฉพาะสำหรับ Manager

#### Information Display:
- แสดง `rejection_reason` เมื่อ state = rejected
- แสดง `reason` (auto reject reason) แยกต่างหาก
- แสดง warehouse ที่เลือกใน header

### 6. Security & Access Control ✅

#### User Groups:
1. **Internal Consume User**: เห็นเฉพาะ request ตัวเอง
2. **Internal Consume Manager**: เห็น request ของทีม, สามารถ Approve/Reject
3. **Internal Consume Stock**: เห็นทุก request, สามารถสร้าง Picking

#### Record Rules:
- User: `[('employee_id.user_id', '=', user.id)]`
- Manager: `['|', ('employee_id.user_id', '=', user.id), ('employee_id.parent_id.user_id', '=', user.id)]`
- Stock: `[(1, '=', 1)]` (ทั้งหมด)

## Workflow

```
Draft → Submit → To Approve → Approve → Done
          ↓          ↓           ↓
      Auto Reject  Reject    Create Picking
   (stock ไม่พอ)  (manual)  (with validation)
```

### State Transitions:

1. **Draft → To Approve**: 
   - Check stock availability
   - Auto reject if insufficient
   - Create activity for manager

2. **To Approve → Approved**:
   - Validate stock again
   - Raise error if insufficient
   - Auto create picking

3. **To Approve → Rejected**:
   - Manual rejection via wizard
   - Or auto rejection via stock check

4. **Approved → Done**:
   - After picking is validated

## Technical Details

### Models:

#### `internal.consume.request`
- Main request document
- Inherits: `mail.thread`, `mail.activity.mixin`
- Key fields: `warehouse_id`, `has_insufficient_stock`, `allow_submit`, `reason`

#### `internal.consume.request.line`
- Request lines with products
- Computes: `available_qty` based on warehouse

#### `internal.consume.request.reject`
- Transient model for rejection wizard

### Best Practices:
✅ No hardcoded warehouse/location  
✅ Dynamic location based on warehouse selection  
✅ ORM usage (no raw SQL)  
✅ Proper error handling  
✅ Activity tracking  
✅ Multi-company compatible  
✅ UOM conversion support  

## Installation & Configuration

1. Install module via Apps menu
2. Assign users to appropriate groups
3. Configure warehouses if needed
4. Start creating consume requests

## Usage Example

1. Employee creates request
2. Select warehouse (e.g., ST01, ST02)
3. Add products with quantities
4. System shows available stock in real-time
5. If stock sufficient → Submit
6. If stock insufficient → Red warning, cannot submit
7. Manager reviews and approves
8. System creates Delivery Order automatically
9. Stock team validates the delivery
10. Request marked as Done

## Error Handling

### User Errors:
- "Please add at least one product line"
- "No manager found for employee"
- "Request has been automatically rejected due to insufficient stock"
- "Cannot approve: Insufficient stock"

### Auto Reject Scenarios:
- Submit with insufficient stock
- Stock changes between approval and picking creation
- Any line has requested qty > available qty

## Notifications

### Activities Created:
1. **On Submit**: Activity for manager to approve
2. **On Auto Reject**: Warning activity for employee
3. **On Manual Reject**: Feedback on existing activity

### Messages Posted:
- Request submitted
- Request approved/rejected
- Picking created
- Request completed
- Auto rejection with details

## Fields Reference

| Field | Type | Description |
|-------|------|-------------|
| `warehouse_id` | Many2one | Selected warehouse |
| `location_id` | Many2one | Auto-computed from warehouse |
| `picking_type_id` | Many2one | Auto-computed (Delivery Orders) |
| `has_insufficient_stock` | Boolean | True if any line has insufficient stock |
| `allow_submit` | Boolean | True if can submit (sufficient stock) |
| `reason` | Text | Auto reject reason |
| `rejection_reason` | Text | Manual rejection reason |

## Performance Considerations

- Stock computation uses indexed fields
- Quant search limited to warehouse location tree
- Computed fields not stored (on-demand calculation)
- Efficient domain filters in views

---

**Version**: 17.0.1.0.0  
**License**: LGPL-3  
**Author**: Your Company  
**Odoo Version**: 17.0 Enterprise
