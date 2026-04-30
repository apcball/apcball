/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class InternalConsumeBarcodeApp extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        
        this.state = useState({
            manualInput: "",
            request: null,
            lines: [],
            productBarcode: "",
            cameraEnabled: false,
        });
        
        this.productScannerRef = useRef("productScanner");
        this.html5QrcodeScanner = null;
        
        onMounted(() => {
            // Setup listener for cleanup
        });
    }

    startCameraScanner() {
        this.state.cameraEnabled = true;
        // Wait for DOM to render the reader div
        setTimeout(() => {
            const config = { 
                fps: 10, 
                qrbox: 250,
                videoConstraints: { facingMode: "environment" }
            };
            this.html5QrcodeScanner = new Html5QrcodeScanner("reader", config);
            this.html5QrcodeScanner.render(this.onScanSuccess.bind(this), this.onScanError.bind(this));
        }, 200);
    }
    
    startProductCameraScanner() {
        this.state.cameraEnabled = true;
        setTimeout(() => {
            const config = { 
                fps: 10, 
                qrbox: 250,
                videoConstraints: { facingMode: "environment" }
            };
            this.html5QrcodeScanner = new Html5QrcodeScanner("product_reader", config);
            this.html5QrcodeScanner.render(this.onProductScanSuccess.bind(this), this.onScanError.bind(this));
        }, 200);
    }
    
    stopScanner() {
        if (this.html5QrcodeScanner) {
            this.html5QrcodeScanner.clear().catch(error => {
                console.error("Failed to clear html5QrcodeScanner. ", error);
            });
            this.html5QrcodeScanner = null;
        }
        this.state.cameraEnabled = false;
    }

    onScanSuccess(decodedText, decodedResult) {
        this.state.manualInput = decodedText;
        this.searchRequest();
    }
    
    onProductScanSuccess(decodedText, decodedResult) {
        this.state.productBarcode = decodedText;
        this.processProductBarcode();
    }

    onScanError(errorMessage) {
        // Handle scan error, but usually ignore background scanning errors
    }

    async searchRequest() {
        const reqName = this.state.manualInput.trim();
        if (!reqName) return;

        try {
            const requests = await this.orm.searchRead(
                "internal.consume.request",
                [["name", "=", reqName], ["state", "in", ["approved", "partial_pick"]]],
                ["id", "name", "state", "line_ids"]
            );

            if (requests.length === 0) {
                this.notification.add(`ไม่พบเอกสาร ${reqName} หรือสถานะไม่ถูกต้อง`, { type: "danger" });
                return;
            }

            const request = requests[0];
            const lines = await this.orm.searchRead(
                "internal.consume.request.line",
                [["id", "in", request.line_ids]],
                ["id", "product_id", "qty_requested", "available_qty", "issued_qty"]
            );

            // Fetch product barcodes for quick scanning
            const productIds = lines.map(l => l.product_id[0]);
            const products = await this.orm.searchRead(
                "product.product",
                [["id", "in", productIds]],
                ["id", "barcode"]
            );
            const barcodeMap = {};
            products.forEach(p => {
                if (p.barcode) barcodeMap[p.barcode] = p.id;
            });

            this.state.request = request;
            this.state.lines = lines.map(l => ({
                id: l.id,
                product_id: l.product_id[0],
                product_name: l.product_id[1],
                qty_requested: l.qty_requested,
                available_qty: l.available_qty,
                issued_qty: l.issued_qty || 0,
            }));
            this.barcodeMap = barcodeMap;
            this.state.manualInput = "";
            this.stopScanner();
            
            // Auto focus product scanner if element exists
            setTimeout(() => {
                if (this.productScannerRef.el) {
                    this.productScannerRef.el.focus();
                }
            }, 100);

        } catch (error) {
            console.error(error);
            this.notification.add("เกิดข้อผิดพลาดในการดึงข้อมูล", { type: "danger" });
        }
    }

    onManualInputKeyup(ev) {
        if (ev.key === "Enter") {
            this.searchRequest();
        }
    }

    onProductBarcodeKeyup(ev) {
        if (ev.key === "Enter") {
            this.processProductBarcode();
        }
    }
    
    processProductBarcode() {
        const barcode = this.state.productBarcode.trim();
        this.state.productBarcode = "";
        if (!barcode) return;

        const productId = this.barcodeMap[barcode];
        if (!productId) {
            this.notification.add(`ไม่พบรหัสสินค้า ${barcode} ในเอกสารนี้`, { type: "warning" });
            return;
        }

        // Find line and increment
        const line = this.state.lines.find(l => l.product_id === productId);
        if (line) {
            if (line.issued_qty < line.qty_requested && line.issued_qty < line.available_qty) {
                line.issued_qty += 1;
                // Optional: Play success sound
            } else {
                this.notification.add(`ไม่สามารถจ่าย ${line.product_name} เพิ่มได้`, { type: "warning" });
            }
        }
    }

    incrementQty(line) {
        if (line.issued_qty < line.qty_requested && line.issued_qty < line.available_qty) {
            line.issued_qty += 1;
        } else {
            this.notification.add(`ถึงจำนวนสูงสุดสำหรับ ${line.product_name}`, { type: "warning" });
        }
    }

    decrementQty(line) {
        if (line.issued_qty > 0) {
            line.issued_qty -= 1;
        }
    }

    validateQty(line) {
        let val = parseFloat(line.issued_qty);
        if (isNaN(val) || val < 0) val = 0;
        if (val > line.qty_requested) val = line.qty_requested;
        if (val > line.available_qty) val = line.available_qty;
        line.issued_qty = val;
    }

    clearRequest() {
        this.stopScanner();
        this.state.request = null;
        this.state.lines = [];
        this.state.manualInput = "";
        this.barcodeMap = {};
    }

    async saveQuantities() {
        this.stopScanner();
        if (!this.state.request) return;

        try {
            // Check state first if it's approved -> move to issuing?
            if (this.state.request.state === 'approved') {
                await this.orm.call("internal.consume.request", "action_start_issue", [[this.state.request.id]]);
            }

            // Save line quantities
            for (const line of this.state.lines) {
                await this.orm.write("internal.consume.request.line", [line.id], {
                    issued_qty: line.issued_qty
                });
            }

            this.notification.add("บันทึกจำนวนสำเร็จ", { type: "success" });
            
            // Go to the request form view to complete signatures
            this.action.doAction({
                type: 'ir.actions.act_window',
                name: 'รายละเอียดการจ่ายของ',
                res_model: 'internal.consume.request',
                res_id: this.state.request.id,
                views: [[false, 'form']],
                target: 'current',
            });

        } catch (error) {
            console.error(error);
            this.notification.add("เกิดข้อผิดพลาดในการบันทึก", { type: "danger" });
        }
    }
}

InternalConsumeBarcodeApp.template = "internal_consume_request.BarcodeApp";

registry.category("actions").add("internal_consume_request.barcode_client_action", InternalConsumeBarcodeApp);
