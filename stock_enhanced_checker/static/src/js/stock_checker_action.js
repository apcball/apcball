/** @odoo-module **/
/**
 * File: static/src/js/stock_checker_action.js
 * Purpose: Main OWL component for Stock Enhanced Checker client action.
 */

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { StockCheckerTable } from "./stock_checker_table";
import { STOCK_FILTERS, debounce, formatQty } from "./stock_checker_filters";

class StockCheckerAction extends Component {
    static template = "stock_enhanced_checker.StockCheckerAction";
    static components = { StockCheckerTable };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.filters = STOCK_FILTERS;

        this.state = useState({
            warehouses: [],
            locations: [],
            pricelists: [],
            selectedWarehouseId: false,
            selectedLocationId: false,
            selectedPricelistId: false,

            products: [],
            total: 0,
            offset: 0,
            limit: 50,

            loading: false,
            creating: false,
            search: '',
            filterType: 'all',
            toast: null,
            theme: 'dark',

            stats: { in_stock: 0, low_stock: 0, out_of_stock: 0, with_incoming: 0 },

            canCreateQuotation: false,

            selectedIds: [],
            qtys: {},
            prices: {},

            partnerCode: '',
            partnerName: '',
            selectedPartnerId: false,
            partnerResults: [],
        });

        this._debouncedPartnerSearch = debounce(this._searchPartner.bind(this), 300);

