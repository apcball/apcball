
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class AdvanceClearWizard(models.TransientModel):
    _name = 'advance.clear.wizard'
    _description = 'Post All Pending Advance Clearings for Sheet'

    sheet_id = fields.Many2one('hr.expense.sheet', required=True)
    amount = fields.Monetary(related='sheet_id.total_amount', readonly=True)
    currency_id = fields.Many2one(related='sheet_id.currency_id', readonly=True)

    def action_post(self):
        clearings = self.env['hr.expense.advance.clearing'].search([('expense_sheet_id','=',self.sheet_id.id), ('state','=','draft')])
        for c in clearings:
            c.action_post()
        adv = clearings[:1].advance_id if clearings else False
        if adv and adv.balance_amount <= 0.0001:
            adv.action_set_cleared()
        return {'type':'ir.actions.act_window_close'}
