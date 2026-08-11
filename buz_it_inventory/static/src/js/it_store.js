/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const ITEM_MODEL = "buz.it.inventory.item";
const CATEGORY_MODEL = "buz.it.inventory.item.category";
const REQUEST_MODEL = "buz.it.issue.request";
const ACTIVE_STATES = ["draft", "submitted", "partially_issued"];

export class ItStore extends Component {
    static template = "buz_it_inventory.ItStore";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            tab: "catalog", categories: [], items: [], search: "", categoryId: null,
            cart: {}, selections: {}, loading: true, catalogError: "", submitting: false,
            modalOpen: false, modalSubmitting: false, requesterName: "", departmentName: "", reason: "",
            requestLoading: false, requestError: "", requests: [], requestSearch: "", requestOffset: 0,
            requestHasMore: false, activeCount: 0, drawerOpen: false, drawerLoading: false, drawerError: "", selectedRequest: null,
            lastCreatedRequest: null,
        });
        ["loadCatalog", "loadRequests", "refreshCurrentTab", "selectCategory", "setTab", "openCreateModal", "closeModal", "confirmCreate", "openRequest", "closeDrawer", "loadMoreRequests"].forEach((name) => { this[name] = this[name].bind(this); });
        onWillStart(() => Promise.all([this.loadCatalog(), this.loadRequests()]));
    }

    async loadCatalog() {
        this.state.loading = true; this.state.catalogError = "";
        try {
            const [items, categories] = await Promise.all([
                this.orm.searchRead(ITEM_MODEL, [["active", "=", true], ["is_published", "=", true]], ["name", "image_1920", "category_id", "item_type", "unit", "description", "available_qty", "max_per_request", "store_status"], { order: "category_id, name" }),
                this.orm.searchRead(CATEGORY_MODEL, [], ["name"], { order: "name" }),
            ]);
            this.state.items = items; this.state.categories = categories;
        } catch (error) { this.state.catalogError = error.message || "ไม่สามารถโหลดรายการได้"; }
        finally { this.state.loading = false; }
    }

    async loadRequests(reset = true) {
        if (this.state.requestLoading) return;
        if (reset) { this.state.requestOffset = 0; this.state.requests = []; }
        this.state.requestLoading = true; this.state.requestError = "";
        try {
            const query = this.state.requestSearch.trim();
            const domain = query ? ["|", "|", ["name", "ilike", query], ["reason", "ilike", query], ["line_ids.item_id", "ilike", query]] : [];
            const [rows, activeCount] = await Promise.all([
                this.orm.searchRead(REQUEST_MODEL, domain, ["name", "request_date", "state", "reason", "line_count", "total_qty", "remaining_total_qty", "ticket_id"], { order: "request_date desc, id desc", limit: 20, offset: this.state.requestOffset }),
                this.orm.searchCount(REQUEST_MODEL, [["state", "in", ACTIVE_STATES]]),
            ]);
            this.state.requests = reset ? rows : [...this.state.requests, ...rows];
            this.state.requestOffset += rows.length; this.state.requestHasMore = rows.length === 20; this.state.activeCount = activeCount;
        } catch (error) { this.state.requestError = error.message || "ไม่สามารถโหลดคำขอได้"; }
        finally { this.state.requestLoading = false; }
    }

    refreshCurrentTab() { return this.state.tab === "catalog" ? this.loadCatalog() : this.loadRequests(); }
    setTab(tab) { this.state.tab = tab; if (tab === "requests" && !this.state.requests.length && !this.state.requestError) this.loadRequests(); }
    get filteredItems() { const query = this.state.search.trim().toLowerCase(); return this.state.items.filter((item) => { const categoryId = item.category_id && item.category_id[0]; const categoryName = item.category_id && item.category_id[1]; return (!this.state.categoryId || categoryId === this.state.categoryId) && (!query || [item.name, categoryName, item.description].filter(Boolean).join(" ").toLowerCase().includes(query)); }); }
    get activeRequests() { return this.state.requests.filter((r) => ACTIVE_STATES.includes(r.state)); }
    get completedRequests() { return this.state.requests.filter((r) => !ACTIVE_STATES.includes(r.state)); }
    get cartLines() { return Object.entries(this.state.cart).map(([id, quantity]) => { const item = this.state.items.find((candidate) => candidate.id === Number(id)); return item ? { item, quantity } : null; }).filter(Boolean); }
    get cartCount() { return this.cartLines.reduce((total, line) => total + line.quantity, 0); }
    selectCategory(categoryId) { this.state.categoryId = categoryId; }
    maxQuantity(item) { return item.max_per_request > 0 ? Math.min(item.available_qty, item.max_per_request) : item.available_qty; }
    cartQuantity(item) { return this.state.cart[item.id] || 0; }
    remainingQuantity(item) { return Math.max(0, this.maxQuantity(item) - this.cartQuantity(item)); }
    selectionQuantity(item) { const remaining = this.remainingQuantity(item); return remaining ? Math.min(this.state.selections[item.id] || 1, remaining) : 0; }
    canIncreaseSelection(item) { return this.selectionQuantity(item) < this.remainingQuantity(item); }
    setSelectionQuantity(item, quantity) { const remaining = this.remainingQuantity(item); const selections = { ...this.state.selections }; if (remaining) selections[item.id] = Math.max(1, Math.min(quantity, remaining)); else delete selections[item.id]; this.state.selections = selections; }
    setCartQuantity(item, quantity) { const bounded = Math.max(0, Math.min(quantity, this.maxQuantity(item))); const cart = { ...this.state.cart }; if (bounded) cart[item.id] = bounded; else delete cart[item.id]; this.state.cart = cart; }
    addSelectedItem(item) { const quantity = this.selectionQuantity(item); if (!quantity) return; this.setCartQuantity(item, this.cartQuantity(item) + quantity); const selections = { ...this.state.selections }; delete selections[item.id]; this.state.selections = selections; }
    removeItem(item) { this.setCartQuantity(item, 0); }
    imageUrl(item) { return `/web/image?model=${ITEM_MODEL}&field=image_1920&id=${item.id}`; }
    itemTypeLabel(item) { return { consumable: "วัสดุสิ้นเปลือง", non_serialized_equipment: "อุปกรณ์ไม่ระบุหมายเลข" }[item.item_type] || (item.category_id && item.category_id[1]) || "ทั่วไป"; }
    statusLabel(item) { return { ready: "พร้อมเบิก", low: "ใกล้หมด", out: "หมด" }[item.store_status] || "ไม่พร้อมเบิก"; }
    requestStateLabel(state) { return { draft: "แบบร่าง", submitted: "ส่งคำขอแล้ว", partially_issued: "จ่ายบางส่วน", done: "เสร็จสิ้น", rejected: "ไม่อนุมัติ", cancelled: "ยกเลิก" }[state] || state; }
    get departmentLabel() { return this.state.departmentName || "ไม่ระบุแผนก"; }
    get requestSearchValue() { return this.state.requestSearch; }
    setRequestSearch(value) { this.state.requestSearch = value; this.loadRequests(); }

    async openCreateModal() { if (!this.cartLines.length || this.state.submitting || this.state.modalOpen) return; this.state.submitting = true; try { const summary = await this.orm.call(ITEM_MODEL, "get_store_requester_summary", []); this.state.requesterName = summary.requester_name; this.state.departmentName = summary.department_name; this.state.reason = ""; this.state.modalOpen = true; } catch (error) { this.notification.add(error.message || "ไม่สามารถแสดงข้อมูลผู้ขอได้", { type: "danger" }); } finally { this.state.submitting = false; } }
    closeModal() { if (!this.state.modalSubmitting) this.state.modalOpen = false; }
    async confirmCreate() { const reason = this.state.reason.trim(); if (!reason) { this.notification.add("กรุณาระบุเหตุผลในการขอเบิก", { type: "warning" }); return; } if (!this.state.modalOpen || this.state.modalSubmitting) return; this.state.modalSubmitting = true; try { const result = await this.orm.call(ITEM_MODEL, "action_create_and_submit_store_request", [this.cartLines.map(({ item, quantity }) => ({ item_id: item.id, quantity })), reason]); this.state.modalOpen = false; this.state.cart = {}; this.state.selections = {}; this.state.lastCreatedRequest = result; this.notification.add(`ส่งคำขอ ${result.request_name || "เรียบร้อยแล้ว"}`, { type: "success" }); await this.loadCatalog(); } catch (error) { this.notification.add(error.message || "ไม่สามารถสร้างคำขอได้", { type: "danger" }); } finally { this.state.modalSubmitting = false; } }
    async openRequest(request) { this.state.drawerOpen = true; this.state.drawerLoading = true; this.state.drawerError = ""; this.state.selectedRequest = null; try { const rows = await this.orm.read(REQUEST_MODEL, [request.id], ["name", "request_date", "state", "reason", "ticket_id", "line_ids"]); const detail = rows[0]; if (detail) { const lines = await this.orm.read("buz.it.issue.request.line", detail.line_ids || [], ["item_id", "requested_qty", "issued_qty", "cancelled_qty", "remaining_qty", "unit"]); detail.lines = lines; this.state.selectedRequest = detail; } } catch (error) { this.state.drawerError = error.message || "ไม่สามารถโหลดรายละเอียดคำขอได้"; } finally { this.state.drawerLoading = false; } }
    closeDrawer() { this.state.drawerOpen = false; this.state.selectedRequest = null; }
    loadMoreRequests() { if (this.state.requestHasMore) return this.loadRequests(false); }
}
registry.category("actions").add("buz_it_inventory.store", ItStore);