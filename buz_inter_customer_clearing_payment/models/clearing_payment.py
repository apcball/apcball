# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    clearing_payment_ids = fields.One2many(
        'buz.clearing.link', 'payment_id', 
        string='Clearing Links', readonly=True,
        help='Links to clearing entries created for inter-customer allocation'
    )
    is_clearing_payment = fields.Boolean(
        string='Is Clearing Payment', readonly=True,
        help='Indicates if this payment is part of an inter-customer clearing process'
    )
    clearing_advance_amount = fields.Monetary(
        string='Advance Amount', readonly=True,
        currency_field='currency_id',
        help='Remaining amount after allocation to other customers'
    )

    def action_cancel(self):
        """Override to handle clearing payment cancellation"""
        for payment in self:
            if payment.is_clearing_payment:
                # Check if there are clearing entries to cancel
                clearing_links = payment.clearing_payment_ids.filtered(lambda l: l.clearing_move_id)
                if clearing_links:
                    # Unreconcile all related lines first
                    for link in clearing_links:
                        if link.clearing_move_id.state == 'posted':
                            # Find and unreconcile partial reconciliations
                            partial_reconciles = self.env['account.partial.reconcile'].search([
                                '|', ('debit_move_id', 'in', link.clearing_move_id.line_ids.ids),
                                '|', ('credit_move_id', 'in', link.clearing_move_id.line_ids.ids),
                            ])
                            if partial_reconciles:
                                partial_reconciles.unlink()
                    
                    # Cancel clearing journal entries
                    clearing_moves = clearing_links.mapped('clearing_move_id')
                    clearing_moves.button_cancel()
                    clearing_moves.unlink()
        
        return super(AccountPayment, self).action_cancel()

    def unlink(self):
        """Override to handle clearing payment deletion"""
        for payment in self:
            if payment.is_clearing_payment:
                # First cancel the payment to clean up clearing entries
                if payment.state not in ['draft', 'cancelled']:
                    payment.action_cancel()
        
        return super(AccountPayment, self).unlink()


class AccountMove(models.Model):
    _inherit = 'account.move'

    clearing_payment_ids = fields.One2many(
        'buz.clearing.link', 'invoice_id', 
        string='Clearing Payments', readonly=True,
        help='Links to clearing payments that allocated to this invoice'
    )
    clearing_payment_amount = fields.Monetary(
        string='Clearing Payment Amount', readonly=True,
        currency_field='currency_id',
        compute='_compute_clearing_payment_amount',
        help='Total amount paid through inter-customer clearing'
    )

    @api.depends('clearing_payment_ids.amount')
    def _compute_clearing_payment_amount(self):
        for move in self:
            move.clearing_payment_amount = sum(move.clearing_payment_ids.mapped('amount'))