/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component } from "@odoo/owl";

export class FifoResetResult extends Component {
    get parsedResult() {
        if (!this.props.record.data[this.props.name]) {
            return null;
        }
        try {
            return JSON.parse(this.props.record.data[this.props.name]);
        } catch (e) {
            return null;
        }
    }
}

FifoResetResult.template = "fifo_reset_engine.FifoResetResult";
FifoResetResult.props = {
    ...standardFieldProps,
};

export const fifoResetResult = {
    component: FifoResetResult,
    supportedTypes: ["char", "text"],
};

registry.category("fields").add("fifo_reset_result", fifoResetResult);
