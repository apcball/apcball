# -*- coding: utf-8 -*-
"""
Portal Approval Controller
==========================

This controller handles portal-based document approval.
It validates tokens, displays documents, and processes approve/reject actions.
"""

import logging

from odoo import http, fields, _
from odoo.http import request
from odoo.exceptions import AccessDenied, ValidationError

_logger = logging.getLogger(__name__)


class PortalApprovalController(http.Controller):
    """Controller for handling approval requests via portal."""

    def _get_client_info(self):
        """
        Get client IP address and user agent from request.
        
        Returns:
            tuple: (ip_address, user_agent)
        """
        ip_address = request.httprequest.remote_addr
        user_agent = request.httprequest.user_agent.string if request.httprequest.user_agent else ''
        
        # Handle proxy headers
        forwarded_for = request.httprequest.headers.get('X-Forwarded-For')
        if forwarded_for:
            ip_address = forwarded_for.split(',')[0].strip()
            
        return ip_address, user_agent

    def _validate_token(self, model, doc_id, token):
        """
        Validate the approval token.
        
        Args:
            model: Document model name
            doc_id: Document ID
            token: Token string
            
        Returns:
            tuple: (token_record, error_dict)
        """
        ApprovalToken = request.env['approval.token'].sudo()
        
        # Find and validate token
        token_record = ApprovalToken.validate_token(token, model, doc_id)
        
        if not token_record:
            return None, {
                'error': 'invalid_token',
                'message': _("The approval link is invalid or has expired."),
            }
        
        # Check rate limiting
        ICP = request.env['ir.config_parameter'].sudo()
        max_views = int(ICP.get_param('line_portal_notification.max_token_views', 50))
        
        if token_record.check_rate_limit(max_views):
            # Log rate limit hit
            ip_address, user_agent = self._get_client_info()
            request.env['approval.audit.log'].sudo().log_action(
                res_model=model,
                res_id=doc_id,
                action='rate_limited',
                token_id=token_record.id,
                token_value=token,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return None, {
                'error': 'rate_limited',
                'message': _("Too many access attempts. Please request a new approval link."),
            }
        
        return token_record, None

    def _get_document(self, model, doc_id):
        """
        Get the document record.
        
        Args:
            model: Document model name
            doc_id: Document ID
            
        Returns:
            record or None
        """
        try:
            # Check if model exists
            if model not in request.env:
                return None
            
            record = request.env[model].sudo().browse(doc_id)
            if not record.exists():
                return None
                
            return record
        except Exception as e:
            _logger.error("Error fetching document %s/%s: %s", model, doc_id, str(e))
            return None

    @http.route(
        '/my/approve/<string:model>/<int:doc_id>',
        type='http',
        auth='public',
        website=True,
        methods=['GET'],
    )
    def portal_approval_view(self, model, doc_id, token=None, **kwargs):
        """
        Display the document for approval in portal.
        
        Args:
            model: Document model name
            doc_id: Document ID
            token: Approval token
            
        Returns:
            HTTP response
        """
        ip_address, user_agent = self._get_client_info()
        
        # Token is required
        if not token:
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Access Denied"),
                'error_message': _("An approval token is required to access this page."),
            })
        
        # Validate token
        token_record, error = self._validate_token(model, doc_id, token)
        
        if error:
            # Log invalid access
            request.env['approval.audit.log'].sudo().log_action(
                res_model=model,
                res_id=doc_id,
                action='invalid_access',
                token_value=token,
                ip_address=ip_address,
                user_agent=user_agent,
                notes=error.get('message'),
            )
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Access Denied"),
                'error_message': error['message'],
            })
        
        # Get document
        document = self._get_document(model, doc_id)
        
        if not document:
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Document Not Found"),
                'error_message': _("The requested document could not be found."),
            })
        
        # Increment view count
        token_record.increment_view_count()
        
        # Log portal view
        request.env['approval.audit.log'].sudo().log_action(
            res_model=model,
            res_id=doc_id,
            action='portal_viewed',
            approver_id=token_record.approver_id.id,
            line_user_id=token_record.line_user_id,
            token_id=token_record.id,
            token_value=token,
            ip_address=ip_address,
            user_agent=user_agent,
            res_name=token_record.res_name,
        )
        
        # Build document info for display
        doc_info = self._build_document_info(document)
        
        return request.render('line_portal_notification.portal_approval_page', {
            'document': document,
            'doc_info': doc_info,
            'token': token,
            'token_record': token_record,
            'model': model,
            'doc_id': doc_id,
        })

    def _build_document_info(self, document):
        """
        Build document information dictionary for display.
        
        Args:
            document: Document record
            
        Returns:
            dict: Document information
        """
        info = {
            'name': '',
            'amount': '',
            'date': '',
            'state': '',
            'description': '',
            'lines': [],
            'partner': '',
            'currency': '',
        }
        
        # Get document name
        for field in ['name', 'display_name', 'reference', 'ref']:
            if hasattr(document, field):
                value = getattr(document, field)
                if value:
                    info['name'] = value
                    break
        
        # Get amount
        for field in ['amount_total', 'total_amount', 'amount', 'total']:
            if hasattr(document, field):
                amount = getattr(document, field)
                if amount:
                    info['amount'] = amount
                    break
        
        # Get currency
        for field in ['currency_id', 'company_currency_id']:
            if hasattr(document, field):
                currency = getattr(document, field)
                if currency:
                    info['currency'] = currency.name
                    break
        
        # Get date
        for field in ['date_order', 'date', 'create_date']:
            if hasattr(document, field):
                date = getattr(document, field)
                if date:
                    info['date'] = date
                    break
        
        # Get state
        if hasattr(document, 'state'):
            info['state'] = document.state
        
        # Get partner
        for field in ['partner_id', 'vendor_id', 'supplier_id']:
            if hasattr(document, field):
                partner = getattr(document, field)
                if partner:
                    info['partner'] = partner.name
                    break
        
        # Get description/notes
        for field in ['note', 'notes', 'description', 'narration']:
            if hasattr(document, field):
                value = getattr(document, field)
                if value:
                    info['description'] = value
                    break
        
        # Try to get order lines
        for field in ['order_line', 'invoice_line_ids', 'line_ids', 'move_line_ids']:
            if hasattr(document, field):
                lines = getattr(document, field)
                if lines:
                    for line in lines[:10]:  # Limit to 10 lines
                        line_info = {'name': '', 'quantity': '', 'price': ''}
                        
                        if hasattr(line, 'name'):
                            line_info['name'] = line.name
                        elif hasattr(line, 'product_id') and line.product_id:
                            line_info['name'] = line.product_id.name
                            
                        if hasattr(line, 'product_qty'):
                            line_info['quantity'] = line.product_qty
                        elif hasattr(line, 'quantity'):
                            line_info['quantity'] = line.quantity
                            
                        if hasattr(line, 'price_subtotal'):
                            line_info['price'] = line.price_subtotal
                        elif hasattr(line, 'price_total'):
                            line_info['price'] = line.price_total
                            
                        info['lines'].append(line_info)
                    break
        
        return info

    @http.route(
        '/my/approve/<string:model>/<int:doc_id>/action',
        type='http',
        auth='public',
        website=True,
        methods=['POST'],
        csrf=True,
    )
    def portal_approval_action(self, model, doc_id, token=None, action=None, reject_reason=None, **kwargs):
        """
        Process approval or rejection action.
        
        Args:
            model: Document model name
            doc_id: Document ID
            token: Approval token
            action: 'approve' or 'reject'
            reject_reason: Optional rejection reason
            
        Returns:
            HTTP response
        """
        ip_address, user_agent = self._get_client_info()
        
        # Validate inputs
        if not token:
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Access Denied"),
                'error_message': _("An approval token is required."),
            })
        
        if action not in ['approve', 'reject']:
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Invalid Action"),
                'error_message': _("Invalid action specified."),
            })
        
        # Validate token
        token_record, error = self._validate_token(model, doc_id, token)
        
        if error:
            request.env['approval.audit.log'].sudo().log_action(
                res_model=model,
                res_id=doc_id,
                action='invalid_access',
                token_value=token,
                ip_address=ip_address,
                user_agent=user_agent,
                notes=f"Action attempted: {action}",
            )
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Access Denied"),
                'error_message': error['message'],
            })
        
        # Get document
        document = self._get_document(model, doc_id)
        
        if not document:
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Document Not Found"),
                'error_message': _("The requested document could not be found."),
            })
        
        # Process the action
        try:
            if action == 'approve':
                # Check if document has action_approve method
                if hasattr(document, 'action_approve'):
                    document.action_approve()
                else:
                    # Try to update state directly
                    if hasattr(document, 'state'):
                        document.write({'state': 'approved'})
                
                action_for_log = 'approved'
                result_title = _("Document Approved")
                result_message = _("The document has been approved successfully.")
                
            else:  # reject
                # Check if document has action_reject method
                if hasattr(document, 'action_reject'):
                    if reject_reason and hasattr(document, 'reject_reason'):
                        document.reject_reason = reject_reason
                    document.action_reject()
                else:
                    # Try to update state directly
                    if hasattr(document, 'state'):
                        document.write({'state': 'rejected'})
                
                action_for_log = 'rejected'
                result_title = _("Document Rejected")
                result_message = _("The document has been rejected.")
            
            # Mark token as used
            token_record.mark_as_used(action_for_log)
            
            # Log the action
            notes = reject_reason if action_for_log == 'rejected' and reject_reason else None
            request.env['approval.audit.log'].sudo().log_action(
                res_model=model,
                res_id=doc_id,
                action=action_for_log,
                approver_id=token_record.approver_id.id,
                line_user_id=token_record.line_user_id,
                token_id=token_record.id,
                token_value=token,
                ip_address=ip_address,
                user_agent=user_agent,
                res_name=token_record.res_name,
                notes=notes,
            )
            
            # Post message to chatter if available
            if hasattr(document, 'message_post'):
                approver_name = token_record.approver_id.name
                if action_for_log == 'approved':
                    body = _("Document approved via portal by %s") % approver_name
                else:
                    body = _("Document rejected via portal by %s") % approver_name
                    if reject_reason:
                        body += f"\n{_('Reason')}: {reject_reason}"
                
                document.message_post(body=body, message_type='notification')
            
            return request.render('line_portal_notification.portal_success', {
                'success_title': result_title,
                'success_message': result_message,
                'document_name': token_record.res_name,
            })
            
        except Exception as e:
            _logger.error(
                "Error processing approval action for %s/%s: %s",
                model, doc_id, str(e)
            )
            
            # Log the error
            request.env['approval.audit.log'].sudo().log_action(
                res_model=model,
                res_id=doc_id,
                action='invalid_access',
                approver_id=token_record.approver_id.id,
                token_id=token_record.id,
                token_value=token,
                ip_address=ip_address,
                user_agent=user_agent,
                notes=f"Error: {str(e)}",
            )
            
            return request.render('line_portal_notification.portal_error', {
                'error_title': _("Error"),
                'error_message': _("An error occurred while processing your request. Please try again or contact support."),
            })
