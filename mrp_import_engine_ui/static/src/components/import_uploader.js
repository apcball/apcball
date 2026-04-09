/** @odoo-module **/

import { Component, useState, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ImportUploader extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.fileInput = useRef("fileInput");
        
        this.state = useState({
            isDragging: false,
            file: null,
            importType: 'bom',
            uploading: false
        });
    }

    onDragOver(ev) {
        this.state.isDragging = true;
    }

    onDragLeave(ev) {
        this.state.isDragging = false;
    }

    onDrop(ev) {
        this.state.isDragging = false;
        if (ev.dataTransfer.files && ev.dataTransfer.files.length > 0) {
            this.state.file = ev.dataTransfer.files[0];
        }
    }

    openFileDialog() {
        this.fileInput.el.click();
    }

    downloadTemplate() {
        const url = `/web/mrp/import/template/${this.state.importType}`;
        // Use a hidden <a> so the download happens without navigating away
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    onFileChange(ev) {
        if (ev.target.files && ev.target.files.length > 0) {
            this.state.file = ev.target.files[0];
        }
    }

    async uploadFile() {
        if (!this.state.file) return;
        
        this.state.uploading = true;
        
        try {
            const fileReader = new FileReader();
            fileReader.onload = async (e) => {
                let base64Data = e.target.result.split(',')[1];
                
                // For a complete implementation, this should parse the file based on its extension,
                // and then call the backend API. Here we assume we just upload the binary 
                // to a new Session for server-side processing to keep it simple, 
                // or we could use the /api/v1 endpoints if parsed in JS.
                
                const sessionId = await this.orm.create('mrp.import.session', [{
                    filename: this.state.file.name,
                    file: base64Data,
                    import_type: this.state.importType,
                    state: 'draft'
                }]);
                
                await this.orm.call('mrp.import.session', 'action_process', [sessionId]);
                
                this.notification.add("File uploaded and queued for processing", { type: "success" });
                this.state.file = null;
                this.state.uploading = false;
                
                if (this.props.onUpload) {
                    this.props.onUpload();
                }
            };
            fileReader.readAsDataURL(this.state.file);
        } catch (error) {
            this.notification.add("Error uploading file: " + error.message, { type: "danger" });
            this.state.uploading = false;
        }
    }
}

ImportUploader.template = "mrp_import_engine.Uploader";
