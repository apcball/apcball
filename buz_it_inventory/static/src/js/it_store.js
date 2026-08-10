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
        this.notification = useService("notification");
        this.state = useState({ categories: [], items: [], search: "", categoryId: null, cart: {}, selections: {}, loading: true, submitting: false, modalOpen: false, modalSubmitting: false, requesterName: "", departmentName: "" });
        this.loadCatalog = this.loadCatalog.bind(this);
        this.selectCategory = this.selectCategory.bind(this);
        this.selectionQuantity = this.selectionQuantity.bind(this);
        this.canIncreaseSelection = this.canIncreaseSelection.bind(this);
        this.setSelectionQuantity = this.setSelectionQuantity.bind(this);
        this.addSelectedItem = this.addSelectedItem.bind(this);
        this.removeItem = this.removeItem.bind(this);
        this.openCreateModal = this.openCreateModal.bind(this);
        this.closeModal = this.closeModal.bind(this);
        this.confirmCreate = this.confirmCreate.bind(this);
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
    remainingQuantity(item) { return Math.max(0, this.maxQuantity(item) - this.cartQuantity(item)); }
    selectionQuantity(item) {
        const remaining = this.remainingQuantity(item);
        return remaining ? Math.min(this.state.selections[item.id] || 1, remaining) : 0;
    }
    canIncreaseSelection(item) { return this.selectionQuantity(item) < this.remainingQuantity(item); }

    setSelectionQuantity(item, quantity) {
        const remaining = this.remainingQuantity(item);
        const selections = { ...this.state.selections };
        if (remaining) {
            selections[item.id] = Math.max(1, Math.min(quantity, remaining));
        } else {
            delete selections[item.id];
        }
        this.state.selections = selections;
    }

    setCartQuantity(item, quantity) {
        const bounded = Math.max(0, Math.min(quantity, this.maxQuantity(item)));
        const cart = { ...this.state.cart };
        if (bounded) { cart[item.id] = bounded; } else { delete cart[item.id]; }
        this.state.cart = cart;
    }

    addSelectedItem(item) {
        const quantity = this.selectionQuantity(item);
        if (!quantity) return;
        this.setCartQuantity(item, this.cartQuantity(item) + quantity);
        const selections = { ...this.state.selections };
        delete selections[item.id];
        this.state.selections = selections;
    }
    removeItem(item) { this.setCartQuantity(item, 0); }
    imageUrl(item) { return `/web/image?model=${ITEM_MODEL}&field=image_1920&id=${item.id}`; }
    itemTypeLabel(item) { return { consumable: "วัสดุสิ้นเปลือง", non_serialized_equipment: "อุปกรณ์ไม่ระบุหมายเลข" }[item.item_type] || (item.category_id && item.category_id[1]) || "ทั่วไป"; }
    statusLabel(item) { return { ready: "พร้อมเบิก", low: "ใกล้หมด", out: "หมด" }[item.store_status] || "ไม่พร้อมเบิก"; }
    get departmentLabel() { return this.state.departmentName || "ไม่ระบุแผนก"; }

    async openCreateModal() {
        if (!this.cartLines.length || this.state.submitting || this.state.modalOpen) return;
        this.state.submitting = true;
        try {
            const summary = await this.orm.call(ITEM_MODEL, "get_store_requester_summary", []);
            this.state.requesterName = summary.requester_name;
            this.state.departmentName = summary.department_name;
            this.state.modalOpen = true;
        } catch (error) {
            this.notification.add(error.message || "ไม่สามารถแสดงข้อมูลผู้ขอได้", { type: "danger" });
            await this.loadCatalog();
        } finally {
            this.state.submitting = false;
        }
    }

    closeModal() {
        if (this.state.modalSubmitting) return;
        this.state.modalOpen = false;
    }

    async confirmCreate() {
        if (!this.state.modalOpen || this.state.modalSubmitting || this.state.submitting) return;
        this.state.modalSubmitting = true;
        try {
            const result = await this.orm.call(ITEM_MODEL, "action_create_and_submit_store_request", [
                this.cartLines.map(({ item, quantity }) => ({ item_id: item.id, quantity })),
            ]);
            this.state.modalOpen = false;
            this.state.cart = {};
            this.state.selections = {};
            if (result.activity_count > 0) {
                this.notification.add("ส่งคำขอให้ IT แล้ว" + (result.request_name ? `: ${result.request_name}` : ""), { type: "success" });
            } else {
                this.notification.add("ส่งคำขอให้ IT แล้ว แต่ยังไม่มีผู้ใช้ IT รับการแจ้งเตือน", { type: "warning" });
            }
            await this.loadCatalog();
        } catch (error) {
            this.notification.add(error.message || "ไม่สามารถสร้างคำขอเบิกได้", { type: "danger" });
        } finally {
            this.state.modalSubmitting = false;
        }
    }
}

registry.category("actions").add("buz_it_inventory.store", ItStore);
