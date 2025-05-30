/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, useState } from "@odoo/owl";

export class TaxReportBackend extends Component {
    static template = "l10n_th_account_tax_report.TaxReportBackend";
    
    setup() {
        this.actionService = useService("action");
        this.rpc = useService("rpc");
        this.state = useState({
            html: "",
        });
        
        this.given_context = {};
        this.odoo_context = this.props.action.context;
        this.controller_url = this.props.action.context.url;
        
        if (this.props.action.context.context) {
            this.given_context = this.props.action.context.context;
        }
        this.given_context.active_id =
            this.props.action.context.active_id || this.props.action.params?.active_id;
        this.given_context.model = this.props.action.context.active_model || false;
        this.given_context.ttype = this.props.action.context.ttype || false;
        
        onMounted(async () => {
            await this.get_html();
        });
    }

    // Fetches the html and is previous report.context if any,
    // else create it
    async get_html() {
        try {
            const result = await this.rpc({
                model: this.given_context.model,
                method: "get_html",
                args: [this.given_context],
                context: this.odoo_context,
            });
            this.state.html = result.html || "";
        } catch (error) {
            console.error("Error fetching report HTML:", error);
            this.state.html = "<div>Error loading report</div>";
        }
    }

    async print() {
        try {
            const result = await this.rpc({
                model: this.given_context.model,
                method: "print_report",
                args: [this.given_context.active_id, "qweb-pdf"],
                context: this.odoo_context,
            });
            this.actionService.doAction(result);
        } catch (error) {
            console.error("Error printing report:", error);
        }
    }

    async export() {
        try {
            const result = await this.rpc({
                model: this.given_context.model,
                method: "print_report",
                args: [this.given_context.active_id, "xlsx"],
                context: this.odoo_context,
            });
            this.actionService.doAction(result);
        } catch (error) {
            console.error("Error exporting report:", error);
        }
    }
}

registry.category("actions").add("l10n_th_account_tax_report_backend", TaxReportBackend);
