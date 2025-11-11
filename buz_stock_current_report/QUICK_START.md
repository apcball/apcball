# Quick Start - buz_stock_current_report

## Module Installation

### Step 1: Module is Ready
The module code has been updated and is located at:
```
/opt/instance1/odoo17/custom-addons/buz_stock_current_report/
```

### Step 2: Activate the Module

**Option A - Through Odoo UI:**
1. Open http://localhost:8069
2. Go to Apps → Modules → Update Apps List
3. Search for "Current Stock Report"
4. Click "Upgrade" button

**Option B - Command Line (if server is down):**
```bash
cd /opt/instance1
sudo -u odoo /opt/instance1/odoo17/odoo-bin -d odoo17 -u buz_stock_current_report --stop-after-init
```

**Option C - Restart Service:**
```bash
sudo systemctl restart instance1
```

## After Installation - What You'll See

### Location in Menu
```
Inventory (or Stock)
├── Reports
│   └── Current Stock Report
│       ├── Current Stock View ← This is the main report
│       └── Export Stock to Excel
```

### Tree View Display
Shows a table with these columns:
- **Product** - Product name and code
- **Unit Cost** - ฿220.00 (from product standard price)
- **Total Value** - ฿167,288.00 (Quantity × Unit Cost)
- **On Hand** - 760.4000 (current stock quantity)
- **Free to Use** - 388.4000 (available qty after allocations)
- **Incoming** - 12.0000 (pending purchase orders)
- **Outgoing** - 385.6600 (pending sales orders)
- **Unit** - PCS (unit of measure)

### Interactive Features
- **Search/Filter**: Filter by Product, Location, or Category
- **Group By**: Organize by Location (default), Category, or Product
- **Zero Filter**: "Hide Zero Quantity" to show only items with stock
- **Click Row**: Opens detailed form view with:
  - History button → View past movements
  - Replenishment button → View reorder suggestions
  - Locations button → See stock across warehouses
  - Forecast button → View stock forecast

## Key Fields in the Report

| Field | Type | Source | Purpose |
|-------|------|--------|---------|
| Product | Link | stock.quant → product | Identifies the item |
| Location | Link | stock.quant → location | Warehouse/zone |
| Category | Link | product.template → category | Product grouping |
| Unit Cost | Number | product.template.standard_price | Base item cost |
| Total Value | Calculation | Qty × Unit Cost | Inventory value |
| On Hand | Number | stock.quant.quantity | Actual stock count |
| Free to Use | Number | On Hand minus allocations | Available qty |
| Incoming | Number | Pending purchases | Expected arrivals |
| Outgoing | Number | Pending sales | Expected shipments |
| UoM | Link | product.template.uom_id | Measurement unit |

## Data Updates
- **Real-time**: On-hand quantity updates automatically
- **Incoming/Outgoing**: Updates when purchase/sale orders change state
- **Cost**: Pulls from product standard price (updates when price changes)

## Troubleshooting

### Issue: "Module not found" after upgrade
**Solution**: 
- Click "Update Apps List" first
- Clear browser cache (Ctrl+Shift+Delete)
- Refresh page

### Issue: No data appearing
**Check:**
1. Stock locations exist (Inventory → Configuration → Locations)
2. Products have cost set (Product → Standard Cost field)
3. Stock movements exist (Stock → Operations → Moves)

### Issue: All columns showing zeros
**Likely causes:**
- Products don't have standard_price set
- No stock exists in internal locations
- No purchase/sale orders created

### Issue: Column headers not in right order
- Clear cache and refresh (F5 or Ctrl+R)
- Check if form was customized (reset to default)

## Accessing the Report

### Method 1: Menu Navigation
```
Inventory → Reports → Current Stock Report → Current Stock View
```

### Method 2: Search Box
```
Type: "Current Stock Report" in search bar
Then: Click on "Current Stock View" action
```

### Method 3: Direct Link (if known)
```
http://localhost:8069/web#action=[action_id]&model=stock.current.report
```

## Using Filters

### Find products by location:
1. Click search filter icon
2. Click "Location" field
3. Select location from dropdown

### Hide empty items:
1. Click search filter icon
2. Select "Hide Zero Quantity" checkbox

### Group by category:
1. Click "Group By" dropdown
2. Select "Category"

## Export to Excel

1. Go to Current Stock Report → Export Stock to Excel
2. Select date range (defaults to today)
3. Click "Export"
4. Excel file downloads with full stock data

## Common Adjustments

### Change default grouping from Location to Product:
Edit XML in `stock_current_report_views.xml`:
```xml
<field name="context">{'search_default_group_product': 1}</field>
```

### Add more columns to tree view:
Edit tree view to add fields like category_id:
```xml
<field name="category_id" readonly="1"/>
```

### Customize column order:
Reorder fields in the tree view XML to match desired display

## Performance Notes

- Report loads stock from database view (optimized queries)
- Initial load may take a few seconds if many products exist
- Search/filter operations are optimized with indexes
- Totals calculate on-the-fly in real-time

## For Developers

### Files Modified:
1. `models/stock_current_report.py` - Added fields & SQL view
2. `views/stock_current_report_views.xml` - Enhanced tree/form/search views

### Add Custom Field:
1. Add field in model: `my_field = fields.Float(...)`
2. Add to SQL view: `pt.field AS my_field`
3. Add to tree view: `<field name="my_field"/>`

### Debug Issues:
- Check logs: `/tmp/upgrade.log`
- Database logs: PostgreSQL logs
- Odoo server logs: `journalctl -u instance1`

## Support Documentation

For detailed information, see:
- `IMPLEMENTATION.md` - Full technical details
- `CHANGES_SUMMARY.md` - What was changed
- `__manifest__.py` - Module metadata

---

**Last Updated**: November 11, 2025
**Module Version**: 17.0.1.0.0
**Status**: Ready for Installation
