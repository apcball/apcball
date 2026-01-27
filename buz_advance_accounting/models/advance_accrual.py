# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseAdvanceAccrual(models.Model):
    _name = 'purchase.advance.accrual'
    _description = 'PO Advance Accrual Entry'
    _order = 'id desc'

    name = fields.Char(string='Reference', default=lambda self: _('PO Advance Accrual'))
    purchase_id = fields.Many2one('purchase.order', required=True, ondelete='cascade', index=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', required=True, ondelete='cascade')
    amount = fields.Monetary(string='Accrued Amount', currency_field='currency_id', required=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
    ], default='posted', required=True)
    reversal_move_id = fields.Many2one('account.move', string='Reversal Entry', ondelete='set null')
    date = fields.Date(default=fields.Date.context_today)
    
    # Exchange rate fields
    exchange_rate = fields.Float(string='Exchange Rate (USD→THB)', digits=(12, 6), 
                                  help='Exchange rate used when creating the accrual')
    amount_thb = fields.Monetary(string='Amount in THB', currency_field='company_currency_id')
    company_currency_id = fields.Many2one('res.currency', related='purchase_id.company_id.currency_id', store=False)

    def action_reverse(self):
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only posted accruals can be reversed.'))
            if not rec.move_id or rec.move_id.state != 'posted':
                raise UserError(_('Related journal entry must be posted.'))
            
            move = rec.move_id
            # Create reversal move manually for better compatibility
            reversal_vals = {
                'move_type': 'entry',
                'date': fields.Date.context_today(self),
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
            rec.reversal_move_id = reversal.id
            rec.state = 'reversed'
        return True
