/** @odoo-module **/

import { Component } from "@odoo/owl";

export class SummaryCards extends Component {
    static template = "buz_wip_manufacturing_report.SummaryCards";
    static props = ["summary"];

    fmt(n, decimals = 2) {
        return (n || 0).toLocaleString(undefined, {
            minimumFractionDigits: decimals, maximumFractionDigits: decimals,
        });
    }
}
