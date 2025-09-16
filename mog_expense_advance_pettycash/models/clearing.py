
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ExpenseAdvanceClearing(models.Model):
    _name = "hr.expense.advance.clearing"
    _description = "Advance Clearing Entry"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default=lambda self: self.env['ir.sequence'].next_by_code('hr.expense.advance.clearing'), required=True, tracking=True)
    advance_id = fields.Many2one('hr.expense.advance', required=True, ondelete='cascade', tracking=True)
    expense_sheet_id = fields.Many2one('hr.expense.sheet', string='Expense Sheet', required=True, tracking=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='advance_id.currency_id', store=True)
    diff_move_id = fields.Many2one('account.move', readonly=True, copy=False)
    state = fields.Selection([('draft','Draft'),('posted','Posted')], default='draft', tracking=True)

    def action_post(self):
        for rec in self:
            if rec.amount <= 0:
                raise UserError(_('Amount must be positive.'))
            advance_acct = rec.advance_id.advance_account_id
            sheet = rec.expense_sheet_id
            if not sheet.journal_id.default_account_id:
                raise UserError(_('Define default account on expense sheet journal.'))
            move_vals = {
                'move_type': 'entry',
                'journal_id': sheet.journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': _('Clear %s with %s') % (rec.advance_id.name, sheet.name or sheet.id),
                'line_ids': [
                    (0,0,{'name': _('Clear advance'), 'account_id': sheet.journal_id.default_account_id.id, 'debit': rec.amount}),
                    (0,0,{'name': _('Advance'), 'account_id': advance_acct.id, 'credit': rec.amount}),
                ]
            }
            move = self.env['account.move'].create(move_vals)
            move._post()
            rec.write({'diff_move_id': move.id, 'state': 'posted'})
