from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError
import secrets
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    _name = 'purchase.order'
    _inherit = ['purchase.order', 'line.approval.mixin']

    requested_by_id = fields.Many2one('res.users', string='Requested By')
    buz_purchase_request_id = fields.Many2one('buz.purchase.request', string="Purchase Request")
    partner_contact_id = fields.Many2one('res.partner', string="Contact Person")
    client_order_ref = fields.Char(string='Customer Reference')
    employee_contact_id = fields.Many2one('res.partner', string="Contact Person")
    payment_term_id = fields.Many2one('account.payment.term', string="Payment Term")
    date_order = fields.Datetime(string="Order Date")
    date_planned = fields.Datetime(string='Planned Date', default=fields.Datetime.now)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True)
    department_id = fields.Many2one(
        'hr.department',
        string="แผนก",
        related='user_id.employee_id.department_id',
        store=True,
        readonly=True
    )
    requisition_id = fields.Many2one('purchase.requisition', string='Purchase Agreement')
    custom_request_date = fields.Date(string="วันที่ตามแบบฟอร์ม")
    delivery_date = fields.Date(string="วันที่ส่งมอบ")
    project_id = fields.Many2one('project.project', string="Project")
    remarks = fields.Char(string="หมายเหตุ")
    district_id = fields.Many2one('res.country.district', string="ตำบล")
    department_name = fields.Char(
        string='Department Name',
        compute='_compute_department_name',
        store=False
    )
    amount_total_text_th = fields.Char(
        string='Amount Total (Thai Text)',
        compute='_compute_amount_total_text_th',
        store=False
    )
    has_vat = fields.Boolean(
        string='Has VAT',
        compute='_compute_has_vat',
        store=False
    )
    destination_location_id = fields.Many2one('stock.location', string="Destination Location")
    l1_approved_by = fields.Many2one('res.users', string='Checked by (L1)')
    l1_approved_date = fields.Date(string='Checked Date (L1)')
    l2_approved_by = fields.Many2one('res.users', string='Approved by (L2)')
    l2_approved_date = fields.Date(string='Approved Date (L2)')

    # Approval Flow Fields
    prepared_signature = fields.Binary(string='Prepared Signature', copy=False, attachment=True)
    prepared_date = fields.Datetime(string='Prepared Date', copy=False)

    reviewer_id = fields.Many2one('res.users', string='Reviewer', tracking=True)
    reviewed_signature = fields.Binary(string='Reviewer Signature', copy=False, attachment=True)
    reviewed_date = fields.Datetime(string='Reviewed Date', copy=False)

    # New Manager Approval Fields
    approval_state = fields.Selection([
        ('draft', 'Draft'),
        ('to_review', 'Waiting for Review'),
        ('to_approve', 'Waiting for Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected')
    ], string='Approval Status', default='draft', tracking=True, copy=False)
    
    approver_id = fields.Many2one('res.users', string='Manager Approver', tracking=True)
    approval_date = fields.Datetime(string='Approval Date', copy=False)
    approval_signature = fields.Binary(string='Signature', copy=False, attachment=True)
    approval_token = fields.Char(string='Approval Token', copy=False)
    approval_token_created = fields.Datetime(string='Token Created On', copy=False)
    approval_token_expired = fields.Boolean(string='Token Expired', default=False, copy=False)
    reject_reason = fields.Text(string='Rejection Reason', copy=False)


    can_review = fields.Boolean(compute='_compute_visual_buttons')
    can_approve = fields.Boolean(compute='_compute_visual_buttons')

    @api.depends('reviewer_id', 'approver_id', 'approval_state')
    def _compute_visual_buttons(self):
        for rec in self:
            is_admin = self.env.user.has_group('base.group_system')
            # Check review
            item_can_review = False
            if rec.approval_state == 'to_review':
                 if is_admin or rec.reviewer_id == self.env.user:
                     item_can_review = True
            rec.can_review = item_can_review

            # Check approve
            item_can_approve = False
            if rec.approval_state == 'to_approve':
                 if is_admin or rec.approver_id == self.env.user:
                     item_can_approve = True
            rec.can_approve = item_can_approve

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'approval_state' not in vals:
                vals['approval_state'] = 'draft'
        return super(PurchaseOrder, self).create(vals_list)

    def _generate_approval_token(self):
        self.ensure_one()
        self.approval_token = secrets.token_urlsafe(32)
        self.approval_token_created = fields.Datetime.now()
        self.approval_token_expired = False

    def get_public_approval_url(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        if not self.approval_token:
             self._generate_approval_token()
        db_name = self.env.cr.dbname
        return f"{base_url}/l/purchase/approve/{self.approval_token}?db={db_name}"


    def action_submit_for_review(self):
        self.ensure_one()
        
        # Validation: Check if Analytic Distribution is set for all lines
        for line in self.order_line:
            if not line.display_type and not line.analytic_distribution:
                raise UserError(_("Please specify Analytic Account (Analytic Distribution) for all lines before submitting for review.\nProduct: %s") % line.name)

        # Auto-sign if employee has signature
        employee = self.env.user.employee_id
        if not employee:
            raise UserError(_("Current user is not linked to an Employee record."))
            
        if not employee.signature_image:
            raise UserError(_("You have not uploaded a signature in your Employee profile.\nPlease go to Employees app > select your profile > upload signature."))

        company = self.company_id
        if not company.po_reviewer_id:
            raise UserError(_("No default reviewer configured. Please set up the Purchase Order Reviewer in Settings."))

        # Update PO
        self.write({
            'prepared_signature': employee.signature_image,
            'prepared_date': fields.Datetime.now(),
            'approval_state': 'to_review',
            'reviewer_id': company.po_reviewer_id.id
        })

        # Schedule Review Activity
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=company.po_reviewer_id.id,
            summary='Please Review Purchase Order',
            note=f'Purchase Order {self.name} needs your review.'
        )
        
        # Trigger LINE Notification
        self.action_send_line_approval_request(raise_exception=False)

        return True

    def action_review_signature(self):
        self.ensure_one()
        if self.approval_state != 'to_review':
             raise UserError(_("This order is not waiting for review."))
        # Auto-sign if employee has signature
        employee = self.env.user.employee_id
        if not employee:
             raise UserError(_("Current user is not linked to an Employee record."))
             
        if not employee.signature_image:
             raise UserError(_("You have not uploaded a signature in your Employee profile.\nPlease go to Employees app > select your profile > upload signature."))
             
        company = self.company_id
        
        # Determine Approver
        limit = company.po_approver_limit
        amount = self.amount_total
        next_approver = company.po_approver_id
        
        if amount > limit and company.po_approver_above_limit_id:
             next_approver = company.po_approver_above_limit_id

        if not next_approver:
             raise UserError(_("No approver configured. Please set up the Purchase Order Approver in Settings."))
             
        # Update PO
        self.write({
            'reviewed_signature': employee.signature_image,
            'reviewed_date': fields.Datetime.now(),
            'approval_state': 'to_approve',
            'reviewer_id': self.env.user.id,
            'approver_id': next_approver.id
        })
        
        # Complete Review Activity
        activity_domain = [('res_id', '=', self.id), ('res_model', '=', 'purchase.order'), ('user_id', '=', self.env.user.id)]
        self.env['mail.activity'].search(activity_domain).action_feedback()
        
        # Schedule Approve Activity & Send Email
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=next_approver.id,
            summary='Please Approve Purchase Order',
            note=f'Purchase Order {self.name} needs your approval.'
        )
        
        # Generate Token if not exists
        if not self.approval_token:
            self._generate_approval_token()

        # Send Email
        template_id = self.env.ref('buz_po_portal.email_template_purchase_approval_request')
        if template_id:
            template_id.send_mail(self.id, force_send=True)
            
        # Trigger LINE Notification
        self.action_send_line_approval_request(raise_exception=False)
        
        return True

    def action_approve_signature(self):
        self.ensure_one()
        if self.approval_state != 'to_approve':
             raise UserError(_("This order is not waiting for approval."))
        
        # Auto-sign if employee has signature
        employee = self.env.user.employee_id
        if not employee:
             raise UserError(_("Current user is not linked to an Employee record."))
             
        if not employee.signature_image:
             raise UserError(_("You have not uploaded a signature in your Employee profile.\nPlease go to Employees app > select your profile > upload signature."))
             
        # Update PO
        self.write({
            'approval_signature': employee.signature_image,
            'approval_date': fields.Datetime.now(),
            'approval_state': 'approved',
            'approver_id': self.env.user.id
        })
        
        # Complete Approve Activity
        activity_domain = [('res_id', '=', self.id), ('res_model', '=', 'purchase.order'), ('user_id', '=', self.env.user.id)]
        self.env['mail.activity'].search(activity_domain).action_feedback()
        
        # Confirm Order
        self.button_confirm()
        
        return True

    def action_reset_approval_draft(self):
        self.write({
            'approval_state': 'draft',
            'approval_signature': False,
            'approval_date': False,
            'approval_token': False,
            'approval_token_expired': False,
        })

    @api.depends('order_line.taxes_id')
    def _compute_has_vat(self):
        for order in self:
            order.has_vat = any(
                line.taxes_id.filtered(lambda tax: tax.amount > 0.0 and 'vat' in (tax.tax_group_id.name or '').lower())
                for line in order.order_line
            )

    def action_send_line_approval_request(self, raise_exception=True):
        """
        Override to send LINE approval request only to managers and use PO specific link.
        """
        self.ensure_one()

        # Prevent duplicate sends within short timeframe (e.g. 60 seconds)
        if self.line_notification_sent and self.line_notification_datetime:
            diff = fields.Datetime.now() - self.line_notification_datetime
            if diff.total_seconds() < 60:
                 _logger.info("LINE Notification: Skipping duplicate request for PO %s (sent %s seconds ago)", self.name, diff.total_seconds())
                 return False
        
        # 1. Skip if in review stage (only waiting for approval needs LINE)
        if self.approval_state == 'to_review':
            _logger.info("LINE Notification: Skipping notification for review stage on PO %s", self.name)
            return False
            
        if self.approval_state != 'to_approve':
            if raise_exception:
                raise UserError(_("PO must be in 'Waiting for Approval' state to send LINE notification."))
            return False

        # 2. Get approver (Manager)
        approver = self.approver_id
        if not approver:
            if raise_exception:
                raise UserError(_("Please assign an Approver (Manager) before sending LINE notification."))
            return False

        # 3. Validation LINE ID
        if not approver.line_user_id or not approver.line_user_id.strip():
            msg = _(
                "Approver '%s' does not have LINE User ID configured.\n\n"
                "Please go to:\n"
                "Settings > Users > %s\n"
                "And add LINE User ID in the 'LINE Notification' section."
            ) % (approver.name, approver.name)
            if raise_exception:
                raise UserError(msg)
            return False

        # 4. Generate Approval Token
        # Create approval.token record instead of local token
        doc_name = self.name or f"PO/{self.id}"
        token_record = self.env['approval.token'].generate_token(
            res_model='purchase.order',
            res_id=self.id,
            approver_id=approver.id,
            res_name=doc_name,
            line_user_id=approver.line_user_id,
        )
        
        # Update local fields for backward compatibility (optional but good for view)
        self.write({
            'approval_token': token_record.token,
            'approval_token_created': fields.Datetime.now(),
            'approval_token_expired': False,
            'approval_token_id': token_record.id,
        })

        # Construct URL using the new token (landing page for LINE browser detection)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        db_name = self.env.cr.dbname
        portal_url = f"{base_url}/l/purchase/approve/{token_record.token}?db={db_name}"

        
        # 5. Build Messages
        text_message = self._get_line_approval_message(portal_url)
        flex_contents = self._build_po_flex_message(portal_url)
        
        # 6. Send Messages
        line_service = self.env['line.api.service']
        try:
            # Try to send Flex message (rich UI) as primary notification
            try:
                alt_text = f"PO {self.name} รอการอนุมัติ ({self.amount_total:,.2f} {self.currency_id.name if self.currency_id else 'THB'})"
                line_service.send_flex_message(approver.line_user_id, alt_text, flex_contents)
            except Exception as flex_error:
                _logger.warning(f"Failed to send Flex message, fallback to text: {str(flex_error)}")
                # Send text message fallback
                line_service.send_push_message(approver.line_user_id, text_message)
            
            # Update status
            self.write({
                'line_notification_sent': True,
                'line_notification_datetime': fields.Datetime.now(),
            })
            
            # Log Success
            if hasattr(self, 'message_post'):
                self.message_post(
                    body=_("LINE approval request sent to %s") % approver.name,
                    message_type='notification',
                )
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Success"),
                    'message': _("LINE approval request sent to %s") % approver.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            msg = _("Failed to send LINE message: %s") % str(e)
            _logger.error(msg)
            if hasattr(self, 'message_post'):
                self.message_post(body=f"⚠️ {msg}")
            if raise_exception:
                raise UserError(msg)
            return False

    def send_line_approval_notification_by_token(self, token_record):
        """
        Resend approval notification for specific token.
        Called from approval.token button.
        """
        self.ensure_one()
        
        # 1. Validation
        if self.approval_state != 'to_approve':
            raise UserError(_("PO must be in 'Waiting for Approval' state to resend notification."))

        approver = token_record.approver_id
        if not approver.line_user_id:
             raise UserError(_("Approver '%s' does not have LINE User ID.") % approver.name)

        # 2. Construct URL
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        db_name = self.env.cr.dbname
        portal_url = f"{base_url}/l/purchase/approve/{token_record.token}?db={db_name}"
        
        # 3. Build Messages
        text_message = self._get_line_approval_message(portal_url)
        flex_contents = self._build_po_flex_message(portal_url)
        
        # 4. Send Messages
        line_service = self.env['line.api.service']
        try:
            # Try to send Flex message
            try:
                alt_text = f"PO {self.name} รอการอนุมัติ ({self.amount_total:,.2f} {self.currency_id.name if self.currency_id else 'THB'})"
                line_service.send_flex_message(approver.line_user_id, alt_text, flex_contents)
            except Exception as flex_error:
                _logger.warning(f"Failed to send Flex message, fallback to text: {str(flex_error)}")
                line_service.send_push_message(approver.line_user_id, text_message)
            
            # Update status (optional, update timestamp only)
            self.write({
                'line_notification_sent': True,
                'line_notification_datetime': fields.Datetime.now(),
            })
            
            # Log Success
            if hasattr(self, 'message_post'):
                self.message_post(
                    body=_("LINE approval request resent to %s") % approver.name,
                    message_type='notification',
                )
                
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Success"),
                    'message': _("LINE approval request resent to %s") % approver.name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            msg = _("Failed to send LINE message: %s") % str(e)
            raise UserError(msg)

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['purchase.order'].browse(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'purchase.order',
            'docs': docs,
        }
    
    @api.depends('amount_total')
    def _compute_amount_total_text_th(self):
        for rec in self:
            if rec.currency_id and rec.amount_total is not None:
               rec.amount_total_text_th = rec._baht_text_th(rec.amount_total)
            else:
                rec.amount_total_text_th = "-"                 

    def _baht_text_th(self, amount):
        t1 = ["ศูนย์", "หนึ่ง", "สอง", "สาม", "สี่", "ห้า", "หก", "เจ็ด", "แปด", "เก้า"]
        t2 = ["", "สิบ", "ร้อย", "พัน", "หมื่น", "แสน", "ล้าน"]

        def num2thai(number):
            number = int(number)
            if number == 0:
                return t1[0]

            result = ""
            digits = list(str(number))
            length = len(digits)

            for i in range(length):
                n = int(digits[i])
                pos = length - i - 1

                if n == 0:
                    continue

                # ตำแหน่งหลักสิบ
                if pos == 1:
                    if n == 1:
                        result += t2[1]
                    elif n == 2:
                        result += "ยี่" + t2[1]
                    else:
                        result += t1[n] + t2[1]
                # ตำแหน่งหลักหน่วย
                elif pos == 0:
                    result += t1[n]
                # ตำแหน่งอื่น ๆ
                else:
                    result += t1[n] + t2[pos]

            return result

        amount = round(amount, 2)
        baht = int(amount)
        satang = int(round((amount - baht) * 100))

        result = num2thai(baht) + "บาท"
        if satang > 0:
            result += num2thai(satang) + "สตางค์"
        else:
            result += "ถ้วน"
        return result

    def _compute_department_name(self):
        for rec in self:
            rec.department_name = rec.department_id.name if rec.department_id else '-'

    def button_confirm(self):
        for order in self:
            if order.approval_state != 'approved':
                raise UserError(_("You cannot confirm the Purchase Order until it is approved by the manager."))
        return super(PurchaseOrder, self).button_confirm()

    def name_get(self):
        result = []
        for rec in self:
            name = rec.description or "รายการ"
        result.append((rec.id, name))
        return result

    # LINE Approval Mixin Methods
    def _get_line_approval_approver(self):
        """Return the approver user for LINE notification."""
        self.ensure_one()
        # Select approver based on current approval state
        if self.approval_state == 'to_review':
            # Need reviewer's approval
            approver = self.reviewer_id
            if not approver:
                raise UserError(_("Please assign a Reviewer before sending LINE notification."))
            if not approver.line_user_id or not approver.line_user_id.strip():
                raise UserError(_(
                    "Reviewer '%s' does not have LINE User ID configured.\n\n"
                    "Please go to:\n"
                    "Settings > Users > %s\n"
                    "And add LINE User ID in the 'LINE Notification' section."
                ) % (approver.name, approver.name))
            return approver
        elif self.approval_state == 'to_approve':
            # Need manager's approval
            approver = self.approver_id
            if not approver:
                raise UserError(_("Please assign an Approver (Manager) before sending LINE notification."))
            if not approver.line_user_id or not approver.line_user_id.strip():
                raise UserError(_(
                    "Approver '%s' does not have LINE User ID configured.\n\n"
                    "Please go to:\n"
                    "Settings > Users > %s\n"
                    "And add LINE User ID in the 'LINE Notification' section."
                ) % (approver.name, approver.name))
            return approver
        else:
            raise UserError(_("PO must be in 'Waiting for Review' or 'Waiting for Approval' state to send LINE notification."))

    def _get_line_approval_document_name(self):
        """Get the document reference/name for the LINE message."""
        self.ensure_one()
        return self.name or f"PO/{self.id}"

    def _get_line_approval_amount(self):
        """Get the amount to display in LINE message."""
        self.ensure_one()
        if self.amount_total and self.currency_id:
            return f"{self.amount_total:,.2f} {self.currency_id.name}"
        return None

    def _get_line_approval_message(self, portal_url):
        """Build the LINE message content for purchase order approval (Text Fallback)."""
        self.ensure_one()
        
        # Get expiry days from settings
        expiry_days = int(self.env['ir.config_parameter'].sudo().get_param('line_portal_notification.token_expiry_days', 7))
        
        # Format amount
        amount_str = f"{self.amount_total:,.2f}" if self.amount_total else "0.00"
        currency = self.currency_id.name if self.currency_id else "THB"
        
        # Format date
        date_str = self.date_order.strftime('%d/%m/%Y') if self.date_order else "-"
        
        # Build message according to prompt.md specification
        message_lines = [
            "📋 Purchase Order Approval Required",
            "",
            f"PO No: {self.name}",
            f"Vendor: {self.partner_id.name}",
            f"Amount: {amount_str} {currency}",
            f"Date: {date_str}",
            "",
            "👉 กรุณาเปิดลิงก์ด้านล่างเพื่อพิจารณาอนุมัติ",
            portal_url,
            "",
            "⚠️ หากเปิดจาก LINE ให้กด ⋮ → เปิดในเบราว์เซอร์",
            f"⏳ ลิงก์นี้หมดอายุภายใน {expiry_days} วัน",
        ]
        
        return "\n".join(message_lines)

    def _build_po_flex_message(self, portal_url):
        """Build Flex Message for executive-style approval request."""
        self.ensure_one()
        
        # Format amount
        amount_str = f"{self.amount_total:,.2f}" if self.amount_total else "0.00"
        currency = self.currency_id.name if self.currency_id else "THB"
        
        # Format date
        date_str = self.date_order.strftime('%d/%m/%Y') if self.date_order else "-"
        
        # Build Flex Message according to prompt.md specification
        flex_contents = {
            "type": "bubble",
            "size": "mega",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "Purchase Order Approval",
                        "weight": "bold",
                        "size": "lg"
                    },
                    {
                        "type": "separator",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "spacing": "sm",
                        "margin": "md",
                        "contents": [
                            {"type": "text", "text": f"PO No: {self.name}", "size": "sm", "weight": "bold"},
                            {"type": "text", "text": f"Vendor: {self.partner_id.name}", "size": "sm", "wrap": True},
                            {"type": "text", "text": f"Amount: {amount_str} {currency}", "size": "sm", "weight": "bold"},
                            {"type": "text", "text": f"Date: {date_str}", "size": "sm"}
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#06C755",
                        "action": {
                            "type": "uri",
                            "label": "Approve",
                            "uri": f"{portal_url}?action=approve"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "uri",
                            "label": "Reject",
                            "uri": f"{portal_url}?action=reject"
                        }
                    },
                    {
                        "type": "text",
                        "text": "กรุณาเปิดผ่าน Safari / Chrome หากเปิดจาก LINE",
                        "size": "xs",
                        "color": "#999999",
                        "align": "center",
                        "wrap": True
                    }
                ]
            }
        }
        
        return flex_contents

    def action_approve(self):
        """Approve the purchase order (called from portal)."""
        self.ensure_one()
        if self.approval_state == 'to_review':
            # Reviewer approval
            self.write({
                'approval_state': 'to_approve',
                'reviewed_date': fields.Datetime.now(),
            })
            self._invalidate_approval_token('reviewed')
            if hasattr(self, 'message_post'):
                self.message_post(
                    body=_("Purchase Order reviewed and sent for manager approval."),
                    message_type='notification',
                )
        elif self.approval_state == 'to_approve':
            # Manager approval
            self.write({
                'approval_state': 'approved',
                'approval_date': fields.Datetime.now(),
            })
            self._invalidate_approval_token('approved')
            if hasattr(self, 'message_post'):
                self.message_post(
                    body=_("Purchase Order approved by manager."),
                    message_type='notification',
                )
        else:
            raise UserError(_("This purchase order is not in a state that can be approved."))

    def action_reject(self, reject_reason=None):
        """Reject the purchase order (called from portal)."""
        self.ensure_one()
        
        update_vals = {'approval_state': 'rejected'}
        if reject_reason:
            update_vals['reject_reason'] = reject_reason
            
        self.write(update_vals)
        self._invalidate_approval_token('rejected')
        
        if hasattr(self, 'message_post'):
            body = _("Purchase Order rejected via portal.")
            if reject_reason:
                body += f"\n{_('Reason')}: {reject_reason}"
            self.message_post(
                body=body,
                message_type='notification',
            )


class BuzPurchaseOrderLine(models.Model):
    _name = 'buz.purchase.order.line'
    _description = 'Custom Purchase Order Line'

    order_id = fields.Many2one('purchase.order', string='Purchase Order', ondelete='cascade')
    quantity = fields.Float(string='จำนวน')
    unit_id = fields.Many2one('uom.uom', string='หน่วย')
    description = fields.Text(string='ชื่อและรายละเอียดสิ่งที่ต้องการ')
    unit_price = fields.Float(string='ราคาต่อหน่วย')
    remark = fields.Char(string='หมายเหตุ')
    