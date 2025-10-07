from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AccountPaymentRegisterWizard(models.TransientModel):
    _name = 'account.payment.register.wizard'
    _description = 'Account Payment Register Wizard for Payment Voucher'

    # Fields to display bill information
    voucher_line_id = fields.Many2one('account.payment.voucher.line', string='Voucher Line', readonly=True, ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    move_id = fields.Many2one('account.move', string='Bill/Refund', readonly=True)
    move_name = fields.Char(related='move_id.name', string='Bill Number', readonly=True)
    move_date = fields.Date(related='move_id.date', string='Bill Date', readonly=True)
    move_amount_total = fields.Monetary(related='move_id.amount_total', string='Bill Total', readonly=True)
    move_amount_residual = fields.Monetary(related='move_id.amount_residual', string='Residual Amount', readonly=True)
    currency_id = fields.Many2one(related='move_id.currency_id', readonly=True)
    
    # Fields to specify payment details
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Payment Method', 
                                 default=lambda self: self._default_journal())

    def _default_journal(self):
        # Get the company from the context or from the voucher line
        company_id = self.env.context.get('default_company_id') or self.env.company.id
        return self.env['account.journal'].search([
            ('type', 'in', ('bank', 'cash')),
            ('company_id', '=', company_id)
        ], limit=1)
    company_id = fields.Many2one('res.company', string='Company', 
                                 default=lambda self: self.env.company, required=True)
    communication = fields.Char(string='Memo', help="Payment reference")
    
    # Amount fields
    amount_to_pay_gross = fields.Monetary(string='Amount to Pay (Gross)', readonly=True)
    wht_amount = fields.Monetary(string='WHT Amount', readonly=True)
    amount_to_pay_net = fields.Monetary(string='Amount to Pay (Net)', readonly=True)
    
    def action_register_payment(self):
        """Register the payment for the selected bill based on voucher line information"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_("No bill/refund found for this line."))
            
        # Validate the bill
        if self.move_id.state != 'posted':
            raise UserError(_("Bill %s is not in 'Posted' state. Only posted bills can be used for payment registration.") % self.move_id.name)
            
        if self.move_id.move_type not in ['in_invoice', 'in_refund']:
            raise UserError(_("Bill %s is not a vendor bill or refund. Only vendor bills and refunds can be used for payment registration.") % self.move_id.name)
            
        if self.move_id.payment_state == 'paid':
            raise UserError(_("Bill %s is already fully paid. Cannot register payment for fully paid bills.") % self.move_id.name)
            
        # Prepare payment values
        payment_values = {
            'partner_id': self.partner_id.id,
            'amount': self.amount_to_pay_net,  # Use net amount after WHT
            'payment_date': self.payment_date,
            'communication': self.communication or f'Payment Voucher {self.voucher_line_id.voucher_id.name}',
            'journal_id': self.journal_id.id,
            'partner_type': 'supplier',
            'payment_type': 'outbound',
            'ref': f'PV {self.voucher_line_id.voucher_id.name}',
            'move_id': False,  # Will be set when creating the payment
        }
        
        # Create the payment
        payment = self.env['account.payment'].create(payment_values)
        payment.action_post()  # Confirm and post the payment
        
        # Link the payment to the voucher line
        self.voucher_line_id.payment_ids = [(4, payment.id)]
        
        # Reconcile the payment with the bill
        self.voucher_line_id.voucher_id._reconcile_payment_with_bills(payment, self.move_id)
        
        # Process WHT if applicable
        if self.wht_amount > 0:
            # Create WHT entries
            self.voucher_line_id.voucher_id._create_wht_entries(self.voucher_line_id, payment, self.partner_id)
            # Create WHT certificates if module is installed
            self.voucher_line_id.voucher_id._create_wht_certificates(self.voucher_line_id, payment, self.partner_id)
        
        # Return action to show the created payment
        return {
            'name': _('Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'form',
            'res_id': payment.id,
            'target': 'current',
        }