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


class BuzClearingLink(models.Model):
    _name = 'buz.clearing.link'
    _description = 'Link between payment, clearing entry, and invoice'
    _order = 'date desc, id desc'

    payment_id = fields.Many2one(
        'account.payment', string='Payment', required=True, ondelete='cascade',
        help='Payment that received the funds')
    clearing_move_id = fields.Many2one(
        'account.move', string='Clearing Entry', ondelete='set null',
        help='Clearing journal entry created for inter-customer allocation')
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', required=True, ondelete='cascade',
        domain=[('move_type', '=', 'out_invoice')],
        help='Invoice that was paid through clearing')
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id',
        help='Amount allocated from payment to invoice')
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id)
    date = fields.Date(
        string='Date', required=True, default=fields.Date.today,
        help='Date of the clearing allocation')
    paying_partner_id = fields.Many2one(
        'res.partner', string='Paying Customer',
        related='payment_id.partner_id', readonly=True, store=True)
    invoice_partner_id = fields.Many2one(
        'res.partner', string='Invoice Customer',
        related='invoice_id.partner_id', readonly=True, store=True)

    # Extended fields for batch settlement traceability
    trade_channel = fields.Selection(
        selection=TRADE_CHANNEL_SELECTION,
        string='Trade Channel', readonly=True,
        help='Trade channel of the allocated invoice')
    invoice_date = fields.Date(
        string='Invoice Date', readonly=True,
        help='Date of the allocated invoice')
    settlement_batch = fields.Char(
        string='Settlement Batch Reference', readonly=True,
        help='Reference to the batch settlement that created this link')

    @api.model
    def create(self, vals):
        # Inherit currency from invoice if not supplied
        if not vals.get('currency_id') and vals.get('invoice_id'):
            invoice = self.env['account.move'].browse(vals['invoice_id'])
            vals['currency_id'] = invoice.currency_id.id
        return super().create(vals)