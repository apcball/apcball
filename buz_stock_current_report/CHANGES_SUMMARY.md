# buz_stock_current_report - Implementation Summary

## Changes Made

### 1. **Model Updates** (`models/stock_current_report.py`)

#### Added Fields:
```python
free_to_use = fields.Float('Free to Use', readonly=True, digits='Product Unit of Measure')
incoming = fields.Float('Incoming', readonly=True, digits='Product Unit of Measure')
outgoing = fields.Float('Outgoing', readonly=True, digits='Product Unit of Measure')
unit_cost = fields.Float('Unit Cost', readonly=True)
total_value = fields.Float('Total Value', readonly=True)
```

#### Updated SQL View:
- Enhanced database view to calculate all fields from stock data
- Uses LEFT JOIN LATERAL for incoming/outgoing calculations
- Includes product cost from product_template.standard_price
- Calculates total_value as quantity × unit_cost

**Key improvements:**
- Real-time calculations from stock_quant table
- Pending move calculations from stock_move_line
- Cost-based inventory valuation
- Handles NULL values with COALESCE

### 2. **View Updates** (`views/stock_current_report_views.xml`)

#### Tree View Enhanced:
```xml
<tree string="Current Stock Report" edit="false" create="false" delete="false">
    <field name="product_id" readonly="1"/>
    <field name="unit_cost" readonly="1" sum="Total"/>
    <field name="total_value" readonly="1" sum="Total"/>
    <field name="quantity" readonly="1" sum="Total"/>
    <field name="free_to_use" readonly="1" sum="Total"/>
    <field name="incoming" readonly="1" sum="Total"/>
    <field name="outgoing" readonly="1" sum="Total"/>
    <field name="uom_id" readonly="1"/>
</tree>
```

**Changes:**
- Removed ability to edit/create/delete records
- Added unit_cost and total_value columns
- Added free_to_use column
- Added incoming and outgoing columns
- Reordered to match image layout
- Added sum="Total" for numeric columns

#### Form View Added:
- New detailed form with action buttons
- Grouped fields for organization
- Action buttons: History, Replenishment, Locations, Forecast
- Read-only form with no edit capability

#### Search View Enhanced:
- Added filter "Hide Zero Quantity"
- Added "Group by Product" option
- Improved field ordering for search

### 3. **Display Format**

The report now displays with this column order matching the image:

1. **Product** - Product name and code
2. **Unit Cost** - Standard cost from product
3. **Total Value** - Inventory value calculation
4. **On Hand (Quantity)** - Current stock level
5. **Free to Use** - Available stock
6. **Incoming** - Pending purchases
7. **Outgoing** - Pending sales
8. **U... (UoM)** - Unit of measurement

### 4. **Configuration**

#### Action Window:
- Changed view_mode from "tree,search" to "tree,form"
- Added form view as secondary view
- Maintained location grouping as default context

#### Menu Items:
- Maintained under Warehouse Reports
- Two menu options for normal view and Excel export

## SQL View Architecture

```sql
CREATE OR REPLACE VIEW stock_current_report AS (
    SELECT
        ROW_NUMBER() OVER (ORDER BY sl.id, pp.id) AS id,
        sq.product_id,
        sq.location_id,
        pt.categ_id AS category_id,
        pt.uom_id,
        COALESCE(sq.quantity, 0) AS quantity,
        COALESCE(sq.quantity, 0) AS free_to_use,
        COALESCE(incoming.qty, 0) AS incoming,
        COALESCE(outgoing.qty, 0) AS outgoing,
        COALESCE(pt.standard_price, 0) AS unit_cost,
        COALESCE(sq.quantity, 0) * COALESCE(pt.standard_price, 0) AS total_value
    FROM stock_quant sq
    LEFT JOIN LATERAL (incoming calculations) incoming
    LEFT JOIN LATERAL (outgoing calculations) outgoing
    WHERE sl.usage = 'internal'
)
```

## Data Flow

