# Technical Specification for Sidebar Enhancement

## 1. Model Enhancements

### SQL View Fix (stock_current_report.py)

The current SQL view needs to be updated to properly link locations to warehouses:

```python
def init(self):
    tools.drop_view_if_exists(self._cr, self._table)
    self._cr.execute(f"""
        CREATE OR REPLACE VIEW {self._table} AS (
            SELECT
                sq.id AS id,
                sq.product_id,
                sq.location_id,
                COALESCE(sl.warehouse_id, w.id) AS warehouse_id,
                pt.categ_id AS category_id,
                pt.uom_id,
                COALESCE(sq.quantity, 0) AS quantity,
                COALESCE(sq.quantity, 0) AS free_to_use,
                COALESCE(incoming.qty, 0) AS incoming,
                COALESCE(outgoing.qty, 0) AS outgoing,
                COALESCE(pt.standard_price, 0) AS unit_cost,
                COALESCE(sq.quantity, 0) * COALESCE(pt.standard_price, 0) AS total_value,
                sl.usage AS location_usage,
                CASE 
                    WHEN sl.usage = 'internal' THEN 'Internal'
                    WHEN sl.usage = 'production' THEN 'Production'
                    WHEN sl.usage = 'inventory' THEN 'Inventory'
                    ELSE sl.usage
                END AS location_type_name
            FROM stock_quant sq
            JOIN product_product pp ON pp.id = sq.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN stock_location sl ON sl.id = sq.location_id
            LEFT JOIN stock_warehouse w ON (
                sl.id = w.lot_stock_id OR 
                sl.id = w.input_location_id OR 
                sl.id = w.output_location_id OR
                sl.id = w.pack_location_id OR
                sl.id = w.pick_location_id
            )
            LEFT JOIN (
                SELECT
                    sml.location_dest_id,
                    sml.product_id,
                    SUM(sml.quantity) AS qty
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                AND sml.location_dest_id IS NOT NULL
                GROUP BY sml.location_dest_id, sml.product_id
            ) incoming ON incoming.location_dest_id = sq.location_id AND incoming.product_id = sq.product_id
            LEFT JOIN (
                SELECT
                    sml.location_id,
                    sml.product_id,
                    SUM(sml.quantity) AS qty
                FROM stock_move_line sml
                JOIN stock_move sm ON sm.id = sml.move_id
                WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                AND sml.location_id IS NOT NULL
                GROUP BY sml.location_id, sml.product_id
            ) outgoing ON outgoing.location_id = sq.location_id AND outgoing.product_id = sq.product_id
            WHERE sl.usage IN ('internal', 'production', 'inventory')
        )
    """)
```

### New Model Fields

```python
location_usage = fields.Selection([
    ('internal', 'Internal'),
    ('production', 'Production'),
    ('inventory', 'Inventory'),
    ('supplier', 'Supplier'),
    ('customer', 'Customer'),
    ('transit', 'Transit'),
], string='Location Usage', readonly=True)

location_type_name = fields.Char(string='Location Type', readonly=True)
```

### Enhanced Methods

