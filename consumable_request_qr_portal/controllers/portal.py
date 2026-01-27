# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError

class ConsumableRequestPortal(http.Controller):

    @http.route('/consumable/request/<string:token>', type='http', auth='public', website=True)
    def portal_view(self, token, **kwargs):
        req = request.env['internal.consume.request'].sudo().search([
            ('qr_token', '=', token)
        ], limit=1)
        
        if not req:
            return request.render('consumable_request_qr_portal.portal_request_not_found')
        
        if req.state not in ('approved', 'issued', 'done'):
             return request.render('consumable_request_qr_portal.portal_request_access_denied', {
                 'message': 'Request must be Approved to view.'
             })

        values = {
            'consumable_request': req,
            'token': token,
            'user': request.env.user,
            'is_internal_user': request.env.user.has_group('base.group_user'), # Check if logged-in internal user
        }
        return request.render('consumable_request_qr_portal.portal_request_view', values)

    @http.route('/consumable/request/issue', type='json', auth='user')
    def portal_issue_goods(self, token, **kwargs):
        """ Allow logged-in stock user to issue goods from portal """
        req = request.env['internal.consume.request'].sudo().search([
            ('qr_token', '=', token)
        ], limit=1)
        
        if not req:
            return {'error': 'Request not found'}
            
        if req.state != 'approved':
             return {'error': 'Request must be in Approved state to issue.'}

        try:
            # Check permissions (optional, but good practice. The button only shows if logged in)
            # We use sudo() on the model above to find it, but the action itself should check access rights usually.
            # Here we are calling action_issue_goods which might check groups.
            # But since we are in a 'json' controller authenticated as 'user', we can try calling it as the user.
            
            # Re-browse as user to ensure rights checking if needed, or stick to sudo if we want to allow any internal user
            # existing action_issue_goods method has `groups="stock.group_stock_user"` in XML but not in python (except implicit model access).
            # Let's try calling it as the current user.
            req.with_user(request.env.user).action_issue_goods()
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}

    @http.route('/consumable/request/confirm', type='json', auth='public')
    def portal_confirm(self, token, signature, **kwargs):
        req = request.env['internal.consume.request'].sudo().search([
            ('qr_token', '=', token)
        ], limit=1)
        
        if not req:
            return {'error': 'Request not found'}
        
        if req.state != 'issued':
            return {'error': 'Request must be in Issued state to confirm receive.'}
            
        if req.portal_confirmed:
            return {'error': 'Already confirmed'}
            
        if not signature:
            return {'error': 'Signature is required'}
            
        if ',' in signature:
            signature = signature.split(',')[1]
            
        try:
            req.action_portal_receive(signature)
            return {'success': True}
        except Exception as e:
            return {'error': str(e)}
