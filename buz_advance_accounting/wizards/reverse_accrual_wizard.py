# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ReverseAccrualWizard(models.TransientModel):
    _name = 'reverse.accrual.wizard'
    _description = 'Reverse All Accrual Entries Wizard'

    purchase_id = fields.Many2one('purchase.order', required=True, readonly=True)
    reversal_date = fields.Date(
        string='Reversal Date', 
        required=True, 
        default=fields.Date.context_today,
        help='Date for the reversal journal entries'
    )
    accrual_count = fields.Integer(
        string='Accrual Entries to Reverse',
        compute='_compute_accrual_count'
    )
    accrual_ids = fields.One2many(
        related='purchase_id.advance_accrual_ids',
        readonly=True
    )

    @api.depends('purchase_id')
    def _compute_accrual_count(self):
        for wizard in self:
            if wizard.purchase_id:
                wizard.accrual_count = len(wizard.purchase_id.advance_accrual_ids.filtered(
                    lambda a: a.state == 'posted'
                ))
            else:
                wizard.accrual_count = 0

    def action_reverse_all(self):
        """Reverse all accrual entries with the specified date"""
        self.ensure_one()
        
        if not self.purchase_id:
            raise UserError(_('No Purchase Order provided.'))
        
        if not self.reversal_date:
            raise UserError(_('Please specify a reversal date.'))
        
        accruals_to_reverse = self.purchase_id.advance_accrual_ids.filtered(
            lambda a: a.state == 'posted'
        )
        
        if not accruals_to_reverse:
            raise UserError(_('No accrual entries found to reverse.'))
        
        reversed_count = 0
        for accrual in accruals_to_reverse:
            if accrual.state != 'posted':
                continue
                
            if not accrual.move_id or accrual.move_id.state != 'posted':
                continue
            
            move = accrual.move_id
            # Create reversal move with specified date
            reversal_vals = {
                'move_type': 'entry',
                'date': self.reversal_date,
                'journal_id': move.journal_id.id,
                'ref': (move.ref or '') + _(' (Reversal)'),
                'partner_id': move.partner_id.id,
                'currency_id': move.currency_id.id,
                'line_ids': []
            }
            
            # Create reversed lines
            for line in move.line_ids:
                line_vals = {
                    'name': line.name + _(' (Reversal)'),
                    'account_id': line.account_id.id,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'debit': line.credit,  # Reverse debit/credit
                    'credit': line.debit,
                    'currency_id': line.currency_id.id if line.currency_id else False,
                    'amount_currency': -line.amount_currency if line.amount_currency else 0.0,
                }
                reversal_vals['line_ids'].append((0, 0, line_vals))
            
            reversal = self.env['account.move'].create(reversal_vals)
            reversal.action_post()
            accrual.reversal_move_id = reversal.id
            accrual.state = 'reversed'
            reversed_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reversal Complete'),
                'message': _('%s accrual entries reversed on %s.') % (
                    reversed_count, 
                    self.reversal_date.strftime('%d/%m/%Y')
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        """Cancel the wizard"""
        return {'type': 'ir.actions.act_window_close'}
