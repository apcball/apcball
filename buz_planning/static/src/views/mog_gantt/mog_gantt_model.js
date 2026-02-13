/** @odoo-module **/

import { Model } from "@web/model/model";
import { KeepLast } from "@web/core/utils/concurrency";

const { DateTime } = luxon;

export class MogGanttModel extends Model {
    setup(params) {
        this.params = params;
        this.resModel = params.resModel;
        this.fields = params.fields || {};
        this.defaultGroupBy = params.defaultGroupBy || "employee_id";
        this.keepLast = new KeepLast();

        // State
        this.rows = [];
        this.slots = [];
        this.groupMode = this.defaultGroupBy === "workcenter_id" ? "workcenter" : "employee";
        this.scale = "week";
        this.focusDate = DateTime.now();
        this._computeRange();
    }

    _computeRange() {
        const fd = this.focusDate;
        if (this.scale === "day") {
            this.startDate = fd.startOf("day");
            this.endDate = fd.endOf("day");
        } else if (this.scale === "week") {
            this.startDate = fd.startOf("week");
            this.endDate = fd.endOf("week");
        } else {
            this.startDate = fd.startOf("month");
            this.endDate = fd.endOf("month");
        }
    }

    get dateRange() {
        return { start: this.startDate, end: this.endDate };
    }

    setScale(scale) {
        this.scale = scale;
        this._computeRange();
    }

    navigatePrev() {
        const unit = this.scale === "day" ? { days: 1 } : this.scale === "week" ? { weeks: 1 } : { months: 1 };
        this.focusDate = this.focusDate.minus(unit);
        this._computeRange();
    }

    navigateNext() {
        const unit = this.scale === "day" ? { days: 1 } : this.scale === "week" ? { weeks: 1 } : { months: 1 };
        this.focusDate = this.focusDate.plus(unit);
        this._computeRange();
    }

    navigateToday() {
        this.focusDate = DateTime.now();
        this._computeRange();
    }

    setGroupMode(mode) {
        this.groupMode = mode;
    }

    async load(searchParams) {
        const startStr = this.startDate.toUTC().toFormat("yyyy-MM-dd HH:mm:ss");
        const endStr = this.endDate.toUTC().toFormat("yyyy-MM-dd HH:mm:ss");

        const domain = [
            ["start_datetime", "<", endStr],
            ["end_datetime", ">", startStr],
            ["state", "!=", "cancelled"],
        ];

        const result = await this.keepLast.add(
            this.orm.searchRead(
                this.resModel,
                domain,
                [
                    "name", "start_datetime", "end_datetime",
                    "employee_id", "workcenter_id", "slot_type",
                    "state", "color", "project_task_id", "mrp_workorder_id",
                    "project_id", "production_id",
                ],
            )
        );

        // Build rows
        if (this.groupMode === "employee") {
            const employees = await this.orm.searchRead(
                "hr.employee", [], ["id", "name"],
            );
            this.rows = employees.map((e) => ({ id: e.id, name: e.name }));
            const hasUnassigned = result.some((s) => !s.employee_id);
            if (hasUnassigned) {
                this.rows.unshift({ id: false, name: "Unassigned" });
            }
        } else {
            const workcenters = await this.orm.searchRead(
                "mrp.workcenter", [], ["id", "name"],
            );
            this.rows = workcenters.map((w) => ({ id: w.id, name: w.name }));
            const hasUnassigned = result.some((s) => !s.workcenter_id);
            if (hasUnassigned) {
                this.rows.unshift({ id: false, name: "Unassigned" });
            }
        }

        this.slots = result.map((s) => this._parseSlot(s));
        this.notify();
    }

