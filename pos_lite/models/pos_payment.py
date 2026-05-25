from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class PosLitePayment(models.Model):
    _name = 'pos.lite.payment'
    _description = 'POS Lite Payment'
    _order = 'id desc'

    order_id = fields.Many2one(
        'pos.lite.order',
        required=True,
        ondelete='cascade',
        check_company=True,
    )
    state = fields.Selection(related='order_id.state', store=False, readonly=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, readonly=True)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('transfer', 'Transfer'),
        ('card', 'Card'),
        ('promptpay', 'PromptPay'),
        ('other', 'Other'),
    ], default='cash', required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)
    journal_id = fields.Many2one(
        'account.journal',
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
    )
    reference = fields.Char(string='Reference', help='Payment reference, slip number, or transaction ID')
    payment_date = fields.Date(default=fields.Date.context_today, string='Payment Date')
    note = fields.Char()
    account_payment_id = fields.Many2one(
        'account.payment', readonly=True, copy=False,
        string='Journal Entry',
        help='The account.payment created when the order is processed.',
    )

    @api.onchange('payment_method')
    def _onchange_payment_method(self):
        if self.payment_method and not self.journal_id and self.order_id:
            self.journal_id = self.order_id._get_default_payment_journal()

    @api.constrains('amount')
    def _check_amount(self):
        for payment in self:
            if payment.order_id and payment.order_id.is_return:
                if payment.amount > 0:
                    raise ValidationError(_('Refund payment amount must be less than or equal to zero.'))
            elif payment.amount < 0:
                raise ValidationError(_('Payment amount must not be negative.'))

    def _prepare_account_payment_vals(self):
        """Return dict to create account.payment from this pos.lite.payment."""
        self.ensure_one()
        order = self.order_id
        partner = order.partner_id or order._get_or_create_customer_partner()
        payment_type = 'outbound' if order.is_return else 'inbound'
        partner_type = 'customer'
        journal = self.journal_id or order._get_default_payment_journal()
        if not journal:
            raise ValidationError(_('No payment journal found for order %s.') % order.name)
        return {
            'payment_type': payment_type,
            'partner_type': partner_type,
            'partner_id': partner.id,
            'amount': abs(self.amount),
            'currency_id': order.currency_id.id,
            'journal_id': journal.id,
            'ref': '%s - %s' % (order.name, self.payment_method),
            'date': self.payment_date or fields.Date.context_today(self),
        }