```python
@api.model
def get_warehouses_with_internal_locations(self):
    """Enhanced method with better performance and more data"""
    query = """
        SELECT 
            w.id,
            w.name,
            w.code,
            COUNT(DISTINCT l.id) as location_count,
            COALESCE(SUM(s.total_products), 0) as total_products,
            COALESCE(SUM(s.total_value), 0) as total_value
        FROM stock_warehouse w
        LEFT JOIN stock_location l ON l.warehouse_id = w.id AND l.usage = 'internal'
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
    self._cr.execute(query)
    warehouses = self._cr.dictfetchall()
    
    # Get locations for each warehouse
    for warehouse in warehouses:
        location_query = """
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
            WHERE l.warehouse_id = %s AND l.usage = 'internal'
            GROUP BY l.id, l.name, l.complete_name, l.usage
            ORDER BY l.name
        """
        self._cr.execute(location_query, (warehouse['id'],))
        warehouse['locations'] = self._cr.dictfetchall()
    
    return warehouses

@api.model
def get_location_hierarchy(self):
    """Get hierarchical structure of all internal locations"""
    query = """
        WITH RECURSIVE location_tree AS (
            SELECT 
                l.id,
                l.name,
                l.complete_name,
                l.location_id,
                l.warehouse_id,
                l.usage,
                0 as level,
                ARRAY[l.id] as path
            FROM stock_location l
            WHERE l.location_id IS NULL AND l.usage IN ('internal', 'production', 'inventory')
            
            UNION ALL
            
            SELECT 
                child.id,
                child.name,
                child.complete_name,
                child.location_id,
                child.warehouse_id,
                child.usage,
                lt.level + 1,
                lt.path || child.id
            FROM stock_location child
            JOIN location_tree lt ON child.location_id = lt.id
            WHERE child.usage IN ('internal', 'production', 'inventory')
        )
        SELECT 
            lt.*,
            w.name as warehouse_name,
            COUNT(DISTINCT scr.product_id) as product_count
        FROM location_tree lt
        LEFT JOIN stock_warehouse w ON w.id = lt.warehouse_id
        LEFT JOIN stock_current_report scr ON scr.location_id = lt.id
        GROUP BY lt.id, lt.name, lt.complete_name, lt.location_id, 
                 lt.warehouse_id, lt.usage, lt.level, lt.path, w.name
        ORDER BY lt.path
    """
    self._cr.execute(query)
    return self._cr.dictfetchall()
```

## 2. JavaScript Component Enhancements

### Enhanced WarehouseSidebar Component

```javascript
export class WarehouseSidebar extends Component {
    static template = "buz_stock_current_report.WarehouseSidebar";
    
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            warehouses: [],
            expandedWarehouses: new Set(),
            loading: true,
            selectedWarehouse: null,
            selectedLocation: null,
            searchTerm: '',
            showOnlyWithStock: false
        });
        
        onWillStart(async () => {
            await this.loadWarehouses();
        });
    }

    async loadWarehouses() {
        try {
            this.state.loading = true;
            const result = await this.orm.call(
                'stock.current.report',
                'get_warehouses_with_internal_locations',
                []
            );
            this.state.warehouses = result;
        } catch (error) {
            this.notification.add(
                _t("Error loading warehouses: ") + error.message,
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    get filteredWarehouses() {
        let warehouses = this.state.warehouses;
        
        if (this.state.searchTerm) {
            const term = this.state.searchTerm.toLowerCase();
            warehouses = warehouses.filter(wh => 
                wh.name.toLowerCase().includes(term) ||
                wh.code.toLowerCase().includes(term) ||
                wh.locations.some(loc => 
                    loc.name.toLowerCase().includes(term) ||
                    loc.complete_name.toLowerCase().includes(term)
                )
            );
        }
        
        if (this.state.showOnlyWithStock) {
            warehouses = warehouses.filter(wh => 
                wh.total_products > 0 || 
                wh.locations.some(loc => loc.product_count > 0)
            );
        }
        
        return warehouses;
    }

    toggleWarehouse(warehouseId) {
        if (this.state.expandedWarehouses.has(warehouseId)) {
            this.state.expandedWarehouses.delete(warehouseId);
        } else {
            this.state.expandedWarehouses.add(warehouseId);
        }
        this.render();
    }

    async onWarehouseClick(warehouse) {
        this.state.selectedWarehouse = warehouse.id;
        this.state.selectedLocation = null;
        
        const domain = [['location_id.warehouse_id', '=', warehouse.id]];
        this.updateDomain(domain);
        
        this.notification.add(
            _t("Filtered by warehouse: ") + warehouse.name,
            { type: "info" }
        );
    }

    async onLocationClick(location) {
        this.state.selectedLocation = location.id;
        this.state.selectedWarehouse = null;
        
        const domain = [['location_id', '=', location.id]];
        this.updateDomain(domain);
        
        this.notification.add(
            _t("Filtered by location: ") + location.name,
            { type: "info" }
        );
    }

    async onClearFilters() {
        this.state.selectedWarehouse = null;
        this.state.selectedLocation = null;
        this.state.searchTerm = '';
        this.state.showOnlyWithStock = false;
        this.updateDomain([]);
    }

    updateDomain(domain) {
        if (this.env.searchModel) {
            this.env.searchModel.updateSearchDomain(domain);
        }
    }

    async refreshData() {
        await this.loadWarehouses();
        this.notification.add(
            _t("Warehouse data refreshed"),
            { type: "success" }
        );
    }

    getLocationTypeIcon(usage) {
        const icons = {
            'internal': 'fa-home',
            'production': 'fa-industry',
            'inventory': 'fa-warehouse',
            'supplier': 'fa-truck',
            'customer': 'fa-store',
            'transit': 'fa-exchange-alt'
        };
        return icons[usage] || 'fa-map-marker';
    }

    getStockStatusClass(quantity) {
        if (quantity <= 0) return 'text-danger';
        if (quantity < 10) return 'text-warning';
        return 'text-success';
    }
}
```

