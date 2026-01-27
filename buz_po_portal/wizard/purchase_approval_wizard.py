from odoo import api, fields, models, _
from odoo.exceptions import UserError

class PurchaseOrderApprovalWizard(models.TransientModel):
    _name = 'purchase.order.approval.wizard'
    _description = 'Purchase Order Approval Wizard'

    order_id = fields.Many2one('purchase.order', string="Purchase Order", required=True)
    signature_type = fields.Selection([('draw', 'Draw Signature'), ('upload', 'Upload File')], string="Signature Type", default='draw')
    approval_stage = fields.Selection([
        ('prepare', 'Prepare'),
        ('review', 'Review'),
        ('approve', 'Approve')
    ], string="Approval Stage", default='approve')
    draw_signature = fields.Binary(string='Draw Signature')
    upload_signature = fields.Binary(string='Upload Signalue')

    def action_approve(self):
        self.ensure_one()
        signature = self.draw_signature if self.signature_type == 'draw' else self.upload_signature
        
        if not signature:
            raise UserError(_("Please provide a signature."))

        vals = {}
        company = self.order_id.company_id
        
        if self.approval_stage == 'prepare':
            if not company.po_reviewer_id:
                raise UserError(_("No default reviewer configured. Please set up the Purchase Order Reviewer in Settings."))

            vals = {
                'prepared_signature': signature,
                'prepared_date': fields.Datetime.now(),
                'approval_state': 'to_review',
                'reviewer_id': company.po_reviewer_id.id if company.po_reviewer_id else False
            }
            # Schedule Review Activity
            if company.po_reviewer_id:
                self.order_id.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=company.po_reviewer_id.id,
                    summary='Please Review Purchase Order',
                    note=f'Purchase Order {self.order_id.name} needs your review.'
                )

        elif self.approval_stage == 'review':
            
            # Determine Approver based on Limit
            limit = company.po_approver_limit
            amount = self.order_id.amount_total
            next_approver = company.po_approver_id
            
            if amount > limit and company.po_approver_above_limit_id:
                next_approver = company.po_approver_above_limit_id

            if not next_approver:
                raise UserError(_("No approver configured. Please set up the Purchase Order Approver in Settings."))

            vals = {
                'reviewed_signature': signature,
                'reviewed_date': fields.Datetime.now(),
                'approval_state': 'to_approve',
                 # Record the actual reviewer
                'reviewer_id': self.env.user.id,
                'approver_id': next_approver.id if next_approver else False
            }
            
            # Complete Review Activity
            activity_domain = [('res_id', '=', self.order_id.id), ('res_model', '=', 'purchase.order'), ('user_id', '=', self.env.user.id)]
            self.env['mail.activity'].search(activity_domain).action_feedback()

            # Write vals now to update approver_id before sending email
            self.order_id.write(vals)
            vals = {} # Clear vals so we don't write again at the end (or we can just be careful)

            # Schedule Approve Activity & Send Email
            if next_approver:
                self.order_id.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=next_approver.id,
                    summary='Please Approve Purchase Order',
                    note=f'Purchase Order {self.order_id.name} needs your approval.'
                )
                
                # Generate Token if not exists
                if not self.order_id.approval_token:
                    self.order_id._generate_approval_token()

                # Send Email
                template_id = self.env.ref('buz_po_portal.email_template_purchase_approval_request')
                if template_id:
                    template_id.send_mail(self.order_id.id, force_send=True)

        elif self.approval_stage == 'approve':
            vals = {
                'approval_signature': signature,
                'approval_date': fields.Datetime.now(),
                'approval_state': 'approved',
                'approver_id': self.env.user.id
            }

            # Complete Approve Activity
            activity_domain = [('res_id', '=', self.order_id.id), ('res_model', '=', 'purchase.order'), ('user_id', '=', self.env.user.id)]
            self.env['mail.activity'].search(activity_domain).action_feedback()

        self.order_id.write(vals)
        
        # Trigger LINE Notification for Prepare and Review stages
        if self.approval_stage in ['prepare', 'review']:
                 # Check if we are in a valid state to send (Double check, though write(vals) should have set it)
                 if self.order_id.approval_state in ['to_review', 'to_approve']:
                     self.order_id.action_send_line_approval_request(raise_exception=False)

        if self.approval_stage == 'approve':
             self.order_id.button_confirm()
             
        return {'type': 'ir.actions.act_window_close'}
