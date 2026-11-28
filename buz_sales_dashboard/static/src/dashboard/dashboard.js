/** @odoo-module **/

import { Component, onWillStart, useEffect, useRef, useState } from "@odoo/owl";
import { loadJS } from "@web/core/assets";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { download } from "@web/core/network/download";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/webclient/actions/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { SalesDashboardMultiSelect } from "./multi_select";

const REPORT = "buz.sales.dashboard.report";
const SAVED = "buz.sales.dashboard.filter";
const TABS = [
    { id: "period", name: "ตามช่วงเวลา" },
    { id: "user", name: "พนักงานขาย" },
    { id: "team", name: "ทีมขาย" },
];
const COUNT_FORMAT = new Intl.NumberFormat("th-TH", { maximumFractionDigits: 0 });
const GROUP_TITLES = { sales: "ขาย · ตามวันที่ SO", wait: "รอส่ง", pos: "POS", invoice: "ออกบิล · ตามวันที่ใบแจ้งหนี้" };
const STATUS = {
    done: { label: "ถึงเป้าแล้ว", css: "o_bsd_done" },
    ahead: { label: "ตามแผน", css: "o_bsd_ahead" },
    behind: { label: "ช้ากว่าแผน", css: "o_bsd_behind" },
    missed: { label: "ขาดเป้า", css: "o_bsd_behind" },
    set: { label: "ตั้งเป้าแล้ว", css: "o_bsd_ahead" },
    none: { label: "ยังไม่ตั้งเป้า", css: "o_bsd_none" },
};
// the shortcuts beside the page title
const QUICK_PRESETS = [
    { id: "this_month", name: "เดือนนี้" },
    { id: "last_3_months", name: "3 เดือน" },
    { id: "last_6_months", name: "6 เดือน" },
    { id: "this_year", name: "ปีนี้" },
];
// The four cards: [measure, row style, other label, remark, tag]
const CARDS = [
    {
        id: "sales", icon: "fa-file-text", title: "ขาย", note: "นับตามวันที่ SO · บาทก่อน VAT",
        lead: "amount_total", leadNote: "ใช้เทียบเป้า",
        rows: [
            ["amount_so", "o_bsd_strong"],
            ["amount_delivered", "o_bsd_sub"],
            ["amount_pending", "o_bsd_sub o_bsd_ref", "+ รอส่ง (ดูกลุ่ม “รอส่ง”)"],
            ["amount_service", "o_bsd_sub"],
            ["amount_adjust", "o_bsd_sub"],
            ["amount_so_credit", "o_bsd_sub", null, "ตามวันที่ใบลดหนี้"],
            ["amount_pos", "o_bsd_ref", "+ POS สุทธิ (ดูกลุ่ม “POS”)"],
            ["amount_quotation", "o_bsd_sep", null, null, "ไม่รวมในยอดขาย"],
        ],
    },
    {
        id: "wait", icon: "fa-hourglass-half", title: "รอส่ง", note: "ส่วนของ SO ยืนยันแล้วที่ยังไม่ส่ง",
        lead: "amount_pending", side: { label: "ของ SO สุทธิ", of: "amount_so" },
        stack: ["amount_pending_open", "amount_pending_billed", "amount_pending_other"],
        rows: [],
    },
    {
        id: "pos", icon: "fa-desktop", title: "POS", note: "นับตามวันที่ใบแจ้งหนี้",
        lead: "amount_pos", side: { label: "ของยอดขายรวม", of: "amount_total" },
        rows: [["amount_pos_invoice", ""], ["amount_pos_refund", ""]],
    },
    {
        id: "invoice", icon: "fa-list-alt", title: "ออกบิล", tag: "ไม่บวกในยอดขายรวม",
        note: "สุทธิหลังลดหนี้ · นับตามวันที่ พนักงานขาย และทีมของใบแจ้งหนี้",
        lead: "amount_invoiced", leadNote: "ตรงกับ Invoice Analysis",
        rows: [
            ["amount_inv_so", "o_bsd_strong"],
            ["amount_inv_so_invoice", "o_bsd_sub"],
            ["amount_inv_so_refund", "o_bsd_sub"],
            ["amount_inv_other", ""],
            ["amount_pos", "o_bsd_ref", "+ POS สุทธิ (ดูกลุ่ม “POS”)"],
        ],
    },
];

