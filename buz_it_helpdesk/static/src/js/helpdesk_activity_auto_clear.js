/** @odoo-module **/

import { ActivityController } from "@mail/views/web/activity/activity_controller";
import { patch } from "@web/core/utils/patch";

patch(ActivityController.prototype, {
    async openRecord(record, mode) {
        if (this.props.resModel === "it.helpdesk.ticket") {
            await this.model.orm.call(
                "it.helpdesk.ticket",
                "action_clear_new_ticket_activity",
                [[record.resId]]
            );
        }
        return super.openRecord(record, mode);
    },
});