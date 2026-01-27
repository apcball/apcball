# คู่มือการใช้งาน Scripts สำหรับแก้ไข Stock Valuation by Warehouse

## ภาพรวม

Scripts เหล่านี้ใช้สำหรับจัดการข้อมูล Stock Valuation Layer ให้ถูกต้องตาม Warehouse โดยเฉพาะกรณี:
1. ยกของเข้าคลังครั้งแรก
2. แก้ไขข้อมูล valuation และ remaining qty ที่ผิด
3. คำนวณ FIFO ใหม่แยกตาม warehouse

---

## Scripts ที่มี

### 1. `fix_valuation_by_warehouse.py`
**วัตถุประสงค์**: แก้ไขข้อมูล valuation layer ที่มีอยู่แล้วให้ถูกต้อง

**ใช้เมื่อ**:
- Remaining Qty ≠ Moved Qty
- warehouse_id ขาดหายหรือผิด
- remaining_qty/remaining_value คำนวณผิด

**การทำงาน**:
1. ตรวจสอบและแก้ไข `warehouse_id` ที่ขาดหาย
2. คำนวณ `remaining_qty` และ `remaining_value` ใหม่แยกตาม warehouse
3. ใช้ FIFO logic คำนวณ remaining จาก layers เก่าไปใหม่

### 2. `create_initial_stock_by_warehouse.py`
**วัตถุประสงค์**: สร้าง stock เริ่มต้นในแต่ละคลัง

**ใช้เมื่อ**:
- ยกของเข้าระบบครั้งแรก
- ปรับปรุงยอดคงเหลือ
- เพิ่ม stock แยกตาม warehouse

**การทำงาน**:
1. สร้าง stock.move (Inventory Adjustment)
2. สร้าง stock.valuation.layer พร้อม warehouse_id
3. ตั้งค่า remaining_qty = quantity (เพราะยังไม่มีการใช้)

---

## วิธีใช้งาน

### เตรียมความพร้อม

1. **Backup ข้อมูลก่อน**:
```bash
pg_dump -U odoo -d MOG_TEST -f /backup/MOG_TEST_$(date +%Y%m%d_%H%M%S).sql
```

2. **ตรวจสอบ Odoo path**:
```bash
cd /opt/instance1/odoo17
ls -la odoo-bin
```

---

## การใช้งาน Script 1: แก้ไขข้อมูลที่มีอยู่

### วิธีที่ 1: รันผ่าน Odoo Shell (แนะนำ)

```bash
cd /opt/instance1/odoo17

# ขั้นตอน 1: ทดสอบก่อน (Dry Run)
python3 odoo-bin shell -d MOG_TEST --no-http << 'EOF'
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/fix_valuation_by_warehouse.py')
EOF

# ขั้นตอน 2: ดำเนินการจริง (ถ้าผลลัพธ์ถูกต้อง)
python3 odoo-bin shell -d MOG_TEST --no-http << 'EOF'
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/fix_valuation_by_warehouse.py')
fix_valuation_by_warehouse(env, dry_run=False)
EOF
```

### วิธีที่ 2: Copy-Paste ใน Odoo Shell

```bash
# เปิด Odoo shell
python3 odoo-bin shell -d MOG_TEST --no-http
```

จากนั้น copy code จากไฟล์ `fix_valuation_by_warehouse.py` ทั้งหมด paste เข้าไป แล้วรันคำสั่ง:

```python
# ทดสอบก่อน
fix_valuation_by_warehouse(env, dry_run=True)

# ดำเนินการจริง
fix_valuation_by_warehouse(env, dry_run=False)
```

---

## การใช้งาน Script 2: สร้าง Stock เริ่มต้น

### สร้างรายการเดียว

```bash
python3 odoo-bin shell -d MOG_TEST --no-http
```

```python
# โหลด script
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/create_initial_stock_by_warehouse.py')

# ทดสอบสร้างรายการเดียว
result = create_initial_stock_layer(
    env,
    product_code='PROD001',          # รหัสสินค้า
    warehouse_code='WH/Stock',       # รหัสคลัง
    quantity=100,                    # จำนวน
    unit_cost=50.00,                 # ราคาต้นทุน/หน่วย
    description='ยกยอดเริ่มต้น',     # คำอธิบาย
    dry_run=True                     # ทดสอบก่อน
)

print(result)

# ดำเนินการจริง
result = create_initial_stock_layer(
    env,
    product_code='PROD001',
    warehouse_code='WH/Stock',
    quantity=100,
    unit_cost=50.00,
    description='ยกยอดเริ่มต้น',
    dry_run=False  # บันทึกจริง
)
```

### สร้างหลายรายการ

```python
# เตรียมข้อมูล
stock_data = [
    {
        'product_code': 'PROD001',
        'warehouse_code': 'WH/Stock',
        'quantity': 100,
        'unit_cost': 50.00,
        'description': 'ยกยอดคลังหลัก'
    },
    {
        'product_code': 'PROD001',
        'warehouse_code': 'WH2',
        'quantity': 50,
        'unit_cost': 50.00,
        'description': 'ยกยอดคลังสาขา'
    },
    {
        'product_code': 'PROD002',
        'warehouse_code': 'WH/Stock',
        'quantity': 200,
        'unit_cost': 30.00,
        'description': 'ยกยอดเริ่มต้น'
    },
]

# ทดสอบก่อน
results = bulk_create_initial_stock(env, stock_data, dry_run=True)

# ดำเนินการจริง
results = bulk_create_initial_stock(env, stock_data, dry_run=False)

print(f"Success: {results['success']}, Failed: {results['failed']}")
```

