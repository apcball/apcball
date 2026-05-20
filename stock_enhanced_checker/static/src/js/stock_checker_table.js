/** @odoo-module **/
/**
 * File: static/src/js/stock_checker_table.js
 * Purpose: OWL sub-components for stock product cards.
 *          - StockCheckerRow: individual product card with editable qty/price
 *          - StockCheckerTable: renders the list of StockCheckerRow items
 */

import { Component } from "@odoo/owl";
import { formatQty } from "./stock_checker_filters";

export class StockCheckerRow extends Component {
    static template = "stock_enhanced_checker.StockCheckerRow";

    static props = {
        product: { type: Object },
        selected: { type: Boolean },
        qty: { type: Number },
        price: { type: Number },
        canCreateQuotation: { type: Boolean },
        onToggle: { type: Function },
        onQtyChange: { type: Function },
        onPriceChange: { type: Function },
    };

    formatQty(qty) {
        return formatQty(qty);
    }

    /**
     * Returns the CSS class for the available qty badge.
     */
    availableClass(product) {
        const qty = product.actual_available;
        if (qty <= 0) return 'sc-avail-bad';
        if (qty <= product.low_stock_threshold) return 'sc-avail-warn';
        return 'sc-avail-ok';
    }

    onQtyInput(ev) {
        const val = parseFloat(ev.target.value) || 0;
        this.props.onQtyChange(val);
    }

    onPriceInput(ev) {
        const val = parseFloat(ev.target.value) || 0;
        this.props.onPriceChange(val);
    }

    onQtyFocus() {
        if (!this.props.selected) {
            this.props.onToggle();
        }
    }
}

export class StockCheckerTable extends Component {
    static template = "stock_enhanced_checker.StockCheckerTable";

    static components = { StockCheckerRow };

    static props = {
        products: { type: Array },
        selectedIds: { type: Array },
        qtys: { type: Object },
        prices: { type: Object },
        onToggleRow: { type: Function },
        onQtyChange: { type: Function },
        onPriceChange: { type: Function },
        canCreateQuotation: { type: Boolean },
    };
}
