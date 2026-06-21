/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";

let mediaQuery = null;

/**
 * Apply dark mode by toggling .o_webclient_dark on body.
 * Reads config parameter from session (set by backend).
 */
function applyDark(enabled) {
    document.body.classList.toggle("o_webclient_dark", enabled);
}

function getMode() {
    // session_info injected by backend
    return session.buz_theme_odoo19_dark_mode || "os";
}

function applyCurrentMode() {
    const mode = getMode();
    if (mode === "always") {
        applyDark(true);
    } else if (mode === "os") {
        applyDark(false);
    } else if (mode === "system") {
        const mq = window.matchMedia("(prefers-color-scheme: dark)");
        applyDark(mq.matches);
        if (!mediaQuery) {
            mediaQuery = mq;
            mediaQuery.addEventListener("change", (e) => applyDark(e.matches));
        }
    } else {
        // "user" — let Odoo native handle it (nothing)
    }
}

// Run on page load
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyCurrentMode);
} else {
    applyCurrentMode();
}
