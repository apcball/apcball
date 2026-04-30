# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    unbuild_id = fields.Many2one(
        'mrp.unbuild',
        string='Unbuild Order',
        copy=False,
        readonly=True,
        ondelete='set null',
    )

    def button_validate(self):
        res = super().button_validate()
        done_pickings = self.filtered(lambda picking: picking.state == 'done' and picking.unbuild_id)
        if done_pickings:
            done_pickings.mapped('unbuild_id').write({'state': 'done'})
        return res
