/** @odoo-module **/

import { Component } from "@odoo/owl";

export class MainPanel extends Component {
    static template = "buz_new_stock_card.MainPanel";
    static props = [
        "state", "onToggleShowMovementsOnly", "onChangePage", "onChangePageSize", "openDocument",
    ];

    fmt(n) {
        return (n || 0).toFixed(2);
    }

    onDocClick(line) {
        if (line.res_model && line.res_id) {
            this.props.openDocument(line.res_model, line.res_id);
        }
    }

    get pageStart() {
        if (!this.props.state.cardData || !this.props.state.cardData.total_count) {
            return 0;
        }
        return this.props.state.page * this.props.state.pageSize + 1;
    }

    get pageEnd() {
        const d = this.props.state.cardData;
        if (!d) {
            return 0;
        }
        return Math.min(this.pageStart + d.lines.length - 1, d.total_count);
    }

    onPageSizeChange(ev) {
        this.props.onChangePageSize(parseInt(ev.target.value, 10));
    }

    get lastPage() {
        const d = this.props.state.cardData;
        if (!d || !d.page_size) {
            return 0;
        }
        return Math.max(0, Math.ceil(d.total_count / d.page_size) - 1);
    }
}
