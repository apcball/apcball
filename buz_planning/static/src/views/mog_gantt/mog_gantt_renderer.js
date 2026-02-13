/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount, onPatched, onWillUpdateProps } from "@odoo/owl";

const { DateTime } = luxon;

export class MogGanttRenderer extends Component {
    setup() {
        this.containerRef = useRef("ganttContainer");
        this.timelineRef = useRef("timelineArea");
        this.state = useState({
            dragging: false,
            dragSlotId: null,
            dragType: null,
            ghostLeft: 0,
            ghostWidth: 0,
            conflicts: new Set(),
        });

        this._dragState = null;
        this._onMouseMoveBound = this._onMouseMove.bind(this);
        this._onMouseUpBound = this._onMouseUp.bind(this);

        onMounted(() => {
            document.addEventListener("mousemove", this._onMouseMoveBound);
            document.addEventListener("mouseup", this._onMouseUpBound);
            this._updateConflicts();
        });

        onWillUnmount(() => {
            document.removeEventListener("mousemove", this._onMouseMoveBound);
            document.removeEventListener("mouseup", this._onMouseUpBound);
        });

        onPatched(() => {
            this._updateConflicts();
        });

        onWillUpdateProps(() => {
            this._updateConflicts();
        });
    }

    _updateConflicts() {
        const conflicts = this.props.model.detectConflicts();
        this.state.conflicts = conflicts;
    }

    // ---- Time/pixel helpers ----

    get totalMs() {
        const { start, end } = this.props.model.dateRange;
        return end.toMillis() - start.toMillis();
    }

    _getTimelineWidth() {
        const el = this.containerRef.el;
        if (el) {
            const sidebar = el.querySelector(".mog-gantt-sidebar");
            const sidebarW = sidebar ? sidebar.offsetWidth : 200;
            return Math.max(el.offsetWidth - sidebarW, 800);
        }
        return 1200;
    }

    msToPixel(ms) {
        return (ms / this.totalMs) * this._getTimelineWidth();
    }

    pixelToMs(px) {
        return (px / this._getTimelineWidth()) * this.totalMs;
    }

    dateToPixel(dt) {
        const ms = dt.toMillis() - this.props.model.dateRange.start.toMillis();
        return this.msToPixel(ms);
    }

    pixelToDate(px) {
        const ms = this.pixelToMs(px);
        return DateTime.fromMillis(this.props.model.dateRange.start.toMillis() + ms);
    }

    // ---- Computed getters for template ----

    get rows() {
        return this.props.model.rows;
    }

    get headerCells() {
        const cells = [];
        const { start, end } = this.props.model.dateRange;
        const scale = this.props.model.scale;
        let cursor = start;

        if (scale === "day") {
            while (cursor < end) {
                const next = cursor.plus({ hours: 1 });
                cells.push({
                    label: cursor.toFormat("HH:mm"),
                    left: this.dateToPixel(cursor),
                    width: this.msToPixel(next.toMillis() - cursor.toMillis()),
                });
                cursor = next;
            }
        } else if (scale === "week") {
            while (cursor < end) {
                const next = cursor.plus({ days: 1 });
                cells.push({
                    label: cursor.toFormat("EEE dd"),
                    left: this.dateToPixel(cursor),
                    width: this.msToPixel(next.toMillis() - cursor.toMillis()),
                });
                cursor = next;
            }
        } else {
            while (cursor < end) {
                const next = cursor.plus({ days: 1 });
                cells.push({
                    label: cursor.toFormat("dd"),
                    left: this.dateToPixel(cursor),
                    width: this.msToPixel(next.toMillis() - cursor.toMillis()),
                });
                cursor = next;
            }
        }
        return cells;
    }

    get rangeLabel() {
        const { start, end } = this.props.model.dateRange;
        const scale = this.props.model.scale;
        if (scale === "day") {
            return start.toFormat("EEEE, dd MMMM yyyy");
        } else if (scale === "week") {
            return `${start.toFormat("dd MMM")} - ${end.toFormat("dd MMM yyyy")}`;
        }
        return start.toFormat("MMMM yyyy");
    }

    getRowSlots(rowId) {
        let slots = this.props.model.getRowSlots(rowId);
        const filter = this.props.slotTypeFilter;
        if (filter && filter !== "all") {
            slots = slots.filter((s) => s.slot_type === filter);
        }
        return slots;
    }

    getSlotStyle(slot) {
        const left = Math.max(0, this.dateToPixel(slot.start));
        const right = this.dateToPixel(slot.end);
        const width = Math.max(right - left, 4);
        return `left:${left}px;width:${width}px;`;
    }

    getSlotClass(slot) {
        const classes = ["mog-gantt-slot"];
        classes.push(`mog-gantt-slot--${slot.state || "draft"}`);
        classes.push(`slot--${slot.slot_type || "manual"}`);
        if (this.state.conflicts.has(slot.id)) {
            classes.push("mog-gantt-slot--conflict");
        }
        if (this.state.dragSlotId === slot.id) {
            classes.push("mog-gantt-slot--dragging");
        }
        return classes.join(" ");
    }

    getSlotBadge(slot) {
        if (slot.slot_type === "task" && slot.project_name) {
            return slot.project_name;
        }
        if (slot.slot_type === "workorder" && slot.production_name) {
            return slot.production_name;
        }
        return "";
    }

