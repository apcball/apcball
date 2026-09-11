/** @odoo-module **/
import { Component, onWillStart, onWillDestroy, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { fileInfo, badgeLabel } from "./document_components";

export class DocumentViewer extends Component {
    static template = "buz_document_control.DocumentViewer";
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.previewRef = useRef("preview");
        this.documentId = Number(this.props.action.params?.document_id || this.props.action.context?.active_id);
        this.state = useState({ loading: true, busy: false, error: false, data: null, tab: "overview", revisionId: false, version: 0 });
        this.fileInfo = fileInfo;
        this.badgeLabel = badgeLabel;
        this.destroyed = false;
        onWillStart(() => this.load());
        onWillDestroy(() => { this.destroyed = true; clearTimeout(this.pollTimer); });
    }
    get doc() { return this.state.data.document; }
    get revision() {
        return this.state.data?.history.find(r => r.id === this.state.revisionId) || this.state.data?.current ||
            (this.state.data?.is_manager ? this.state.data.history[0] : false) || false;
    }
    get previewUrl() {
        const route = `/buz_document/preview/${this.revision.id}?v=${this.state.version}`;
        return `/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(route)}`;
    }
    get tabs() {
        return [{ key: "overview", label: _t("Overview") }, { key: "current", label: _t("Current Revision") },
            { key: "history", label: _t("Revision History") }, { key: "access", label: _t("Access") },
            { key: "audit", label: _t("Audit Trail") }];
    }
    async load() {
        clearTimeout(this.pollTimer);
        try {
            const data = await this.orm.call("buz.document", "get_document_viewer_data", [[this.documentId]]);
            if (this.destroyed) return;
            this.state.data = data;
            this.state.error = false;
            if (this.revision?.preview_status === "pending") this.pollTimer = setTimeout(() => this.load(), 5000);
        } catch {
            if (!this.destroyed) { this.state.error = true; this.state.data = null; }
        } finally { if (!this.destroyed) this.state.loading = false; }
    }
    back() { return this.action.doAction("buz_document_control.action_document_center"); }
    selectTab(key) {
        this.state.tab = key;
        if (key === "current") this.state.revisionId = false;
    }
    selectRevision(revision) { this.state.revisionId = revision.id; this.state.tab = "overview"; }
    async invoke(model, method, id, message = "") {
        if (this.state.busy) return;
        this.state.busy = true;
        try {
            const result = await this.orm.call(model, method, [[id]]);
            if (result?.type) await this.action.doAction(result, { onClose: () => this.load() });
            if (message && !this.destroyed) this.notification.add(message, { type: "success" });
            if (!this.destroyed) { this.state.version++; await this.load(); }
        } catch {
            if (!this.destroyed) this.notification.add(_t("The action could not be completed. Refresh the document and check your permissions and required fields."), { type: "warning" });
        } finally { if (!this.destroyed) this.state.busy = false; }
    }
    download() { return this.invoke("buz.document.revision", "action_download", this.revision.id); }
    openPreview() { return this.invoke("buz.document.revision", "action_preview", this.revision.id); }
    newRevision() { return this.invoke("buz.document", "action_new_revision", this.doc.id); }
    async regenerate() {
        await this.invoke("buz.document.revision", "action_regenerate_preview", this.revision.id);
        if (this.destroyed || !this.revision) return;
        this.notification.add(this.revision.preview_status === "ready" ? _t("Preview generated successfully.") : _t("Preview is unavailable. You can still download the original document."),
            { type: this.revision.preview_status === "ready" ? "success" : "warning" });
    }
    sendReview() { return this.invoke("buz.document.revision", "action_send_review", this.revision.id, _t("Revision sent for review.")); }
    publish() {
        const revision = this.revision;
        this.dialog.add(ConfirmationDialog, {
            title: _t("Publish Revision %s?", revision.revision),
            body: this.state.data.current ? _t("Revision %s will become Obsolete. Users will receive the new published revision.", this.state.data.current.revision) : _t("This revision will become the current document available to authorized users."),
            confirmLabel: _t("Publish"), confirm: () => this.invoke("buz.document.revision", "action_publish", revision.id, _t("Document published successfully.")),
        });
    }
    archive() {
        this.dialog.add(ConfirmationDialog, { title: _t("Archive document?"),
            body: _t("This document will no longer appear in the employee Document Center."), confirmLabel: _t("Archive"),
            confirm: async () => { await this.invoke("buz.document", "action_archive", this.doc.id, _t("Document archived.")); },
        });
    }
    openManagement() {
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Manage Document"),
            res_model: "buz.document", res_id: this.doc.id, views: [[false, "form"]], target: "new" }, { onClose: () => this.load() });
    }
    openRevision(id) {
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Revision"),
            res_model: "buz.document.revision", res_id: id, views: [[false, "form"]] });
    }
    allHistory() {
        return this.action.doAction({ type: "ir.actions.act_window", name: _t("Revision History"),
            res_model: "buz.document.revision", views: [[false, "list"], [false, "form"]], domain: [["document_id", "=", this.doc.id]] });
    }
    async fullscreen() {
        try { await this.previewRef.el?.requestFullscreen?.(); }
        catch { this.notification.add(_t("Use Open Preview to view the document in a separate tab."), { type: "info" }); }
    }
}
registry.category("actions").add("buz_document_control.viewer", DocumentViewer);
