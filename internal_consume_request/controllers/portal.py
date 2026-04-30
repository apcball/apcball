# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
import json
import logging

_logger = logging.getLogger(__name__)


class InternalConsumePortal(http.Controller):

    @http.route(['/consume/receive/<string:token>'], type='http', auth="public", website=True)
    def consume_receive_portal(self, token, **kwargs):
        """Render the portal page showing the QR Code for the employee"""
        request_sudo = request.env['internal.consume.request'].sudo().search([
            ('name', '=', token),
        ], limit=1)

        if not request_sudo or request_sudo.state not in ['approved', 'done']:
            return request.render('website.page_404', {})
            
        if request_sudo.picking_id or request_sudo.signature:
            # Already processed -> Redirect to success/already done page
            return request.render('internal_consume_request.portal_receive_success', {
                'message': _('This request has already been confirmed and signed.')
            })
            
        values = {
            'req': request_sudo,
            'token': token,
        }
        return request.render('internal_consume_request.portal_display_qr_template', values)

    @http.route(['/consume/scan/<string:token>'], type='http', auth="public", website=True)
    def consume_scan_portal(self, token, **kwargs):
        """Render the portal page for receiving consumables (Stock Staff View)"""
        request_sudo = request.env['internal.consume.request'].sudo().search([
            ('name', '=', token),
        ], limit=1)

        if not request_sudo or request_sudo.state not in ['approved', 'done']:
            return request.render('website.page_404', {})
            
        if request_sudo.picking_id or request_sudo.signature:
            # Already processed -> Redirect to success/already done page
            return request.render('internal_consume_request.portal_receive_success', {
                'message': _('This request has already been confirmed and signed.')
            })
            
        values = {
            'req': request_sudo,
            'token': token,
        }
        return request.render('internal_consume_request.portal_scan_template', values)

    @http.route(['/consume/confirm'], type='json', auth="public", methods=['POST'], website=True, csrf=False)
    def consume_confirm_portal(self, **post):
        """Process the confirmation from the portal"""
        token = post.get('token')
        signature = post.get('signature')
        stock_signature = post.get('stock_signature')
        lines_data = post.get('lines', [])
        
        if not token:
            return {'success': False, 'error': _('Invalid Token')}
            
        request_sudo = request.env['internal.consume.request'].sudo().search([
            ('name', '=', token),
            ('state', '=', 'approved')
        ], limit=1)
        
        if not request_sudo:
            return {'success': False, 'error': _('Request not found or already processed')}
            
        # Clean base64 signature if it has prefix 'data:image/png;base64,'
        if signature and ',' in signature:
            signature = signature.split(',')[1]
            
        if stock_signature and ',' in stock_signature:
            stock_signature = stock_signature.split(',')[1]
            
        try:
            # Call the model method to process confirmation
            request_sudo.action_confirm_receive(signature, stock_signature, lines_data)
            return {
                'success': True, 
                'redirect_url': f'/consume/success?token={token}'
            }
        except Exception as e:
            _logger.error(f"Error confirming consumable request: {str(e)}")
            return {'success': False, 'error': str(e)}

    @http.route(['/consume/success'], type='http', auth="public", website=True)
    def consume_success_page(self, token=None, **kwargs):
        """Render success page after confirmation"""
        message = kwargs.get('message', False)
        return request.render('internal_consume_request.portal_receive_success', {'message': message})
