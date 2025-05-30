/** @odoo-module **/

import { Component } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class WithholdingTaxReportWidget extends Component {
    static template = "l10n_th_account_tax_report.WithholdingTaxReportWidget";
    
    setup() {
        this.actionService = useService("action");
    }

    boundLink(e) {
        const res_model = e.target.dataset.resModel;
        const res_id = parseInt(e.target.dataset.activeId);
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: res_model,
            res_id: res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    boundLinkmulti(e) {
        let res_model = e.target.dataset.resModel;
        let domain = e.target.dataset.domain;
        if (!res_model) {
            res_model = e.target.parentElement.dataset.resModel;
        }
        if (!domain) {
            domain = e.target.parentElement.dataset.domain;
        }
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            name: this._toTitleCase(res_model.split(".").join(" ")),
            res_model: res_model,
            domain: JSON.parse(domain),
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    boundLinkMonetary(e) {
        const res_model = e.target.parentElement.dataset.resModel;
        const res_id = parseInt(e.target.parentElement.dataset.activeId);
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: res_model,
            res_id: res_id,
            views: [[false, "form"]],
            target: "current",
        });
    }

    boundLinkMonetarymulti(e) {
        const res_model = e.target.parentElement.dataset.resModel;
        const domain = e.target.parentElement.dataset.domain;
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: res_model,
            domain: JSON.parse(domain),
            views: [
                [false, "list"],
                [false, "form"],
            ],
            target: "current",
        });
    }

    _toTitleCase(str) {
        return str.replace(/\w\S*/g, function (txt) {
            return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
        });
    }
}
