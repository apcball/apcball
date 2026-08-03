/** @odoo-module **/

import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class ITManagementDashboard extends Component {
    static template = "buz_it_asset.ITManagementDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.openDrilldown = this.openDrilldown.bind(this);
        this.trendRef = useRef("ticketTrend");
        this.ticketStatusRef = useRef("ticketStatus");
        this.assetStatusRef = useRef("assetStatus");
        this.categoryRef = useRef("assetCategory");
        this.charts = {};
        this.state = useState({
            data: null,
            period: "this_month",
            company: "all",
            loading: true,
            error: null,
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
            this.state.data = await this.orm.call(
                "buz.it.management.dashboard",
                "get_dashboard_data",
                [this.filters],
            );
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

    destroyCharts() {
        Object.values(this.charts).forEach((chart) => chart.destroy());
        this.charts = {};
    }

    renderCharts() {
        const data = this.state.data;
        if (!data || !window.Chart || !this.trendRef.el) {
            return;
        }
        this.destroyCharts();
        const chartOptions = {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
        };
        const trend = data.ticket_trend || [];
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
                    legend: { display: true, position: "top", align: "end" },
                    tooltip: { mode: "index", intersect: false },
                },
            },
        });
        this.charts.ticketStatus = this.makeDoughnut(
            this.ticketStatusRef.el,
            data.ticket_status || [],
            ["#6d36e9", "#287df0", "#22b45b", "#8b96a8"],
            (index) => this.openDrilldown(
                "ticket_status", data.ticket_status[index].stage_id
            ),
        );
        this.charts.assetStatus = this.makeDoughnut(
            this.assetStatusRef.el,
            data.asset_status || [],
            ["#22b45b", "#287df0", "#f39a16", "#8b96a8", "#ee3e4b"],
            (index) => this.openDrilldown(
                "asset_status", data.asset_status[index].state
            ),
        );
        const categories = data.assets_by_category || [];
        this.charts.category = new window.Chart(this.categoryRef.el, {
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
                scales: { x: { beginAtZero: true } },
                onClick: (_event, elements) => {
                    if (elements.length) {
                        this.openDrilldown(
                            "asset_category", categories[elements[0].index]
                        );
                    }
                },
            },
        });
    }

    makeDoughnut(element, rows, colors, onClick) {
        if (!element) {
            return null;
        }
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
                ctx.fillStyle = "#142348";
                ctx.font = "800 24px Inter, sans-serif";
                ctx.fillText(total, x, y + 2);
                ctx.fillStyle = "#6f7d96";
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
                    borderColor: "#ffffff",
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