## 3. XML Template Enhancements

### Enhanced WarehouseSidebar Template

```xml
<t t-name="buz_stock_current_report.WarehouseSidebar" owl="1">
    <div class="warehouse-sidebar">
        <div class="warehouse-sidebar-header">
            <h5 class="mb-3">
                <i class="fa fa-building me-2"/>Warehouses & Locations
            </h5>
            
            <!-- Search Box -->
            <div class="sidebar-search mb-3">
                <div class="input-group input-group-sm">
                    <input type="text" 
                           class="form-control" 
                           placeholder="Search warehouses or locations..."
                           t-model="state.searchTerm"/>
                    <button class="btn btn-outline-secondary" 
                            type="button" 
                            t-on-click="refreshData"
                            title="Refresh">
                        <i class="fa fa-refresh"/>
                    </button>
                </div>
            </div>
            
            <!-- Quick Filters -->
            <div class="sidebar-filters mb-3">
                <div class="form-check">
                    <input class="form-check-input" 
                           type="checkbox" 
                           id="showOnlyWithStock"
                           t-model="state.showOnlyWithStock"/>
                    <label class="form-check-label" for="showOnlyWithStock">
                        Show only with stock
                    </label>
                </div>
            </div>
            
            <!-- Clear Filters Button -->
            <button class="btn btn-sm btn-outline-secondary w-100 mb-3"
                    t-on-click="onClearFilters">
                <i class="fa fa-times me-1"/>Clear All Filters
            </button>
        </div>
        
        <!-- Loading State -->
        <div t-if="state.loading" class="text-center p-4">
            <div class="spinner-border spinner-border-sm" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <div class="mt-2">Loading warehouses...</div>
        </div>
        
        <!-- Warehouse List -->
        <div t-else="" class="warehouse-list">
            <div t-if="filteredWarehouses.length === 0" class="text-center p-3 text-muted">
                <i class="fa fa-search fa-2x mb-2"/>
                <div>No warehouses found</div>
            </div>
            
            <div t-foreach="filteredWarehouses" t-as="warehouse" t-key="warehouse.id"
                 class="warehouse-item mb-3">
                
                <!-- Warehouse Header -->
                <div class="warehouse-header card">
                    <div class="card-body p-2">
                        <div class="d-flex justify-content-between align-items-center"
                             t-att-class="isWarehouseSelected(warehouse.id) ? 'text-primary' : ''"
                             t-on-click="() => this.onWarehouseClick(warehouse)">
                            <div class="d-flex align-items-center flex-grow-1">
                                <i t-att-class="isWarehouseExpanded(warehouse.id) ? 'fa fa-chevron-down me-2' : 'fa fa-chevron-right me-2'"
                                   class="cursor-pointer text-muted"
                                   t-on-click.stop="() => this.toggleWarehouse(warehouse.id)"/>
                                <div>
                                    <strong class="d-block">
                                        <i class="fa fa-building me-1"/>
                                        <t t-esc="warehouse.name"/>
                                    </strong>
                                    <small class="text-muted" t-if="warehouse.code">
                                        Code: <t t-esc="warehouse.code"/>
                                    </small>
                                </div>
                            </div>
                            <div class="text-end">
                                <div class="badge bg-primary rounded-pill">
                                    <t t-esc="warehouse.location_count"/> locations
                                </div>
                                <div class="small text-muted mt-1">
                                    <t t-esc="warehouse.total_products"/> products
                                </div>
                            </div>
                        </div>
                        
                        <!-- Warehouse Summary -->
                        <div t-if="warehouse.total_value > 0" class="mt-2">
                            <small class="text-muted">
                                Total Value: 
                                <strong t-esc="formatMonetary(warehouse.total_value)"/>
                            </small>
                        </div>
                    </div>
                </div>
                
                <!-- Locations List -->
                <div t-if="isWarehouseExpanded(warehouse.id)" class="location-list ms-3 mt-2">
                    <div t-if="warehouse.locations.length === 0" class="text-center p-3 text-muted bg-light rounded">
                        <small>No internal locations found</small>
                    </div>
                    
                    <div t-foreach="warehouse.locations" t-as="location" t-key="location.id"
                         class="location-item mb-2">
                        <div class="card border-0 bg-light">
                            <div class="card-body p-2">
                                <div class="d-flex justify-content-between align-items-center"
                                     t-att-class="isLocationSelected(location.id) ? 'bg-success text-white rounded' : ''"
                                     t-on-click="() => this.onLocationClick(location)">
                                    <div class="d-flex align-items-center flex-grow-1">
                                        <i t-att-class="getLocationTypeIcon(location.usage) + ' me-2 text-muted'"/>
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
                                        <div class="badge bg-info rounded-pill">
                                            <t t-esc="location.product_count"/> products
                                        </div>
                                        <div class="small mt-1">
                                            <span t-att-class="getStockStatusClass(location.total_quantity)">
                                                Qty: <t t-esc="formatQuantity(location.total_quantity)"/>
                                            </span>
                                        </div>
                                    </div>
                                </div>
                                
                                <!-- Location Value -->
                                <div t-if="location.total_value > 0" class="mt-2">
                                    <small class="text-muted">
                                        Value: <strong t-esc="formatMonetary(location.total_value)"/>
                                    </small>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Summary Section -->
        <div class="warehouse-summary mt-3 p-3 bg-light rounded">
            <h6 class="mb-2">Summary</h6>
            <div class="row g-2">
                <div class="col-6">
                    <small class="text-muted d-block">Warehouses</small>
                    <strong t-esc="state.warehouses.length"/>
                </div>
                <div class="col-6">
                    <small class="text-muted d-block">Locations</small>
                    <strong t-esc="state.warehouses.reduce((sum, wh) => sum + wh.location_count, 0)"/>
                </div>
                <div class="col-6">
                    <small class="text-muted d-block">Total Products</small>
                    <strong t-esc="state.warehouses.reduce((sum, wh) => sum + wh.total_products, 0)"/>
                </div>
                <div class="col-6">
                    <small class="text-muted d-block">Total Value</small>
                    <strong t-esc="formatMonetary(state.warehouses.reduce((sum, wh) => sum + wh.total_value, 0))"/>
                </div>
            </div>
        </div>
    </div>
</t>
```

