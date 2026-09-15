/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const THEME_STORAGE_KEY = "buz_it_management_dashboard_theme";

export class ITManagementDashboard extends Component {
    static template = "buz_it_asset.ITManagementDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.openDrilldown = this.openDrilldown.bind(this);
        this.toggleTheme = this.toggleTheme.bind(this);
        // ใช้ใน arrow expression ของ QWeb จึงต้องผูก context ของ component ไว้เอง
        this.selectTab = this.selectTab.bind(this);
        this.trendRef = useRef("ticketTrend");
        this.ticketStatusRef = useRef("ticketStatus");
        this.assetStatusRef = useRef("assetStatus");
        this.categoryRef = useRef("assetCategory");
        this.ticketFunnelRef = useRef("ticketFunnel");
        this.ticketAgingRef = useRef("ticketAging");
        this.repairStatusRef = useRef("repairStatus");
        this.repairWorkflowRef = useRef("repairWorkflow");
        this.charts = {};
        this.state = useState({
            data: null,
            period: "this_month",
            company: "all",
            loading: true,
            error: null,
            lastUpdated: null,
            tab: "overview",
            theme: this.getSavedTheme(),
        });
        onWillStart(async () => {
            try {
                await loadJS("/web/static/lib/Chart/Chart.js");
            } catch {
                // Chart.js can already be loaded by another backend asset bundle.
            }
            await this.loadData();
        });
        onMounted(() => this.renderCharts());
        onPatched(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    get filters() {
        const companyIds = this.state.company === "all"
            ? (this.state.data?.companies || []).map((company) => company.id)
            : [Number(this.state.company)];
        return {
            period: this.state.period,
            company_ids: companyIds,
        };
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = null;
        try {
            const data = await this.orm.call(
                "buz.it.management.dashboard",
                "get_dashboard_data",
                [this.filters],
            );
            this.state.data = data;
            this.state.lastUpdated = new Date();
        } catch (error) {
            this.state.error = error.message || "Unable to load dashboard data.";
        } finally {
            this.state.loading = false;
        }
    }

    async refresh() {
        if (this.state.loading) {
            return;
        }
        await this.loadData();
    }

    async onPeriodChange(event) {
        this.state.period = event.target.value;
        await this.loadData();
    }

    async onCompanyChange(event) {
        this.state.company = event.target.value;
        await this.loadData();
    }

    selectTab(tab) {
        this.state.tab = tab;
    }

    getSavedTheme() {
        try {
            return window.localStorage.getItem(THEME_STORAGE_KEY) === "dark" ? "dark" : "light";
        } catch {
            return "light";
        }
    }

    toggleTheme() {
        this.state.theme = this.state.theme === "dark" ? "light" : "dark";
        try {
            window.localStorage.setItem(THEME_STORAGE_KEY, this.state.theme);
        } catch {
            // บาง browser อาจปิดการใช้งาน storage แต่ยังสลับธีมชั่วคราวได้
        }
    }

    destroyCharts() {
        Object.values(this.charts).forEach((chart) => chart.destroy());
        this.charts = {};
    }

    renderCharts() {
        const data = this.state.data;
        if (!data || !window.Chart) {
            return;
        }
        this.destroyCharts();
        const chartOptions = this.getChartOptions();
        const trend = data.ticket_trend || [];
        if (this.trendRef.el) {
        this.charts.trend = new window.Chart(this.trendRef.el, {
            type: "line",
            data: {
                labels: trend.map((row) => row.label),
                datasets: [
                    {
                        label: "Opened",
                        data: trend.map((row) => row.opened),
                        borderColor: "#287df0",
                        backgroundColor: "rgba(40, 125, 240, .10)",
                        fill: true,
                        tension: .35,
                    },
                    {
                        label: "Closed",
                        data: trend.map((row) => row.closed),
                        borderColor: "#15b7c8",
                        backgroundColor: "transparent",
                        tension: .35,
                    },
                ],
            },
            options: {
                ...chartOptions,
                plugins: {
                    legend: { display: true, position: "top", align: "end", labels: { color: this.state.theme === "dark" ? "#e5e7eb" : "#142348" } },
                    tooltip: { mode: "index", intersect: false },
                },
                onClick: (_event, elements) => {
                    if (!elements.length) {
                        return;
                    }
                    const element = elements[0];
                    const target = element.datasetIndex === 0
                        ? "ticket_trend_opened" : "ticket_trend_closed";
                    this.openDrilldown(target, trend[element.index].date);
                },
            },
        }); }
        if (this.ticketStatusRef.el) { this.charts.ticketStatus = this.makeDoughnut(
            this.ticketStatusRef.el,
            data.ticket_status || [],
            ["#6d36e9", "#287df0", "#f39a16", "#22b45b", "#8b96a8"],
            (index) => this.openDrilldown(
                "ticket_status", data.ticket_status[index].stage_id
            ),
        ); }
        if (this.assetStatusRef.el) { this.charts.assetStatus = this.makeDoughnut(
            this.assetStatusRef.el,
            data.asset_status || [],
            ["#22b45b", "#287df0", "#f39a16", "#8b96a8", "#ee3e4b"],
            (index) => this.openDrilldown(
                "asset_status", data.asset_status[index].state
            ),
        ); }
        const categories = data.assets_by_category || [];
        if (this.categoryRef.el) { this.charts.category = new window.Chart(this.categoryRef.el, {
            type: "bar",
            data: {
                labels: categories.map((row) => row.label),
                datasets: [{
                    data: categories.map((row) => row.value),
                    backgroundColor: "#287df0",
                    borderRadius: 6,
                }],
            },
            options: {
                ...chartOptions,
                indexAxis: "y",
                scales: { x: { ...chartOptions.scales.x, beginAtZero: true }, y: chartOptions.scales.y },
                onClick: (_event, elements) => {
                    if (elements.length) {
                        this.openDrilldown(
                            "asset_category", categories[elements[0].index]
                        );
                    }
                },
            },
        }); }
        const workflow = data.workflow || {};
        const analytics = workflow.ticket_analytics || {};
        if (this.ticketFunnelRef.el) {
            this.charts.ticketFunnel = this.makeBar(this.ticketFunnelRef.el, data.ticket_status || [], "#287df0");
        }
        if (this.ticketAgingRef.el) {
            this.charts.ticketAging = this.makeBar(this.ticketAgingRef.el, analytics.aging || [], "#6d36e9");
        }
        if (this.repairStatusRef.el) {
            this.charts.repairStatus = this.makeBar(this.repairStatusRef.el, workflow.repair_analytics?.status || [], "#f39a16");
        }
        if (this.repairWorkflowRef.el) {
            this.charts.repairWorkflow = this.makeBar(this.repairWorkflowRef.el, workflow.repair_analytics?.status || [], "#f39a16");
        }
    }

    getChartOptions() {
        const textColor = this.state.theme === "dark" ? "#e5e7eb" : "#142348";
        const gridColor = this.state.theme === "dark" ? "rgba(148, 163, 184, .18)" : "rgba(20, 35, 72, .10)";
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false, labels: { color: textColor } } },
            scales: {
                x: { ticks: { color: textColor }, grid: { color: gridColor } },
                y: { ticks: { color: textColor }, grid: { color: gridColor } },
            },
        };
    }

    makeBar(element, rows, color) {
        return new window.Chart(element, {
            type: "bar",
            data: { labels: rows.map((row) => row.label), datasets: [{ data: rows.map((row) => row.value), backgroundColor: color, borderRadius: 5 }] },
            options: { ...this.getChartOptions(), responsive: true, maintainAspectRatio: false, indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0, color: this.state.theme === "dark" ? "#e5e7eb" : "#142348" }, grid: { color: this.state.theme === "dark" ? "rgba(148, 163, 184, .18)" : "rgba(20, 35, 72, .10)" } }, y: { ticks: { color: this.state.theme === "dark" ? "#e5e7eb" : "#142348" }, grid: { color: this.state.theme === "dark" ? "rgba(148, 163, 184, .18)" : "rgba(20, 35, 72, .10)" } } } },
        });
    }

    makeDoughnut(element, rows, colors, onClick) {
        if (!element) {
            return null;
        }
        const theme = this.state.theme;
        const centerText = {
            id: "itDashboardDoughnutCenter",
            afterDraw(chart) {
                const { ctx, chartArea } = chart;
                if (!chartArea || !rows.length) {
                    return;
                }
                const total = rows.reduce((sum, row) => sum + Number(row.value || 0), 0);
                const x = (chartArea.left + chartArea.right) / 2;
                const y = (chartArea.top + chartArea.bottom) / 2;
                ctx.save();
                ctx.textAlign = "center";
                ctx.fillStyle = theme === "dark" ? "#f3f4f6" : "#142348";
                ctx.font = "800 24px Inter, sans-serif";
                ctx.fillText(total, x, y + 2);
                ctx.fillStyle = theme === "dark" ? "#aeb9cc" : "#6f7d96";
                ctx.font = "12px Inter, sans-serif";
                ctx.fillText("Total", x, y + 21);
                ctx.restore();
            },
        };
        return new window.Chart(element, {
            type: "doughnut",
            data: {
                labels: rows.map((row) => row.label),
                datasets: [{
                    data: rows.map((row) => row.value),
                    backgroundColor: colors,
                    borderWidth: 2,
                    borderColor: theme === "dark" ? "#202b42" : "#ffffff",
                }],
            },
            plugins: [centerText],
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "66%",
                plugins: { legend: { display: false } },
                onClick: (_event, elements) => {
                    if (elements.length) {
                        onClick(elements[0].index);
                    }
                },
            },
        });
    }

    statusPercentage(rows, value) {
        const total = (rows || []).reduce((sum, row) => sum + Number(row.value || 0), 0);
        return total ? Math.round(Number(value || 0) / total * 100) : 0;
    }

    statusColor(label) {
        return {
            "New": "#6d36e9",
            "In Progress": "#287df0",
            "Pending User": "#f39a16",
            "Resolved": "#22b45b",
            "Closed": "#8b96a8",
        }[label] || "#8b96a8";
    }

    formatHours(value) {
        return value ? `${value} h` : "N/A";
    }
    formatSlaRate(rate, eligible) {
        if (!eligible || rate === null || rate === undefined) {
            return "No eligible tickets";
        }
        return `${Number(rate).toFixed(1)}% of eligible tickets`;
    }

    formatLastUpdated() {
        if (!this.state.lastUpdated) {
            return "Not synced yet";
        }
        return this.state.lastUpdated.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    formatDateRange(dateFrom, dateTo) {
        if (!dateFrom || !dateTo) {
            return "Date range unavailable";
        }
        const formatter = new Intl.DateTimeFormat(undefined, {
            year: "numeric",
            month: "short",
            day: "numeric",
        });
        const parseDate = (value) => new Date(`${value}T00:00:00`);
        return `${formatter.format(parseDate(dateFrom))} – ${formatter.format(parseDate(dateTo))}`;
    }

    hasRows(rows) {
        return Array.isArray(rows) && rows.some((row) => Number(row.value || 0) > 0);
    }

    formatAmount(value) {
        return new Intl.NumberFormat(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(Number(value || 0));
    }

    attentionItems(attention) {
        const rows = [];
        (attention?.urgent_tickets || []).forEach((item) => rows.push({ ...item, label: "Urgent", kind: "urgent", icon: "fa-bell-o" }));
        return rows.slice(0, 4);
    }

    async openDrilldown(target, bucket = null) {
        try {
            const action = await this.orm.call(
                "buz.it.management.dashboard",
                "get_drilldown_action",
                [target, this.filters, bucket],
            );
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(
                error.message || "Unable to open dashboard details.",
                { type: "danger" },
            );
        }
    }
}

registry.category("actions").add(
    "buz_it_management_dashboard",
    ITManagementDashboard,
);
