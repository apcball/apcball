# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import Markup
import uuid
import base64
import io

try:
    import qrcode
except ImportError:
    qrcode = None

class InternalConsumeRequest(models.Model):
    _inherit = 'internal.consume.request'

    state = fields.Selection(selection_add=[
        ('issued', 'Issued'),
        ('rejected', 'Rejected'),
        ('cancel', 'Cancelled')
    ], ondelete={'issued': 'set default', 'rejected': 'set default', 'cancel': 'set default'})

    qr_token = fields.Char(string='Portal Token', readonly=True, copy=False)
    qr_code = fields.Binary(string='QR Code', readonly=True, attachment=True)
    signature = fields.Binary(string='Signature', readonly=True, attachment=True)
    received_date = fields.Datetime(string='Received Date', readonly=True)
    portal_confirmed = fields.Boolean(string='Portal Confirmed', default=False)
    
    issued_by = fields.Many2one('res.users', string='Issued By', readonly=True, copy=False)
    issued_date = fields.Datetime(string='Issued Date', readonly=True, copy=False)
    
    def action_cancel(self):
        for record in self:
            # Attempt to cancel linked pickings if they exist
            if hasattr(record, 'picking_ids') and record.picking_ids:
                record.picking_ids.action_cancel()
            elif hasattr(record, 'picking_id') and record.picking_id:
                record.picking_id.action_cancel()
            record.write({'state': 'cancel'})

    def action_reject(self):
        return self.write({'state': 'rejected'})

    def action_approve(self):
        # Base module action_approve creates picking
        res = super(InternalConsumeRequest, self).action_approve()
        for record in self:
            record._generate_qr_token()
            # record._send_portal_email(reason='approved')
        return res

    def _generate_qr_token(self):
        self.ensure_one()
        if not self.qr_token:
            token = uuid.uuid4().hex
            self.qr_token = token
            
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            portal_url = f"{base_url}/consumable/request/{token}"
            
            if qrcode:
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(portal_url)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                self.qr_code = base64.b64encode(buffer.getvalue())
            
            # Post message with link
            link_btn = Markup(f"""
                <div style="margin-top: 10px;">
                    <a href="{portal_url}" target="_blank" 
                       style="background-color: #875A7B; color: #FFFFFF; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold;">
                       <i class="fa fa-external-link"></i> View Portal Request
                    </a>
                </div>
            """)
            self.message_post(body=Markup(_("QR Code generated for portal access.<br/>%s")) % link_btn)

    def _send_portal_email(self, reason='approved'):
        self.ensure_one()
        if not self.qr_token:
            return

        recipient = self.employee_id.work_email or (self.employee_id.user_id and self.employee_id.user_id.email)
        if not recipient:
            return
            
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        portal_url = f"{base_url}/consumable/request/{self.qr_token}"
        
        if reason == 'approved':
            subject = _('Approval Required: %s') % self.name
            action_text = _('Your request has been approved.')
            button_text = _('View Request')
        elif reason == 'issued':
            subject = _('Ready to Pickup: %s') % self.name
            action_text = _('Your items have been issued by the warehouse. Please proceed to pick up and sign.')
            button_text = _('Receive & Sign Items')
        else:
            subject = _('Notification: %s') % self.name
            action_text = _('There is an update on your request.')
            button_text = _('View Request')

        body_html = f"""
            <div style="background-color: #EAF0F6; padding: 20px; font-family: sans-serif; border-radius: 5px;">
                <div style="margin-bottom: 20px;">
                    <strong style="font-size: 16px; color: #333;">Subject: {subject}</strong>
                </div>
                
                <p style="color: #555;">Dear {self.employee_id.name},</p>
                
                <p style="color: #555;">{action_text}</p>
                
                <ul style="color: #555; list-style-type: disc; padding-left: 20px;">
                    <li><strong>Document:</strong> {self.name}</li>
                    <li><strong>Requester:</strong> {self.employee_id.name}</li>
                    <li><strong>Department:</strong> {self.department_id.name or '-'}</li>
                </ul>

                <div style="margin: 30px 0px; text-align: left;">
                    <a href="{portal_url}"
                        style="background-color: #875A7B; 
                               color: #FFFFFF; 
                               padding: 12px 25px; 
                               text-decoration: none; 
                               border-radius: 5px; 
                               font-weight: bold; 
                               font-size: 14px;
                               display: inline-block;">
                        {button_text}
                    </a>
                </div>
                
                <p style="color: #555; margin-top: 20px;">Thank you.</p>
                <p style="font-size: 11px; color: #888; margin-top: 30px;">
                    Link: <a href="{portal_url}" style="color: #875A7B;">{portal_url}</a>
                </p>
            </div>
        """
        
        mail_values = {
            'subject': subject,
            'body_html': body_html,
            'email_to': recipient,
            'email_from': self.env.user.email_formatted or self.env.company.email,
        }
        self.env['mail.mail'].create(mail_values).send()

    def action_issue_goods(self):
        """Issuer confirms goods are ready/issued"""
        self.ensure_one()
        if self.state != 'approved':
             raise UserError(_("Request must be in Approved state to issue goods."))
        
        self.write({
            'state': 'issued',
            'issued_by': self.env.user.id,
            'issued_date': fields.Datetime.now()
        })
        
        # Post message with link
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        portal_url = f"{base_url}/consumable/request/{self.qr_token}"
        
        link_btn = Markup(f"""
            <div style="margin-top: 10px;">
                <a href="{portal_url}" target="_blank" 
                   style="background-color: #875A7B; color: #FFFFFF; padding: 8px 16px; text-decoration: none; border-radius: 4px; font-weight: bold;">
                   <i class="fa fa-external-link"></i> Open Receiver Portal
                </a>
            </div>
        """)
        
        self.message_post(body=Markup(_("Goods Issued by %s. Ready for receiver confirmation.<br/>%s")) % (self.env.user.name, link_btn))
        
        # self._send_portal_email(reason='issued')

    def action_portal_receive(self, signature_data):
        self.ensure_one()
        
        # New Rule: Must be Issued before receiving
        if self.state != 'issued':
            raise UserError(_("Items must be marked as Issued by warehouse before receiving. Current state: %s") % self.state)

        if self.portal_confirmed:
            raise UserError(_("Request is already confirmed."))

        # Update signature and date
        self.write({
            'signature': signature_data,
            'received_date': fields.Datetime.now(),
            'portal_confirmed': True,
        })

        # Process Picking
        picking = self.picking_id
        if not picking:
            # Create if not exists (fallback, though base module creates it)
            self.action_create_picking()
            picking = self.picking_id
        
        if picking.state == 'cancel':
             raise UserError(_("Associated picking is cancelled."))
             
        if picking.state not in ('done', 'cancel'):
             if picking.state == 'draft':
                 picking.action_confirm()
                 
             # picking.action_assign() # Optional: Check availability automatically
             
             # User requested NOT to validate automatically.
             # Warehouse staff will validate the picking manually later.
             # for move in picking.move_ids:
             #    move.quantity = move.product_uom_qty 
             # picking.button_validate()
        
        # Request state remains 'issued' until Picking is validated (handled by stock.picking inherit)
        # if self.state != 'done':
        #    self.write({'state': 'done'})
            
        self.message_post(
            body=_("Items received via Portal. Waiting for Warehouse Validation."),
            attachments=[('Signature.png', base64.b64decode(signature_data) if signature_data else b'')]
        )
        return True