export class SalesDashboard extends Component {
    static template = "buz_sales_dashboard.Dashboard";
    static components = { MultiSelect: SalesDashboardMultiSelect };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.chartRef = useRef("chart");
        this.tabs = TABS;
        this.quickPresets = QUICK_PRESETS;
        this.state = useState({
            options: null,
            filters: null,
            data: null,
            loading: true,
            exporting: false,
            tab: "period",
            savedId: 0,
            saveName: "",
            saveDefault: false,
            saveMenu: false,
            showFilters: false,
        });
        this.cards = CARDS;
        this.request = 0;
        // keep the filters when coming back through the breadcrumbs
        useSetupAction({
            getLocalState: () => ({
                filters: JSON.parse(JSON.stringify(this.state.filters)),
                tab: this.state.tab,
                savedId: this.state.savedId,
            }),
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            this.state.options = await this.orm.call(REPORT, "get_dashboard_options", []);
            const previous = this.props.state;
            if (previous && previous.filters) {
                this.state.filters = previous.filters;
                this.state.tab = previous.tab;
                this.state.savedId = previous.savedId;
                this.syncSaveForm();
            } else {
                const preferred = this.state.options.saved_filters.find((f) => f.is_default);
                this.applySaved(preferred ? preferred.id : 0);
            }
            await this.load();
            // a team view starts on its people
            if (!(previous && previous.filters) && this.state.data.members) {
                this.state.tab = "user";
            }
        });

