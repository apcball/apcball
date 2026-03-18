# -*- coding: utf-8 -*-

from odoo import models, fields, api, _

# Same list as marketplace_settlement — hardcoded to avoid fragile
# dynamic field lookups that can fail if the dependency isn't loaded yet.
TRADE_CHANNEL_SELECTION = [
    ('shopee', 'Shopee'),
    ('lazada', 'Lazada'),
    ('nocnoc', 'Noc Noc'),
    ('tiktok', 'Tiktok'),
    ('spx', 'SPX'),
    ('online_line_fb', 'ONLINE/Line + Facebook'),
    ('offline_mogen_outlet', 'OFFLINE/Mogen Outlet'),
    ('after_sale_service', 'After sale service'),
    ('installation_service', 'Installation service'),
    ('own_channel_cdc', 'Own channel ( CDC )'),
    ('other', 'Other'),
]


class BuzBatchPaymentLine(models.TransientModel):
    _name = 'buz.batch.payment.line'
    _description = 'Batch Payment Allocation Line'

    wizard_id = fields.Many2one(
        'buz.batch.payment.wizard', string='Wizard',
        required=True, ondelete='cascade')
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', required=True)

    # NOTE: transient models must NOT use store=True on related fields —
    # it causes RecursionError in Odoo's field setup chain.
    partner_id = fields.Many2one(
        'res.partner', string='Customer',
        related='invoice_id.partner_id')
    invoice_date = fields.Date(
        string='Invoice Date', related='invoice_id.invoice_date')
    residual = fields.Monetary(
        string='Residual Amount',
        related='invoice_id.amount_residual',
        currency_field='currency_id')
    allocate_amount = fields.Monetary(
        string='Allocate Amount', currency_field='currency_id')
    selected = fields.Boolean(string='Selected', default=False)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        related='invoice_id.currency_id')
    trade_channel = fields.Selection(
        selection=TRADE_CHANNEL_SELECTION,
        string='Trade Channel',
        related='invoice_id.trade_channel')
    partner_tax_id = fields.Char(
        string='VAT', related='partner_id.vat')

    @api.onchange('allocate_amount')
    def _onchange_allocate_amount(self):
        """Auto-select/deselect when allocation amount changes."""
        if self.allocate_amount and self.allocate_amount > 0:
            self.selected = True
            if self.allocate_amount > self.residual:
                self.allocate_amount = self.residual
        else:
            self.selected = False
