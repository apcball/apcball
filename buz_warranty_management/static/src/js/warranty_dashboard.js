/** @odoo-module **/

import { registry } from "@web/core/registry";
import {
    Component,
    onMounted,
    onPatched,
    onWillStart,
    onWillUnmount,
    useRef,
    useState,
} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

export class WarrantyDashboard extends Component {
    static template = "buz_warranty_management.WarrantyDashboard";

    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        this.chartRefs = {
            warrantyStatus: useRef("warrantyStatusChart"),
            claimsTrend: useRef("claimsTrendChart"),
            monthlyComparison: useRef("monthlyComparisonChart"),
            topProducts: useRef("topProductsChart"),
            topCustomers: useRef("topCustomersChart"),
            claimTypes: useRef("claimTypesChart"),
            warrantyExpiry: useRef("warrantyExpiryChart"),
        };
        this.charts = {};

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

        this.state = useState({
            loading: true,
            filters: {
                date_from: this.formatDate(firstDay),
                date_to: this.formatDate(today),
                product_id: "",
                customer_id: "",
            },
            filterOptions: {
                products: [],
                customers: [],
            },
            data: {
                kpi: {},
                warranty_status: [],
                claims_trend: [],
                monthly_comparison: [],
                top_products: [],
                top_customers: [],
                claim_types: [],
                warranty_expiry: [],
                recent_warranties: [],
            },
        });

