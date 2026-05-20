# -*- coding: utf-8 -*-

from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    unbuild_id = fields.Many2one(
        "mrp.unbuild",
        string="Unbuild Order",
        copy=False,
        readonly=True,
        ondelete="set null",
    )

    def button_validate(self):
        res = super().button_validate()
        done_pickings = self.filtered(lambda picking: picking.state == "done" and picking.unbuild_id)
        if done_pickings:
            # Move unbuild to 'confirm' state — user must press "Confirm Done"
            # to trigger standard BOM explosion via _perform_done()
            done_pickings.mapped("unbuild_id").filtered(
                lambda ub: ub.state == "picking"
            ).write({"state": "confirm"})
        return res
