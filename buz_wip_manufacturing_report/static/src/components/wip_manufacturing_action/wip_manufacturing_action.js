/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState } from "@odoo/owl";
import { WipSidebar } from "../wip_sidebar/wip_sidebar";
import { WipMainPanel } from "../wip_main_panel/wip_main_panel";
import { SummaryCards } from "../summary_cards/summary_cards";

function todayISO() {
    return new Date().toISOString().slice(0, 10);
}

function firstOfMonthISO() {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
}

export class WipManufacturingAction extends Component {
    static template = "buz_wip_manufacturing_report.WipManufacturingAction";
    static components = { WipSidebar, WipMainPanel, SummaryCards };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.company = useService("company");

        this.state = useState({
            dateFrom: firstOfMonthISO(),
            dateTo: todayISO(),
            companyId: this.company.currentCompany.id,
            moIds: [],
            productIds: [],
            componentIds: [],
            locationIds: [],
            statusList: ["progress", "to_close", "done"],
            costSource: "svl",
            showValuationDetail: false,
            page: 0,
            pageSize: 50,
            search: "",
            expanded: {},
            reportData: null,
            loading: false,
            error: null,
        });
    }

    onSetDateFrom(value) {
        this.state.dateFrom = value;
    }

    onSetDateTo(value) {
        this.state.dateTo = value;
    }

    onSetMoIds(ids) {
        this.state.moIds = ids;
    }

    onSetProductIds(ids) {
        this.state.productIds = ids;
    }

    onSetComponentIds(ids) {
        this.state.componentIds = ids;
    }

    onSetLocationIds(ids) {
        this.state.locationIds = ids;
    }

    onToggleStatus(value, checked) {
        const set = new Set(this.state.statusList);
        if (checked) {
            set.add(value);
        } else {
            set.delete(value);
        }
        this.state.statusList = [...set];
    }

    onSetCostSource(value) {
        this.state.costSource = value;
    }

    onToggleValuationDetail() {
        this.state.showValuationDetail = !this.state.showValuationDetail;
    }

    onSetSearch(value) {
        this.state.search = value;
    }

    onChangePage(page) {
        this.state.page = Math.max(0, page);
        this.fetchData();
    }

    onChangePageSize(size) {
        this.state.pageSize = size;
        this.state.page = 0;
        this.fetchData();
    }

    toggleExpand(moId) {
        this.state.expanded[moId] = !this.state.expanded[moId];
    }

    expandAll() {
        if (!this.state.reportData) return;
        for (const mo of this.state.reportData.data) {
            this.state.expanded[mo.mo_id] = true;
        }
    }

    collapseAll() {
        if (!this.state.reportData) return;
        for (const mo of this.state.reportData.data) {
            this.state.expanded[mo.mo_id] = false;
        }
    }

    reset() {
        this.state.dateFrom = firstOfMonthISO();
        this.state.dateTo = todayISO();
        this.state.moIds = [];
        this.state.productIds = [];
        this.state.componentIds = [];
        this.state.locationIds = [];
        this.state.statusList = ["progress", "to_close", "done"];
        this.state.costSource = "svl";
        this.state.showValuationDetail = false;
        this.state.page = 0;
        this.state.search = "";
        this.state.reportData = null;
        this.state.error = null;
    }

    async generateReport() {
        if (this.state.dateFrom > this.state.dateTo) {
            this.notification.add("Date From must not be later than Date To", { type: "warning" });
            return;
        }
        this.state.page = 0;
        await this.fetchData();
    }

    async fetchData() {
        if (this.state.loading) {
            return;
        }
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call(
                "buz.wip.manufacturing.report", "get_wip_data",
                [],
                {
                    mo_ids: this.state.moIds.length ? this.state.moIds : false,
                    date_from: this.state.dateFrom,
                    date_to: this.state.dateTo,
                    product_ids: this.state.productIds.length ? this.state.productIds : false,
                    component_ids: this.state.componentIds.length ? this.state.componentIds : false,
                    location_ids: this.state.locationIds.length ? this.state.locationIds : false,
                    status_list: this.state.statusList.length ? this.state.statusList : false,
                    show_valuation_detail: this.state.showValuationDetail,
                    cost_source: this.state.costSource,
                    company_ids: [this.state.companyId],
                    page_size: this.state.pageSize,
                    page: this.state.page,
                }
            );
            this.state.reportData = data;
            for (const mo of data.data) {
                if (!(mo.mo_id in this.state.expanded)) {
                    this.state.expanded[mo.mo_id] = true;
                }
            }
        } catch (err) {
            this.state.error = "Unable to load WIP Manufacturing Report data. Please try again.";
            this.notification.add(this.state.error, { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    exportExcel() {
        this.action.doAction("buz_wip_manufacturing_report.action_wip_manufacturing_export_wizard", {
            additionalContext: {
                default_date_from: this.state.dateFrom,
                default_date_to: this.state.dateTo,
                default_mo_ids: this.state.moIds,
                default_product_ids: this.state.productIds,
                default_component_ids: this.state.componentIds,
                default_location_ids: this.state.locationIds,
                default_cost_source: this.state.costSource,
                default_show_valuation_detail: this.state.showValuationDetail,
            },
        });
    }

    openRecord(resModel, resId) {
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

registry.category("actions").add("buz_wip_manufacturing_report", WipManufacturingAction);
