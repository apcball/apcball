/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { download } from "@web/core/network/download";
import { Component, onWillStart, useState } from "@odoo/owl";
import { ChartCard } from "./chart_card";

const PALETTE = ["#0a6ed1", "#e9730c", "#107e3e", "#7858ff", "#bb0000", "#5b738b", "#2ab1b9", "#c5a100"];
const POSTED = "#107e3e";
const PLANNED = "#0a6ed1";
const DRAFT = "#c5a100";
const EXCEPTION = "#bb0000";

function today() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}

export class AssetDashboard extends Component {
    static template = "buz_asset_management.AssetDashboard";
    static components = { ChartCard };
    static props = ["*"];

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: null,
            data: null,
            moreOpen: false,
            filters: {
                company_ids: [],
                as_of: today(),
                department_id: false,
                category_id: false,
                location_id: false,
                operational_state: false,
            },
        });
        this.debouncedLoad = useDebounced(() => this.load(), 300);
        onWillStart(() => this.load());
    }

    // ---------------------------------------------------------------- data
    get requestFilters() {
        return { ...this.state.filters };
    }

    async load() {
        this.state.loading = true;
        this.state.error = null;
        try {
            this.state.data = await this.rpc("/buz_asset/dashboard/data", {
                filters: this.requestFilters,
            });
        } catch (error) {
            this.state.error = (error.data && error.data.message) || error.message || String(error);
        } finally {
            this.state.loading = false;
        }
    }

    onFilterChange(key, ev) {
        const value = ev.target.value;
        const numeric = ["department_id", "category_id", "location_id"];
        this.state.filters[key] = numeric.includes(key) ? parseInt(value) || false : value || false;
        this.debouncedLoad();
    }

    onCompanyChange(ev) {
        const id = parseInt(ev.target.value);
        this.state.filters.company_ids = id ? [id] : [];
        this.debouncedLoad();
    }

    resetFilters() {
        Object.assign(this.state.filters, {
            company_ids: [],
            as_of: today(),
            department_id: false,
            category_id: false,
            location_id: false,
            operational_state: false,
        });
        this.load();
    }

    async exportXlsx() {
        try {
            await download({
                url: "/buz_asset/dashboard/export",
                data: { filters: JSON.stringify(this.requestFilters) },
            });
        } catch (error) {
            this.notification.add(error.message || "Export failed", { type: "danger" });
        }
    }

    printPdf() {
        window.print();
    }

    // ------------------------------------------------------------- formatting
    money(value) {
        const cur = this.state.data && this.state.data.meta.currency;
        const digits = cur ? cur.decimals : 2;
        const text = new Intl.NumberFormat("en-US", {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits,
        }).format(value || 0);
        if (!cur) {
            return text;
        }
        return cur.position === "before" ? cur.symbol + " " + text : text + " " + cur.symbol;
    }

    compact(value) {
        const abs = Math.abs(value || 0);
        if (abs >= 1e6) {
            return (value / 1e6).toFixed(1) + "M";
        }
        if (abs >= 1e3) {
            return (value / 1e3).toFixed(0) + "K";
        }
        return Math.round(value || 0).toString();
    }

    // ------------------------------------------------------------------ charts
    get baseOptions() {
        return { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } };
    }

    get trendChart() {
        const t = this.state.data.charts.trend;
        const line = (label, key, color) => ({
            label,
            data: t[key],
            borderColor: color,
            backgroundColor: color + "22",
            pointBackgroundColor: color,
            pointRadius: 3,
            tension: 0.3,
            fill: key === "nbv",
        });
        return {
            type: "line",
            data: {
                labels: t.labels,
                datasets: [
                    line("ราคาทุน", "cost", PALETTE[0]),
                    line("ค่าเสื่อมราคาสะสม", "accumulated", PALETTE[1]),
                    line("มูลค่าตามบัญชี", "nbv", PALETTE[2]),
                ],
            },
            options: {
                ...this.baseOptions,
                plugins: { legend: { position: "top", align: "end" } },
                scales: { y: { beginAtZero: true, ticks: { callback: (v) => this.compact(v) } } },
            },
        };
    }

    // Legend rows for the donuts (name, value, share, colour).
    legend(rows, key) {
        const total = rows.reduce((sum, r) => sum + (r[key] || 0), 0) || 1;
        return rows.map((r, i) => ({
            name: r.name,
            color: PALETTE[i % PALETTE.length],
            count: r.count,
            value: r[key],
            pct: ((100 * (r[key] || 0)) / total).toFixed(1),
        }));
    }

    get categoryLegend() {
        return this.legend(this.state.data.charts.by_category, "nbv");
    }

    get statusLegend() {
        return this.legend(this.state.data.charts.by_status, "count");
    }

    toggleMore() {
        this.state.moreOpen = !this.state.moreOpen;
    }

    donut(rows, valueKey) {
        return {
            type: "doughnut",
            data: {
                labels: rows.map((r) => r.name),
                datasets: [{
                    data: rows.map((r) => r[valueKey]),
                    backgroundColor: rows.map((r, i) => PALETTE[i % PALETTE.length]),
                }],
            },
            options: {
                ...this.baseOptions,
                cutout: "66%",
                plugins: { legend: { display: false } },
            },
        };
    }

    get categoryChart() {
        return this.donut(this.state.data.charts.by_category, "nbv");
    }

    get statusChart() {
        return this.donut(this.state.data.charts.by_status, "count");
    }

    get monthlyChart() {
        const m = this.state.data.charts.monthly_depreciation;
        const set = (label, key, color) => ({ label, data: m.series[key], backgroundColor: color });
        return {
            type: "bar",
            data: {
                labels: m.labels,
                datasets: [
                    set("Posted", "posted", POSTED),
                    set("Planned", "planned", PLANNED),
                    set("Draft", "draft", DRAFT),
                    set("Exception", "exception", EXCEPTION),
                ],
            },
            options: {
                ...this.baseOptions,
                scales: {
                    x: { stacked: true },
                    y: { stacked: true, ticks: { callback: (v) => this.compact(v) } },
                },
            },
        };
    }

    get departmentChart() {
        const rows = this.state.data.charts.by_department;
        return {
            type: "bar",
            data: {
                labels: rows.map((r) => r.name),
                datasets: [{ label: "NBV", data: rows.map((r) => r.nbv), backgroundColor: PALETTE[0] }],
            },
            options: {
                ...this.baseOptions,
                indexAxis: "y",
                plugins: { legend: { display: false } },
                scales: { x: { ticks: { callback: (v) => this.compact(v) } } },
            },
        };
    }

    // ----------------------------------------------------------- quick actions
    // Quick actions only open existing views/wizards. Every state change stays in
    // the model methods, which re-check groups server-side.
    openAction(action) {
        this.action.doAction(action);
    }

    createAsset() {
        this.openAction({
            type: "ir.actions.act_window",
            name: "Asset",
            res_model: "buz.asset",
            views: [[false, "form"]],
            target: "current",
        });
    }

    importFromBill() {
        this.openAction({
            type: "ir.actions.act_window",
            name: "Posted Vendor Bills",
            res_model: "account.move",
            views: [[false, "list"], [false, "form"]],
            domain: [["move_type", "=", "in_invoice"], ["state", "=", "posted"]],
            context: { default_move_type: "in_invoice" },
        });
    }

    generateDepreciation() {
        this.openAction("buz_asset_management.action_buz_asset_depreciation_line");
    }

    transferAsset() {
        this.openAction({
            type: "ir.actions.act_window",
            name: "Asset Transfer",
            res_model: "buz.asset.transfer",
            views: [[false, "form"]],
            target: "current",
        });
    }

    printQr() {
        this.openAction({
            type: "ir.actions.act_window",
            name: "Assets - select, then Print > QR label",
            res_model: "buz.asset",
            views: [[false, "list"], [false, "form"]],
            domain: [["operational_state", "!=", "disposed"]],
        });
    }

    startAudit() {
        this.openAction({
            type: "ir.actions.act_window",
            name: "Physical Audit",
            res_model: "buz.asset.audit",
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ----------------------------------------------------------------- drill
    openRecord(model, resId) {
        this.openAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: resId,
            views: [[false, "form"]],
        });
    }

    openPending(row) {
        this.openAction({
            type: "ir.actions.act_window",
            name: row.label,
            res_model: row.model,
            domain: row.domain,
            views: [[false, "list"], [false, "form"]],
        });
    }
}

registry.category("actions").add("buz_asset_management.dashboard", AssetDashboard);
