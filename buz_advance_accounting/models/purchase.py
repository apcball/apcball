# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    advance_accrual_ids = fields.One2many('purchase.advance.accrual', 'purchase_id', string='Advance Accruals')
    advance_accrual_count = fields.Integer(compute='_compute_advance_accrual_count')

    def _compute_advance_accrual_count(self):
        for order in self:
            order.advance_accrual_count = len(order.advance_accrual_ids)

    def action_open_advance_accruals(self):
        self.ensure_one()
        action = self.env.ref('buz_advance_accounting.action_purchase_advance_accrual').read()[0]
        action['domain'] = [('purchase_id', '=', self.id)]
        action['context'] = {
            'default_purchase_id': self.id,
        }
        return action

    def action_open_advance_bill_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Advance Accrual'),
            'res_model': 'purchase.advance.bill.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('buz_advance_accounting.view_advance_bill_wizard_form').id,
            'target': 'new',
            'context': {
                'default_purchase_id': self.id,
                'default_amount': self.amount_total,  # Changed from amount_untaxed to amount_total
                'default_currency_id': self.currency_id.id,
            }
        }

    def action_reverse_all_advance_accruals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reverse All Accrual Entries'),
            'res_model': 'reverse.accrual.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('buz_advance_accounting.view_reverse_accrual_wizard_form').id,
            'target': 'new',
            'context': {
                'default_purchase_id': self.id,
            }
        }

