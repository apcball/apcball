/** @odoo-module **/
/**
 * File: static/src/js/stock_checker_filters.js
 * Purpose: Filter config, debounce, and formatting utilities.
 */

/**
 * Filter definitions with icons for the filter bar pills.
 */
export const STOCK_FILTERS = [
    { key: 'all',          label: 'All',         icon: 'th-large' },
    { key: 'in_stock',     label: 'In Stock',    icon: 'check-circle' },
    { key: 'out_of_stock', label: 'Out of Stock', icon: 'times-circle' },
    { key: 'low_stock',    label: 'Low Stock',   icon: 'exclamation-circle' },
];

/**
 * Debounce helper.
 * @param {Function} fn
 * @param {number} delay
 * @returns {Function}
 */
export function debounce(fn, delay = 300) {
    let timer = null;
    return function (...args) {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => {
            timer = null;
            fn.apply(this, args);
        }, delay);
    };
}

/**
 * Format a numeric quantity for display.
 * @param {number} qty
 * @returns {string}
 */
export function formatQty(qty) {
    if (qty === null || qty === undefined || isNaN(qty)) return '0';
    const n = parseFloat(qty);
    return n.toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 3,
    });
}
