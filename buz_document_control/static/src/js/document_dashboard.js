/** @odoo-module **/
import { Component, onWillStart, onWillDestroy, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { deserializeDate, deserializeDateTime, formatDate } from "@web/core/l10n/dates";
import { badgeLabel, fileInfo } from "./document_components";

export class DocumentDashboard extends Component {
    static template = "buz_document_control.DocumentDashboard";
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.user = useService("user");
        this.state = useState({ query: "", filter: "all", typeId: false, offset: 0,
            loading: true, error: false, data: null, summary: null, moreFilters: false });
        this.requestId = 0;
        this.destroyed = false;
        this.badgeLabel = badgeLabel;
        this.fileInfo = fileInfo;
        onWillStart(() => this.load(true));
        onWillDestroy(() => { this.destroyed = true; clearTimeout(this.searchTimer); this.requestId++; });
    }
    get filters() {
        const filters = [
            { key: "all", label: _t("ทั้งหมด") }, { key: "forms", label: _t("แบบฟอร์ม") },
            { key: "my_department", label: _t("แผนกของฉัน") }, { key: "recent", label: _t("อัปเดตล่าสุด") },
            { key: "due", label: _t("Review Due") },
        ];
        if (this.state.data?.is_manager) filters.push({ key: "confidential", label: _t("Confidential") });
        return filters;
    }
    get extraFilters() {
        return this.state.data?.is_manager ? [
            { key: "draft", label: _t("Draft") }, { key: "review", label: _t("Waiting Review") },
            { key: "overdue", label: _t("Overdue") }, { key: "preview_failed", label: _t("Preview issues") },
        ] : [];
    }
    get kpis() {
        return [
            { key: "all", label: _t("เอกสารทั้งหมด"), icon: "fa-files-o", tone: "blue" },
            { key: "published", label: _t("Published"), icon: "fa-check-circle-o", tone: "published" },
            { key: "due", label: _t("Review Due"), icon: "fa-clock-o", tone: "due_soon" },
            { key: "overdue", label: _t("Overdue"), icon: "fa-exclamation-circle", tone: "overdue" },
            { key: "draft", label: _t("Draft"), icon: "fa-file-text-o", tone: "draft" },
        ];
    }
    get isSearching() { return Boolean(this.state.query || this.state.typeId || this.state.filter !== "all"); }
    get visibleDocuments() { return this.isSearching ? this.state.data.documents : this.state.data.documents.slice(0, 3); }
    get dateToday() { return this.state.summary ? this.date(this.state.summary.today) : ""; }
    date(value) { return value ? formatDate(value.length > 10 ? deserializeDateTime(value) : deserializeDate(value)) : "—"; }
    percent(key) {
        const counts = this.state.summary?.counts || {};
        return counts.all ? Math.round(100 * (counts[key] || 0) / counts.all) : 0;
    }
    typeCode(document) {
        return this.state.summary?.document_types.find(type => type.id === document.document_type_id?.[0])?.code || "—";
    }
    typeTone(code) { return ({ QM: "blue", QP: "green", WI: "orange", FM: "purple", SD: "cyan", EX: "gray" })[code] || "gray"; }
    attentionStatus(row) {
        if (row.state === "published" && row.review_status !== "ok") return row.review_status;
        return row.pending_revision?.state || (row.state === "published" ? "check" : row.state);
    }
    attentionStatusLabel(row) { const status = this.attentionStatus(row); return status === "check" ? _t("Check document") : badgeLabel(status); }
    attentionLabel(row) { return this.attentionStatus(row) === "draft" ? _t("Edit") : _t("Review"); }
    daysLabel(value) {
        if (!value || !this.state.summary?.today) return "";
        const days = Math.round(deserializeDate(value).diff(deserializeDate(this.state.summary.today), "days").days);
        return days < 0 ? _t("เกินกำหนด %s วัน", -days) : days === 0 ? _t("ครบกำหนดวันนี้") : _t("อีก %s วัน", days);
    }
    get departmentBars() {
        const departments = this.state.summary?.departments || [];
        const named = departments.filter(row => row.id);
        const rows = named.slice(0, 5).map(row => ({ ...row, domain: [["department_id", "=", row.id]] }));
        const unassigned = departments.find(row => !row.id);
        if (unassigned) rows.push({ ...unassigned, id: "unassigned", domain: [["department_id", "=", false]] });
        if (named.length > 5) rows.push({ id: "other", name: _t("อื่น ๆ"), count: named.slice(5).reduce((sum, row) => sum + row.count, 0),
            domain: [["department_id", "in", named.slice(5).map(row => row.id)]] });
        const max = Math.max(1, ...rows.map(row => row.count));
        return rows.map((row, index) => ({ ...row, width: 100 * row.count / max, tone: ["blue", "purple", "green", "orange", "pink", "gray"][index % 6] }));
    }
    submitSearch() { clearTimeout(this.searchTimer); this.state.offset = 0; return this.load(); }
    refresh() { clearTimeout(this.searchTimer); return this.load(true); }
    async load(summary = false) {
        const request = ++this.requestId;
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call("buz.document", "get_document_center_data", [], {
                query: this.state.query, filter_key: this.state.filter,
                type_id: this.state.typeId, offset: this.state.offset, include_summary: summary || !this.state.summary,
            });
            if (this.destroyed || request !== this.requestId) return;
            this.state.data = data;
            if (data.counts) this.state.summary = data;
        } catch {
            if (!this.destroyed && request === this.requestId) this.state.error = true;
        } finally {
            if (!this.destroyed && request === this.requestId) this.state.loading = false;
        }
    }
    search(event) {
        this.state.query = event.target.value;
        this.state.offset = 0;
        clearTimeout(this.searchTimer);
        this.requestId++; // Invalidate an earlier response immediately, including during debounce.
        this.searchTimer = setTimeout(() => this.load(), 300);
    }
    setFilter(key) {
        clearTimeout(this.searchTimer);
        this.state.filter = key;
        this.state.offset = 0;
        return this.load();
    }
    setType(id) {
        clearTimeout(this.searchTimer);
        this.state.typeId = this.state.typeId === id ? false : id;
        this.state.offset = 0;
        return this.load();
    }
    reset() {
        this.state.query = ""; this.state.typeId = false;
        return this.setFilter("all");
    }
    page(direction) { this.state.offset = Math.max(0, this.state.offset + direction * 12); return this.load(); }
    openDocument(id) {
        return this.action.doAction({ type: "ir.actions.client", tag: "buz_document_control.viewer",
            name: _t("Document Viewer"), params: { document_id: id } });
    }
    async download(id) {
        try { await this.action.doAction(await this.orm.call("buz.document", "action_download", [[id]])); }
        catch { this.notification.add(_t("Unable to download this document. Check your access or refresh the page."), { type: "warning" }); }
    }
    openNative(typeId = false, mode = "kanban") {
        const domain = typeId ? [["document_type_id", "=", typeId], ["state", "not in", ["obsolete", "archived"]]] : this.state.data.domain;
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Documents"),
            res_model: "buz.document", views: [[false, mode], [false, mode === "kanban" ? "list" : "kanban"], [false, "form"]], domain });
    }
    openSummary(key = "all", extraDomain = []) {
        const domain = [...(this.state.summary.summary_domains?.[key] || this.state.summary.base_domain), ...extraDomain];
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Documents"),
            res_model: "buz.document", views: [[false, "list"], [false, "kanban"], [false, "form"]], domain });
    }
    createDocument() {
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Create Document"),
            res_model: "buz.document", views: [[false, "form"]], target: "new" }, { onClose: () => this.load(true) });
    }
    openPending(row) {
        if (row.state === "draft" && !row.pending_revision) return this.action.doAction({
            type: "ir.actions.act_window", name: _t("Edit Document"), res_model: "buz.document",
            res_id: row.id, views: [[false, "form"]],
        });
        if (!row.pending_revision) return this.openDocument(row.id);
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Review Revision"),
            res_model: "buz.document.revision", res_id: row.pending_revision.id, views: [[false, "form"]] });
    }
}
registry.category("actions").add("buz_document_control.center", DocumentDashboard);
