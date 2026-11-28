/** @odoo-module **/

import { Component, useExternalListener, useRef, useState } from "@odoo/owl";

export class SalesDashboardMultiSelect extends Component {
    static template = "buz_sales_dashboard.MultiSelect";
    static props = {
        label: String,
        choices: Array,
        selected: Array,
        onChange: Function,
    };

    setup() {
        this.root = useRef("root");
        this.state = useState({ open: false, search: "" });
        useExternalListener(window, "click", (ev) => {
            if (this.root.el && !this.root.el.contains(ev.target)) {
                this.state.open = false;
            }
        }, { capture: true });
    }

    get shown() {
        const term = this.state.search.trim().toLowerCase();
        return this.props.choices.filter((c) => c.name.toLowerCase().includes(term));
    }

    get summary() {
        const names = this.props.choices
            .filter((c) => this.props.selected.includes(c.id))
            .map((c) => c.name);
        if (!this.props.selected.length) {
            return "ทั้งหมด";
        }
        return names.length === 1 ? names[0] : `${this.props.selected.length} รายการ`;
    }

    toggle(id) {
        const selected = this.props.selected.includes(id)
            ? this.props.selected.filter((v) => v !== id)
            : [...this.props.selected, id];
        this.props.onChange(selected);
    }

    selectShown() {
        const ids = new Set([...this.props.selected, ...this.shown.map((c) => c.id)]);
        this.props.onChange([...ids]);
    }

    clear() {
        this.props.onChange([]);
    }
}
