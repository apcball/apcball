/** @odoo-module **/

import { useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    Many2ManyBinaryField,
    many2ManyBinaryField,
} from "@web/views/fields/many2many_binary/many2many_binary_field";

export class HelpdeskAttachmentPreviewField extends Many2ManyBinaryField {
    static template = "buz_it_helpdesk.HelpdeskAttachmentPreviewField";

    setup() {
        super.setup();
        this.previewState = useState({ file: null, zoom: 1 });
    }

    openPreview(file) {
        if (this.isImage(file)) {
            this.previewState.file = file;
            this.previewState.zoom = 1;
            return;
        }
        window.open(this.getUrl(file.id), "_blank", "noopener");
    }

    onPreviewKeydown(event, file) {
        if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.openPreview(file);
        }
    }

    closePreview() {
        this.previewState.file = null;
    }

    zoomIn() {
        this.previewState.zoom = Math.min(this.previewState.zoom + 0.25, 3);
    }

    zoomOut() {
        this.previewState.zoom = Math.max(this.previewState.zoom - 0.25, 0.5);
    }

    resetZoom() {
        this.previewState.zoom = 1;
    }

    getPreviewUrl(file) {
        return "/web/image/ir.attachment/" + file.id + "/datas";
    }

    getFileName(file) {
        return (file && (file.name || file.datas_fname)) || "Attachment";
    }

    getExtension(file) {
        const name = this.getFileName(file);
        return name.includes(".") ? name.replace(/^.*\./, "").toLowerCase() : "";
    }

    getFileTypeLabel(file) {
        const extension = this.getExtension(file);
        if (extension) {
            return extension.toUpperCase();
        }

        const mimetype = String((file && (file.mimetype || file.type)) || "").toLowerCase();
        const mimetypeLabels = {
            "application/msword": "DOC",
            "application/pdf": "PDF",
            "application/vnd.ms-excel": "XLS",
            "application/vnd.ms-powerpoint": "PPT",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PPTX",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
            "image/jpeg": "JPG",
        };
        if (mimetypeLabels[mimetype]) {
            return mimetypeLabels[mimetype];
        }

        const subtype = mimetype.includes("/") ? mimetype.split("/").pop() : "";
        return subtype ? subtype.replace(/^vnd\./, "").toUpperCase() : "FILE";
    }

    isImage(file) {
        const mimetype = String((file && (file.mimetype || file.type)) || "").toLowerCase();
        const imageExtensions = ["bmp", "gif", "jpeg", "jpg", "png", "svg", "webp"];
        return mimetype.startsWith("image/") || imageExtensions.includes(this.getExtension(file));
    }
}

registry.category("fields").add("buz_helpdesk_attachment_preview", {
    ...many2ManyBinaryField,
    component: HelpdeskAttachmentPreviewField,
});
