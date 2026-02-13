/** @odoo-module **/

import { Component, useRef, useState } from "@odoo/owl";
import { Layout } from "@web/search/layout";
import { useModel } from "@web/model/model";
import { useService } from "@web/core/utils/hooks";
import { useSetupView } from "@web/views/view_hook";
import { standardViewProps } from "@web/views/standard_view_props";

export class MogGanttController extends Component {
    setup() {
        this.rootRef = useRef("root");
        this.model = useModel(this.props.Model, this.props.modelParams);
        useSetupView({ rootRef: this.rootRef });
        this.actionService = useService("action");
        this.notificationService = useService("notification");

        this.state = useState({
            scale: this.model.scale,
            groupMode: this.model.groupMode,
            slotTypeFilter: "all",
        });
    }

    get rendererProps() {
        return {
            model: this.model,
            slotTypeFilter: this.state.slotTypeFilter,
            onSlotUpdated: this.onSlotUpdated.bind(this),
            onSlotCreated: this.onSlotCreated.bind(this),
            onSlotClicked: this.onSlotClicked.bind(this),
        };
    }

    onSlotTypeFilterChange(filter) {
        this.state.slotTypeFilter = filter;
    }

    get defaultCreateType() {
        if (this.state.groupMode === "workcenter") return "workorder";
        return "task";
    }

    // ---- Navigation ----

    async onPrev() {
        this.model.navigatePrev();
        this.state.scale = this.model.scale;
        await this.model.load();
    }

    async onNext() {
        this.model.navigateNext();
        this.state.scale = this.model.scale;
        await this.model.load();
    }

    async onToday() {
        this.model.navigateToday();
        this.state.scale = this.model.scale;
        await this.model.load();
    }

    async onScaleChange(scale) {
        this.model.setScale(scale);
        this.state.scale = scale;
        await this.model.load();
    }

    async onGroupModeChange(mode) {
        this.model.setGroupMode(mode);
        this.state.groupMode = mode;
        await this.model.load();
    }

    // ---- Slot operations ----

    async onSlotUpdated(slotId, vals) {
        try {
            await this.model.updateSlot(slotId, vals);
            this.notificationService.add("Slot updated", { type: "success" });
        } catch (e) {
            this.notificationService.add("Failed to update slot", { type: "danger" });
            await this.model.load();
        }
    }

    async onSlotCreated(rowId, start, end, createType) {
        const slotType = createType || this.defaultCreateType;
        const vals = {
            name: "New Slot",
            start,
            end,
        };
        if (this.model.groupMode === "employee") {
            vals.employee_id = rowId || false;
        } else {
            vals.workcenter_id = rowId || false;
        }

        try {
            const slot = await this.model.createSlot(vals);
            if (slot) {
                this.notificationService.add("Slot created", { type: "success" });
                this.actionService.doAction({
                    type: "ir.actions.act_window",
                    res_model: "planning.slot",
                    res_id: slot.id,
                    views: [[false, "form"]],
                    target: "current",
                });
            }
        } catch (e) {
            this.notificationService.add("Failed to create slot", { type: "danger" });
        }
    }

    onSlotClicked(slot) {
        let resModel = "planning.slot";
        let resId = slot.id;

        if (slot.slot_type === "task" && slot.project_task_id) {
            resModel = "project.task";
            resId = slot.project_task_id;
        } else if (slot.slot_type === "workorder" && slot.mrp_workorder_id) {
            resModel = "mrp.workorder";
            resId = slot.mrp_workorder_id;
        }

        this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            res_id: resId,
            views: [[false, "form"]],
            target: "current",
        });
    }
}

MogGanttController.template = "buz_planning.MogGanttController";
MogGanttController.components = { Layout };
MogGanttController.props = {
    ...standardViewProps,
    Model: Function,
    modelParams: Object,
    Renderer: Function,
};
