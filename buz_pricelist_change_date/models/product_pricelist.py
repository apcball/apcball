# -*- coding: utf-8 -*-

from odoo import models, fields


class ProductPricelist(models.Model):
    """Inherit product.pricelist to add the change date functionality"""
    _inherit = 'product.pricelist'

    def action_change_pricelist_date(self):
        """
        Open the wizard to change dates for all pricelist items
        """
        self.ensure_one()
        return {
            'name': 'Change Pricelist Dates',
            'type': 'ir.actions.act_window',
            'res_model': 'pricelist.change.date.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_pricelist_id': self.id,
            }
        }