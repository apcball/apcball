from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PosLitePaymentWizard(models.TransientModel):
    _name = 'pos.lite.payment.wizard'
    _description = 'POS Lite Payment Wizard'

    order_id = fields.Many2one('pos.lite.order', required=True, check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id', readonly=True)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('transfer', 'Transfer'),
        ('card', 'Card'),
        ('promptpay', 'PromptPay'),
        ('other', 'Other'),
    ], default='cash', required=True)
    amount = fields.Monetary(required=True)
    journal_id = fields.Many2one(
        'account.journal',
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    reference = fields.Char(string='Reference')
    note = fields.Char()
    auto_process = fields.Boolean(
        string='Process after payment', default=True,
        help='Automatically process the order after this payment is registered.',
    )

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.order_id and not self.journal_id:
            self.journal_id = self.order_id._get_default_payment_journal()

    @api.constrains('amount')
    def _check_amount(self):
        for wizard in self:
            if wizard.amount <= 0:
                raise ValidationError(_('Payment amount must be greater than zero.'))

    def action_confirm(self):
        self.ensure_one()
        order = self.order_id
        if order.state not in ('draft', 'held'):
            raise UserError(_('Only draft or held orders can be paid.'))
        if order.state == 'held':
            order.write({'state': 'draft'})
        default_journal = order._get_default_payment_journal()
        payment_amount = -abs(self.amount) if order.is_return else self.amount
        self.env['pos.lite.payment'].create({
            'order_id': order.id,
            'payment_method': self.payment_method,
            'amount': payment_amount,
            'journal_id': self.journal_id.id or (default_journal.id if default_journal else False),
            'reference': self.reference,
            'note': self.note,
        })
        if self.auto_process:
            order.action_process_order()
        return {'type': 'ir.actions.act_window_close'}
