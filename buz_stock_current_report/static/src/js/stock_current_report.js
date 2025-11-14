/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";
import { ListRenderer } from "@web/views/list/list_renderer";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { Component, useState, onWillStart, onMounted, onPatched } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

// Custom Kanban Record to handle clicks without navigation
export class StockKanbanRecord extends KanbanRecord {
    /**
     * Override global click to prevent form opening when clicking on checkboxes or buttons
     * This allows multi-product selection without navigation
     */
    onGlobalClick(ev) {
        // Check if click is on interactive elements that shouldn't trigger navigation
        const isInteractiveElement = ev.target.closest(
            '.product-selection-checkbox, .transfer-product-btn, button, a, input, select, textarea'
        );
        
        if (isInteractiveElement) {
            // Don't open record form, let the element handle the click
            return;
        }
        
        // For all other clicks, call the parent method to open record form
        super.onGlobalClick(ev);
    }
}

// Product Selection Manager for Transfer Feature
export class ProductSelectionManager {
    constructor() {
        this.selectedProducts = new Map();
        this.callbacks = new Set();
    }

    toggleProductSelection(productData) {
        const key = `${productData.productId}_${productData.locationId}`;
        if (this.selectedProducts.has(key)) {
            this.selectedProducts.delete(key);
        } else {
            this.selectedProducts.set(key, productData);
        }
        this.notifyCallbacks();
    }

    isProductSelected(productId, locationId) {
        const key = `${productId}_${locationId}`;
        return this.selectedProducts.has(key);
    }

    getSelectedProducts() {
        return Array.from(this.selectedProducts.values());
    }

    getSelectedCount() {
        return this.selectedProducts.size;
    }

    clearSelection() {
        this.selectedProducts.clear();
        this.notifyCallbacks();
    }

    onSelectionChange(callback) {
        this.callbacks.add(callback);
    }

    notifyCallbacks() {
        this.callbacks.forEach(callback => callback());
    }
}

export class StockListController extends ListController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.selectionManager = new ProductSelectionManager();
        
        // Add transfer button to toolbar
        this.renderTransferButton();
    }

    renderTransferButton() {
        // transfer feature disabled
        return;
    }

    async onTransferSelected() {
        const selectedProducts = this.selectionManager.getSelectedProducts();
        if (selectedProducts.length === 0) {
            this.notification.add("Please select at least one product", { type: "warning" });
            return;
        }
        
        await this.openTransferWizard(selectedProducts);
    }

    async openTransferWizard(selectedProducts) {
        console.log("StockListController.openTransferWizard", selectedProducts);
        try {
            const wizardId = await this.orm.create(
                'stock.current.transfer.wizard',
                {
                    line_ids: selectedProducts.map(prod => [0, 0, {
                        product_id: prod.productId,
                        source_location_id: prod.locationId,
                        available_quantity: prod.quantity,
                        quantity_to_transfer: prod.quantity,
                        uom_id: prod.uomId,
                    }]),
                    source_location_id: selectedProducts.length > 0 && selectedProducts.every(p => p.locationId === selectedProducts[0].locationId) ? selectedProducts[0].locationId : null,
                }
            );
            return this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'stock.current.transfer.wizard',
                res_id: wizardId,
                view_mode: 'form',
                target: 'new',
                views: [[false, 'form']],
            });
        } catch (err) {
            console.error("Error:", err);
            this.notification.add("Error: " + err.message, { type: "danger" });
        }
    }

    async onTransferSingleProduct(productData) {
        await this.openTransferWizard([productData]);
    }
}

export class StockKanbanController extends KanbanController {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.selectionManager = new ProductSelectionManager();
        
        // Add transfer button to toolbar
        onMounted(() => {
            this.renderTransferButton();
            this.setupProductSelection();
        });
        
