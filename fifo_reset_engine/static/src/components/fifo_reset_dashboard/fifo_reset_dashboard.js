/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onWillUpdateProps } from "@odoo/owl";

export class FifoResetDashboard extends Component {
    setup() {
        this.parseData(this.props);
        onWillUpdateProps((nextProps) => {
            this.parseData(nextProps);
        });
    }

    parseData(props) {
        this.kpiData = {
            open_pickings: 0,
            reserved_qty: 0,
            total_products: 0,
            total_stock_value: 0,
            currency_symbol: '$',
        };
        if (props.record.data[props.name]) {
            try {
                this.kpiData = JSON.parse(props.record.data[props.name]);
            } catch (e) {
                console.error("Invalid KPI Data:", e);
            }
        }
    }
}

FifoResetDashboard.template = "fifo_reset_engine.FifoResetDashboard";
FifoResetDashboard.props = {
    ...standardFieldProps,
};

export const fifoResetDashboard = {
    component: FifoResetDashboard,
    supportedTypes: ["char", "text"],
};

registry.category("fields").add("fifo_reset_dashboard", fifoResetDashboard);
