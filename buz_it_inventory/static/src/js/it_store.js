/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ITEM_MODEL = "buz.it.inventory.item";
const CATEGORY_MODEL = "buz.it.inventory.item.category";

export class ItStore extends Component {
    static template = "buz_it_inventory.ItStore";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ categories: [], items: [], search: "", categoryId: null, cart: {}, loading: true, submitting: false });
        onWillStart(() => this.loadCatalog());
    }

    async loadCatalog() {
        this.state.loading = true;
        try {
            const [items, categories] = await Promise.all([
                this.orm.searchRead(ITEM_MODEL, [["active", "=", true], ["is_published", "=", true]], [
                    "name", "image_1920", "category_id", "item_type", "unit", "description",
                    "available_qty", "max_per_request", "store_status",
                ], { order: "category_id, name" }),
                this.orm.searchRead(CATEGORY_MODEL, [], ["name"], { order: "name" }),
            ]);
            this.state.items = items;
            this.state.categories = categories;
        } finally {
            this.state.loading = false;
        }
    }

    get filteredItems() {
        const query = this.state.search.trim().toLowerCase();
        return this.state.items.filter((item) => {
            const categoryId = item.category_id && item.category_id[0];
            const categoryName = item.category_id && item.category_id[1];
            const matchesCategory = !this.state.categoryId || categoryId === this.state.categoryId;
            const searchable = [item.name, categoryName, item.description].filter(Boolean).join(" ").toLowerCase();
            return matchesCategory && (!query || searchable.includes(query));
        });
    }

    get cartLines() {
        return Object.entries(this.state.cart).map(([id, quantity]) => {
            const item = this.state.items.find((candidate) => candidate.id === Number(id));
            return item ? { item, quantity } : null;
        }).filter(Boolean);
    }

    get cartCount() { return this.cartLines.reduce((total, line) => total + line.quantity, 0); }
    selectCategory(categoryId) { this.state.categoryId = categoryId; }
    maxQuantity(item) { return item.max_per_request > 0 ? Math.min(item.available_qty, item.max_per_request) : item.available_qty; }
    cartQuantity(item) { return this.state.cart[item.id] || 0; }
    canIncrease(item) { return this.cartQuantity(item) < this.maxQuantity(item); }

    setCartQuantity(item, quantity) {
        const bounded = Math.max(0, Math.min(quantity, this.maxQuantity(item)));
        const cart = { ...this.state.cart };
        if (bounded) { cart[item.id] = bounded; } else { delete cart[item.id]; }
        this.state.cart = cart;
    }

    addItem(item) { if (this.maxQuantity(item)) this.setCartQuantity(item, this.cartQuantity(item) + 1); }
    removeItem(item) { this.setCartQuantity(item, 0); }
    imageUrl(item) { return `/web/image?model=${ITEM_MODEL}&field=image_1920&id=${item.id}`; }
    statusLabel(item) { return { ready: "พร้อมเบิก", low: "ใกล้หมด", out: "หมด" }[item.store_status] || "ไม่พร้อมเบิก"; }

    async createRequest() {
        if (!this.cartLines.length || this.state.submitting) return;
        this.state.submitting = true;
        try {
            const action = await this.orm.call(ITEM_MODEL, "action_create_store_request", [
                this.cartLines.map(({ item, quantity }) => ({ item_id: item.id, quantity })),
            ]);
            await this.action.doAction(action);
        } catch (error) {
            this.notification.add(error.message || "ไม่สามารถสร้างคำขอเบิกได้", { type: "danger" });
            await this.loadCatalog();
        } finally {
            this.state.submitting = false;
        }
    }
}

registry.category("actions").add("buz_it_inventory.store", ItStore);
