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
        this.user = useService("user");

        this.rootRef = useRef("root");
        this.chartRefs = {
            warrantyStatus: useRef("warrantyStatusChart"),
            claimsTrend: useRef("claimsTrendChart"),
        };
        this.charts = {};
        this.sparkCharts = [];

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

    get userName() {
        return (this.user && this.user.name) || "Admin";
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

    nearExpiryPercent() {
        const kpi = this.state.data.kpi || {};
        const total = kpi.total_warranties || 0;
        if (!total) return "0.0%";
        return this.formatPercent(((kpi.near_expiry_warranties || 0) / total) * 100);
    }

    // --- Derived rows for template ---

    statusLegend() {
        const rows = this.state.data.warranty_status || [];
        const total = rows.reduce((s, r) => s + (r.value || 0), 0) || 1;
        const colorMap = {
            active: "#3b82f6",
            expired: "#ef4444",
            claimed: "#f59e0b",
            "near expiry": "#06b6d4",
            draft: "#94a3b8",
            cancelled: "#64748b",
        };
        return rows.map((r) => ({
            label: r.label,
            value: r.value || 0,
            pct: this.formatPercent(((r.value || 0) / total) * 100),
            color: colorMap[(r.label || "").toLowerCase()] || r.color || "#6366f1",
        }));
    }

    _rankRows(rows) {
        const data = (rows || []).slice(0, 10);
        const total = data.reduce((s, r) => s + (r.warranties || 0), 0) || 1;
        const max = Math.max(...data.map((r) => r.warranties || 0), 1);
        return data.map((r, i) => ({
            rank: i + 1,
            name: r.name,
            value: r.warranties || 0,
            barPct: Math.round(((r.warranties || 0) / max) * 100),
            sharePct: this.formatPercent(((r.warranties || 0) / total) * 100),
        }));
    }

    topProductRows() {
        return this._rankRows(this.state.data.top_products);
    }

    topCustomerRows() {
        return this._rankRows(this.state.data.top_customers);
    }

    // --- Data loading ---

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

    // --- Charts ---

    destroyAllCharts() {
        Object.values(this.charts).forEach((c) => c && c.destroy());
        this.charts = {};
        this.sparkCharts.forEach((c) => c && c.destroy());
        this.sparkCharts = [];
    }

    renderAllCharts() {
        if (this.state.loading) return;
        this.destroyAllCharts();
        this.renderWarrantyStatusChart();
        this.renderClaimsTrendChart();
        this.renderSparklines();
    }

    renderWarrantyStatusChart() {
        const el = this.chartRefs.warrantyStatus.el;
        if (!el || !window.Chart) return;
        const legend = this.statusLegend();
        if (!legend.length) return;
        this.charts.warrantyStatus = new window.Chart(el, {
            type: "doughnut",
            data: {
                labels: legend.map((r) => r.label),
                datasets: [
                    {
                        data: legend.map((r) => r.value),
                        backgroundColor: legend.map((r) => r.color),
                        borderWidth: 2,
                        borderColor: "#ffffff",
                        hoverOffset: 6,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "68%",
                plugins: {
                    legend: { display: false },
                },
            },
        });
    }

    renderClaimsTrendChart() {
        const el = this.chartRefs.claimsTrend.el;
        if (!el || !window.Chart) return;
        const d = this.state.data.claims_trend || [];
        if (!d.length) return;
        const ctx = el.getContext("2d");
        const gradient = ctx.createLinearGradient(0, 0, 0, 300);
        gradient.addColorStop(0, "rgba(139, 92, 246, 0.35)");
        gradient.addColorStop(1, "rgba(139, 92, 246, 0.02)");
        this.charts.claimsTrend = new window.Chart(el, {
            type: "line",
            data: {
                labels: d.map((r) => r.period),
                datasets: [
                    {
                        label: "Claims",
                        data: d.map(
                            (r) => (r.under_warranty || 0) + (r.out_of_warranty || 0)
                        ),
                        borderColor: "#8b5cf6",
                        backgroundColor: gradient,
                        pointBackgroundColor: "#8b5cf6",
                        pointBorderColor: "#ffffff",
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        fill: true,
                        tension: 0.4,
                        borderWidth: 2.5,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: "rgba(148, 163, 184, 0.15)" },
                        ticks: { color: "#94a3b8" },
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: "#94a3b8" },
                    },
                },
            },
        });
    }

    renderSparklines() {
        const root = this.rootRef.el;
        if (!root || !window.Chart) return;
        const monthly = this.state.data.monthly_comparison || [];
        const trend = this.state.data.claims_trend || [];
        const series = {
            warranties: monthly.map((r) => r.warranties || 0),
            claims: trend.map(
                (r) => (r.under_warranty || 0) + (r.out_of_warranty || 0)
            ),
        };
        root.querySelectorAll("canvas.o_wd_spark").forEach((el) => {
            const color = el.dataset.color || "#6366f1";
            const data = series[el.dataset.series] || [];
            if (data.length < 2) {
                el.style.display = "none";
                return;
            }
            el.style.display = "";
            el.width = el.clientWidth || 220;
            el.height = el.clientHeight || 40;
            const ctx = el.getContext("2d");
            const gradient = ctx.createLinearGradient(0, 0, 0, 40);
            gradient.addColorStop(0, color + "33");
            gradient.addColorStop(1, color + "05");
            this.sparkCharts.push(
                new window.Chart(el, {
                    type: "line",
                    data: {
                        labels: data.map((_, i) => i),
                        datasets: [
                            {
                                data,
                                borderColor: color,
                                backgroundColor: gradient,
                                fill: true,
                                tension: 0.45,
                                borderWidth: 1.5,
                                pointRadius: 0,
                            },
                        ],
                    },
                    options: {
                        responsive: false,
                        maintainAspectRatio: false,
                        events: [],
                        plugins: { legend: { display: false }, tooltip: { enabled: false } },
                        scales: {
                            x: { display: false },
                            y: { display: false },
                        },
                    },
                })
            );
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

    async openWarrantyCard(id) {
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "warranty.card",
            res_id: id,
            views: [[false, "form"]],
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
            name: "Claims",
            res_model: "service.receipt",
            views: [[false, "list"], [false, "form"]],
            domain: [["service_case_type", "=", "replacement"]],
            context: {default_service_case_type: "replacement"},
        });
    }
}

registry
    .category("actions")
    .add("buz_warranty_dashboard", WarrantyDashboard);
