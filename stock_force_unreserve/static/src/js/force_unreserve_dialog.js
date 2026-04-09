/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class ForceUnreserveDialog extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        
        this.state = useState({
            loading: true,
            executing: false,
            insight: {
                picking_name: "",
                lines: [],
                competing_pickings: []
            }
        });

        onWillStart(async () => {
            this.pickingId = this.props.action.context.active_id;
            await this.loadInsightData();
        });
    }

    async loadInsightData() {
        try {
            const data = await this.orm.call("stock.picking", "get_reservation_insight_data", [this.pickingId]);
            this.state.insight = data;
        } catch (error) {
            console.error(error);
            this.notification.add("Failed to load insight data", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async confirm() {
        if (this.state.executing) return;
        this.state.executing = true;

        try {
            const result = await this.orm.call("stock.picking", "action_execute_force_unreserve", [[this.pickingId]]);
            
            if (result.status === "success") {
                this.notification.add("Stock successfully reallocated.", { type: "success" });
            } else if (result.status === "partial") {
                this.notification.add("Partial reallocation completed. Some products are still unavailable.", { type: "warning" });
            } else {
                this.notification.add("Unable to reallocate stock.", { type: "danger" });
            }
            
            this.action.doAction({ type: "ir.actions.act_window_close" });
            this.action.doAction({ type: "ir.actions.client", tag: "reload" });
        } catch (error) {
            this.notification.add("An error occurred during forced unreserve.", { type: "danger" });
            console.error(error);
        } finally {
            this.state.executing = false;
        }
    }

    cancel() {
        this.action.doAction({ type: "ir.actions.act_window_close" });
    }
}

ForceUnreserveDialog.template = "stock_force_unreserve.ForceUnreserveDialog";

registry.category("actions").add("stock_force_unreserve.force_unreserve_dialog", ForceUnreserveDialog);
