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

export class SalesAnalyticsDashboard extends Component {
    static template = "buz_sales_analytics_dashboard.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        this.chartRefs = {
            revenueTrend: useRef("revenueTrendChart"),
            topCustomers: useRef("topCustomersChart"),
            topProducts: useRef("topProductsChart"),
            salesByCategory: useRef("salesByCategoryChart"),
            salesByPerson: useRef("salesByPersonChart"),
            orderStatus: useRef("orderStatusChart"),
            deliveryStatus: useRef("deliveryStatusChart"),
            forecast: useRef("forecastChart"),
        };
        this.charts = {};

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

        this.state = useState({
            loading: true,
            filters: {
                date_from: this.formatDate(firstDay),
                date_to: this.formatDate(today),
                salesperson_id: "",
                team_id: "",
                category_id: "",
                partner_id: "",
                period_type: "monthly",
            },
            filterOptions: {
                salespersons: [],
                teams: [],
                categories: [],
            },
            display: { controlPanel: {} },
            data: {
                kpi: {},
                revenue_trend: [],
                top_customers: [],
                top_products: [],
                sales_by_category: [],
                sales_by_salesperson: [],
                order_status: [],
                delivery_status: [],
                sales_funnel: [],
                forecast: { historical: [], forecast: [], trend: 0 },
                monthly_comparison: [],
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
            maximumFractionDigits: 2,
        });
    }

    formatCurrency(value) {
        return (value || 0).toLocaleString(undefined, {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    formatPercent(value) {
        return `${(value || 0).toFixed(1)}%`;
    }

    async loadFilterOptions() {
        try {
            const opts = await this.rpc(
                "/sales/analytics/dashboard/filter_options",
                {}
            );
            this.state.filterOptions = opts;
        } catch (e) {
            console.error("Failed to load filter options:", e);
            this.notification.add(
                "Failed to load filter options",
                { type: "danger" }
            );
        }
    }

    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.rpc("/sales/analytics/dashboard/data", {
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

    async onFilterChange() {
        await this.loadData();
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

    async onRefresh() {
        try {
            const data = await this.rpc("/sales/analytics/dashboard/refresh", {
                filters: this.state.filters,
            });
            this.state.data = data;
        } catch (e) {
            console.error("Failed to refresh dashboard:", e);
            this.notification.add(
                "Failed to refresh dashboard data",
                { type: "danger" }
            );
        }
    }

    destroyAllCharts() {
        Object.values(this.charts).forEach((c) => c && c.destroy());
        this.charts = {};
    }

    renderAllCharts() {
        if (this.state.loading) return;
        this.destroyAllCharts();
        this.renderRevenueTrendChart();
        this.renderTopCustomersChart();
        this.renderTopProductsChart();
        this.renderCategoryChart();
        this.renderSalespersonChart();
        this.renderOrderStatusChart();
        this.renderDeliveryStatusChart();
        this.renderForecastChart();
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

    renderRevenueTrendChart() {
        const el = this.chartRefs.revenueTrend.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.revenue_trend || [];
        const c = this.getChartColors();
        this.charts.revenueTrend = new window.Chart(el, {
            type: "line",
            data: {
                labels: d.map((r) => r.period || ""),
                datasets: [
                    {
                        label: "Revenue",
                        data: d.map((r) => r.revenue || 0),
                        borderColor: c.primary,
                        backgroundColor: c.primaryLight,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    },
                    {
                        label: "Orders",
                        data: d.map((r) => r.order_count || 0),
                        borderColor: c.success,
                        backgroundColor: "transparent",
                        borderDash: [5, 5],
                        tension: 0.4,
                        yAxisID: "y1",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { position: "top" } },
                scales: {
                    y: { beginAtZero: true },
                    y1: { position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
                },
            },
        });
    }

    renderTopCustomersChart() {
        const el = this.chartRefs.topCustomers.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.top_customers || [];
        const c = this.getChartColors();
        this.charts.topCustomers = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.partner_name || ""),
                datasets: [
                    {
                        label: "Revenue",
                        data: d.map((r) => r.total_revenue || 0),
                        backgroundColor: c.palette.slice(0, d.length),
                        borderRadius: 6,
                    },
                ],
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: { x: { beginAtZero: true } },
            },
        });
    }

    renderTopProductsChart() {
        const el = this.chartRefs.topProducts.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.top_products || [];
        const c = this.getChartColors();
        this.charts.topProducts = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.product_code || r.product_name || ""),
                datasets: [
                    {
                        label: "Revenue",
                        data: d.map((r) => r.revenue || 0),
                        backgroundColor: c.primary,
                        borderRadius: 6,
                        yAxisID: "y",
                    },
                    {
                        label: "Qty Sold",
                        data: d.map((r) => r.qty_sold || 0),
                        backgroundColor: c.success,
                        borderRadius: 6,
                        yAxisID: "y1",
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "top" } },
                scales: {
                    y: { type: "linear", display: true, position: "left", beginAtZero: true },
                    y1: { type: "linear", display: true, position: "right", beginAtZero: true, grid: { drawOnChartArea: false } },
                },
            },
        });
    }

    renderCategoryChart() {
        const el = this.chartRefs.salesByCategory.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.sales_by_category || [];
        const c = this.getChartColors();
        this.charts.salesByCategory = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: d.map((r) => r.category_name || ""),
                datasets: [
                    {
                        data: d.map((r) => r.revenue || 0),
                        backgroundColor: c.palette.slice(0, d.length),
                        hoverOffset: 8,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right" } },
            },
        });
    }

    renderSalespersonChart() {
        const el = this.chartRefs.salesByPerson.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.sales_by_salesperson || [];
        const c = this.getChartColors();
        this.charts.salesByPerson = new window.Chart(el, {
            type: "bar",
            data: {
                labels: d.map((r) => r.user_name || ""),
                datasets: [
                    {
                        label: "Revenue",
                        data: d.map((r) => r.revenue || 0),
                        backgroundColor: c.primary,
                        borderRadius: 6,
                    },
                    {
                        label: "Target",
                        data: d.map((r) => r.target_amount || 0),
                        type: "line",
                        borderColor: c.danger,
                        backgroundColor: "transparent",
                        borderDash: [5, 5],
                        pointRadius: 5,
                        pointBackgroundColor: c.danger,
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

    renderOrderStatusChart() {
        const el = this.chartRefs.orderStatus.el;
        if (!el || !window.Chart) return;
        const d = (this.state.data.order_status || []).filter((r) => r.count > 0);
        const statusColors = {
            draft: "rgba(156, 163, 175, 0.85)",
            sent: "rgba(59, 130, 246, 0.85)",
            sale: "rgba(16, 185, 129, 0.85)",
            done: "rgba(99, 102, 241, 0.85)",
            cancel: "rgba(239, 68, 68, 0.85)",
            pos_draft: "rgba(245, 158, 11, 0.85)",
            pos_done: "rgba(20, 184, 166, 0.85)",
        };
        this.charts.orderStatus = new window.Chart(el, {
            type: "pie",
            data: {
                labels: d.map((r) => r.label || ""),
                datasets: [
                    {
                        data: d.map((r) => r.count || 0),
                        backgroundColor: d.map(
                            (r) => statusColors[r.state] || "rgba(156, 163, 175, 0.85)"
                        ),
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right" } },
            },
        });
    }

    renderDeliveryStatusChart() {
        const el = this.chartRefs.deliveryStatus.el;
        if (!el || !window.Chart) return;
        const d = (this.state.data.delivery_status || []).filter((r) => r.count > 0);
        const deliveryColors = {
            del_draft: "rgba(156, 163, 175, 0.85)",
            del_confirmed: "rgba(59, 130, 246, 0.85)",
            del_assigned: "rgba(245, 158, 11, 0.85)",
            del_done: "rgba(16, 185, 129, 0.85)",
            del_cancel: "rgba(239, 68, 68, 0.85)",
        };
        this.charts.deliveryStatus = new window.Chart(el, {
            type: "pie",
            data: {
                labels: d.map((r) => r.label || ""),
                datasets: [
                    {
                        data: d.map((r) => r.count || 0),
                        backgroundColor: d.map(
                            (r) => deliveryColors[r.state] || "rgba(156, 163, 175, 0.85)"
                        ),
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: "right" } },
            },
        });
    }

    renderForecastChart() {
        const el = this.chartRefs.forecast.el;
        if (!el || !window.Chart) return;
        const fd = this.state.data.forecast || {};
        const hist = fd.historical || [];
        const fore = fd.forecast || [];
        const c = this.getChartColors();

        const allLabels = [
            ...hist.map((h) => h.period),
            ...fore.map((f) => f.period),
        ];
        const histData = [
            ...hist.map((h) => h.revenue),
            ...fore.map(() => null),
        ];
        const foreData = [
            ...hist.map(() => null),
            ...fore.map((f) => f.predicted),
        ];
        if (hist.length > 0 && fore.length > 0) {
            histData[hist.length - 1] = hist[hist.length - 1].revenue;
            foreData[hist.length - 1] = hist[hist.length - 1].revenue;
        }
        const upperData = [
            ...hist.map(() => null),
            ...fore.map((f) => f.upper_bound),
        ];
        const lowerData = [
            ...hist.map(() => null),
            ...fore.map((f) => f.lower_bound),
        ];

        this.charts.forecast = new window.Chart(el, {
            type: "line",
            data: {
                labels: allLabels,
                datasets: [
                    {
                        label: "Actual Revenue",
                        data: histData,
                        borderColor: c.primary,
                        backgroundColor: c.primaryLight,
                        fill: false,
                        tension: 0.4,
                        pointRadius: 4,
                    },
                    {
                        label: "Forecast",
                        data: foreData,
                        borderColor: c.warning,
                        backgroundColor: "transparent",
                        borderDash: [6, 3],
                        tension: 0.4,
                        pointRadius: 4,
                    },
                    {
                        label: "Upper Bound",
                        data: upperData,
                        borderColor: "transparent",
                        backgroundColor: c.warningLight,
                        fill: "+1",
                        pointRadius: 0,
                    },
                    {
                        label: "Lower Bound",
                        data: lowerData,
                        borderColor: "transparent",
                        backgroundColor: "transparent",
                        fill: false,
                        pointRadius: 0,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: "top" },
                    tooltip: {
                        callbacks: {
                            label(ctx) {
                                if (ctx.dataset.label === "Upper Bound" || ctx.dataset.label === "Lower Bound") return null;
                                return `${ctx.dataset.label}: ${ctx.parsed.y?.toLocaleString() || 0}`;
                            },
                        },
                    },
                },
                scales: { y: { beginAtZero: true } },
            },
        });
    }

    get funnelMaxValue() {
        const stages = this.state.data.sales_funnel || [];
        if (!stages.length) return 1;
        return Math.max(...stages.map((s) => s.value || 0)) || 1;
    }

    get funnelWidthPercent() {
        return (value) => {
            const maxVal = this.funnelMaxValue;
            return Math.max((value / maxVal) * 100, 15);
        };
    }

    get kpiGrowthClass() {
        const rate = (this.state.data.kpi || {}).growth_rate || 0;
        if (rate > 0) return "kpi-positive";
        if (rate < 0) return "kpi-negative";
        return "";
    }

    get kpiGrowthIcon() {
        const rate = (this.state.data.kpi || {}).growth_rate || 0;
        if (rate > 0) return "fa-arrow-up";
        if (rate < 0) return "fa-arrow-down";
        return "fa-minus";
    }

    async openOrders() {
        const domain = [["state", "=", "sale"]];
        if (this.state.filters.date_from) {
            domain.push(["date_order", ">=", this.state.filters.date_from]);
        }
        if (this.state.filters.date_to) {
            domain.push(["date_order", "<=", this.state.filters.date_to + " 23:59:59"]);
        }
        await this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sale Orders",
            res_model: "sale.order",
            views: [[false, "list"], [false, "form"]],
            domain: domain,
            context: {},
        });
    }

    async openInvoices() {
        await this.action.doAction("account.action_move_out_invoice_type", {
            additionalContext: {
                search_default_outstanding: true,
            },
        });
    }
}

registry.category("actions").add("buz_sales_analytics_dashboard", SalesAnalyticsDashboard);
