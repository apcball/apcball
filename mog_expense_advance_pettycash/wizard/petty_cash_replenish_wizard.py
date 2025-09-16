
# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class PettyCashReplenishWizard(models.TransientModel):
    _name = 'petty.cash.replenish.wizard'
    _description = 'Replenish Petty Cash'

    box_id = fields.Many2one('account.petty.cash.box', required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='box_id.currency_id', readonly=True)
    src_journal_id = fields.Many2one('account.journal', string='Source Journal', domain=[('type','in',('bank','cash'))], required=True)

    def action_confirm(self):
        self.ensure_one()
        self.box_id.action_replenish(self.amount, self.src_journal_id)
        return {'type': 'ir.actions.act_window_close'}