    getSlotColor(slot) {
        const colors = [
            "#4CAF50", "#2196F3", "#FF9800", "#9C27B0",
            "#F44336", "#00BCD4", "#795548", "#607D8B",
            "#E91E63", "#3F51B5", "#009688", "#FFC107",
        ];
        const idx = (slot.color || 0) % colors.length;
        return colors[idx];
    }

    // ---- Now-line ----

    get nowLineStyle() {
        const now = DateTime.now();
        const { start, end } = this.props.model.dateRange;
        if (now < start || now > end) return null;
        const left = this.dateToPixel(now);
        return `left:${left}px;`;
    }

    // ---- Drag & Drop ----

    onSlotMouseDown(ev, slot, type) {
        ev.preventDefault();
        ev.stopPropagation();

        const containerEl = this.containerRef.el;
        if (!containerEl) return;

        const rowEls = containerEl.querySelectorAll(".mog-gantt-timeline-row");
        let rowIndex = 0;
        for (let i = 0; i < rowEls.length; i++) {
            const rowRect = rowEls[i].getBoundingClientRect();
            if (ev.clientY >= rowRect.top && ev.clientY <= rowRect.bottom) {
                rowIndex = i;
                break;
            }
        }

        this._dragState = {
            type,
            slotId: slot.id,
            startX: ev.clientX,
            startY: ev.clientY,
            origStart: slot.start,
            origEnd: slot.end,
            origRowIndex: rowIndex,
            currentRowIndex: rowIndex,
            origField: this.props.model.groupMode === "employee" ? "employee_id" : "workcenter_id",
            origRowId: slot[this.props.model.groupMode === "employee" ? "employee_id" : "workcenter_id"],
        };

        this.state.dragging = true;
        this.state.dragSlotId = slot.id;
        this.state.dragType = type;
    }

    _onMouseMove(ev) {
        if (!this._dragState) return;

        const ds = this._dragState;
        const deltaX = ev.clientX - ds.startX;
        const deltaMs = this.pixelToMs(deltaX);

        const containerEl = this.containerRef.el;
        if (!containerEl) return;

        const rowEls = containerEl.querySelectorAll(".mog-gantt-timeline-row");
        for (let i = 0; i < rowEls.length; i++) {
            const rowRect = rowEls[i].getBoundingClientRect();
            if (ev.clientY >= rowRect.top && ev.clientY <= rowRect.bottom) {
                ds.currentRowIndex = i;
                break;
            }
        }

        const slot = this.props.model.slots.find((s) => s.id === ds.slotId);
        if (!slot) return;

        if (ds.type === "move") {
            slot.start = DateTime.fromMillis(ds.origStart.toMillis() + deltaMs);
            slot.end = DateTime.fromMillis(ds.origEnd.toMillis() + deltaMs);
        } else if (ds.type === "resize-left") {
            const newStart = DateTime.fromMillis(ds.origStart.toMillis() + deltaMs);
            if (newStart < slot.end) {
                slot.start = newStart;
            }
        } else if (ds.type === "resize-right") {
            const newEnd = DateTime.fromMillis(ds.origEnd.toMillis() + deltaMs);
            if (newEnd > slot.start) {
                slot.end = newEnd;
            }
        }

        if (ds.currentRowIndex !== ds.origRowIndex) {
            const newRow = this.props.model.rows[ds.currentRowIndex];
            if (newRow) {
                slot[ds.origField] = newRow.id;
            }
        }

        this.state.ghostLeft = this.dateToPixel(slot.start);
        this.state.ghostWidth = this.dateToPixel(slot.end) - this.state.ghostLeft;
    }

    async _onMouseUp(ev) {
        if (!this._dragState) return;

        const ds = this._dragState;
        const slot = this.props.model.slots.find((s) => s.id === ds.slotId);

        this.state.dragging = false;
        this.state.dragSlotId = null;
        this.state.dragType = null;

        if (!slot) {
            this._dragState = null;
            return;
        }

        const vals = {
            start: slot.start,
            end: slot.end,
        };

        if (ds.currentRowIndex !== ds.origRowIndex) {
            const newRow = this.props.model.rows[ds.currentRowIndex];
            if (newRow) {
                vals[ds.origField] = newRow.id;
            }
        }

        this._dragState = null;

        const startChanged = vals.start.toMillis() !== ds.origStart.toMillis();
        const endChanged = vals.end.toMillis() !== ds.origEnd.toMillis();
        const rowChanged = ds.currentRowIndex !== ds.origRowIndex;

        if (startChanged || endChanged || rowChanged) {
            await this.props.onSlotUpdated(ds.slotId, vals);
        }
    }

    // ---- Quick Create (click empty area) ----

    onTimelineClick(ev, rowId) {
        if (this.state.dragging) return;
        if (ev.target.closest(".mog-gantt-slot")) return;

        const rowEl = ev.currentTarget;
        const rect = rowEl.getBoundingClientRect();
        const x = ev.clientX - rect.left;

        const clickDate = this.pixelToDate(x);
        const snapped = clickDate.startOf("hour");
        const endDate = snapped.plus({ hours: 1 });

        this.props.onSlotCreated(rowId, snapped, endDate);
    }

    // ---- Slot click (open form) ----

    onSlotClick(ev, slot) {
        ev.stopPropagation();
        if (this.state.dragging) return;
        this.props.onSlotClicked(slot);
    }
}

MogGanttRenderer.template = "buz_planning.MogGanttRenderer";
MogGanttRenderer.props = {
    model: Object,
    slotTypeFilter: { type: String, optional: true },
    onSlotUpdated: Function,
    onSlotCreated: Function,
    onSlotClicked: Function,
};
