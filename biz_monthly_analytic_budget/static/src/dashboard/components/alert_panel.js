/** @odoo-module */
import { Component } from "@odoo/owl";

export class AlertPanel extends Component {
    static template = "biz_monthly_analytic_budget.AlertPanel";
    static props = {
        data: { type: Array, optional: true }
    };
}
