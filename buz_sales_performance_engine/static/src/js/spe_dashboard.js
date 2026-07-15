/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

const SERIES = [
    { key: "so", label: "Sales Order", color: "#3b82f6" },
    { key: "delivery", label: "Delivery Order", color: "#8b5cf6" },
    { key: "invoice", label: "Invoice", color: "#f59e0b" },
    { key: "payment", label: "Payment", color: "#10b981" },
];

class SpeDashboard extends Component {
    static template = "buz_sales_performance_engine.Dashboard";

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        this.chartRefs = {
            trend: useRef("trendChart"),
            byCompany: useRef("byCompanyChart"),
            topCustomers: useRef("topCustomersChart"),
            byCategory: useRef("byCategoryChart"),
            sparkSo: useRef("sparkSo"),
            sparkDelivery: useRef("sparkDelivery"),
            sparkInvoice: useRef("sparkInvoice"),
            sparkPayment: useRef("sparkPayment"),
        };
        this.charts = {};
        this.palette = ["#3b82f6", "#8b5cf6", "#f59e0b", "#10b981", "#f43f5e",
                        "#0ea5e9", "#a855f7", "#f97316", "#64748b"];

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

        this.state = useState({
            loading: true,
            filters: {
                company_id: "",
                period: "this_month",
                date_from: this._fmt(firstDay),
                date_to: this._fmt(today),
                team_id: "",
                salesperson_id: "",
                partner_id: "",
                source: "",
            },
            options: { companies: [], teams: [], salespersons: [], partners: [] },
            kpi: {}, kpiPrev: {}, funnel: [], comparison: {},
            salespersonRows: [],
            followups: [],
            activeTab: "so_follow_up",
        });

