/** @odoo-module **/

import { Component } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { KanbanRecord } from "@web/views/kanban/kanban_record";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

patch(KanbanRecord.prototype, {
    /**
     * Override openRecord method to open the appropriate form view
     * based on the ticket category
     */
    openRecord() {
        // Check if this is an IT ticket kanban view
        if (this.props.resModel === 'it.ticket') {
            const record = this.props.record;
            const category = record.data.category;
            
            // Define form view IDs for each category
            const formViewIds = {
                'issue': 'buz_it_ticket.view_it_ticket_issue_form',
                'access': 'buz_it_ticket.view_it_ticket_access_form',
                'purchase': 'buz_it_ticket.view_it_ticket_purchase_form',
            };
            
            // Get the appropriate form view ID
            const formViewId = formViewIds[category] || false;
            
            // Create action to open the form
            const action = {
                type: 'ir.actions.act_window',
                res_model: 'it.ticket',
                res_id: record.resId,
                views: [[formViewId, 'form']],
                target: 'current',
            };
            
            // Execute the action
            this.env.services.action.doAction(action);
            return;
        }
        
        // For non-IT ticket models, use the default behavior
        return this._super(...arguments);
    },
});

export class ItTicketDashboard extends Component {
    setup() {
        console.log("Loading IT Ticket dashboard...");
    }
}

ItTicketDashboard.template = 'buz_it_ticket.ItTicketDashboard';