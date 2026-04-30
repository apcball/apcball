/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";
import { loadJS } from "@web/core/assets";

export class SaleForecastDashboard extends Component {
    static template = "sale_forecast.SaleForecastDashboard";
    static components = { Layout };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.monthlyCanvas = useRef("monthlyCanvas");
        this.productCanvas = useRef("productCanvas");

        this.monthlyChart = null;
        this.productChart = null;

        this.state = useState({
            loading: true,
            target_month: this.getCurrentMonth(),
            display: {
                controlPanel: {},
            },
            kpi: {
                forecast_qty: 0,
                forecast_qty_month: 0,
                allocated_qty: 0,
                actual_sold: 0,
                allocation_rate: 0,
                accuracy_rate: 0,
                active_plans: 0,
                pending_allocations: 0,
            },
            monthly: [],
            products: [],
            recent_plans: [],
            recent_allocations: [],
            weekly: [],
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadDashboard();
        });

        onMounted(() => this.renderCharts());
        onPatched(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    getCurrentMonth() {
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, "0");
        return `${year}-${month}`;
    }

    async onMonthChange(ev) {
        await this.loadDashboard();
    }

    async loadDashboard() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("sale.forecast.dashboard", "get_dashboard_data", [this.state.target_month]);
            this.state.kpi = data.kpi || this.state.kpi;
            this.state.monthly = data.monthly || [];
            this.state.products = data.products || [];
            this.state.recent_plans = data.recent_plans || [];
            this.state.recent_allocations = data.recent_allocations || [];
            this.state.weekly = data.weekly || [];
        } catch (e) {
            console.error("Failed to load dashboard data:", e);
        }
        this.state.loading = false;
    }

    destroyCharts() {
        if (this.monthlyChart) {
            this.monthlyChart.destroy();
            this.monthlyChart = null;
        }
        if (this.productChart) {
            this.productChart.destroy();
            this.productChart = null;
        }
    }

    renderCharts() {
        if (this.state.loading) {
            return;
        }
        this.destroyCharts();
        this.renderMonthlyChart();
        this.renderProductChart();
    }

    renderMonthlyChart() {
        const canvas = this.monthlyCanvas.el;
        if (!canvas || !window.Chart) {
            return;
        }
        const labels = this.state.monthly.map((row) => this.formatMonth(row.month));
        this.monthlyChart = new window.Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Forecast",
                        data: this.state.monthly.map((row) => row.forecast_qty || 0),
                        borderRadius: 8,
                        backgroundColor: "rgba(99, 102, 241, 0.75)",
                    },
                    {
                        label: "Allocated",
                        data: this.state.monthly.map((row) => row.allocated_qty || 0),
                        borderRadius: 8,
                        backgroundColor: "rgba(16, 185, 129, 0.75)",
                    },
                    {
                        label: "Actual Sold",
                        data: this.state.monthly.map((row) => row.actual_sold_qty || 0),
                        borderRadius: 8,
                        backgroundColor: "rgba(245, 158, 11, 0.80)",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top" },
                },
            },
        });
    }

    renderProductChart() {
        const canvas = this.productCanvas.el;
        if (!canvas || !window.Chart) {
            return;
        }
        const palette = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#06b6d4", "#8b5cf6", "#f97316", "#14b8a6"];
        this.productChart = new window.Chart(canvas, {
            type: "doughnut",
            data: {
                labels: this.state.products.map((row) => row.product_name || "Unknown"),
                datasets: [
                    {
                        data: this.state.products.map((row) => row.allocated_qty || 0),
                        backgroundColor: this.state.products.map((_, i) => palette[i % palette.length]),
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "right" },
                },
            },
        });
    }

    formatNumber(value) {
        return (value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
    }

    formatPercent(value) {
        return `${(value || 0).toFixed(2)}%`;
    }

    formatMonth(value) {
        if (!value) {
            return "-";
        }
        const date = new Date(`${value}T00:00:00`);
        return Number.isNaN(date.getTime())
            ? value
            : date.toLocaleDateString(undefined, { month: "short", year: "numeric" });
    }

    get weeklyRows() {
        const grouped = {};
        for (const row of this.state.weekly) {
            const month = row.arrival_month || "-";
            if (!grouped[month]) {
                grouped[month] = {
                    month,
                    week1: 0,
                    week2: 0,
                    week3: 0,
                    week4: 0,
                    week5: 0,
                    total: 0,
                };
            }
            const key = `week${row.week_index}`;
            grouped[month][key] = row.forecast_qty || 0;
            grouped[month].total += row.forecast_qty || 0;
        }
        return Object.values(grouped).sort((a, b) => (a.month > b.month ? 1 : -1));
    }

    async openPlans() {
        await this.action.doAction("sale_forecast.action_forecast_plan");
    }

    async openAllocations() {
        await this.action.doAction("sale_forecast.action_forecast_allocation");
    }
}
