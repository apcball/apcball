/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const pad = (value) => String(value).padStart(2, "0");
const today = new Date();
const firstDay = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-01`;
const lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);
const defaultDateTo = `${lastDay.getFullYear()}-${pad(lastDay.getMonth() + 1)}-${pad(lastDay.getDate())}`;

const defaultFilters = () => ({
    company_id: "",
    date_from: firstDay,
    date_to: defaultDateTo,
    team_id: "",
    assignee_id: "",
    priority_id: "",
    category_id: "",
});

export class HelpdeskDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.openTickets = this.openTickets.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.resetFilters = this.resetFilters.bind(this);
        this.load = this.load.bind(this);
        this.loadSequence = 0;
        this.state = useState({
            filters: defaultFilters(),
            data: null,
            loading: true,
            error: false,
        });
        onWillStart(this.load);
    }

    async load() {
        const sequence = ++this.loadSequence;
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call(
                "it.helpdesk.ticket",
                "get_dashboard_data",
                [this.state.filters]
            );
            if (sequence === this.loadSequence) {
                this.state.data = data;
            }
        } catch (error) {
            if (sequence === this.loadSequence) {
                this.state.error = true;
            }
        } finally {
            if (sequence === this.loadSequence) {
                this.state.loading = false;
            }
        }
    }

    async onFilterChange(event) {
        this.state.filters[event.currentTarget.name] = event.currentTarget.value;
        await this.load();
    }

    async resetFilters() {
        Object.assign(this.state.filters, defaultFilters());
        await this.load();
    }

    async openTickets(item, title) {
        const domain = item?.domain || this.state.data?.domain || [];
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: "it.helpdesk.ticket",
            views: [[false, "list"], [false, "form"]],
            domain,
            context: { create: false, edit: false, delete: false },
            target: "current",
        });
    }

    kpiIcon(code) {
        return {
            open: "fa-folder-open-o",
            new: "fa-inbox",
            in_progress: "fa-cogs",
            pending_user: "fa-hourglass-half",
            resolved: "fa-check-circle",
            closed: "fa-archive",
            sla_overdue: "fa-exclamation-triangle",
            response_sla_overdue: "fa-clock-o",
        }[code] || "fa-ticket";
    }

    barWidth(count, items) {
        const max = Math.max(...(items || []).map((item) => item.count), 1);
        return `${Math.min(Math.max((count / max) * 100, count ? 4 : 0), 100)}%`;
    }
}

HelpdeskDashboard.template = "buz_it_helpdesk.HelpdeskDashboard";
registry.category("actions").add("buz_it_helpdesk_dashboard", HelpdeskDashboard);
