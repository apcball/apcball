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
            period: 'month',
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
                recent_claims: [],
            },
        });

        onWillStart(async () => {
            try {
                await loadJS("/web/static/lib/Chart/Chart.js");
            } catch (e) {
                console.warn("Chart.js already loaded");
            }
            await Promise.all([this.loadFilterOptions(), this.loadData()]);
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
        return this.formatPercent(this.nearExpiryValue());
    }

    nearExpiryValue() {
        const kpi = this.state.data.kpi || {};
        const total = kpi.total_warranties || 0;
        return total ? ((kpi.near_expiry_warranties || 0) / total) * 100 : 0;
    }

    // --- Derived rows for template ---

    statusLegend() {
        const rows = this.state.data.warranty_status || [];
        const total = rows.reduce((s, r) => s + (r.value || 0), 0) || 1;
        const colorMap = {
            active: "#10c494",
            expired: "#ef4444",
            claimed: "#f59e0b",
            "near expiry": "#ffba24",
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
        const rows = (this.state.data.top_products || []).slice(0, 5);
        const max = Math.max(...rows.map((r) => r.claims || 0), 1);
        return rows.map((r, i) => ({...r, rank: i + 1, value: r.claims,
            barPct: (r.claims || 0) / max * 100}));
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
            const [data, details] = await Promise.all([
                this.rpc("/warranty/dashboard/data", {filters: this.state.filters}),
                this.orm.call('warranty.dashboard', 'get_dashboard_details', [this.state.filters]),
            ]);
            Object.assign(data, details);
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
            case "today":
                from = new Date(today);
                break;
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
        this.state.period = period;
        this.state.filters.date_to = this.formatDate(today);
        await this.loadData();
    }

    async onFilterChange() {
        this.state.period = '';
        await this.loadData();
    }

    async onRefresh() {
        this.state.loading = true;
        try {
            const [data, details] = await Promise.all([
                this.rpc("/warranty/dashboard/refresh", {filters: this.state.filters}),
                this.orm.call('warranty.dashboard', 'get_dashboard_details', [this.state.filters]),
            ]);
            Object.assign(data, details);
            this.state.data = data;
            this.notification.add("Dashboard refreshed", { type: "success" });
        } catch (e) {
            console.error("Failed to refresh dashboard:", e);
            this.notification.add("Failed to refresh dashboard data", {
                type: "danger",
            });
        } finally {
            this.state.loading = false;
        }
    }

    progress(value) {
        return Math.min(100, Math.max(0, Number(value) || 0));
    }

    displayDate(value) {
        return value ? value.split('-').reverse().join('/') : '—';
    }

    warrantyStatus(row) {
        if (row.state === 'active' && row.end_date && row.days_remaining >= 0 && row.days_remaining <= 30) {
            return {key: 'near', label: 'Near Expiry'};
        }
        return {key: row.state, label: {active: 'Active', expired: 'Expired', draft: 'Draft', cancelled: 'Cancelled'}[row.state] || row.state};
    }

    async openClaim(id) {
        await this.action.doAction({type: 'ir.actions.act_window', res_model: 'service.receipt',
            res_id: id, views: [[false, 'form']]});
    }

    exportDashboard() {
        const rows = [['Metric', 'Value'],
            ['Total Warranties', this.state.data.kpi.total_warranties || 0],
            ['Active Warranties', this.state.data.kpi.active_warranties || 0],
            ['Expired Warranties', this.state.data.kpi.expired_warranties || 0],
            ['Near Expiry (30 Days)', this.state.data.kpi.near_expiry_warranties || 0],
            ['Claims This Month', this.state.data.kpi.claims_this_month || 0],
            [], ['Date From', this.state.filters.date_from], ['Date To', this.state.filters.date_to],
            [], ['Recent Warranty', 'Customer', 'Product', 'Start', 'End', 'Status'],
            ...(this.state.data.recent_warranties || []).map((r) => [r.name, r.partner_name, r.product_name, r.start_date, r.end_date, this.warrantyStatus(r).label]),
            [], ['Recent Claim', 'Date', 'Customer', 'Product', 'Status'],
            ...(this.state.data.recent_claims || []).map((r) => [r.name, r.date, r.partner_name, r.product_name, r.state_label])];
        const csv = rows.map((row) => row.map((value) => {
            let text = String(value ?? '');
            if (/^[=+@\-\t\r]/.test(text)) text = "'" + text;
            return '"' + text.replace(/"/g, '""') + '"';
        }).join(',')).join('\r\n');
        const url = URL.createObjectURL(new Blob(['\ufeff', csv], {type: 'text/csv;charset=utf-8;'}));
        const link = document.createElement('a');
        link.href = url;
        link.download = `warranty-dashboard-${this.formatDate(new Date())}.csv`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
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
        gradient.addColorStop(0, "rgba(47, 123, 255, 0.30)");
        gradient.addColorStop(1, "rgba(47, 123, 255, 0.02)");
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
                        borderColor: "#2f7bff",
                        backgroundColor: gradient,
                        pointBackgroundColor: "#2f7bff",
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