    _parseSlot(raw) {
        const employeeId = raw.employee_id ? raw.employee_id[0] : false;
        const workcenterId = raw.workcenter_id ? raw.workcenter_id[0] : false;
        return {
            id: raw.id,
            name: raw.name || raw.display_name || "",
            start: DateTime.fromSQL(raw.start_datetime, { zone: "utc" }).toLocal(),
            end: DateTime.fromSQL(raw.end_datetime, { zone: "utc" }).toLocal(),
            start_datetime: raw.start_datetime,
            end_datetime: raw.end_datetime,
            employee_id: employeeId,
            employee_name: raw.employee_id ? raw.employee_id[1] : "",
            workcenter_id: workcenterId,
            workcenter_name: raw.workcenter_id ? raw.workcenter_id[1] : "",
            slot_type: raw.slot_type || "manual",
            state: raw.state,
            color: raw.color || 0,
            project_task_id: raw.project_task_id ? raw.project_task_id[0] : false,
            project_task_name: raw.project_task_id ? raw.project_task_id[1] : "",
            mrp_workorder_id: raw.mrp_workorder_id ? raw.mrp_workorder_id[0] : false,
            mrp_workorder_name: raw.mrp_workorder_id ? raw.mrp_workorder_id[1] : "",
            project_id: raw.project_id ? raw.project_id[0] : false,
            project_name: raw.project_id ? raw.project_id[1] : "",
            production_id: raw.production_id ? raw.production_id[0] : false,
            production_name: raw.production_id ? raw.production_id[1] : "",
        };
    }

    getRowSlots(rowId) {
        const field = this.groupMode === "employee" ? "employee_id" : "workcenter_id";
        return this.slots.filter((s) => {
            const val = s[field];
            if (!rowId && !val) return true;
            return val === rowId;
        });
    }

    async updateSlot(slotId, vals) {
        const writeVals = {};
        if (vals.start) {
            writeVals.start_datetime = vals.start.toUTC().toFormat("yyyy-MM-dd HH:mm:ss");
        }
        if (vals.end) {
            writeVals.end_datetime = vals.end.toUTC().toFormat("yyyy-MM-dd HH:mm:ss");
        }
        if ("employee_id" in vals) {
            writeVals.employee_id = vals.employee_id || false;
        }
        if ("workcenter_id" in vals) {
            writeVals.workcenter_id = vals.workcenter_id || false;
        }

        await this.orm.write(this.resModel, [slotId], writeVals);

        // Update local slot
        const idx = this.slots.findIndex((s) => s.id === slotId);
        if (idx >= 0) {
            const slot = this.slots[idx];
            if (vals.start) slot.start = vals.start;
            if (vals.end) slot.end = vals.end;
            if ("employee_id" in vals) slot.employee_id = vals.employee_id;
            if ("workcenter_id" in vals) slot.workcenter_id = vals.workcenter_id;
        }
        return this.slots[idx] || null;
    }

    async createSlot(vals) {
        const createVals = {
            name: vals.name || "New Slot",
            start_datetime: vals.start.toUTC().toFormat("yyyy-MM-dd HH:mm:ss"),
            end_datetime: vals.end.toUTC().toFormat("yyyy-MM-dd HH:mm:ss"),
        };
        if (vals.employee_id) createVals.employee_id = vals.employee_id;
        if (vals.workcenter_id) createVals.workcenter_id = vals.workcenter_id;
        if (vals.project_task_id) createVals.project_task_id = vals.project_task_id;
        if (vals.mrp_workorder_id) createVals.mrp_workorder_id = vals.mrp_workorder_id;

        const newId = await this.orm.create(this.resModel, [createVals]);
        const ids = Array.isArray(newId) ? newId : [newId];
        const records = await this.orm.read(this.resModel, ids, [
            "name", "start_datetime", "end_datetime", "employee_id",
            "workcenter_id", "slot_type", "state", "color",
            "project_task_id", "mrp_workorder_id",
            "project_id", "production_id",
        ]);
        if (records.length) {
            const created = this._parseSlot(records[0]);
            this.slots.push(created);
            return created;
        }
        return null;
    }

    detectConflicts() {
        const conflicts = new Set();
        for (const row of this.rows) {
            const rowSlots = this.getRowSlots(row.id);
            for (let i = 0; i < rowSlots.length; i++) {
                for (let j = i + 1; j < rowSlots.length; j++) {
                    const a = rowSlots[i];
                    const b = rowSlots[j];
                    if (a.start < b.end && a.end > b.start) {
                        conflicts.add(a.id);
                        conflicts.add(b.id);
                    }
                }
            }
        }
        return conflicts;
    }
}
