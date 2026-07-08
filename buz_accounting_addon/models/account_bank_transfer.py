from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountBankTransfer(models.Model):
    _name = 'account.bank.transfer'
    _description = 'Bank Transfer'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='/', index=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Confirmed'),
        ('cancel', 'Cancelled')
    ], string='Status', required=True, readonly=True, copy=False, tracking=True, default='draft')

    journal_id = fields.Many2one('account.journal', string='Source Journal', required=True, domain=[('type', 'in', ('bank', 'cash'))], tracking=True)
    destination_journal_id = fields.Many2one('account.journal', string='Destination Journal', required=True, domain=[('type', 'in', ('bank', 'cash'))], tracking=True)
    
    amount = fields.Monetary(string='Amount', required=True, tracking=True)
    currency_id = fields.Many2one('res.currency', related='journal_id.currency_id', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)

    payment_id = fields.Many2one('account.payment', string='Payment', readonly=True, copy=False)
    buz_payment_voucher_id = fields.Many2one('account.payment.voucher', string='Payment Voucher', readonly=True, copy=False)
    move_id = fields.Many2one('account.move', string='Journal Entry', related='payment_id.move_id', readonly=True, store=True)
    
    # For report compatibility
    partner_bank_id = fields.Many2one('res.partner.bank', string='Recipient Bank Account', related='destination_journal_id.bank_account_id', readonly=True)
    paired_internal_transfer_payment_id = fields.Many2one('account.payment', related='payment_id.paired_internal_transfer_payment_id', readonly=True)
    ref = fields.Char(string='Memo')

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        if not vals.get('amount'):
            voucher_id = self._context.get('default_buz_payment_voucher_id') or self._context.get('buz_payment_voucher_id')
            if voucher_id:
                voucher = self.env['account.payment.voucher'].browse(voucher_id)
                if voucher.exists():
                    vals['amount'] = voucher.amount_total_net
        return vals

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            vals['name'] = self.env['ir.sequence'].next_by_code('account.bank.transfer') or '/'
        return super(AccountBankTransfer, self).create(vals)
    
    def action_confirm(self):
        self.ensure_one()
        if self.amount <= 0:
             raise UserError(_("Amount must be strictly positive."))
        if self.journal_id == self.destination_journal_id:
             raise UserError(_("Source and Destination journals must be different."))
             
        # Create Internal Transfer
        payment_vals = {
            'payment_type': 'outbound',
            'is_internal_transfer': True,
            'journal_id': self.journal_id.id,
            'destination_journal_id': self.destination_journal_id.id,
            'amount': self.amount,
            'date': self.date,
            'ref': self.name + (f" - {self.ref}" if self.ref else ""),
            'currency_id': self.currency_id.id or self.company_id.currency_id.id,
        }
        
        if self.buz_payment_voucher_id:
            payment_vals['buz_payment_voucher_id'] = self.buz_payment_voucher_id.id

        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        
        self.write({
            'state': 'posted',
            'payment_id': payment.id,
        })
        return True

    def action_draft(self):
        for rec in self:
            if rec.payment_id:
                if rec.payment_id.state == 'posted':
                    rec.payment_id.action_draft()
                rec.payment_id.action_cancel()
            rec.write({'state': 'draft'})

    def action_view_payment(self):
        self.ensure_one()
        return {
            'name': _('Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'res_id': self.payment_id.id,
            'view_mode': 'form',
        }
