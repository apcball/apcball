/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController, ListRenderer } from "@web/views/list/list_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController, KanbanRenderer } from "@web/views/kanban/kanban_controller";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class StockListController extends ListController {
    setup() {
        super.setup();
    }
}

export class StockKanbanController extends KanbanController {
    setup() {
        super.setup();
    }
}

// Define WarehouseSidebar component first
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
                'get_warehouses_with_locations',
                [],
                {}
            );
            this.state.warehouses = result || [];
        } catch (error) {
            console.error('Error loading warehouses:', error);
            this.notification.add(
                _t("Error loading warehouses: ") + (error.message || error.toString()),
                { type: "danger" }
            );
            this.state.warehouses = [];
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
                (wh.code && wh.code.toLowerCase().includes(term)) ||
                (wh.internal_locations && wh.internal_locations.some(loc =>
                    loc.name.toLowerCase().includes(term) ||
                    loc.complete_name.toLowerCase().includes(term)
                )) ||
                (wh.transit_locations && wh.transit_locations.some(loc =>
                    loc.name.toLowerCase().includes(term) ||
                    loc.complete_name.toLowerCase().includes(term)
                ))
            );
        }
        
        if (this.state.showOnlyWithStock) {
            warehouses = warehouses.filter(wh =>
                wh.total_products > 0 ||
                (wh.internal_locations && wh.internal_locations.some(loc => loc.product_count > 0)) ||
                (wh.transit_locations && wh.transit_locations.some(loc => loc.product_count > 0))
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
    }

    onWarehouseClick(warehouse) {
        this.state.selectedWarehouse = warehouse.id;
        this.state.selectedLocation = null;
        
        const domain = [['location_id.warehouse_id', '=', warehouse.id]];
        this.updateDomain(domain);
        
        this.notification.add(
            _t("Filtered by warehouse: ") + warehouse.name,
            { type: "info" }
        );
    }

    onLocationClick(location) {
        this.state.selectedLocation = location.id;
        this.state.selectedWarehouse = null;
        
        const domain = [['location_id', '=', location.id]];
        this.updateDomain(domain);
        
        this.notification.add(
            _t("Filtered by location: ") + location.name,
            { type: "info" }
        );
    }

    onClearFilters() {
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

    formatMonetary(amount) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(amount || 0);
    }

    formatQuantity(quantity) {
        return new Intl.NumberFormat().format(quantity || 0);
    }

    isWarehouseExpanded(warehouseId) {
        return this.state.expandedWarehouses.has(warehouseId);
    }

    isWarehouseSelected(warehouseId) {
        return this.state.selectedWarehouse === warehouseId;
    }

    isLocationSelected(locationId) {
        return this.state.selectedLocation === locationId;
    }
}

// Controller with Sidebar - defined after WarehouseSidebar
export class StockListWithSidebarController extends ListController {
    static components = {
        ...ListController.components,
        WarehouseSidebar,
    };

    setup() {
        super.setup();
        this.sidebarState = useState({
            showSidebar: true,
        });
    }
}

export class StockKanbanWithSidebarController extends KanbanController {
    static components = {
        ...KanbanController.components,
        WarehouseSidebar,
    };

    setup() {
        super.setup();
        this.sidebarState = useState({
            showSidebar: true,
        });
    }
}

export const stockListView = {
    ...listView,
    Controller: StockListController,
};

export const stockKanbanView = {
    ...kanbanView,
    Controller: StockKanbanController,
};

// Views with Sidebar
export const stockListWithSidebarView = {
    ...listView,
    Controller: StockListWithSidebarController,
    Renderer: ListRenderer,
};

export const stockKanbanWithSidebarView = {
    ...kanbanView,
    Controller: StockKanbanWithSidebarController,
    Renderer: KanbanRenderer,
};

registry.category("views").add("stock_current_list", stockListView);
registry.category("views").add("stock_current_kanban", stockKanbanView);
registry.category("views").add("stock_current_list_sidebar", stockListWithSidebarView);
registry.category("views").add("stock_current_kanban_sidebar", stockKanbanWithSidebarView);
