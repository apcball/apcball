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
        """Override to unreconcile and cancel clearing entries before cancelling payment."""
        for payment in self:
            if payment.is_clearing_payment:
                self._cancel_clearing_entries(payment)
        return super(AccountPayment, self).action_cancel()

    def _cancel_clearing_entries(self, payment):
        """Unreconcile and cancel/delete all clearing journal entries for a payment."""
        clearing_links = payment.clearing_payment_ids.filtered(
            lambda l: l.clearing_move_id and l.clearing_move_id.state == 'posted')

        for link in clearing_links:
            move = link.clearing_move_id
            # Unreconcile all partial reconciliations on this clearing move
            partials = self.env['account.partial.reconcile'].search([
                '|',
                ('debit_move_id', 'in', move.line_ids.ids),
                ('credit_move_id', 'in', move.line_ids.ids),
            ])
            if partials:
                partials.unlink()

            # Try to reset to draft and delete; fall back to reversal for locked periods
            try:
                move.button_draft()
                move.button_cancel()
            except Exception:
                # Period is locked — create a reversal instead
                reversal = self.env['account.move.reversal'].with_context(
                    active_ids=move.ids, active_model='account.move'
                ).create({
                    'refund_method': 'cancel',
                    'reason': _('Clearing entry reversed — payment cancelled'),
                    'journal_id': move.journal_id.id,
                })
                reversal.reverse_moves()

    def action_reverse_clearing_payment(self):
        """Create reversal entries for the payment and all associated clearing moves.

        Used when the accounting period is locked and button_cancel is not possible.
        """
        self.ensure_one()
        if not self.is_clearing_payment:
            raise UserError(_('This action is only available for clearing payments.'))

        clearing_links = self.clearing_payment_ids.filtered(
            lambda l: l.clearing_move_id and l.clearing_move_id.state == 'posted')

        # Reverse each clearing move
        for link in clearing_links:
            move = link.clearing_move_id
            reversal_wizard = self.env['account.move.reversal'].with_context(
                active_ids=move.ids, active_model='account.move',
            ).create({
                'refund_method': 'cancel',
                'reason': _('Clearing entry reversed — batch settlement reversed'),
                'journal_id': move.journal_id.id,
            })
            reversal_wizard.reverse_moves()

        # Reverse the payment itself by resetting and cancelling,
        # or creating a reversal of the underlying move if period is locked
        try:
            self.action_cancel()
        except Exception:
            move = self.move_id
            reversal_wizard = self.env['account.move.reversal'].with_context(
                active_ids=move.ids, active_model='account.move',
            ).create({
                'refund_method': 'cancel',
                'reason': _('Payment reversed — batch settlement reversed'),
                'journal_id': move.journal_id.id,
            })
            reversal_wizard.reverse_moves()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reversed'),
                'message': _('The clearing payment and all associated clearing entries have been reversed.'),
                'type': 'success',
                'sticky': False,
            },
        }

    def unlink(self):
        """Override to cancel clearing entries before deletion."""
        for payment in self:
            if payment.is_clearing_payment and payment.state not in ['draft', 'cancelled']:
                self._cancel_clearing_entries(payment)
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