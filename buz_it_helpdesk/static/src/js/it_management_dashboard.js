/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { HelpdeskDashboard } from "./helpdesk_dashboard";

const pad = (value) => String(value).padStart(2, "0");
const today = new Date();
const defaultDateTo = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
const defaultDateFrom = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-01`;

export class ItManagementDashboard extends Component {
    static components = { HelpdeskDashboard };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            section: "overview",
            filters: { company_id: "", date_from: defaultDateFrom, date_to: defaultDateTo },
            data: null,
            loading: false,
            error: false,
            filterVersion: 0,
        });
        this.load = this.load.bind(this);
        this.selectSection = this.selectSection.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.openSource = this.openSource.bind(this);
        onWillStart(this.load);
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        try {
            this.state.data = await this.orm.call(
                "it.management.dashboard", "get_dashboard_data",
                [this.state.section, this.state.filters]
            );
        } catch (error) {
            this.state.error = true;
        } finally {
            this.state.loading = false;
        }
    }

    async selectSection(section) {
        if (section === this.state.section) {
            return;
        }
        this.state.section = section;
        this.state.data = null;
        await this.load();
    }

    async onFilterChange(event) {
        this.state.filters[event.target.name] = event.target.value;
        this.state.filterVersion += 1;
        await this.load();
    }

    async openSource(item, title) {
        if (!item?.domain || !item?.res_model) {
            return;
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: item.res_model,
            views: [[false, "list"], [false, "form"]],
            domain: item.domain,
            context: { create: false, edit: false, delete: false },
            target: "current",
        });
    }

    isCompanySelected(companyId) {
        return String(companyId) === String(this.state.filters.company_id);
    }

    get filterKey() {
        return `${this.state.section}-${this.state.filterVersion}`;
    }
}

ItManagementDashboard.template = "buz_it_helpdesk.ItManagementDashboard";
registry.category("actions").add("buz_it_helpdesk_dashboard", ItManagementDashboard);