        onWillStart(async () => {
            await this._init();
        });
    }

    // ── Init ───────────────────────────────────────────────────────────

    async _init() {
        this.state.loading = true;
        try {
            const savedTheme = localStorage.getItem('sc_theme');
            if (savedTheme === 'light' || savedTheme === 'dark') {
                this.state.theme = savedTheme;
            }

            const [warehouses, prefs, rights, pricelists] = await Promise.all([
                this.orm.call('stock.checker.helper', 'get_warehouses', []),
                this.orm.call('stock.checker.helper', 'get_user_preferences', []),
                this.orm.call('stock.checker.helper', 'get_user_rights', []),
                this.orm.call('stock.checker.helper', 'get_pricelists', []),
            ]);

            this.state.warehouses = warehouses;
            this.state.pricelists = pricelists;
            this.state.canCreateQuotation = rights.can_create_quotation;

            // Restore pricelist preference
            if (prefs.pricelist_id) {
                this.state.selectedPricelistId = prefs.pricelist_id;
            }

            let warehouseId = prefs.warehouse_id;
            if (!warehouseId && warehouses.length) {
                warehouseId = warehouses[0].id;
            }

            if (warehouseId) {
                this.state.selectedWarehouseId = warehouseId;
                await this._loadLocations(warehouseId);

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

    // ── Data Loaders ───────────────────────────────────────────────────

    async _loadLocations(warehouseId) {
        const locs = await this.orm.call(
            'stock.checker.helper', 'get_locations', [], { warehouse_id: warehouseId }
        );
        this.state.locations = locs;
    }

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
                    pricelist_id: this.state.selectedPricelistId || false,
                }
            );

            if (reset) {
                this.state.products = result.products;
                // Reset prices from pricelist when data reloads
                const newPrices = {};
                for (const p of result.products) {
                    if (this.state.selectedIds.includes(p.id)) {
                        // Keep user-edited price if already selected
                        if (this.state.prices[p.id] !== undefined) {
                            newPrices[p.id] = this.state.prices[p.id];
                        } else {
                            newPrices[p.id] = p.list_price;
                        }
                    }
                }
                this.state.prices = { ...this.state.prices, ...newPrices };
            } else {
                this.state.products = [...this.state.products, ...result.products];
            }
            this.state.total = result.total;
            if (result.stats) {
                this.state.stats = result.stats;
            }
        } catch (err) {
            this._showToast('error', _t('Error'), _t('Failed to load stock data.'));
            console.error('[StockChecker] get_stock_data error:', err);
        } finally {
            this.state.loading = false;
        }
    }

    // ── Event Handlers ─────────────────────────────────────────────────

    async loadStockData() {
        await this._loadStockData(true);
    }

    async onWarehouseChange(ev) {
        const warehouseId = parseInt(ev.target.value) || false;
        this.state.selectedWarehouseId = warehouseId;
        this.state.selectedLocationId = false;
        this.state.products = [];
        this.state.total = 0;

        if (warehouseId) {
            await this._loadLocations(warehouseId);
            if (this.state.locations.length) {
                this.state.selectedLocationId = this.state.locations[0].id;
                await this._loadStockData(true);
                this._savePreferences();
            }
        } else {
            this.state.locations = [];
        }
    }

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

    async onPricelistChange(ev) {
        const pricelistId = parseInt(ev.target.value) || false;
        this.state.selectedPricelistId = pricelistId;

        // Reload data with new pricelist prices
        if (this.state.selectedLocationId) {
            // Reset prices so they update from pricelist
            this.state.prices = {};
            await this._loadStockData(true);
        }
        this._savePreferences();
    }

    onSearchType(ev) {
        this.state.search = ev.target.value;
    }

    async onSearchKeydown(ev) {
        if (ev.key === 'Enter') {
            await this._loadStockData(true);
        }
    }

    async onFilterChange(filterKey) {
        this.state.filterType = filterKey;
        await this._loadStockData(true);
    }

    async loadMore() {
        this.state.offset += this.state.limit;
        await this._loadStockData(false);
    }

    // ── Partner ────────────────────────────────────────────────────────

    onPartnerCodeInput(ev) {
        this.state.partnerCode = ev.target.value;
        this.state.selectedPartnerId = false;
        if (!ev.target.value.trim()) {
            this.state.partnerResults = [];
            return;
        }
        this._debouncedPartnerSearch();
    }

    onPartnerCodeKeydown(ev) {
        if (ev.key === 'Escape') {
            this.state.partnerResults = [];
        }
    }

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

    onSelectPartner(partner) {
        this.state.selectedPartnerId = partner.id;
        this.state.partnerCode = partner.ref || partner.display;
        this.state.partnerName = partner.name;
        this.state.partnerResults = [];
    }

    onPartnerNameInput(ev) {
        this.state.partnerName = ev.target.value;
        this.state.selectedPartnerId = false;
    }

    // ── Selection ──────────────────────────────────────────────────────

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
                    newQtys[p.id] = 1;
                    newPrices[p.id] = p.list_price;
                }
            }
            this.state.selectedIds = newIds;
            this.state.qtys = newQtys;
            this.state.prices = newPrices;
        }
    }

    onToggleRow(productId) {
        const idx = this.state.selectedIds.indexOf(productId);
        if (idx >= 0) {
            this.state.selectedIds = this.state.selectedIds.filter(id => id !== productId);
        } else {
            const product = this.state.products.find(p => p.id === productId);
            this.state.selectedIds = [...this.state.selectedIds, productId];
            if (this.state.qtys[productId] === undefined && product) {
                this.state.qtys = { ...this.state.qtys, [productId]: 1 };
            }
            if (this.state.prices[productId] === undefined && product) {
                this.state.prices = { ...this.state.prices, [productId]: product.list_price };
            }
        }
    }

    onQtyChange(productId, qty) {
        this.state.qtys = { ...this.state.qtys, [productId]: qty };
    }

    onPriceChange(productId, price) {
        this.state.prices = { ...this.state.prices, [productId]: price };
    }

    clearSelection() {
        this.state.selectedIds = [];
    }

    // ── Computed ───────────────────────────────────────────────────────

    get allSelected() {
        return (
            this.state.products.length > 0 &&
            this.state.products.every(p => this.state.selectedIds.includes(p.id))
        );
    }

    get stats() {
        return this.state.stats;
    }

    get selectedPricelistCurrency() {
        const pl = this.state.pricelists.find(p => p.id === this.state.selectedPricelistId);
        return pl ? pl.currency : '';
    }

    // ── Quotation ──────────────────────────────────────────────────────

    async createQuotation() {
        const lines = this.state.selectedIds
            .map(id => {
                const qty = this.state.qtys[id] || 0;
                if (qty <= 0) return null;
                return { product_id: id, qty, price: this.state.prices[id] ?? 0 };
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
                        ? this.state.partnerName : false,
                    pricelist_id: this.state.selectedPricelistId || false,
                }
            );

            if (result.error) {
                this._showToast('error', _t('Error'), result.error);
                return;
            }

            const partnerInfo = this.state.partnerName ? ` for ${this.state.partnerName}` : '';
            this._showToast('success', _t('Quotation Created'),
                _t('%(name)s%(partner)s has been created.', { name: result.name, partner: partnerInfo }));

            await this.action.doAction({
                type: 'ir.actions.act_window',
                res_model: 'sale.order',
                res_id: result.sale_order_id,
                views: [[false, 'form']],
                target: 'current',
            });

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

    // ── Helpers ────────────────────────────────────────────────────────

    async _savePreferences() {
        try {
            await this.orm.call(
                'stock.checker.helper', 'save_user_preferences', [],
                {
                    warehouse_id: this.state.selectedWarehouseId,
                    location_id: this.state.selectedLocationId,
                    pricelist_id: this.state.selectedPricelistId || false,
                }
            );
        } catch (_) { }
    }

    _showToast(type, title, msg, duration = 4000) {
        this.state.toast = { type, title, msg };
        if (this._toastTimer) clearTimeout(this._toastTimer);
        this._toastTimer = setTimeout(() => { this.state.toast = null; }, duration);
    }

    clearToast() {
        this.state.toast = null;
        if (this._toastTimer) { clearTimeout(this._toastTimer); this._toastTimer = null; }
    }

    toggleTheme() {
        this.state.theme = this.state.theme === 'dark' ? 'light' : 'dark';
        localStorage.setItem('sc_theme', this.state.theme);
    }

    formatQty(qty) { return formatQty(qty); }
}

registry.category("actions").add(
    "stock_enhanced_checker.StockCheckerAction",
    StockCheckerAction
);
