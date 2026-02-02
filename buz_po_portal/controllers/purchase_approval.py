from odoo import http, fields, _
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class PurchaseApprovalController(http.Controller):

    @http.route(
        '/l/purchase/approve/<string:token>',
        type='http',
        auth='public',
        website=True
    )
    def landing_page(self, token, action=None, **kwargs):
        """
        Landing page for LINE browser detection.
        Detects LINE browser and shows 'Open in Browser' page.
        Non-LINE browsers are redirected to the actual approval page.
        """
        # Get user agent
        user_agent = request.httprequest.user_agent.string if request.httprequest.user_agent else ''
        
        # Check if it's LINE browser
        is_line_browser = 'Line/' in user_agent or 'LINE/' in user_agent
        
        # Validate token exists (basic check)
        token_rec = request.env['approval.token'].sudo().search([
            ('token', '=', token),
            ('res_model', '=', 'purchase.order'),
        ], limit=1)
        
        po = None
        if token_rec:
            po = request.env['purchase.order'].sudo().browse(token_rec.res_id)
        else:
            # Fallback to legacy token
            po = request.env['purchase.order'].sudo().search([
                ('approval_token', '=', token),
            ], limit=1)
        
        if not po or not po.exists():
            return request.render('http_routing.403')
        
        # If not LINE browser, redirect to approval page
        # Modified to ALWAYS redirect, allowing LINE browser to open directly
        # if not is_line_browser: 
        base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url')
        approval_url = f"{base_url}/purchase/approve/token/{token}"
        
        params = []
        if action:
            params.append(f"action={action}")
            
        # Propagate DB parameter to ensure correct DB selection
        db = kwargs.get('db')
        if db:
            params.append(f"db={db}")
        
        if params:
            approval_url += "?" + "&".join(params)
            
        return request.redirect(approval_url)

    @http.route(
        '/purchase/approve/token/<string:token>',
        type='http',
        auth='public',
        website=True
    )
    def approve_po_by_token(self, token, action=None):
        # 1. Look up via approval.token model
        token_rec = request.env['approval.token'].sudo().search([
            ('token', '=', token),
            ('res_model', '=', 'purchase.order'),
        ], limit=1)

        po = None
        is_expired = False
        
        if token_rec:
            po = request.env['purchase.order'].sudo().browse(token_rec.res_id)
            if token_rec.state != 'active':
                is_expired = True
            elif token_rec.is_expired:
                is_expired = True
                
            # Rate limiting / View counting from generic model
            token_rec.increment_view_count()
            
        else:
            # Fallback: Look up via legacy fields on PO
            po = request.env['purchase.order'].sudo().search([
                ('approval_token', '=', token),
            ], limit=1)
            
            if po:
                if po.approval_token_expired:
                     is_expired = True
                elif po.approval_token_created:
                    from datetime import timedelta
                    expiry_days = int(request.env['ir.config_parameter'].sudo().get_param('line_portal_notification.token_expiry_days', 7))
                    expiration_time = po.approval_token_created + timedelta(days=expiry_days)
                    if fields.Datetime.now() > expiration_time:
                         is_expired = True

        if not po or not po.exists():
            return request.render('http_routing.403')

        return request.render(
            'buz_po_portal.po_signature_page_public',
            {
                'po': po, 
                'token_expired_by_time': is_expired,
                'approval_token': token,  # Pass token to template for form submission
                'action': action,  # Pass action (approve/reject) to template
            }
        )
        

    @http.route(
        '/purchase/approve/print/<string:token>',
        type='http',
        auth='public',
        website=True
    )
    def print_po_by_token(self, token):
        # Find PO via token (active or inactive)
        token_rec = request.env['approval.token'].sudo().search([
            ('token', '=', token),
            ('res_model', '=', 'purchase.order'),
        ], limit=1)

        po = None
        if token_rec:
            po = request.env['purchase.order'].sudo().browse(token_rec.res_id)
        else:
            po = request.env['purchase.order'].sudo().search([
                ('approval_token', '=', token),
            ], limit=1)

        if not po or not po.exists():
            return request.render('http_routing.403')

        # Generate PDF
        pdf_content, _ = request.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'buz_po_portal.action_report_purchase_order_custom',
            [po.id]
        )
        
        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(pdf_content)),
            ('Content-Disposition', f'attachment; filename="Purchase Order {po.name}.pdf"'),
        ]
        return request.make_response(pdf_content, headers=pdfhttpheaders)

    @http.route(
        '/purchase/approve/<int:po_id>/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        website=True,
        csrf=False 
    )
    def confirm_approval(self, po_id, token, **post):
        po = request.env['purchase.order'].sudo().browse(po_id)
        
        # Debug logging
        _logger.info(f"PO Approval Attempt - ID: {po_id}, Token: {token}")

        if not po.exists():
            return request.make_json_response({
                'success': False,
                'message': 'Purchase Order not found.'
            })

        # Validate Token
        token_rec = request.env['approval.token'].sudo().search([
            ('token', '=', token),
            ('res_model', '=', 'purchase.order'),
            ('res_id', '=', po.id)
        ], limit=1)
        
        if token_rec:
            if token_rec.state != 'active':
                 return request.make_json_response({
                    'success': False,
                    'message': 'This link has expired or has already been used.'
                })
            if token_rec.is_expired:
                 return request.make_json_response({
                    'success': False,
                    'message': 'This approval link has expired.'
                })
        else:
            # Fallback legacy check
            if po.approval_token != token:
                return request.make_json_response({
                    'success': False,
                    'message': 'Invalid token.'
                })
            if po.approval_token_expired:
                return request.make_json_response({
                    'success': False,
                    'message': 'This order has already been approved.'
                })

        # Handle signature
        signature = post.get('signature', '')
        if signature:
            # Remove data:image/png;base64, prefix if present
            if signature.startswith('data:image'):
                signature = signature.split(',')[1]
        elif request.session.uid:
             # Auto-sign for logged in user
             user = request.env['res.users'].sudo().browse(request.session.uid)
             employee = user.employee_id
             if not employee:
                 return request.make_json_response({
                    'success': False,
                    'message': 'Logged in user is not linked to an employee. Cannot usage auto-signature.'
                })
             if not employee.signature_image:
                  return request.make_json_response({
                    'success': False,
                    'message': 'No signature found in your Employee profile. Please upload one first.'
                })
             signature = employee.signature_image
        
        if not signature:
             return request.make_json_response({
                'success': False,
                'message': 'Signature is required.'
            })

        # Update PO
        po.write({
            'approval_signature': signature,
            'approval_state': 'approved',
            'approval_date': fields.Datetime.now(),
            'approval_token_expired': True, # Keep legacy field updated
        })
        
        # Mark token as used
        if token_rec:
            token_rec.mark_as_used('approved')
        
        # Complete Approver Activity
        if po.approver_id:
             activity_domain = [('res_id', '=', po.id), ('res_model', '=', 'purchase.order'), ('user_id', '=', po.approver_id.id)]
             activity = request.env['mail.activity'].sudo().search(activity_domain, limit=1)
             if activity:
                 activity.action_feedback(feedback="Approved via Portal Loop")

        # Notify Creator (Activity)
        if po.user_id:
             request.env['mail.activity'].sudo().create({
                 'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                 'note': _('Purchase Order has been approved by %s') % (po.approver_id.name or 'Manager'),
                 'user_id': po.user_id.id,
                 'res_id': po.id,
                 'res_model_id': request.env.ref('purchase.model_purchase_order').id,
                 'summary': _('PO Approved via Portal'),
             })

        po.button_confirm()
        if po.state == 'to approve':
             po.button_approve()
        
        # Double check state
        if po.state != 'purchase' and po.state != 'done':
             _logger.warning(f"PO Portal: PO {po.name} did not reach 'purchase' state. Current state: {po.state}")

        # Notify Creator via LINE
        if po.user_id and po.user_id.line_user_id:
            try:
                line_service = request.env['line.api.service']
                approver_name = po.approver_id.name or 'Manager'
                msg = f"✅ Purchase Order Approved\n\nPO No: {po.name}\nApproved by: {approver_name}"
                line_service.send_push_message(po.user_id.line_user_id, msg)
            except Exception as e:
                _logger.error(f"Failed to send LINE notification to creator: {e}")

        msg = f"Purchase Order approved remotely via email/line link from IP {request.httprequest.remote_addr}."
        po.message_post(body=msg)

        return request.make_json_response({
            'success': True,
            'message': 'Purchase Order approved successfully!'
        })

    @http.route(
        '/purchase/reject/<int:po_id>/<string:token>',
        type='http',
        auth='public',
        methods=['POST'],
        website=True,
        csrf=False
    )
    def confirm_rejection(self, po_id, token, **post):
        """Handle PO rejection with mandatory reason."""
        po = request.env['purchase.order'].sudo().browse(po_id)
        
        # Debug logging
        _logger.info(f"PO Rejection Attempt - ID: {po_id}, Token: {token}")

        if not po.exists():
            return request.make_json_response({
                'success': False,
                'message': 'Purchase Order not found.'
            })

        # Get reject reason
        reject_reason = post.get('reject_reason', '').strip()
        if not reject_reason:
            return request.make_json_response({
                'success': False,
                'message': 'กรุณาระบุเหตุผลในการไม่อนุมัติ (Rejection reason is required.)'
            })

        # Validate Token
        token_rec = request.env['approval.token'].sudo().search([
            ('token', '=', token),
            ('res_model', '=', 'purchase.order'),
            ('res_id', '=', po.id)
        ], limit=1)
        
        if token_rec:
            if token_rec.state != 'active':
                 return request.make_json_response({
                    'success': False,
                    'message': 'This link has expired or has already been used.'
                })
            if token_rec.is_expired:
                 return request.make_json_response({
                    'success': False,
                    'message': 'This approval link has expired.'
                })
        else:
            # Fallback legacy check
            if po.approval_token != token:
                return request.make_json_response({
                    'success': False,
                    'message': 'Invalid token.'
                })
            if po.approval_token_expired:
                return request.make_json_response({
                    'success': False,
                    'message': 'This order has already been processed.'
                })

        # Call action_reject with reason
        po.action_reject(reject_reason=reject_reason)
        
        # Mark token as used
        if token_rec:
            token_rec.mark_as_used('rejected')
        else:
            po.write({'approval_token_expired': True})
        
        # Complete Approver Activity
        if po.approver_id:
             activity_domain = [('res_id', '=', po.id), ('res_model', '=', 'purchase.order'), ('user_id', '=', po.approver_id.id)]
             activity = request.env['mail.activity'].sudo().search(activity_domain, limit=1)
             if activity:
                 activity.action_feedback(feedback=f"Rejected via Portal: {reject_reason}")

        # Notify Creator (Activity)
        if po.user_id:
             request.env['mail.activity'].sudo().create({
                 'activity_type_id': request.env.ref('mail.mail_activity_data_todo').id,
                 'note': _('Purchase Order has been rejected.\nReason: %s') % reject_reason,
                 'user_id': po.user_id.id,
                 'res_id': po.id,
                 'res_model_id': request.env.ref('purchase.model_purchase_order').id,
                 'summary': _('PO Rejected via Portal'),
             })

        # Notify Creator via LINE
        if po.user_id and po.user_id.line_user_id:
            try:
                line_service = request.env['line.api.service']
                approver_name = po.approver_id.name or 'Manager'
                msg = f"❌ Purchase Order Rejected\n\nPO No: {po.name}\nRejected by: {approver_name}\nReason: {reject_reason}"
                line_service.send_push_message(po.user_id.line_user_id, msg)
            except Exception as e:
                _logger.error(f"Failed to send LINE notification to creator: {e}")

        msg = f"Purchase Order rejected remotely via email/line link from IP {request.httprequest.remote_addr}.\nReason: {reject_reason}"
        po.message_post(body=msg)

        return request.make_json_response({
            'success': True,
            'message': 'บันทึกการไม่อนุมัติเรียบร้อย (Purchase Order rejected successfully.)'
        })

    @http.route(
        '/purchase/approve/success/<string:token>',
        type='http',
        auth='public',
        website=True
    )
    def approval_success(self, token):
        # Allow viewing success page even if token is expired
        # Try finding via token record first
        token_rec = request.env['approval.token'].sudo().search([
            ('token', '=', token),
            ('res_model', '=', 'purchase.order'),
        ], limit=1)
        
        po = None
        if token_rec:
            po = request.env['purchase.order'].sudo().browse(token_rec.res_id)
        else:
            po = request.env['purchase.order'].sudo().search([
                ('approval_token', '=', token)
            ], limit=1)
        
        if not po or not po.exists():
            return request.render('http_routing.403')
            
        return request.render('buz_po_portal.approval_success_page', {'po': po})