## 4. CSS Styling Enhancements

### Enhanced CSS Classes

```css
/* Enhanced Warehouse Sidebar */
.warehouse-sidebar {
    width: 320px;
    min-height: 500px;
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    border: 1px solid #dee2e6;
    border-radius: 12px;
    padding: 1rem;
    margin-right: 1rem;
    overflow-y: auto;
    max-height: calc(100vh - 150px);
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.warehouse-sidebar-header {
    border-bottom: 2px solid #007bff;
    padding-bottom: 1rem;
    margin-bottom: 1rem;
    background: white;
    margin: -1rem -1rem 1rem -1rem;
    padding: 1rem;
    border-radius: 12px 12px 0 0;
}

/* Search Box Styling */
.sidebar-search .input-group {
    border-radius: 20px;
    overflow: hidden;
}

.sidebar-search input {
    border: 1px solid #e0e0e0;
    border-radius: 20px 0 0 20px;
    padding-left: 1rem;
}

.sidebar-search button {
    border-radius: 0 20px 20px 0;
    border-left: none;
}

/* Warehouse Card Styling */
.warehouse-header {
    transition: all 0.3s ease;
    cursor: pointer;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
}

.warehouse-header:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.warehouse-header.text-primary {
    background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
    border-left: 4px solid #007bff;
}

/* Location Item Styling */
.location-item .card {
    transition: all 0.2s ease;
    border-left: 3px solid transparent;
}

.location-item .card:hover {
    transform: translateX(4px);
    border-left-color: #28a745;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.location-item .bg-success {
    background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important;
    border-left-color: #28a745 !important;
}

/* Badge Enhancements */
.warehouse-sidebar .badge {
    font-size: 0.7rem;
    padding: 0.35rem 0.65rem;
    border-radius: 12px;
    font-weight: 500;
}

/* Icon Styling */
.warehouse-sidebar .fa-building {
    color: #007bff;
}

.warehouse-sidebar .fa-home {
    color: #28a745;
}

.warehouse-sidebar .fa-industry {
    color: #ffc107;
}

.warehouse-sidebar .fa-warehouse {
    color: #6f42c1;
}

/* Animation for expand/collapse */
.location-list {
    overflow: hidden;
    transition: all 0.3s ease-in-out;
    animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
    from {
        opacity: 0;
        max-height: 0;
        transform: translateY(-10px);
    }
    to {
        opacity: 1;
        max-height: 1000px;
        transform: translateY(0);
    }
}

/* Summary Section */
.warehouse-summary {
    background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
    border: 1px solid #e9ecef;
    border-radius: 8px;
    margin-top: 1rem;
}

/* Loading State */
.spinner-border-sm {
    width: 1rem;
    height: 1rem;
}

/* Responsive Design */
@media (max-width: 1200px) {
    .warehouse-sidebar {
        width: 300px;
        margin-right: 0.5rem;
    }
}

@media (max-width: 992px) {
    .warehouse-sidebar {
        width: 100%;
        max-height: 400px;
        margin-bottom: 1rem;
        margin-right: 0;
    }
    
    .o_content {
        flex-direction: column;
    }
}

/* Dark mode support */
@media (prefers-color-scheme: dark) {
    .warehouse-sidebar {
        background: linear-gradient(135deg, #2d3748 0%, #1a202c 100%);
        color: #e2e8f0;
    }
    
    .warehouse-sidebar-header {
        background: #1a202c;
        color: #e2e8f0;
    }
    
    .location-item .card {
        background: #2d3748;
        color: #e2e8f0;
    }
}
```

## 5. View Integration

### Enhanced Controller Integration

```javascript
// Enhanced List Controller with Sidebar
export class StockListControllerWithSidebar extends ListController {
    setup() {
        super.setup();
        this.sidebarState = useState({
            visible: true,
            warehouseFilter: null,
            locationFilter: null
        });
    }

    get rendererProps() {
        const props = super.rendererProps;
        props.sidebarState = this.sidebarState;
        return props;
    }
}

// Enhanced Kanban Controller with Sidebar  
export class StockKanbanControllerWithSidebar extends KanbanController {
    setup() {
        super.setup();
        this.sidebarState = useState({
            visible: true,
            warehouseFilter: null,
            locationFilter: null
        });
    }

    get rendererProps() {
        const props = super.rendererProps;
        props.sidebarState = this.sidebarState;
        return props;
    }
}
```

This technical specification provides all the necessary code changes to enhance the sidebar functionality for displaying warehouse names and internal locations in a more user-friendly and feature-rich manner.