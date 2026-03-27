/** @odoo-module */
import { Component } from "@odoo/owl";

export class KpiCards extends Component {
    static template = "biz_monthly_analytic_budget.KpiCards";
    static props = {
        data: { type: Object, optional: true }
    };

    get formatCurrency() {
        return (value) => {
            if (value === undefined || value === null) return "0.00";
            return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        };
    }
}
