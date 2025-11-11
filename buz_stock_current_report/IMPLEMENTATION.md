# buz_stock_current_report Module Implementation

## Overview
The `buz_stock_current_report` module has been implemented to display current stock levels with cost and value calculations, matching the UI from the provided image. The module provides real-time stock information with multiple views and export capabilities.

## Features Implemented

### 1. Data Model (stock_current_report.py)
Added comprehensive fields to match the image display:
- **product_id**: Link to product (Many2one to product.product)
- **location_id**: Warehouse/location (Many2one to stock.location)
- **category_id**: Product category (Many2one to product.category)
- **uom_id**: Unit of Measure (Many2one to uom.uom)
- **quantity**: Current on-hand quantity (Float)
- **free_to_use**: Available quantity after allocations (Float)
- **incoming**: Inbound stock movements (Float)
- **outgoing**: Outbound stock movements (Float)
- **unit_cost**: Product standard cost (Float)
- **total_value**: Quantity × Unit Cost calculation (Float)

### 2. Database View
The module uses a PostgreSQL view for real-time data calculation:

**Key calculations:**
- **quantity**: COALESCE(sq.quantity, 0) - Current on-hand from stock_quant
- **free_to_use**: Same as quantity for available stock
- **incoming**: SUM of stock moves in confirmed/assigned state to the location
- **outgoing**: SUM of stock moves in confirmed/assigned state from the location
- **unit_cost**: product_template.standard_price
- **total_value**: quantity × unit_cost

**Data joins:**
- stock_quant (current quantities)
- product_product (product details)
- product_template (template and cost info)
- stock_location (location/warehouse info)
- stock_move_line + stock_move (for incoming/outgoing calculations)

### 3. Tree View
The main report view displays all columns as shown in the image:
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

**Features:**
- Read-only display (edit="false", create="false", delete="false")
- Totals for numeric columns (sum="Total")
- All fields are readonly to prevent modifications

### 4. Form View
A detailed form view with action buttons matching the image:
```xml
<form string="Current Stock" create="false" delete="false" edit="false">
    <div class="oe_button_box" name="button_box">
        <button type="action" name="action_view_quant_history" class="oe_stat_button" icon="fa-history">
            <span>History</span>
        </button>
        <button type="action" name="action_view_replenishment" class="oe_stat_button" icon="fa-refresh">
            <span>Replenishment</span>
        </button>
        <button type="action" name="action_view_locations" class="oe_stat_button" icon="fa-map-marker">
            <span>Locations</span>
        </button>
        <button type="action" name="action_view_forecast" class="oe_stat_button" icon="fa-line-chart">
            <span>Forecast</span>
        </button>
    </div>
    <!-- Additional fields grouped for organization -->
</form>
```

**Action Buttons:**
- **History**: View stock movement history for the product
- **Replenishment**: View replenishment recommendations
- **Locations**: View stock across all locations
- **Forecast**: View stock forecast

### 5. Search View
Enhanced filtering and grouping options:
- Search by Product, Location, Category
- Hide Zero Quantity filter
- Group by: Location, Category, or Product (with Location as default)

### 6. Menu Structure
- Parent Menu: Warehouse Reports (stock.menu_warehouse_report)
- Menu Items:
  - Current Stock View - Tree/Form views of all stock
  - Export Stock to Excel - Wizard for exporting data

## File Structure
```
buz_stock_current_report/
├── __init__.py
├── __manifest__.py
├── models/
│   ├── __init__.py
│   └── stock_current_report.py (Updated with all fields and SQL view)
├── views/
│   ├── stock_current_report_views.xml (Updated with tree, form, and search views)
│   └── stock_current_export_wizard_views.xml
├── wizard/
│   ├── __init__.py
│   └── stock_current_export_wizard.py
├── report/
└── security/
    └── stock_current_report_security.xml
```

## Installation Steps

1. **Module Update via UI:**
   - Go to Apps > Updates > Update Apps List
   - Search for "buz_stock_current_report"
   - Click "Upgrade" button

2. **Command Line (if needed):**
   ```bash
   cd /opt/instance1
   /opt/instance1/odoo17/odoo-bin -d odoo17 -u buz_stock_current_report --stop-after-init
   ```

3. **Via Terminal (with Odoo running):**
   - Access Odoo at http://localhost:8069
   - Apps → Modules → Search "Current Stock Report"
   - Click "Upgrade"

## Usage

1. **Access Report:**
   - Go to Stock > Reports > Current Stock Report > Current Stock View
   - Or: Inventory > Warehouse → Current Stock Report → Current Stock View

2. **Filter Data:**
   - Use search bar to filter by Product, Location, or Category
   - Apply "Hide Zero Quantity" filter to show only products with stock
   - Click "Group By" to organize by Location, Category, or Product

3. **View Details:**
   - Click on any row to open detailed form view
   - View cost information, quantities, and pending movements
   - Access related information via action buttons

4. **Export Data:**
   - Go to Current Stock Report > Export Stock to Excel
   - Select desired date
   - Click "Export" to download Excel file

## Data Mapping to Image

The tree view columns now match the image exactly:

| Column | Source | Calculation |
|--------|--------|-------------|
| Product | product_id | Product name from product.product |
| Unit Cost | unit_cost | product_template.standard_price |
| Total Value | total_value | quantity × unit_cost |
| On Hand | quantity | Current stock from stock_quant |
| Free to Use | free_to_use | Available quantity (same as On Hand) |
| Incoming | incoming | Confirmed/Assigned purchase orders |
| Outgoing | outgoing | Confirmed/Assigned sales orders |
| U... (UoM) | uom_id | Product unit of measure |

## SQL Query Details

The database view performs the following operations:

1. **Base Join**: Combines stock_quant with product and location information
2. **Cost Lookup**: Retrieves standard_price from product_template
3. **Incoming Calculation**: LEFT JOIN with filtered stock_move_line for pending receipts
4. **Outgoing Calculation**: LEFT JOIN with filtered stock_move_line for pending deliveries
5. **Value Calculation**: Multiplies quantity by unit_cost for inventory value

### Filtering Criteria:
- Only includes locations with usage = 'internal' (internal warehouses)
- Incoming: Moves in state 'confirmed', 'assigned', or 'partially_available'
- Outgoing: Moves in state 'confirmed', 'assigned', or 'partially_available'
- Excludes done and canceled movements from pending calculations

## Performance Considerations

- The view is read-only (no CREATE or UPDATE operations)
- Indexed joins on product_id and location_id
- Uses LATERAL joins for efficient subquery execution
- ROW_NUMBER() for unique ID generation
- COALESCE for NULL value handling

## Dependencies

- **stock**: Base stock management module
- **report_xlsx**: For Excel export functionality

## Security

- Defined in `security/stock_current_report_security.xml`
- Read-only access to the report view
- No creation, editing, or deletion of report records allowed
- Standard Odoo access control through ACLs

## Customization

To add additional fields:
1. Add field definition in `stock_current_report.py` class
2. Update the SQL view in the `init()` method
3. Add field to `stock_current_report_views.xml` tree view
4. Update manifest if new dependencies needed

## Notes

- The module creates a temporary view for real-time data
- View is automatically recreated when module is updated
- No permanent database modifications
- All calculations are read-only and reflected in real-time

## Support

For issues or questions:
- Check the module logs: `/tmp/upgrade.log`
- Verify database user has view creation permissions
- Ensure stock_quant table exists and is populated
- Validate that products have standard_price set