### อ่านจาก CSV File

1. สร้างไฟล์ CSV: `initial_stock.csv`
```csv
product_code,warehouse_code,quantity,unit_cost,description
PROD001,WH/Stock,100,50.00,ยกยอดคลังหลัก
PROD001,WH2,50,50.00,ยกยอดคลังสาขา
PROD002,WH/Stock,200,30.00,ยกยอดเริ่มต้น
```

2. รัน script:
```python
import csv

# โหลด script
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/create_initial_stock_by_warehouse.py')

# อ่านข้อมูลจาก CSV
def load_from_csv(filepath):
    stock_data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stock_data.append({
                'product_code': row['product_code'],
                'warehouse_code': row['warehouse_code'],
                'quantity': float(row['quantity']),
                'unit_cost': float(row['unit_cost']),
                'description': row.get('description', 'ยกยอดเข้าระบบ')
            })
    return stock_data

# โหลดข้อมูล
stock_data = load_from_csv('/path/to/initial_stock.csv')

# ทดสอบ
results = bulk_create_initial_stock(env, stock_data, dry_run=True)

# ดำเนินการจริง
results = bulk_create_initial_stock(env, stock_data, dry_run=False)
```

---

## ตรวจสอบผลลัพธ์

### ใน Odoo UI

1. ไปที่ **Inventory → Reporting → Stock Valuation**
2. Group By: **Warehouse > Product**
3. ตรวจสอบว่า:
   - Moved Qty = Remaining Qty (ถ้ายังไม่มีการตัดใช้)
   - แต่ละ warehouse แยกกันชัดเจน
   - Total Value ถูกต้อง

### ผ่าน Odoo Shell

```python
# ตรวจสอบ product ใน warehouse
SVL = env['stock.valuation.layer']
product = env['product.product'].search([('default_code', '=', 'PROD001')], limit=1)
warehouse = env['stock.warehouse'].search([('code', '=', 'WH/Stock')], limit=1)

layers = SVL.search([
    ('product_id', '=', product.id),
    ('warehouse_id', '=', warehouse.id)
], order='create_date ASC')

total_qty = sum(layers.mapped('quantity'))
total_remain = sum(layers.mapped('remaining_qty'))
total_value = sum(layers.mapped('value'))
total_remain_value = sum(layers.mapped('remaining_value'))

print(f"Product: {product.display_name}")
print(f"Warehouse: {warehouse.name}")
print(f"Total Qty: {total_qty:,.2f}")
print(f"Remaining Qty: {total_remain:,.2f}")
print(f"Total Value: {total_value:,.2f}")
print(f"Remaining Value: {total_remain_value:,.2f}")

for layer in layers:
    print(f"\nLayer {layer.id}:")
    print(f"  Qty: {layer.quantity:,.2f}, Remaining: {layer.remaining_qty:,.2f}")
    print(f"  Cost: {layer.unit_cost:,.2f}, Value: {layer.value:,.2f}")
```

---

## Troubleshooting

### ปัญหา 1: ไม่พบสินค้า

**ข้อความ**: `ไม่พบสินค้า: PROD001`

**วิธีแก้**:
```python
# ตรวจสอบรหัสสินค้า
products = env['product.product'].search([
    ('default_code', 'ilike', 'PROD')
])
for p in products:
    print(f"{p.default_code}: {p.name}")
```

### ปัญหา 2: ไม่พบคลัง

**ข้อความ**: `ไม่พบคลัง: WH/Stock`

**วิธีแก้**:
```python
# ตรวจสอบรหัสคลัง
warehouses = env['stock.warehouse'].search([])
for wh in warehouses:
    print(f"{wh.code}: {wh.name}")
```

### ปัญหา 3: Remaining Qty ยังไม่ถูกต้อง

**วิธีแก้**:
1. รัน `fix_valuation_by_warehouse.py` อีกครั้ง
2. ตรวจสอบว่ามี negative layers ก่อน positive layers หรือไม่ (ผิดลำดับ)
3. ตรวจสอบ `create_date` ของ layers

```python
# ตรวจสอบลำดับ layers
layers = SVL.search([
    ('product_id', '=', product.id),
    ('warehouse_id', '=', warehouse.id)
], order='create_date ASC, id ASC')

for layer in layers:
    print(f"{layer.create_date} | Qty: {layer.quantity:,.2f} | "
          f"Remain: {layer.remaining_qty:,.2f}")
```

---

## Best Practices

1. **ทดสอบก่อนเสมอ**: ใช้ `dry_run=True` ก่อนทุกครั้ง
2. **Backup ข้อมูล**: ก่อนรัน script จริง
3. **ตรวจสอบผลลัพธ์**: ดูใน UI และ shell
4. **รันทีละ warehouse**: ถ้ามีข้อมูลเยอะ แยกรันทีละคลัง
5. **บันทึกล็อก**: เก็บ output ของ script ไว้อ้างอิง

---

## ติดต่อ/ขอความช่วยเหลือ

หากพบปัญหาหรือต้องการความช่วยเหลือ:
1. ตรวจสอบ log file: `/var/log/odoo/instance1.log`
2. เปิด issue ใน GitHub
3. ติดต่อทีม APC Ball

---

**เวอร์ชัน**: 17.0.1.1.3  
**อัปเดตล่าสุด**: 2025-11-28  
**ผู้เขียน**: APC Ball
