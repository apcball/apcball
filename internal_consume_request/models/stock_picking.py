# -*- coding: utf-8 -*-

from odoo import models

class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        # Call the original validate method
        res = super(StockPicking, self).button_validate()
        
        # After validation, find related internal consume requests
        requests = self.env['internal.consume.request'].search([
            ('picking_id', 'in', self.ids),
            ('state', '=', 'approved')
        ])
        
        # Mark them as done
        for req in requests:
            req.action_done()
            
        return res
