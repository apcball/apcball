/** @odoo-module **/

import { onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import {
    Many2ManyBinaryField,
    many2ManyBinaryField,
} from "@web/views/fields/many2many_binary/many2many_binary_field";

export class HelpdeskAttachmentPreviewField extends Many2ManyBinaryField {
    static template = "buz_it_helpdesk.HelpdeskAttachmentPreviewField";

    setup() {
        super.setup();
        this.previewViewport = useRef("previewViewport");
        this.previewImage = useRef("previewImage");
        this.previewState = useState({ file: null, zoom: 1, dragging: false });
        this.panX = 0;
        this.panY = 0;
        this.panFrame = null;
        this.dragState = {
            pointerId: null,
            startX: 0,
            startY: 0,
            startPanX: 0,
            startPanY: 0,
        };
        this.onWindowKeydown = (event) => {
            if (!this.previewState.file) {
                return;
            }
            if (event.key === "Escape") {
                event.preventDefault();
                this.closePreview();
            } else if (event.key === "+" || event.key === "=" || event.code === "NumpadAdd") {
                event.preventDefault();
                this.zoomIn();
            } else if (event.key === "-" || event.code === "NumpadSubtract") {
                event.preventDefault();
                this.zoomOut();
            } else if (event.key === "0") {
                event.preventDefault();
                this.resetZoom();
            }
        };
        this.onWindowResize = () => {
            this.clampPan();
            this.applyImageTransform(false);
        };
        onMounted(() => {
            window.addEventListener("keydown", this.onWindowKeydown);
            window.addEventListener("resize", this.onWindowResize);
        });
        onWillUnmount(() => {
            window.removeEventListener("keydown", this.onWindowKeydown);
            window.removeEventListener("resize", this.onWindowResize);
            if (this.panFrame) {
                cancelAnimationFrame(this.panFrame);
            }
        });
    }

    openPreview(file) {
        if (this.isImage(file)) {
            this.previewState.file = file;
            this.resetZoom();
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
        this.previewState.dragging = false;
        this.previewState.file = null;
    }

    zoomIn() {
        this.setZoom(this.previewState.zoom + 0.2);
    }

    zoomOut() {
        this.setZoom(this.previewState.zoom - 0.2);
    }

    resetZoom() {
        this.previewState.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        this.applyImageTransform();
    }

    onPreviewWheel(event) {
        event.preventDefault();
        const delta = Math.max(-100, Math.min(100, event.deltaY));
        const factor = Math.exp(-delta * 0.0015);
        this.setZoom(this.previewState.zoom * factor, event.clientX, event.clientY);
    }

    setZoom(value, clientX = null, clientY = null) {
        const oldZoom = this.previewState.zoom;
        const newZoom = Math.max(0.5, Math.min(4, value));
        if (Math.abs(newZoom - oldZoom) < 0.001) {
            return;
        }

        const viewport = this.previewViewport.el;
        if (viewport && clientX !== null && clientY !== null) {
            const rect = viewport.getBoundingClientRect();
            const offsetX = clientX - (rect.left + rect.width / 2);
            const offsetY = clientY - (rect.top + rect.height / 2);
            const ratio = newZoom / oldZoom;
            this.panX = offsetX - (offsetX - this.panX) * ratio;
            this.panY = offsetY - (offsetY - this.panY) * ratio;
        }

        this.previewState.zoom = newZoom;
        this.clampPan(newZoom);
        this.applyImageTransform();
    }

    onPreviewPointerDown(event) {
        if (event.button !== 0 || this.previewState.zoom <= 1) {
            return;
        }
        event.preventDefault();
        this.dragState.pointerId = event.pointerId;
        this.dragState.startX = event.clientX;
        this.dragState.startY = event.clientY;
        this.dragState.startPanX = this.panX;
        this.dragState.startPanY = this.panY;
        this.previewState.dragging = true;
        event.currentTarget.setPointerCapture(event.pointerId);
    }

    onPreviewPointerMove(event) {
        if (!this.previewState.dragging || event.pointerId !== this.dragState.pointerId) {
            return;
        }
        event.preventDefault();
        this.panX = this.dragState.startPanX + event.clientX - this.dragState.startX;
        this.panY = this.dragState.startPanY + event.clientY - this.dragState.startY;
        this.clampPan();
        if (!this.panFrame) {
            this.panFrame = requestAnimationFrame(() => {
                this.panFrame = null;
                this.applyImageTransform(false);
            });
        }
    }

    onPreviewPointerUp(event) {
        if (event.pointerId !== this.dragState.pointerId) {
            return;
        }
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
        }
        this.dragState.pointerId = null;
        this.previewState.dragging = false;
    }

    onPreviewImageLoad() {
        this.resetZoom();
    }

    clampPan(zoom = this.previewState.zoom) {
        const viewport = this.previewViewport.el;
        const image = this.previewImage.el;
        if (!viewport || !image) {
            return;
        }
        const maxX = Math.max(0, (image.offsetWidth * zoom - viewport.clientWidth) / 2);
        const maxY = Math.max(0, (image.offsetHeight * zoom - viewport.clientHeight) / 2);
        this.panX = Math.max(-maxX, Math.min(maxX, this.panX));
        this.panY = Math.max(-maxY, Math.min(maxY, this.panY));
    }

    applyImageTransform(animate = true) {
        const image = this.previewImage.el;
        if (!image) {
            return;
        }
        image.style.transition = animate ? "transform 100ms ease-out" : "none";
        image.style.transform = this.getImageTransform();
    }

    getImageTransform() {
        return `translate3d(${this.panX}px, ${this.panY}px, 0) scale(${this.previewState.zoom})`;
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
