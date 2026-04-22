/** @odoo-module **/
/**
 * File: static/src/js/stock_checker_table.js
 * Purpose: OWL sub-components for the stock product table.
 *          - StockCheckerRow: individual product row with editable qty/price
 *          - StockCheckerTable: the full table wrapper
 */

import { Component } from "@odoo/owl";
import { formatQty } from "./stock_checker_filters";

/**
 * StockCheckerRow
 * Renders a single product row in the stock checker table.
 * Handles checkbox toggle, qty input, and price input events.
 */
export class StockCheckerRow extends Component {
    static template = "stock_enhanced_checker.StockCheckerRow";

    static props = {
        product: { type: Object },
        selected: { type: Boolean },
        qty: { type: Number },
        price: { type: Number },
        onToggle: { type: Function },
        onQtyChange: { type: Function },
        onPriceChange: { type: Function },
    };

    /**
     * Format a quantity value for display.
     * @param {number} qty
     * @returns {string}
     */
    formatQty(qty) {
        return formatQty(qty);
    }

    /**
     * Determine the CSS class for the actual available quantity cell
     * based on thresholds.
     *
     * @param {Object} product
     * @returns {string} CSS class string
     */
    availableClass(product) {
        const qty = product.actual_available;
        if (qty <= 0) return 'sc-qty-negative';
        if (qty <= product.low_stock_threshold) return 'sc-qty-warning';
        return 'sc-qty-positive';
    }

    /**
     * Handle qty input event — parse value and propagate upward.
     * @param {InputEvent} ev
     */
    onQtyInput(ev) {
        const val = parseFloat(ev.target.value) || 0;
        this.props.onQtyChange(val);
    }

    /**
     * Handle price input event — parse value and propagate upward.
     * @param {InputEvent} ev
     */
    onPriceInput(ev) {
        const val = parseFloat(ev.target.value) || 0;
        this.props.onPriceChange(val);
    }

    /**
     * Handle qty input focus — auto-select the row if not already selected.
     * This replaces the inline `if` that OWL template compiler cannot handle.
     */
    onQtyFocus() {
        if (!this.props.selected) {
            this.props.onToggle();
        }
    }
}

/**
 * StockCheckerTable
 * Renders the full product stock table with a header checkbox for select-all
 * and a StockCheckerRow for each product.
 */
export class StockCheckerTable extends Component {
    static template = "stock_enhanced_checker.StockCheckerTable";

    static components = { StockCheckerRow };

    static props = {
        products: { type: Array },
        selectedIds: { type: Array },
        qtys: { type: Object },
        prices: { type: Object },
        onToggleAll: { type: Function },
        onToggleRow: { type: Function },
        onQtyChange: { type: Function },
        onPriceChange: { type: Function },
        allSelected: { type: Boolean },
    };
}
