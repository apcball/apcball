# วิเคราะห์ Module stock_fifo_by_location

## 📋 สรุปโดยทั่วไป

Module `stock_fifo_by_location` เป็นการขยายระบบการประเมินค่า Stock (Stock Valuation) ของ Odoo 17 เพื่อรองรับการคำนวณ FIFO (First-In-First-Out) บนพื้นฐาน **per-location** ทีละสถานที่เก็บรักษา

### 🎯 ปัญหาหลักที่แก้ไข

Odoo 17 ปกติใช้ FIFO แบบ company-wide ซึ่งสามารถทำให้การคำนวณต้นทุนไม่ถูกต้องเมื่อ:
- มีสินค้าเก็บในหลายสถานที่ (Multi-warehouse)
- ใช้ Transit Location สำหรับการถ่ายโอนสินค้าระหว่างคลังสินค้า
- ต้องทำบัญชีต้นทุนสินค้าขายได้ (COGS) อย่างแม่นยำต่อสถานที่

---

## 🏗️ สถาปัตยกรรมโมดูล

### โครงสร้างไฟล์

```
stock_fifo_by_location/
├── __init__.py                          # Package initialization
├── __manifest__.py                      # Metadata โมดูล
├── models/
│   ├── __init__.py                     # Package
│   ├── stock_valuation_layer.py        # ✅ ขยาย model หลัก
│   ├── stock_move.py                   # ✅ จัดการการบันทึกสถานที่
│   └── fifo_service.py                 # ✅ Service สำหรับการคำนวณ
├── security/
│   └── ir.model.access.csv             # Access control
├── data/
│   └── config_parameters.xml           # ตั้งค่าเริ่มต้นโมดูล
├── views/
│   └── stock_valuation_layer_views.xml # UI extension
├── migrations/
│   └── populate_location_id.py         # 🔧 Script migrate ข้อมูลเดิม
├── tests/
│   └── test_fifo_by_location.py        # ✅ Test cases
└── README.md                            # เอกสาร
```

---

## 🔑 Component หลัก

### 1. **stock_valuation_layer.py** - Core Model Extension

#### ฟิลด์ใหม่
```python
location_id = fields.Many2one('stock.location', ...)
```

**คุณลักษณะ:**
- 🔗 Indexed สำหรับ query เร็ว
- 🚫 ondelete='restrict' ป้องกัน orphaned records
- ⚙️ Mandatory ในหลายสถานการณ์

#### Method สำคัญ

| Method | วัตถุประสงค์ |
|--------|-----------|
| `_create_layer_from_layer_request()` | Capture location เมื่อสร้าง layer ใหม่ |
| `create(vals)` | Set location_id จาก context หรือ stock.move |
| `_get_fifo_queue()` | ดึง FIFO queue สำหรับ product ที่สถานที่นั้น |
| `_get_total_available_qty()` | คำนวณ qty ทั้งหมดในอยู่ queue |

**ตรรกะการกำหนดสถานที่:**

```python
# สำหรับ Positive Layer (รับเข้า)
layer_qty > 0 → use destination location

# สำหรับ Negative Layer (ส่งออก)
layer_qty < 0 → use source location (warehouse)
                UNLESS source is non-internal
                THEN use destination
```

---

### 2. **fifo_service.py** - Service Layer

#### AbstractModel สำหรับการคำนวณ FIFO

**Service Methods:**

| Method | ฟังก์ชั่น | Return |
|--------|---------|--------|
| `get_valuation_layer_queue()` | ดึง FIFO queue | Recordset (sorted by create_date) |
| `get_available_qty_at_location()` | จำนวน qty พร้อม | float |
| `calculate_fifo_cost()` | คำนวณ COGS | dict {cost, qty, unit_cost, layers[]} |
| `validate_location_availability()` | ตรวจสอบพอ/ไม่พอ | dict {available, shortage, fallback_locs} |
| `get_shortage_policy()` | อ่านนโยบาย | 'error' \| 'fallback' |

#### ตัวอย่าง calculate_fifo_cost()

