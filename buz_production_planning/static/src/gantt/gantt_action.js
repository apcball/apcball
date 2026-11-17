/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { deserializeDateTime, serializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

const { DateTime, Settings } = luxon;

const LABEL_W = 430;       // px, two left columns (Plan / Document + Product / Description)
const LOAD_H = 20;         // px, daily load strip
const LANE_H = 28;         // px, one bar
const GROUP_COLORS = ["#e0584f", "#4a90d9", "#f0a030", "#8e6cd9", "#14b8a6", "#64748b"];
const CARD_ICON = {
    to_review: "fa-file-text-o", no_document: "fa-check", late_suggestions: "fa-exclamation",
    buy_no_vendor: "fa-shopping-cart", shortage_products: "fa-cube", not_applied: "fa-calendar",
};
const ZOOMS = {
    day: { days: 14, pxPerMin: 104 / 1440, snap: 60, step: 7 },
    week: { days: 42, pxPerMin: 40 / 1440, snap: 120, step: 28 },
};

export class BuzGanttAction extends Component {
    static template = "buz_production_planning.GanttAction";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.state = useState({
            runId: this.props.action.params?.run_id || false,
            runs: [], run: false, cards: [], workcenters: [], lines: [], capacity: {}, load: {},
            pickingTypes: [], canApply: false, loading: true,
            zoom: "day",
            start: DateTime.now().startOf("week"),
            filters: { pickingType: 0, workcenter: 0, lateOnly: false },
            collapsed: {}, pop: null,
        });
        this.drag = null;
        this._move = this.onPointerMove.bind(this);
        this._up = this.onPointerUp.bind(this);
        onWillStart(() => this.load());
        onWillUnmount(() => this.stopListening());
    }

    // ------------------------------------------------------------------ data
    get zoom() { return ZOOMS[this.state.zoom]; }
    get pxPerMin() { return this.zoom.pxPerMin; }
    get viewStart() { return this.state.start.startOf("day"); }
    get viewEnd() { return this.viewStart.plus({ days: this.zoom.days }); }
    get trackWidth() { return this.zoom.days * 1440 * this.pxPerMin; }
    get labelWidth() { return LABEL_W; }

    async load() {
        this.state.loading = true;
        const f = this.state.filters;
        const data = await this.orm.call("buz.plan.run", "gantt_data", [], {
            run_id: this.state.runId,
            date_from: serializeDateTime(this.viewStart),
            date_to: serializeDateTime(this.viewEnd),
            tz: Settings.defaultZone.name,
            filters: {
                picking_type_id: f.pickingType || false,
                workcenter_id: f.workcenter || false,
                late_only: f.lateOnly,
            },
        });
        Object.assign(this.state, {
            runs: data.runs, run: data.run, workcenters: data.workcenters,
            capacity: data.capacity, load: data.load, pickingTypes: data.picking_types,
            canApply: data.can_apply, cards: data.cards || [], runId: data.run ? data.run.id : false,
            lines: data.lines.map((l) => ({
                ...l,
                sMs: deserializeDateTime(l.start).toMillis(),
                eMs: deserializeDateTime(l.end).toMillis(),
                deadlineMs: l.deadline ? deserializeDateTime(l.deadline).toMillis() : 0,
            })),
            loading: false,
        });
    }

    // ------------------------------------------------------------------ layout
    xOf(ms) {
        return ((ms - this.viewStart.toMillis()) / 60000) * this.pxPerMin;
    }

    get days() {
        const out = [];
        for (let i = 0; i < this.zoom.days; i++) {
            const d = this.viewStart.plus({ days: i });
            out.push({
                key: d.toFormat("yyyy-MM-dd"),
                x: i * 1440 * this.pxPerMin,
                w: 1440 * this.pxPerMin,
                label: d.toFormat("ccc dd"),
                weekend: d.weekday >= 6,
                today: d.hasSame(DateTime.now(), "day"),
            });
        }
        return out;
    }

    /** Top header tier: week bands in Day zoom, month bands in Week zoom. */
    get headGroups() {
        const out = [];
        const dayZoom = this.state.zoom === "day";
        let cur = null;
        for (let i = 0; i < this.zoom.days; i++) {
            const d = this.viewStart.plus({ days: i });
            const key = dayZoom ? d.startOf("week").toFormat("yyyy-MM-dd") : d.toFormat("yyyy-MM");
            if (!cur || cur.key !== key) {
                cur = { key, x: i * 1440 * this.pxPerMin, w: 0, first: d, last: d };
                out.push(cur);
            }
            cur.w += 1440 * this.pxPerMin;
            cur.last = d;
        }
        for (const g of out) {
            g.label = dayZoom
                ? `${g.first.toFormat("dd LLL")} – ${g.last.toFormat("dd LLL yyyy")}`
                : g.first.toFormat("LLLL yyyy");
        }
        return out;
    }

    /** Bottom header tier: one cell per day (Day zoom) or per week (Week zoom). */
    get ticks() {
        if (this.state.zoom === "day") {
            return this.days.map((d) => ({ ...d, label: this.viewStart.plus({ days: Math.round(d.x / (1440 * this.pxPerMin)) }).toFormat("ccc dd") }));
        }
        const out = [];
        for (let i = 0; i < this.zoom.days; i += 7) {
            const d = this.viewStart.plus({ days: i });
            out.push({
                key: d.toFormat("yyyy-MM-dd"), x: i * 1440 * this.pxPerMin, w: 7 * 1440 * this.pxPerMin,
                label: d.toFormat("dd LLL"), weekend: false,
                today: DateTime.now() >= d && DateTime.now() < d.plus({ days: 7 }),
            });
        }
        return out;
    }

    get nowX() {
        const x = this.xOf(Date.now());
        return x >= 0 && x <= this.trackWidth ? x : null;
    }

    get rows() {
        const rows = [];
        const byWc = {};
        for (const l of this.state.lines) {
            (byWc[l.wc] = byWc[l.wc] || []).push(l);
        }
        let lastGroup = null;
        let gi = -1;
        for (const wc of this.state.workcenters) {
            if (wc.group !== lastGroup) {
                gi += 1;
                rows.push({
                    type: "group", key: "g" + wc.group, label: wc.group,
                    color: GROUP_COLORS[gi % GROUP_COLORS.length],
                    collapsed: !!this.state.collapsed[wc.group],
                    count: this.state.workcenters.filter((w) => w.group === wc.group).length,
                });
                lastGroup = wc.group;
            }
            if (this.state.collapsed[wc.group]) {
                continue;
            }
            const bars = this.layoutBars(byWc[wc.id] || []);
            const lanes = Math.max(1, ...bars.map((b) => b.lane + 1));
            rows.push({
                type: "wc", key: "w" + wc.id, wc, bars,
                height: LOAD_H + lanes * LANE_H + 8,
                cells: this.loadCells(wc.id),
                cap: this.capSummary(wc.id),
                jobs: bars.length,
                color: GROUP_COLORS[gi % GROUP_COLORS.length],
            });
        }
        return rows;
    }

    layoutBars(lines) {
        const sorted = [...lines].sort((a, b) => a.sMs - b.sMs);
        const laneEnds = [];
        let maxEnd = -Infinity;
        let maxBar = null;
        const bars = [];
        for (const l of sorted) {
            let lane = laneEnds.findIndex((end) => end <= l.sMs);
            if (lane < 0) {
                lane = laneEnds.length;
            }
            laneEnds[lane] = l.eMs;
            const bar = { line: l, lane, conflict: false };
            if (l.sMs < maxEnd && maxBar) {
                bar.conflict = true;
                maxBar.conflict = true;
            }
            if (l.eMs > maxEnd) {
                maxEnd = l.eMs;
                maxBar = bar;
            }
            bars.push(bar);
        }
        return bars.map((b) => ({
            ...b,
            conflict: b.conflict,
            left: this.xOf(b.line.sMs),
            width: Math.max(4, ((b.line.eMs - b.line.sMs) / 60000) * this.pxPerMin),
            top: LOAD_H + 3 + b.lane * LANE_H,
            deadlineX: b.line.deadlineMs && b.line.deadlineMs >= b.line.sMs && b.line.deadlineMs <= b.line.eMs ? 1 : null,
            cls: this.barClass(b),
            title: this.tooltip(b.line),
        }));
    }

    /** done → Completed, late → Delay, waiting for components/predecessor → Waiting, else On Track. */
    statusOf(l) {
        if (l.wo_state === "done") {
            return "done";
        }
        if (l.is_late) {
            return "delay";
        }
        if (l.wo_state === "pending" || l.wo_state === "waiting") {
            return "waiting";
        }
        return "track";
    }

    barClass(bar) {
        const l = bar.line;
        return [
            "o_buz_bar",
            "o_buz_s_" + this.statusOf(l),
            l.is_late ? "o_buz_late" : "",
            l.is_locked ? "o_buz_locked" : "",
            l.is_manual ? "o_buz_manual" : "",
            bar.conflict ? "o_buz_conflict" : "",
            l.state === "applied" ? "o_buz_applied" : "",
        ].join(" ");
    }

    fmt(ms) {
        return DateTime.fromMillis(ms).toFormat("dd LLL HH:mm");
    }

    tooltip(l) {
        const lines = [
            `${l.mo} · ${l.product}`,
            `${_t("Qty")}: ${l.qty} · ${l.operation}`,
            `${this.fmt(l.sMs)} → ${this.fmt(l.eMs)} (${Math.round(l.minutes)} min, ${l.source})`,
        ];
        if (l.deadlineMs) {
            lines.push(`${_t("Deadline")}: ${this.fmt(l.deadlineMs)}`);
        }
        return lines.join("\n");
    }

    loadCells(wcId) {
        const cap = this.state.capacity[wcId] || {};
        const used = this.state.load[wcId] || {};
        return this.days.map((d) => {
            const c = cap[d.key] || 0;
            const u = used[d.key] || 0;
            const ratio = c ? u / c : u ? 2 : 0;
            return {
                key: d.key, x: d.x, w: d.w, text: this.state.zoom === "day" && (c || u) ? `${Math.round(u)} / ${Math.round(c)}` : "",
                cls: ratio > 1 ? "o_buz_load_over" : ratio > 0.85 ? "o_buz_load_high" : ratio > 0 ? "o_buz_load_ok" : "",
            };
        });
    }

    capSummary(wcId) {
        const cap = this.state.capacity[wcId] || {};
        const used = this.state.load[wcId] || {};
        let c = 0;
        let u = 0;
        for (const d of this.days) {
            c += cap[d.key] || 0;
            u += used[d.key] || 0;
        }
        const ratio = c ? u / c : u ? 2 : 0;
        return {
            text: `${Math.round(u)} / ${Math.round(c)} min`,
            pct: Math.min(100, Math.round(ratio * 100)),
            cls: ratio > 1 ? "o_buz_cap_over" : ratio > 0.85 ? "o_buz_cap_high" : "",
        };
    }

    cardIcon(card) {
        return CARD_ICON[card.key] || "fa-circle";
    }

    openCard(card) {
        this.action.doAction({
            type: "ir.actions.act_window", name: card.label, res_model: card.model, domain: card.domain,
            views: [[false, "list"], [false, "form"]], target: "current",
            context: card.group_by ? { group_by: [card.group_by] } : {},
        });
    }

    exportCsv() {
        const wcName = Object.fromEntries(this.state.workcenters.map((w) => [w.id, w.name]));
        const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
        const head = ["Plan", "Workcenter", "MO", "Product", "Operation", "Qty", "Start", "End", "Minutes", "Status"];
        const rows = [...this.state.lines]
            .sort((a, b) => a.sMs - b.sMs)
            .map((l) => [
                this.state.run?.name, wcName[l.wc], l.mo, l.product, l.operation, l.qty,
                DateTime.fromMillis(l.sMs).toFormat("yyyy-MM-dd HH:mm"),
                DateTime.fromMillis(l.eMs).toFormat("yyyy-MM-dd HH:mm"), Math.round(l.minutes), this.statusOf(l),
            ]);
        const csv = "\ufeff" + [head, ...rows].map((r) => r.map(esc).join(",")).join("\r\n");
        const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
        const a = document.createElement("a");
        a.href = url;
        a.download = `${(this.state.run?.name || "gantt").replace(/[^\w.-]+/g, "_")}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    toggleGroup(label) {
        this.state.collapsed[label] = !this.state.collapsed[label];
    }

    showPopover(ev, bar) {
        if (this.drag) {
            return;
        }
        const r = ev.currentTarget.getBoundingClientRect();
        const w = 320;
        const x = Math.min(Math.max(8, r.left), window.innerWidth - w - 8);
        const below = r.bottom + 8;
        const y = below + 230 > window.innerHeight ? Math.max(8, r.top - 238) : below;
        this.state.pop = { line: bar.line, conflict: bar.conflict, x, y };
    }

    hidePopover() {
        this.state.pop = null;
    }

    // ------------------------------------------------------------------ toolbar
    async shift(days) {
        this.state.start = this.state.start.plus({ days });
        await this.load();
    }
    async today() {
        this.state.start = DateTime.now().startOf("week");
        await this.load();
    }
    async setZoom(zoom) {
        this.state.zoom = zoom;
        await this.load();
    }
    async onRunChange(ev) {
        this.state.runId = parseInt(ev.target.value);
        await this.load();
    }
    async onFilterChange(key, ev) {
        this.state.filters[key] = ev.target.type === "checkbox" ? ev.target.checked : parseInt(ev.target.value) || 0;
        await this.load();
    }
    async reschedule() {
        await this.orm.call("buz.plan.run", "action_schedule", [[this.state.runId]]);
        this.notification.add(_t("Schedule recomputed."), { type: "success" });
        await this.load();
    }
    apply() {
        this.dialog.add(ConfirmationDialog, {
            title: _t("Apply schedule"),
            body: _t("This writes the planned start and end dates on the real workorders and moves the manufacturing order dates. Continue?"),
            confirm: async () => {
                let applied = 0;
                let remaining = 1;
                // One request per batch of manufacturing orders: no single call can time out.
                while (remaining > 0) {
                    const res = await this.orm.call("buz.plan.run", "apply_schedule_batch", [[this.state.runId]]);
                    applied += res.applied;
                    remaining = res.remaining;
                    if (remaining > 0) {
                        this.notification.add(
                            _t("Applying… %s workorders done, %s manufacturing orders left.", applied, remaining),
                            { type: "info" });
                    }
                }
                this.notification.add(_t("Schedule applied: %s workorders.", applied), { type: "success" });
                await this.load();
            },
            cancel: () => {},
        });
    }

    openProduction(line) {
        this.action.doAction({
            type: "ir.actions.act_window", res_model: "mrp.production",
            res_id: line.mo_id, views: [[false, "form"]], target: "current",
        });
    }

    // ------------------------------------------------------------------ drag / resize
    onBarPointerDown(ev, line, mode) {
        if (ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        ev.stopPropagation();
        this.state.pop = null;
        // Locked jobs cannot be dragged but can still be clicked to open the MO.
        this.drag = {
            line, mode, x0: ev.clientX, s0: line.sMs, e0: line.eMs, moved: false,
            locked: line.is_locked,
        };
        window.addEventListener("pointermove", this._move);
        window.addEventListener("pointerup", this._up);
    }

    onPointerMove(ev) {
        const d = this.drag;
        if (!d || d.locked) {
            return;
        }
        const dx = ev.clientX - d.x0;
        if (Math.abs(dx) > 3) {
            d.moved = true;
        }
        if (!d.moved) {
            return;
        }
        const snapMs = this.zoom.snap * 60000;
        const deltaMs = Math.round(dx / this.pxPerMin / this.zoom.snap) * snapMs;
        if (d.mode === "move") {
            d.line.sMs = d.s0 + deltaMs;
            d.line.eMs = d.e0 + deltaMs;
        } else {
            d.line.eMs = Math.max(d.s0 + snapMs, d.e0 + deltaMs);
        }
    }

    async onPointerUp() {
        this.stopListening();
        const d = this.drag;
        this.drag = null;
        if (!d) {
            return;
        }
        if (!d.moved) {
            this.openProduction(d.line);
            return;
        }
        try {
            await this.orm.call("buz.plan.schedule.line", "gantt_update", [
                [d.line.id],
                serializeDateTime(DateTime.fromMillis(d.line.sMs)),
                serializeDateTime(DateTime.fromMillis(d.line.eMs)),
                d.mode,
            ]);
        } catch (error) {
            const message = error?.data?.message || _t("The job could not be moved.");
            this.notification.add(message, { type: "danger" });
        }
        await this.load();
    }

    stopListening() {
        window.removeEventListener("pointermove", this._move);
        window.removeEventListener("pointerup", this._up);
    }
}

registry.category("actions").add("buz_production_planning.gantt", BuzGanttAction);
