/** @odoo-module **/

import { onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import { KanbanRenderer } from "@web/views/kanban/kanban_renderer";

patch(KanbanRenderer.prototype, {
    setup() {
        super.setup();
        this.helpdeskStageVisibility = useState({
            loaded: false,
            visibleIds: null,
        });
        this.orm = useService("orm");

        onWillStart(async () => {
            if (!this.isHelpdeskStageKanban()) {
                this.helpdeskStageVisibility.loaded = true;
                return;
            }
            try {
                const stages = await this.orm.searchRead(
                    "buz.helpdesk.stage",
                    [
                        ["active", "=", true],
                        ["show_in_kanban", "=", true],
                    ],
                    ["id"]
                );
                this.helpdeskStageVisibility.visibleIds = new Set(
                    stages.map((stage) => stage.id)
                );
            } catch {
                // Keep all groups visible if the optional visibility lookup
                // cannot be completed, so the Kanban remains usable.
                this.helpdeskStageVisibility.visibleIds = null;
            } finally {
                this.helpdeskStageVisibility.loaded = true;
            }
        });
    },

    isHelpdeskStageKanban() {
        const stageField = this.props.list.fields?.stage_id;
        return Boolean(
            this.props.list.isGrouped &&
                this.props.list.groupByField?.name === "stage_id" &&
                stageField?.relation === "buz.helpdesk.stage"
        );
    },

    getGroupsOrRecords() {
        const groupsOrRecords = super.getGroupsOrRecords();
        const visibleIds = this.helpdeskStageVisibility?.visibleIds;
        if (!this.isHelpdeskStageKanban() || !visibleIds) {
            return groupsOrRecords;
        }
        return groupsOrRecords.filter(({ group }) => {
            // Keep the empty/unassigned group, if Odoo creates one.
            return !group || !group.value || visibleIds.has(Number(group.value));
        });
    },
});
