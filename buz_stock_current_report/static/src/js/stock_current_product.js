/** @odoo-module **/

import { Domain } from "@web/core/domain";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import { SearchModel } from "@web/search/search_model";
import { useState } from "@odoo/owl";
import { kanbanView } from "@web/views/kanban/kanban_view";
import { KanbanController } from "@web/views/kanban/kanban_controller";

const RES_MODEL = "stock.current.product";

const SORT_OPTIONS = [
    { value: "default_code:asc", label: "รหัสสินค้า (A-Z)" },
    { value: "default_code:desc", label: "รหัสสินค้า (Z-A)" },
    { value: "free_to_use:desc", label: "พร้อมใช้ (มาก → น้อย)" },
    { value: "sales_qty_90d:desc", label: "ขายดี 90 วัน" },
    { value: "price_with_vat:asc", label: "ราคา (ต่ำ → สูง)" },
    { value: "price_with_vat:desc", label: "ราคา (สูง → ต่ำ)" },
];

const PANEL_PREF_KEY = "buz_stock_current_report.panel_collapsed";

function readPanelPref() {
    try {
        return window.localStorage.getItem(PANEL_PREF_KEY) === "1";
    } catch {
        return false;
    }
}

function writePanelPref(collapsed) {
    try {
        window.localStorage.setItem(PANEL_PREF_KEY, collapsed ? "1" : "0");
    } catch {
        // storage unavailable: preference is just not remembered
    }
}

export class StockCurrentProductKanbanController extends KanbanController {
    static template = "buz_stock_current_report.KanbanView";

    setup() {
        super.setup();
        this.panelState = useState({ collapsed: readPanelPref() });
    }

    togglePanel() {
        this.panelState.collapsed = !this.panelState.collapsed;
        writePanelPref(this.panelState.collapsed);
    }

    get selectedWarehouse() {
        const section = this.env.searchModel
            .getSections((s) => s.type === "category" && s.fieldName === "warehouse_id")[0];
        const value = section && section.activeValueId && section.values.get(section.activeValueId);
        return value ? value.display_name : "All";
    }

    get sortOptions() {
        return SORT_OPTIONS;
    }

    get currentSort() {
        const order = this.model.root.orderBy && this.model.root.orderBy[0];
        return order ? `${order.name}:${order.asc ? "asc" : "desc"}` : SORT_OPTIONS[0].value;
    }

    async onSortChange(ev) {
        const [name, direction] = ev.target.value.split(":");
        await this.model.root.load({ orderBy: [{ name, asc: direction === "asc" }] });
    }
}

registry.category("views").add("stock_current_product_kanban", {
    ...kanbanView,
    Controller: StockCurrentProductKanbanController,
});

// Warehouse panel: show the number of products on the "All" row.
patch(SearchModel.prototype, {
    async _fetchCategories(categories) {
        await super._fetchCategories(...arguments);
        if (this.resModel !== RES_MODEL) {
            return;
        }
        const domain = Domain.and([this.searchDomain, this._getFilterDomain()]).toList();
        const total = await this.orm.searchCount(this.resModel, domain, {
            context: this.globalContext,
        });
        for (const category of categories) {
            const allValue = category.values.get(false);
            if (allValue) {
                allValue.__count = total;
            }
        }
    },
});
