/** @odoo-module **/

import { Component, useState, onWillStart, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const FILTERS = [
    { key: "all", label: "ทั้งหมด" },
    { key: "low_stock", label: "ใกล้หมด" },
    { key: "out_of_stock", label: "หมดสต็อก" },
    { key: "in_cart", label: "ในตะกร้า" },
];

export class ProductCard extends Component {
    static template = "buz_it_consumable_store.ProductCard";
    static props = {
        item: { type: Object },
        busy: { type: Boolean },
        onAdd: { type: Function },
        onRemove: { type: Function },
    };
}

export class CartPanel extends Component {
    static template = "buz_it_consumable_store.CartPanel";
    static props = {
        cart: { type: Object },
        busy: { type: Boolean },
        submitting: { type: Boolean },
        onSubmit: { type: Function },
        onClear: { type: Function },
        onQtyChange: { type: Function },
        onQtyInput: { type: Function },
        onRemoveLine: { type: Function },
    };
}

export class ConsumableStoreAction extends Component {
    static template = "buz_it_consumable_store.Store";
    static components = { ProductCard, CartPanel };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.filters = FILTERS;
        this.state = useState({
            loading: true,
            busy: false,
            submitting: false,
            search: "",
            filter: "all",
            activeCategory: false,
            categories: [],
            items: [],
            cart: this._emptyCart(),
        });

        onWillStart(() => this._init());
        onMounted(() => {
            window.addEventListener("focus", this._onWindowFocus);
            this._pollTimer = setInterval(() => this._refreshCart(), 30000);
        });
        onWillUnmount(() => {
            window.removeEventListener("focus", this._onWindowFocus);
            clearInterval(this._pollTimer);
        });
    }

    _emptyCart() {
        return { id: false, name: false, lines: [], line_count: 0, total_qty: 0 };
    }

    get filteredItems() {
        const q = this.state.search.trim().toLowerCase();
        let items = this.state.items;
        if (this.state.activeCategory !== false) {
            items = items.filter((i) => i.category_id === this.state.activeCategory);
        }
        if (q) {
            items = items.filter(
                (i) =>
                    (i.name || "").toLowerCase().includes(q) ||
                    (i.category_name || "").toLowerCase().includes(q) ||
                    (i.description || "").toLowerCase().includes(q)
            );
        }
        if (this.state.filter === "low_stock") {
            items = items.filter((i) => i.low_stock);
        } else if (this.state.filter === "out_of_stock") {
            items = items.filter((i) => i.on_hand_qty === 0);
        } else if (this.state.filter === "in_cart") {
            items = items.filter((i) => i.cart_qty > 0);
        }
        return items;
    }

    async _init() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("buz.it.consumable.request", "get_store_data", []);
            this.state.categories = data.categories;
            this.state.items = data.items;
            this._applyCart(data.cart);
        } catch (err) {
            this._notifyError(err, "ไม่สามารถโหลดข้อมูลหน้าร้านได้");
        } finally {
            this.state.loading = false;
        }
    }

    _applyCart(cart) {
        this.state.cart = cart;
        const qtyMap = {};
        for (const line of cart.lines) {
            qtyMap[line.consumable_id] = line.qty;
        }
        for (const item of this.state.items) {
            item.cart_qty = qtyMap[item.id] || 0;
        }
    }

    async _refreshCart() {
        if (this.state.busy || this._refreshing) return;
        this._refreshing = true;
        try {
            const data = await this.orm.call("buz.it.consumable.request", "get_cart_data", []);
            this._applyCart(data.cart);
        } catch (_) {
        } finally {
            this._refreshing = false;
        }
    }

    _onWindowFocus = () => {
        this._refreshCart();
    };

    selectCategory(id) {
        this.state.activeCategory = this.state.activeCategory === id ? false : id;
    }

    setFilter(key) {
        this.state.filter = key;
    }

    onSearchInput(ev) {
        this.state.search = ev.target.value;
    }

    async onAdd(item) {
        await this._mutate(() => this.orm.call("buz.it.consumable.request", "cart_add", [item.id, 1]));
    }

    async onRemove(item) {
        const qty = item.cart_qty > 0 ? item.cart_qty - 1 : 0;
        await this._mutate(() =>
            this.orm.call("buz.it.consumable.request", "cart_set_qty", [item.id, qty])
        );
    }

    async onQtyChange(consumableId, qty) {
        if (!isFinite(qty) || qty < 0) return;
        await this._mutate(() =>
            this.orm.call("buz.it.consumable.request", "cart_set_qty", [consumableId, qty])
        );
    }

    async onCartQtyInput(consumableId, ev) {
        const val = Math.floor(parseFloat(ev.target.value) || 0);
        if (!isFinite(val) || val < 0) return;
        await this.onQtyChange(consumableId, val);
    }

    async onRemoveLine(consumableId) {
        await this._mutate(() =>
            this.orm.call("buz.it.consumable.request", "cart_remove", [consumableId])
        );
    }

    async onClearCart() {
        await this._mutate(() => this.orm.call("buz.it.consumable.request", "cart_clear", []));
    }

    async onSubmit() {
        if (this.state.submitting || this.state.cart.line_count === 0) return;
        this.state.submitting = true;
        try {
            const result = await this.orm.call("buz.it.consumable.request", "cart_submit", []);
            this.notification.add(`ส่งคำขอ ${result.name} แล้ว`, {
                type: "success",
            });
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: "buz.it.consumable.request",
                res_id: result.id,
                views: [[false, "form"]],
            });
        } catch (err) {
            this._notifyError(err, "ส่งคำขอไม่สำเร็จ");
            await this._init();
        } finally {
            this.state.submitting = false;
        }
    }

    async onOpenCart() {
        try {
            await this.action.doAction(
                await this.orm.call("buz.it.consumable.request", "cart_open", [])
            );
        } catch (err) {
            this._notifyError(err, "ยังไม่มีรายการในตะกร้า");
        }
    }

    async _mutate(fn) {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            const result = await fn();
            this._applyCart(result.cart);
        } catch (err) {
            this._notifyError(err, "ดำเนินการไม่สำเร็จ");
            await this._init();
        } finally {
            this.state.busy = false;
        }
    }

    _notifyError(err, fallback) {
        const msg = this._extractMessage(err);
        this.notification.add(msg || fallback, { type: "danger" });
    }

    _extractMessage(err) {
        if (err && err.data && err.data.message) {
            const m = String(err.data.message).match(/UserError:\s*(.+)/);
            if (m) return m[1];
            return String(err.data.message);
        }
        const raw = err && err.message ? String(err.message) : "";
        const m = raw.match(/UserError:\s*(.+)/);
        if (m) return m[1];
        const m2 = raw.match(/"message"\s*:\s*"((?:\\.|[^"\\])*)"/);
        if (m2) return m2[1];
        return raw || "";
    }
}

registry.category("actions").add("buz_it_consumable_store.Store", ConsumableStoreAction);
