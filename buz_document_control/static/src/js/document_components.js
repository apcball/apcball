/** @odoo-module **/
import { Component, useState, onWillDestroy } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";
import { BinaryField, binaryField } from "@web/views/fields/binary/binary_field";
import { KanbanController } from "@web/views/kanban/kanban_controller";
import { kanbanView } from "@web/views/kanban/kanban_view";

export function fileInfo(filename) {
    const extension = (filename || "").split(".").pop().toLowerCase();
    if (extension === "pdf") return { icon: "fa-file-pdf-o", label: _t("PDF Document"), tone: "pdf" };
    if (["doc", "docx"].includes(extension)) return { icon: "fa-file-word-o", label: _t("Word Document"), tone: "word" };
    if (["xls", "xlsx"].includes(extension)) return { icon: "fa-file-excel-o", label: _t("Excel Spreadsheet"), tone: "excel" };
    return { icon: "fa-file-o", label: _t("Document"), tone: "generic" };
}

export function badgeLabel(value) {
    return {
        published: _t("Current"), draft: _t("Draft"), review: _t("In Review"),
        obsolete: _t("Obsolete"), archived: _t("Archived"), cancelled: _t("Cancelled"),
        general: _t("General"), restricted: _t("Restricted"), confidential: _t("Confidential"),
        due_soon: _t("Review Due"), overdue: _t("Overdue"),
    }[value] || value;
}

export class DocumentCard extends Component {
    static template = "buz_document_control.DocumentCard";
    static props = { document: Object, onOpen: Function, onDownload: Function };
    fileInfo = fileInfo;
    badgeLabel = badgeLabel;
}

export class DocumentDropzone extends BinaryField {
    static template = "buz_document_control.Dropzone";
    setup() {
        super.setup();
        this.state = useState({ dragging: false, busy: false, error: "" });
        this.destroyed = false;
        onWillDestroy(() => { this.destroyed = true; this.reader?.abort(); });
    }
    async selectFile(event) {
        await this.readFile(event.target.files?.[0]);
        event.target.value = "";
    }
    async dropFile(event) {
        this.state.dragging = false;
        if (event.dataTransfer.files.length !== 1) {
            this.state.error = _t("Please choose one document at a time.");
            return;
        }
        await this.readFile(event.dataTransfer.files[0]);
    }
    async readFile(file) {
        if (!file || this.props.readonly || this.state.busy) return;
        this.state.error = "";
        if (!/\.(pdf|docx?|xlsx?|pptx?|txt|jpe?g|png)$/i.test(file.name)) {
            this.state.error = _t("Unsupported file type. Choose Word, Excel, PDF or another supported document format.");
            return;
        }
        this.state.busy = true;
        try {
            const result = await new Promise((resolve, reject) => {
                this.reader = new FileReader();
                this.reader.onload = () => resolve(this.reader.result);
                this.reader.onerror = () => reject(new Error("read"));
                this.reader.onabort = () => reject(new Error("abort"));
                this.reader.readAsDataURL(file);
            });
            if (!this.destroyed) await this.update({ data: result.split(",")[1], name: file.name });
        } catch {
            if (!this.destroyed) this.state.error = _t("The file could not be read. Please try again.");
        } finally {
            if (!this.destroyed) this.state.busy = false;
        }
    }
}
registry.category("fields").add("bdc_dropzone", { ...binaryField, component: DocumentDropzone });

class DocumentKanbanController extends KanbanController {
    async openRecord(record) {
        return this.actionService.doAction({
            type: "ir.actions.client", tag: "buz_document_control.viewer",
            name: _t("Document Viewer"), params: { document_id: record.resId },
        });
    }
}
registry.category("views").add("bdc_document_kanban", { ...kanbanView, Controller: DocumentKanbanController });
