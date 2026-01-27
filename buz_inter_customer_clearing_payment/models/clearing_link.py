# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class BuzClearingLink(models.Model):
    _name = 'buz.clearing.link'
    _description = 'Link between payment, clearing entry, and invoice'
    
    payment_id = fields.Many2one(
        'account.payment', string='Payment', required=True, ondelete='cascade',
        help='Payment that received the funds'
    )
    clearing_move_id = fields.Many2one(
        'account.move', string='Clearing Entry', ondelete='cascade',
        help='Clearing journal entry created for inter-customer allocation'
    )
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', required=True, ondelete='cascade',
        domain=[('move_type', '=', 'out_invoice')],
        help='Invoice that was paid through clearing'
    )
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id',
        help='Amount allocated from payment to invoice'
    )
    currency_id = fields.Many2one(
        'res.currency', string='Currency', required=True,
        default=lambda self: self.env.company.currency_id
    )
    date = fields.Date(
        string='Date', required=True, default=fields.Date.today,
        help='Date of the clearing allocation'
    )
    paying_partner_id = fields.Many2one(
        'res.partner', string='Paying Customer',
        related='payment_id.partner_id', readonly=True, store=True
    )
    invoice_partner_id = fields.Many2one(
        'res.partner', string='Invoice Customer',
        related='invoice_id.partner_id', readonly=True, store=True
    )
    
    @api.model
    def create(self, vals):
        # Set currency from invoice if not provided
        if not vals.get('currency_id') and vals.get('invoice_id'):
            invoice = self.env['account.move'].browse(vals['invoice_id'])
            vals['currency_id'] = invoice.currency_id.id
        
        return super(BuzClearingLink, self).create(vals)