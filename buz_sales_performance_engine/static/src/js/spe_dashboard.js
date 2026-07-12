/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";

class SpeDashboard extends Component {
    static template = "buz_sales_performance_engine.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");

        this.chartRefs = {
            salesVsTarget: useRef("salesVsTargetChart"),
            daily: useRef("dailyChart"),
            monthly: useRef("monthlyChart"),
            delivery: useRef("deliveryChart"),
            invoiceRefund: useRef("invoiceRefundChart"),
            topCustomers: useRef("topCustomersChart"),
            topProducts: useRef("topProductsChart"),
            topSalespersons: useRef("topSalespersonsChart"),
            topTeams: useRef("topTeamsChart"),
        };
        this.charts = {};
        this.palette = ["#0d9488", "#6366f1", "#f59e0b", "#f43f5e", "#10b981",
                        "#0ea5e9", "#a855f7", "#f97316"];

        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);

        this.state = useState({
            loading: true,
            filters: {
                date_from: this._fmt(firstDay),
                date_to: this._fmt(today),
                salesperson_id: "",
                team_id: "",
                partner_id: "",
                product_id: "",
                categ_id: "",
                company_id: "",
                source: "",
            },
            options: { salespersons: [], teams: [], partners: [], products: [], categories: [], companies: [] },
            kpi: {},
            kpiPrev: {},
            leaderboardSalespersons: [],
            leaderboardTeams: [],
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

    _fmt(d) {
        const y = d.getFullYear();
        const m = String(d.getMonth() + 1).padStart(2, "0");
        const day = String(d.getDate()).padStart(2, "0");
        return `${y}-${m}-${day}`;
    }
    fmtNum(v) { return (v || 0).toLocaleString(undefined, {maximumFractionDigits: 0}); }
    fmtMoney(v) { return (v || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
    fmtPct(v) { return `${(v || 0).toFixed(1)}%`; }
    cap100(v) { return Math.min(v || 0, 100); }
    rankClass(i) { return "spe-rank spe-rank-" + Math.min(i + 1, 4); }

    async loadOptions() {
        try {
            this.state.options = await this.rpc("/spe/dashboard/filter_options", {});
        } catch (e) {
            this.notification.add("Failed to load filter options", {type: "danger"});
        }
    }

    async loadAll() {
        this.state.loading = true;
        try {
            const [kpi, kpiPrev, daily, monthly, delivery, invoiceRefund,
                   topCustomers, topProducts, topSalespersons, topTeams,
                   lbSalespersons, lbTeams] = await Promise.all([
                this.rpc("/spe/dashboard/kpi", {filters: this.state.filters}),
                this._loadPrevKpi(),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "daily"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "monthly"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "delivery_trend"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "monthly"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "top", field: "partner_id"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "top", field: "product_id"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "top", field: "salesperson_id"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "top", field: "team_id"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "leaderboard", field: "salesperson_id"}),
                this.rpc("/spe/dashboard/series", {filters: this.state.filters, kind: "leaderboard", field: "team_id"}),
            ]);
            this.state.kpi = kpi;
            this.state.kpiPrev = kpiPrev;
            this._daily = daily;
            this._monthly = monthly;
            this._delivery = delivery;
            this._invoiceRefund = invoiceRefund;
            this._topCustomers = topCustomers;
            this._topProducts = topProducts;
            this._topSalespersons = topSalespersons;
            this._topTeams = topTeams;
            this.state.leaderboardSalespersons = lbSalespersons;
            this.state.leaderboardTeams = lbTeams;
        } catch (e) {
            this.notification.add("Failed to load dashboard data", {type: "danger"});
        } finally {
            this.state.loading = false;
        }
    }

    async _loadPrevKpi() {
        const f = this.state.filters;
        if (!f.date_from || !f.date_to) { return {}; }
        const from = new Date(f.date_from);
        const to = new Date(f.date_to);
        const spanMs = to.getTime() - from.getTime() + 24 * 3600 * 1000;
        const prevTo = new Date(from.getTime() - 24 * 3600 * 1000);
        const prevFrom = new Date(from.getTime() - spanMs);
        try {
            return await this.rpc("/spe/dashboard/kpi", {
                filters: {...f, date_from: this._fmt(prevFrom), date_to: this._fmt(prevTo)},
            });
        } catch (e) { return {}; }
    }

    delta(field) {
        const cur = (this.state.kpi || {})[field] || 0;
        const prev = (this.state.kpiPrev || {})[field] || 0;
        if (!prev) { return null; }
        return ((cur - prev) / Math.abs(prev)) * 100.0;
    }

    fmtDelta(field) {
        const d = this.delta(field);
        if (d === null) { return ""; }
        const arrow = d >= 0 ? "▲" : "▼";
        return `${arrow} ${Math.abs(d).toFixed(1)}%`;
    }

    deltaClass(field) {
        const d = this.delta(field);
        if (d === null) { return "spe-delta"; }
        return d >= 0 ? "spe-delta spe-up" : "spe-delta spe-down";
    }

    async applyFilters() { await this.loadAll(); }
    async onFilter(ev) {
        const el = ev.target;
        this.state.filters[el.name] = el.value;
    }
    async setSource(src) {
        this.state.filters.source = src;
        await this.loadAll();
    }

    drill(kind) {
        this.rpc("/spe/dashboard/action_drill", {filters: this.state.filters, kind}).then((act) => {
            if (act && act.res_model) { this.action.doAction(act); }
        });
    }

    renderCharts() {
        this.destroyCharts();
        this._chart("salesVsTarget", "bar", {
            labels: (this._monthly || []).map(r => r.label),
            datasets: [
                {label: "Net Sales", data: (this._monthly || []).map(r => r.net), backgroundColor: "#0d9488", borderRadius: 4},
                {label: "Invoice", data: (this._monthly || []).map(r => r.invoice), backgroundColor: "#67e8f9", borderRadius: 4},
                {label: "Refund", data: (this._monthly || []).map(r => r.refund), backgroundColor: "#fda4af", borderRadius: 4},
            ],
        });
        this._chart("daily", "line", {
            labels: (this._daily || []).map(r => r.label),
            datasets: [{label: "Daily Net Sales", data: (this._daily || []).map(r => r.net),
                        borderColor: "#0d9488", backgroundColor: "rgba(13,148,136,0.12)",
                        fill: true, tension: 0.35, pointRadius: 2, pointBackgroundColor: "#0d9488"}],
        });
        this._chart("monthly", "bar", {
            labels: (this._monthly || []).map(r => r.label),
            datasets: [{label: "Monthly Net Sales", data: (this._monthly || []).map(r => r.net),
                        backgroundColor: "#0d9488", borderRadius: 4}],
        });
        this._chart("delivery", "line", {
            labels: (this._delivery || []).map(r => r.label),
            datasets: [
                {label: "Delivered Qty", data: (this._delivery || []).map(r => r.delivered),
                 borderColor: "#10b981", backgroundColor: "#10b981", tension: 0.35, pointRadius: 2},
                {label: "Invoiced Qty", data: (this._delivery || []).map(r => r.invoiced),
                 borderColor: "#6366f1", backgroundColor: "#6366f1", tension: 0.35, pointRadius: 2},
            ],
        });
        this._chart("invoiceRefund", "bar", {
            labels: (this._invoiceRefund || []).map(r => r.label),
            datasets: [
                {label: "Invoice", data: (this._invoiceRefund || []).map(r => r.invoice), backgroundColor: "#10b981", borderRadius: 4},
                {label: "Refund", data: (this._invoiceRefund || []).map(r => r.refund), backgroundColor: "#f43f5e", borderRadius: 4},
            ],
        });
        this._pie("topCustomers", this._topCustomers);
        this._pie("topProducts", this._topProducts);
        this._pie("topSalespersons", this._topSalespersons);
        this._pie("topTeams", this._topTeams);
    }

    _chart(ref, type, data) {
        const el = this.chartRefs[ref] && this.chartRefs[ref].el;
        if (!el) return;
        this.charts[ref] = new Chart(el.getContext("2d"), {
            type, data,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {legend: {labels: {boxWidth: 12, usePointStyle: true}}},
                scales: type === "doughnut" ? {} : {
                    y: {grid: {color: "rgba(0,0,0,0.05)"}},
                    x: {grid: {display: false}},
                },
            },
        });
    }
    _pie(ref, data) {
        const el = this.chartRefs[ref] && this.chartRefs[ref].el;
        if (!el) return;
        const items = data || [];
        this.charts[ref] = new Chart(el.getContext("2d"), {
            type: "doughnut",
            data: {
                labels: items.map(r => r.name),
                datasets: [{data: items.map(r => r.value),
                            backgroundColor: this.palette,
                            borderColor: "#ffffff", borderWidth: 2, hoverOffset: 6}],
            },
            options: {
                responsive: true, maintainAspectRatio: false, cutout: "62%",
                plugins: {legend: {position: "right", labels: {boxWidth: 10, usePointStyle: true}}},
            },
        });
    }
    destroyCharts() {
        Object.values(this.charts).forEach(c => { try { c.destroy(); } catch (e) {} });
        this.charts = {};
    }
}

registry.category("actions").add("buz_sales_performance_engine", SpeDashboard);
export default SpeDashboard;