```
Input:
  product_id = Product X
  location_id = Warehouse A
  quantity = 12 units

Layers in queue (oldest first):
  Layer 1: 10 units @ $100 each
  Layer 2: 5 units @ $120 each

Consumption (FIFO):
  - 10 units from Layer 1 @ $100 = $1,000
  - 2 units from Layer 2 @ $120 = $240
  
Output:
{
  'cost': 1240.0,
  'qty': 12.0,
  'unit_cost': 103.33,
  'layers': [
    {'layer_id': 1, 'qty_consumed': 10, 'unit_cost': 100, 'cost': 1000},
    {'layer_id': 2, 'qty_consumed': 2, 'unit_cost': 120, 'cost': 240}
  ]
}
```

#### Shortage Policy

**Error Mode (Default):**
- ❌ Block delivery ถ้าไม่พอ stock ที่สถานที่นั้น
- ⚠️ Raise UserError
- 🛡️ ป้องกัน shipment จากสถานที่ผิด

**Fallback Mode:**
- ✅ อนุญาตเอาสินค้าจากสถานที่อื่น
- 📝 Log การใช้ fallback
- 🔍 Audit trail

---

### 3. **stock_move.py** - Stock Move Override

#### Method เพิ่มเติม

| Method | วัตถุประสงค์ |
|--------|-----------|
| `_get_fifo_valuation_layer_location()` | กำหนดสถานที่ที่ถูกต้องตามประเภท move |
| `_create_valuation_layers_for_internal_transfer()` | สร้าง layer สำหรับการโอนย้ายภายใน |
| `_update_created_layers_location()` | Update location ของ layer ที่สร้างแล้ว |

#### ตรรกะการกำหนดสถานที่ (Priority Order)

```
Supplier/Production → Internal/Transit    → use destination
Customer → Internal                       → use destination
Transit → Internal (receipt)              → use destination
Transit → Transit                         → use destination
Internal → Transit (shipment)             → use source
Internal → Internal (transfer)            → use destination
Internal → Customer/Supplier (outgoing)   → use source
```

#### Transit Location Scenarios ที่รองรับ

```
1. Warehouse A → Transit → Warehouse B:
   Step 1: Negative layer (A), Positive layer (Transit)
   Step 2: Negative layer (Transit), Positive layer (B)

2. Direct Transit:
   Supplier → Transit → Customer

3. Production → Transit → Warehouse
```

---

## 🎮 Configuration & Settings

ไฟล์: `data/config_parameters.xml`

| Parameter | Default | Values | Purpose |
|-----------|---------|--------|---------|
| `stock_fifo_by_location.shortage_policy` | `error` | 'error', 'fallback' | นโยบายจัดการ shortage |
| `stock_fifo_by_location.enable_validation` | `True` | True/False | เปิด/ปิด location validation |
| `stock_fifo_by_location.debug_mode` | `False` | True/False | เปิด debug logging |

**การตั้งค่า:**
Settings → Technical → Parameters

---

## 📊 Data Flow & Workflow

### 1. Incoming Receipt (รับเข้า)

```
Purchase Order Approved
         ↓
PO Receipt Created (location_dest_id = Location A)
         ↓
Receipt Validated (stock.move done)
         ↓
stock.valuation.layer created:
  ├─ product_id = Product X
  ├─ location_id = Location A ✅
  ├─ quantity = 100
  ├─ unit_cost = $100
  └─ value = $10,000
```

### 2. Internal Transfer (โอนย้ายภายใน)

```
Internal Transfer: Location A → Location B (50 units)
         ↓
Transfer Validated (stock.move done)
         ↓
Valuation Layers:
  ├─ Negative: location_id = Location A, qty = -50 ✅
  └─ Positive: location_id = Location B, qty = +50 ✅
  
(Cost basis maintained from Location A)
```

### 3. Outgoing Delivery (ส่งออก)

```
Sales Order Shipped from Location A (30 units)
         ↓
Delivery Validated (stock.move done)
         ↓
FIFO Consumption (Location A queue):
  - Check Location A availability: 100 units ✅
  - Consume from oldest layers at Location A ✅
         ↓
stock.valuation.layer created:
  ├─ quantity = -30
  ├─ location_id = Location A ✅
  ├─ COGS = $3,000 (using Location A's FIFO)
  └─ Journal Entry:
       Debit: COGS $3,000
       Credit: Inventory $3,000
```

### 4. Transit Transfer (Warehouse A → Warehouse B)

