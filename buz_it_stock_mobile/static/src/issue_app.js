/** @odoo-module **/

import { Component, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { Dialog } from "@web/core/dialog/dialog";

export function itemKey(productId, lotId = false) {
    return `${productId}:${lotId || 0}`;
}

export function quantityTotals(lines) {
    const totals = {};
    for (const line of lines) {
        totals[line.uom] = (totals[line.uom] || 0) + Number(line.quantity);
    }
    return Object.entries(totals).map(([unit, qty]) => `${Number(qty.toFixed(6))} ${unit}`).join(" · ");
}

const CHART_COLORS = ["#0668ff", "#3995ff", "#ffad00", "#ff654e", "#9147ff", "#13c1b8"];

export function categoryChart(categories = []) {
    const positive = categories.filter(item => Number(item.qty) > 0);
    if (!positive.length || new Set(positive.map(item => item.uom)).size !== 1) {
        return null;
    }
    const total = positive.reduce((sum, item) => sum + Number(item.qty), 0);
    let cursor = 0;
    const segments = positive.map((item, index) => {
        const start = cursor;
        cursor += Number(item.qty) / total * 100;
        return `${CHART_COLORS[index % CHART_COLORS.length]} ${start}% ${cursor}%`;
    });
    return { style: `background: conic-gradient(${segments.join(",")})`, total, uom: positive[0].uom };
}

class ITIssueDetail extends Component {
    static template = "buz_it_stock_mobile.Detail";
    static components = { Dialog };
    static props = { detail: Object, close: Function, formatDate: Function, number: Function, statusLabel: Function };
}

export class ITIssueApp extends Component {
    static template = "buz_it_stock_mobile.App";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        this.canvas = useRef("signature");
        this.state = useState({
            ready: false, busy: false, error: "", step: 0, nav: false,
            boot: {}, products: [], more: false, search: "", category: false, catalogExpanded: false,
            cart: [], note: "", people: [], employeeSearch: "", employee: null,
            locationId: "", detail: null, dashboard: null, lotProduct: null, lots: [],
            signed: false, requestKey: null, uncertain: false, failedImages: {},
            lowOpen: false, lowProducts: [], lowSearch: '', lowCategory: '', lowStatus: 'all',
            lowPage: 0, purchaseSelection: {}, canPurchase: false, canReadPurchase: false,
        });
        this.catalogRevision = 0;
        this.peopleRevision = 0;
        this.drawing = false;
        this.inkDistance = 0;
        onWillStart(() => this.load());
        this.stockTimer = setInterval(() => {
            if (this.state.ready && !this.state.boot.setup_error && !document.hidden &&
                !this.state.busy && !this.state.uncertain && (this.state.step === 0 || this.state.lowOpen)) {
                this.run(() => this.dashboard());
            }
        }, 60000);
        onWillUnmount(() => {
            clearInterval(this.stockTimer);
            clearTimeout(this.searchTimer);
            clearTimeout(this.peopleTimer);
            this.catalogRevision++;
            this.peopleRevision++;
        });
    }

    get title() {
        return ["IT Issue", "ตรวจสอบรายการ", "ยืนยันผู้รับ", "เซ็นรับอุปกรณ์", "สำเร็จ"][this.state.step];
    }
    get totals() { return quantityTotals(this.state.cart); }
    get distinctCount() { return new Set(this.state.cart.map(line => line.product_id)).size; }
    get detailTotals() { return quantityTotals(this.state.detail?.lines || []); }
    get storageKey() { return `buz_it_issue:${this.state.boot.company_id}:${this.state.boot.user_id}`; }
    formatDate(value) { return value ? deserializeDateTime(value).toFormat("dd/MM/yyyy HH:mm") : ""; }
    number(value) { return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 }); }
    icon(category) { return `fa fa-${category.icon || "cube"}`; }
    itemKey(productId, lotId) { return itemKey(productId, lotId); }
    image(productId) { return `/web/image/product.product/${productId}/image_256`; }
    imageFailed(productId) { this.state.failedImages[productId] = true; }
    get chart() { return categoryChart(this.state.dashboard?.categories); }
    chartColor(index) { return `background: ${CHART_COLORS[index % CHART_COLORS.length]}`; }
    statusLabel(state) { return { draft: "ร่าง", awaiting: "รอเซ็น", done: "เสร็จสิ้น", cancel: "ยกเลิก" }[state] || state; }
    categoryImage(id) {
        const product = this.state.products.find(item => item.category_id === id && item.has_image && !this.state.failedImages[item.id]);
        return product ? this.image(product.id) : false;
    }
    categoryImageFailed(event) {
        const match = event.currentTarget.getAttribute("src").match(/\/product\.product\/(\d+)\//);
        if (match) { this.imageFailed(Number(match[1])); }
    }
    showCart() {
        if (this.state.busy || this.state.uncertain || this.state.step === 4) { return; }
        this.clearSignature();
        this.state.nav = false;
        this.state.step = 1;
    }
    showAllProducts() {
        this.state.catalogExpanded = true;
        this.state.search = "";
        clearTimeout(this.searchTimer);
        return this.selectCategory(false);
    }
    openMyIssues() {
        return this.openAction({
            type: "ir.actions.act_window", name: "รายการของฉัน", res_model: "buz.it.issue",
            views: [[false, "list"], [false, "form"]],
            domain: [["create_uid", "=", this.state.boot.user_id], ["company_id", "=", this.state.boot.company_id]],
            target: "current",
        });
    }

    async run(callback) {
        if (this.state.busy) { return; }
        this.state.busy = true;
        this.state.error = "";
        try { await callback(); }
        catch (error) {
            this.state.error = error.data?.message || error.message || "ไม่สามารถเชื่อมต่อได้ กรุณาลองใหม่";
        } finally { this.state.busy = false; }
    }
    async load() {
        await this.run(async () => {
            this.state.boot = await this.orm.call("buz.it.issue", "get_bootstrap", []);
            if (!this.state.boot.setup_error) {
                await Promise.all([this.catalog(), this.dashboard()]);
                if (this.props.action?.params?.low_stock) { this.state.lowOpen = true; }
                const issueId = this.props.action?.params?.issue_id;
                const pending = sessionStorage.getItem(this.storageKey);
                if (issueId) {
                    this.restore(await this.orm.call("buz.it.issue", "get_detail", [[issueId]]));
                } else if (pending) {
                    this.state.requestKey = pending;
                    const detail = await this.orm.call("buz.it.issue", "request_status", [pending]);
                    if (detail && ["awaiting", "done"].includes(detail.state)) {
                        this.restore(detail);
                    }
                }
            }
            this.state.ready = true;
        });
    }
    async catalog(append = false) {
        const revision = ++this.catalogRevision;
        const result = await this.orm.call("buz.it.issue", "get_catalog", [
            this.state.search, this.state.category, append ? this.state.products.length : 0,
        ]);
        if (revision !== this.catalogRevision) { return; }
        this.state.products = append ? [...this.state.products, ...result.products] : result.products;
        this.state.more = result.more;
    }
    async dashboard() {
        const [dashboard, low] = await Promise.all([
            this.orm.call("buz.it.issue", "get_dashboard", []),
            this.orm.call("buz.it.issue", "get_low_stock", []),
        ]);
        this.state.dashboard = dashboard;
        this.state.lowProducts = low.products;
        this.state.canPurchase = low.can_create;
        this.state.canReadPurchase = low.can_read;
        const ids = new Set(low.products.map(product => product.id));
        for (const id of Object.keys(this.state.purchaseSelection)) {
            if (!ids.has(Number(id))) { delete this.state.purchaseSelection[id]; }
        }
        this.state.lowPage = Math.min(this.state.lowPage, this.lowPages - 1);
    }
    get selectedPurchase() { return Object.values(this.state.purchaseSelection); }
    get filteredLowStock() {
        const term = this.state.lowSearch.trim().toLocaleLowerCase();
        return this.state.lowProducts.filter(p =>
            (!term || `${p.name} ${p.category}`.toLocaleLowerCase().includes(term)) &&
            (!this.state.lowCategory || p.category_id === Number(this.state.lowCategory)) &&
            (this.state.lowStatus !== 'empty' || p.available <= 0) &&
            (this.state.lowStatus !== 'ordering' || p.status === 'ordering') &&
            (this.state.lowStatus !== 'low' || p.status === 'low'));
    }
    purchaseStatus(state) {
        return {draft: 'ร่าง', waiting_head_approval: 'รอหัวหน้าอนุมัติ',
            waiting_purchase_approval: 'รอจัดซื้ออนุมัติ', approved: 'อนุมัติแล้ว',
            purchase_order_created: 'สร้าง PO แล้ว', received: 'รับแล้ว', cancelled: 'ยกเลิก'}[state] || state;
    }
    openPurchaseReport(productId = false) {
        return this.run(async () => {
            const action = await this.orm.call('buz.it.issue', 'get_replenishment_report', [productId]);
            await this.action.doAction(action);
        });
    }
    openPurchase(id) {
        return this.run(() => this.action.doAction({type: 'ir.actions.act_window',
            res_model: 'employee.purchase.requisition', res_id: id,
            views: [[false, 'form']], target: 'current'}));
    }
    get lowPages() { return Math.max(1, Math.ceil(this.filteredLowStock.length / 6)); }
    get lowRows() { return this.filteredLowStock.slice(this.state.lowPage * 6, (this.state.lowPage + 1) * 6); }
    filterLowStock() { this.state.lowPage = 0; }
    openLowStock() {
        if (this.state.busy || this.state.uncertain) { return; }
        this.state.nav = false;
        return this.run(async () => {
            await this.dashboard();
            const ids = new Set(this.state.lowProducts.map(p => p.id));
            for (const id of Object.keys(this.state.purchaseSelection)) {
                if (!ids.has(Number(id))) { delete this.state.purchaseSelection[id]; }
            }
            this.state.lowPage = 0;
            this.state.lowOpen = true;
        });
    }
    togglePurchase(product, checked) {
        if (checked) { this.state.purchaseSelection[product.id] = { product_id: product.id, quantity: product.quantity }; }
        else { delete this.state.purchaseSelection[product.id]; }
    }
    purchaseQuantity(product, value) {
        product.quantity = Number(value);
        if (this.state.purchaseSelection[product.id]) {
            this.state.purchaseSelection[product.id].quantity = Number(value);
        }
    }
    createPurchase() {
        return this.run(async () => {
            const action = await this.orm.call('buz.it.issue', 'prepare_purchase_requisition', [this.selectedPurchase]);
            await this.action.doAction(action);
        });
    }
    searchInput(event) {
        this.state.catalogExpanded = true;
        this.state.search = event.target.value;
        clearTimeout(this.searchTimer);
        this.searchTimer = setTimeout(() => this.run(() => this.catalog()), 250);
    }
    selectCategory(id) {
        this.state.catalogExpanded = true;
        this.state.category = id;
        return this.run(() => this.catalog());
    }
    async add(product) {
        if (product.tracking !== "none") {
            return this.run(async () => {
                this.state.lots = await this.orm.call("buz.it.issue", "get_lots", [product.id]);
                this.state.lotProduct = product;
            });
        }
        this.addLine(product);
    }
    addLine(product, lot = null) {
        const key = itemKey(product.id, lot?.id);
        const line = this.state.cart.find(item => item.key === key);
        if (line && product.tracking === "serial") { return; }
        const available = lot?.available ?? product.available;
        const increment = Math.max(product.rounding, Math.min(1, available));
        if ((line?.quantity || 0) + increment > available + 0.000001) {
            this.notification.add("จำนวนพร้อมเบิกไม่เพียงพอ", { type: "warning" });
            return;
        }
        if (line) { line.quantity = Number((line.quantity + increment).toFixed(6)); }
        else {
            this.state.cart.push({
                key, product_id: product.id, name: product.name, category: product.category,
                quantity: increment, uom: product.uom, rounding: product.rounding,
                tracking: product.tracking, lot_id: lot?.id || false, lot_name: lot?.name || "",
                available,
            });
        }
        this.clearSignature();
    }
    changeQty(line, value) {
        const qty = Number(value);
        if (Number.isFinite(qty) && qty > 0 && line.tracking !== "serial") {
            line.quantity = qty;
            this.clearSignature();
        }
    }
    remove(line) {
        this.state.cart = this.state.cart.filter(item => item.key !== line.key);
        this.clearSignature();
    }
    async chooseReceiver() {
        if (!this.state.cart.length) { return; }
        await this.run(async () => {
            await this.people();
            this.state.step = 2;
        });
    }
    async people() {
        const revision = ++this.peopleRevision;
        const people = await this.orm.call("buz.it.issue", "get_people", [this.state.employeeSearch]);
        if (revision === this.peopleRevision) { this.state.people = people; }
    }
    peopleInput(event) {
        this.state.employeeSearch = event.target.value;
        clearTimeout(this.peopleTimer);
        this.peopleTimer = setTimeout(() => this.run(() => this.people()), 250);
    }
    selectEmployee(employee) {
        this.state.employee = employee;
        this.state.locationId = String(employee.location_id || "");
        this.clearSignature();
    }
    async confirmRecipient() {
        if (!this.state.employee) { return; }
        await this.run(async () => {
            if (!this.state.requestKey) { this.state.requestKey = crypto.randomUUID(); }
            sessionStorage.setItem(this.storageKey, this.state.requestKey);
            this.state.detail = await this.orm.call("buz.it.issue", "save_request", [{
                request_key: this.state.requestKey, employee_id: this.state.employee.id,
                work_location_id: Number(this.state.locationId) || false, note: this.state.note,
                lines: this.state.cart.map(line => ({
                    product_id: line.product_id, quantity: line.quantity, lot_id: line.lot_id,
                })),
            }]);
            this.state.step = this.state.detail.state === "done" ? 4 : 3;
            this.state.uncertain = false;
            this.clearSignature();
        });
    }
    restore(detail) {
        if (detail.company_id !== this.state.boot.company_id) {
            throw new Error("กรุณาสลับไปบริษัทของใบเบิกก่อนเปิดรายการนี้");
        }
        this.state.detail = detail;
        this.state.requestKey = detail.request_key;
        sessionStorage.setItem(this.storageKey, detail.request_key);
        this.state.cart = detail.lines.map(line => ({ ...line, key: itemKey(line.product_id, line.lot_id) }));
        this.state.employee = { id: detail.employee_id, name: detail.receiver, department: detail.department };
        this.state.locationId = String(detail.work_location_id || "");
        this.state.note = detail.note;
        this.state.step = detail.state === "done" ? 4 : detail.state === "awaiting" ? 3 : 1;
        this.state.uncertain = false;
    }
    point(event) {
        const canvas = this.canvas.el;
        const rect = canvas.getBoundingClientRect();
        return { x: (event.clientX - rect.left) * canvas.width / rect.width,
            y: (event.clientY - rect.top) * canvas.height / rect.height };
    }
    startSignature(event) {
        if (this.state.busy || this.state.uncertain) { return; }
        event.preventDefault();
        this.canvas.el.setPointerCapture(event.pointerId);
        this.drawing = true;
        this.lastPoint = this.point(event);
    }
    drawSignature(event) {
        if (!this.drawing) { return; }
        event.preventDefault();
        const next = this.point(event);
        const context = this.canvas.el.getContext("2d");
        context.lineWidth = 3;
        context.lineCap = "round";
        context.lineJoin = "round";
        context.strokeStyle = "#151b2e";
        context.beginPath();
        context.moveTo(this.lastPoint.x, this.lastPoint.y);
        context.lineTo(next.x, next.y);
        context.stroke();
        this.inkDistance += Math.hypot(next.x - this.lastPoint.x, next.y - this.lastPoint.y);
        this.lastPoint = next;
        this.state.signed = this.inkDistance > 35;
    }
    endSignature() { this.drawing = false; }
    clearSignature() {
        this.state.signed = false;
        this.inkDistance = 0;
        this.drawing = false;
        if (this.canvas.el) { this.canvas.el.getContext("2d").clearRect(0, 0, 800, 320); }
    }
    async sign() {
        if (!this.state.signed || this.state.uncertain) { return; }
        await this.run(async () => {
            const signature = this.canvas.el.toDataURL("image/png").split(",")[1];
            this.state.uncertain = true;
            try {
                this.state.detail = await this.orm.call("buz.it.issue", "action_sign", [[this.state.detail.id], signature, this.state.detail.revision]);
                this.state.step = 4;
                this.state.uncertain = false;
                await this.dashboard();
            } catch (error) {
                if (error.data?.message) { this.state.uncertain = false; }
                throw error;
            }
        });
    }
    async checkStatus() {
        await this.run(async () => {
            const detail = await this.orm.call("buz.it.issue", "request_status", [this.state.requestKey]);
            if (detail) { this.restore(detail); this.clearSignature(); }
        });
    }
    back() {
        if (this.state.busy || this.state.uncertain) { return; }
        this.clearSignature();
        this.state.step = Math.max(0, this.state.step - 1);
    }
    home() {
        if (this.state.busy || this.state.uncertain) { return; }
        this.state.nav = false;
        if (this.state.detail?.state === "done") { return this.newIssue(); }
        this.clearSignature();
        this.state.step = 0;
    }
    async newIssue() {
        sessionStorage.removeItem(this.storageKey);
        Object.assign(this.state, {
            step: 0, cart: [], employee: null, locationId: "", note: "", detail: null,
            signed: false, requestKey: null, uncertain: false, error: "",
        });
        await this.run(async () => { await Promise.all([this.catalog(), this.dashboard()]); });
    }
    openAction(action) {
        if (this.state.busy || this.state.uncertain) { return; }
        this.state.nav = false;
        return this.action.doAction(action);
    }
    openDetail(id) {
        if (this.state.uncertain) { return; }
        return this.run(async () => {
            const detail = await this.orm.call("buz.it.issue", "get_detail", [[id]]);
            this.dialog.add(ITIssueDetail, {
                detail, formatDate: value => this.formatDate(value),
                number: value => this.number(value), statusLabel: value => this.statusLabel(value),
            });
        });
    }
}

registry.category("actions").add("buz_it_stock_mobile.app", ITIssueApp);
