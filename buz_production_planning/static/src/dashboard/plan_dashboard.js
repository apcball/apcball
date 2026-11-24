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
const CARD_ICON = {
    to_review: "fa-check-square-o", no_document: "fa-file-text-o", late_suggestions: "fa-exclamation",
    buy_no_vendor: "fa-shopping-cart", shortage_products: "fa-cube", late_workorders: "fa-clock-o",
    not_applied: "fa-calendar",
};
const STATUS_COLOR = { on_track: "#1fa971", at_risk: "#3b82f6", overdue: "#f59e0b" };
const STATE_BADGE = {
    draft: "text-bg-secondary", computed: "text-bg-info", confirmed: "text-bg-primary",
    done: "text-bg-success",
};

function num(value, digits = 1) {
    return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: digits });
}

/** One domain matching any of the given domains (prefix notation). */
function anyOf(domains) {
    const parts = domains.map((d) => (d.length > 1 ? [...Array(d.length - 1).fill("&"), ...d] : d));
    return [...Array(Math.max(0, parts.length - 1)).fill("|"), ...parts.flat()];
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
            runs: [], run: false, cards: [], canCreate: false, updatedAt: "", charts: null,
            period: "week", weeks: [], loadChart: null, topSuggestions: [], status: null, activity: [],
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
            runs: data.runs, run: data.run, cards: data.cards,
            weeks: data.charts.load_weeks ? data.charts.load_weeks.weeks : [],
            topSuggestions: data.top_suggestions, status: data.status, activity: data.activity,
            canCreate: data.can_create, runId: data.run ? data.run.id : false,
            updatedAt: deserializeDateTime(data.updated_at).toFormat("HH:mm"),
            charts: data.run ? markRaw(this.buildCharts(data)) : null,
            loading: false,
        });
        if (data.run) {
            this.buildLoadChart();
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
            status: data.status.total ? this.statusChart(data.status) : null,
        };
    }

    /** New config object only when data or period change, so the chart is not redrawn each render. */
    buildLoadChart() {
        const buckets = this.buckets();
        this.state.loadChart = buckets.length ? markRaw(this.loadChart(buckets)) : null;
    }

    buckets() {
        const period = this.state.period;
        const groups = new Map();
        for (const w of this.state.weeks) {
            const d = DateTime.fromISO(w.week);
            const start = period === "month" ? d.startOf("month")
                : period === "quarter" ? d.startOf("quarter") : d;
            const key = start.toISODate();
            if (!groups.has(key)) {
                groups.set(key, {
                    week: key, load_hours: 0, capacity_hours: 0, domains: [],
                    label: period === "week" ? weekLabel(key)
                        : period === "month" ? start.toFormat("LLL yy") : start.toFormat("'Q'q yy"),
                });
            }
            const g = groups.get(key);
            g.load_hours += w.load_hours;
            g.capacity_hours += w.capacity_hours;
            g.domains.push(w.domain);
        }
        return [...groups.values()].map((g) => ({
            ...g, load_hours: Math.round(g.load_hours * 10) / 10,
            capacity_hours: Math.round(g.capacity_hours * 10) / 10,
        }));
    }

    setPeriod(period) {
        this.state.period = period;
        this.buildLoadChart();
    }

    iconFor(card) {
        return CARD_ICON[card.key] || "fa-circle";
    }

    openSuggestion(row) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: SUGGESTION, res_id: row.id,
            views: [[false, "form"]], target: "current",
        });
    }

    viewAllSuggestions() {
        this.openList(_t("Suggestions"), SUGGESTION,
            [["run_id", "=", this.state.run.id], ["state", "in", ["proposed", "approved"]]]);
    }

    openActivity(row) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: row.model, res_id: row.res_id,
            views: [[false, "form"]], target: "current",
        });
    }

    activityTime(row) {
        return deserializeDateTime(row.date).toFormat("HH:mm");
    }

    loadChart(weeks) {
        const base = this.baseOptions((el) => {
            const week = weeks[el.index];
            this.openList(_t("Schedule, %s", week.label), SCHEDULE_LINE, anyOf(week.domains));
        });
        const hours = _t("hours");
        return {
            type: "bar",
            data: {
                labels: weeks.map((w) => w.label),
                datasets: [{
                    type: "line", label: _t("Capacity"), stack: "capacity", order: 0,
                    data: weeks.map((w) => w.capacity_hours),
                    borderColor: COLOR.capacity, backgroundColor: COLOR.capacity,
                    borderWidth: 2, pointRadius: 3, tension: 0,
                }, {
                    label: _t("Load within capacity"), stack: "load", order: 1,
                    data: weeks.map((w) => Math.min(w.load_hours, w.capacity_hours)),
                    backgroundColor: COLOR.load, borderRadius: 4,
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
                            title: (items) => items[0].label,
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

    statusChart(status) {
        const base = this.baseOptions(() => this.viewAllSuggestions());
        const onTrack = status.rows.find((r) => r.key === "on_track");
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
                ctx.font = "bold 26px sans-serif";
                ctx.fillText(`${onTrack.pct} %`, x, y - 8);
                ctx.font = "12px sans-serif";
                ctx.fillText(_t("On Track"), x, y + 14);
                ctx.restore();
            },
        };
        const unit = _t("suggestions");
        return {
            type: "doughnut",
            plugins: [centre],
            data: {
                labels: status.rows.map((r) => r.label),
                datasets: [{
                    data: status.rows.map((r) => r.count),
                    backgroundColor: status.rows.map((r) => STATUS_COLOR[r.key]), borderWidth: 2,
                }],
            },
            options: {
                ...base.options, cutout: "70%",
                plugins: {
                    legend: { display: false },
                    tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${num(ctx.parsed, 0)} ${unit}` } },
                },
            },
        };
    }
}

registry.category("actions").add("buz_production_planning.dashboard", BuzPlanDashboard);
