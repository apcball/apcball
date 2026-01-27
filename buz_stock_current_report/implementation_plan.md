# Implementation Plan: Add Transit Locations to Warehouse Sidebar

## Overview
Enhance the Current Stock View sidebar to show transit locations as a separate section for each warehouse.

## Current Implementation Analysis
- The sidebar currently only shows internal locations (`usage = 'internal'`) for each warehouse
- Data is fetched via `get_warehouses_with_internal_locations()` method in `stock_current_report.py`
- The JavaScript component `WarehouseSidebar` in `stock_current_report.js` handles the sidebar logic
- The XML template `WarehouseSidebar` in `stock_current_report.xml` renders the sidebar UI

## Implementation Steps

### 1. Update Python Model Method
**File:** `buz_stock_current_report/models/stock_current_report.py`

**Method to modify:** `get_warehouses_with_internal_locations()`

**Changes needed:**
1. Rename method to `get_warehouses_with_locations()` to reflect new functionality
2. Modify the main query to include both internal and transit locations
3. Create separate queries for internal and transit locations for each warehouse
4. Return warehouse data with two location arrays: `internal_locations` and `transit_locations`

**Implementation details:**
```python
@api.model
def get_warehouses_with_locations(self):
    """Enhanced method to include both internal and transit locations"""
    # Main warehouse query (unchanged)
    query = """
        SELECT
            w.id,
            w.name,
            w.code,
            COUNT(DISTINCT l.id) as location_count,
            COALESCE(SUM(s.total_products), 0) as total_products,
            COALESCE(SUM(s.total_value), 0) as total_value
        FROM stock_warehouse w
        LEFT JOIN stock_location l ON l.warehouse_id = w.id AND l.usage IN ('internal', 'transit') AND l.active = true
        LEFT JOIN (
            SELECT
                location_id,
                COUNT(DISTINCT product_id) as total_products,
                SUM(total_value) as total_value
            FROM stock_current_report
            GROUP BY location_id
        ) s ON s.location_id = l.id
        WHERE w.active = true
        GROUP BY w.id, w.name, w.code
        ORDER BY w.name
    """
    
    # Get internal locations for each warehouse
    internal_location_query = """
        SELECT
            l.id,
            l.name,
            l.complete_name,
            l.usage,
            COUNT(DISTINCT scr.product_id) as product_count,
            COALESCE(SUM(scr.quantity), 0) as total_quantity,
            COALESCE(SUM(scr.total_value), 0) as total_value
        FROM stock_location l
        LEFT JOIN stock_current_report scr ON scr.location_id = l.id
        WHERE l.warehouse_id = %s AND l.usage = 'internal' AND l.active = true
        GROUP BY l.id, l.name, l.complete_name, l.usage
        ORDER BY l.name
    """
    
    # Get transit locations for each warehouse
    transit_location_query = """
        SELECT
            l.id,
            l.name,
            l.complete_name,
            l.usage,
            COUNT(DISTINCT scr.product_id) as product_count,
            COALESCE(SUM(scr.quantity), 0) as total_quantity,
            COALESCE(SUM(scr.total_value), 0) as total_value
        FROM stock_location l
        LEFT JOIN stock_current_report scr ON scr.location_id = l.id
        WHERE l.warehouse_id = %s AND l.usage = 'transit' AND l.active = true
        GROUP BY l.id, l.name, l.complete_name, l.usage
        ORDER BY l.name
    """
```

### 2. Update JavaScript Component
**File:** `buz_stock_current_report/static/src/js/stock_current_report.js`

**Component to modify:** `WarehouseSidebar`

**Changes needed:**
1. Update the `loadWarehouses()` method to call the new method name
2. Modify the filtered locations logic to handle both location types
3. Update click handlers to work with the new structure

**Implementation details:**
```javascript
async loadWarehouses() {
    try {
        this.state.loading = true;
        const result = await this.orm.call(
            'stock.current.report',
            'get_warehouses_with_locations',  // Updated method name
            [],
            {}
        );
        this.state.warehouses = result || [];
    } catch (error) {
        // Error handling remains the same
    }
}
```

### 3. Update XML Template
**File:** `buz_stock_current_report/static/src/xml/stock_current_report.xml`

**Template to modify:** `buz_stock_current_report.WarehouseSidebar`

**Changes needed:**
1. Add a separate section for transit locations after internal locations
2. Use appropriate icons for transit locations (fa-exchange-alt)
3. Add styling to differentiate transit locations from internal locations

**Implementation details:**
```xml
<!-- After the internal locations list, add transit locations section -->
<!-- Transit Locations List -->
<div t-if="isWarehouseExpanded(warehouse.id) and warehouse.transit_locations and warehouse.transit_locations.length > 0" 
     class="transit-location-list ms-3 mt-2">
    <div class="location-type-header mb-2">
        <small class="text-muted fw-bold">
            <i class="fa fa-exchange-alt me-1"/>Transit Locations
        </small>
    </div>
    <div t-foreach="warehouse.transit_locations" t-as="location" t-key="location.id"
         class="location-item mb-2">
        <div class="card border-0 bg-light">
            <div class="card-body p-2">
                <div class="d-flex justify-content-between align-items-center"
                     t-att-class="isLocationSelected(location.id) ? 'bg-warning text-dark rounded' : ''"
                     t-on-click.stop="() => this.onLocationClick(location)">
                    <div class="d-flex align-items-center flex-grow-1">
                        <i class="fa fa-exchange-alt me-2 text-warning"/>
                        <div>
                            <div class="fw-bold">
                                <t t-esc="location.name"/>
                            </div>
                            <small class="text-muted" t-if="!isLocationSelected(location.id)">
                                <t t-esc="location.complete_name"/>
                            </small>
                        </div>
                    </div>
                    <div class="text-end">
                        <div class="badge bg-warning text-dark rounded-pill">
                            <t t-esc="location.product_count"/> products
                        </div>
                        <div class="small mt-1">
                            <span t-att-class="getStockStatusClass(location.total_quantity)">
                                Qty: <t t-esc="formatQuantity(location.total_quantity)"/>
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
```

### 4. Update CSS Styling
**File:** `buz_stock_current_report/static/src/css/stock_current_report.css`

**Add styles for transit locations:**
```css
/* Transit locations styling */
.transit-location-list {
    border-left: 3px solid #ffc107;
    padding-left: 10px;
}

.location-type-header {
    border-bottom: 1px dashed #dee2e6;
    padding-bottom: 5px;
    margin-bottom: 10px;
}

.transit-location-list .location-item {
    opacity: 0.9;
}

.transit-location-list .location-item:hover {
    opacity: 1;
}
```

### 5. Update Method References
**Files to update:**
- `buz_stock_current_report/views/stock_current_report_sidebar_views.xml` (if needed)

Make sure all references to the old method name are updated to the new method name.

## Testing Checklist
1. Verify that warehouses now show both internal and transit locations
2. Check that transit locations have appropriate icons (exchange-alt)
3. Ensure transit locations are displayed in a separate section
4. Test filtering functionality for both location types
5. Verify that clicking on transit locations filters the report correctly
6. Check that the badge colors for transit locations are different (warning/yellow)
7. Ensure the summary section correctly counts all locations

## Additional Considerations
- Consider adding a toggle to show/hide transit locations
- Add a visual indicator in the warehouse header showing the count of transit locations
- Ensure performance is maintained with the additional data