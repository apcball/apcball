/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { ImportUploader } from "./import_uploader";

export class ImportDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            sessions: []
        });

        onWillStart(async () => {
            await this.loadSessions();
        });
        this.loadSessions = this.loadSessions.bind(this);
    }

    async loadSessions() {
        this.state.sessions = await this.orm.searchRead('mrp.import.session', [], ['name', 'import_type', 'state', 'total_records', 'success_records', 'failed_records', 'create_date']);
    }

    openSession(sessionId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'mrp.import.session',
            res_id: sessionId,
            views: [[false, 'form']],
            target: 'current'
        });
    }
}

ImportDashboard.template = "mrp_import_engine.Dashboard";
ImportDashboard.components = { ImportUploader };

registry.category("actions").add("mrp_import_engine.dashboard", ImportDashboard);