        onWillStart(async () => {
            try { await loadJS("/web/static/lib/Chart/Chart.js"); }
            catch (e) { console.warn("Chart.js already loaded"); }
            await this.loadOptions();
            await this.loadAll();
        });
        onMounted(() => this.renderCharts());
        onPatched(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    // ------------------------------------------------------------------
    // Formatting helpers
    // ------------------------------------------------------------------
    _fmt(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${day}`;
    }
    fmtMoney(v) { return (v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    fmtNum(v) { return (v || 0).toLocaleString(undefined, {maximumFractionDigits: 0}); }
    fmtPct(v) { return `${(v || 0).toFixed(1)}%`; }
    cap100(v) { return Math.min(v || 0, 100); }
    fmtCompact(v) {
        const n = v || 0;
        const abs = Math.abs(n);
        if (abs >= 1e9) { return (n / 1e9).toFixed(2) + "B"; }
        if (abs >= 1e6) { return (n / 1e6).toFixed(2) + "M"; }
        if (abs >= 1e3) { return (n / 1e3).toFixed(1) + "K"; }
        return n.toFixed(0);
    }

    kpiAmount(key) {
        return ((this.state.kpi[key] || {}).amount) || 0;
    }
    kpiCount(key) {
        return ((this.state.kpi[key] || {}).count) || 0;
    }
    delta(key) {
        const cur = ((this.state.kpi[key] || {}).amount) || 0;
        const prev = ((this.state.kpiPrev[key] || {}).amount) || 0;
        if (!prev) { return null; }
        return ((cur - prev) / Math.abs(prev)) * 100.0;
    }
    fmtDelta(key) {
        const d = this.delta(key);
        if (d === null) { return "—"; }
        const arrow = d >= 0 ? "▲" : "▼";
        return `${arrow} ${Math.abs(d).toFixed(1)}%`;
    }
    deltaClass(key, invert) {
        const d = this.delta(key);
        if (d === null) { return "spe-delta"; }
        const good = invert ? d < 0 : d >= 0;
        return good ? "spe-delta spe-up" : "spe-delta spe-down";
    }
    compDelta(key) {
        return ((this.state.comparison[key] || {}).delta) || 0;
    }
    compDeltaClass(key) {
        return this.compDelta(key) >= 0 ? "spe-delta spe-up" : "spe-delta spe-down";
    }
    fmtCompDelta(key) {
        const d = this.compDelta(key);
        return `${d >= 0 ? "▲" : "▼"} ${Math.abs(d).toFixed(1)}%`;
    }
    funnelWidth(i) {
        const funnel = this.state.funnel || [];
        const max = Math.max(...funnel.map(s => Math.abs(s.amount)), 1);
        const amount = Math.abs((funnel[i] || {}).amount || 0);
        return Math.max(18, (amount / max) * 100);
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------
    async loadOptions() {
        try {
            const opts = await this.rpc("/spe/dashboard/filter_options", {});
            this.state.options = Object.assign(
                {companies: [], teams: [], salespersons: [], partners: []},
                opts || {});
        } catch (e) {
            this.notification.add("Failed to load filter options", {type: "danger"});
        }
    }

    async loadAll() {
        this.state.loading = true;
        try {
            const f = this.state.filters;
            const [overview, charts, spRows, followups] = await Promise.all([
                this.rpc("/spe/dashboard/overview", {filters: f}),
                this.rpc("/spe/dashboard/charts", {filters: f}),
                this.rpc("/spe/dashboard/salesperson_table", {filters: f}),
                this.rpc("/spe/dashboard/followups", {filters: f, kind: this.state.activeTab}),
            ]);
            this.state.kpi = (overview || {}).kpi || {};
            this.state.kpiPrev = (overview || {}).kpi_prev || {};
            this.state.funnel = Array.isArray((overview || {}).funnel)
                ? overview.funnel : [];
            this.state.comparison = (overview || {}).comparison || {};
            this._spark = (overview || {}).spark || {};
            this._charts = charts || {};
            this.state.salespersonRows = Array.isArray(spRows) ? spRows : [];
            this.state.followups = Array.isArray(followups) ? followups : [];
        } catch (e) {
            console.error(e);
            this.notification.add("Failed to load dashboard data", {type: "danger"});
        } finally {
            this.state.loading = false;
        }
    }

    async applyFilters() { await this.loadAll(); }

    onFilter(ev) {
        const el = ev.target;
        this.state.filters[el.name] = el.value;
        if (el.name === "date_from" || el.name === "date_to") {
            this.state.filters.period = "custom";
        }
    }

    onPeriod(ev) {
        const period = ev.target.value;
        this.state.filters.period = period;
        const today = new Date();
        let from = null, to = today;
        if (period === "this_month") {
            from = new Date(today.getFullYear(), today.getMonth(), 1);
        } else if (period === "last_month") {
            from = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            to = new Date(today.getFullYear(), today.getMonth(), 0);
        } else if (period === "this_quarter") {
            from = new Date(today.getFullYear(), Math.floor(today.getMonth() / 3) * 3, 1);
        } else if (period === "this_year") {
            from = new Date(today.getFullYear(), 0, 1);
        }
        if (from) {
            this.state.filters.date_from = this._fmt(from);
            this.state.filters.date_to = this._fmt(to);
        }
    }

    async setSource(src) {
        this.state.filters.source = src;
        await this.loadAll();
    }

    async setTab(tab) {
        this.state.activeTab = tab;
        try {
            const rows = await this.rpc("/spe/dashboard/followups", {
                filters: this.state.filters, kind: tab,
            });
            this.state.followups = Array.isArray(rows) ? rows : [];
        } catch (e) {
            this.notification.add("Failed to load list", {type: "danger"});
        }
    }

    drill(kind) {
        this.rpc("/spe/dashboard/action_drill", {filters: this.state.filters, kind})
            .then((act) => {
                if (act && act.res_model) { this.action.doAction(act); }
            });
    }

    openRecord(row) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: row.res_model,
            res_id: row.id,
            view_mode: "form",
            views: [[false, "form"]],
        });
    }

    // ------------------------------------------------------------------
    // Charts
    // ------------------------------------------------------------------
    renderCharts() {
        this.destroyCharts();
        if (this.state.loading || !this._charts) { return; }
        this._renderTrend();
        this._renderByCompany();
        this._renderTopCustomers();
        this._renderByCategory();
        this._renderSparks();
    }

    _mergeLabels(seriesMap) {
        const labels = new Set();
        for (const s of SERIES) {
            for (const r of (seriesMap[s.key] || [])) {
                if (r.key) { labels.add(r.key); }
            }
        }
        return [...labels].sort();
    }

    _seriesData(rows, labels) {
        const byKey = Object.fromEntries((rows || []).map(r => [r.key, r.amount]));
        return labels.map(l => byKey[l] || 0);
    }

    _renderTrend() {
        const trend = this._charts.trend || {};
        const labels = this._mergeLabels(trend);
        const shortLabels = labels.map(l =>
            trend.bucket === "month" ? l.slice(0, 7) : l.slice(5));
        this._chart("trend", {
            type: "line",
            data: {
                labels: shortLabels,
                datasets: SERIES.map(s => ({
                    label: s.label,
                    data: this._seriesData(trend[s.key], labels),
                    borderColor: s.color,
                    backgroundColor: s.color,
                    tension: 0.35, pointRadius: 2, borderWidth: 2,
                })),
            },
            options: this._opts(),
        });
    }

    _renderByCompany() {
        const rows = this._charts.by_company || [];
        this._chart("byCompany", {
            type: "bar",
            data: {
                labels: rows.map(r => r.name),
                datasets: SERIES.map(s => ({
                    label: s.label,
                    data: rows.map(r => r[s.key] || 0),
                    backgroundColor: s.color,
                    borderRadius: 3,
                })),
            },
            options: this._opts(),
        });
    }

    _renderTopCustomers() {
        const rows = this._charts.top_customers || [];
        this._chart("topCustomers", {
            type: "bar",
            data: {
                labels: rows.map(r => r.name),
                datasets: [{
                    label: "Sales Order",
                    data: rows.map(r => r.amount),
                    backgroundColor: "#3b82f6",
                    borderRadius: 3,
                }],
            },
            options: {
                ...this._opts(false),
                indexAxis: "y",
                scales: {
                    x: {grid: {color: "rgba(0,0,0,0.05)"},
                        ticks: {callback: (v) => this.fmtCompact(v)}},
                    y: {grid: {display: false}},
                },
            },
        });
    }

    _renderByCategory() {
        const rows = this._charts.by_category || [];
        this._chart("byCategory", {
            type: "doughnut",
            data: {
                labels: rows.map(r => r.name),
                datasets: [{
                    data: rows.map(r => r.amount),
                    backgroundColor: this.palette,
                    borderColor: "#ffffff", borderWidth: 2, hoverOffset: 6,
                }],
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: "62%",
                plugins: {legend: {position: "right",
                                   labels: {boxWidth: 10, usePointStyle: true}}},
            },
        });
    }

    _renderSparks() {
        const spark = this._spark || {};
        const map = {
            sparkSo: {rows: spark.so, color: "#3b82f6"},
            sparkDelivery: {rows: spark.delivery, color: "#8b5cf6"},
            sparkInvoice: {rows: spark.invoice, color: "#f59e0b"},
            sparkPayment: {rows: spark.payment, color: "#10b981"},
        };
        for (const [ref, cfg] of Object.entries(map)) {
            const rows = cfg.rows || [];
            let cum = 0;
            const data = rows.filter(r => r.key).map(r => (cum += r.amount));
            this._chart(ref, {
                type: "line",
                data: {
                    labels: data.map((_, i) => i + 1),
                    datasets: [{
                        data,
                        borderColor: cfg.color,
                        backgroundColor: cfg.color + "22",
                        fill: true, tension: 0.4, pointRadius: 0, borderWidth: 1.5,
                    }],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {legend: {display: false}, tooltip: {enabled: false}},
                    scales: {x: {display: false}, y: {display: false}},
                },
            });
        }
    }

    _opts(legend = true) {
        return {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {legend: {display: legend,
                               labels: {boxWidth: 12, usePointStyle: true}}},
            scales: {
                y: {grid: {color: "rgba(0,0,0,0.05)"},
                    ticks: {callback: (v) => this.fmtCompact(v)}},
                x: {grid: {display: false}},
            },
        };
    }

    _chart(ref, config) {
        const el = this.chartRefs[ref] && this.chartRefs[ref].el;
        if (!el) return;
        this.charts[ref] = new Chart(el.getContext("2d"), config);
    }

    destroyCharts() {
        Object.values(this.charts).forEach(c => { try { c.destroy(); } catch (e) {} });
        this.charts = {};
    }
}

registry.category("actions").add("buz_sales_performance_engine", SpeDashboard);
export default SpeDashboard;
