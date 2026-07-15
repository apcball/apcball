/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const pad = (value) => String(value).padStart(2, "0");
const today = new Date();
const firstDay = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-01`;
const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);
const defaultDateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;

export class HelpdeskDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ filters: { company_id: "", date_from: firstDay, date_to: defaultDateTo, team_id: "", assignee_id: "", priority_id: "", category_id: "" }, data: null, loading: true });
        onWillStart(() => this.load());
    }
    async load() {
        this.state.loading = true;
        this.state.data = await this.orm.call("it.helpdesk.ticket", "get_dashboard_data", [this.state.filters]);
        this.state.loading = false;
    }
    async onFilterChange(event) {
        this.state.filters[event.target.name] = event.target.value;
        await this.load();
    }
    async resetFilters() {
        Object.assign(this.state.filters, { company_id: "", date_from: firstDay, date_to: defaultDateTo, team_id: "", assignee_id: "", priority_id: "", category_id: "" });
        await this.load();
    }
    async openTickets(item, title) {
        await this.action.doAction({ type: "ir.actions.act_window", name: title, res_model: "it.helpdesk.ticket", views: [[false, "list"], [false, "form"]], domain: item.domain || this.state.data.domain, context: { create: false, edit: false, delete: false }, target: "current" });
    }
    get barMax() {
        const values = [...(this.state.data?.trend || []), ...(this.state.data?.status_overview || [])].map((item) => item.count);
        return Math.max(...values, 1);
    }
    barWidth(count) {
        return `${Math.max((count / this.barMax) * 100, count ? 4 : 0)}%`;
    }
}
HelpdeskDashboard.template = "buz_it_helpdesk.HelpdeskDashboard";
registry.category("actions").add("buz_it_helpdesk_dashboard", HelpdeskDashboard);