        // Re-setup listeners when kanban is patched
        onPatched(() => {
            this.setupProductSelection();
        });
    }

    renderTransferButton() {
        // transfer feature disabled
        return;
    }

    setupProductSelection() {
        // Attach checkbox listeners
        const checkboxes = document.querySelectorAll('.product-selection-checkbox');
        checkboxes.forEach(checkbox => {
            // Skip if already has listener
            if (checkbox._hasStockListener) return;
            checkbox._hasStockListener = true;
            
            checkbox.addEventListener('change', (e) => {
                try {
                    const productId = parseInt(e.target.dataset.productId);
                    const locationId = parseInt(e.target.dataset.locationId);
                    const quantity = parseFloat(e.target.dataset.quantity);
                    const uomId = parseInt(e.target.dataset.uomId);
                    
                    if (!productId || !locationId) {
                        console.warn("Missing product or location id", {
                            productId,
                            locationId,
                            dataset: e.target.dataset
                        });
                        return;
                    }
                    
                    const productData = {
                        productId: productId,
                        locationId: locationId,
                        quantity: quantity || 0,
                        uomId: uomId || 0,
                        productName: e.target.dataset.productName || 'Product',
                        locationName: e.target.dataset.locationName || 'Location'
                    };
                    
                    console.log("Product selected:", productData);
                    
                    this.selectionManager.toggleProductSelection(productData);
                    
                    // Update card visual state
                    const card = e.target.closest('.oe_kanban_card, .o_kanban_record');
                    if (card) {
                        const isSelected = this.selectionManager.isProductSelected(
                            productData.productId, 
                            productData.locationId
                        );
                        card.classList.toggle('kanban-card-selected', isSelected);
                    }
                } catch (err) {
                    console.error("Error in checkbox change handler:", err);
                }
            }, { once: false });
        });
    }

    async onTransferSelected() {
        const selectedProducts = this.selectionManager.getSelectedProducts();
        if (selectedProducts.length === 0) {
            this.notification.add("Please select at least one product", { type: "warning" });
            return;
        }
        
        await this.openTransferWizard(selectedProducts);
    }

    async openTransferWizard(selectedProducts) {
        console.log("StockKanbanController.openTransferWizard", selectedProducts);
        try {
            const wizardId = await this.orm.create(
                'stock.current.transfer.wizard',
                {
                    line_ids: selectedProducts.map(prod => [0, 0, {
                        product_id: prod.productId,
                        source_location_id: prod.locationId,
                        available_quantity: prod.quantity,
                        quantity_to_transfer: prod.quantity,
                        uom_id: prod.uomId,
                    }]),
                    source_location_id: selectedProducts.length > 0 && selectedProducts.every(p => p.locationId === selectedProducts[0].locationId) ? selectedProducts[0].locationId : null,
                }
            );
            return this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'stock.current.transfer.wizard',
                res_id: wizardId,
                view_mode: 'form',
                target: 'new',
                views: [[false, 'form']],
            });
        } catch (err) {
            console.error("Error:", err);
            this.notification.add("Error: " + err.message, { type: "danger" });
        }
    }

    async onTransferSingleProduct(productData) {
        await this.openTransferWizard([productData]);
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
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.selectionManager = new ProductSelectionManager();
        this.sidebarState = useState({
            showSidebar: true,
        });
        
        // Add transfer button to toolbar
        this.renderTransferButton();
    }

    renderTransferButton() {
        // transfer feature disabled
        return;
    }

    async onTransferSelected() {
        const selectedProducts = this.selectionManager.getSelectedProducts();
        if (selectedProducts.length === 0) {
            this.notification.add("Please select at least one product", { type: "warning" });
            return;
        }
        
        await this.openTransferWizard(selectedProducts);
    }

    async openTransferWizard(selectedProducts) {
        console.log("StockListWithSidebarController.openTransferWizard", selectedProducts);
        try {
            const wizardId = await this.orm.create(
                'stock.current.transfer.wizard',
                {
                    line_ids: selectedProducts.map(prod => [0, 0, {
                        product_id: prod.productId,
                        source_location_id: prod.locationId,
                        available_quantity: prod.quantity,
                        quantity_to_transfer: prod.quantity,
                        uom_id: prod.uomId,
                    }]),
                    source_location_id: selectedProducts.length > 0 && selectedProducts.every(p => p.locationId === selectedProducts[0].locationId) ? selectedProducts[0].locationId : null,
                }
            );
            return this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'stock.current.transfer.wizard',
                res_id: wizardId,
                view_mode: 'form',
                target: 'new',
                views: [[false, 'form']],
            });
        } catch (err) {
            console.error("Error:", err);
            this.notification.add("Error: " + err.message, { type: "danger" });
        }
    }

    async onTransferSingleProduct(productData) {
        await this.openTransferWizard([productData]);
    }
}

export class StockKanbanWithSidebarController extends KanbanController {
    static components = {
        ...KanbanController.components,
        WarehouseSidebar,
    };

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.selectionManager = new ProductSelectionManager();
        this.sidebarState = useState({
            showSidebar: true,
        });
        
        // Setup product selection handlers
        this.setupProductSelection();
        