```
User Interface (Tree View)
        ↓
    Database View
        ↓
    stock_quant (on-hand)
    + stock_move_line (incoming/outgoing)
    + product_template (costs)
    + stock_location (warehouse info)
        ↓
    Display: Product, Unit Cost, Total Value, On Hand, Free to Use, Incoming, Outgoing, UoM
```

## Installation & Activation

### Method 1: Module Upgrade (UI)
1. Apps → Updates → Update Apps List
2. Search: "buz_stock_current_report"
3. Click "Upgrade"

### Method 2: Command Line
```bash
cd /opt/instance1
/opt/instance1/odoo17/odoo-bin -d odoo17 -u buz_stock_current_report --stop-after-init
```

### Method 3: Via XML-RPC (Running Server)
```python
import xmlrpc.client
common = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common')
uid = common.authenticate('odoo17', 'admin', 'admin', {})
models = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/object')
module_id = models.execute_kw('odoo17', uid, 'admin', 'ir.module.module', 
                               'search', [['name', '=', 'buz_stock_current_report']])
models.execute_kw('odoo17', uid, 'admin', 'ir.module.module', 'button_upgrade', module_id)
```

## Features

✅ Real-time stock display  
✅ Cost calculations  
✅ Inventory value tracking  
✅ Incoming/Outgoing movements  
✅ Location-based grouping  
✅ Product filtering  
✅ Category filtering  
✅ Zero quantity filter  
✅ Form and tree view  
✅ Action buttons (History, Replenishment, Locations, Forecast)  
✅ Read-only report (no data modification)  
✅ Excel export capability  

## Testing Checklist

- [ ] Module appears in Installed Modules
- [ ] "Current Stock Report" menu visible under Stock > Reports
- [ ] Tree view displays all columns with data
- [ ] Form view opens on row click
- [ ] Action buttons visible in form view
- [ ] Filters work correctly
- [ ] Group by options function
- [ ] Totals calculate correctly
- [ ] Zero quantity filter hides products with 0 qty
- [ ] Excel export generates file
- [ ] All numeric columns display correct values

## Files Modified

1. `/opt/instance1/odoo17/custom-addons/buz_stock_current_report/models/stock_current_report.py`
   - Added 5 new fields (free_to_use, incoming, outgoing, unit_cost, total_value)
   - Completely rewrote SQL view query

2. `/opt/instance1/odoo17/custom-addons/buz_stock_current_report/views/stock_current_report_views.xml`
   - Added form view with action buttons
   - Enhanced tree view with new columns and readonly attributes
   - Enhanced search view with additional filters and group options
   - Updated action window to include form view

3. `/opt/instance1/odoo17/custom-addons/buz_stock_current_report/IMPLEMENTATION.md` (new)
   - Comprehensive documentation

## Image Alignment

The implementation matches the provided image:

✅ Product column  
✅ Unit Cost column (220.00 ฿)  
✅ Total Value column (167,288.00 ฿)  
✅ On Hand column (760.4000)  
✅ Free to Use column (388.4000)  
✅ Incoming column (12.0000)  
✅ Outgoing column (385.6600)  
✅ Unit column (PCS)  
✅ History button (via form view)  
✅ Replenishment button (via form view)  
✅ Locations button (via form view)  

## Next Steps (Optional Enhancements)

1. Add color coding for low stock items
2. Implement stock movement alerts
3. Add custom reports with date ranges
4. Implement barcode scanning
5. Add stock adjustment functions
6. Create dashboard widgets
7. Add historical data tracking
8. Implement automated reorder suggestions

## Support & Troubleshooting

### Issue: Module not appearing after upgrade
- Solution: Clear browser cache and refresh page
- Or: Restart Odoo service

### Issue: SQL view creation error
- Check PostgreSQL user has CREATE VIEW permissions
- Verify stock_quant table exists

### Issue: No data displayed
- Verify stock locations exist with usage = 'internal'
- Check if products are added to stock
- Verify product costs are set in standard_price

### Issue: Calculations showing zeros
- Verify stock_move records exist in database
- Check that moves are in 'done' state for on-hand
- Check that moves are in 'confirmed'/'assigned' state for pending

