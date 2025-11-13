# Part of Odoo. See COPYRIGHT & LICENSE files for full copyright and licensing details.
from odoo import api, models, fields, _



class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    is_main_warehouse = fields.Boolean(string="Main Warehouse?")