        onWillStart(async () => {
            try {
                await loadJS("/web/static/lib/Chart/Chart.js");
            } catch (e) {
                console.warn("Chart.js already loaded");
            }
            await this.loadFilterOptions();
            await this.loadData();
        });
        onMounted(() => this.renderAllCharts());
        onPatched(() => this.renderAllCharts());
        onWillUnmount(() => this.destroyAllCharts());
    }

    formatDate(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${day}`;
    }

    formatNumber(value) {
        return (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        });
    }

    formatPercent(value) {
        return `${(value || 0).toFixed(1)}%`;
    }

    async loadFilterOptions() {
        try {
            const opts = await this.rpc(
                "/warranty/dashboard/filter_options",
                {}
            );
            this.state.filterOptions = opts;
        } catch (e) {
            console.error("Failed to load filter options:", e);
        }
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.rpc("/warranty/dashboard/data", {
                filters: this.state.filters,
            });
            this.state.data = data;
        } catch (e) {
            console.error("Failed to load dashboard data:", e);
            this.notification.add(
                "Failed to load dashboard data. Check console for details.",
                { type: "danger", sticky: true }
            );
        }
        this.state.loading = false;
    }

    async onQuickPeriod(period) {
        const today = new Date();
        let from;
        switch (period) {
            case "week":
                from = new Date(today);
                from.setDate(today.getDate() - today.getDay());
                break;
            case "month":
                from = new Date(today.getFullYear(), today.getMonth(), 1);
                break;
            case "quarter": {
                const q = Math.floor(today.getMonth() / 3);
                from = new Date(today.getFullYear(), q * 3, 1);
                break;
            }
            case "year":
                from = new Date(today.getFullYear(), 0, 1);
                break;
            default:
                return;
        }
        this.state.filters.date_from = this.formatDate(from);
        this.state.filters.date_to = this.formatDate(today);
        await this.loadData();
    }

    async onFilterChange() {
        await this.loadData();
    }

    async onRefresh() {
        try {
            const data = await this.rpc("/warranty/dashboard/refresh", {
                filters: this.state.filters,
            });
            this.state.data = data;
            this.notification.add("Dashboard refreshed", { type: "success" });
        } catch (e) {
            console.error("Failed to refresh dashboard:", e);
            this.notification.add("Failed to refresh dashboard data", {
                type: "danger",
            });
        }
    }

    async onRebuildCache() {
        try {
            await this.rpc("/warranty/dashboard/rebuild", {});
            const data = await this.rpc("/warranty/dashboard/data", {
                filters: this.state.filters,
            });
            this.state.data = data;
            this.notification.add("Cache rebuilt successfully", {
                type: "success",
            });
        } catch (e) {
            console.error("Failed to rebuild cache:", e);
            this.notification.add("Failed to rebuild cache", {
                type: "danger",
            });
        }
    }

    destroyAllCharts() {
        Object.values(this.charts).forEach((c) => c && c.destroy());
        this.charts = {};
    }

    renderAllCharts() {
        if (this.state.loading) return;
        this.destroyAllCharts();
        this.renderWarrantyStatusChart();
        this.renderClaimsTrendChart();
        this.renderMonthlyComparisonChart();
        this.renderTopProductsChart();
        this.renderTopCustomersChart();
        this.renderClaimTypesChart();
        this.renderWarrantyExpiryChart();
    }

    getChartColors() {
        return {
            primary: "rgba(99, 102, 241, 0.85)",
            primaryLight: "rgba(99, 102, 241, 0.15)",
            success: "rgba(16, 185, 129, 0.85)",
            successLight: "rgba(16, 185, 129, 0.15)",
            warning: "rgba(245, 158, 11, 0.85)",
            warningLight: "rgba(245, 158, 11, 0.15)",
            danger: "rgba(239, 68, 68, 0.85)",
            dangerLight: "rgba(239, 68, 68, 0.15)",
            info: "rgba(6, 182, 212, 0.85)",
            purple: "rgba(139, 92, 246, 0.85)",
            orange: "rgba(249, 115, 22, 0.85)",
            teal: "rgba(20, 184, 166, 0.85)",
            palette: [
                "#6366f1", "#10b981", "#f59e0b", "#ef4444",
                "#06b6d4", "#8b5cf6", "#f97316", "#14b8a6",
                "#ec4899", "#84cc16", "#a855f7", "#0ea5e9",
            ],
        };
    }

    // --- Chart renderers ---

    renderWarrantyStatusChart() {
        const el = this.chartRefs.warrantyStatus.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.warranty_status || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.warrantyStatus = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: d.map((r) => r.label),
                datasets: [
                    {
                        data: d.map((r) => r.value),
                        backgroundColor: c.palette.slice(0, d.length),
                        hoverOffset: 8,
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

    renderClaimsTrendChart() {
        const el = this.chartRefs.claimsTrend.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.claims_trend || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.claimsTrend = new window.Chart(el, {
            type: "line",
            data: {
                labels: d.map((r) => r.period),
                datasets: [
                    {
                        label: "Under Warranty",
                        data: d.map((r) => r.under_warranty || 0),
                        borderColor: c.success,
                        backgroundColor: c.successLight,
                        fill: true,
                        tension: 0.4,
                    },
                    {
                        label: "Out of Warranty",
                        data: d.map((r) => r.out_of_warranty || 0),
                        borderColor: c.danger,
                        backgroundColor: c.dangerLight,
                        fill: true,
                        tension: 0.4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "top" } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    renderMonthlyComparisonChart() {
        const el = this.chartRefs.monthlyComparison.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.monthly_comparison || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.monthlyComparison = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.period),
                datasets: [
                    {
                        label: "New Warranties",
                        data: d.map((r) => r.warranties || 0),
                        backgroundColor: c.primary,
                        borderRadius: 6,
                    },
                    {
                        label: "Claims",
                        data: d.map((r) => r.claims || 0),
                        backgroundColor: c.warning,
                        borderRadius: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    renderTopProductsChart() {
        const el = this.chartRefs.topProducts.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.top_products || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.topProducts = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.name),
                datasets: [
                    {
                        label: "Warranties",
                        data: d.map((r) => r.warranties || 0),
                        backgroundColor: c.primary,
                        borderRadius: 6,
                    },
                    {
                        label: "Claims",
                        data: d.map((r) => r.claims || 0),
                        backgroundColor: c.danger,
                        borderRadius: 6,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: { x: { beginAtZero: true } },
            },
        });
    }

    renderTopCustomersChart() {
        const el = this.chartRefs.topCustomers.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.top_customers || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.topCustomers = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.name),
                datasets: [
                    {
                        label: "Warranties",
                        data: d.map((r) => r.warranties || 0),
                        backgroundColor: c.success,
                        borderRadius: 6,
                    },
                    {
                        label: "Claims",
                        data: d.map((r) => r.claims || 0),
                        backgroundColor: c.warning,
                        borderRadius: 6,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: { x: { beginAtZero: true } },
            },
        });
    }

    renderClaimTypesChart() {
        const el = this.chartRefs.claimTypes.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.claim_types || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.claimTypes = new window.Chart(el, {
            type: "line",
            data: {
                labels: d.map((r) => r.period),
                datasets: [
                    {
                        label: "Repair",
                        data: d.map((r) => r.repair || 0),
                        borderColor: c.primary,
                        backgroundColor: c.primaryLight,
                        fill: true,
                        tension: 0.4,
                    },
                    {
                        label: "Replace",
                        data: d.map((r) => r.replace || 0),
                        borderColor: c.success,
                        backgroundColor: c.successLight,
                        fill: true,
                        tension: 0.4,
                    },
                    {
                        label: "Refund",
                        data: d.map((r) => r.refund || 0),
                        borderColor: c.warning,
                        backgroundColor: c.warningLight,
                        fill: true,
                        tension: 0.4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "top" } },
                scales: {
                    y: { beginAtZero: true, stacked: true },
                    x: { stacked: true },
                },
            },
        });
    }

    renderWarrantyExpiryChart() {
        const el = this.chartRefs.warrantyExpiry.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.warranty_expiry || [];
        if (!d.length) return;
        const c = this.getChartColors();
        this.charts.warrantyExpiry = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.period),
                datasets: [
                    {
                        label: "Expiring",
                        data: d.map((r) => r.count || 0),
                        backgroundColor: c.danger,
                        borderRadius: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    // --- Navigation ---

    async openWarrantyCards(domain) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Warranty Cards",
            res_model: "warranty.card",
            views: [[false, "list"], [false, "form"]],
            domain: domain || [],
            context: {},
        });
    }

    async openActiveWarranties() {
        await this.openWarrantyCards([["state", "=", "active"]]);
    }

    async openExpiredWarranties() {
        await this.openWarrantyCards([
            "|",
            ["state", "=", "expired"],
            ["end_date", "<", new Date().toISOString().slice(0, 10)],
        ]);
    }

    async openClaimedWarranties() {
        await this.openWarrantyCards([["claim_count", ">", 0]]);
    }

    async openNearExpiryWarranties() {
        const today = new Date().toISOString().slice(0, 10);
        const future = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000)
            .toISOString()
            .slice(0, 10);
        await this.openWarrantyCards([
            ["state", "=", "active"],
            ["end_date", ">=", today],
            ["end_date", "<=", future],
        ]);
    }

    async openAllWarranties() {
        await this.openWarrantyCards([]);
    }

    async openWarrantyClaims() {
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Warranty Claims",
            res_model: "warranty.claim",
            views: [[false, "list"], [false, "form"]],
            domain: [],
            context: {},
        });
    }
}

registry
    .category("actions")
    .add("buz_warranty_dashboard", WarrantyDashboard);
