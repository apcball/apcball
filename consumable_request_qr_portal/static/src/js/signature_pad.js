/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { jsonrpc } from "@web/core/network/rpc_service";

publicWidget.registry.ConsumableRequestPortal = publicWidget.Widget.extend({
    selector: '#wrap',
    
    events: {
        'change .item-check': '_onCheckChange',
        'click #btn-clear-signature': '_onClearSignature',
        'click #btn-confirm-receive': '_onConfirmReceive',
    },

    start: function () {
        var self = this;
        this.canvas = document.getElementById('signature-canvas');
        if (this.canvas) {
            this.ctx = this.canvas.getContext('2d');
            this.drawing = false;
            this.hasSignature = false;
            
            // Adjust canvas resolution for high DPI
            var ratio = Math.max(window.devicePixelRatio || 1, 1);
            // We use clientWidth/clientHeight because offsetWidth might include borders
            this.canvas.width = this.canvas.clientWidth * ratio;
            this.canvas.height = this.canvas.clientHeight * ratio;
            this.ctx.scale(ratio, ratio);

            // Events for drawing
            this.canvas.addEventListener('mousedown', this._startDraw.bind(this));
            this.canvas.addEventListener('mousemove', this._draw.bind(this));
            this.canvas.addEventListener('mouseup', this._endDraw.bind(this));
            this.canvas.addEventListener('mouseout', this._endDraw.bind(this));
            
            // Touch events
            this.canvas.addEventListener('touchstart', this._startDraw.bind(this), {passive: false});
            this.canvas.addEventListener('touchmove', this._draw.bind(this), {passive: false});
            this.canvas.addEventListener('touchend', this._endDraw.bind(this));
        }
        return this._super.apply(this, arguments);
    },

    _startDraw: function (e) {
        if (e.target !== this.canvas) return;
        e.preventDefault();
        this.drawing = true;
        this.hasSignature = true;
        this.ctx.beginPath();
        var pos = this._getPos(e);
        this.ctx.moveTo(pos.x, pos.y);
        this._updateConfirmButton();
    },

    _draw: function (e) {
        if (!this.drawing) return;
        if (e.cancelable) e.preventDefault(); 
        var pos = this._getPos(e);
        this.ctx.lineTo(pos.x, pos.y);
        this.ctx.stroke();
    },

    _endDraw: function (e) {
        this.drawing = false;
    },

    _getPos: function (e) {
        var rect = this.canvas.getBoundingClientRect();
        var clientX = e.clientX;
        var clientY = e.clientY;
        if (e.touches && e.touches.length > 0) {
            clientX = e.touches[0].clientX;
            clientY = e.touches[0].clientY;
        }
        return {
            x: clientX - rect.left,
            y: clientY - rect.top
        };
    },

    _onClearSignature: function () {
        if (this.ctx) {
             this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
             this.ctx.beginPath(); // Reset path
             this.hasSignature = false;
             this._updateConfirmButton();
        }
    },

    _onCheckChange: function () {
        this._updateConfirmButton();
    },

    _updateConfirmButton: function () {
        var allChecked = true;
        if (this.$('.item-check').length > 0) {
             this.$('.item-check').each(function () {
                 if (!$(this).prop('checked')) allChecked = false;
            });
        }
        
        var canConfirm = allChecked && this.hasSignature;
        $('#btn-confirm-receive').prop('disabled', !canConfirm);
    },

    _onConfirmReceive: async function () {
        var self = this;
        var token = $('#qr_token').val();
        var signature = this.canvas.toDataURL('image/png');
        
        $('#btn-confirm-receive').prop('disabled', true).text('Processing...');

        try {
            const result = await jsonrpc('/consumable/request/confirm', {
                token: token,
                signature: signature
            });
            
            if (result.success) {
                window.location.reload();
            } else {
                alert('Error: ' + (result.error || 'Unknown error'));
                self._updateConfirmButton();
                $('#btn-confirm-receive').text('Confirm Receive');
            }
        } catch (error) {
             console.error(error);
             alert('Error: ' + error.message || error);
             self._updateConfirmButton();
             $('#btn-confirm-receive').text('Confirm Receive');
        }
    }
});
