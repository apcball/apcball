/** @odoo-module **/

import { Component, useState } from "@odoo/owl";

export class LocationTree extends Component {
    static template = "buz_new_stock_card.LocationTree";
    static components = {};
    static props = ["nodes", "counts", "selectedId", "onSelect"];

    setup() {
        this.state = useState({ expanded: new Set() });
    }

    isExpanded(id) {
        return this.state.expanded.has(id);
    }

    toggle(id) {
        if (this.state.expanded.has(id)) {
            this.state.expanded.delete(id);
        } else {
            this.state.expanded.add(id);
        }
    }

    select(node) {
        this.props.onSelect(node.id, node.display_name || node.name, node.selectable);
    }

    getCount(id) {
        return this.props.counts[id] || 0;
    }
}
LocationTree.components = { LocationTree };
