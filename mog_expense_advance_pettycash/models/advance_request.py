
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ExpenseAdvance(models.Model):
    _name = "hr.expense.advance"
    _description = "Expense Advance (Employee/Partner)"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Advance No.', default=lambda self: self.env['ir.sequence'].next_by_code('hr.expense.advance'), tracking=True, required=True)
    request_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', tracking=True)
    partner_id = fields.Many2one('res.partner', string='Partner (Vendor/Other)', tracking=True)
    partner_type = fields.Selection([('employee','Employee'),('partner','Partner')], compute='_compute_partner_type', store=True)
    amount = fields.Monetary(required=True, tracking=True)
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id.id, required=True)
    journal_id = fields.Many2one('account.journal', string='Payment Journal', required=True, domain=[('type','in',('cash','bank'))])
    advance_account_id = fields.Many2one('account.account', string='Advance Account', required=True,
        help='Receivable-like account to hold the advance (e.g., Employee Advance).')
    payment_move_id = fields.Many2one('account.move', readonly=True, copy=False)
    cleared_amount = fields.Monetary(compute='_compute_cleared', currency_field='currency_id', store=True)
    balance_amount = fields.Monetary(compute='_compute_cleared', currency_field='currency_id', store=True)
    state = fields.Selection([('draft','Draft'),('approved','Approved'),('paid','Paid'),('cleared','Cleared'),('cancel','Cancelled')], default='draft', tracking=True)

    @api.depends('employee_id','partner_id')
    def _compute_partner_type(self):
        for rec in self:
            rec.partner_type = 'employee' if rec.employee_id else 'partner'

    @api.depends('amount','clearing_ids.amount')
    def _compute_cleared(self):
        for rec in self:
            cleared = sum(rec.clearing_ids.mapped('amount'))
            rec.cleared_amount = cleared
            rec.balance_amount = rec.amount - cleared

    clearing_ids = fields.One2many('hr.expense.advance.clearing', 'advance_id', string='Clearings')

    def action_approve(self):
        self.write({'state':'approved'})

    def action_register_payment(self):
        for rec in self:
            if rec.state not in ('approved','draft'):
                continue
            if not rec.journal_id.default_account_id:
                raise UserError(_('Define default account on payment journal.'))
            move_vals = {
                'move_type': 'entry',
                'journal_id': rec.journal_id.id,
                'date': fields.Date.context_today(self),
                'ref': _('Advance %s') % rec.name,
                'line_ids': [
                    (0,0,{'name': _('Advance paid'), 'account_id': rec.advance_account_id.id, 'debit': rec.amount}),
                    (0,0,{'name': _('Bank/Cash'), 'account_id': rec.journal_id.default_account_id.id, 'credit': rec.amount}),
                ]
            }
            move = self.env['account.move'].create(move_vals)
            move._post()
            rec.payment_move_id = move.id
            rec.state = 'paid'

    def action_set_cleared(self):
        for rec in self:
            if rec.balance_amount > 0.0001:
                raise UserError(_('Cannot set to cleared until balance is zero.'))
            rec.state = 'cleared'
