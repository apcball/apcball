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
        this.loadSequence = 0;
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            section: "overview",
            filters: { company_id: "", date_from: defaultDateFrom, date_to: defaultDateTo },
            data: null,
            loading: false,
            error: false,
            filterVersion: 0,
            lastUpdated: null,
            sidebarCollapsed: false,
        });
        this.load = this.load.bind(this);
        this.selectSection = this.selectSection.bind(this);
        this.onFilterChange = this.onFilterChange.bind(this);
        this.openSource = this.openSource.bind(this);
        this.openChartSource = this.openChartSource.bind(this);
        this.onChartKeydown = this.onChartKeydown.bind(this);
        this.openNavigation = this.openNavigation.bind(this);
        onWillStart(this.load);
    }

    async load() {
        const sequence = ++this.loadSequence;
        const section = this.state.section;
        const filters = { ...this.state.filters };
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call(
                "it.management.dashboard", "get_dashboard_data",
                [section, filters]
            );
            if (this.isCurrentRequest(sequence, section)) {
                this.state.data = data;
                this.state.lastUpdated = new Date();
            }
        } catch (error) {
            if (this.isCurrentRequest(sequence, section)) {
                this.state.error = true;
            }
        } finally {
            if (this.isCurrentRequest(sequence, section)) {
                this.state.loading = false;
            }
        }
    }

    isCurrentRequest(sequence, section) {
        return sequence === this.loadSequence && section === this.state.section;
    }

    async openNavigation(item) {
        if (item?.kind === "section" && item.section) {
            await this.selectSection(item.section);
            return;
        }
        if (item?.kind === "action" && item.action_xml_id) {
            await this.action.doAction(item.action_xml_id);
        }
    }

    get navigationItems() {
        return this.state.data?.options?.navigation || [];
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

    toggleSidebar() {
        this.state.sidebarCollapsed = !this.state.sidebarCollapsed;
    }

    async refresh() {
        await this.load();
    }

    async openSource(item, title) {
        if (!item?.res_model) {
            return;
        }
        if (item.res_id) {
            await this.action.doAction({
                type: "ir.actions.act_window",
                name: title,
                res_model: item.res_model,
                res_id: item.res_id,
                views: [[false, "form"]],
                target: "current",
            });
            return;
        }
        if (!item.domain) {
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

    async onRowKeydown(event, item, title) {
        if (event.key !== 'Enter' && event.key !== ' ') {
            return;
        }
        event.preventDefault();
        await this.openSource(item, title);
    }

    get recentTickets() {
        return this.state.data?.recent_tickets?.rows || [];
    }

    get renewalsDue() {
        return this.state.data?.renewals_due?.rows || [];
    }

    formatDashboardDate(value) {
        return value ? value.slice(0, 10) : "";
    }

    kpiIcon(code) {
        return {
            open: "fa-ticket",
            sla_overdue: "fa-clock-o",
            in_use: "fa-desktop",
            repair: "fa-wrench",
            license_expiring: "fa-file-text-o",
        }[code] || "fa-bar-chart";
    }

    isCompanySelected(companyId) {
        return String(companyId) === String(this.state.filters.company_id);
    }

    get chartSeries() {
        return this.state.data?.charts?.created_resolved?.series || [];
    }

    get backlogRows() {
        return this.state.data?.charts?.ticket_backlog?.rows || [];
    }

    get assetStatusRows() {
        return this.state.data?.charts?.asset_status?.rows || [];
    }

    get assetStatusTotal() {
        return this.state.data?.charts?.asset_status?.total || 0;
    }

    chartMax() {
        return Math.max(1, ...this.chartSeries.map((item) => Math.max(item.created_count, item.resolved_count)));
    }

    linePoints(key) {
        const series = this.chartSeries;
        const max = this.chartMax();
        if (!series.length) {
            return "";
        }
        return series.map((item, index) => {
            const x = 52 + (index * 616) / Math.max(1, series.length - 1);
            const y = 198 - (item[key] * 156) / max;
            return x + "," + y;
        }).join(" ");
    }

    linePointX(index) {
        return 52 + (index * 616) / Math.max(1, this.chartSeries.length - 1);
    }

    linePointY(value) {
        return 198 - (value * 156) / this.chartMax();
    }

    backlogMax() {
        return Math.max(1, ...this.backlogRows.map((item) => item.count));
    }

    backlogY(index) {
        return 28 + index * 34;
    }

    backlogWidth(count) {
        return (count * 180) / this.backlogMax();
    }

    assetDashOffset(index) {
        return -this.assetStatusRows.slice(0, index).reduce((total, row) => total + row.percentage, 0);
    }

    assetColor(code) {
        return {
            available: "#12A57A",
            in_use: "#7A5AF8",
            repair: "#F79009",
            lost: "#D92D20",
            retired: "#667085",
        }[code] || "#98A2B3";
    }

    async openChartSource(item, kind, title) {
        const domain = item?.[kind + "_domain"] || item?.domain;
        if (domain) {
            await this.openSource({ domain, res_model: kind === "created" || kind === "resolved" ? "it.helpdesk.ticket" : "buz.it.asset" }, title);
        }
    }

    onChartKeydown(event, item, kind, title) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.openChartSource(item, kind, title);
        }
    }
    get lastUpdatedLabel() {
        if (!this.state.lastUpdated) {
            return "Not loaded yet";
        }
        return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(this.state.lastUpdated);
    }

    get hasData() {
        const data = this.state.data || {};
        return Boolean(data.kpis?.length || data.tickets?.length || data.assets?.length || data.status_overview?.length || data.status?.length);
    }

    get filterKey() {
        return `${this.state.section}-${this.state.filterVersion}`;
    }
}

ItManagementDashboard.template = "buz_it_helpdesk.ItManagementDashboard";
registry.category("actions").add("buz_it_helpdesk_dashboard", ItManagementDashboard);
