from odoo import fields, models


class StockCountAdjustmentImport(models.TransientModel):
    _name = 'stock.count.adjustment.import'
    _description = 'Stock Count Adjustment Import Wizard'

    adjustment_id = fields.Many2one('stock.count.adjustment')
