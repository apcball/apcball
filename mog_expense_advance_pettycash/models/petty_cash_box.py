
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PettyCashBox(models.Model):
    _name = "account.petty.cash.box"
    _description = "Petty Cash Box"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(default=lambda self: self.env['ir.sequence'].next_by_code('petty.cash.box'), required=True, tracking=True)
    owner_id = fields.Many2one('res.partner', string='Owner (Employee/Partner)', tracking=True, required=True)
    journal_id = fields.Many2one('account.journal', domain=[('type','=','cash')], required=True, tracking=True,
                                 help='Cash journal representing this petty cash box.')
    currency_id = fields.Many2one(related='journal_id.currency_id', store=True)
    active = fields.Boolean(default=True)
    balance = fields.Monetary(compute='_compute_balance', currency_field='currency_id', store=False)
    move_ids = fields.One2many('account.move', 'petty_cash_box_id', string='Moves')

    @api.depends('move_ids.line_ids.balance')
    def _compute_balance(self):
        for box in self:
            # Balance = sum of cash account move lines assigned to this box (debit-credit)
            balance = 0.0
            for move in box.move_ids:
                for line in move.line_ids.filtered(lambda l: l.account_id == box.journal_id.default_account_id):
                    balance += line.debit - line.credit
            box.balance = balance

    def action_replenish(self, amount, src_journal):
        self.ensure_one()
        if amount <= 0:
            raise UserError(_('Amount must be positive.'))
        if not self.journal_id.default_account_id:
            raise UserError(_('Define default account on cash journal.'))
        if not src_journal.default_account_id:
            raise UserError(_('Define default account on source journal.'))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': self.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': _('Replenish petty cash %s') % self.name,
            'petty_cash_box_id': self.id,
            'line_ids': [
                (0,0,{
                    'name': _('Replenish petty cash'),
                    'account_id': self.journal_id.default_account_id.id,
                    'debit': amount,
                }),
                (0,0,{
                    'name': _('From %s') % src_journal.name,
                    'account_id': src_journal.default_account_id.id,
                    'credit': amount,
                }),
            ]
        })
        move._post()
        return move
