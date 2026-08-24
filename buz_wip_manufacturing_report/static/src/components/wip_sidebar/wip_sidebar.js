/** @odoo-module **/

import { Component } from "@odoo/owl";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";

export class WipSidebar extends Component {
    static template = "buz_wip_manufacturing_report.WipSidebar";
    static components = { MultiRecordSelector };
    static props = [
        "state", "onSetDateFrom", "onSetDateTo", "onSetMoIds", "onSetProductIds",
        "onSetComponentIds", "onSetLocationIds", "onToggleStatus", "onSetCostSource",
        "onToggleValuationDetail", "onReset",
    ];

    onDateFromChange(ev) {
        this.props.onSetDateFrom(ev.target.value);
    }

    onDateToChange(ev) {
        this.props.onSetDateTo(ev.target.value);
    }

    onStatusChange(value, ev) {
        this.props.onToggleStatus(value, ev.target.checked);
        // "In Progress" (UI) covers both the progress and to_close MO
        // states; keep them toggled together so unchecking one doesn't
        // leave the other silently still included.
        if (value === "progress") {
            this.props.onToggleStatus("to_close", ev.target.checked);
        }
    }

    onCostSourceChange(ev) {
        this.props.onSetCostSource(ev.target.value);
    }

    isStatusChecked(value) {
        return this.props.state.statusList.includes(value);
    }
}
