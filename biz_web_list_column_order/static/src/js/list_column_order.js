/** @odoo-module **/

import { ListRenderer } from "@web/views/list/list_renderer";
import { patch } from "@web/core/utils/patch";
import { onMounted, onPatched } from "@odoo/owl";

const STORAGE_PREFIX = "biz_list_col_order";
const WIDTH_PREFIX = "biz_list_col_width";

/**
 * Persist and restore the left-to-right order of *field* columns in backend
 * list views, per user (via localStorage), letting users drag column headers
 * to reorder them.  The shared view definition is never modified.
 */
patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        // Wire native HTML5 drag-and-drop onto the header cells after every
        // render, and keep the applied order in sync with what the user saved.
        onMounted(() => {
            this._colOrderBindHeaders();
            this._colWidthApply();
        });
        onPatched(() => {
            this._colOrderBindHeaders();
            this._colWidthApply();
        });
    },

    /** Remember which column a resize started on, so only it gets persisted. */
    onStartResize(ev) {
        const th = ev.target.closest("th");
        this._colWidthResizingName = (th && th.dataset.name) || null;
        return super.onStartResize(ev);
    },

    /**
     * The base handler runs on pointerup. On Odoo 17 an in-progress resize is
     * tracked via the plain `this.resizing` flag (set in `onStartResize` and
     * cleared by its own window pointerup listener, which fires *after* this
     * one since it's bound on `window` — bubbling reaches the header before
     * it). The final width is already committed to the DOM at that point
     * (it's applied live on every pointermove during the resize), so we read
     * it back and persist it for the column the resize started on.
     */
    onColumnTitleMouseUp(ev) {
        const wasResizing = this.resizing;
        const res = super.onColumnTitleMouseUp(ev);
        if (wasResizing || this.preventReorder) {
            this._colWidthCapture(this._colWidthResizingName);
            this._colWidthResizingName = null;
        }
        return res;
    },

    /**
     * Store the current DOM width of the column named `onlyName` (or of every
     * column when no name is given), merged into the saved width map.
     */
    _colWidthCapture(onlyName) {
        const root = this.tableRef && this.tableRef.el;
        if (!root) {
            return;
        }
        const map = this._colWidthRead() || {};
        root.querySelectorAll("thead th[data-name]").forEach((th) => {
            if (onlyName && th.dataset.name !== onlyName) {
                return;
            }
            const w = Math.round(th.getBoundingClientRect().width);
            if (w > 0) {
                map[th.dataset.name] = w;
            }
        });
        this._colWidthWrite(map);
    },

    /** Reapply saved widths onto matching header cells (and freeze the layout). */
    _colWidthApply() {
        const root = this.tableRef && this.tableRef.el;
        if (!root) {
            return;
        }
        const map = this._colWidthRead();
        if (!map || !Object.keys(map).length) {
            return;
        }
        let applied = false;
        root.querySelectorAll("thead th[data-name]").forEach((th) => {
            const w = map[th.dataset.name];
            if (w) {
                th.style.width = `${w}px`;
                applied = true;
            }
        });
        if (applied) {
            // Match the base hook: fixed layout makes explicit th widths stick.
            root.style.tableLayout = "fixed";
        }
    },

    /**
     * A stable storage key for this particular list. We namespace by model and
     * the current view's id so two different lists on the same model keep
     * separate orders. For an x2many list the config is the enclosing form
     * view's, so embedded lists are still distinguished from standalone ones.
     * localStorage is per browser profile → inherently per user.
     */
    _colOrderStorageKey() {
        const model = this.props.list.resModel || "unknown";
        const viewId = this.env.config?.viewId ?? "default";
        return `${STORAGE_PREFIX}:${model}:${viewId}`;
    },

    /** Same identity as the order key, but a separate namespace for widths. */
    _colWidthStorageKey() {
        return this._colOrderStorageKey().replace(STORAGE_PREFIX, WIDTH_PREFIX);
    },

    _colWidthRead() {
        try {
            const raw = window.localStorage.getItem(this._colWidthStorageKey());
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    },

    _colWidthWrite(map) {
        try {
            window.localStorage.setItem(
                this._colWidthStorageKey(),
                JSON.stringify(map)
            );
        } catch {
            // ignore
        }
    },

    _colWidthClear() {
        try {
            window.localStorage.removeItem(this._colWidthStorageKey());
        } catch {
            // ignore
        }
    },

    _colOrderRead() {
        try {
            const raw = window.localStorage.getItem(this._colOrderStorageKey());
            return raw ? JSON.parse(raw) : null;
        } catch {
            return null;
        }
    },

    _colOrderWrite(names) {
        try {
            window.localStorage.setItem(
                this._colOrderStorageKey(),
                JSON.stringify(names)
            );
        } catch {
            // Storage may be unavailable (private mode / quota) — fail silently.
        }
    },

    _colOrderClear() {
        try {
            window.localStorage.removeItem(this._colOrderStorageKey());
        } catch {
            // ignore
        }
    },

    /**
     * Forget this list's saved order and widths and go back to the default
     * layout (called from the optional-columns ⚙ dropdown). Also drop the base
     * renderer's width cache so `freezeColumnWidths` recomputes from content
     * on the re-render instead of reapplying the resized widths.
     */
    _colLayoutReset() {
        this._colOrderClear();
        this._colWidthClear();
        this.keepColumnWidths = false;
        this.columnWidths = null;
        this.state.columns = this.getActiveColumns(this.props.list);
    },

    /**
     * Override the active-columns computation so the returned columns follow
     * the user's saved order.  Unknown / new columns keep their default
     * relative position at the end.
     */
    getActiveColumns(list) {
        const columns = super.getActiveColumns(list);
        const saved = this._colOrderRead();
        if (!saved || !saved.length) {
            return columns;
        }
        // Only reorder plain field columns: sort them by the saved order and
        // put them back into the field slots, so non-field columns (button
        // groups, …) keep their exact positions.
        const fields = columns.filter((col) => col.type === "field");
        const indexOf = (col) => {
            const i = saved.indexOf(col.name);
            return i === -1 ? saved.length + fields.indexOf(col) : i;
        };
        const sorted = fields.slice().sort((a, b) => indexOf(a) - indexOf(b));
        let f = 0;
        return columns.map((col) => (col.type === "field" ? sorted[f++] : col));
    },

    /**
     * Attach drag handlers to each field header cell. Idempotent: we tag bound
     * cells so repeated renders don't stack listeners.
     */
    _colOrderBindHeaders() {
        const root = this.tableRef && this.tableRef.el;
        if (!root) {
            return;
        }
        const headers = root.querySelectorAll(
            "thead th[data-name]:not([data-col-order-bound])"
        );
        for (const th of headers) {
            th.setAttribute("data-col-order-bound", "1");
            th.setAttribute("draggable", "true");
            th.classList.add("o_col_order_draggable");

            th.addEventListener("dragstart", (ev) => {
                // Don't hijack a column *resize*: if the drag begins on the
                // resize handle (or a resize is in progress), abort the reorder.
                if (
                    (ev.target.closest && ev.target.closest(".o_resize")) ||
                    this.resizing
                ) {
                    ev.preventDefault();
                    return;
                }
                this._colOrderDragName = th.dataset.name;
                ev.dataTransfer.effectAllowed = "move";
                // Some browsers require data to be set for drag to start.
                try {
                    ev.dataTransfer.setData("text/plain", th.dataset.name);
                } catch {
                    // ignore
                }
                th.classList.add("o_col_order_dragging");
            });
            th.addEventListener("dragend", () => {
                th.classList.remove("o_col_order_dragging");
                this._colOrderClearIndicators(root);
                this._colOrderDragName = null;
            });
            // Some views (e.g. Accounting's Invoices/Bills lists, js_class
            // "account_tree") wrap the whole list in a file-drop zone that
            // listens for "dragenter" on the list's root element and, on the
            // very first bubble, shows an upload overlay on top of the table
            // — which then swallows every subsequent dragover/drop, so our
            // column never gets dropped. Stop our own reorder-drag events
            // from bubbling past the header so that overlay never appears;
            // external file drags (which never set _colOrderDragName) are
            // untouched and keep working as before.
            th.addEventListener("dragenter", (ev) => {
                if (this._colOrderDragName) {
                    ev.stopPropagation();
                }
            });
            th.addEventListener("dragover", (ev) => {
                if (!this._colOrderDragName || this._colOrderDragName === th.dataset.name) {
                    return;
                }
                ev.preventDefault();
                ev.stopPropagation();
                ev.dataTransfer.dropEffect = "move";
                this._colOrderClearIndicators(root);
                th.classList.add("o_col_order_drop_target");
            });
            th.addEventListener("dragleave", () => {
                th.classList.remove("o_col_order_drop_target");
            });
            th.addEventListener("drop", (ev) => {
                const from = this._colOrderDragName;
                if (!from) {
                    return;
                }
                ev.preventDefault();
                ev.stopPropagation();
                const to = th.dataset.name;
                this._colOrderClearIndicators(root);
                if (to && from !== to) {
                    this._colOrderMove(from, to);
                }
            });
        }
    },

    _colOrderClearIndicators(root) {
        root
            .querySelectorAll(".o_col_order_drop_target")
            .forEach((el) => el.classList.remove("o_col_order_drop_target"));
    },

    /**
     * Move column `fromName` so it sits immediately before `toName`, then
     * persist and re-render. Works from the currently displayed order so it
     * composes correctly with hidden/optional columns.
     */
    _colOrderMove(fromName, toName) {
        const current = this.state.columns
            .filter((c) => c.type === "field")
            .map((c) => c.name);
        const fromIdx = current.indexOf(fromName);
        const toIdx = current.indexOf(toName);
        if (fromIdx === -1 || toIdx === -1) {
            return;
        }
        current.splice(fromIdx, 1);
        // Re-find target index after removal so we drop *before* the target.
        const insertAt = current.indexOf(toName);
        current.splice(insertAt, 0, fromName);
        this._colOrderWrite(current);
        // Reassigning triggers reactivity (state is an owl useState proxy),
        // no explicit render() call needed on Odoo 17.
        this.state.columns = this.getActiveColumns(this.props.list);
    },
});
