/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { Sidebar } from "../sidebar/sidebar";
import { MainPanel } from "../main_panel/main_panel";

function todayISO() {
    return new Date().toISOString().slice(0, 10);
}

function firstOfMonthISO() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

export class StockCardAction extends Component {
    static template = "buz_new_stock_card.StockCardAction";
    static components = { Sidebar, MainPanel };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.company = useService("company");

        this.state = useState({
            productId: false,
            productName: "",
            dateFrom: firstOfMonthISO(),
            dateTo: todayISO(),
            companyId: this.company.currentCompany.id,
            warehouseId: false,
            selectedLocationId: false,
            selectedLocationName: "",
            includeChildren: false,
            page: 0,
            pageSize: 20,
            showMovementsOnly: false,
            product: null,
            cardData: null,
            locationTree: [],
            locationCounts: {},
            loading: false,
            error: null,
        });

    }

    async loadProductLocationTree() {
        if (!this.state.productId) {
            this.state.locationTree = [];
            this.state.locationCounts = {};
            return;
        }
        this.state.locationTree = await this.orm.call(
            "buz.stock.card.report", "get_product_locations_tree",
            [
                this.state.productId, this.state.dateFrom, this.state.dateTo,
                [this.state.companyId], this.state.warehouseId,
            ]
        );
        this.state.locationCounts = this._flattenCounts(this.state.locationTree);
    }

    _flattenCounts(nodes) {
        let counts = {};
        for (const node of nodes) {
            counts[node.id] = node.move_count || 0;
            if (node.children && node.children.length) {
                counts = { ...counts, ...this._flattenCounts(node.children) };
            }
        }
        return counts;
    }

    async onSelectProduct(productId, productName) {
        this.state.productId = productId;
        this.state.productName = productName;
        this.state.selectedLocationId = false;
        this.state.selectedLocationName = "";
        this.state.cardData = null;
        this.state.product = null;
        await this.loadProductLocationTree();
    }

    async onSelectLocation(locationId, locationName, selectable) {
        this.state.selectedLocationId = locationId;
        this.state.selectedLocationName = locationName;
        // View-type (warehouse folder) locations hold no move lines directly.
        this.state.includeChildren = selectable === false;
        this.state.page = 0;
        await this.fetchCardData();
    }

    onSetDateFrom(value) {
        this.state.dateFrom = value;
    }

    onSetDateTo(value) {
        this.state.dateTo = value;
    }

    onSetCompany(companyId) {
        this.state.companyId = companyId;
        this.state.warehouseId = false;
    }

    async onSetWarehouse(warehouseId) {
        this.state.warehouseId = warehouseId;
        this.state.selectedLocationId = false;
        this.state.selectedLocationName = "";
        this.state.cardData = null;
        await this.loadProductLocationTree();
    }

    onToggleShowMovementsOnly() {
        this.state.showMovementsOnly = !this.state.showMovementsOnly;
        if (this.state.cardData) {
            this.state.page = 0;
            this.fetchCardData();
        }
    }

    onChangePageSize(size) {
        this.state.pageSize = size;
        this.state.page = 0;
        if (this.state.cardData) {
            this.fetchCardData();
        }
    }

    onChangePage(page) {
        this.state.page = Math.max(0, page);
        this.fetchCardData();
    }

    async reset() {
        this.state.productId = false;
        this.state.productName = "";
        this.state.dateFrom = firstOfMonthISO();
        this.state.dateTo = todayISO();
        this.state.warehouseId = false;
        this.state.selectedLocationId = false;
        this.state.selectedLocationName = "";
        this.state.includeChildren = false;
        this.state.page = 0;
        this.state.cardData = null;
        this.state.product = null;
        this.state.locationTree = [];
        this.state.locationCounts = {};
        this.state.error = null;
    }

    async search() {
        if (!this.state.productId) {
            this.notification.add("กรุณาเลือกสินค้า", { type: "warning" });
            return;
        }
        if (this.state.dateFrom > this.state.dateTo) {
            this.notification.add("วันที่เริ่มต้นต้องไม่มากกว่าวันที่สิ้นสุด", { type: "warning" });
            return;
        }
        await this.loadProductLocationTree();
        if (this.state.selectedLocationId) {
            await this.fetchCardData();
        }
    }

    async fetchCardData() {
        if (!this.state.productId || !this.state.selectedLocationId) {
            return;
        }
        if (this.state.loading) {
            return;
        }
        this.state.loading = true;
        this.state.error = null;
        try {
            const scopeIds = await this.orm.call(
                "buz.stock.card.report", "resolve_location_scope",
                [this.state.selectedLocationId, this.state.includeChildren]
            );
            const [cardData, [product]] = await Promise.all([
                this.orm.call(
                    "buz.stock.card.report", "get_stock_card_data",
                    [
                        this.state.productId, scopeIds,
                        this.state.dateFrom, this.state.dateTo,
                        this.state.pageSize, this.state.page,
                        this.state.showMovementsOnly, [this.state.companyId],
                    ]
                ),
                this.orm.read(
                    "product.product",
                    [this.state.productId],
                    ["display_name", "default_code", "uom_id", "image_128"]
                ),
            ]);
            this.state.cardData = cardData;
            this.state.product = product;
        } catch (err) {
            this.state.error = "ไม่สามารถโหลดข้อมูล Stock Card ได้ กรุณาลองใหม่อีกครั้ง";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    exportExcel() {
        this.action.doAction("buz_new_stock_card.action_stock_card_export_wizard", {
            additionalContext: {
                default_product_id: this.state.productId || false,
                default_date_from: this.state.dateFrom,
                default_date_to: this.state.dateTo,
                default_show_movements_only: this.state.showMovementsOnly,
            },
        });
    }

    async printPdf() {
        if (!this.state.productId || !this.state.selectedLocationId) {
            this.notification.add("กรุณาเลือกสินค้าและ Location ก่อนพิมพ์", { type: "warning" });
            return;
        }
        await this.action.doAction({
            type: "ir.actions.report",
            report_type: "qweb-pdf",
            report_name: "buz_new_stock_card.report_stock_card_pdf",
            report_file: "buz_new_stock_card.report_stock_card_pdf",
            data: {
                location_id: this.state.selectedLocationId,
                include_children: this.state.includeChildren,
                date_from: this.state.dateFrom,
                date_to: this.state.dateTo,
                show_movements_only: this.state.showMovementsOnly,
                company_id: this.state.companyId,
            },
            context: {active_ids: [this.state.productId]},
        });
    }

    openDocument(resModel, resId) {
        if (!resModel || !resId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "new",
        });
    }
}

registry.category("actions").add("buz_new_stock_card", StockCardAction);
