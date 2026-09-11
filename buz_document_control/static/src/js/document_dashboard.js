/** @odoo-module **/
import { Component, onWillStart, onWillDestroy, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { DocumentCard, badgeLabel } from "./document_components";

export class DocumentDashboard extends Component {
    static template = "buz_document_control.DocumentDashboard";
    static components = { DocumentCard };
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ query: "", filter: "all", typeId: false, offset: 0,
            loading: true, error: false, data: null, summary: null });
        this.requestId = 0;
        this.destroyed = false;
        this.badgeLabel = badgeLabel;
        onWillStart(() => this.load(true));
        onWillDestroy(() => { this.destroyed = true; clearTimeout(this.searchTimer); this.requestId++; });
    }
    get filters() {
        const filters = [
            { key: "all", label: _t("เอกสารทั้งหมด") }, { key: "forms", label: _t("แบบฟอร์ม") },
            { key: "my_department", label: _t("แผนกของฉัน") }, { key: "recent", label: _t("อัปเดตล่าสุด") },
            { key: "due", label: _t("Review Due") },
        ];
        if (this.state.data?.is_manager) filters.push(
            { key: "draft", label: _t("Draft") }, { key: "review", label: _t("Review") },
            { key: "overdue", label: _t("Overdue") }, { key: "confidential", label: _t("Confidential") },
        );
        return filters;
    }
    get kpis() {
        return [
            { key: "all", label: _t("Total Documents"), icon: "fa-files-o", tone: "neutral" },
            { key: "published", label: _t("Published"), icon: "fa-check-circle-o", tone: "published" },
            { key: "draft", label: _t("Draft"), icon: "fa-pencil-square-o", tone: "draft" },
            { key: "review", label: _t("Waiting Review"), icon: "fa-clock-o", tone: "review" },
            { key: "due", label: _t("Review Due"), icon: "fa-calendar-check-o", tone: "due_soon" },
            { key: "overdue", label: _t("Overdue"), icon: "fa-exclamation-circle", tone: "overdue" },
        ];
    }
    get isSearching() { return Boolean(this.state.query || this.state.typeId || this.state.filter !== "all"); }
    async load(summary = false) {
        const request = ++this.requestId;
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call("buz.document", "get_document_center_data", [], {
                query: this.state.query, filter_key: this.state.filter,
                type_id: this.state.typeId, offset: this.state.offset, include_summary: summary,
            });
            if (this.destroyed || request !== this.requestId) return;
            this.state.data = data;
            if (summary) this.state.summary = data;
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
    createDocument() {
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Create Document"),
            res_model: "buz.document", views: [[false, "form"]], target: "new" }, { onClose: () => this.load(true) });
    }
    openPending(row) {
        if (!row.pending_revision) return this.openDocument(row.id);
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Review Revision"),
            res_model: "buz.document.revision", res_id: row.pending_revision.id, views: [[false, "form"]] });
    }
}
registry.category("actions").add("buz_document_control.center", DocumentDashboard);
