/** @odoo-module **/
/**
 * File: static/src/js/stock_checker_filters.js
 * Purpose: Filter configuration and search debounce utilities
 *          for the Stock Enhanced Checker dashboard.
 */

/**
 * Available filter configurations for the stock checker.
 * Each filter has a key (sent to backend) and a display label.
 */
export const STOCK_FILTERS = [
    { key: 'all',          label: 'All Products' },
    { key: 'in_stock',     label: 'In Stock' },
    { key: 'out_of_stock', label: 'Out of Stock' },
    { key: 'low_stock',    label: 'Low Stock' },
];

/**
 * Create a debounced version of a function.
 * The returned function delays invoking `fn` until after `delay` ms
 * have elapsed since the last time the debounced function was invoked.
 *
 * @param {Function} fn - Function to debounce
 * @param {number} delay - Delay in milliseconds (default 300)
 * @returns {Function} Debounced function
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
 * Shows up to 3 decimal places, removing trailing zeros.
 *
 * @param {number} qty - The quantity value
 * @returns {string} Formatted string
 */
export function formatQty(qty) {
    if (qty === null || qty === undefined || isNaN(qty)) return '0';
    const n = parseFloat(qty);
    // Show up to 3 decimals, strip trailing zeros
    return n.toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 3,
    });
}