        // Add transfer button to toolbar after mount
        onMounted(() => {
            this.renderTransferButton();
        });
    }

    renderTransferButton() {
        // transfer feature disabled
        return;
    }

    setupProductSelection() {
        const attachListeners = () => {
            // Add event listeners for product selection checkboxes
            const checkboxes = document.querySelectorAll('.product-selection-checkbox');
            checkboxes.forEach(checkbox => {
                // Remove old listener if exists
                if (checkbox._stockChangeHandler) {
                    checkbox.removeEventListener('change', checkbox._stockChangeHandler);
                }
                
                checkbox._stockChangeHandler = (e) => {
                    const productData = {
                        productId: parseInt(e.target.dataset.productId),
                        locationId: parseInt(e.target.dataset.locationId),
                        quantity: parseFloat(e.target.dataset.quantity),
                        uomId: parseInt(e.target.dataset.uomId),
                        productName: e.target.dataset.productName,
                        locationName: e.target.dataset.locationName
                    };
                    this.selectionManager.toggleProductSelection(productData);
                    
                    // Update visual selection state
                    const card = e.target.closest('.oe_kanban_card');
                    if (card) {
                        card.classList.toggle('kanban-card-selected', this.selectionManager.isProductSelected(
                            productData.productId, productData.locationId
                        ));
                    }
                };
                checkbox.addEventListener('change', checkbox._stockChangeHandler);
            });

            // Add event listeners for individual transfer buttons
            const transferButtons = document.querySelectorAll('.transfer-product-btn');
            transferButtons.forEach(button => {
                // Remove old listener if exists
                if (button._stockClickHandler) {
                    button.removeEventListener('click', button._stockClickHandler);
                }
                
                button._stockClickHandler = async (e) => {
                    e.stopPropagation();
                    // Use closest to get the button element even if icon is clicked
                    const btn = e.target.closest('.transfer-product-btn');
                    if (!btn) return;
                    
                    const productData = {
                        productId: parseInt(btn.dataset.productId),
                        locationId: parseInt(btn.dataset.locationId),
                        quantity: parseFloat(btn.dataset.quantity),
                        uomId: parseInt(btn.dataset.uomId),
                        productName: btn.dataset.productName,
                        locationName: btn.dataset.locationName
                    };
                    await this.onTransferSingleProduct(productData);
                };
                button.addEventListener('click', button._stockClickHandler);
            });
        };
        
        onMounted(() => {
            attachListeners();
        });
        
        // Reattach listeners after kanban refresh/filter
        onPatched(() => {
            attachListeners();
        });
    }

    async onTransferSelected() {
        const selectedProducts = this.selectionManager.getSelectedProducts();
        if (selectedProducts.length === 0) {
            this.notification.add("Please select at least one product", { type: "warning" });
            return;
        }
        
        await this.openTransferWizard(selectedProducts);
    }

    async openTransferWizard(selectedProducts) {
        console.log("StockKanbanWithSidebarController.openTransferWizard", selectedProducts);
        try {
            const wizardId = await this.orm.create(
                'stock.current.transfer.wizard',
                {
                    line_ids: selectedProducts.map(prod => [0, 0, {
                        product_id: prod.productId,
                        source_location_id: prod.locationId,
                        available_quantity: prod.quantity,
                        quantity_to_transfer: prod.quantity,
                        uom_id: prod.uomId,
                    }]),
                    source_location_id: selectedProducts.length > 0 && selectedProducts.every(p => p.locationId === selectedProducts[0].locationId) ? selectedProducts[0].locationId : null,
                }
            );
            return this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'stock.current.transfer.wizard',
                res_id: wizardId,
                view_mode: 'form',
                target: 'new',
                views: [[false, 'form']],
            });
        } catch (err) {
            console.error("Error:", err);
            this.notification.add("Error: " + err.message, { type: "danger" });
        }
    }

    async onTransferSingleProduct(productData) {
        await this.openTransferWizard([productData]);
    }
}

export const stockListView = {
    ...listView,
    Controller: StockListController,
};

export const stockKanbanView = {
    ...kanbanView,
    Controller: StockKanbanController,
    Record: StockKanbanRecord,
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
    Record: StockKanbanRecord,
};

registry.category("views").add("stock_current_list", stockListView);
registry.category("views").add("stock_current_kanban", stockKanbanView);
registry.category("views").add("stock_current_list_sidebar", stockListWithSidebarView);
registry.category("views").add("stock_current_kanban_sidebar", stockKanbanWithSidebarView);

// Global setup for stock report transfer functionality
document.addEventListener('DOMContentLoaded', () => {
    setupStockTransferUI();
});

// Setup function for transfer UI
function setupStockTransferUI() {
    // transfer feature disabled
    return;
}

// Initialize globally when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    setupStockTransferUI();
    setupTransferButtonHandlers();
});

// Setup Transfer button handlers for kanban cards
function setupTransferButtonHandlers() {
    // transfer handlers disabled
    return;
}

// Also try initialization after Odoo has loaded
setTimeout(setupStockTransferUI, 1000);
setTimeout(setupStockTransferUI, 3000);
setTimeout(setupTransferButtonHandlers, 1000);
setTimeout(setupTransferButtonHandlers, 3000);
