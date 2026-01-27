# -*- coding: utf-8 -*-
from odoo import models, api

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _action_done(self):
        res = super(StockPicking, self)._action_done()
        for picking in self:
            # Find related internal consume requests
            requests = self.env['internal.consume.request'].search([
                ('picking_id', '=', picking.id),
                ('state', '=', 'issued')
            ])
            if requests:
                requests.write({'state': 'done'})
        return res
