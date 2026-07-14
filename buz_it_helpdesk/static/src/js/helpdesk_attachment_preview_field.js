/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useFileViewer } from "@web/core/file_viewer/file_viewer_hook";
import {
    Many2ManyBinaryField,
    many2ManyBinaryField,
} from "@web/views/fields/many2many_binary/many2many_binary_field";

export class HelpdeskAttachmentPreviewField extends Many2ManyBinaryField {
    static template = "buz_it_helpdesk.HelpdeskAttachmentPreviewField";

    setup() {
        super.setup();
        this.fileViewer = useFileViewer();
    }

    isImage(file) {
        return (file.mimetype || "").startsWith("image/");
    }

    getThumbnailUrl(file) {
        return `/web/image/ir.attachment/${file.id}/datas`;
    }

    getInlineUrl(file) {
        return `/web/content/${file.id}?download=false`;
    }

    toViewerFile(file) {
        const mimetype = file.mimetype || "";
        const isImage = mimetype.startsWith("image/");
        const isPdf = mimetype === "application/pdf";
        const isVideo = mimetype.startsWith("video/");
        const isText = mimetype.startsWith("text/");
        return {
            id: file.id,
            displayName: file.name,
            downloadUrl: `/web/content/${file.id}?download=true`,
            defaultSource: isImage ? this.getThumbnailUrl(file) : this.getInlineUrl(file),
            mimetype,
            isImage,
            isPdf,
            isVideo,
            isText,
            isViewable: isImage || isPdf || isVideo || isText,
        };
    }

    openPreview(file) {
        const files = this.files.map((item) => this.toViewerFile(item));
        const selected = files.find((item) => item.id === file.id);
        if (selected?.isViewable) {
            this.fileViewer.open(selected, files);
            return;
        }
        window.open(this.getInlineUrl(file), "_blank", "noopener,noreferrer");
    }
}

registry.category("fields").add("helpdesk_attachment_preview", {
    ...many2ManyBinaryField,
    component: HelpdeskAttachmentPreviewField,
});