```
Inter-warehouse Transfer (Warehouse A → Warehouse B)
         ↓
Step 1: Create internal move (A → Transit location)
  ├─ Negative layer: location_id = Warehouse A
  └─ Positive layer: location_id = Transit
         ↓
Step 2: Create receipt move (Transit → Warehouse B)
  ├─ Negative layer: location_id = Transit
  └─ Positive layer: location_id = Warehouse B
         ↓
Result: Inventory moved with correct location tracking at each step
```

---

## 🧪 Testing

### Test Coverage

ไฟล์: `tests/test_fifo_by_location.py` (482 lines)

| Scenario | Test Name | Status |
|----------|-----------|--------|
| Incoming receipt ที่ location | `test_incoming_receipt_location_captured` | ✅ |
| FIFO queue isolation | `test_fifo_queue_retrieval_by_location` | ✅ |
| Cost calculation (FIFO) | `test_fifo_cost_calculation_at_location` | ✅ |
| Multiple locations, isolated FIFO | `test_multiple_locations_isolated_fifo` | ✅ |
| Shortage: error mode | `test_location_shortage_error_mode` | ✅ |
| Shortage: fallback mode | `test_location_shortage_fallback_mode` | ✅ |
| Internal transfers | `test_internal_transfer_location_assignment` | ✅ |

### วิธีรันทดสอบ

```bash
# Via pytest
pytest -xvs addons/stock_fifo_by_location/tests/test_fifo_by_location.py

# Via Odoo
python -m odoo.bin -d your_database -m stock_fifo_by_location --test-enable

# Via UI
Settings → Developer Tools → Activate
Apps → stock_fifo_by_location → Tests
```

---

## 🔧 Migration Script

### ไฟล์: `migrations/populate_location_id.py` (612 lines)

#### ฟังก์ชันหลัก

| ฟังก์ชั่น | วัตถุประสงค์ | Supports |
|----------|-----------|----------|
| `populate_location_id()` | Main migration | Internal, Transit, Supplier, Production |
| `populate_transit_location_layers()` | Transit only | Transit location scenarios |
| `analyze_transit_locations()` | Pre-migration analysis | Transit diagnostics |

#### ตรรกะ Priority

```
Priority 1: Direct link from stock.move (destination location)
Priority 2: Fallback from stock.move.line (destination)
Priority 3: Temporal matching (±1 day window)
Priority 4: Manual review needed
```

#### วิธีใช้

```python
# Via Odoo Shell
python -m odoo.bin shell -d your_database

# Basic migration
>>> from odoo.addons.stock_fifo_by_location.migrations import populate_location_id
>>> result = populate_location_id.populate_location_id(env)
>>> print(f"Successful: {result['successful']}, Failed: {result['failed']}")

# Transit-only
>>> result = populate_location_id.populate_transit_location_layers(env)

# Pre-migration analysis
>>> stats = populate_location_id.analyze_transit_locations(env)
```

#### Scenarios ที่ Support

✅ Internal → Transit (warehouse shipments)  
✅ Transit → Internal (warehouse receipts)  
✅ Transit → Transit (inter-transit moves)  
✅ Supplier → Transit (direct imports)  
✅ Transit → Customer (direct deliveries)

---

## 📈 Database Queries

### หา Valuation Layers ที่ขาด location_id

```sql
SELECT COUNT(*) FROM stock_valuation_layer WHERE location_id IS NULL;
```

### Inventory value per location

```sql
SELECT 
    sl.id,
    sl.name,
    COUNT(svl.id) as layer_count,
    SUM(svl.quantity) as total_qty,
    SUM(svl.value) as total_value
FROM stock_valuation_layer svl
LEFT JOIN stock_location sl ON svl.location_id = sl.id
GROUP BY sl.id, sl.name
ORDER BY total_value DESC;
```

### FIFO queue สำหรับ product

```sql
SELECT 
    svl.id,
    p.name as product,
    sl.name as location,
    svl.quantity,
    svl.unit_cost,
    svl.value,
    svl.create_date
FROM stock_valuation_layer svl
JOIN product_product p ON svl.product_id = p.id
JOIN stock_location sl ON svl.location_id = sl.id
WHERE p.id = <product_id>
  AND sl.id = <location_id>
  AND svl.quantity > 0
ORDER BY svl.create_date ASC;
```

---

## ⚠️ Known Limitations & Considerations

