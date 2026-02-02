/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { _t } from "@web/core/l10n/translation";

/**
 * Purchase Order Auto Approval Widget
 * Handles automatic approval for logged-in users
 */
publicWidget.registry.POAutoApprove = publicWidget.Widget.extend({
    selector: '.o_portal_sidebar, .o_portal_content', // Target areas where buttons exist
    events: {
        'click #btn-auto-approve': '_onAutoApprove',
        'click #btn-auto-approve-mobile': '_onAutoApprove',
    },

    _onAutoApprove: function (ev) {
        ev.preventDefault();
        const btn = $(ev.currentTarget);

        // We need to find the form tokens/ids. 
        // Since we are outside the modal, we can grab them from the modal form which should still be present in DOM
        // OR we can add data attributes to the button itself.
        // Let's look at the modal form: <form id="accept" ... t-att-data-order-id="po.id" t-att-data-token="po.approval_token">
        const modalForm = document.getElementById('accept');
        if (!modalForm) {
            console.error('Approval form not found');
            return;
        }

        const poId = modalForm.dataset.orderId;
        const token = modalForm.dataset.token;
        const csrfToken = modalForm.querySelector('input[name="csrf_token"]').value;

        if (!confirm('Confirm approval with your stored signature?')) {
            return;
        }

        // Disable button
        btn.prop('disabled', true);
        const originalContent = btn.html();
        btn.html('<i class="fa fa-spinner fa-spin"/> Processing...');

        const formData = new FormData();
        formData.append('csrf_token', csrfToken);
        formData.append('po_id', poId);
        formData.append('signature', ''); // Explicitly empty for auto-sign

        fetch(`/purchase/approve/${poId}/${token}`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.reload();
                } else {
                    alert(data.message || 'An error occurred.');
                    btn.prop('disabled', false);
                    btn.html(originalContent);
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred.');
                btn.prop('disabled', false);
                btn.html(originalContent);
            });
    }
});

/**
 * Purchase Order Signature Widget
 * Handles signature drawing and form submission for PO approval
 */
publicWidget.registry.POSignature = publicWidget.Widget.extend({
    selector: '#modalaccept',
    events: {
        'show.bs.modal': '_onModalShow',
        'hide.bs.modal': '_onModalHide',
        'click #clearSignature': '_onClearSignature',
        'click #submitApproval': '_onSubmitApproval',
        'change input[name="signature_type"]': '_onSignatureTypeChange',
    },

    /**
     * Initialize the widget
     */
    start: function () {
        this._super.apply(this, arguments);
        this.canvas = null;
        this.ctx = null;
        this.isDrawing = false;
        this.hasSignature = false;
    },

    /**
     * Handle signature type change
     */
    _onSignatureTypeChange: function (ev) {
        const type = ev.target.value;
        if (type === 'draw') {
            this.$('#draw_container').removeClass('d-none');
            this.$('#upload_container').addClass('d-none');
            // Re-init canvas if needed because display:none might affect dimensions
            setTimeout(() => this._initCanvas(), 100);
        } else {
            this.$('#draw_container').addClass('d-none');
            this.$('#upload_container').removeClass('d-none');
        }
    },

    /**
     * Handle modal show event
     */
    _onModalShow: function (ev) {
        const self = this;
        // Initialize canvas after modal is shown
        setTimeout(function () {
            self._initCanvas();
        }, 100);
    },

    /**
     * Initialize canvas for signature drawing
     */
    _initCanvas: function () {
        const self = this;
        this.canvas = document.getElementById('signature');
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        // Match Odoo standard signature color (Dark Blue)
        this.ctx.strokeStyle = '#34495e';
        this.ctx.lineWidth = 4;
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        // Clear the canvas
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.hasSignature = false;

        // Touch events for mobile
        this.canvas.addEventListener('touchstart', function (e) {
            e.preventDefault();
            const touch = e.touches[0];
            const rect = self.canvas.getBoundingClientRect();
            const scaleX = self.canvas.width / rect.width;
            const scaleY = self.canvas.height / rect.height;
            const x = (touch.clientX - rect.left) * scaleX;
            const y = (touch.clientY - rect.top) * scaleY;
            self._startDrawing(x, y);
        });

        this.canvas.addEventListener('touchmove', function (e) {
            e.preventDefault();
            if (!self.isDrawing) return;
            const touch = e.touches[0];
            const rect = self.canvas.getBoundingClientRect();
            const scaleX = self.canvas.width / rect.width;
            const scaleY = self.canvas.height / rect.height;
            const x = (touch.clientX - rect.left) * scaleX;
            const y = (touch.clientY - rect.top) * scaleY;
            self._draw(x, y);
        });

        this.canvas.addEventListener('touchend', function (e) {
            e.preventDefault();
            self._stopDrawing();
        });

        // Mouse events
        this.canvas.addEventListener('mousedown', function (e) {
            const rect = self.canvas.getBoundingClientRect();
            const scaleX = self.canvas.width / rect.width;
            const scaleY = self.canvas.height / rect.height;
            const x = (e.clientX - rect.left) * scaleX;
            const y = (e.clientY - rect.top) * scaleY;
            self._startDrawing(x, y);
        });

        this.canvas.addEventListener('mousemove', function (e) {
            if (!self.isDrawing) return;
            const rect = self.canvas.getBoundingClientRect();
            const scaleX = self.canvas.width / rect.width;
            const scaleY = self.canvas.height / rect.height;
            const x = (e.clientX - rect.left) * scaleX;
            const y = (e.clientY - rect.top) * scaleY;
            self._draw(x, y);
        });

        this.canvas.addEventListener('mouseup', function (e) {
            self._stopDrawing();
        });

        this.canvas.addEventListener('mouseleave', function (e) {
            self._stopDrawing();
        });
    },

    /**
     * Start drawing
     */
    _startDrawing: function (x, y) {
        this.isDrawing = true;
        this.ctx.beginPath();
        this.ctx.moveTo(x, y);
        this.hasSignature = true;
    },

    /**
     * Draw on canvas
     */
    _draw: function (x, y) {
        this.ctx.lineTo(x, y);
        this.ctx.stroke();
    },

    /**
     * Stop drawing
     */
    _stopDrawing: function () {
        if (this.isDrawing) {
            this.ctx.closePath();
            this.isDrawing = false;
        }
    },

    /**
     * Clear signature
     */
    _onClearSignature: function (ev) {
        ev.preventDefault();
        if (this.ctx && this.canvas) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
            this.hasSignature = false;
        }
    },

    /**
     * Handle modal hide event
     */
    _onModalHide: function (ev) {
        // Clean up
        if (this.ctx && this.canvas) {
            this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        }
        this.hasSignature = false;
    },

    /**
     * Submit approval with signature
     */
    _onSubmitApproval: function (ev) {
        ev.preventDefault();
        const self = this;
        const type = this.$('input[name="signature_type"]:checked').val();

        let signatureData = '';

        if (type === 'draw') {
            if (!this.hasSignature) {
                alert('Please provide your signature before submitting.');
                return;
            }
            signatureData = this.canvas.toDataURL('image/png');
            this._submitData(signatureData);
        } else {
            const fileInput = document.getElementById('signature_file');
            if (!fileInput || !fileInput.files || !fileInput.files[0]) {
                alert('Please select a file to upload.');
                return;
            }

            const file = fileInput.files[0];
            // Check size (2MB max)
            if (file.size > 2 * 1024 * 1024) {
                alert('File size too large. Maximum size is 2MB.');
                return;
            }

            const reader = new FileReader();
            reader.onload = function (e) {
                self._submitData(e.target.result);
            };
            reader.readAsDataURL(file);
        }
    },

    /**
     * Internal function to send data to server
     */
    _submitData: function (signatureData) {
        // Get form data
        const form = document.getElementById('accept');
        if (!form) return;

        const formData = new FormData(form);
        formData.append('signature', signatureData);

        const poId = form.dataset.orderId;
        const token = form.dataset.token;

        // Disable submit button
        const submitBtn = document.getElementById('submitApproval');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin"/> Processing...';

        // Submit via AJAX
        fetch(`/purchase/approve/${poId}/${token}`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(response => {
                console.log('Response status:', response.status);
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return response.json();
                } else {
                    return { success: true };
                }
            })
            .then(data => {
                if (data.success) {
                    // Close modal
                    const modalElement = document.getElementById('modalaccept');
                    if (typeof bootstrap !== 'undefined' && modalElement) {
                        const modal = bootstrap.Modal.getInstance(modalElement);
                        if (modal) {
                            modal.hide();
                        }
                    }
                    setTimeout(function () {
                        window.location.reload();
                    }, 300);
                } else {
                    alert(data.message || 'An error occurred. Please try again.');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fa fa-check"/> Approve &amp; Sign';
                }
            })
            .catch(error => {
                console.error('Error details:', error);
                setTimeout(function () {
                    window.location.reload();
                }, 500);
            });
    },
});

