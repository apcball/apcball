/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillUnmount, useState } from "@odoo/owl";
import { Sidebar } from "../sidebar/sidebar";
import { MainPanel } from "../main_panel/main_panel";
const { DateTime } = luxon;

export class StockCardAction extends Component {
    static template = "buz_new_stock_card.StockCardAction";
    static components = { Sidebar, MainPanel };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.company = useService("company");
        this.requestId = 0;
        this.state = useState({
            productId: false, productName: "",
            dateFrom: DateTime.local().startOf("month").toISODate(),
            dateTo: DateTime.local().toISODate(),
            companyId: this.company.currentCompany.id,
            warehouseId: false, selectedLocationId: false, selectedLocationName: "",
            includeChildren: false, page: 0, pageSize: 50, showMovementsOnly: false,
            product: null, cardData: null, scopeLabel: "",
            locationTree: [], locationCounts: {}, loading: false, error: null,
        });
        onWillUnmount(() => { this.requestId++; });
    }

    get rpcOptions() {
        return { context: { allowed_company_ids: [this.state.companyId] } };
    }

    invalidate({ location = false, product = false } = {}) {
        this.requestId++;
        Object.assign(this.state, {
            page: 0, cardData: null, product: null, loading: false, error: null,
            locationTree: [], locationCounts: {}, scopeLabel: "",
        });
        if (location) {
            Object.assign(this.state, {
                selectedLocationId: false, selectedLocationName: "", includeChildren: false,
            });
        }
        if (product) {
            this.state.productId = false;
            this.state.productName = "";
        }
    }

    onSelectProduct(productId, productName) {
        this.invalidate({ location: true });
        Object.assign(this.state, { productId, productName });
    }

    async onSelectLocation(locationId, locationName, selectable) {
        Object.assign(this.state, {
            selectedLocationId: locationId, selectedLocationName: locationName,
            includeChildren: selectable === false, page: 0,
        });
        await this.fetchCardData();
    }

    onSetDateFrom(value) { this.invalidate(); this.state.dateFrom = value; }
    onSetDateTo(value) { this.invalidate(); this.state.dateTo = value; }

    onSetCompany(companyId) {
        this.invalidate({ location: true, product: true });
        Object.assign(this.state, { companyId, warehouseId: false });
    }

    onSetWarehouse(warehouseId) {
        this.invalidate({ location: true });
        this.state.warehouseId = warehouseId;
    }

    onToggleShowMovementsOnly() {
        this.state.showMovementsOnly = !this.state.showMovementsOnly;
        if (this.state.cardData || this.state.loading) { this.search(); }
    }

    onChangePageSize(size) {
        this.state.pageSize = size;
        this.search();
    }

    onChangePage(page) {
        const last = Math.max(0, Math.ceil((this.state.cardData?.total_count || 0) / this.state.pageSize) - 1);
        this.state.page = Math.min(last, Math.max(0, page));
        this.fetchCardData();
    }

    reset() {
        this.invalidate({ location: true, product: true });
        Object.assign(this.state, {
            dateFrom: DateTime.local().startOf("month").toISODate(),
            dateTo: DateTime.local().toISODate(), warehouseId: false,
            pageSize: 50, showMovementsOnly: false,
        });
    }

    validFilters() {
        let message;
        if (!this.state.productId) {
            message = "กรุณาเลือกสินค้า";
        } else if (!this.state.dateFrom || !this.state.dateTo || this.state.dateFrom > this.state.dateTo) {
            message = "กรุณาระบุช่วงวันที่ให้ถูกต้อง วันที่เริ่มต้นต้องไม่มากกว่าวันที่สิ้นสุด";
        }
        if (message) { this.notification.add(message, { type: "warning" }); }
        return !message;
    }

    search() {
        this.state.page = 0;
        return this.fetchCardData();
    }

    async fetchCardData() {
        if (!this.validFilters()) { return; }
        const requestId = ++this.requestId;
        const filters = { ...this.state };
        const options = this.rpcOptions;
        this.state.loading = true;
        this.state.error = null;
        try {
            const scope = await this.orm.call("buz.stock.card.report", "resolve_report_scope", [
                filters.companyId, filters.warehouseId ? [filters.warehouseId] : [],
                filters.selectedLocationId ? [filters.selectedLocationId] : [], filters.includeChildren,
            ], options);
            if (requestId !== this.requestId) { return; }
            const [cardData, [product], tree] = await Promise.all([
                this.orm.call("buz.stock.card.report", "get_stock_card_data", [
                    filters.productId, scope.location_ids, filters.dateFrom, filters.dateTo,
                    filters.pageSize, filters.page, filters.showMovementsOnly, [filters.companyId],
                ], options),
                this.orm.read("product.product", [filters.productId], [
                    "display_name", "default_code", "uom_id", "active", "type", "categ_id",
                ], options),
                this.orm.call("buz.stock.card.report", "get_product_locations_tree", [
                    filters.productId, filters.dateFrom, filters.dateTo,
                    [filters.companyId], filters.warehouseId,
                ], options),
            ]);
            if (requestId !== this.requestId) { return; }
            const counts = {};
            const collect = (nodes) => nodes.forEach((node) => {
                counts[node.id] = node.move_count || 0;
                collect(node.children || []);
            });
            collect(tree);
            Object.assign(this.state, {
                cardData, product, scopeLabel: scope.label, locationTree: tree, locationCounts: counts,
            });
        } catch (err) {
            if (requestId !== this.requestId) { return; }
            this.state.cardData = null;
            this.state.error = "ไม่สามารถโหลดข้อมูล Stock Card ได้ กรุณาตรวจสอบตัวกรองแล้วลองใหม่อีกครั้ง";
        } finally {
            if (requestId === this.requestId) { this.state.loading = false; }
        }
    }

    exportExcel() {
        if (!this.validFilters()) { return; }
        this.action.doAction("buz_new_stock_card.action_stock_card_export_wizard", {
            additionalContext: {
                ...this.rpcOptions.context,
                default_product_id: this.state.productId,
                default_company_id: this.state.companyId,
                default_date_from: this.state.dateFrom, default_date_to: this.state.dateTo,
                default_warehouse_ids: this.state.warehouseId ? [this.state.warehouseId] : [],
                default_location_ids: this.state.selectedLocationId ? [this.state.selectedLocationId] : [],
                default_include_children: this.state.includeChildren,
                default_report_scope: true, default_include_cost_lot: false,
                default_show_movements_only: this.state.showMovementsOnly,
            },
        });
    }

    openDocument(resModel, resId) {
        if (!resModel || !resId) { return; }
        this.action.doAction({
            type: "ir.actions.act_window", res_model: resModel, res_id: resId,
            views: [[false, "form"]], target: "new", context: this.rpcOptions.context,
        });
    }
}
registry.category("actions").add("buz_new_stock_card", StockCardAction);