### ✅ Supported
- Multi-company behavior (separate queues per company)
- Multi-warehouse (isolated FIFO per location)
- Transit locations (full FIFO tracking)
- Internal transfers
- Scrap and adjustments
- Negative quantities (excluded from FIFO)

### ❌ Not Supported
- Standard costing products (module won't affect them)
- Products using weighted average (override Odoo's default behavior)

### 🔧 Edge Cases
- Negative quantities: logged but excluded from FIFO queue
- Rounding: uses Odoo's precision settings (Product Price)
- Orphaned layers (no related move): needs manual review

---

## 🚀 Advanced Usage

### Custom Behavior Extension

```python
# ตัวอย่าง: Inherit FIFO Service
class CustomFifoService(models.AbstractModel):
    _inherit = 'fifo.service'
    
    @api.model
    def get_valuation_layer_queue(self, product_id, location_id, company_id=None):
        queue = super().get_valuation_layer_queue(product_id, location_id, company_id)
        # Custom filtering/logging
        return queue
```

### Override Location Logic

```python
class CustomStockMove(models.Model):
    _inherit = 'stock.move'
    
    def _get_fifo_valuation_layer_location(self):
        # Custom location determination
        return super()._get_fifo_valuation_layer_location()
```

---

## 🔍 Troubleshooting

### ❌ Layers Missing location_id

**สาเหตุ:**
- Module ติดตั้งแต่มีข้อมูลเดิมแล้ว
- Enable_validation = False

**วิธีแก้:**
```bash
cd /path/to/odoo17
python -m odoo.bin shell -d your_database
>>> exec(open('migrations/populate_location_id.py').read())
>>> populate_location_id(env)
```

### ❌ Unexpected COGS Amounts

**Debug Steps:**
1. Enable debug_mode ใน Settings
2. Query FIFO queue:
   ```python
   layers = env['fifo.service'].get_valuation_layer_queue(product, location)
   for layer in layers:
       print(f"Layer {layer.id}: qty={layer.quantity}, cost={layer.unit_cost}")
   ```
3. ตรวจสอบ shortage policy
4. ค้นหา negative quantities ใน queue

### ❌ Migration Fails

**สาเหตุ:**
- Orphaned layers (no related move)
- Circular location relationships

**วิธีแก้:**
```sql
-- Check orphaned layers
SELECT svl.* FROM stock_valuation_layer svl
LEFT JOIN stock_move sm ON svl.stock_move_id = sm.id
WHERE svl.stock_move_id IS NOT NULL AND sm.id IS NULL;

-- Manually assign location
UPDATE stock_valuation_layer 
SET location_id = <warehouse_id>
WHERE id = <layer_id>;
```

---

## 📊 Performance Metrics

### Optimization
- `location_id` is **indexed** → fast FIFO queue retrieval
- Recommend periodic: `VACUUM ANALYZE stock_valuation_layer`
- Monitor for orphaned layers regularly

### Scalability
- ✅ Works with large datasets (tested with 100K+ layers)
- ✅ Transit location migration optimized
- ✅ Batch processing for bulk operations

---

## 📝 Key Takeaways

| ลักษณะ | รายละเอียด |
|--------|-----------|
| **หัวใจของโมดูล** | Per-location FIFO tracking via `location_id` field |
| **ปัญหาที่แก้** | Accurate COGS in multi-warehouse environments |
| **ประเภทสถานที่** | Internal, Transit, Supplier, Customer, Production |
| **Core Methods** | `_get_fifo_queue()`, `calculate_fifo_cost()`, `validate_location_availability()` |
| **Migration** | Intelligent backfill with transit location support |
| **Testing** | 7+ test cases covering all scenarios |
| **Config** | 3 parameters (shortage_policy, enable_validation, debug_mode) |

---

## 📚 Documentation Files

- `README.md` - Comprehensive user guide
- `TRANSIT_LOCATION_MIGRATION_GUIDE.md` - Transit-specific migration
- `QUICK_START.md` - Quick setup guide
- `MANUAL_TESTING.md` - Testing procedures
- `INSTALLATION_CHECKLIST.md` - Installation steps

---

**Version:** 17.0.1.0.0  
**License:** LGPL-3  
**Author:** APC Ball  
**Repository:** https://github.com/apcball/apcball
