# สรุปการแก้ไข JavaScript Assets - buz_stock_current_report

## ปัญหาที่พบ
1. **Import statements ผิด** - ListRenderer และ KanbanRenderer ถูก import จาก controller แทนที่จะเป็น renderer
2. **OWL Template Syntax ผิด** - ไม่มี `this.` prefix สำหรับการเรียกใช้ methods และ computed properties ใน XML template
3. **Asset loading issues** - ทำให้หน้าจอขาวและ JavaScript ไม่ทำงาน

## การแก้ไขที่ทำ

### 1. แก้ไข JavaScript Imports (`static/src/js/stock_current_report.js`)
```javascript
// เดิม (ผิด)
import { ListController, ListRenderer } from "@web/views/list/list_controller";
import { KanbanController, KanbanRenderer } from "@web/views/kanban/kanban_controller";

// ใหม่ (ถูก)
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
```

### 2. แก้ไข XML Template Syntax (`static/src/xml/stock_current_report.xml`)

เพิ่ม `this.` prefix สำหรับ:
- `this.isWarehouseSelected()` 
- `this.isWarehouseExpanded()`
- `this.isLocationSelected()`
- `this.getLocationTypeIcon()`
- `this.getStockStatusClass()`
- `this.formatMonetary()`
- `this.formatQuantity()`
- `this.filteredWarehouses`

**ตัวอย่าง:**
```xml
<!-- เดิม -->
<div t-if="isWarehouseExpanded(warehouse.id)">
<div t-att-class="isWarehouseSelected(warehouse.id) ? 'text-primary' : ''">
<strong t-esc="formatMonetary(warehouse.total_value)"/>

<!-- ใหม่ -->
<div t-if="this.isWarehouseExpanded(warehouse.id)">
<div t-att-class="this.isWarehouseSelected(warehouse.id) ? 'text-primary' : ''">
<strong t-esc="this.formatMonetary(warehouse.total_value)"/>
```

## คำสั่งที่ใช้

```bash
# 1. สำรองไฟล์ XML
cp /opt/instance1/odoo17/custom-addons/buz_stock_current_report/static/src/xml/stock_current_report.xml \
   /opt/instance1/odoo17/custom-addons/buz_stock_current_report/static/src/xml/stock_current_report.xml.backup

# 2. แก้ไข XML ด้วย sed
cd /opt/instance1/odoo17/custom-addons/buz_stock_current_report/static/src/xml
sed -i 's/t-att-class="isWarehouseSelected/t-att-class="this.isWarehouseSelected/g; \
        s/t-att-class="isWarehouseExpanded/t-att-class="this.isWarehouseExpanded/g; \
        s/t-att-class="isLocationSelected/t-att-class="this.isLocationSelected/g; \
        s/t-att-class="getLocationTypeIcon/t-att-class="this.getLocationTypeIcon/g; \
        s/t-att-class="getStockStatusClass/t-att-class="this.getStockStatusClass/g; \
        s/t-if="isWarehouseExpanded/t-if="this.isWarehouseExpanded/g; \
        s/t-if="!isLocationSelected/t-if="!this.isLocationSelected/g; \
        s/t-esc="formatMonetary/t-esc="this.formatMonetary/g; \
        s/t-esc="formatQuantity/t-esc="this.formatQuantity/g; \
        s/t-if="filteredWarehouses\.length/t-if="this.filteredWarehouses.length/g; \
        s/t-foreach="filteredWarehouses"/t-foreach="this.filteredWarehouses"/g' \
        stock_current_report.xml

# 3. รีสตาร์ท Odoo
sudo systemctl restart instance1
```

## การทดสอบ

### 1. ตรวจสอบ Assets Loading
```bash
# ตรวจสอบ log ว่าไม่มี JavaScript errors
tail -100 /var/log/odoo/instance1.log | grep -i "asset\|javascript\|error"
```

### 2. ตรวจสอบในเบราว์เซอร์
1. เปิด Developer Console (F12)
2. ไปที่ Inventory > Reports > Current Stock Report
3. ตรวจสอบว่า:
   - ไม่มี JavaScript errors ใน Console
   - หน้าจอแสดงผลปกติ (ไม่ขาว)
   - Assets ทั้งหมดโหลดสำเร็จ
   - Sidebar แสดงผล warehouses และ locations
   - Kanban cards แสดงผลถูกต้อง

### 3. ฟังก์ชันที่ต้องทำงาน
- ✅ แสดงรายการ warehouses ใน sidebar
- ✅ Expand/collapse warehouses
- ✅ Filter by warehouse หรือ location
- ✅ Search warehouses/locations
- ✅ Show only with stock checkbox
- ✅ Clear filters button
- ✅ Kanban cards แสดงข้อมูลสินค้า
- ✅ View Moves buttons

## ไฟล์ที่แก้ไข
1. `/opt/instance1/odoo17/custom-addons/buz_stock_current_report/static/src/js/stock_current_report.js`
2. `/opt/instance1/odoo17/custom-addons/buz_stock_current_report/static/src/xml/stock_current_report.xml`

## สถานะ
✅ แก้ไขเสร็จสิ้น - พร้อมทดสอบใน browser

## หมายเหตุ
- การแก้ไขนี้เป็นไปตามมาตรฐาน Odoo 17 OWL framework
- ต้องใช้ `this.` prefix สำหรับการเรียก methods และ computed properties ใน template
- Import statements ต้องแยก Controller และ Renderer ออกจากกัน
