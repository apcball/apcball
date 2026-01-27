# -*- coding: utf-8 -*-

import base64
from odoo import http, _
from odoo.http import request


class MarginApprovalController(http.Controller):
    
    @http.route(['/margin/approve/<int:sale_id>'], type='http', auth="user", website=True)
    def approve_margin(self, sale_id=None, **post):
        sale_order = request.env['sale.order'].sudo().browse(sale_id)
        if not sale_order.exists():
            return request.redirect('/web#action=sale.action_orders')
        
        # Check authorization
        if request.env.user not in sale_order.margin_approval_user_ids and not request.env.user.has_group('sales_team.group_sale_manager') and not request.env.user.has_group('buz_margin_approval.group_margin_approval'):
            return request.render('buz_margin_approval.not_authorized', {
                'message': _("You are not authorized to approve this order's margin."),
                'sale_order': sale_order
            })
        
        sale_order.action_approve_margin()
        return request.redirect('/web#id=%s&view_type=form&model=sale.order' % sale_order.id)
        
    @http.route(['/margin/reject/<int:sale_id>'], type='http', auth="user", website=True)
    def reject_margin(self, sale_id=None, reason=None, **post):
        sale_order = request.env['sale.order'].sudo().browse(sale_id)
        if not sale_order.exists():
            return request.redirect('/web#action=sale.action_orders')
        
        # Check authorization
        if request.env.user not in sale_order.margin_approval_user_ids and not request.env.user.has_group('sales_team.group_sale_manager') and not request.env.user.has_group('buz_margin_approval.group_margin_approval'):
            return request.render('buz_margin_approval.not_authorized', {
                'message': _("You are not authorized to reject this order's margin."),
                'sale_order': sale_order
            })
        
        if request.httprequest.method == 'POST':
            reason = post.get('reason')
            sale_order.action_reject_margin()
            if reason:
                sale_order.message_post(body=_("Rejection reason: %s") % reason)
            return request.redirect('/web#id=%s&view_type=form&model=sale.order' % sale_order.id)
        
        return request.render('buz_margin_approval.reject_reason_form', {
            'sale_order': sale_order
        })
