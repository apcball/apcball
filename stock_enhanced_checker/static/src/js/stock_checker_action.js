/** @odoo-module **/
/**
 * File: static/src/js/stock_checker_action.js
 * Purpose: Main OWL component for the Stock Enhanced Checker client action.
 *          Handles all state management: warehouse/location selection,
 *          product loading, search/filter, multi-select, and quotation creation.
 */

import { Component, useState, onWillStart, onWillUpdateProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { StockCheckerTable } from "./stock_checker_table";
import { STOCK_FILTERS, debounce, formatQty } from "./stock_checker_filters";

/**
 * StockCheckerAction
 *
 * Root OWL component registered as the "stock_enhanced_checker.StockCheckerAction"
 * client action tag. Manages the complete stock checker dashboard lifecycle.
 */
class StockCheckerAction extends Component {
    static template = "stock_enhanced_checker.StockCheckerAction";
    static components = { StockCheckerTable };

    // ── Lifecycle ──────────────────────────────────────────────────────────

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        /** @type {string[]} */
        this.filters = STOCK_FILTERS;

        /** @type {ReturnType<typeof useState>} */
        this.state = useState({
            // Warehouse & location
            warehouses: [],
            locations: [],
            selectedWarehouseId: false,
            selectedLocationId: false,

            // Product data
            products: [],
            total: 0,
            offset: 0,
            limit: 50,

            // UI
            loading: false,
            creating: false,
            search: '',
            filterType: 'all',
            toast: null,

            // Selection
            selectedIds: [],
            qtys: {},      // { productId: qty }
            prices: {},    // { productId: price }

            // Partner
            partnerCode: '',
            partnerName: '',
            selectedPartnerId: false,
            partnerResults: [],
        });

        /** Debounced partner code search */
        this._debouncedPartnerSearch = debounce(this._searchPartner.bind(this), 300);
        this._debouncedSearch = null;

        onWillStart(async () => {
            await this._init();
        });
    }

    // ── Init ───────────────────────────────────────────────────────────────

    /**
     * Initialise the component: load warehouses and restore user preferences.
     */
    async _init() {
        this.state.loading = true;
        try {
            // Load warehouses and user prefs in parallel
            const [warehouses, prefs] = await Promise.all([
                this.orm.call('stock.checker.helper', 'get_warehouses', []),
                this.orm.call('stock.checker.helper', 'get_user_preferences', []),
            ]);

            this.state.warehouses = warehouses;

            // Restore or default warehouse
            let warehouseId = prefs.warehouse_id;
            if (!warehouseId && warehouses.length) {
                warehouseId = warehouses[0].id;
            }

            if (warehouseId) {
                this.state.selectedWarehouseId = warehouseId;
                await this._loadLocations(warehouseId);

                // Restore or default location
                let locationId = prefs.location_id;
                if (!locationId && this.state.locations.length) {
                    locationId = this.state.locations[0].id;
                }

                if (locationId) {
                    this.state.selectedLocationId = locationId;
                    await this._loadStockData(true);
                }
            }
        } finally {
            this.state.loading = false;
        }
    }

    // ── Data Loaders ───────────────────────────────────────────────────────

    /**
     * Load internal locations for a given warehouse.
     * @param {number} warehouseId
     */
    async _loadLocations(warehouseId) {
        const locs = await this.orm.call(
            'stock.checker.helper', 'get_locations', [], { warehouse_id: warehouseId }
        );
        this.state.locations = locs;
    }

    /**
     * Load (or reload) stock data for the current location/filter/search.
     * @param {boolean} reset - If true, reset offset and product list
     */
    async _loadStockData(reset = false) {
        if (!this.state.selectedLocationId) return;

        if (reset) {
            this.state.offset = 0;
            this.state.products = [];
        }

        this.state.loading = true;
        try {
            const result = await this.orm.call(
                'stock.checker.helper', 'get_stock_data', [],
                {
                    location_id: this.state.selectedLocationId,
                    search: this.state.search,
                    filter_type: this.state.filterType,
                    offset: this.state.offset,
                    limit: this.state.limit,
                }
            );

            if (reset) {
                this.state.products = result.products;
            } else {
                this.state.products = [...this.state.products, ...result.products];
            }
            this.state.total = result.total;
        } catch (err) {
            this._showToast('error', _t('Error'), _t('Failed to load stock data.'));
            console.error('[StockChecker] get_stock_data error:', err);
        } finally {
            this.state.loading = false;
        }
    }

    // ── Public methods (bound to template events) ──────────────────────────

    /**
     * Expose public loadStockData for refresh button.
     */
    async loadStockData() {
        await this._loadStockData(true);
    }

    /**
     * Handle warehouse dropdown change.
     * @param {Event} ev
     */
    async onWarehouseChange(ev) {
        const warehouseId = parseInt(ev.target.value) || false;
        this.state.selectedWarehouseId = warehouseId;
        this.state.selectedLocationId = false;
        this.state.products = [];
        this.state.total = 0;

        if (warehouseId) {
            await this._loadLocations(warehouseId);
            // Auto-select the first location (warehouse default stock)
            if (this.state.locations.length) {
                this.state.selectedLocationId = this.state.locations[0].id;
                await this._loadStockData(true);
                this._savePreferences();
            }
        } else {
            this.state.locations = [];
        }
    }

    /**
     * Handle location dropdown change.
     * @param {Event} ev
     */
    async onLocationChange(ev) {
        const locationId = parseInt(ev.target.value) || false;
        this.state.selectedLocationId = locationId;
        this.state.products = [];
        this.state.selectedIds = [];
        this.state.qtys = {};
        this.state.prices = {};

        if (locationId) {
            await this._loadStockData(true);
            this._savePreferences();
        }
    }

    // ── Partner Search ───────────────────────────────────────────────────────

    /**
     * Handle partner code input — update state and trigger debounced RPC search.
     * @param {InputEvent} ev
     */
    onPartnerCodeInput(ev) {
        this.state.partnerCode = ev.target.value;
        this.state.selectedPartnerId = false;
        if (!ev.target.value.trim()) {
            this.state.partnerResults = [];
            return;
        }
        this._debouncedPartnerSearch();
    }

    /**
     * Close the partner dropdown on Escape key.
     * @param {KeyboardEvent} ev
     */
    onPartnerCodeKeydown(ev) {
        if (ev.key === 'Escape') {
            this.state.partnerResults = [];
        }
    }

    /**
     * Execute partner search RPC (called after debounce delay).
     */
    async _searchPartner() {
        const q = this.state.partnerCode;
        if (!q || !q.trim()) {
            this.state.partnerResults = [];
            return;
        }
        try {
            const results = await this.orm.call(
                'stock.checker.helper', 'search_partner', [],
                { query: q, limit: 8 }
            );
            this.state.partnerResults = results;
        } catch (err) {
            console.error('[StockChecker] search_partner error:', err);
        }
    }

    /**
     * Select a partner from the autocomplete dropdown.
     * @param {{ id: number, name: string, ref: string, display: string }} partner
     */
    onSelectPartner(partner) {
        this.state.selectedPartnerId = partner.id;
        this.state.partnerCode = partner.ref || partner.display;
        this.state.partnerName = partner.name;
        this.state.partnerResults = [];
    }

    /**
     * Handle customer name input — clears selected partner since user may be
     * typing a new (non-existing) customer name.
     * @param {InputEvent} ev
     */
    onPartnerNameInput(ev) {
        this.state.partnerName = ev.target.value;
        this.state.selectedPartnerId = false;
    }

    /**
     * Handle search input typing — update local state only, no RPC.
     * The actual search fires when the user presses Enter.
     * @param {InputEvent} ev
     */
    onSearchType(ev) {
        this.state.search = ev.target.value;
    }

    /**
     * Handle search keydown — trigger load only when Enter is pressed.
     * @param {KeyboardEvent} ev
     */
    async onSearchKeydown(ev) {
        if (ev.key === 'Enter') {
            await this._loadStockData(true);
        }
    }

    /**
     * Handle filter pill click.
     * @param {string} filterKey
     */
    async onFilterChange(filterKey) {
        this.state.filterType = filterKey;
        await this._loadStockData(true);
    }

    /**
     * Load the next page of products.
     */
    async loadMore() {
        this.state.offset += this.state.limit;
        await this._loadStockData(false);
    }

    // ── Selection ──────────────────────────────────────────────────────────

    /**
     * Toggle all products' selection state.
     */
    onToggleAll() {
        if (this.allSelected) {
            this.state.selectedIds = [];
        } else {
            const newIds = [...this.state.selectedIds];
            const newQtys = { ...this.state.qtys };
            const newPrices = { ...this.state.prices };

            for (const p of this.state.products) {
                if (!newIds.includes(p.id)) {
                    newIds.push(p.id);
                    // Auto-fill qty with 1 as default
                    newQtys[p.id] = 1;
                    newPrices[p.id] = p.list_price;
                }
            }
            this.state.selectedIds = newIds;
            this.state.qtys = newQtys;
            this.state.prices = newPrices;
        }
    }

    /**
     * Toggle individual product row selection.
     * @param {number} productId
     */
    onToggleRow(productId) {
        const idx = this.state.selectedIds.indexOf(productId);
        if (idx >= 0) {
            this.state.selectedIds = this.state.selectedIds.filter(id => id !== productId);
        } else {
            const product = this.state.products.find(p => p.id === productId);
            this.state.selectedIds = [...this.state.selectedIds, productId];
            // Auto-fill qty with 1 as default if not yet set
            if (this.state.qtys[productId] === undefined && product) {
                this.state.qtys = {
                    ...this.state.qtys,
                    [productId]: 1,
                };
            }
            if (this.state.prices[productId] === undefined && product) {
                this.state.prices = {
                    ...this.state.prices,
                    [productId]: product.list_price,
                };
            }
        }
    }

    /**
     * Update the qty to quote for a product.
     * @param {number} productId
     * @param {number} qty
     */
    onQtyChange(productId, qty) {
        this.state.qtys = { ...this.state.qtys, [productId]: qty };
    }

    /**
     * Update the unit price for a product.
     * @param {number} productId
     * @param {number} price
     */
    onPriceChange(productId, price) {
        this.state.prices = { ...this.state.prices, [productId]: price };
    }

    /**
     * Clear all selections.
     */
    clearSelection() {
        this.state.selectedIds = [];
    }

    // ── Computed ───────────────────────────────────────────────────────────

    /**
     * Whether all currently displayed products are selected.
     * @returns {boolean}
     */
    get allSelected() {
        return (
            this.state.products.length > 0 &&
            this.state.products.every(p => this.state.selectedIds.includes(p.id))
        );
    }

    /**
     * Compute summary statistics from the current product list.
     * @returns {{ inStock: number, outOfStock: number, lowStock: number, withIncoming: number }}
     */
    get stats() {
        const products = this.state.products;
        const threshold = products[0]?.low_stock_threshold ?? 5;
        return {
            inStock:     products.filter(p => p.actual_available > threshold).length,
            lowStock:    products.filter(p => p.actual_available > 0 && p.actual_available <= threshold).length,
            outOfStock:  products.filter(p => p.actual_available <= 0).length,
            withIncoming:products.filter(p => p.incoming_qty > 0).length,
        };
    }

    // ── Quotation Creation ─────────────────────────────────────────────────

    /**
     * Create a sale.order quotation from the selected products.
     * Opens the created quotation form via action service.
     */
    async createQuotation() {
        const lines = this.state.selectedIds
            .map(id => {
                const qty = this.state.qtys[id] || 0;
                if (qty <= 0) return null;
                return {
                    product_id: id,
                    qty: qty,
                    price: this.state.prices[id] ?? 0,
                };
            })
            .filter(Boolean);

        if (!lines.length) {
            this._showToast('error', _t('No Items'), _t('Please set qty > 0 for at least one product.'));
            return;
        }

        this.state.creating = true;
        try {
            const result = await this.orm.call(
                'stock.checker.helper', 'create_quotation', [],
                {
                    lines,
                    partner_id: this.state.selectedPartnerId || false,
                    partner_name: (!this.state.selectedPartnerId && this.state.partnerName)
                        ? this.state.partnerName
                        : false,
                }
            );

            if (result.error) {
                this._showToast('error', _t('Error'), result.error);
                return;
            }

            // Build toast message including partner info
            const partnerInfo = this.state.partnerName ? ` for ${this.state.partnerName}` : '';
            this._showToast(
                'success',
                _t('Quotation Created'),
                _t('%(name)s%(partner)s has been created.', {
                    name: result.name,
                    partner: partnerInfo,
                })
            );

            // Open created quotation
            await this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'sale.order',
                res_id: result.sale_order_id,
                views: [[false, 'form']],
                target: 'current',
            });

            // Reset selection and partner fields
            this.state.selectedIds = [];
            this.state.qtys = {};
            this.state.prices = {};
            this.state.partnerCode = '';
            this.state.partnerName = '';
            this.state.selectedPartnerId = false;
            this.state.partnerResults = [];

        } catch (err) {
            this._showToast('error', _t('Error'), _t('Failed to create quotation.'));
            console.error('[StockChecker] create_quotation error:', err);
        } finally {
            this.state.creating = false;
        }
    }

    // ── Helpers ────────────────────────────────────────────────────────────

    /**
     * Save warehouse/location preferences for the current user.
     */
    async _savePreferences() {
        try {
            await this.orm.call(
                'stock.checker.helper', 'save_user_preferences', [],
                {
                    warehouse_id: this.state.selectedWarehouseId,
                    location_id: this.state.selectedLocationId,
                }
            );
        } catch (err) {
            // Non-critical, fail silently
        }
    }

    /**
     * Show a toast notification for a given duration.
     * @param {'success'|'error'|'info'} type
     * @param {string} title
     * @param {string} msg
     * @param {number} [duration=4000] - Auto-dismiss duration in ms
     */
    _showToast(type, title, msg, duration = 4000) {
        this.state.toast = { type, title, msg };
        if (this._toastTimer) clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => {
            this.state.toast = null;
        }, duration);
    }

    /**
     * Dismiss the current toast immediately.
     */
    clearToast() {
        this.state.toast = null;
        if (this._toastTimer) {
            clearTimeout(this._toastTimer);
            this._toastTimer = null;
        }
    }

    /**
     * Expose formatQty to the template.
     * @param {number} qty
     * @returns {string}
     */
    formatQty(qty) {
        return formatQty(qty);
    }
}

// Register as a client action tag
registry.category("actions").add(
    "stock_enhanced_checker.StockCheckerAction",
    StockCheckerAction
);
