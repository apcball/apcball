/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { rpc } from "@web/core/rpc";
import { registry } from "@web/core/registry";

// Global variables for QR Scanner
let html5QrcodeScanner = null;
let currentResId = null;

window.startInternalQRScanner = async function() {
    try {
        // Check if Html5QrcodeScanner is available
        if (typeof Html5QrcodeScanner === 'undefined') {
            console.error('Html5QrcodeScanner is not loaded');
            alert('Library ไม่ได้ถูกโหลด กรุณารีเฟรชหน้า');
            return;
        }

        if (html5QrcodeScanner) {
            html5QrcodeScanner.clear();
        }

        const config = {
            fps: 10,
            qrbox: { width: 250, height: 250 },
            aspectRatio: 1.0,
            videoConstraints: { facingMode: "environment" }
        };

        html5QrcodeScanner = new Html5QrcodeScanner(
            "internal-qr-reader",
            config,
            /* verbose= */ false
        );

        html5QrcodeScanner.render(onQRCodeScanned, onQRCodeError);

    } catch (error) {
        console.error("Error starting QR scanner:", error);
        alert("เกิดข้อผิดพลาดในการเริ่ม QR Scanner: " + error.message);
    }
};

window.stopInternalQRScanner = async function() {
    try {
        if (html5QrcodeScanner) {
            await html5QrcodeScanner.clear();
            html5QrcodeScanner = null;
        }
        const resultDiv = document.getElementById("internal-qr-result");
        if (resultDiv) {
            resultDiv.innerHTML = "";
        }
    } catch (error) {
        console.error("Error stopping QR scanner:", error);
    }
};

async function onQRCodeScanned(decodedText, decodedResult) {
    try {
        const resultDiv = document.getElementById("internal-qr-result");
        if (!resultDiv) return;

        // Check if it's a product barcode or request name
        // Format: REQ00045 for requests, or barcode for products
        if (decodedText.startsWith('REQ')) {
            // It's a request - navigate to it
            resultDiv.innerHTML = `<div class="alert alert-info">พบเอกสาร: <strong>${decodedText}</strong></div>`;
            // Navigate to the request
            await rpc('/web/dataset/call_kw', {
                model: 'internal.consume.request',
                method: 'search_read',
                args: [[['name', '=', decodedText]]],
                kwargs: { fields: ['id', 'state'], limit: 1 }
            }).then(result => {
                if (result.length > 0) {
                    window.location.href = `/web#id=${result[0].id}&model=internal.consume.request&view_type=form`;
                } else {
                    resultDiv.innerHTML = `<div class="alert alert-warning">ไม่พบเอกสาร: ${decodedText}</div>`;
                }
            });
        } else {
            // It's a product barcode - show info
            resultDiv.innerHTML = `<div class="alert alert-success">สแกนได้: <strong>${decodedText}</strong></div>`;
        }
    } catch (error) {
        console.error("Error processing QR code:", error);
    }
}

function onQRCodeError(errorMessage) {
    // Ignore background scanning errors
}

// Cleanup when leaving the form
window.addEventListener('beforeunload', () => {
    window.stopInternalQRScanner();
});

// Patch FormController to stop scanner when changing views
patch(FormController.prototype, {
    async switchView(type) {
        await window.stopInternalQRScanner();
        return this._super(...arguments);
    },
});