/**
 * Purchase Order Rejection Widget
 * Handles rejection form submission with mandatory reason validation
 */
publicWidget.registry.PORejection = publicWidget.Widget.extend({
    selector: '#modalreject',
    events: {
        'click #submitRejection': '_onSubmitRejection',
    },

    /**
     * Submit rejection with reason
     */
    _onSubmitRejection: function (ev) {
        ev.preventDefault();
        const self = this;

        // Get reject reason
        const reasonTextarea = document.getElementById('reject_reason');
        const reason = reasonTextarea ? reasonTextarea.value.trim() : '';

        // Validate reason
        if (!reason) {
            reasonTextarea.classList.add('is-invalid');
            document.getElementById('reject_reason_error').style.display = 'block';
            return;
        }

        reasonTextarea.classList.remove('is-invalid');
        document.getElementById('reject_reason_error').style.display = 'none';

        // Get form data
        const form = document.getElementById('reject');
        if (!form) return;

        const formData = new FormData(form);
        formData.append('reject_reason', reason);

        const poId = form.dataset.orderId;
        const token = form.dataset.token;

        // Disable submit button
        const submitBtn = document.getElementById('submitRejection');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin"/> กำลังดำเนินการ...';

        // Submit via AJAX
        fetch(`/purchase/reject/${poId}/${token}`, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
            .then(response => {
                console.log('Response status:', response.status);
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    return response.json();
                } else {
                    return { success: true };
                }
            })
            .then(data => {
                if (data.success) {
                    // Show success message
                    alert(data.message || 'บันทึกการไม่อนุมัติเรียบร้อย\nเหตุผลถูกส่งกลับไปยังผู้จัดทำเอกสาร');

                    // Close modal
                    const modalElement = document.getElementById('modalreject');
                    if (typeof bootstrap !== 'undefined' && modalElement) {
                        const modal = bootstrap.Modal.getInstance(modalElement);
                        if (modal) {
                            modal.hide();
                        }
                    }
                    setTimeout(function () {
                        window.location.reload();
                    }, 300);
                } else {
                    alert(data.message || 'เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง');
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fa fa-ban"/> Confirm Reject';
                }
            })
            .catch(error => {
                console.error('Error details:', error);
                alert('เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง');
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fa fa-ban"/> Confirm Reject';
            });
    },
});