        useEffect(
            () => this.renderChart(),
            () => [this.state.data, this.chartRef.el]
        );
    }

    // ---------------------------------------------------------------- data
    async load() {
        const request = ++this.request;
        this.state.loading = true;
        try {
            const data = await this.orm.call(REPORT, "get_dashboard_data", [this.state.filters]);
            // a slower, older answer must not overwrite a newer one
            if (request === this.request) {
                this.state.data = data;
            }
        } finally {
            if (request === this.request) {
                this.state.loading = false;
            }
        }
    }

    setFilter(changes) {
        Object.assign(this.state.filters, changes);
        this.load();
    }

    onPreset(ev) {
        const preset = ev.target.value;
        const changes = { date_preset: preset };
        if (preset === "custom" && this.state.data) {
            changes.date_from = this.state.data.date_from;
            changes.date_to = this.state.data.date_to;
        }
        this.setFilter(changes);
    }

    onDate(key, ev) {
        const dates = {
            date_preset: "custom",
            date_from: this.state.data.date_from,
            date_to: this.state.data.date_to,
        };
        dates[key] = ev.target.value || false;
        this.setFilter(dates);
    }

    toggleSource(id) {
        const current = this.state.filters.sources;
        const sources = current.includes(id) ? current.filter((s) => s !== id) : [...current, id];
        if (sources.length) {
            this.setFilter({ sources });
        }
    }

    // ---------------------------------------------------------------- saved filters
    syncSaveForm() {
        const saved = this.state.options.saved_filters.find((f) => f.id === this.state.savedId);
        this.state.saveName = saved ? saved.name : "";
        this.state.saveDefault = saved ? saved.is_default : false;
    }

    applySaved(id) {
        const saved = this.state.options.saved_filters.find((f) => f.id === id);
        this.state.savedId = saved ? saved.id : 0;
        const filters = saved ? saved.filters : this.state.options.default_filters;
        this.state.filters = JSON.parse(JSON.stringify(filters));
        this.syncSaveForm();
    }

    onSaved(ev) {
        this.applySaved(Number(ev.target.value));
        this.load();
    }

    async refreshSaved(id) {
        const options = await this.orm.call(REPORT, "get_dashboard_options", []);
        this.state.options = options;
        this.state.savedId = id;
        this.syncSaveForm();
    }

    async saveFilter(asNew) {
        const name = this.state.saveName.trim();
        if (!name) {
            this.notification.add("กรุณาตั้งชื่อชุดตัวกรอง", { type: "warning" });
            return;
        }
        const values = {
            name,
            filters: this.state.filters,
            is_default: this.state.saveDefault,
        };
        let id = this.state.savedId;
        if (id && !asNew) {
            await this.orm.write(SAVED, [id], values);
        } else {
            [id] = await this.orm.create(SAVED, [values]);
        }
        await this.refreshSaved(id);
        this.notification.add(`บันทึกชุดตัวกรอง "${name}" แล้ว`, { type: "success" });
    }

    deleteFilter() {
        const id = this.state.savedId;
        this.dialog.add(ConfirmationDialog, {
            body: `ลบชุดตัวกรอง "${this.state.saveName}" ?`,
            confirmLabel: "ลบ",
            confirm: async () => {
                await this.orm.unlink(SAVED, [id]);
                await this.refreshSaved(0);
            },
            cancel: () => {},
        });
    }

    // ---------------------------------------------------------------- actions
    async exportExcel() {
        this.state.exporting = true;
        try {
            await download({
                url: "/buz_sales_dashboard/export",
                data: { filters: JSON.stringify(this.state.filters) },
            });
        } finally {
            this.state.exporting = false;
        }
    }

    openDocuments(title, extra = []) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: REPORT,
            views: [[false, "list"], [false, "pivot"], [false, "graph"]],
            domain: [...this.state.data.domain, ...extra],
            target: "current",
        });
    }

    openAnalysis() {
        // the same domain as the dashboard, in the pivot of the analysis page
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `วิเคราะห์ยอดขาย ${this.state.data.date_from} ถึง ${this.state.data.date_to}`,
            res_model: REPORT,
            views: [[false, "pivot"], [false, "graph"], [false, "list"]],
            domain: this.state.data.domain,
            target: "current",
        });
    }

    openCard(measure) {
        this.openDocuments(measure.name, [[measure.id, "!=", 0]]);
    }

    openRow(row) {
        const field = this.state.tab === "period"
            ? this.state.data.granularity
            : `${this.state.tab}_id`;
        const value = this.state.tab === "period" ? row.key : row.key || false;
        this.openDocuments(row.label, [[field, "=", value]]);
    }

    openTargets() {
        this.action.doAction("buz_sales_dashboard.action_target_board");
    }

    openMember(member) {
        this.setFilter({ user_ids: [member.id] });
    }

    // ---------------------------------------------------------------- display
    get periodRows() {
        return this.state.data[this.state.data.granularity];
    }

    get rows() {
        return this.state.tab === "period" ? this.periodRows : this.state.data[this.state.tab];
    }

    get rowHeader() {
        if (this.state.tab === "period") {
            return this.state.data.granularity === "week" ? "สัปดาห์ (จ.-อา.)" : "เดือน";
        }
        return this.tabs.find((t) => t.id === this.state.tab).name;
    }

    // "2026-W47 (16/11-22/11)" -> "W47 · 16/11–22/11", "2026-11" -> "11/2026"
    shortPeriod(key) {
        const week = /^\d{4}-(W\d{2}) \((\d{2}\/\d{2})-(\d{2}\/\d{2})\)$/.exec(key);
        if (week) {
            return `${week[1]} · ${week[2]}–${week[3]}`;
        }
        const month = /^(\d{4})-(\d{2})$/.exec(key);
        return month ? `${month[2]}/${month[1]}` : key;
    }

    rowLabel(row) {
        return this.state.tab === "period" ? this.shortPeriod(row.label) : row.label;
    }

    // what the closed filter panel of a phone is filtering on
    get chips() {
        const filters = this.state.filters;
        const options = this.state.options;
        const named = (choices, ids, unit) => ids.length === 1
            ? (choices.find((c) => c.id === ids[0]) || { name: `${unit} 1` }).name
            : `${unit} ${ids.length}`;
        const preset = options.presets.find((p) => p.id === this.state.data.filters.date_preset);
        const chips = [{
            id: "period",
            label: filters.date_preset === "custom"
                ? `${this.day(this.state.data.date_from)}–${this.day(this.state.data.date_to)}`
                : preset.name,
        }];
        if (filters.user_ids.length) {
            chips.push({ id: "users", label: named(options.users, filters.user_ids, "พนักงานขาย"), clear: { user_ids: [] } });
        }
        if (filters.team_ids.length) {
            chips.push({ id: "teams", label: named(options.teams, filters.team_ids, "ทีม"), clear: { team_ids: [] } });
        }
        if (filters.sources.length < options.sources.length) {
            chips.push({
                id: "sources",
                label: options.sources.filter((s) => filters.sources.includes(s.id)).map((s) => s.name).join(", "),
                clear: { sources: options.sources.map((s) => s.id) },
            });
        }
        return chips;
    }

    day(value) {
        return value ? value.split("-").reverse().join("/") : "";
    }

    get tableGroups() {
        const groups = [];
        for (const measure of this.state.options.measures) {
            const last = groups[groups.length - 1];
            if (last && last.id === measure.group) {
                last.span += 1;
            } else {
                groups.push({ id: measure.group, title: GROUP_TITLES[measure.group], span: 1 });
            }
        }
        return groups;
    }

    isGroupStart(index) {
        const measures = this.state.options.measures;
        return index === 0 || measures[index - 1].group !== measures[index].group;
    }

    name(id) {
        return this.state.options.measures.find((m) => m.id === id).name;
    }

    measure(id) {
        return this.state.options.measures.find((m) => m.id === id);
    }

    total(id) {
        return this.state.data.total[id];
    }

    share(part, whole) {
        // credit notes can leave a part larger than its whole: no share then
        const percent = whole > 0.5 ? Math.round((part / whole) * 100) : -1;
        return percent >= 0 && percent <= 100 ? `${percent}%` : "—";
    }

    shortName(id) {
        return this.name(id).replace(/^รอส่ง: /, "");
    }

    stackSize(id) {
        return Math.max(0, this.total(id));
    }

    status(key) {
        return STATUS[key] || STATUS.none;
    }

    percent(value, digits = 1) {
        return value === false || value === undefined ? "—" : `${value.toFixed(digits)}%`;
    }

    initials(name) {
        return name.trim().slice(0, 2);
    }

    barWidth(percent) {
        return Math.max(0, Math.min(100, percent));
    }

    amount(value) {
        // "|| 0" turns a rounded -0 into 0
        return COUNT_FORMAT.format(Math.round(value) || 0);
    }

    renderChart() {
        if (!this.chartRef.el || !this.state.data) {
            return;
        }
        const rows = this.periodRows;
        const label = (id) => this.state.options.measures.find((m) => m.id === id).name;
        const series = (id, color, extra = {}) => ({
            label: label(id),
            data: rows.map((r) => Math.round(r[id])),
            backgroundColor: color,
            borderColor: color,
            ...extra,
        });
        // the SO + POS total above each stacked bar, when the bars are few
        const barTotals = {
            id: "bsdBarTotals",
            afterDatasetsDraw: (chart) => {
                if (rows.length > 16) {
                    return;
                }
                const { ctx } = chart;
                const sales = [0, 1].filter((i) => chart.isDatasetVisible(i));
                if (!sales.length) {
                    return;
                }
                ctx.save();
                ctx.font = "bold 11px sans-serif";
                ctx.fillStyle = "#253044";
                ctx.textAlign = "center";
                rows.forEach((row, index) => {
                    const bars = sales.map((i) => chart.getDatasetMeta(i).data[index]);
                    // from the unrounded figures, so it matches the table
                    const total = sales.reduce((sum, i) => sum + row[["amount_so", "amount_pos"][i]], 0);
                    if (Math.round(total)) {
                        const top = Math.min(...bars.map((bar) => Math.min(bar.y, bar.base)));
                        ctx.fillText(this.amount(total), bars[0].x, top - 5);
                    }
                });
                ctx.restore();
            },
        };
        const chart = new window.Chart(this.chartRef.el, {
            type: "bar",
            plugins: [barTotals],
            data: {
                labels: rows.map((r) => this.shortPeriod(r.label)),
                datasets: [
                    series("amount_so", "#1976f8", { stack: "sales", borderRadius: 3 }),
                    series("amount_pos", "#8270e9", { stack: "sales" }),
                    series("amount_quotation", "#94a3b8", { stack: "quotation", hidden: true }),
                    series("amount_invoiced", "#059e7b", { stack: "invoiced", hidden: true }),
                ],
            },
            options: {
                maintainAspectRatio: false,
                animation: false,
                layout: { padding: { top: 16 } },
                scales: {
                    x: { stacked: true },
                    y: { stacked: true, ticks: { callback: (v) => this.amount(v) } },
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label: (c) => `${c.dataset.label}: ${this.amount(c.parsed.y)}`,
                        },
                    },
                },
            },
        });
        return () => chart.destroy();
    }
}

registry.category("actions").add("buz_sales_dashboard.dashboard", SalesDashboard);
