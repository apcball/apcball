# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PettyCashReplenishWizard(models.TransientModel):
    _name = 'petty.cash.replenish.wizard'
    _description = 'Petty Cash Replenish Wizard'

    box_id = fields.Many2one('account.petty.cash.box', string='Petty Cash Box', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True,
                                  default=lambda self: self.env.company.currency_id.id)
    src_journal_id = fields.Many2one('account.journal', string='Source Journal', required=True,
                                     domain=[('type', 'in', ('cash', 'bank'))])

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # If opened from petty cash box, default the box
        box_id = self.env.context.get('default_box_id') or self.env.context.get('active_id')
        if box_id:
            res.setdefault('box_id', box_id)
        return res

    def action_confirm(self):
        self.ensure_one()
        if not self.src_journal_id:
            raise UserError(_('Select source journal.'))
        if not self.amount or self.amount <= 0:
            raise UserError(_('Enter a positive amount.'))
        box = self.box_id
        if not box:
            raise UserError(_('No petty cash box selected.'))

        # Call existing method which creates and posts the replenishment move
        box.action_replenish(self.amount, self.src_journal_id)

        return {'type': 'ir.actions.act_window_close'}
