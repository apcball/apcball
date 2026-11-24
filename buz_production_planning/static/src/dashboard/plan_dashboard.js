/** @odoo-module **/
import { loadJS } from "@web/core/assets";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import {
    Component, markRaw, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState,
} from "@odoo/owl";

const { DateTime, Settings } = luxon;

const STORAGE_KEY = "buz_production_planning.dashboard.run_id";
const SUGGESTION = "buz.plan.suggestion";
const SCHEDULE_LINE = "buz.plan.schedule.line";

// One colour per meaning, everywhere on the page.
const COLOR = {
    late: "#d9534f",        // late / over capacity
    onTime: "#2e9e5b",
    load: "#5b8fc7",
    capacity: "#495057",
    make: "#3b82c4",
    buy: "#8a6fbf",
    grid: "rgba(128, 128, 128, 0.2)",
};
const DOCUMENT_COLOR = {
    none: "#adb5bd", draft: "#e0a030", open: "#3b82c4", done: "#1f8a8a", cancel: "#6c757d",
};
const STATE_BADGE = {
    draft: "text-bg-secondary", computed: "text-bg-info", confirmed: "text-bg-primary",
    done: "text-bg-success",
};

function num(value, digits = 1) {
    return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function weekLabel(isoDate) {
    return DateTime.fromISO(isoDate).toFormat("dd LLL");
}

/** Thin Chart.js wrapper: draws again only when the config object changes. */
export class BuzPlanChart extends Component {
    static template = "buz_production_planning.PlanChart";
    static props = {
        config: { type: Object },
        height: { type: Number, optional: true },
    };

    setup() {
        this.canvas = useRef("canvas");
        this.chart = null;
        this.drawn = null;
        onMounted(() => this.draw());
        onPatched(() => this.draw());
        onWillUnmount(() => this.destroy());
    }

    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    draw() {
        const config = this.props.config;
        if (config === this.drawn && this.chart) {
            return;
        }
        this.destroy();
        this.drawn = config;
        if (this.canvas.el && window.Chart) {
            this.chart = new window.Chart(this.canvas.el, config);
        }
    }
}

export class BuzPlanDashboard extends Component {
    static template = "buz_production_planning.PlanDashboard";
    static components = { BuzPlanChart };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            loading: true, error: false, runId: this.initialRunId(),
            runs: [], run: false, cards: [], bottlenecks: [], canCreate: false,
            updatedAt: "", charts: null,
        });
        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.load();
        });
    }

    // ------------------------------------------------------------------ data
    initialRunId() {
        const fromAction = this.props.action.params?.run_id;
        if (fromAction) {
            return fromAction;
        }
        try {
            return parseInt(window.localStorage.getItem(STORAGE_KEY)) || false;
        } catch {
            return false;
        }
    }

    remember(runId) {
        try {
            window.localStorage.setItem(STORAGE_KEY, String(runId));
        } catch {
            // Private window or blocked storage: the latest plan is shown next time.
        }
    }

    async load() {
        this.state.loading = true;
        this.state.error = false;
        let data;
        try {
            data = await this.orm.call("buz.plan.dashboard", "get_dashboard_data", [], {
                run_id: this.state.runId,
                tz: Settings.defaultZone.name,
            });
        } catch (error) {
            this.state.loading = false;
            this.state.error = true;
            throw error;
        }
        Object.assign(this.state, {
            runs: data.runs, run: data.run, cards: data.cards, bottlenecks: data.bottlenecks,
            canCreate: data.can_create, runId: data.run ? data.run.id : false,
            updatedAt: deserializeDateTime(data.updated_at).toFormat("HH:mm"),
            charts: data.run ? markRaw(this.buildCharts(data)) : null,
            loading: false,
        });
        if (data.run) {
            this.remember(data.run.id);
        }
    }

    async onRunChange(ev) {
        this.state.runId = parseInt(ev.target.value) || false;
        await this.load();
    }

    // ------------------------------------------------------------------ header
    get stateBadge() {
        return STATE_BADGE[this.state.run.state] || "text-bg-secondary";
    }

    get dateRange() {
        const run = this.state.run;
        const fmt = (d) => DateTime.fromISO(d).toLocaleString(DateTime.DATE_MED);
        return `${fmt(run.date_from)} – ${fmt(run.date_to)}`;
    }

    openPlan() {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "buz.plan.run", res_id: this.state.run.id,
            views: [[false, "form"]], target: "current",
        });
    }

    openGantt() {
        this.action.doAction({
            type: "ir.actions.client", tag: "buz_production_planning.gantt",
            name: _t("Schedule Gantt"), params: { run_id: this.state.run.id },
        });
    }

    createPlan() {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "buz.plan.run",
            views: [[false, "form"]], target: "current",
        });
    }

    // ------------------------------------------------------------------ drill-down
    /** Opens existing records only; the domain is the one the number was counted with. */
    openList(name, model, domain, groupBy) {
        this.action.doAction({
            type: "ir.actions.act_window", name, res_model: model, domain,
            views: [[false, "list"], [false, "form"]], target: "current",
            context: groupBy ? { group_by: [groupBy] } : {},
        });
    }

    openCard(card) {
        this.openList(card.label, card.model, card.domain, card.group_by);
    }

    // ------------------------------------------------------------------ charts
    baseOptions(onClick) {
        const ink = getComputedStyle(document.body).color;
        return {
            ink,
            options: {
                responsive: true, maintainAspectRatio: false, animation: false, color: ink,
                onClick: (ev, elements) => {
                    if (elements.length) {
                        onClick(elements[0]);
                    }
                },
                onHover: (ev, elements) => {
                    if (ev.native && ev.native.target) {
                        ev.native.target.style.cursor = elements.length ? "pointer" : "default";
                    }
                },
            },
            axis: (title, extra = {}) => ({
                grid: { color: COLOR.grid }, ticks: { color: ink },
                title: { display: Boolean(title), text: title, color: ink }, ...extra,
            }),
            legend: { position: "bottom", labels: { color: ink, boxWidth: 14 } },
        };
    }

    buildCharts(data) {
        const c = data.charts;
        return {
            scheduled: c.load_weeks.scheduled,
            truncated: c.load_weeks.truncated,
            load: c.load_weeks.weeks.length ? this.loadChart(c.load_weeks.weeks) : null,
            workcenters: data.bottlenecks.length ? this.workcenterChart(data.bottlenecks) : null,
            onTime: c.on_time.total ? this.onTimeChart(c.on_time) : null,
            release: c.release_weeks.length ? this.releaseChart(c.release_weeks) : null,
            documents: c.documents.some((d) => d.count) ? this.documentChart(c.documents) : null,
        };
    }

    loadChart(weeks) {
        const base = this.baseOptions((el) => {
            const week = weeks[el.index];
            this.openList(_t("Schedule, week of %s", weekLabel(week.week)), SCHEDULE_LINE, week.domain);
        });
        const hours = _t("hours");
        return {
            type: "bar",
            data: {
                labels: weeks.map((w) => weekLabel(w.week)),
                datasets: [{
                    type: "line", label: _t("Capacity"), stack: "capacity", order: 0,
                    data: weeks.map((w) => w.capacity_hours),
                    borderColor: COLOR.capacity, backgroundColor: COLOR.capacity,
                    borderWidth: 2, pointRadius: 3, tension: 0,
                }, {
                    label: _t("Load within capacity"), stack: "load", order: 1,
                    data: weeks.map((w) => Math.min(w.load_hours, w.capacity_hours)),
                    backgroundColor: COLOR.load,
                }, {
                    label: _t("Load over capacity"), stack: "load", order: 2,
                    data: weeks.map((w) => Math.max(0, w.load_hours - w.capacity_hours)),
                    backgroundColor: COLOR.late,
                }],
            },
            options: {
                ...base.options,
                interaction: { mode: "index", intersect: false },
                scales: {
                    x: base.axis(_t("Week starting"), { stacked: true }),
                    y: base.axis(_t("Hours"), { stacked: true, beginAtZero: true }),
                },
                plugins: {
                    legend: base.legend,
                    tooltip: {
                        callbacks: {
                            title: (items) => _t("Week of %s", items[0].label),
                            label: (ctx) => `${ctx.dataset.label}: ${num(ctx.parsed.y)} ${hours}`,
                            footer: (items) => {
                                const week = weeks[items[0].dataIndex];
                                return _t("Total load: %s hours", num(week.load_hours));
                            },
                        },
                    },
                },
            },
        };
    }

    workcenterChart(rows) {
        const base = this.baseOptions((el) => {
            const row = rows[el.index];
            this.openList(_t("Schedule of %s", row.name), SCHEDULE_LINE, row.domain);
        });
        const known = rows.filter((r) => r.pct !== false).map((r) => r.pct);
        const top = Math.max(120, ...known) * 1.15;
        const text = (row) => (row.pct === false ? _t("No working time") : `${num(row.pct, 0)} %`);
        const marks = {
            id: "buzWorkcenterMarks",
            afterDatasetsDraw(chart) {
                const { ctx, chartArea, scales } = chart;
                const x100 = scales.x.getPixelForValue(100);
                ctx.save();
                ctx.strokeStyle = COLOR.capacity;
                ctx.setLineDash([5, 4]);
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.moveTo(x100, chartArea.top);
                ctx.lineTo(x100, chartArea.bottom);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = base.ink;
                ctx.font = "11px sans-serif";
                ctx.textBaseline = "middle";
                chart.getDatasetMeta(0).data.forEach((bar, index) => {
                    const label = text(rows[index]);
                    const width = ctx.measureText(label).width;
                    const inside = bar.x + width + 8 > chartArea.right;
                    ctx.textAlign = inside ? "right" : "left";
                    ctx.fillStyle = inside ? "#fff" : base.ink;
                    ctx.fillText(label, inside ? bar.x - 6 : bar.x + 6, bar.y);
                });
                ctx.restore();
            },
        };
        return {
            type: "bar",
            plugins: [marks],
            data: {
                labels: rows.map((r) => r.name),
                datasets: [{
                    label: _t("Load % of capacity"),
                    data: rows.map((r) => (r.pct === false ? top : r.pct)),
                    backgroundColor: rows.map((r) => (r.overloaded ? COLOR.late : COLOR.load)),
                }],
            },
            options: {
                ...base.options,
                indexAxis: "y",
                scales: {
                    x: base.axis(_t("Load as % of capacity (dashed line = 100 %)"), {
                        beginAtZero: true, max: Math.ceil(top / 10) * 10,
                        ticks: { color: base.ink, callback: (v) => `${v} %` },
                    }),
                    y: base.axis(""),
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const row = rows[ctx.dataIndex];
                                return _t("Load %s hours of %s hours capacity (%s)",
                                    num(row.load_hours), num(row.capacity_hours), text(row));
                            },
                        },
                    },
                },
            },
        };
    }

    onTimeChart(data) {
        const base = this.baseOptions(() => {
            this.openList(_t("Work orders finishing late"), SCHEDULE_LINE, data.late_domain);
        });
        const centre = {
            id: "buzCentreText",
            afterDraw(chart) {
                const { ctx, chartArea } = chart;
                const x = (chartArea.left + chartArea.right) / 2;
                const y = (chartArea.top + chartArea.bottom) / 2;
                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = base.ink;
                ctx.font = "bold 24px sans-serif";
                ctx.fillText(`${num(data.pct, 0)} %`, x, y - 8);
                ctx.font = "12px sans-serif";
                ctx.fillText(_t("on time"), x, y + 14);
                ctx.restore();
            },
        };
        const unit = _t("manufacturing orders");
        return {
            type: "doughnut",
            plugins: [centre],
            data: {
                labels: [_t("On time"), _t("Late")],
                datasets: [{
                    data: [data.on_time, data.late],
                    backgroundColor: [COLOR.onTime, COLOR.late], borderWidth: 1,
                }],
            },
            options: {
                ...base.options,
                cutout: "68%",
                plugins: {
                    legend: base.legend,
                    tooltip: {
                        callbacks: { label: (ctx) => `${ctx.label}: ${num(ctx.parsed, 0)} ${unit}` },
                    },
                },
            },
        };
    }

    releaseChart(weeks) {
        const kinds = [
            { key: "make", label: _t("Make"), color: COLOR.make },
            { key: "buy", label: _t("Buy"), color: COLOR.buy },
        ];
        const base = this.baseOptions((el) => {
            const week = weeks[el.index];
            this.openList(_t("Suggestions, week of %s", weekLabel(week.week)), SUGGESTION, week.domain);
        });
        const unit = _t("suggestions");
        return {
            type: "bar",
            data: {
                labels: weeks.map((w) => weekLabel(w.week)),
                datasets: kinds.map((kind) => ({
                    label: kind.label, backgroundColor: kind.color,
                    data: weeks.map((w) => w[kind.key]),
                })),
            },
            options: {
                ...base.options,
                interaction: { mode: "index", intersect: false },
                scales: {
                    x: base.axis(_t("Week to order / start"), { stacked: true }),
                    y: base.axis(_t("Suggestions"), {
                        stacked: true, beginAtZero: true, ticks: { color: base.ink, precision: 0 },
                    }),
                },
                plugins: {
                    legend: base.legend,
                    tooltip: {
                        callbacks: {
                            title: (items) => _t("Week of %s", items[0].label),
                            label: (ctx) => `${ctx.dataset.label}: ${num(ctx.parsed.y, 0)} ${unit}`,
                        },
                    },
                },
            },
        };
    }

    documentChart(rows) {
        const base = this.baseOptions((el) => {
            const row = rows[el.datasetIndex];
            this.openList(_t("Suggestions: %s", row.label), SUGGESTION, row.domain);
        });
        const unit = _t("suggestions");
        return {
            type: "bar",
            data: {
                labels: [_t("Suggestions")],
                datasets: rows.map((row) => ({
                    label: row.label, data: [row.count],
                    backgroundColor: DOCUMENT_COLOR[row.key] || DOCUMENT_COLOR.none,
                })),
            },
            options: {
                ...base.options,
                indexAxis: "y",
                scales: {
                    x: base.axis(_t("Suggestions"), {
                        stacked: true, beginAtZero: true, ticks: { color: base.ink, precision: 0 },
                    }),
                    y: base.axis("", { stacked: true, display: false }),
                },
                plugins: {
                    legend: base.legend,
                    tooltip: {
                        callbacks: {
                            title: () => "",
                            label: (ctx) => `${ctx.dataset.label}: ${num(ctx.parsed.x, 0)} ${unit}`,
                        },
                    },
                },
            },
        };
    }
}

registry.category("actions").add("buz_production_planning.dashboard", BuzPlanDashboard);
