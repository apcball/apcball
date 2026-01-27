# 🚀 Quick Start: แก้ไข Valuation ใน MOG_TEST

## วิธีที่ 1: ใช้ Quick Fix Script (แนะนำ)

```bash
cd /opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts
./quick_fix_mog_test.sh
```

จากนั้นเลือก:
- **1**: แก้ไขข้อมูล valuation ที่มีอยู่ (สำหรับข้อมูลที่ผิด)
- **2**: ยกของเข้าคลัง (สำหรับสร้าง stock ใหม่)
- **3**: ดูตัวอย่าง
- **4**: เปิด Odoo Shell

---

## วิธีที่ 2: รันใน Odoo Shell

### แก้ไขข้อมูลที่มีอยู่

```bash
cd /opt/instance1/odoo17
python3 odoo-bin shell -d MOG_TEST --no-http
```

```python
# โหลด script
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/fix_valuation_by_warehouse.py')

# ทดสอบก่อน
fix_valuation_by_warehouse(env, dry_run=True)

# บันทึกจริง (หลังจากตรวจสอบผลแล้ว)
fix_valuation_by_warehouse(env, dry_run=False)
```

### ยกของเข้าคลัง

```python
# โหลด script
execfile('/opt/instance1/odoo17/custom-addons/stock_fifo_by_location/scripts/create_initial_stock_by_warehouse.py')

# สร้างรายการเดียว
result = create_initial_stock_layer(
    env,
    product_code='PROD001',
    warehouse_code='WH/Stock',
    quantity=100,
    unit_cost=50.00,
    description='ยกยอดเริ่มต้น',
    dry_run=True  # เปลี่ยนเป็น False เมื่อพร้อมบันทึก
)
```

---

## ตรวจสอบผลลัพธ์

### ใน Odoo UI
1. Inventory → Reporting → **Stock Valuation**
2. Group By: **Warehouse > Product**
3. ตรวจสอบว่า **Moved Qty = Remaining Qty**

### ใน Database
```python
# ดูข้อมูล product ใน warehouse
SVL = env['stock.valuation.layer']
product = env['product.product'].search([('default_code', '=', 'PROD001')], limit=1)
warehouse = env['stock.warehouse'].search([('code', '=', 'WH/Stock')], limit=1)

layers = SVL.search([
    ('product_id', '=', product.id),
    ('warehouse_id', '=', warehouse.id)
])

print(f"Total Qty: {sum(layers.mapped('quantity'))}")
print(f"Remaining: {sum(layers.mapped('remaining_qty'))}")
```

---

## หมายเหตุสำคัญ

⚠️ **ก่อนรัน script**:
1. Backup database: `pg_dump -U postgres -d MOG_TEST > backup.sql`
2. ใช้ `dry_run=True` ทดสอบก่อนเสมอ
3. Stop Odoo instance ก่อนรัน (หรือใช้ API mode)

✅ **หลังรัน script**:
1. ตรวจสอบผลใน UI
2. Restart Odoo instance
3. ทดสอบการรับ-จ่ายสินค้า

---

## ต้องการความช่วยเหลือ?

📖 อ่านคู่มือฉบับเต็ม: `scripts/README.md`

🐛 พบปัญหา? เช็ค log: `/var/log/odoo/instance1.log`
